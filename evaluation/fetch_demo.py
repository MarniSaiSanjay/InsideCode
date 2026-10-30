"""Download the frozen demo repository ZIP and verify its checksum."""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = json.loads((HERE / "cases.json").read_text())["repository"]
TARGET = HERE.parent / ".brahmaniss" / "demo" / f"{DEMO['name']}.zip"


def main() -> int:
    if not TARGET.exists():
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(DEMO["zip_url"], timeout=60) as response:
            TARGET.write_bytes(response.read())
    digest = hashlib.sha256(TARGET.read_bytes()).hexdigest()
    if digest != DEMO["sha256"]:
        print(f"Checksum mismatch for {TARGET}: {digest}", file=sys.stderr)
        return 1
    print(TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
