"""Keep docs/ indexed in AGENTS.md and current specifications aligned with code versions.

Every docs/*.md must carry a status line under its title and be linked from
AGENTS.md. A current specification declares the code it describes: version
constants (VERSION / *_VERSION / *_PROTOCOL in backend/, llm_agent/, simulation/)
or repository paths. Bumping a version constant without updating the documents
that declare the old value fails this test.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CURRENT = re.compile(r"^> 状态：现行 · 对应代码：(?P<refs>.+)$")
RECORD = re.compile(r"^> 状态：记录（\d{4}-\d{2}-\d{2}），内容不再修改$")
LOG = re.compile(r"^> 状态：日志，只追加新条目，不改旧条目$")
CONSTANT = re.compile(r"""^\s*[A-Z_]*(?:VERSION|PROTOCOL)\s*=\s*['"]([^'"]+)['"]""", re.M)


def _status_line(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    return next((line for line in lines[1:] if line.strip()), "")


def _code_versions():
    versions = set()
    for folder in ("backend", "llm_agent", "simulation"):
        for source in (ROOT / folder).rglob("*.py"):
            versions.update(CONSTANT.findall(source.read_text(encoding="utf-8")))
    return versions


class DocsIndexTests(unittest.TestCase):
    def test_every_doc_is_linked_from_agents_md(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        missing = [p.name for p in sorted(DOCS.glob("*.md")) if f"](docs/{p.name})" not in agents]
        self.assertEqual(missing, [], "Add these docs to the AGENTS.md document index.")

    def test_every_doc_has_a_valid_status_line(self):
        invalid = [p.name for p in sorted(DOCS.glob("*.md"))
                   if not any(rule.match(_status_line(p)) for rule in (CURRENT, RECORD, LOG))]
        self.assertEqual(invalid, [], "The second non-empty line must be a 状态 line (现行 / 记录 / 日志).")

    def test_current_specs_match_code_versions_and_paths(self):
        versions = _code_versions()
        self.assertIn("three-round-release-v1", versions, "version scan found no known constant")
        stale = []
        for path in sorted(DOCS.glob("*.md")):
            match = CURRENT.match(_status_line(path))
            if not match:
                continue
            refs = re.findall(r"`([^`]+)`", match.group("refs"))
            if not refs:
                stale.append(f"{path.name}: declares no code reference")
            for ref in refs:
                if ref not in versions and not (ROOT / ref).exists():
                    stale.append(f"{path.name}: {ref}")
        self.assertEqual(stale, [], "Update these specifications (content and status line) to the current code.")


if __name__ == "__main__":
    unittest.main()
