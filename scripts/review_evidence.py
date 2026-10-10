"""Summarize Claude's review attestation; never infer review completion from exit 0."""

import json
import os
import re
from pathlib import Path

REASONS = {
    "reviewed": "Review reported complete",
    "closed": "PR closed",
    "draft": "Draft PR",
    "not_needed": "Plugin decided review was unnecessary",
    "prior_review": "Plugin found a prior Claude comment",
    "revision_changed": "PR head or base changed during review",
    "other": "Plugin skipped for another reason",
}


def evidence(event, action_outcome, structured):
    pr = event["pull_request"]
    head, base = pr["head"]["sha"], pr["base"]["sha"]
    if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (head, base)):
        raise ValueError("Review event must contain full head and base SHAs")
    result = {"head": head, "base": base, "outcome": "UNVERIFIED", "detail": "No valid attestation"}
    if pr.get("draft"):
        return {**result, "outcome": "SKIPPED", "detail": "Draft PR; paid review not launched"}
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
        not {"outcome", "reason", "reviewed_head_sha", "reviewed_base_sha", "findings_count"}
        <= report.keys()
    ):
        return result
    reason = report.get("reason")
    if not isinstance(reason, str) or reason not in REASONS:
        return result
    if report.get("outcome") == "skipped" and reason != "reviewed":
        if any(
            report.get(key) is not None
            for key in ("reviewed_head_sha", "reviewed_base_sha", "findings_count")
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
    return {
        **result,
        "outcome": "COMPLETED (model reported)",
        "detail": f"{count} findings reported; publication disabled",
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
        "This workflow requests terminal-only output; it does not request PR comments.\n"
    )


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    result = evidence(
        event, os.environ.get("REVIEW_ACTION_OUTCOME"), os.environ.get("REVIEW_REPORT")
    )
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
        output.write(summary(result))


if __name__ == "__main__":
    main()
