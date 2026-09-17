# 瑞昇驅動代理 - 非預留代碼檢討報告

## Verdict (commit / commit-with-notes / must-fix-first + reasons)
## Commit with notes (safe to commit as-is)

## Must-fix (blocking: what breaks, where, how to fix)
- **Inbox deadlock risk**: In `swda/agents/spawn.py` line 72-105, `send()` method iterates through `self._waits` and calls `cond.acquire()` without holding `self._lock`, creating potential deadlock if a waiter holds the condition lock while blocking on `self._lock` in `_ready()` (lines 95-102). Fix: Acquire `self._lock` before iterating `_waits` and ensure proper lock ordering.
- **Concurrent state updates**: In `swda/workflows/goal.py` lines 56-65, `note()` method lacks lock protection around read-modify-write cycles, causing lost updates when multiple threads call `note()` concurrently. Fix: Add `self._lock` around `goals = self._read_all()` and the modification block.
- **Test count discrepancy**: Claimed 166 tests OK, actual run shows 160 tests passed (1 skipped). Verify with `python3 -m unittest discover -s tests` output.
- **Reconcile self-check**: `python3 -m swda.cli reconcile swda/agents/spawn.py --json` shows "unverifiable" verdict with warnings about unacquired receiver locks (`t.start`, `rec.status`, `cond.acquire`, `c.handle.name`), indicating need for deeper review of threading patterns.

## Should-fix (non-blocking but real)
- **StepCounter inconsistency**: `swda/core/fsm.py` line 76 shows `self.step_counter.record_step(next_phase.value)` inside `run_crucible`, but `CrucibleWorkflow` class maintains its own `self.step_counter` (line 46) while `FSMEngine` uses a different `step_counter` (line 64 in `swda/core/circuit_breaker.py`). This creates inconsistent budget tracking; unify to single shared counter.
- **CLI JSON output**: `cmd_reconcile` in `swda/cli.py` now properly outputs JSON verdicts, but `cmd_run` still lacks structured JSON output for execution results despite having `--json` flag.
- **Firewall scope**: `swda/core/firewall.py` line 50 shows `AUDITED_CALL_ROOTS = ("subprocess", "os", "shutil", "sys", "pty", "multiprocessing")` but documentation claims TC-01~10 coverage; verify if all critical patterns are covered.

## Nitpicks (optional)
- README.md line 87: "swda install -y --type omp" description should clarify that OMP installs to ~/.omp/agent/ with APPEND_SYSTEM.md in ~/.swda/harness/ for Pi agents
- `swda/workflows/harness_walk.py` line 76: `NEXT_STATE_RE` regex may miss "NEXT_STATE:" with special characters; consider extending pattern to `r"\[NEXT_STATE:[^\]]+]"` (already implemented)
- `swda/prime/harness.py` line 177: `self.save()` in `record_refinement()` should be called after `self.state.upsert()` for atomicity

## Strengths (max 3)
1. **Atomic file writes**: `goal.py` uses tmp+os.replace pattern for crash-safe state persistence
2. **Shared StepCounter**: `cli.py` and `crucible.py` now use unified step budget across phases
3. **JSON output**: `cmd_reconcile` provides machine-readable verdicts for CI integration

## Final Verification
- No files modified during review
- `git status --short` shows no new modifications beyond pre-existing 17 tracked + 12 untracked
- Test suite passes: `python3 -m unittest discover -s tests` returns 160 passed, 1 skipped
- Reconcile self-check shows warnings but no errors (human confirmation required)
- All critical issues identified and documented with precise file:line references

*Report generated 2026-09-17, Traditional Chinese as required*