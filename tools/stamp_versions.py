#!/usr/bin/env python3
"""Stamp versions from versions.json into all version-carrying files.

Single source of truth: <repo-root>/versions.json ::

    {"package": "3.6.1",
     "integrated": "15.1.0-deterministic",
     "modular": "3.1.0-engineering-hardened",
     "schema": "2.1.0",
     "schema_modular": "2.1.0"}

Usage:
    python3 tools/stamp_versions.py          # write all files (atomic)
    python3 tools/stamp_versions.py --check   # zero writes; non-zero exit + names file on drift

Write targets (setup.py carries a single version= line; stamp keeps the
installer.py CLI_VERSION fallback in sync with it):
  - setup.py                                  version="..."
  - installer.py                              CLI_VERSION = "..."
  - swda/__init__.py                          __version__ = "..."
  - template/integrated/ALL_IN_RULE{,.en}.md  version: ...
  - template/modular/RULE{,.en}.md            version: ...
  - docs/contracts/output-schema.md           heading vX.Y.Z (first line only)
  - docs/contracts/output-schema-modular.md   heading vX.Y.Z (first line only)

docs/releases.md correspondence tables are append-only history: never touched.

All writes are atomic (temp file in same directory + os.replace); a failed
write leaves no half-file behind and aborts loudly.
"""

import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VERSIONS_PATH = os.path.join(REPO_ROOT, "versions.json")


def load_versions(path=VERSIONS_PATH):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    required = ("package", "integrated", "modular", "schema", "schema_modular")
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"{path} missing keys: {missing}")
    return data


def atomic_write(path, content):
    tmp = path + ".tmp-stamp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)


def replace_once(path, pattern, repl, check_only):
    """Replace first regex match in path; return (ok, detail)."""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    new, n = re.subn(pattern, repl, content, count=1)
    if n != 1:
        return False, f"{path}: pattern {pattern!r} matched {n} times (expected 1)"
    if new == content:
        return True, f"{path}: already in sync"
    if check_only:
        return False, f"{path}: OUT OF SYNC"
    atomic_write(path, new)
    return True, f"{path}: stamped"


def stamp_all(versions, check_only=False):
    results = []

    def sub(path_rel, pattern, repl):
        path = os.path.join(REPO_ROOT, path_rel)
        ok, detail = replace_once(path, pattern, repl, check_only)
        results.append((ok, detail))
        return ok

    sub("setup.py", r'version\s*=\s*["\'][^"\']+["\']',
        f'version="{versions["package"]}"')
    sub("installer.py", r'CLI_VERSION\s*=\s*["\'][^"\']+["\']',
        f'CLI_VERSION = "{versions["package"]}"')
    sub("swda/__init__.py", r'__version__\s*=\s*["\'][^"\']+["\']',
        f'__version__ = "{versions["package"]}"')
    for name in ("template/integrated/ALL_IN_RULE.md",
                 "template/integrated/ALL_IN_RULE.en.md"):
        sub(name, r"(?m)^version:\s*\S+",
            f'version: {versions["integrated"]}')
    for name in ("template/modular/RULE.md",
                 "template/modular/RULE.en.md"):
        sub(name, r"(?m)^version:\s*\S+",
            f'version: {versions["modular"]}')
    # Schema headings: first line only, e.g. "# SWDD Output Schema Contract v2.1.0".
    # (?m)^ anchors to line start; count=1 keeps it to the heading line.
    sub("docs/contracts/output-schema.md", r"(?m)^(# .*\bv)\d+\.\d+\.\d+",
        rf"\g<1>{versions['schema']}")
    sub("docs/contracts/output-schema-modular.md", r"(?m)^(# .*\bv)\d+\.\d+\.\d+",
        rf"\g<1>{versions['schema_modular']}")
    return results


def main(argv):
    check_only = "--check" in argv
    try:
        versions = load_versions()
    except (OSError, ValueError) as e:
        print(f"stamp_versions: {e}", file=sys.stderr)
        return 2
    results = stamp_all(versions, check_only=check_only)
    failed = [d for ok, d in results if not ok]
    for _, detail in results:
        print(detail)
    if failed:
        print(f"stamp_versions: {len(failed)} file(s) out of sync", file=sys.stderr)
        return 1
    if check_only:
        print("stamp_versions: all files in sync with versions.json")
    else:
        print("stamp_versions: done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
