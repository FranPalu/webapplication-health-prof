"""Run backend tooling with local env defaults; explicit environment wins."""
import os
import subprocess
import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
path = root / '.env.dev'
if path.exists():
    for line in path.read_text().splitlines():
        if line and not line.startswith('#'):
            key, value = line.split('=', 1)
            os.environ.setdefault(key, value)
raise SystemExit(subprocess.call(sys.argv[1:], cwd=root / 'backend'))
