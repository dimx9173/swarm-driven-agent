#!/usr/bin/env python3
"""Static FSM reachability check over the integrated contract template.

Transition table is parsed from the contract itself — no builtin table:
  * Primary edges: fenced (```xml) `[NEXT_STATE: ...]` lines in
    template/integrated/ALL_IN_RULE.en.md. Source phase = enclosing XML
    root tag (TAG_PHASES); an unknown root tag is a loud-fail, not a guess.
  * Named prose edges (each tied to a verbatim anchor that must be present;
    anchor deleted/reworded => loud-fail, which is the point: the escape
    path must never silently vanish):
      LITE_MODE -> PHASE_5_SYNTHESIS      ("go directly to PHASE_5 SYNTHESIS")
      PHASE_7_REVIEW -> PHASE_6_IMPLEMENT (BLOCKER re-test sentence)
      PHASE_7_REVIEW -> HITL_SUSPEND       ("else HITL" in the same sentence)
      budget phases -> HITL_SUSPEND        (Circuit Breaker bullet)
      PHASE_5_SYNTHESIS -> ACTION_REALIZATION_BLOCK (pre-dispatch gate)

Checks:
  (a) every non-terminal node has >= 1 out-edge;
  (b) every node reachable from INTENT_GATE;
  (c) PHASE_7_REVIEW has a back-edge to IMPLEMENT or HITL (BLOCKER path).

Terminals: None (task done / gate blocked), FAST_PASS_EXIT (direct reply).
"""

import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONTRACT = os.path.join(REPO_ROOT, "template", "integrated", "ALL_IN_RULE.en.md")

# XML root tag -> source phase. Unknown tags fail loudly.
TAG_PHASES = {
    "INTENT_GATE_RESULT": "INTENT_GATE",
    "DESTRUCT_RESULT": "PHASE_1_DESTRUCT",
    "GATHER_RESULT": "PHASE_2_GATHER",
    "HYPERPLAN_RESULT": "PHASE_3_HYPERPLAN",
    "SYSTEM_SPECIFICATION": "PHASE_5_SYNTHESIS",
    "TASK_SUMMARY_REPORT": "PHASE_6_IMPLEMENT",
    "REVIEW_CONVERGENCE": "PHASE_7_REVIEW",
    "RETRO_CONVERGENCE": "PHASE_8_RETRO",
    "ACTION_REALIZATION_BLOCK": "PHASE_5_SYNTHESIS",
}

NEXT_RE = re.compile(r"^\s*\[NEXT_STATE:\s*([^\]]+)\]", re.MULTILINE)
TOKEN_RE = re.compile(r"^[A-Z][A-Z_0-9]*$")
# Terminal sinks: control leaves the machine (done / direct reply / human).
TERMINALS = {"None", "FAST_PASS_EXIT", "HITL_SUSPEND"}

# (anchor, source, targets): prose-derived edges; anchor must occur verbatim.
PROSE_EDGES = [
    ("go directly to PHASE_5 SYNTHESIS",
     "LITE_MODE", ["PHASE_5_SYNTHESIS"]),
    ("must be fixed and re-tested before advancing, else HITL",
     "PHASE_7_REVIEW", ["PHASE_6_IMPLEMENT", "HITL_SUSPEND"]),
    ("transition to `[NEXT_STATE: HITL_SUSPEND]`",
     "BUDGET", ["HITL_SUSPEND"]),  # BUDGET expands to all budget phases below
]
BUDGET_PHASES = ["INTENT_GATE", "PHASE_1_DESTRUCT", "PHASE_2_GATHER",
                 "PHASE_3_HYPERPLAN", "PHASE_6_IMPLEMENT"]


def parse_targets(raw):
    """Split 'A | B | tail note' into state tokens; None is the end sentinel."""
    targets = []
    for part in raw.split("|"):
        tok = part.strip().split()[0] if part.strip() else ""
        if tok == "None":
            targets.append("None")
        elif TOKEN_RE.match(tok or ""):
            targets.append(tok)
        # else: trailing note ("Zero-Chat Contract Active") — dropped
    if not targets:
        raise ValueError(f"NEXT_STATE line yielded no state tokens: {raw!r}")
    return targets


def build_graph(text):
    graph = {}  # src -> set(targets)

    def add(src, tgts):
        graph.setdefault(src, set()).update(tgts)

    # Primary edges from fenced xml blocks.
    lines, in_block, root = text.splitlines(), False, None
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if s == "```xml":
            if in_block:
                raise ValueError(f"line {i}: nested ```xml opener")
            in_block, root = True, None
        elif s == "```":
            if in_block:
                in_block, root = False, None
        elif in_block:
            m = re.match(r"<([A-Z][A-Z_0-9]*)>", s)
            if m and root is None:
                tag = m.group(1)
                if tag not in TAG_PHASES:
                    raise ValueError(f"line {i}: unknown XML root tag <{tag}>")
                root = tag
            m = re.match(r"^\s*\[NEXT_STATE:\s*([^\]]+)\]", line)
            if m:
                if root is None:
                    raise ValueError(f"line {i}: NEXT_STATE outside a tagged block")
                add(TAG_PHASES[root], parse_targets(m.group(1)))
    if in_block:
        raise ValueError("unclosed ```xml block at EOF")

    # Prose-anchored edges.
    for anchor, src, tgts in PROSE_EDGES:
        if anchor not in text:
            raise ValueError(f"prose anchor vanished (escape path at risk): {anchor!r}")
        if src == "BUDGET":
            for phase in BUDGET_PHASES:
                add(phase, tgts)
        else:
            add(src, tgts)
    return graph


def check(graph):
    errors = []
    nodes = set(graph) | {t for tgts in graph.values() for t in tgts}
    for node in sorted(nodes):
        if node not in TERMINALS and not graph.get(node):
            errors.append(f"dead end: {node} has no out-edge")
    # Reachability from INTENT_GATE.
    seen, stack = set(), ["INTENT_GATE"]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(graph.get(n, ()))
    for node in sorted(nodes):
        if node not in seen:
            errors.append(f"unreachable from INTENT_GATE: {node}")
    back = graph.get("PHASE_7_REVIEW", set())
    if not (back & {"PHASE_6_IMPLEMENT", "HITL_SUSPEND"}):
        errors.append("PHASE_7_REVIEW has no back-edge to IMPLEMENT/HITL (BLOCKER path cut)")
    return errors, nodes


def main(argv):
    _ = argv
    with open(CONTRACT, encoding="utf-8") as f:
        text = f.read()
    try:
        graph = build_graph(text)
    except ValueError as e:
        print(f"FSM-GRAPH-ERROR: {e}")
        return 1
    errors, nodes = check(graph)
    print(f"nodes ({len(nodes)}): {sorted(nodes)}")
    for src in sorted(graph):
        print(f"  {src} -> {sorted(graph[src])}")
    if errors:
        for e in errors:
            print(f"FSM-GRAPH-ERROR: {e}")
        return 1
    print("fsm graph: all phases reachable, no dead ends, BLOCKER path intact")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
