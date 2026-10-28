#!/usr/bin/env python3
"""Check ZH/EN contract template structural parity.

Compares fenced (```xml) block tag sets, [NEXT_STATE: ...] target sets,
and `## N.` section-number sets between the ZH template and its EN twin.
Prose mentions outside fences are ignored: only the machine-consumed
structure must match.

Also asserts each file's `version:` frontmatter matches versions.json
(steps on the step-2 stamp mechanism's toes deliberately: parity without
version equality is a false pass).

Usage:
    python3 tools/check_zh_en_parity.py           # check all pairs
    python3 tools/check_zh_en_parity.py --check   # same (default is check-only)
    pairs are hardcoded: integrated + modular.

Exit non-zero with named file + missing/extra items on any drift.
"""

import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

PAIRS = [
    ("template/integrated/ALL_IN_RULE.md",
     "template/integrated/ALL_IN_RULE.en.md",
     "integrated"),
    ("template/modular/RULE.md",
     "template/modular/RULE.en.md",
     "modular"),
]

TAG_RE = re.compile(r"</?[A-Z][A-Z_0-9]*>")
NEXT_RE = re.compile(r"\[NEXT_STATE:\s*([^\]]+)\]")
SECTION_RE = re.compile(r"(?m)^##\s+(\d+)\.")
VERSION_RE = re.compile(r"(?m)^version:\s*(\S+)")


def fenced_blocks(text):
    """Yield contents of ```xml fenced blocks (strict pairing, loud on stray)."""
    lines = text.splitlines()
    blocks, buf, in_block = [], [], False
    for i, line in enumerate(lines, 1):
        if line.strip() == "```xml":
            if in_block:
                raise ValueError(f"line {i}: nested ```xml opener")
            in_block = True
            buf = []
        elif line.strip() == "```":
            # Bare closes for non-xml fences (```bash etc.) appear as lone
            # closers; ignore them unless we are inside an xml block.
            if in_block:
                blocks.append("\n".join(buf))
                in_block = False
        elif in_block:
            buf.append(line)
    if in_block:
        raise ValueError("unclosed ```xml block at EOF")
    return blocks


def structure_of(text, path):
    tags, nexts = set(), set()
    for block in fenced_blocks(text):
        tags.update(TAG_RE.findall(block))
        nexts.update(t.strip() for t in NEXT_RE.findall(block) for t in [t])
    sections = set(SECTION_RE.findall(text))
    m = VERSION_RE.search(text)
    version = m.group(1) if m else None
    return {"tags": tags, "nexts": nexts, "sections": sections,
            "version": version, "path": path}


def check_pair(zh_rel, en_rel, versions):
    zh_path = os.path.join(REPO_ROOT, zh_rel)
    en_path = os.path.join(REPO_ROOT, en_rel)
    with open(zh_path, encoding="utf-8") as f:
        zh = structure_of(f.read(), zh_rel)
    with open(en_path, encoding="utf-8") as f:
        en = structure_of(f.read(), en_rel)
    problems = []
    for key in ("tags", "nexts", "sections"):
        only_zh = sorted(zh[key] - en[key])
        only_en = sorted(en[key] - zh[key])
        if only_zh:
            problems.append(f"{zh_rel} has extra {key}: {only_zh}")
        if only_en:
            problems.append(f"{en_rel} has extra {key}: {only_en}")
    if zh["version"] != en["version"]:
        problems.append(f"version mismatch: {zh_rel}={zh['version']} vs "
                        f"{en_rel}={en['version']}")
    if versions:
        for side in (zh, en):
            want = versions.get("integrated") if "integrated" in side["path"] \
                else versions.get("modular")
            if side["version"] != want:
                problems.append(f"{side['path']} version {side['version']} != "
                                f"versions.json {want}")
    return problems


def main(argv):
    _ = argv
    versions_path = os.path.join(REPO_ROOT, "versions.json")
    try:
        with open(versions_path, encoding="utf-8") as f:
            versions = json.load(f)
    except OSError:
        versions = {}
    all_problems = []
    for zh_rel, en_rel, _label in PAIRS:
        try:
            all_problems.extend(check_pair(zh_rel, en_rel, versions))
        except ValueError as e:
            all_problems.append(f"{zh_rel}/{en_rel}: fence parse error: {e}")
    if all_problems:
        for p in all_problems:
            print(f"PARITY-DRIFT: {p}")
        return 1
    print("parity: ZH/EN structures match (tags, NEXT_STATE, sections, versions)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
