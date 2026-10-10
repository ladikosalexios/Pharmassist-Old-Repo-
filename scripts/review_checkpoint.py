"""Best-effort review reuse for an exact PR/head/base; never an approval gate."""

import hashlib
import json
import os
import re
from pathlib import Path


def identity(event):
    pr = event["pull_request"]
    return {
        "repository": event["repository"]["full_name"],
        "pr": pr["number"],
        "head": pr["head"]["sha"],
        "base": pr["base"]["sha"],
    }


def load(event, path):
    try:
        record = json.loads(Path(path).read_text())
        expected = identity(event)
        if (
            not isinstance(record, dict)
            or type(record.get("schema")) is not int
            or record["schema"] != 1
        ):
            return None
        if any(record.get(key) != value for key, value in expected.items()):
            return None
        if record.get("outcome") != "completed":
            return None
        if type(record.get("findings_count")) is not int or not 0 <= record["findings_count"] <= 50:
            return None
        if not isinstance(record.get("run_id"), str) or not re.fullmatch(
            r"[0-9]+", record["run_id"]
        ):
            return None
        findings = Path(path).with_name("findings.json")
        if findings.stat().st_size > 4 * 1024 * 1024:
            return None
        digest = hashlib.sha256(findings.read_bytes()).hexdigest()
        if record.get("findings_sha256") != digest:
            return None
        return record
    except (OSError, ValueError, TypeError, KeyError):
        return None


def write(event, result, path, run_id):
    if result["outcome"] != "COMPLETED (model reported)":
        return False
    if not re.fullmatch(r"[0-9]+", run_id):
        raise ValueError("Completion record needs a GitHub run identifier")
    record = {
        **identity(event),
        "schema": 1,
        "outcome": "completed",
        "run_id": run_id,
        "findings_count": result["findings_count"],
        "findings_sha256": hashlib.sha256(
            Path(path).with_name("findings.json").read_bytes()
        ).hexdigest(),
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(record, indent=2) + "\n")
    return True


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    record = load(event, os.environ["REVIEW_COMPLETION_PATH"])
    required = not event["pull_request"].get("draft") and record is None
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"review_required={'true' if required else 'false'}\n")


if __name__ == "__main__":
    main()
