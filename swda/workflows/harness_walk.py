#!/usr/bin/env python3
"""
SWDA Harness-Walk Proof: scanner that proves an OMP session really walked
the defined harness.

Harness definition under test (APPEND_SYSTEM.md, integrated contract):
  * Delivery-Gate Tool Binding (end of PHASE_4 SYNTHESIS): before leaving
    SYNTHESIS, call the ``swda_reconcile`` MCP tool on every modified Python
    file; a ``valid:false`` result returns the task to CRUCIBLE. Optionally
    pre-screen shell/code with ``swda_firewall_audit``.
  * FSM discipline: outputs wrapped in phase XML tags
    (``<INTENT_GATE_RESULT>`` ... ``<TASK_SUMMARY_REPORT>``), each turn ending
    with ``[NEXT_STATE: ...]``.
  * FAST_PASS is objective: it applies only when the turn performs no file
    writes. A model must not self-declare FAST_PASS to skip gates.

What counts as proof (hard evidence first):
  * MCP invocation traces: ``swda_reconcile`` / ``swda_firewall_audit`` calls
    in the OMP session jsonl (``tool_execution_start`` + assistant ``toolCall``
    shapes + flat top-level ``toolCall`` items; tool names are normalized so
    ``mcp__swda__swda_reconcile``-style wrappers still count; ``toolResult``
    only feeds verdict extraction, never counting, so one call is never
    double-counted).
  * CLI fallback traces: ``swda reconcile`` / ``swda run`` / ``swda doctor``
    as real shell commands (parsed with shlex, so ``echo "swda reconcile"``
    does NOT count). CLI reconcile verdicts are extracted from the matching
    bash ``toolResult`` stdout (``Reverse Reconciliation Passed|FAILED`` or
    ``"valid": true|false``); a CLI gate with no observable verdict is
    reported under ``unverified``, never as a pass verdict.
  * Soft evidence: FSM XML tags + ``[NEXT_STATE]`` in assistant text. A tag
    counts only as an open+close pair, so quoting a tag name in discussion
    does not satisfy the discipline check.

Levels:
  * ``fast_pass``: no Python touched, no gate needed (chat) -> passed.
  * ``full``:     Python modified + gate called + FSM discipline + gate ran
    at/after the SYNTHESIS spec + no ``valid:false`` verdict -> passed.
  * ``gate``:     Python modified + gate called, but no FSM trace (gate
    walked, prompt discipline missing) -> passed with ``fsm-discipline``
    note in ``missing``.
  * ``none``:     Python modified but no gate call (or gate ran only before
    the spec, or any file's latest gate verdict is ``valid:false`` and the
    task was delivered anyway) -> failed.

Stdlib only, no MCP transport needed: the scanner reads session ``.jsonl``
files as text.
"""
import json
import os
import re
import shlex
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

SWDA_TOOL_NAMES = (
    "swda_reconcile",
    "swda_firewall_audit",
    "swda_stats",
    "swda_models",
)

FSM_TAGS = (
    "INTENT_GATE_RESULT",
    "DESTRUCT_RESULT",
    "GATHER_RESULT",
    "HYPERPLAN_RESULT",
    "SYSTEM_SPECIFICATION",
    "TASK_SUMMARY_REPORT",
)

DOWNSTREAM_TAGS = (
    "HYPERPLAN_RESULT",
    "SYSTEM_SPECIFICATION",
    "TASK_SUMMARY_REPORT",
)

NEXT_STATE_RE = re.compile(r"\[NEXT_STATE:[^\]]+\]")
VALID_RE = re.compile(r'"valid"\s*:\s*(true|false)', re.IGNORECASE)
ALLOWED_RE = re.compile(r'"allowed"\s*:\s*(true|false)', re.IGNORECASE)
RECONCILE_PASS_RE = re.compile(r"Reverse Reconciliation Passed", re.IGNORECASE)
RECONCILE_FAIL_RE = re.compile(r"Reverse Reconciliation FAILED", re.IGNORECASE)
RECONCILE_UNVERIFIABLE_RE = re.compile(r"Reverse Reconciliation UNVERIFIABLE", re.IGNORECASE)
VERDICT_LINE_RE = re.compile(r'"verdict"\s*:\s*"(valid|invalid|unverifiable)"', re.IGNORECASE)

SHELL_SEP_RE = re.compile(r"&&|\|\||;|\||\n")
REDIRECT_PY_RE = re.compile(r">\s*([^\s;|&'\"]+\.py)\b")
TEE_PY_RE = re.compile(r"\btee\b[^\n|&;]*?([^\s;|&'\"]+\.py)\b")
# Inline interpreters whose -c source can write .py files out of band.
INLINE_PY_RE = re.compile(r"\b(?:python3?|perl|node|ruby)\b[^\n|&;]*?-c\b")
PY_WRITE_CALL_RE = re.compile(r"open\s*\([^)]*['\"]\s*w['\"]|write_text|write_bytes|\.py['\"]?\s*\)?\s*,?\s*['\"]\s*w")
# Unmodeled file-write channels: sed -i, git apply, mv/cp/install onto .py.
SED_PY_RE = re.compile(r"\bsed\b[^\n|&;]*?-i[^\n|&;]*?([^\s;|&'\"]+\.py)\b")
GIT_APPLY_RE = re.compile(r"\bgit\b[^\n|&;]*?\bapply\b")
MVCP_PY_RE = re.compile(r"\b(?:mv|cp|install)\b[^\n|&;]*?([^\s;|&'\"]+\.py)\b")

def _bash_py_targets(command: str) -> Set[str]:
    """Collects .py targets of redirect/tee/sed/mv/cp writes (basenames)."""
    found: Set[str] = set()
    for seg in SHELL_SEP_RE.split(command):
        for m in REDIRECT_PY_RE.finditer(seg):
            found.add(os.path.basename(m.group(1)))
        for m in TEE_PY_RE.finditer(seg):
            found.add(os.path.basename(m.group(1)))
        for m in SED_PY_RE.finditer(seg):
            found.add(os.path.basename(m.group(1)))
        for m in MVCP_PY_RE.finditer(seg):
            found.add(os.path.basename(m.group(1)))
        if GIT_APPLY_RE.search(seg):
            # A patch may touch any file: opaque marker, never fast_pass.
            found.add("<patch-apply>")
    return found


PY_WRITE_TOOL_NAMES = ("edit", "write")

BEGIN_MARKER = "<!-- swda-begin -->"
END_MARKER = "<!-- swda-end -->"
CONTRACT_HEADER = "# Swarm-Driven Agent (SWDA) Integrated"


def normalize_tool_name(name: Any) -> str:
    """Maps MCP wrapper spellings to the canonical swda tool name.

    ``mcp__swda__swda_reconcile`` -> ``swda_reconcile``; unknown names pass
    through lowercased so exact-match call sites keep working.
    """
    if not isinstance(name, str):
        return ""
    n = name.strip().lower()
    if n in SWDA_TOOL_NAMES:
        return n
    for cand in SWDA_TOOL_NAMES:
        if n == cand or n.endswith("__" + cand) or n.endswith("/" + cand) or n.endswith("." + cand):
            return cand
    return n


def _is_py_path(value: Any) -> bool:
    return isinstance(value, str) and value.strip().endswith(".py")


def _args_touch_py(args: Any) -> bool:
    """True when ANY nested arg value looks like a .py path.

    Value scan (not fixed keys): tools using ``file_path``, ``filename``,
    ``target`` or nested option dicts are all detected.
    """
    return bool(_args_py_files(args))


def _args_py_files(args: Any) -> Set[str]:
    """Collects every nested .py path value (basenames)."""
    found: Set[str] = set()
    stack = [args]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)
        elif _is_py_path(cur):
            found.add(os.path.basename(cur.strip()))
    return found


def _match_argv(argv: List[str]) -> Optional[Tuple[str, Optional[str]]]:
    """Matches one shell segment's argv; returns (label, file-or-None)."""
    if not argv:
        return None
    head = os.path.basename(argv[0]).lower()
    rest = argv[1:]
    if head in ("python", "python3") and rest[:1] == ["-m"] and len(rest) >= 2:
        mod = rest[1]
        if mod == "swda.cli":
            return _match_swda_subcommand(rest[2:])
        if mod == "installer":
            return ("doctor", None) if rest[2:3] == ["doctor"] else None
        return None
    if head in ("swda", "swda.cli"):
        return _match_swda_subcommand(rest)
    if head == "installer.py":
        return ("doctor", None) if rest[:1] == ["doctor"] else None
    base = os.path.basename(head)
    if base in ("python", "python3") and rest[:1] == ["-m"] and len(rest) >= 2:
        return _match_argv(["swda"] + rest[2:]) if rest[1] in ("swda.cli", "installer") else None
    return None


def _match_swda_subcommand(rest: List[str]) -> Optional[Tuple[str, Optional[str]]]:
    if not rest:
        return None
    sub, args = rest[0], rest[1:]
    if sub == "reconcile":
        target = next((a for a in args if not a.startswith("-")), None)
        return ("reconcile", target)
    if sub == "run":
        return ("run-mock", None) if "--mock" in args else ("run", None)
    if sub == "doctor":
        return ("doctor", None)
    if sub == "stats":
        return ("stats", None)
    if sub == "scan":
        return ("scan", None)
    if sub == "models":
        return ("models", None)
    return None


def _match_cli(command: str) -> Optional[Tuple[str, Optional[str]]]:
    """Matches real shell invocations; ``echo "swda reconcile"`` never matches."""
    hits = _match_cli_all(command)
    return hits[0] if hits else None


def _match_cli_all(command: str) -> List[Tuple[str, Optional[str]]]:
    """Matches every shell segment (``a.py; b.py`` both count)."""
    out: List[Tuple[str, Optional[str]]] = []
    for seg in SHELL_SEP_RE.split(command):
        seg = seg.strip()
        if not seg:
            continue
        try:
            argv = shlex.split(seg, posix=True)
        except ValueError:
            continue
        hit = _match_argv(argv)
        if hit:
            out.append(hit)
    return out


def _bash_inline_py_write(command: str) -> bool:
    """Detects ``python -c "open('x.py','w')..."`` style out-of-band writes."""
    for seg in SHELL_SEP_RE.split(command):
        if INLINE_PY_RE.search(seg) and PY_WRITE_CALL_RE.search(seg):
            return True
    return False


def _content_texts(content: Any) -> List[str]:
    texts: List[str] = []
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    texts.append(item["text"])
    return texts


def _iter_toolcall_items(content: Any):
    """Yields (name, args, call_id) for both assistant toolCall shapes."""
    if not isinstance(content, list):
        return
    for item in content:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("toolCall"), dict):
            tc = item["toolCall"]
            yield tc.get("name", ""), tc.get("arguments", {}), tc.get("id")
        elif item.get("type") == "toolCall" and isinstance(item.get("name"), str):
            yield item.get("name", ""), item.get("arguments", item.get("partialArgs", {})), item.get("id")


def _count_tag_pairs(text: str, tag: str) -> int:
    """Counts open+close pairs; a bare mention without a closing tag is 0."""
    return min(text.count(f"<{tag}>"), text.count(f"</{tag}>"))


def _extract_reconcile_verdict(stdout: str) -> Optional[str]:
    """Extracts the reconcile verdict line: valid | invalid | unverifiable | None."""
    if RECONCILE_FAIL_RE.search(stdout):
        return "invalid"
    if RECONCILE_UNVERIFIABLE_RE.search(stdout):
        return "unverifiable"
    if RECONCILE_PASS_RE.search(stdout):
        return "valid"
    m = VERDICT_LINE_RE.search(stdout)
    if m:
        return m.group(1).lower()
    m = VALID_RE.search(stdout)
    if m:
        return "valid" if m.group(1).lower() == "true" else "invalid"
    return None


def scan_lines(lines: Iterable[str]) -> Dict[str, Any]:
    swda_tool_calls: Dict[str, int] = {name: 0 for name in SWDA_TOOL_NAMES}
    cli_harness_calls: List[str] = []
    fsm_tags: Dict[str, int] = {tag: 0 for tag in FSM_TAGS}
    next_state_count = 0
    py_modifications = 0
    modified_files: Set[str] = set()
    cli_reconcile_count = 0
    reconcile_idxs: List[int] = []
    spec_idxs: List[int] = []
    gate_verdicts: List[bool] = []
    gate_verdicts_by_file: Dict[str, List[bool]] = {}
    firewall_verdicts: List[bool] = []
    unverified: List[str] = []
    pending: Dict[str, Dict[str, Any]] = {}
    seen_call_ids = set()
    def _record_verdict(file: Optional[str], verdict: bool) -> None:
        gate_verdicts.append(verdict)
        if file:
            gate_verdicts_by_file.setdefault(os.path.basename(file), []).append(verdict)
    def _count_invocation(name: str, args: Any, call_id: Any, idx: int) -> None:
        canon = normalize_tool_name(name)
        if canon not in SWDA_TOOL_NAMES:
            return
        if call_id and call_id in seen_call_ids:
            return
        if call_id:
            seen_call_ids.add(call_id)
        swda_tool_calls[canon] += 1
        if canon == "swda_reconcile":
            reconcile_idxs.append(idx)
            file = args.get("file") if isinstance(args, dict) else None
            if call_id:
                pending[str(call_id)] = {"kind": "reconcile", "file": os.path.basename(file) if isinstance(file, str) else None}

    def _handle_bash_command(cmd: str, call_id: Any, idx: int) -> None:
        nonlocal py_modifications, cli_reconcile_count
        hits = _match_cli_all(cmd)
        for label, target in hits:
            cli_harness_calls.append(f"{label}: {cmd[:120]}")
            if label == "reconcile":
                cli_reconcile_count += 1
                reconcile_idxs.append(idx)
                if call_id:
                    pending[str(call_id)] = {"kind": "cli-reconcile", "file": os.path.basename(target) if target else None}
        if not hits:
            touched = _bash_py_targets(cmd)
            if touched:
                py_modifications += 1
                modified_files.update(touched)
            elif _bash_inline_py_write(cmd):
                # Inline interpreter with a write-shaped -c source: the target
                # file is unknowable, so record an opaque marker that can never
                # be covered by a file verdict (fail-closed, never fast_pass).
                py_modifications += 1
                modified_files.add("<inline-python-write>")

    for idx, line in enumerate(lines):
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(obj, dict):
            continue

        # Shape 0: flat top-level toolCall item.
        if obj.get("type") == "toolCall" and isinstance(obj.get("name"), str):
            _count_invocation(obj.get("name", ""), obj.get("arguments", obj.get("partialArgs", {})),
                              obj.get("id"), idx)
            if normalize_tool_name(obj.get("name", "")) in PY_WRITE_TOOL_NAMES:
                touched = _args_py_files(obj.get("arguments", {}))
                if touched:
                    py_modifications += 1
                    modified_files.update(touched)
            continue

        # Shape 1: tool_execution_start envelope.
        if obj.get("customType") == "tool_execution_start":
            data = obj.get("data", {})
            if not isinstance(data, dict):
                continue
            tname = data.get("toolName", "")
            args = data.get("args", {})
            cid = data.get("toolCallId")
            _count_invocation(tname, args, cid, idx)
            if normalize_tool_name(tname) in PY_WRITE_TOOL_NAMES:
                touched = _args_py_files(args)
                if touched:
                    py_modifications += 1
                    modified_files.update(touched)
            if normalize_tool_name(tname) == "bash" and isinstance(args, dict):
                cmd = args.get("command", "")
                if isinstance(cmd, str):
                    _handle_bash_command(cmd, cid, idx)
            continue

        # Shape 2/3: session message envelope.
        if obj.get("type") != "message":
            continue
        msg = obj.get("message", {})
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")

        if role == "assistant":
            content = msg.get("content", [])
            for name, args, cid in _iter_toolcall_items(content):
                _count_invocation(name, args, cid, idx)
                if normalize_tool_name(name) in PY_WRITE_TOOL_NAMES:
                    touched = _args_py_files(args)
                    if touched:
                        py_modifications += 1
                        modified_files.update(touched)
                if normalize_tool_name(name) == "bash" and isinstance(args, dict):
                    cmd = args.get("command", "")
                    if isinstance(cmd, str):
                        _handle_bash_command(cmd, cid, idx)
            for text in _content_texts(content):
                for tag in FSM_TAGS:
                    n = _count_tag_pairs(text, tag)
                    if n:
                        fsm_tags[tag] += n
                        if tag == "SYSTEM_SPECIFICATION":
                            spec_idxs.extend([idx] * n)
                next_state_count += len(NEXT_STATE_RE.findall(text))
        elif role == "toolResult":
            # Verdicts only; never counted (avoids double-counting the call).
            tname = msg.get("toolName", "")
            canon = normalize_tool_name(tname)
            blob = "\n".join(_content_texts(msg.get("content", [])))
            cid = msg.get("toolCallId")
            entry = pending.pop(str(cid), None) if cid else None
            if canon == "swda_reconcile":
                m = VERDICT_LINE_RE.search(blob)
                if m:
                    verdict = m.group(1).lower()
                else:
                    m = VALID_RE.search(blob)
                    verdict = ("valid" if m.group(1).lower() == "true" else "invalid") if m else None
                if verdict == "unverifiable":
                    unverified.append(f"unverified: reconcile {entry.get('file') if entry else '(unknown file)'}: needs human confirmation")
                elif verdict in ("valid", "invalid"):
                    _record_verdict(entry.get("file") if entry else None, verdict == "valid")
            elif canon == "swda_firewall_audit":
                m = ALLOWED_RE.search(blob)
                if m:
                    firewall_verdicts.append(m.group(1).lower() == "true")
            elif canon == "bash" and entry and entry.get("kind") == "cli-reconcile":
                verdict = _extract_reconcile_verdict(blob)
                if verdict is None:
                    unverified.append(f"unverified: cli-reconcile {entry.get('file') or '(unknown file)'}: no verdict in output")
                elif verdict == "unverifiable":
                    unverified.append(f"unverified: cli-reconcile {entry.get('file') or '(unknown file)'}: needs human confirmation")
                else:
                    _record_verdict(entry.get("file"), verdict == "valid")

    for cid, entry in pending.items():
        if entry.get("kind") == "cli-reconcile":
            unverified.append(f"unverified: cli-reconcile {entry.get('file') or '(unknown file)'}: no matching toolResult")
        elif entry.get("kind") == "reconcile":
            unverified.append(f"unverified: reconcile {entry.get('file') or '(unknown file)'}: no verdict observed")

    reconcile_count = swda_tool_calls["swda_reconcile"] + cli_reconcile_count
    firewall_count = swda_tool_calls["swda_firewall_audit"]
    fsm_ok = (
        fsm_tags["INTENT_GATE_RESULT"] > 0
        and next_state_count > 0
        and any(fsm_tags[t] > 0 for t in DOWNSTREAM_TAGS)
    )
    has_spec = fsm_tags["SYSTEM_SPECIFICATION"] > 0
    first_spec = min(spec_idxs) if spec_idxs else None
    order_ok = True
    if first_spec is not None and reconcile_idxs:
        order_ok = any(i >= first_spec for i in reconcile_idxs)

    file_failed = sorted(f for f, vs in gate_verdicts_by_file.items() if vs and vs[-1] is False)
    verified_valid = {f for f, vs in gate_verdicts_by_file.items() if vs and vs[-1] is True}
    pending_files = {e.get("file") for e in pending.values() if e.get("file")}
    uncovered = sorted(f for f in modified_files if f not in verified_valid and f not in pending_files)
    missing: List[str] = []
    # FAST_PASS is objective: no Python writes observed -> no gate required,
    # regardless of what the model self-declares (never trust Tier-1
    # self-classification as proof of anything).
    if py_modifications == 0 and reconcile_count == 0:
        level = "fast_pass"
        passed = True
        if any(fsm_tags.values()):
            missing.append("info: FSM trace present on a read-only turn (discipline kept, no gate required)")
    elif reconcile_count == 0 and py_modifications > 0:
        level = "none"
        passed = False
        missing.append("delivery-gate: swda_reconcile not called for modified Python (MCP or `swda reconcile` CLI)")
    elif file_failed:
        level = "none"
        passed = False
        missing.append(
            "delivery-gate: swda_reconcile returned valid:false for "
            + ", ".join(file_failed)
            + " (task must return to CRUCIBLE, not deliver)"
        )
    elif gate_verdicts and gate_verdicts[-1] is False:
        level = "none"
        passed = False
        missing.append("delivery-gate: swda_reconcile returned valid:false (task must return to CRUCIBLE, not deliver)")
    elif uncovered:
        level = "none"
        passed = False
        missing.append(
            "coverage: modified but never verified-valid: "
            + ", ".join(uncovered)
            + " (verify every modified file, not an innocent bystander)"
        )
    elif not order_ok:
        level = "none"
        passed = False
        missing.append("order: swda_reconcile ran only before <SYSTEM_SPECIFICATION> (gate must run at/after the spec)")
    elif reconcile_count > 0 and not gate_verdicts:
        # A gate call with zero observed verdicts is not proof of anything:
        # cap at `gate` and surface the unverified entries.
        level = "gate"
        passed = True
    elif fsm_ok:
        if not has_spec:
            level = "gate"
            passed = True
            missing.append("order: no <SYSTEM_SPECIFICATION> observed (gate walked, spec evidence missing)")
        else:
            level = "full"
            passed = True
    elif py_modifications > 0 or reconcile_count > 0:
        level = "gate"
        passed = True
        missing.append("fsm-discipline: no INTENT_GATE/NEXT_STATE trace (soft evidence missing; gate walked)")
    else:
        level = "gate"
        passed = True
    missing.extend(unverified)

    return {
        "swda_tool_calls": swda_tool_calls,
        "cli_harness_calls": cli_harness_calls,
        "fsm_tags": fsm_tags,
        "next_state_count": next_state_count,
        "py_modifications": py_modifications,
        "modified_files": sorted(modified_files),
        "uncovered_files": uncovered,
        "reconcile_count": reconcile_count,
        "firewall_count": firewall_count,
        "gate_verdicts": gate_verdicts,
        "gate_verdicts_by_file": gate_verdicts_by_file,
        "unverified": unverified,
        "order_ok": order_ok,
        "fsm_ok": fsm_ok,
        "level": level,
        "passed": passed,
        "missing": missing,
    }


def scan_session_text(text: str) -> Dict[str, Any]:
    return scan_lines(text.splitlines())


def scan_session_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return scan_lines(f)


def check_mcp_registration(mcp_json_path: str) -> Dict[str, Any]:
    """Verifies the swda-mcp server entry in an OMP mcp.json file."""
    reasons: List[str] = []
    server: Dict[str, Any] = {}
    try:
        with open(mcp_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return {"registered": False, "reasons": [f"unreadable mcp.json: {e}"], "server": server}
    servers = data.get("mcpServers", {})
    if not isinstance(servers, dict) or "swda-mcp" not in servers:
        return {"registered": False, "reasons": ["mcpServers.swda-mcp entry missing"], "server": server}
    server = servers["swda-mcp"]
    args = server.get("args", [])
    blob = " ".join(str(a) for a in args) if isinstance(args, list) else str(args)
    if "swda_mcp.server" not in blob:
        reasons.append("server args do not reference swda_mcp.server")
    env = server.get("env", {})
    if not isinstance(env, dict) or not env.get("SWDA_REPO"):
        reasons.append("env.SWDA_REPO missing (repo resolution falls back to file location)")
    if not isinstance(env, dict) or not env.get("PYTHONPATH"):
        reasons.append("env.PYTHONPATH missing")
    return {"registered": not reasons, "reasons": reasons, "server": server}


def check_contract_binding(contract_path: str, template_version: Optional[str] = None) -> Dict[str, Any]:
    """Verifies the integrated contract carries the delivery-gate binding."""
    reasons: List[str] = []
    try:
        with open(contract_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        return {"ok": False, "reasons": [f"unreadable contract: {e}"], "counts": {}}
    counts = {
        "begin": content.count(BEGIN_MARKER),
        "end": content.count(END_MARKER),
        "header": content.count(CONTRACT_HEADER),
    }
    if counts["begin"] != 1 or counts["end"] != 1:
        reasons.append(f"swda markers != 1/1 (begin={counts['begin']}, end={counts['end']}): stacked or missing contract")
    if counts["header"] != 1:
        reasons.append(f"contract header count != 1 ({counts['header']}): stacked or missing contract")
    if "swda_reconcile" not in content:
        reasons.append("delivery-gate binding missing (no swda_reconcile reference)")
    if "NEXT_STATE" not in content:
        reasons.append("FSM discipline missing (no NEXT_STATE reference)")
    if template_version:
        m = re.search(r"^version:\s*(.+)$", content, re.MULTILINE)
        found = m.group(1).strip().strip("\"'") if m else None
        if found != template_version:
            reasons.append(f"contract version {found!r} != template {template_version!r}")
    return {"ok": not reasons, "reasons": reasons, "counts": counts}
