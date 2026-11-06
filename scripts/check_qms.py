"""Check QMS traceability and fail closed on unresolved release risks."""

import argparse
import ast
import csv
import json
import re
import sys
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@cache
def test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def validate_register(
    root: Path, register: dict, *, release: bool = False
) -> list[str]:
    errors = []
    hazards = register["hazards"]
    requirements = register["requirements"]
    hazard_ids = {hazard["id"] for hazard in hazards}
    requirement_ids = {item["id"] for item in requirements}
    if not hazards or len(hazard_ids) != len(hazards):
        errors.append("Hazard IDs must be present and unique")
    if not requirements or len(requirement_ids) != len(requirements):
        errors.append("Requirement IDs must be present and unique")

    p0_text = (root / "docs/p0/traceability.md").read_text(encoding="utf-8")
    p0_ids = set(re.findall(r"^\| (TR-\d+) \|", p0_text, re.MULTILINE))
    linked = set()
    for item in requirements:
        key = item["id"]
        links = set(item["hazards"])
        if not links or links - hazard_ids:
            errors.append(f"{key}: missing or unknown hazard link")
        linked.update(links)
        if item["p0_trace"] not in p0_ids:
            errors.append(f"{key}: unknown P0 trace")
        if not item["text"].strip() or not item["planned_test"].strip():
            errors.append(f"{key}: missing requirement or planned verification")
        if not re.fullmatch(r"P(?:[1-9]|10)", item["phase"]):
            errors.append(f"{key}: invalid phase")
        for reference in item["evidence"]:
            file, _, name = reference.partition("::")
            path = (root / file).resolve()
            if (
                not path.is_relative_to(root.resolve())
                or path.suffix != ".py"
                or not path.is_file()
                or not name.startswith("test_")
                or name not in test_functions(path)
            ):
                errors.append(f"{key}: unresolved test {reference}")

    for hazard in hazards:
        key = hazard["id"]
        if key not in linked:
            errors.append(f"{key}: no requirement controls this hazard")
        if any(
            not hazard[field].strip()
            for field in (
                "failure",
                "cause",
                "effect",
                "deviation",
                "current_control",
                "residual",
                "owner",
            )
        ):
            errors.append(f"{key}: incomplete hazard record")
        if not re.fullmatch(r"P(?:[1-9]|10)", hazard["phase"]):
            errors.append(f"{key}: invalid phase")
        if any(
            type(hazard[field]) is not int or not 1 <= hazard[field] <= 4
            for field in ("severity", "probability", "detectability")
        ):
            errors.append(f"{key}: score must be an integer in 1–4")
        if hazard["status"] == "accepted":
            if not hazard.get("approval_ref") or not hazard.get("verification_ref"):
                errors.append(
                    f"{key}: accepted risk lacks approval or verification reference"
                )
        elif hazard["status"] != "blocking":
            errors.append(f"{key}: unknown risk status")
        elif release:
            errors.append(f"{key}: blocks clinical release")
    return errors


def validate_soup(root: Path) -> list[str]:
    with (root / "docs/qms/soup.tsv").open(encoding="utf-8", newline="") as stream:
        items = list(csv.DictReader(stream, delimiter="\t"))
    identities = {(row["ecosystem"], row["component"]) for row in items}
    errors = []
    if len(identities) != len(items):
        errors.append("Duplicate SOUP components")
    if any(not all(row.values()) for row in items):
        errors.append("Missing SOUP metadata")

    lockfile = (root / "pnpm-lock.yaml").read_text(encoding="utf-8")
    packages = lockfile.split("\npackages:\n", 1)[1].split("\nsnapshots:\n", 1)[0]
    locked = {
        ("npm", entry.strip("'\x22"))
        for entry in re.findall(r"^  (\S.*):$", packages, re.MULTILINE)
    }
    requirements = (root / "backend/requirements.txt").read_text(encoding="utf-8")
    imaging = (root / "infra/imaging/Dockerfile").read_text(encoding="utf-8")
    pinned = {
        ("python", entry)
        for entry in re.findall(r"[\w.-]+==[\w.+!-]+", requirements + "\n" + imaging)
    }
    lock_ecosystems = {
        identity for identity in identities if identity[0] in {"npm", "python"}
    }
    for ecosystem, component in sorted((locked | pinned) - lock_ecosystems):
        errors.append(f"SOUP missing {ecosystem} {component}")
    for ecosystem, component in sorted(lock_ecosystems - (locked | pinned)):
        errors.append(f"SOUP obsolete {ecosystem} {component}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release", action="store_true", help="Reject open clinical hazards"
    )
    args = parser.parse_args()
    try:
        register = json.loads(
            (ROOT / "docs/qms/register.json").read_text(encoding="utf-8")
        )
        errors = validate_register(
            ROOT, register, release=args.release
        ) + validate_soup(ROOT)
    except (
        KeyError,
        TypeError,
        AttributeError,
        ValueError,
        SyntaxError,
        OSError,
    ) as exc:
        errors = [f"Invalid QMS evidence: {exc}"]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("QMS references and SOUP inventory verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
