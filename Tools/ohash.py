#!/usr/bin/env python3
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
digest = hashlib.sha256()
rtl = root / "rtl"
extensions = {".v", ".sv", ".vh", ".svh"}

if rtl.is_dir():
    files = sorted(
        p for p in rtl.rglob("*")
        if p.is_file() and p.suffix.lower() in extensions
    )
    for path in files:
        rel = path.relative_to(rtl).as_posix()
        digest.update(("rtl/" + rel + "\0").encode())
        digest.update(path.read_bytes())
        digest.update(b"\0")

for name in ("constraint.sdc", "config.mk"):
    path = root / name
    digest.update((name + "\0").encode())
    if not path.is_file():
        digest.update(b"<missing>\0")
        continue

    content = path.read_bytes()
    if name == "config.mk":
        text = content.decode("utf-8", errors="replace")
        content = "".join(
            line for line in text.splitlines(keepends=True)
            if not line.startswith("PROJ_DIR")
        ).encode()

    digest.update(content)
    digest.update(b"\0")

print(digest.hexdigest()[:16])
