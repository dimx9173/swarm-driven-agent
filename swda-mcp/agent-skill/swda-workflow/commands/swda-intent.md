---
description: SWDA intent gate - classify the request and lock the execution track
---

Run the SWDA INTENT_GATE for the request below. Classify it, lock the track, and
stop. Do not start research or write code in this step.

Request: $ARGUMENTS

Answer in this shape:

```xml
<INTENT_GATE_RESULT>
INTENT_CLASSIFICATION: [CASUAL_CHAT | QUICK_QUERY | FULL_REFACTOR | BUG_FIX | FEATURE_DEV | SECURITY_AUDIT | CONFIG_CHANGE | DEPENDENCY_UPDATE]
EXECUTION_TRACK: [FAST_PASS | LITE_MODE | SWARM_MODE]
RESOURCE_LOCK_REQUIRED: [True | False]
USE_SWARM_WORKFLOW: [True | False]
STRATEGY_TRACK: [the concrete path that will be taken]
</INTENT_GATE_RESULT>
```

Track rules: FAST_PASS answers directly, LITE_MODE skips to SYNTHESIS, and
SWARM_MODE runs the full FSM.
<!-- swda-workflow:v1 -->
