"""Tests for yoyo-py skills system."""

import pytest
from pathlib import Path
from src.skills import SkillSet, Skill


class TestSkill:
    def test_to_prompt(self):
        skill = Skill(name="test", description="A test skill", tools=["bash"], content="Do stuff.")
        prompt = skill.to_prompt()
        assert "test" in prompt
        assert "A test skill" in prompt
        assert "bash" in prompt
        assert "Do stuff." in prompt


class TestSkillSet:
    def test_empty(self):
        s = SkillSet()
        assert s.is_empty()
        assert s.count() == 0

    def test_load_skills(self, tmp_path):
        # Create a skill directory with SKILL.md
        skill_dir = tmp_path / "my_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my_skill\ndescription: Test skill\ntools: [bash]\n---\n# My Skill\nDo things."
        )
        s = SkillSet()
        s.load(str(tmp_path))
        assert s.count() == 1
        assert "my_skill" in s.skills

    def test_load_multiple_skills(self, tmp_path):
        for name in ("skill_a", "skill_b"):
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(
                f"---\nname: {name}\n---\n# {name}"
            )
        s = SkillSet()
        s.load(str(tmp_path))
        assert s.count() == 2

    def test_load_nonexistent_dir(self):
        s = SkillSet()
        s.load("/nonexistent/path")
        assert s.is_empty()

    def test_to_prompt(self, tmp_path):
        d = tmp_path / "test_skill"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: test\n---\nTest content.")
        s = SkillSet()
        s.load(str(tmp_path))
        prompt = s.to_prompt()
        assert "test" in prompt
        assert "Test content." in prompt

    def test_all(self, tmp_path):
        d = tmp_path / "skill1"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: skill1\n---\nContent1.")
        s = SkillSet()
        s.load(str(tmp_path))
        all_skills = s.all()
        assert len(all_skills) == 1
        assert all_skills[0][0] == "skill1"
