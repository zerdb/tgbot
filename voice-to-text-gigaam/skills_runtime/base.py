"""Base class and context for skill-to-skill communication."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

from .contracts import SkillMessage, SkillResult

if TYPE_CHECKING:
    from .registry import SkillRegistry


class SkillContext:
    def __init__(self, registry: "SkillRegistry", task_id: str):
        self.registry = registry
        self.task_id = task_id

    def call(self, to_skill: str, action: str, inputs: dict[str, Any],
             from_skill: str) -> SkillResult:
        message = SkillMessage.create(
            to_skill=to_skill, action=action, inputs=inputs,
            from_skill=from_skill, task_id=self.task_id,
        )
        return self.registry.dispatch(message)


class Skill(ABC):
    name: str
    description: str

    @abstractmethod
    def handle(self, message: SkillMessage, context: SkillContext) -> dict[str, Any]:
        """Execute one documented action and return JSON-serializable data."""
