#!/usr/bin/env python3
"""Generate a pacman repository database without Arch tooling.

Usage: make_pacman_db.py <repo-dir>

Reads every *.pkg.tar.zst in the directory and writes:

    localchat.db.tar.gz     (<pkgname>-<pkgver>-<pkgrel>/desc entries)
    localchat.files.tar.gz  (<pkgname>-<pkgver>-<pkgrel>/files entries)
    localchat.db -> localchat.db.tar.gz
    localchat.files -> localchat.files.tar.gz

Requires the `zstandard` module (python3-zstandard) to read .pkg.tar.zst.
Signing is done separately with gpg (localchat.db.tar.gz.sig).
"""

import gzip
import hashlib
import io
import os
import sys
import tarfile
from pathlib import Path

try:
    import zstandard
except ImportError:  # pragma: no cover - handled with a clear message
    zstandard = None


def read_package(path: Path) -> tuple[dict[str, list[str]], list[str]]:
    if path.name.endswith(".pkg.tar.zst"):
        if zstandard is None:
            raise SystemExit(
                "make_pacman_db: the python3-zstandard module is required to read .pkg.tar.zst"
            )
        # makepkg writes frames without the content size in the header, so read
        # through a streaming decompressor instead of one-shot decompress().
        with open(path, "rb") as handle:
            with zstandard.ZstdDecompressor().stream_reader(handle) as reader:
                data = reader.read()
    else:
        data = path.read_bytes()

    info: dict[str, list[str]] = {}
    dirs: set[str] = set()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tf:
        for member in tf.getmembers():
            name = member.name
            while name.startswith("./"):
                name = name[2:]
            if not name:
                continue
            if name.endswith(".PKGINFO"):
                handle = tf.extractfile(member)
                if handle is not None:
                    for line in handle.read().decode("utf-8", "replace").splitlines():
                        if line.startswith("#") or "=" not in line:
                            continue
                        key, value = line.split("=", 1)
                        info.setdefault(key.strip(), []).append(value.strip())
                continue
            if member.isdir():
                dirs.add(name.rstrip("/") + "/")
            else:
                parent = os.path.dirname(name)
                while parent and parent != ".":
                    dirs.add(parent + "/")
                    parent = os.path.dirname(parent)
    return info, sorted(dirs)


def checksums(path: Path) -> tuple[str, str]:
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
            sha.update(chunk)
    return md5.hexdigest(), sha.hexdigest()


def desc_entry(path: Path, info: dict[str, list[str]]) -> tuple[str, str]:
    name = info["pkgname"][0]
    # makepkg writes the full version (including pkgrel) into pkgver
    version = info["pkgver"][0]
    if info.get("pkgrel"):
        version = f"{version}-{info['pkgrel'][0]}"
    entry = f"{name}-{version}"
    md5, sha = checksums(path)

    lines: list[str] = []

    def section(title: str, values: list[str]) -> None:
        lines.append(f"%{title}%")
        lines.extend(values)
        lines.append("")

    section("FILENAME", [path.name])
    section("NAME", [name])
    section("BASE", [info.get("pkgbase", [name])[0]])
    section("VERSION", [version])
    if info.get("pkgdesc"):
        section("DESC", [info["pkgdesc"][0]])
    section("CSIZE", [str(path.stat().st_size)])
    if info.get("size"):
        section("ISIZE", [info["size"][0]])
    section("MD5SUM", [md5])
    section("SHA256SUM", [sha])
    if info.get("url"):
        section("URL", [info["url"][0]])
    if info.get("license"):
        section("LICENSE", info["license"])
    if info.get("arch"):
        section("ARCH", [info["arch"][0]])
    if info.get("builddate"):
        section("BUILDDATE", [info["builddate"][0]])
    if info.get("packager"):
        section("PACKAGER", [info["packager"][0]])
    if info.get("depend"):
        section("DEPENDS", info["depend"])
    if info.get("optdepend"):
        section("OPTDEPENDS", info["optdepend"])
    if info.get("conflict"):
        section("CONFLICTS", info["conflict"])
    if info.get("provides"):
        section("PROVIDES", info["provides"])
    if info.get("replaces"):
        section("REPLACES", info["replaces"])

    return entry, "\n".join(lines)


def write_tar(path: Path, entries: list[tuple[str, str, str]]) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for entry, filename, content in entries:
            data = content.encode("utf-8")
            member = tarfile.TarInfo(name=f"{entry}/{filename}")
            member.size = len(data)
            member.mode = 0o644
            tar.addfile(member, io.BytesIO(data))
    with gzip.open(path, "wb", compresslevel=9) as gz:
        gz.write(buffer.getvalue())


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 1
    repo = Path(argv[0])
    packages = sorted(repo.glob("*.pkg.tar.zst"))
    if not packages:
        print(f"make_pacman_db: no packages in {repo}", file=sys.stderr)
        return 1

    desc_entries: list[tuple[str, str, str]] = []
    files_entries: list[tuple[str, str, str]] = []
    for package in packages:
        info, dirs = read_package(package)
        if "pkgname" not in info or "pkgver" not in info:
            print(f"make_pacman_db: {package.name}: incomplete .PKGINFO", file=sys.stderr)
            return 1
        entry, desc = desc_entry(package, info)
        files = "%FILES%\n" + "\n".join(dirs) + "\n"
        desc_entries.append((entry, "desc", desc))
        files_entries.append((entry, "files", files))
        print(f"  {entry}")

    db_path = repo / "localchat.db.tar.gz"
    files_path = repo / "localchat.files.tar.gz"
    write_tar(db_path, desc_entries)
    write_tar(files_path, files_entries)
    for link, target in ((repo / "localchat.db", db_path.name),
                         (repo / "localchat.files", files_path.name)):
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)
    print(f"wrote {db_path.name} ({len(desc_entries)} packages)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
