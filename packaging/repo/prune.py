#!/usr/bin/env python3
"""Keep only the newest N package versions in a repository directory.

Usage: prune.py DIR --ext {deb,rpm,pkg} --keep N

The version is parsed from the package file name; all files that belong to a
dropped version are removed. The release-configuration RPM
(local-chat-release-*) never matches and is always kept.
"""

import argparse
import re
import sys
from pathlib import Path

PATTERNS = {
    "deb": re.compile(r"^local-chat_(\d[^_]*)-1_[^_]+\.deb$"),
    "rpm": re.compile(r"^local-chat-(\d[^-]*)-1\.[^.]+\.rpm$"),
    "pkg": re.compile(r"^local-chat-(\d[^-]*)-1-[^.]+\.pkg\.tar\.zst$"),
}


def version_key(version: str) -> list[int]:
    numbers = [int(part) for part in re.findall(r"\d+", version)]
    return numbers or [0]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("--ext", choices=sorted(PATTERNS), required=True)
    parser.add_argument("--keep", type=int, default=3)
    args = parser.parse_args(argv)

    directory = Path(args.directory)
    pattern = PATTERNS[args.ext]
    groups: dict[str, list[Path]] = {}
    for path in directory.iterdir():
        match = pattern.match(path.name)
        if match:
            groups.setdefault(match.group(1), []).append(path)

    versions = sorted(groups, key=version_key)
    if args.keep > 0:
        drop = versions[:-args.keep]
    else:
        drop = []
    for version in drop:
        for path in groups[version]:
            print(f"prune {path.name}")
            path.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
