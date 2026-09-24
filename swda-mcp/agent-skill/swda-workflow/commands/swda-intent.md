---
description: SWDA intent gate - classify the request and lock the execution track
---

Run the SWDA INTENT_GATE for the request below. Classify it, lock the track, and
resolve `AUTO_ADVANCE`. When `AUTO_ADVANCE=True` (the default for SWARM_MODE and
LITE_MODE), do not stop after this step: emit the phase blocks back-to-back in
the same turn until a stop condition is hit (ACTION_REALIZATION_BLOCK,
HITL_SUSPEND, TASK_SUMMARY_REPORT, or FAST_PASS). Stop after this step only when
`AUTO_ADVANCE=False` (user asked to go one step at a time).

Request: $ARGUMENTS

Answer in this shape:

```xml
<INTENT_GATE_RESULT>
INTENT_CLASSIFICATION: [CASUAL_CHAT | QUICK_QUERY | FULL_REFACTOR | BUG_FIX | FEATURE_DEV | SECURITY_AUDIT | CONFIG_CHANGE | DEPENDENCY_UPDATE]
EXECUTION_TRACK: [FAST_PASS | LITE_MODE | SWARM_MODE]
RESOURCE_LOCK_REQUIRED: [True | False]
USE_SWARM_WORKFLOW: [True | False]
AUTO_ADVANCE: [True | False]
</INTENT_GATE_RESULT>
```

Track rules: FAST_PASS answers directly, LITE_MODE skips to SYNTHESIS, and
SWARM_MODE runs the full FSM. `AUTO_ADVANCE=True` means the whole path runs in one
turn; `False` means one phase block per turn.

Optional hint: run `swda jev-intent "$ARGUMENTS"`. It prints a classification
string, `unsure`, or `none` (no Jev key configured). Treat the output as a
hint only; `none` or `unsure` means classify with your own judgment as above.
<!-- swda-workflow:v1 -->
