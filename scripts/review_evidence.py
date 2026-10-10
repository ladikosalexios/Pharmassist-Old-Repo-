"""Summarize Claude's review attestation; never infer review completion from exit 0."""

import json
import os
import re
from pathlib import Path, PurePosixPath

import review_checkpoint

REASONS = {
    "reviewed": "Review reported complete",
    "closed": "PR closed",
    "draft": "Draft PR",
    "not_needed": "Reviewer decided review was unnecessary",
    "prior_review": "Reviewer reported a prior review; no completion established",
    "revision_changed": "PR head or base changed during review",
    "other": "Reviewer skipped for another reason",
}


def validated_findings(report):
    findings = report.get("findings")
    if not isinstance(findings, list) or len(findings) > 50:
        return None
    if len(findings) != report.get("findings_count"):
        return None
    for finding in findings:
        if not isinstance(finding, dict):
            return None
        if set(finding) != {"title", "path", "line", "explanation"}:
            return None
        for key, limit in (("title", 160), ("path", 300), ("explanation", 4000)):
            value = finding[key]
            if not isinstance(value, str) or not 1 <= len(value) <= limit or "\0" in value:
                return None
        path = PurePosixPath(finding["path"])
        if path.is_absolute() or ".." in path.parts or "\\" in finding["path"]:
            return None
        if type(finding["line"]) is not int or not 1 <= finding["line"] <= 1000000:
            return None
    return findings


def evidence(event, action_outcome, structured, checkpoint=None):
    pr = event["pull_request"]
    head, base = pr["head"]["sha"], pr["base"]["sha"]
    if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (head, base)):
        raise ValueError("Review event must contain full head and base SHAs")
    result = {"head": head, "base": base, "outcome": "UNVERIFIED", "detail": "No valid attestation"}
    if pr.get("draft"):
        return {**result, "outcome": "SKIPPED", "detail": "Draft PR; paid review not launched"}
    if action_outcome == "skipped" and checkpoint is not None:
        return {
            **result,
            "outcome": "REUSED (prior model attestation)",
            "detail": f"Exact PR/head/base previously completed in run {checkpoint['run_id']}",
        }
    if action_outcome != "success":
        return {
            **result,
            "outcome": "FAILED" if action_outcome == "failure" else "UNVERIFIED",
            "detail": "Action did not finish successfully",
        }
    try:
        report = json.loads(structured)
    except (TypeError, ValueError):
        return result
    if not isinstance(report, dict):
        return result
    if (
        not {
            "outcome",
            "reason",
            "reviewed_head_sha",
            "reviewed_base_sha",
            "findings_count",
            "findings",
        }
        <= report.keys()
    ):
        return result
    reason = report.get("reason")
    if not isinstance(reason, str) or reason not in REASONS:
        return result
    if report.get("outcome") == "skipped" and reason != "reviewed":
        if any(
            report.get(key) is not None
            for key in ("reviewed_head_sha", "reviewed_base_sha", "findings_count", "findings")
        ):
            return result
        return {**result, "outcome": "SKIPPED (model reported)", "detail": REASONS[reason]}
    if report.get("outcome") != "completed" or reason != "reviewed":
        return result
    if report.get("reviewed_head_sha") != head or report.get("reviewed_base_sha") != base:
        return {**result, "detail": "Attested revisions do not match the event"}
    count = report.get("findings_count")
    if type(count) is not int or count < 0:
        return result
    findings = validated_findings(report)
    if findings is None:
        return result
    return {
        **result,
        "outcome": "COMPLETED (model reported)",
        "detail": f"{count} findings reported; PR publication disabled",
        "findings_count": count,
        "findings": findings,
    }


def summary(result):
    # Only validated identifiers and fixed text/counts are published. Never dump model
    # output, tool logs, findings, credentials or caller-supplied skip explanations.
    return (
        "## Claude review evidence\n\n"
        f"- Outcome: **{result['outcome']}** — {result['detail']}\n"
        f"- Event head SHA: `{result['head']}`\n"
        f"- Event base SHA: `{result['base']}`\n\n"
        "Completion is a model attestation for these revisions, not an independently "
        "verified review or approval. A successful action/job alone is not completion. "
        "Findings stay in the bounded Actions JSON artifact; no PR comments are requested.\n"
    )


def report_from_file(path):
    # The action's documented execution_file is a JSON array of SDK messages.
    # Read only its final successful result. Never dump the transcript or errors.
    try:
        messages = json.loads(Path(path).read_text())
        final = messages[-1]
        if final.get("type") != "result" or final.get("subtype") != "success":
            return None
        if final.get("is_error") is not False or not isinstance(
            final.get("structured_output"), dict
        ):
            return None
        return json.dumps(final["structured_output"])
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        return None


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    completion_path = os.environ.get("REVIEW_COMPLETION_PATH")
    checkpoint = review_checkpoint.load(event, completion_path) if completion_path else None
    report = os.environ.get("REVIEW_REPORT")
    if os.environ.get("REVIEW_EXECUTION_FILE"):
        report = report_from_file(os.environ["REVIEW_EXECUTION_FILE"])
    result = evidence(event, os.environ.get("REVIEW_ACTION_OUTCOME"), report, checkpoint)
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
        output.write(summary(result))
    if result["outcome"] == "COMPLETED (model reported)" and completion_path:
        # JSON artifact only: bounded model text is never interpolated into Markdown.
        findings_path = Path(completion_path).with_name("findings.json")
        findings_path.parent.mkdir(parents=True, exist_ok=True)
        findings_path.write_text(
            json.dumps(
                {
                    "head": result["head"],
                    "base": result["base"],
                    "findings": result["findings"],
                    "notice": "Model reported findings; not independent review or approval",
                },
                indent=2,
            )
            + "\n"
        )
    completed = False
    if completion_path:
        completed = review_checkpoint.write(
            event, result, completion_path, os.environ.get("GITHUB_RUN_ID", "")
        )
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            output.write(f"completed={'true' if completed else 'false'}\n")
            publish = completed or result["outcome"] == "REUSED (prior model attestation)"
            output.write(f"publish_findings={'true' if publish else 'false'}\n")


if __name__ == "__main__":
    main()
