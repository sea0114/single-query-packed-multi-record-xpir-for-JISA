#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fetch the pinned XPIR source into a NEW release-root/native_xpir/upstream.

No source is executed. All 142 file hashes are checked before any extraction.
The caller supplies an existing release root containing the original B0 manifest.
Never run this tool to replace the preserved original workspace's upstream tree.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import sys
import tarfile
import urllib.request

COMMIT = "75c5e912cbe6a8d5bf5ac0f3f74a665b0265c78c"
TREE = "dc9d04de9cab7f5e45cb27b49db61cc8cf61349e"
OFFICIAL_REPOSITORY = "https://github.com/XPIR-team/XPIR"
DOWNLOAD_URL = f"https://codeload.github.com/XPIR-team/XPIR/tar.gz/{COMMIT}"
ARCHIVE_PREFIX = f"XPIR-{COMMIT}"
MANIFEST_REL = "manifests/upstream-build-environment.json"
MANIFEST_SHA256 = "19acb1fe7b90ada0160b403c4fff0b52645b1ca2dd54db9c7cf0ab8e118128c1"
UPSTREAM_PREFIX = "native_xpir/upstream/"
EXPECTED_FILES = 142
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_MEMBERS = 1024


class FetchError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise FetchError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def relative_parts(name):
    """Reject aliases and names unsafe on either Windows or POSIX."""
    require(isinstance(name, str) and name, "Empty or non-text archive path")
    require(not any(c in name for c in ("\\", ":", "\0")), "Unsafe path character")
    require(not name.startswith("/"), "Absolute archive path")
    parts = name.split("/")
    require(all(p not in ("", ".", "..") for p in parts), "Traversal or ambiguous path")
    for part in parts:
        require(not part.endswith((" ", ".")), "Windows-ambiguous path suffix")
        stem = part.split(".", 1)[0].upper()
        require(not re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", stem),
                "Windows reserved path component")
    return tuple(parts)


def real_directory(path):
    """Check existing ancestors without accepting symlinks or reparse points."""
    absolute = Path(os.path.abspath(path))
    for item in (absolute, *absolute.parents):
        info = item.lstat()
        require(stat.S_ISDIR(info.st_mode), f"Not a directory: {item}")
        require(not stat.S_ISLNK(info.st_mode), f"Symlink directory: {item}")
        require(not (getattr(info, "st_file_attributes", 0)
                     & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)),
                f"Reparse-point directory: {item}")
    return absolute


def contract(root):
    """Trust only the exact frozen manifest; never repair or regenerate pins."""
    manifest = root / MANIFEST_REL
    data = manifest.read_bytes()
    require(sha256(data) == MANIFEST_SHA256, "B0 build manifest hash mismatch")
    obj = json.loads(data)
    require(obj.get("backend_commit") == COMMIT, "B0 backend commit mismatch")
    upstream = obj.get("upstream_files")
    require(isinstance(upstream, dict) and len(upstream) == EXPECTED_FILES,
            "B0 must pin exactly 142 upstream files")
    expected = {}
    for name, digest in upstream.items():
        require(name.startswith(UPSTREAM_PREFIX), "Unexpected B0 source path")
        relative = name[len(UPSTREAM_PREFIX):]
        relative_parts(relative)
        require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest),
                "Invalid SHA256 in B0 manifest")
        expected[relative] = digest
    require(len({name.casefold() for name in expected}) == EXPECTED_FILES,
            "Case-colliding source paths")
    return expected


def preflight(root):
    root = real_directory(root)
    expected = contract(root)
    parent = root / "native_xpir"
    if os.path.lexists(parent):
        real_directory(parent)
    output = parent / "upstream"
    require(not os.path.lexists(output), "Output already exists; refusing overwrite")
    return root, expected, output


class FixedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        require(newurl == DOWNLOAD_URL, "Unexpected source-download redirect")
        return super().redirect_request(request, fp, code, message, headers, newurl)


def download():
    opener = urllib.request.build_opener(
        FixedRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )
    request = urllib.request.Request(DOWNLOAD_URL, headers={"User-Agent": "XPIR-source-verifier/1"})
    with opener.open(request, timeout=30) as response:
        require(response.geturl() == DOWNLOAD_URL, "Unexpected source-download URL")
        length = response.headers.get("Content-Length")
        if length is not None:
            require(int(length) <= MAX_ARCHIVE_BYTES, "Archive too large")
        archive = response.read(MAX_ARCHIVE_BYTES + 1)
    require(len(archive) <= MAX_ARCHIVE_BYTES, "Archive exceeds size limit")
    return archive, "official-codeload-tarball"


def git_command(repository, *args):
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repository}", "-C", str(repository), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
    )
    require(result.returncode == 0,
            "Local Git source operation failed: " + result.stderr.decode("utf-8", "replace")[-1000:])
    require(len(result.stdout) <= MAX_ARCHIVE_BYTES, "Local Git output too large")
    return result.stdout


def git_archive(repository, expected):
    repository = Path(repository).resolve(strict=True)
    require(git_command(repository, "cat-file", "-t", COMMIT).strip() == b"commit",
            "Pinned Git object is not a commit")
    require(git_command(repository, "rev-parse", COMMIT + "^{tree}").decode().strip() == TREE,
            "Pinned Git tree mismatch")
    rows = git_command(repository, "ls-tree", "-rz", "--full-tree", COMMIT).split(b"\0")
    names = []
    for row in rows:
        if not row:
            continue
        metadata, encoded = row.split(b"\t", 1)
        mode, kind, oid = metadata.split()
        require(mode in (b"100644", b"100755") and kind == b"blob",
                "Git tree contains a link, submodule, or nonregular object")
        name = encoded.decode("utf-8")
        relative_parts(name)
        names.append(name)
    require(len(names) == EXPECTED_FILES and set(names) == set(expected),
            "Pinned Git file set differs from B0")
    data = git_command(repository, "archive", "--format=tar",
                       f"--prefix={ARCHIVE_PREFIX}/", COMMIT)
    return data, "local-git-archive-verified-commit-and-tree"


def verified_payloads(archive, expected):
    """Read regular files only, validate in memory; never use extract/extractall."""
    require(len(archive) <= MAX_ARCHIVE_BYTES, "Archive exceeds size limit")
    allowed_directories = {ARCHIVE_PREFIX}
    for name in expected:
        parts = relative_parts(name)
        for count in range(1, len(parts)):
            allowed_directories.add(ARCHIVE_PREFIX + "/" + "/".join(parts[:count]))
    payloads, seen = {}, set()
    total = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as bundle:
        for number, member in enumerate(bundle, 1):
            require(number <= MAX_MEMBERS, "Excessive archive members")
            require(member.type in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE),
                    "Archive contains link, device, sparse, or unsupported member")
            require(not getattr(member, "sparse", None), "Sparse member rejected")
            raw_name = member.name
            if member.isdir() and raw_name.endswith("/"):
                raw_name = raw_name[:-1]
            parts = relative_parts(raw_name)
            require(parts[0] == ARCHIVE_PREFIX, "Unexpected archive root")
            normalized = "/".join(parts)
            require(normalized not in seen, "Duplicate archive member")
            seen.add(normalized)
            if member.isdir():
                require(member.size == 0 and normalized in allowed_directories,
                        "Unexpected archive directory")
                continue
            require(len(parts) > 1, "Archive root cannot be a regular file")
            name = "/".join(parts[1:])
            require(name in expected, "Unpinned extra source file: " + name)
            require(0 <= member.size <= MAX_FILE_BYTES, "Source file exceeds size limit")
            total += member.size
            require(total <= MAX_TOTAL_BYTES, "Expanded archive exceeds size limit")
            handle = bundle.extractfile(member)
            require(handle is not None, "Missing regular-file content")
            with handle:
                data = handle.read(MAX_FILE_BYTES + 1)
            require(len(data) == member.size, "Source file length mismatch")
            require(sha256(data) == expected[name], "Pinned source SHA256 mismatch: " + name)
            payloads[name] = (data, 0o755 if member.mode & 0o111 else 0o644)
    require(set(payloads) == set(expected) and len(payloads) == EXPECTED_FILES,
            "Archive does not contain exactly all 142 pinned source files")
    return payloads


def install(root, output, payloads, expected):
    # Recheck output and manifest after acquisition. Never clean a failed attempt.
    current_root, current_expected, current_output = preflight(root)
    require(current_expected == expected and current_output == output,
            "Source contract changed during acquisition")
    if not output.parent.exists():
        output.parent.mkdir()  # A concurrent creation fails, rather than replacing it.
    real_directory(output.parent)
    output.mkdir()  # Exclusive destination creation; existing trees are never merged.
    for name, (data, mode) in sorted(payloads.items()):
        target = output.joinpath(*relative_parts(name))
        target.parent.mkdir(parents=True, exist_ok=True)
        real_directory(target.parent)
        with target.open("xb") as handle:
            handle.write(data)
        os.chmod(target, mode)
    observed = {p.relative_to(output).as_posix(): sha256(p.read_bytes())
                for p in output.rglob("*") if p.is_file()}
    require(observed == expected, "Post-write file/hash verification failed; preserve output")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True,
                        help="Existing staging/release root; native_xpir/upstream must not exist")
    parser.add_argument("--git-repository", type=Path,
                        help="Optional local Git object repository instead of a network download")
    parser.add_argument("--check-contract-only", action="store_true",
                        help="Check root, absence of output, and exact B0 manifest; no download/write")
    args = parser.parse_args(argv)
    root, expected, output = preflight(args.root)
    if args.check_contract_only:
        print(json.dumps({"status": "CONTRACT_OK_NO_FETCH", "commit": COMMIT,
                          "expected_files": EXPECTED_FILES, "manifest_sha256": MANIFEST_SHA256}))
        return 0
    archive, method = (git_archive(args.git_repository, expected)
                       if args.git_repository else download())
    payloads = verified_payloads(archive, expected)
    install(root, output, payloads, expected)
    print(json.dumps({"status": "SOURCE_VERIFIED_NOT_BUILT", "commit": COMMIT,
                      "expected_tree": TREE, "verified_files": len(payloads),
                      "manifest_sha256": MANIFEST_SHA256,
                      "archive_sha256_observed": sha256(archive), "acquisition": method,
                      "official_repository": OFFICIAL_REPOSITORY,
                      "output_relative": "native_xpir/upstream",
                      "historical_binary_identity_claimed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FetchError, OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "BLOCKED_OR_FAILED", "error": str(error),
                          "partial_output_preserved_if_created": True}), file=sys.stderr)
        raise SystemExit(1)
