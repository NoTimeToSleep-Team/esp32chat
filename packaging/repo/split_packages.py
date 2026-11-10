#!/usr/bin/env python3
"""Split an apt Packages file into per-architecture files.

Usage: split_packages.py <Packages-all> <output-dir>

The output dir gets Packages-<arch> files for every architecture found in the
input (amd64, arm64, ...). apt tolerates foreign stanzas, but clean per-arch
indexes are smaller and avoid confusing clients with "not installable" noise.
"""

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 1
    source, out_dir = Path(argv[0]), Path(argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)

    stanzas: list[list[str]] = []
    current: list[str] = []
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            current.append(line)
        elif current:
            stanzas.append(current)
            current = []
    if current:
        stanzas.append(current)

    by_arch: dict[str, list[str]] = {}
    for stanza in stanzas:
        arch = "unknown"
        for line in stanza:
            if line.startswith("Architecture:"):
                arch = line.split(":", 1)[1].strip()
                break
        by_arch.setdefault(arch, []).append("\n".join(stanza))

    for arch, chunks in sorted(by_arch.items()):
        target = out_dir / f"Packages-{arch}"
        target.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")
        print(f"{target}: {len(chunks)} packages")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
