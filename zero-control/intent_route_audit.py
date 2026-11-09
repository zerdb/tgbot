#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zero Control: аудит маршрутизации 500 русскоязычных команд.

Положить файл рядом с intent_router.py и запустить:
    python intent_route_audit.py

По умолчанию:
- использует настоящий understand_command() и локальные пользовательские правила;
- отключает сетевой ИИ, чтобы безопасно и бесплатно проверить локальную маршрутизацию;
- НЕ выполняет команды Windows, не открывает приложения, не удаляет файлы;
- сохраняет только ошибки/расхождения в CSV.

Для проверки семантического слоя:
    python intent_route_audit.py --with-ai --ai-limit 50

В режиме --with-ai будут использованы настроенные провайдеры Groq/Moondream.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

try:
    import intent_router as router
except ImportError as exc:
    raise SystemExit(
        "Не найден intent_router.py. Положите этот скрипт в папку zero-control "
        "рядом с intent_router.py."
    ) from exc


# 50 исходных фраз × 10 речевых/ASR-вариантов = ровно 500 тестов.
# expected_action — ожидаемое намерение, а не факт успешного выполнения действия.
SEEDS = [
    ("inspect_screen", "Сделай скриншот экрана"),
    ("inspect_screen", "Посмотри, что у меня на экране"),
    ("inspect_screen", "Сними изображение монитора"),
    ("open_settings", "Открой настройки Windows"),
    ("open_settings", "Покажи системные параметры компьютера"),
    ("open_assistant_settings", "Открой настройки Zero Control"),
    ("open_assistant_settings", "Покажи настройки помощника"),
    ("open_downloads", "Открой папку Загрузки"),
    ("open_downloads", "Покажи скачанные файлы"),
    ("open_recycle_bin", "Открой корзину"),
    ("empty_recycle_bin", "Очисти корзину"),
    ("empty_recycle_bin", "Опустоши корзину Windows"),
    ("lock_computer", "Заблокируй компьютер"),
    ("lock_computer", "Заблокируй мой ноутбук"),
    ("reboot_computer", "Перезагрузи компьютер"),
    ("reboot_computer", "Перезапусти Windows"),
    ("read_unread_mail", "Прочитай непрочитанные письма"),
    ("read_unread_mail", "Проверь новые письма во входящих"),
    ("open_mail_client", "Открой почтовый клиент"),
    ("open_mail_client", "Покажи мою почту"),
    ("open_contacts", "Открой контакты"),
    ("open_contacts", "Покажи адресную книгу"),
    ("add_contact", "Добавь новый контакт"),
    ("add_contact", "Создай контакт в адресной книге"),
    ("reminder", "Напомни мне купить молоко"),
    ("reminder", "Создай напоминание позвонить Петру"),
    ("open_reminders", "Открой список напоминаний"),
    ("open_reminders", "Покажи мои дела и задачи"),
    ("add_note", "Запомни купить хлеб как заметку"),
    ("add_note", "Запиши позвонить мастеру в заметки"),
    ("save_note", "Сохрани буфер обмена как заметку"),
    ("complete_item", "Отметь оплату счёта выполненной"),
    ("complete_item", "Пометь задачу позвонить Петру готовой"),
    ("organize_folder", "Разбери папку Документы"),
    ("organize_folder", "Рассортируй файлы по папкам"),
    ("email_compose", "Отправь письмо Иванову"),
    ("email_compose", "Отправь на почту файлы Шамилю"),
    ("open_application", "Открой блокнот"),
    ("open_application", "Запусти калькулятор"),
    ("open_installed_application", "Открой Telegram"),
    ("open_installed_application", "Запусти Paint"),
    ("search_web", "Найди погоду в интернете"),
    ("search_web", "Поищи новости в Google"),
    ("search_files", "Найди файл договор"),
    ("search_files", "Поищи документы PDF"),
    ("search_files", "Найди файлы больше 10 ГБ"),
    ("open_folder", "Найди папку Архив"),
    ("open_folder", "Открой папку Проекты"),
    # Контрольные неоднозначные фразы: не должны запускать опасное действие.
    ("unknown", "Перезагрузи"),
    ("unknown", "Очисти"),
]

VARIANTS = [
    lambda s: s,
    lambda s: "Пожалуйста, " + s[:1].lower() + s[1:],
    lambda s: "Мне нужно, чтобы ты " + s[:1].lower() + s[1:],
    lambda s: s + ", пожалуйста",
    lambda s: "Будь добр, " + s[:1].lower() + s[1:],
    lambda s: s + ".",
    lambda s: s.lower(),
    lambda s: "Слушай, " + s[:1].lower() + s[1:],
    lambda s: "Пожалуйста, мне нужно " + s[:1].lower() + s[1:],
    lambda s: s + " на компьютере",
]


def build_cases():
    cases = []
    for seed_id, (expected, phrase) in enumerate(SEEDS, start=1):
        for variant_id, transform in enumerate(VARIANTS, start=1):
            cases.append({
                "case_id": f"{seed_id:02d}-{variant_id:02d}",
                "seed": phrase,
                "phrase": transform(phrase),
                "expected_action": expected,
            })
    return cases


def compact_json(value):
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def run():
    parser = argparse.ArgumentParser(description="Аудит 500 фраз маршрутизатора Zero Control")
    parser.add_argument("--output", default="intent_route_errors.csv",
                        help="CSV-файл только с ошибками (по умолчанию intent_route_errors.csv)")
    parser.add_argument("--with-ai", action="store_true",
                        help="Разрешить реальные вызовы Groq/Moondream для тестовых фраз")
    parser.add_argument("--ai-limit", type=int, default=50,
                        help="Максимум семантических вызовов в режиме --with-ai (по умолчанию 50)")
    args = parser.parse_args()

    original_classifier = router._classify_semantically
    try:
        import local_intents as local_intents_module
        original_record_intent = local_intents_module.record_intent
        # Тестовые фразы не засоряют пользовательский журнал распознанных намерений.
        local_intents_module.record_intent = lambda *args, **kwargs: None
    except Exception:
        local_intents_module = None
        original_record_intent = None

    ai_calls = 0

    def counted_classifier(phrase):
        nonlocal ai_calls
        ai_calls += 1
        return original_classifier(phrase)

    def no_network_classifier(_phrase):
        raise RuntimeError("AI отключён параметрами теста; проверяется локальный fallback")

    failures = []
    counts = Counter()
    cases = build_cases()

    try:
        for case in cases:
            phrase = case["phrase"]
            expected = case["expected_action"]
            semantic_allowed = bool(args.with_ai and ai_calls < max(0, args.ai_limit))

            if not args.with_ai:
                router._classify_semantically = no_network_classifier
            elif not semantic_allowed:
                def limited_classifier(_phrase):
                    raise RuntimeError("Достигнут --ai-limit; проверяется локальный fallback")
                router._classify_semantically = limited_classifier
            else:
                router._classify_semantically = counted_classifier

            calls_before = ai_calls
            try:
                result = router.understand_command(phrase)
                actual = str(result.get("action") or "unknown")
                kind = str(result.get("kind") or "")
                confidence = result.get("confidence", "")
                params = result.get("parameters") or {}
                provider = "Groq/Moondream" if ai_calls > calls_before else "local"
                error = actual != expected
                status = "MISMATCH" if error else "OK"
                if error:
                    counts["mismatch"] += 1
                    failures.append({
                        **case,
                        "actual_action": actual,
                        "kind": kind,
                        "confidence": confidence,
                        "parameters": compact_json(params),
                        "provider": provider,
                        "status": status,
                        "note": "Ожидаемое и фактическое действия различаются",
                    })
                else:
                    counts["ok"] += 1
            except Exception as exc:
                counts["exception"] += 1
                failures.append({
                    **case,
                    "actual_action": "EXCEPTION",
                    "kind": "",
                    "confidence": "",
                    "parameters": "{}",
                    "provider": "",
                    "status": "EXCEPTION",
                    "note": f"{type(exc).__name__}: {exc}",
                })
    finally:
        router._classify_semantically = original_classifier
        if local_intents_module is not None and original_record_intent is not None:
            local_intents_module.record_intent = original_record_intent

    output = Path(args.output).resolve()
    fieldnames = [
        "case_id", "seed", "phrase", "expected_action", "actual_action",
        "kind", "confidence", "parameters", "provider", "status", "note",
    ]
    with output.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(failures)

    print("\n=== ZERO CONTROL: ROUTE AUDIT ===")
    print(f"Всего тестов:       {len(cases)}")
    print(f"Совпало:            {counts['ok']}")
    print(f"Расхождений:        {counts['mismatch']}")
    print(f"Исключений:         {counts['exception']}")
    print(f"Вызовов ИИ:         {ai_calls}")
    print(f"Ошибки сохранены:   {output}")
    print("\nВ CSV записаны только ошибки. Успешные фразы в отчёт не попадают.")

    if failures:
        print("\nПервые ошибки:")
        for item in failures[:20]:
            print(
                f"- [{item['case_id']}] {item['phrase']!r}: "
                f"ожидалось {item['expected_action']}, получено {item['actual_action']}"
            )
    else:
        print("\nРасхождений не обнаружено в выбранном наборе.")


if __name__ == "__main__":
    run()
