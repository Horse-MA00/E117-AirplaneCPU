"""Check a complete source checkout/archive before giving it to reviewers.

No network, provider credentials or application state is used. --git-ref checks
only the committed archive so untracked local evidence cannot hide omissions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.evidence import EvidenceUnavailable, verify_extended


REQUIRED_FILES = (
    "README.md",
    "docs/EXTENDED_VALIDATION.md",
    "simulation/README.md",
    "simulation/validation_extended/manifest.json",
    "simulation/validation_extended/report.json",
    "simulation/validation_extended/forecast_records.jsonl.gz",
    "simulation/validation_extended/seed-20261121/manifest.json",
    "simulation/validation_extended/seed-20261122/manifest.json",
)
REQUIRED_DIRECTORIES = ("docs", "llm_agent/experiments", "simulation/validation_extended")
IGNORED_DIRECTORIES = {
    ".git", ".venv", "venv", ".runtime", "__pycache__", "node_modules",
    "private", "vendor", "outputs", "test-results", "build", "dist", "_site",
}


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _markdown_files(root: Path):
    for folder, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(d for d in directories if d not in IGNORED_DIRECTORIES
                                and not Path(folder, d).is_symlink())
        for name in sorted(files):
            path = Path(folder, name)
            if path.suffix.lower() == ".md" and _inside(root, path):
                yield path


def _markdown_targets(text: str):
    """Read inline/image links and reference definitions, excluding code fences."""
    fence = None
    for line_number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is not None:
            continue
        targets = re.findall(r"\]\(\s*(<[^>]+>|[^\s)]+)", line)
        definition = re.match(r"^\s{0,3}\[[^]]+\]:\s*(<[^>]+>|\S+)", line)
        if definition:
            targets.append(definition.group(1))
        for target in targets:
            yield line_number, target.strip("<>")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _experiment_manifests(root: Path, errors: list[str]) -> int:
    folder = root / "llm_agent/experiments"
    if not _inside(root, folder):
        errors.append("llm_agent/experiments: evidence directory points outside the publication")
        return 0
    manifests = sorted(folder.glob("*/manifest.json"))
    if not manifests:
        errors.append("llm_agent/experiments: no published experiment manifests found")
        return 0
    for child in sorted(folder.iterdir()):
        if child.is_dir() and not (child / "manifest.json").is_file():
            errors.append(f"{child.relative_to(root)}: missing manifest.json")
    for manifest_path in manifests:
        label = manifest_path.relative_to(root)
        if not _inside(root, manifest_path):
            errors.append(f"{label}: manifest points outside the publication")
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("source") != "adaptive_thompson_pricing":
                errors.append(f"{label}: only current Thompson experiment evidence may be published")
            files = manifest.get("files")
            if not isinstance(files, dict) or not files:
                raise ValueError("manifest must list published files")
            for name, expected in files.items():
                path = manifest_path.parent / name
                if not _inside(root, path) or not path.is_file():
                    errors.append(f"{label}: missing or outside-root artifact {name}")
                    continue
                wanted = expected.get("sha256") if isinstance(expected, dict) else expected
                if not isinstance(wanted, str) or not re.fullmatch(r"[0-9a-f]{64}", wanted):
                    errors.append(f"{label}: invalid SHA256 for {name}")
                elif _sha256(path) != wanted:
                    errors.append(f"{label}: SHA256 mismatch for {name}")
                if isinstance(expected, dict) and "bytes" in expected and path.stat().st_size != expected["bytes"]:
                    errors.append(f"{label}: byte count mismatch for {name}")
            report_path = manifest_path.parent / "report.json"
            if report_path.is_file() and _inside(root, report_path):
                report = json.loads(report_path.read_text(encoding="utf-8"))
                if (report.get("version") != "member-thompson-v5-marketing"
                        or report.get("config", {}).get("profile") != "flexible_deal_seekers"):
                    errors.append(f"{label}: retired experiment version or customer profile")
                from scripts.verify_artifacts import experiment_status
                try:
                    experiment_status(report, manifest)
                except (AssertionError, KeyError, TypeError) as exc:
                    errors.append(f"{label}: invalid terminal experiment evidence ({exc})")
            else:
                errors.append(f"{label}: missing current Thompson report.json")
        except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as exc:
            errors.append(f"{label}: cannot verify manifest ({exc})")
    return len(manifests)


def check_publication(root: Path) -> dict:
    root = root.resolve()
    errors: list[str] = []
    for name in REQUIRED_DIRECTORIES:
        if not (root / name).is_dir() or not _inside(root, root / name):
            errors.append(f"Missing required evidence directory: {name}")
    for name in REQUIRED_FILES:
        if not (root / name).is_file() or not _inside(root, root / name):
            errors.append(f"Missing required publication file: {name}")
    documents = list(_markdown_files(root))
    links = 0
    for path in documents:
        label = path.relative_to(root)
        try:
            for line, raw in _markdown_targets(path.read_text(encoding="utf-8")):
                url = urlsplit(raw)
                if url.scheme or url.netloc or not url.path:
                    continue
                links += 1
                decoded = unquote(url.path)
                target = root / decoded.lstrip("/") if decoded.startswith("/") else path.parent / decoded
                if not _inside(root, target) or not target.exists():
                    errors.append(f"{label}:{line}: missing or outside-root link target {raw}")
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{label}: cannot read Markdown ({exc})")
    manifests = _experiment_manifests(root, errors)
    evaluation = None
    try:
        evaluation = verify_extended(root)
    except EvidenceUnavailable as exc:
        errors.append(f"Extended evaluation evidence: {exc}")
    return {"status": "failed" if errors else "passed", "root": str(root),
            "markdown_files": len(documents), "relative_links": links,
            "experiment_manifests": manifests, "extended_evaluation": evaluation,
            "errors": errors}


def check_git_ref(root: Path, reference: str) -> dict:
    """Inspect actual archive bytes; never mix them with uncommitted files."""
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "--verify", "--end-of-options", reference + "^{commit}"],
        text=True, stderr=subprocess.PIPE).strip()
    with tempfile.TemporaryDirectory(prefix="e117-publication-") as temporary:
        archive_root = Path(temporary) / "source"
        archive_root.mkdir()
        with tempfile.TemporaryFile() as archive:
            subprocess.run(["git", "-C", str(root), "archive", "--format=tar", commit],
                           stdout=archive, stderr=subprocess.PIPE, check=True)
            archive.seek(0)
            with tarfile.open(fileobj=archive, mode="r|") as source:
                for member in source:
                    target = archive_root / member.name
                    if not _inside(archive_root, target) or member.issym() or member.islnk():
                        raise ValueError(f"Archive contains an unsafe path/link: {member.name}")
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                    elif member.isfile():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with source.extractfile(member) as src, target.open("wb") as dst:
                            shutil.copyfileobj(src, dst)
                    else:
                        raise ValueError(f"Archive contains unsupported entry: {member.name}")
        result = check_publication(archive_root)
        result.update(root=str(root.resolve()), git_ref=reference, git_commit=commit,
                      source="committed_git_archive")
        return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="Checkout or unpacked archive to inspect; defaults to this repository")
    parser.add_argument("--git-ref", help="Check only this committed Git archive, e.g. HEAD")
    args = parser.parse_args(argv)
    try:
        result = check_git_ref(args.root, args.git_ref) if args.git_ref else check_publication(args.root)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        result = {"status": "failed", "errors": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
