"""Deliver source-owned extension files while preserving unrelated files."""
import argparse
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import os

OWNER = ".ws-owned-files.json"


def _relative(value):
    if not isinstance(value, str):
        raise ValueError("invalid owned filename")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(p in ("", ".", "..") for p in value.split("/")):
        raise ValueError(f"unsafe owned filename: {value}")
    if value == OWNER:
        raise ValueError("owner manifest cannot own itself")
    return path


def _target(root, value):
    path = root
    if path.is_symlink():
        raise ValueError(f"symlink destination: {path}")
    for part in _relative(value).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"symlink destination: {path}")
    return path


def source_files(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("source must be a real directory")
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"source symlink: {path}")
        rel = path.relative_to(root).as_posix()
        if path.is_file() and path.name != "gschemas.compiled" and not any(p.startswith(".") for p in path.relative_to(root).parts):
            _relative(rel)
            files.append(rel)
    return files


def install_files(source, destination):
    source, destination = Path(source), Path(destination)
    files = source_files(source)
    owner = destination / OWNER
    if owner.is_symlink() or destination.is_symlink():
        raise ValueError("symlink owner/destination")
    previous = json.loads(owner.read_text()) if owner.exists() else []
    if not isinstance(previous, list):
        raise ValueError("invalid owner manifest")
    # Validate every source and deletion target before mutating anything.
    targets = {name: _target(destination, name) for name in files}
    stale = [_target(destination, name) for name in previous if name not in files]
    destination.mkdir(parents=True, exist_ok=True)
    for name, target in targets.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
        target.chmod(0o644)
    for target in stale:
        if target.is_file():
            target.unlink()
    with tempfile.NamedTemporaryFile(mode="w", dir=destination, delete=False) as stream:
        json.dump(files, stream)
        temp = stream.name
    os.replace(temp, owner)
    return files


def verify_files(source, destination):
    source, destination = Path(source), Path(destination)
    failures = []
    for name in source_files(source):
        try:
            target = _target(destination, name)
            if not target.is_file() or target.read_bytes() != (source / name).read_bytes():
                failures.append(name)
        except ValueError:
            failures.append(name)
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["install", "verify"])
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.action == "install":
        install_files(args.source, args.destination)
    else:
        failures = verify_files(args.source, args.destination)
        for name in failures:
            print(name)
        return bool(failures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
