import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.cli import main


class NativeAgentCLITests(unittest.TestCase):
    def test_research_requires_no_model_or_api_key(self):
        with tempfile.TemporaryDirectory() as root:
            case = Path(root) / "case"
            code = main(["research", "--direction", "Adaptive firefighting pump",
                         "--patent-provider", "none", "--paper-provider", "none",
                         "--case-dir", str(case)])
            self.assertEqual(code, 0)
            intake = json.loads((case / "00_intake.json").read_text(encoding="utf-8"))
            self.assertFalse(intake["llm_api_required"])
            self.assertEqual(intake["workflow"], "agent_native")
            self.assertEqual(main(["validate", "--case-dir", str(case)]), 2)

    def test_paper_terms_need_data_access_approval(self):
        with tempfile.TemporaryDirectory() as root:
            code = main(["research", "--direction", "Valve",
                         "--paper-query", "cavitation dynamics",
                         "--patent-provider", "none",
                         "--case-dir", str(Path(root) / "case")])
            self.assertEqual(code, 3)
            self.assertFalse((Path(root) / "case").exists())


if __name__ == "__main__":
    unittest.main()
