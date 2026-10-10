"""Synthetic review reports only; no GitHub calls or model sessions."""

import json
import os
import subprocess
import sys
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
    "findings": [],
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
            key: None
            for key in ("reviewed_head_sha", "reviewed_base_sha", "findings_count", "findings")
        }
        skipped.update(outcome="skipped", reason="prior_review")
        result = review.evidence(EVENT, "success", json.dumps(skipped))
        self.assertEqual(result["outcome"], "SKIPPED (model reported)")
        self.assertIn("no completion established", result["detail"])
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

    def test_findings_are_bounded_and_consistent_before_any_completion(self):
        finding = {
            "title": "Synthetic defect",
            "path": "scripts/example.py",
            "line": 3,
            "explanation": "Synthetic context",
        }
        report = {**REPORT, "findings_count": 1, "findings": [finding]}
        self.assertEqual(
            review.evidence(EVENT, "success", json.dumps(report))["outcome"],
            "COMPLETED (model reported)",
        )
        for change in (
            {"path": "../private"},
            {"path": "/private"},
            {"line": True},
            {"title": "x" * 161},
            {"explanation": "x" * 4001},
            {"unexpected": "raw transcript"},
        ):
            altered = {**report, "findings": [{**finding, **change}]}
            self.assertEqual(
                review.evidence(EVENT, "success", json.dumps(altered))["outcome"], "UNVERIFIED"
            )
        for findings in (None, [finding] * 51, []):
            altered = {**report, "findings": findings}
            self.assertEqual(
                review.evidence(EVENT, "success", json.dumps(altered))["outcome"], "UNVERIFIED"
            )

    def test_cli_saves_only_validated_completion_and_bounded_json_findings(self):
        event = {
            **EVENT,
            "repository": {"full_name": "example/synthetic"},
            "pull_request": {**EVENT["pull_request"], "number": 8},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event_path, output = root / "event.json", root / "outputs"
            completion, findings = (
                root / "completion/completed.json",
                root / "completion/findings.json",
            )
            event_path.write_text(json.dumps(event))
            report = {**REPORT, "untrusted_text": "SYNTHETIC_SECRET_DO_NOT_SAVE"}
            env = {
                "GITHUB_EVENT_PATH": str(event_path),
                "GITHUB_STEP_SUMMARY": str(root / "summary"),
                "GITHUB_OUTPUT": str(output),
                "GITHUB_RUN_ID": "123",
                "REVIEW_COMPLETION_PATH": str(completion),
                "REVIEW_ACTION_OUTCOME": "success",
                "REVIEW_REPORT": json.dumps(report),
            }
            with patch.dict(os.environ, env, clear=True):
                review.main()
            self.assertEqual(output.read_text(), "completed=true\npublish_findings=true\n")
            self.assertIsNotNone(review.review_checkpoint.load(event, completion))
            self.assertEqual(json.loads(findings.read_text())["findings"], [])
            self.assertNotIn(
                report["untrusted_text"], completion.read_text() + findings.read_text()
            )
            completion.unlink()
            findings.unlink()
            output.write_text("")
            with patch.dict(os.environ, {**env, "REVIEW_REPORT": ""}, clear=True):
                review.main()
            self.assertEqual(output.read_text(), "completed=false\npublish_findings=false\n")
            self.assertFalse(completion.exists())
            self.assertFalse(findings.exists())

    def test_large_file_backed_report_runs_and_reuse_retains_findings(self):
        event = {
            **EVENT,
            "repository": {"full_name": "example/synthetic"},
            "pull_request": {**EVENT["pull_request"], "number": 8},
        }
        finding = {
            "title": "Synthetic defect",
            "path": "scripts/example.py",
            "line": 3,
            "explanation": "x" * 4000,
        }
        report = {**REPORT, "findings_count": 50, "findings": [finding] * 50}
        self.assertGreater(len(json.dumps(report).encode()), 128 * 1024)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event_path, execution = root / "event.json", root / "execution.json"
            event_path.write_text(json.dumps(event))
            execution.write_text(
                json.dumps(
                    [
                        {"type": "assistant", "content": "SYNTHETIC_SECRET_TRANSCRIPT"},
                        {
                            "type": "result",
                            "subtype": "success",
                            "is_error": False,
                            "structured_output": report,
                        },
                    ]
                )
            )
            env = {
                "GITHUB_EVENT_PATH": str(event_path),
                "GITHUB_STEP_SUMMARY": str(root / "summary"),
                "GITHUB_OUTPUT": str(root / "outputs"),
                "GITHUB_RUN_ID": "123",
                "REVIEW_COMPLETION_PATH": str(root / "completion/completed.json"),
                "REVIEW_ACTION_OUTCOME": "success",
                "REVIEW_EXECUTION_FILE": str(execution),
            }
            command = [sys.executable, str(Path(review.__file__).resolve())]
            first = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
            self.assertEqual(first.stdout + first.stderr, "")
            self.assertNotIn(
                "SYNTHETIC_SECRET_TRANSCRIPT",
                (root / "summary").read_text() + (root / "completion/findings.json").read_text(),
            )
            (root / "outputs").write_text("")
            (root / "summary").write_text("")
            subprocess.run(
                command,
                env={
                    **env,
                    "GITHUB_RUN_ID": "456",
                    "REVIEW_ACTION_OUTCOME": "skipped",
                    "REVIEW_EXECUTION_FILE": "",
                },
                capture_output=True,
                check=True,
            )
            self.assertEqual(
                (root / "outputs").read_text(), "completed=false\npublish_findings=true\n"
            )
            self.assertIn("REUSED", (root / "summary").read_text())
            self.assertIn("run 123", (root / "summary").read_text())

    def test_execution_file_needs_a_final_successful_structured_result(self):
        valid = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "structured_output": REPORT,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "execution.json"
            for messages in (
                [],
                {},
                "not an array",
                [valid, {"type": "assistant"}],
                [{**valid, "is_error": True}],
                [{**valid, "subtype": "error"}],
                [{**valid, "structured_output": None}],
            ):
                path.write_text(json.dumps(messages))
                self.assertIsNone(review.report_from_file(path))
            path.write_text("invalid JSON")
            self.assertIsNone(review.report_from_file(path))
            path.unlink()
            self.assertIsNone(review.report_from_file(path))


if __name__ == "__main__":
    unittest.main()
