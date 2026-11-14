"""Private append-only model interaction records with credential redaction."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
import uuid

BASE = Path(__file__).resolve().parents[1] / "data/private/llm_runs"


def sanitize(value):
    secrets = [v for k, v in os.environ.items() if len(v) >= 8 and any(t in k.upper() for t in ("API_KEY", "TOKEN", "SECRET"))]
    def walk(item):
        if isinstance(item, str):
            for secret in secrets:
                item = item.replace(secret, "[REDACTED]")
            return item
        if isinstance(item, list):
            return [walk(x) for x in item]
        if isinstance(item, dict):
            return {walk(str(k)): "[REDACTED]" if str(k).lower() in ("authorization", "api_key", "api-key", "access_token") else walk(v) for k, v in item.items()}
        return item
    return walk(value)


def _path(run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", run_id):
        raise ValueError("Invalid run ID")
    return BASE / run_id


class Audit:
    def __init__(self, source, metadata=None, run_id=None, resume=False):
        self.run_id = run_id or "journey-" + uuid.uuid4().hex[:16]
        self._lock = threading.Lock()
        self.path = _path(self.run_id)
        self.path.mkdir(parents=True, exist_ok=resume)
        existing = self.path / "metadata.json"
        if resume and existing.exists():
            self.metadata = json.loads(existing.read_text(encoding="utf-8"))
        else:
            self.metadata = {"run_id": self.run_id, "source": source, "created_at": datetime.now(timezone.utc).isoformat(),
                             "status": "running", **(metadata or {})}
            self.update()

    def append(self, record):
        safe = sanitize({"recorded_at": datetime.now(timezone.utc).isoformat(), **record})
        with self._lock:
            with (self.path / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(safe, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())

    def update(self, **changes):
        self.metadata.update(changes)
        target = self.path / "metadata.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(sanitize(self.metadata), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)


def list_runs():
    if not BASE.exists():
        return []
    runs = []
    for directory in BASE.iterdir():
        if directory.is_dir() and (directory / "metadata.json").is_file():
            try:
                metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
                if (directory / "events.jsonl").exists():
                    with (directory / "events.jsonl").open(encoding="utf-8") as handle:
                        metadata["event_records"] = sum(1 for _ in handle)
                else:
                    metadata["event_records"] = 0
                runs.append(metadata)
            except (OSError, json.JSONDecodeError):
                continue
    return sorted(runs, key=lambda x: x.get("created_at", ""), reverse=True)[:100]


def read_run(run_id):
    path = _path(run_id)
    if not (path / "metadata.json").is_file():
        raise ValueError("Run not found")
    records = []
    if (path / "events.jsonl").exists():
        with (path / "events.jsonl").open(encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index >= 5000:
                    raise ValueError("Run exceeds inline audit limit; inspect the local JSONL file")
                records.append(json.loads(line))
    result = {"metadata": json.loads((path / "metadata.json").read_text(encoding="utf-8")), "records": records}
    if (path / "result.json").exists():
        result["result"] = json.loads((path / "result.json").read_text(encoding="utf-8"))
    return sanitize(result)
