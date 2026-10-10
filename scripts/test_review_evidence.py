"""Synthetic review reports only; no GitHub calls or model sessions."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import review_evidence as review

HEAD, BASE = "a" * 40, "b" * 40
EVENT = {"pull_request": {"head": {"sha": HEAD}, "base": {"sha": BASE}, "draft": False}}
REPORT = {
    "outcome": "completed",
    "reason": "reviewed",
    "reviewed_head_sha": HEAD,
    "reviewed_base_sha": BASE,
    "findings_count": 0,
}


class ReviewEvidenceTests(unittest.TestCase):
    def test_completion_requires_revision_attestation_and_findings_count(self):
        result = review.evidence(EVENT, "success", json.dumps(REPORT))
        self.assertEqual(result["outcome"], "COMPLETED (model reported)")
        for change in (
            {"reviewed_head_sha": "c" * 40},
            {"reviewed_base_sha": None},
            {"findings_count": True},
            {"findings_count": -1},
            {"outcome": "unknown"},
            {"reason": "prior_review"},
        ):
            with self.subTest(change=change):
                result = review.evidence(EVENT, "success", json.dumps({**REPORT, **change}))
                self.assertEqual(result["outcome"], "UNVERIFIED")

    def test_success_without_valid_report_is_never_completion(self):
        for report in (
            None,
            "",
            "not JSON",
            "null",
            "[]",
            "{}",
            '{"reason": []}',
            '{"outcome": "skipped", "reason": "prior_review"}',
        ):
            with self.subTest(report=report):
                self.assertEqual(review.evidence(EVENT, "success", report)["outcome"], "UNVERIFIED")

    def test_action_failure_cannot_be_overridden_by_model(self):
        for action in ("failure", "cancelled", "skipped", None):
            with self.subTest(action=action):
                outcome = review.evidence(EVENT, action, json.dumps(REPORT))["outcome"]
                self.assertEqual(outcome, "FAILED" if action == "failure" else "UNVERIFIED")

    def test_plugin_skip_is_explicit_and_cannot_claim_reviewed_revisions(self):
        skipped = {
            key: None for key in ("reviewed_head_sha", "reviewed_base_sha", "findings_count")
        }
        skipped.update(outcome="skipped", reason="prior_review")
        result = review.evidence(EVENT, "success", json.dumps(skipped))
        self.assertEqual(result["outcome"], "SKIPPED (model reported)")
        self.assertIn("prior Claude comment", result["detail"])
        skipped["reviewed_head_sha"] = HEAD
        self.assertEqual(
            review.evidence(EVENT, "success", json.dumps(skipped))["outcome"], "UNVERIFIED"
        )

    def test_draft_skip_is_event_evidence(self):
        event = {"pull_request": {**EVENT["pull_request"], "draft": True}}
        result = review.evidence(event, "skipped", None)
        self.assertEqual(result["outcome"], "SKIPPED")
        self.assertIn("not launched", result["detail"])

    def test_summary_uses_only_validated_fields_and_cli_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            event, output = Path(directory) / "event.json", Path(directory) / "summary.md"
            event.write_text(json.dumps(EVENT))
            report = {**REPORT, "untrusted_text": "SYNTHETIC_SECRET_DO_NOT_PRINT"}
            with patch.dict(
                os.environ,
                {
                    "GITHUB_EVENT_PATH": str(event),
                    "GITHUB_STEP_SUMMARY": str(output),
                    "REVIEW_ACTION_OUTCOME": "success",
                    "REVIEW_REPORT": json.dumps(report),
                },
                clear=True,
            ):
                review.main()
            text = output.read_text()
            self.assertIn(HEAD, text)
            self.assertIn(BASE, text)
            self.assertIn("model attestation", text)
            self.assertIn("publication disabled", text)
            self.assertNotIn(report["untrusted_text"], text)

    def test_event_identifiers_cannot_inject_summary_content(self):
        event = {"pull_request": {**EVENT["pull_request"], "head": {"sha": "bad\n## injected"}}}
        with self.assertRaises(ValueError):
            review.evidence(event, "success", json.dumps(REPORT))


if __name__ == "__main__":
    unittest.main()
