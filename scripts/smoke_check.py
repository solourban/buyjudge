from __future__ import annotations

import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "main.py", ROOT / "app.py"] + sorted((ROOT / "pages").glob("*.py"))


def main() -> int:
    failed: list[tuple[Path, str]] = []
    for path in TARGETS:
        try:
            py_compile.compile(str(path), doraise=True)
            print(f"OK  {path.relative_to(ROOT)}")
        except Exception as exc:
            failed.append((path, f"{type(exc).__name__}: {exc}"))
            print(f"FAIL {path.relative_to(ROOT)} :: {type(exc).__name__}: {exc}")

    if failed:
        print("\nSmoke check failed")
        return 1
    print("\nSmoke check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
