"""Synthetic cache records; no GitHub, paid reviewer or external services."""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import review_checkpoint as checkpoint
import review_evidence as review

EVENT = {
    "repository": {"full_name": "example/synthetic"},
    "pull_request": {
        "number": 8,
        "draft": False,
        "head": {"sha": "a" * 40},
        "base": {"sha": "b" * 40},
    },
}


class ReviewCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "completion.json"
        self.path.with_name("findings.json").write_text('{"findings": []}')
        self.result = {"outcome": "COMPLETED (model reported)", "findings_count": 2}
        checkpoint.write(EVENT, self.result, self.path, "123")

    def test_only_exact_pr_head_base_repository_is_reused(self):
        self.assertIsNotNone(checkpoint.load(EVENT, self.path))
        for field, value in (("head", "c" * 40), ("base", "c" * 40), ("number", 9)):
            event = copy.deepcopy(EVENT)
            event["pull_request"][field] = {"sha": value} if field != "number" else value
            self.assertIsNone(checkpoint.load(event, self.path))
        event = {**EVENT, "repository": {"full_name": "example/other"}}
        self.assertIsNone(checkpoint.load(event, self.path))

    def test_absent_expired_malformed_or_failed_records_cannot_skip(self):
        record = json.loads(self.path.read_text())
        for change in (
            {"outcome": "skipped"},
            {"schema": 2},
            {"schema": True},
            {"findings_count": True},
            {"findings_count": -1},
            {"findings_count": 51},
            {"run_id": "123\nInjected"},
        ):
            self.path.write_text(json.dumps({**record, **change}))
            self.assertIsNone(checkpoint.load(EVENT, self.path))
        for text in ("", "null", "[]", "invalid"):
            self.path.write_text(text)
            self.assertIsNone(checkpoint.load(EVENT, self.path))
        self.path.unlink()
        self.assertIsNone(checkpoint.load(EVENT, self.path))

    def test_missing_or_changed_findings_force_a_fresh_review(self):
        findings = self.path.with_name("findings.json")
        findings.write_text('{"findings": ["tampered"]}')
        self.assertIsNone(checkpoint.load(EVENT, self.path))
        findings.unlink()
        self.assertIsNone(checkpoint.load(EVENT, self.path))

    def test_failed_skipped_unverified_reports_never_create_completion(self):
        self.path.unlink()
        for outcome in ("FAILED", "SKIPPED", "UNVERIFIED", "REUSED (prior model attestation)"):
            self.assertFalse(checkpoint.write(EVENT, {"outcome": outcome}, self.path, "123"))
            self.assertFalse(self.path.exists())

    def test_preflight_launches_missing_revision_but_not_drafts_or_exact_completion(self):
        event_path, output = self.path.parent / "event.json", self.path.parent / "output"
        for draft, cached, expected in (
            (False, True, "false"),
            (False, False, "true"),
            (True, False, "false"),
        ):
            event = copy.deepcopy(EVENT)
            event["pull_request"]["draft"] = draft
            event_path.write_text(json.dumps(event))
            output.write_text("")
            if not cached:
                self.path.unlink(missing_ok=True)
            with patch.dict(
                os.environ,
                {
                    "GITHUB_EVENT_PATH": str(event_path),
                    "GITHUB_OUTPUT": str(output),
                    "REVIEW_COMPLETION_PATH": str(self.path),
                },
                clear=True,
            ):
                checkpoint.main()
            self.assertEqual(output.read_text(), f"review_required={expected}\n")

    def test_reuse_is_distinct_from_a_new_completed_review_or_action_failure(self):
        record = checkpoint.load(EVENT, self.path)
        self.assertEqual(
            review.evidence(EVENT, "skipped", "", record)["outcome"],
            "REUSED (prior model attestation)",
        )
        self.assertEqual(review.evidence(EVENT, "failure", "", record)["outcome"], "FAILED")
        self.assertEqual(review.evidence(EVENT, "success", "", record)["outcome"], "UNVERIFIED")
        self.assertEqual(review.evidence(EVENT, "skipped", "", None)["outcome"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
