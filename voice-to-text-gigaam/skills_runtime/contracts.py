"""Stable, JSON-serializable messages exchanged between skills."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class SkillMessage:
    task_id: str
    from_skill: str
    to_skill: str
    action: str
    inputs: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, to_skill: str, action: str, inputs: dict[str, Any] | None = None,
               from_skill: str = "assistant", task_id: str | None = None) -> "SkillMessage":
        return cls(task_id or uuid4().hex, from_skill, to_skill, action, inputs or {})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SkillResult:
    task_id: str
    skill: str
    status: str
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def success(cls, message: SkillMessage, skill: str, result: dict[str, Any]) -> "SkillResult":
        return cls(message.task_id, skill, "completed", result=result)

    @classmethod
    def failure(cls, message: SkillMessage, skill: str, error: str) -> "SkillResult":
        return cls(message.task_id, skill, "failed", error=error)
