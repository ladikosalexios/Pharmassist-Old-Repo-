"""Summarize Claude's review attestation; never infer review completion from exit 0."""

import json
import os
import re
import shlex
from collections import Counter
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
        f"{result.get('diagnostics', '')}"
        "Completion is a model attestation for these revisions, not an independently "
        "verified review or approval. A successful action/job alone is not completion. "
        "Findings stay in the bounded Actions JSON artifact; no PR comments are requested.\n"
    )


def execution_messages(path):
    # The action's documented execution_file is a JSON array of SDK messages.
    # Parse privately; callers publish only validated fields and fixed categories.
    try:
        messages = json.loads(Path(path).read_text())
        return messages if isinstance(messages, list) else []
    except (OSError, ValueError, TypeError):
        return []


def execution_result(path):
    messages = execution_messages(path)
    final = messages[-1] if messages else None
    return final if isinstance(final, dict) and final.get("type") == "result" else None


def report_from_file(path):
    final = execution_result(path)
    if final is None or final.get("subtype") != "success" or final.get("is_error") is not False:
        return None
    report = final.get("structured_output")
    if not isinstance(report, dict):
        return None
    # A claimed completion with blocked tools cannot establish a reusable review.
    denials = final.get("permission_denials", [])
    if report.get("outcome") == "completed" and (not isinstance(denials, list) or denials):
        return None
    return json.dumps(report)


def tool_category(name, inputs):
    label = (
        name if name in ("Agent", "Task", "Read", "Grep", "Glob", "StructuredOutput") else "other"
    )
    if name == "Bash":
        label = "Bash: other shell command"
        try:
            source = inputs["command"]
            if isinstance(source, str):
                command = shlex.split(source)
                if command[:3] in (["gh", "pr", "view"], ["gh", "pr", "diff"]):
                    label = "Bash: " + " ".join(command[:3])
        except (KeyError, TypeError, ValueError, AttributeError):
            pass
    return label


def diagnostics(path):
    final = execution_result(path)
    denials = final.get("permission_denials") if final else None
    if not isinstance(denials, list):
        return ""
    labels = Counter()
    for denial in denials[:100]:
        name = denial.get("tool_name") if isinstance(denial, dict) else None
        inputs = denial.get("tool_input") if isinstance(denial, dict) else None
        labels[tool_category(name, inputs)] += 1
    # Fixed categories only: never expose tool inputs, commands, or arbitrary names.
    detail = ", ".join(f"{label}: {count}" for label, count in sorted(labels.items())) or "0"
    return f"Tool permission denials (first 100): {detail}.\n\n"


def tool_diagnostics(path):
    calls, errors, identifiers = Counter(), Counter(), {}
    error_labels = {
        "Unknown JSON field": "unsupported GitHub JSON field",
        "Resource not accessible by integration": "GitHub access denied",
        "To get started with GitHub CLI": "GitHub CLI authentication missing",
        "subagent_type is required": "reviewer type missing",
        "Agent would be spawned with zero tools": "reviewer has no tools",
        "Agent terminated early due to an API error": "reviewer API failure",
    }
    for message in execution_messages(path)[:1000]:
        if not isinstance(message, dict) or message.get("parent_tool_use_id") is not None:
            continue
        body = message.get("message")
        content = body.get("content") if isinstance(body, dict) else None
        if not isinstance(content, list):
            continue
        for block in content[:100]:
            if not isinstance(block, dict):
                continue
            if message.get("type") == "assistant" and block.get("type") == "tool_use":
                label = tool_category(block.get("name"), block.get("input"))
                calls[label] += 1
                if isinstance(block.get("id"), str):
                    identifiers[block["id"]] = label
            elif block.get("type") == "tool_result" and block.get("is_error") is True:
                key = block.get("tool_use_id")
                label = identifiers.get(key, "other") if isinstance(key, str) else "other"
                detail = "unclassified tool error"
                text = block.get("content")
                if isinstance(text, str):
                    for marker, fixed in error_labels.items():
                        if marker in text:
                            detail = fixed
                            break
                errors[f"{label} ({detail})"] += 1

    def counts(items):
        return ", ".join(f"{label}: {count}" for label, count in sorted(items.items())) or "0"

    return (
        f"Main-session tool calls (first 1000 messages): {counts(calls)}.\n\n"
        f"Reported tool errors (same messages): {counts(errors)}.\n\n"
    )


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    completion_path = os.environ.get("REVIEW_COMPLETION_PATH")
    checkpoint = review_checkpoint.load(event, completion_path) if completion_path else None
    report = os.environ.get("REVIEW_REPORT")
    if os.environ.get("REVIEW_EXECUTION_FILE"):
        report = report_from_file(os.environ["REVIEW_EXECUTION_FILE"])
    result = evidence(event, os.environ.get("REVIEW_ACTION_OUTCOME"), report, checkpoint)
    if os.environ.get("REVIEW_EXECUTION_FILE"):
        path = os.environ["REVIEW_EXECUTION_FILE"]
        result["diagnostics"] = diagnostics(path) + tool_diagnostics(path)
    text = summary(result)
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
        output.write(text)
    print(text, end="")
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
