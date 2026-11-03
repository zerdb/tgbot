"""File discovery skill. It finds files but never changes or deletes them."""
from pathlib import Path

from skills_runtime.base import Skill, SkillContext
from skills_runtime.contracts import SkillMessage


class FilesSkill(Skill):
    name = "files"
    description = "Find files by folder, glob pattern and optional name fragment."

    def handle(self, message: SkillMessage, context: SkillContext) -> dict:
        if message.action != "find":
            raise ValueError(f"Unsupported action: {message.action}")
        folder = Path(message.inputs["folder"]).expanduser().resolve()
        pattern = str(message.inputs.get("pattern", "*.xlsx"))
        contains = str(message.inputs.get("contains", "")).casefold()
        limit = max(1, min(int(message.inputs.get("limit", 100)), 500))
        if not folder.is_dir():
            raise NotADirectoryError(str(folder))
        found = []
        for path in folder.glob(pattern):
            if path.is_file() and contains in path.name.casefold():
                found.append({"path": str(path.resolve()), "name": path.name,
                              "size_bytes": path.stat().st_size})
                if len(found) >= limit:
                    break
        return {"files": found, "count": len(found), "folder": str(folder)}
