"""Fail closed on missing, malformed or error-bearing official HL7 results."""

import json
import sys
from collections import Counter
from pathlib import Path


def check_result(document):
    if not isinstance(document, dict):
        raise TypeError("Invalid validator report")
    if document.get("resourceType") == "Bundle":
        entries = document.get("entry")
        if not isinstance(entries, list) or not entries:
            raise ValueError("Empty validator report")
        results = [
            entry.get("resource") for entry in entries if isinstance(entry, dict)
        ]
        if len(results) != len(entries):
            raise ValueError("Invalid result entry")
    else:
        results = [document]
    counts = Counter()
    for result in results:
        if (
            not isinstance(result, dict)
            or result.get("resourceType") != "OperationOutcome"
            or not isinstance(result.get("issue"), list)
        ):
            raise ValueError("Missing OperationOutcome")
        for issue in result["issue"]:
            if not isinstance(issue, dict) or issue.get("severity") not in (
                "fatal",
                "error",
                "warning",
                "information",
            ):
                raise ValueError("Invalid issue severity")
            counts[issue["severity"]] += 1
    if counts["fatal"] or counts["error"]:
        raise ValueError(
            f"HL7 validation failed: {counts['fatal']} fatal, {counts['error']} errors"
        )
    return dict(counts)


def main():
    try:
        report = json.loads(Path(sys.argv[1]).read_text())
        print(
            json.dumps(
                {"status": "passed", "issues": check_result(report)}, sort_keys=True
            )
        )
        return 0
    except (IndexError, OSError, ValueError, TypeError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
