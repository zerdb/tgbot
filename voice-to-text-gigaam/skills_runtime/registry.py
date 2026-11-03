"""Skill registry: validates routing and returns uniform results."""
from __future__ import annotations

from .base import Skill, SkillContext
from .contracts import SkillMessage, SkillResult


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        name = getattr(skill, "name", "")
        if not name or name in self._skills:
            raise ValueError(f"Invalid or duplicate skill name: {name!r}")
        self._skills[name] = skill

    def describe(self) -> list[dict[str, str]]:
        return [
            {"name": skill.name, "description": skill.description}
            for skill in self._skills.values()
        ]

    def dispatch(self, message: SkillMessage) -> SkillResult:
        skill = self._skills.get(message.to_skill)
        if skill is None:
            return SkillResult.failure(message, message.to_skill,
                                       f"Skill is not registered: {message.to_skill}")
        try:
            context = SkillContext(self, message.task_id)
            data = skill.handle(message, context)
            if not isinstance(data, dict):
                raise TypeError("A skill must return a dictionary.")
            return SkillResult.success(message, skill.name, data)
        except Exception as exc:
            return SkillResult.failure(message, skill.name, f"{type(exc).__name__}: {exc}")

    def execute(self, to_skill: str, action: str,
                inputs: dict | None = None) -> SkillResult:
        return self.dispatch(SkillMessage.create(to_skill, action, inputs))
