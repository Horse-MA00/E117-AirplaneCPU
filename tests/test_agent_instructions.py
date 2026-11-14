"""Keep the shared AI instructions short and CLAUDE.md a pure import of AGENTS.md."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AgentInstructionTests(unittest.TestCase):
    def test_agents_md_stays_within_100_lines(self):
        lines = (ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len(lines), 100, "AGENTS.md must stay within 100 lines; move details into docs/.")

    def test_claude_md_only_imports_agents_md(self):
        text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        content = [line.strip() for line in re.sub(r"<!--.*?-->", "", text, flags=re.S).splitlines() if line.strip()]
        self.assertEqual(content, ["@AGENTS.md"], "Edit AGENTS.md; CLAUDE.md must only contain the @AGENTS.md import.")


if __name__ == "__main__":
    unittest.main()
