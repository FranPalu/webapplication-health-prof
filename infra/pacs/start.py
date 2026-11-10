"""Generate only an ephemeral secret-bearing configuration; never print it."""

import json
import os
from pathlib import Path


def main():
    users = json.loads(os.environ.get("PACS_USERS_JSON", "{}"))
    if (
        not isinstance(users, dict)
        or not users
        or any(
            not isinstance(name, str)
            or not name
            or not isinstance(password, str)
            or len(password) < 32
            for name, password in users.items()
        )
    ):
        raise RuntimeError("Generated PACS credentials are required")
    config = json.loads(Path("/claria-orthanc.json").read_text())
    config["RegisteredUsers"] = users
    descriptor = os.open(
        "/tmp/claria-orthanc.json", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
    )
    with os.fdopen(descriptor, "w") as stream:
        json.dump(config, stream)
    os.execv("/usr/local/bin/Orthanc", ["Orthanc", "/tmp/claria-orthanc.json"])


if __name__ == "__main__":
    main()
