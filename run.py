"""Launch this bundle's local environment without activating it."""

import os
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent
    relative = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    executable = root / ".venv" / relative
    if not executable.is_file():
        print("Run python install.py with Python 3.13 first.", file=sys.stderr)
        return 1
    env = os.environ.copy()
    env.update(PYTHONPATH=str(root / "src"), PYTHONDONTWRITEBYTECODE="1")
    try:
        return subprocess.run(
            [str(executable), "-m", "bxvzm", *(sys.argv[1:] if argv is None else argv)],
            cwd=root,
            env=env,
            check=False,
        ).returncode
    except OSError as error:
        print(f"Cannot start the app: {error}\nRerun python install.py.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
