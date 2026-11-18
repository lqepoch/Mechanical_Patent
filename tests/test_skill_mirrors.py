"""防止中文技能变更后 Codex 的注册目录未同步。"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SkillMirrorTests(unittest.TestCase):
    def test_repository_skills_are_canonical_and_discoverable(self):
        sources = sorted((ROOT / "skills").glob("*/SKILL.md"))
        mirrors = sorted((ROOT / ".agents" / "skills").glob("*/SKILL.md"))
        self.assertGreaterEqual(len(sources), 14)
        self.assertEqual({x.parent.name for x in sources},
                         {x.parent.name for x in mirrors})
        for path in sources:
            with self.subTest(skill=path.parent.name):
                mirror = ROOT / ".agents" / "skills" / path.parent.name / "SKILL.md"
                data = path.read_text(encoding="utf-8")
                self.assertEqual(data, mirror.read_text(encoding="utf-8"))
                self.assertTrue(data.startswith("---\nname: "))
                self.assertIn("description:", data[:600])
                self.assertTrue(any("\u4e00" <= char <= "\u9fff" for char in data[:800]))
                self.assertNotIn("PATENT_LLM_BASE_URL=", data)
                self.assertNotIn("PATENT_LLM_MODEL=", data)


if __name__ == "__main__":
    unittest.main()
