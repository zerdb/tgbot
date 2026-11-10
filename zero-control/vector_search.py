"""Local semantic file-name search backed by a separate SQLite index.

The main MFT/FTS5 index remains the source of truth. Embeddings contain only
file names and paths, are generated on the local CPU, and are stored separately.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from agent_core import APP_DATA
from file_indexer import DB_PATH as FILE_DB_PATH

MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
VECTOR_DB_PATH = APP_DATA / "vector_index.sqlite3"
MODEL_CACHE = APP_DATA / "models"
EMBEDDING_BATCH_SIZE = 32
SCAN_BATCH_SIZE = 1024
MIN_SIMILARITY = 0.30

_LOCK = threading.RLock()
_MODEL = None
_TOKENIZER = None
_TORCH = None


def _report(callback: Callable[[str], None] | None, message: str) -> None:
    if callback:
        callback(message)


def _load_model():
    """Load the multilingual model lazily; inference always runs on CPU."""
    global _MODEL, _TOKENIZER, _TORCH
    if _MODEL is not None:
        return _TOKENIZER, _MODEL, _TORCH

    os.environ.setdefault("HF_HOME", str(MODEL_CACHE))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    import torch
    from transformers import AutoModel, AutoTokenizer

    # Keep background indexing responsive on everyday Windows machines.
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    MODEL_CACHE.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, cache_dir=str(MODEL_CACHE))
    model = AutoModel.from_pretrained(MODEL_ID, cache_dir=str(MODEL_CACHE))
    model.to("cpu")
    model.eval()
    _TOKENIZER, _MODEL, _TORCH = tokenizer, model, torch
    return _TOKENIZER, _MODEL, _TORCH


def _embed(texts: list[str]) -> np.ndarray:
    tokenizer, model, torch = _load_model()
    encoded = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=128,
        return_tensors="pt",
    )
    with torch.inference_mode():
        hidden = model(**encoded).last_hidden_state
        mask = encoded["attention_mask"].unsqueeze(-1).to(hidden.dtype)
        pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
        vectors = torch.nn.functional.normalize(pooled, p=2, dim=1)
    return vectors.cpu().numpy().astype(np.float32, copy=False)


def _document_text(full_path: str, name: str) -> str:
    path = Path(full_path)
    parent = path.parent.name
    grandparent = path.parent.parent.name
    # The full path is retained as context, while the filename comes first.
    return f"{name} | {parent} | {grandparent} | {full_path}"


def _connect_vector_db() -> sqlite3.Connection:
    APP_DATA.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(VECTOR_DB_PATH, timeout=15)
    connection.execute("PRAGMA busy_timeout=15000")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS file_embeddings (
            full_path TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            model_id TEXT NOT NULL,
            embedding BLOB NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_file_embeddings_model "
        "ON file_embeddings(model_id)"
    )
    return connection


def _sync_index(report: Callable[[str], None] | None = None) -> int:
    """Synchronize embeddings with the already-built MFT file inventory."""
    if not FILE_DB_PATH.is_file():
        raise RuntimeError("Основной индекс файлов ещё не создан.")

    with sqlite3.connect(FILE_DB_PATH, timeout=15) as source:
        inventory = source.execute(
            "SELECT full_path, name FROM files"
        ).fetchall()

    if not inventory:
        _report(report, "В основном индексе пока нет файлов для векторизации.")
        return 0

    connection = _connect_vector_db()
    try:
        existing = {
            path: (name, model_id)
            for path, name, model_id in connection.execute(
                "SELECT full_path, name, model_id FROM file_embeddings"
            )
        }
        current_paths = {path for path, _ in inventory}
        stale_paths = [path for path in existing if path not in current_paths]
        if stale_paths:
            connection.executemany(
                "DELETE FROM file_embeddings WHERE full_path = ?",
                ((path,) for path in stale_paths),
            )

        pending = [
            (path, name)
            for path, name in inventory
            if existing.get(path) != (name, MODEL_ID)
        ]
        _report(
            report,
            f"Векторный индекс: файлов {len(inventory):,}; "
            f"новых или изменённых записей {len(pending):,}.",
        )

        for offset in range(0, len(pending), EMBEDDING_BATCH_SIZE):
            batch = pending[offset:offset + EMBEDDING_BATCH_SIZE]
            texts = [_document_text(path, name) for path, name in batch]
            vectors = _embed(texts)
            connection.executemany(
                """
                INSERT OR REPLACE INTO file_embeddings
                    (full_path, name, model_id, embedding)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (path, name, MODEL_ID, vector.tobytes())
                    for (path, name), vector in zip(batch, vectors)
                ],
            )
            connection.commit()
            completed = min(offset + len(batch), len(pending))
            _report(
                report,
                f"Векторизация: обработано {completed:,} из {len(pending):,}.",
            )
        return len(pending)
    finally:
        connection.close()


def search_similar(
    query: str,
    top_k: int = 1000,
    report: Callable[[str], None] | None = None,
) -> list[Path]:
    """Return locally ranked paths; any failure is handled by the caller."""
    query = str(query or "").strip()
    if not query:
        return []

    with _LOCK:
        _report(report, "Запускаю локальный семантический поиск…")
        _sync_index(report)
        query_vector = _embed([query])[0]

        connection = _connect_vector_db()
        try:
            cursor = connection.execute(
                "SELECT full_path, embedding FROM file_embeddings WHERE model_id = ?",
                (MODEL_ID,),
            )
            best: list[tuple[float, str]] = []
            while True:
                rows = cursor.fetchmany(SCAN_BATCH_SIZE)
                if not rows:
                    break
                paths = [row[0] for row in rows]
                matrix = np.stack(
                    [
                        np.frombuffer(row[1], dtype=np.float32, count=query_vector.size)
                        for row in rows
                    ]
                )
                scores = matrix @ query_vector
                keep_count = min(top_k, len(scores))
                if keep_count <= 0:
                    continue
                indices = np.argpartition(scores, -keep_count)[-keep_count:]
                best.extend(
                    (float(scores[index]), paths[index])
                    for index in indices
                    if float(scores[index]) >= MIN_SIMILARITY
                )
                if len(best) > top_k * 2:
                    best = sorted(best, key=lambda item: item[0], reverse=True)[:top_k]

            best.sort(key=lambda item: item[0], reverse=True)
            result = [Path(path) for _, path in best[:top_k]]
            _report(report, f"Локальный семантический поиск: найдено {len(result)} кандидатов.")
            return result
        finally:
            connection.close()
