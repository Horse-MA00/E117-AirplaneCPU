"""Guard the frozen frontend contract while the UI is redesigned.

frontend/ui-contract.json lists what a redesign may move but must not break:
the page routes, the API calls the browser makes, cross-module events and the
DOM ids that JavaScript or the browser smoke tests depend on. See
docs/FRONTEND_UI.md for the rules.
"""
from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
CONTRACT = json.loads((FRONTEND / "ui-contract.json").read_text(encoding="utf-8"))
SITES = {
    "admin": (FRONTEND / "index.html", sorted(p for p in FRONTEND.glob("*.js"))),
    "members": (FRONTEND / "members" / "index.html", sorted((FRONTEND / "members").glob("*.js"))),
}
ALL_JS = [p for p in FRONTEND.glob("*.js")] + [p for p in (FRONTEND / "members").glob("*.js")]
SMOKE = "".join(p.read_text(encoding="utf-8") for p in FRONTEND.glob("*.mjs"))


def _read(paths):
    return "".join(p.read_text(encoding="utf-8") for p in paths)


def _api_prefix(path):
    """Static part of an API path: up to the first parameter or query string."""
    return re.split(r"[{?$]", path, maxsplit=1)[0]


class FrontendContractTests(unittest.TestCase):
    def test_contract_ids_exist_in_html(self):
        for site, (html, _) in SITES.items():
            present = set(re.findall(r'\bid="([^"]+)"', html.read_text(encoding="utf-8")))
            missing = sorted(set(CONTRACT["dom_ids"][site]) - present)
            self.assertEqual(missing, [], f"{site}: JS or smoke tests depend on these ids. "
                             "Keep them, or update JS, smoke tests and ui-contract.json together.")

    def test_contract_ids_are_still_used(self):
        for site, (html, scripts) in SITES.items():
            used = set(re.findall(r"['\"`]([\w-]+)['\"`]", _read(scripts)))
            used |= set(re.findall(r"#([A-Za-z][\w-]+)", SMOKE))
            used |= set(re.findall(r'href="#([\w-]+)"', html.read_text(encoding="utf-8")))
            used |= {f"view-{route}" for route in CONTRACT["pages"]["/" + site]["routes"]}
            stale = sorted(set(CONTRACT["dom_ids"][site]) - used)
            self.assertEqual(stale, [], f"{site}: nothing references these ids any more; remove them from ui-contract.json.")

    def test_api_calls_match_contract(self):
        source = _read(ALL_JS)
        called = {_api_prefix(m) for m in re.findall(r"['\"`](/api/[^'\"`]*)", source)}
        declared = {_api_prefix(entry["path"]) for entry in CONTRACT["api"]}
        self.assertEqual(sorted(called - declared), [], "New API calls: add them to ui-contract.json.")
        self.assertEqual(sorted(declared - called), [], "The frontend no longer calls these: update ui-contract.json.")

    def test_events_are_dispatched_and_handled(self):
        source = _read(ALL_JS)
        for name in CONTRACT["events"]:
            self.assertIn(f"'{name}'", source, f"Cross-module event {name} disappeared.")


if __name__ == "__main__":
    unittest.main()
