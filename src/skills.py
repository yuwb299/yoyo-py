"""Skills system — load markdown skill files with YAML frontmatter."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Skill:
    """A single skill loaded from a SKILL.md file."""
    name: str
    description: str = ""
    tools: list[str] = field(default_factory=list)
    content: str = ""

    def to_prompt(self) -> str:
        """Format skill for injection into system prompt."""
        parts = [f"## Skill: {self.name}"]
        if self.description:
            parts.append(f"Description: {self.description}")
        if self.tools:
            parts.append(f"Tools: {', '.join(self.tools)}")
        parts.append(self.content)
        return "\n".join(parts)


class SkillSet:
    """Collection of skills loaded from directories."""

    def __init__(self):
        self.skills: dict[str, Skill] = {}

    def load(self, directory: str) -> None:
        """Load all SKILL.md files from a directory tree."""
        dir_path = Path(directory)
        if not dir_path.exists():
            return

        for skill_dir in sorted(dir_path.iterdir()):
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skill = self._parse_skill(skill_dir.name, skill_file)
                    if skill:
                        self.skills[skill.name] = skill

    def is_empty(self) -> bool:
        return len(self.skills) == 0

    def count(self) -> int:
        return len(self.skills)

    def all(self) -> list[tuple[str, str]]:
        return [(s.name, s.content) for s in self.skills.values()]

    def to_prompt(self) -> str:
        return "\n\n".join(s.to_prompt() for s in self.skills.values())

    def _parse_skill(self, name: str, path: Path) -> Skill | None:
        """Parse a SKILL.md with YAML frontmatter."""
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return None

        # Parse YAML frontmatter (between --- delimiters)
        description = ""
        tools: list[str] = []
        content = text

        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
        if fm_match:
            frontmatter = fm_match.group(1)
            content = fm_match.group(2).strip()

            for line in frontmatter.splitlines():
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip()
                elif line.startswith("tools:"):
                    tools_str = line.split(":", 1)[1].strip()
                    if tools_str.startswith("[") and tools_str.endswith("]"):
                        tools = [t.strip().strip("'\"") for t in tools_str[1:-1].split(",") if t.strip()]

        return Skill(name=name, description=description, tools=tools, content=content)
