#!/usr/bin/env python3
"""
SWDA Coding A/B Benchmark Evaluator.

Measures the real coding pass-rate delta (Delta = SWDA - Baseline) by running
self-contained multi-file Python coding tasks in isolated temporary sandboxes
and grading them against hidden unit tests.

Usage:
  # Offline deterministic self-check (mock baseline vs. mock swda)
  python3 -m tests.benchmark.ab_eval --driver mock

  # Live A/B comparison using OMP or Pi CLI
  python3 -m tests.benchmark.ab_eval --driver omp --model <model_id> --report ab_report.md
  python3 -m tests.benchmark.ab_eval --driver pi --model <model_id> --report ab_report.md
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CODING_TASKS_FILE = os.path.join(ROOT_DIR, "tests", "benchmark", "coding_tasks.json")


# Reference solutions used ONLY by the deterministic offline mock driver
_MOCK_SOLUTIONS: dict[str, dict[str, str]] = {
    "HARD-01-LEDGER-ATOMIC": {
        "ledger.py": """import threading
from models import Receipt

class Ledger:
    def __init__(self, initial_balances: dict[str, int], storage):
        self._balances = dict(initial_balances)
        self._storage = storage
        self._receipts = {}
        self._lock = threading.Lock()

    def balance(self, account: str) -> int:
        with self._lock:
            return self._balances[account]

    def transfer(self, src: str, dst: str, amount: int, idempotency_key: str) -> Receipt:
        if amount <= 0 or src == dst:
            raise ValueError("Invalid transfer parameters")
        with self._lock:
            if idempotency_key in self._receipts:
                existing = self._receipts[idempotency_key]
                if (existing.src, existing.dst, existing.amount) == (src, dst, amount):
                    return existing
                raise ValueError("Idempotency key reused with different parameters")
            if src not in self._balances or dst not in self._balances:
                raise ValueError("Unknown account")
            if self._balances[src] < amount:
                raise ValueError("Insufficient funds")
            self._storage.commit_transfer(src, dst, amount, idempotency_key)
            self._balances[src] -= amount
            self._balances[dst] += amount
            receipt = Receipt(idempotency_key, src, dst, amount)
            self._receipts[idempotency_key] = receipt
            return receipt
""",
    },
    "HARD-02-DAG-SCHEDULER": {
        "graph.py": """class CycleError(Exception):
    pass

def validate_dag(deps: dict[str, list[str]]) -> None:
    for node, parents in deps.items():
        for p in parents:
            if p not in deps:
                raise ValueError(f"Unknown dependency: {p}")
    state = {}  # 0=unvisited, 1=visiting, 2=visited
    def dfs(u):
        state[u] = 1
        for p in deps.get(u, []):
            st = state.get(p, 0)
            if st == 1:
                raise CycleError(f"Cycle detected involving {u} -> {p}")
            if st == 0:
                dfs(p)
        state[u] = 2
    for node in deps:
        if state.get(node, 0) == 0:
            dfs(node)
""",
        "scheduler.py": """from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from graph import validate_dag

def run_dag(tasks: dict, deps: dict[str, list[str]], max_workers: int = 2) -> dict:
    full_deps = {tid: list(deps.get(tid, [])) for tid in tasks}
    validate_dag(full_deps)

    dependents = {tid: [] for tid in tasks}
    in_degree = {tid: len(full_deps[tid]) for tid in tasks}
    for tid, parents in full_deps.items():
        for p in parents:
            dependents[p].append(tid)

    results = {}
    failed_or_skipped = set()

    def mark_skipped(node):
        for child in dependents[node]:
            if child not in results:
                results[child] = {"status": "SKIPPED", "result": None, "error": None}
                failed_or_skipped.add(child)
                mark_skipped(child)

    ready = [tid for tid, deg in in_degree.items() if deg == 0]
    running = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while ready or running:
            while ready and len(running) < max_workers:
                tid = ready.pop(0)
                if tid in results:
                    continue
                fut = pool.submit(tasks[tid])
                running[fut] = tid
            if not running:
                break
            done, _ = wait(running.keys(), return_when=FIRST_COMPLETED)
            for fut in done:
                tid = running.pop(fut)
                try:
                    val = fut.result()
                    results[tid] = {"status": "COMPLETED", "result": val, "error": None}
                    for child in dependents[tid]:
                        in_degree[child] -= 1
                        if in_degree[child] == 0 and child not in failed_or_skipped:
                            ready.append(child)
                except Exception as exc:
                    results[tid] = {"status": "FAILED", "result": None, "error": str(exc)}
                    failed_or_skipped.add(tid)
                    mark_skipped(tid)
    return results
""",
    },
    "HARD-03-CIRCUIT-BREAKER": {
        "breaker.py": """import threading
import time
from state import BreakerState, CircuitOpenError

class CircuitBreaker:
    def __init__(self, failure_threshold=3, recovery_timeout=5.0,
                 failure_exceptions=(Exception,), clock=time.monotonic):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_exceptions = failure_exceptions
        self.clock = clock
        self.state = BreakerState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._half_open_in_flight = False
        self._lock = threading.Lock()

    def call(self, fn, *args, **kwargs):
        is_probe = False
        with self._lock:
            if self.state == BreakerState.OPEN:
                if self.clock() - self._opened_at < self.recovery_timeout:
                    raise CircuitOpenError("open")
                self.state = BreakerState.HALF_OPEN
                self._half_open_in_flight = True
                is_probe = True
            elif self.state == BreakerState.HALF_OPEN:
                if self._half_open_in_flight:
                    raise CircuitOpenError("half-open probe in flight")
                self._half_open_in_flight = True
                is_probe = True
        try:
            res = fn(*args, **kwargs)
        except self.failure_exceptions:
            with self._lock:
                if is_probe:
                    self._half_open_in_flight = False
                    self.state = BreakerState.OPEN
                    self._opened_at = self.clock()
                else:
                    self._failures += 1
                    if self._failures >= self.failure_threshold:
                        self.state = BreakerState.OPEN
                        self._opened_at = self.clock()
            raise
        except Exception:
            with self._lock:
                if is_probe:
                    self._half_open_in_flight = False
            raise
        else:
            with self._lock:
                if is_probe:
                    self._half_open_in_flight = False
                self.state = BreakerState.CLOSED
                self._failures = 0
            return res
""",
    },
    "HARD-04-TEMPLATE-SANDBOX": {
        "renderer.py": r"""import re

class SecurityError(Exception):
    pass

_FILTERS = {
    "upper": lambda s: str(s).upper(),
    "lower": lambda s: str(s).lower(),
    "strip": lambda s: str(s).strip(),
}

_PART_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?$")

def _resolve(expr: str, context: dict):
    parts = [p.strip() for p in expr.split("|")]
    path = parts[0]
    filters = parts[1:]

    segments = path.split(".")
    cur = context
    for idx, seg in enumerate(segments):
        m = _PART_RE.match(seg)
        if not m:
            raise KeyError(f"Invalid segment: {seg}")
        name, list_idx = m.group(1), m.group(2)
        if name.startswith("_"):
            raise SecurityError(f"Access to private/dunder attribute '{name}' is forbidden")
        if idx == 0:
            if name not in cur:
                raise KeyError(name)
            cur = cur[name]
        else:
            if isinstance(cur, dict):
                if name not in cur:
                    raise KeyError(name)
                cur = cur[name]
            else:
                if not hasattr(cur, name):
                    raise KeyError(name)
                cur = getattr(cur, name)
        if list_idx is not None:
            cur = cur[int(list_idx)]

    for flt in filters:
        if flt not in _FILTERS:
            raise KeyError(f"Unknown filter: {flt}")
        cur = _FILTERS[flt](cur)
    return str(cur)

def render(template: str, context: dict) -> str:
    placeholder = "__ESC_OPEN_BRACE__"
    safe_tpl = template.replace(r"\{{", placeholder)
    rendered = re.sub(r"\{\{(.*?)\}\}", lambda m: _resolve(m.group(1).strip(), context), safe_tpl)
    return rendered.replace(placeholder, "{{")
""",
    },
    "HARD-05-WAL-KV-RECOVERY": {
        "wal.py": """import json
import os
import zlib

class CorruptionError(Exception):
    pass

class WAL:
    def __init__(self, path: str):
        self.path = path

    def _encode(self, payload: dict) -> str:
        body = json.dumps(payload, sort_keys=True)
        crc = zlib.crc32(body.encode("utf-8")) & 0xFFFFFFFF
        return f"{crc:08x}:{body}\\n"

    def append(self, op: str, key: str, value=None) -> None:
        needs_nl = False
        if os.path.exists(self.path) and os.path.getsize(self.path) > 0:
            with open(self.path, "rb") as rf:
                rf.seek(-1, os.SEEK_END)
                needs_nl = rf.read(1) != b"\\n"
        with open(self.path, "a", encoding="utf-8") as f:
            if needs_nl:
                f.write("\\n")
            f.write(self._encode({"op": op, "key": key, "value": value}))
            f.flush()

    def rewrite_atomic(self, records: list[dict]) -> None:
        tmp = self.path + ".tmp-compact"
        with open(tmp, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(self._encode(rec))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def replay(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            raw_lines = [ln for ln in f.readlines() if ln.strip()]
        out = []
        last_idx = len(raw_lines) - 1
        for idx, line in enumerate(raw_lines):
            try:
                crc_hex, body = line.rstrip("\\n").split(":", 1)
                expected = int(crc_hex, 16)
                actual = zlib.crc32(body.encode("utf-8")) & 0xFFFFFFFF
                if actual != expected:
                    raise ValueError("CRC mismatch")
                out.append(json.loads(body))
            except Exception as exc:
                if idx == last_idx:
                    self.rewrite_atomic(out)
                    break
                raise CorruptionError(f"Corrupted WAL record at line {idx}") from exc
        return out
""",
        "kvstore.py": """from wal import WAL

class KVStore:
    def __init__(self, wal_path: str):
        self.wal = WAL(wal_path)
        self._data = {}
        for rec in self.wal.replay():
            if rec["op"] == "put":
                self._data[rec["key"]] = rec["value"]
            elif rec["op"] == "delete":
                self._data.pop(rec["key"], None)

    def put(self, key: str, value) -> None:
        self.wal.append("put", key, value)
        self._data[key] = value

    def delete(self, key: str) -> None:
        self.wal.append("delete", key)
        self._data.pop(key, None)

    def get(self, key: str):
        return self._data.get(key)

    def compact(self) -> None:
        live = [{"op": "put", "key": k, "value": v} for k, v in self._data.items()]
        self.wal.rewrite_atomic(live)
""",
    },
    "HARD-06-MVCC-SNAPSHOT": {
        "mvcc.py": """import threading

class ConflictError(Exception):
    pass

_DELETED = object()

class Transaction:
    def __init__(self, store, start_ver: int, snapshot: dict):
        self._store = store
        self._start_ver = start_ver
        self._snapshot = snapshot
        self._writes = {}
        self._closed = False

    def _ensure_open(self):
        if self._closed:
            raise RuntimeError("Transaction is already closed")

    def get(self, key: str):
        self._ensure_open()
        if key in self._writes:
            val = self._writes[key]
            return None if val is _DELETED else val
        return self._snapshot.get(key)

    def put(self, key: str, value) -> None:
        self._ensure_open()
        self._writes[key] = value

    def delete(self, key: str) -> None:
        self._ensure_open()
        self._writes[key] = _DELETED

    def commit(self) -> None:
        self._ensure_open()
        try:
            self._store._commit(self._start_ver, self._writes)
        finally:
            self._closed = True

    def rollback(self) -> None:
        self._closed = True

class MVCCStore:
    def __init__(self):
        self._data = {}
        self._version = 0
        self._key_versions = {}
        self._lock = threading.Lock()

    def begin(self) -> Transaction:
        with self._lock:
            return Transaction(self, self._version, dict(self._data))

    def _commit(self, start_ver: int, writes: dict) -> None:
        with self._lock:
            for k in writes:
                if self._key_versions.get(k, 0) > start_ver:
                    raise ConflictError(f"Write-write conflict on key '{k}'")
            self._version += 1
            for k, v in writes.items():
                if v is _DELETED:
                    self._data.pop(k, None)
                else:
                    self._data[k] = v
                self._key_versions[k] = self._version
""",
    },
    "HARD-07-CRON-POSIX": {
        "cron.py": """import calendar
from datetime import datetime, timedelta

def _parse_field(field: str, min_val: int, max_val: int, is_dow: bool = False) -> tuple[bool, set[int]]:
    if field == "*":
        vals = set(range(min_val, max_val + 1))
        if is_dow and 7 in vals:
            vals.add(0)
        return True, vals
    allowed = set()
    for part in field.split(","):
        if not part:
            raise ValueError(f"Empty cron part in '{field}'")
        if "/" in part:
            rng, step_s = part.split("/", 1)
            step = int(step_s)
            if step <= 0:
                raise ValueError("Step must be > 0")
        else:
            rng, step = part, 1
        if rng == "*":
            lo, hi = min_val, max_val
        elif "-" in rng:
            lo_s, hi_s = rng.split("-", 1)
            lo, hi = int(lo_s), int(hi_s)
        else:
            lo = hi = int(rng)
        if lo < min_val or hi > max_val or lo > hi:
            raise ValueError(f"Out of range '{part}' for [{min_val}, {max_val}]")
        for v in range(lo, hi + 1, step):
            allowed.add(0 if (is_dow and v == 7) else v)
    return False, allowed

def next_run(expr: str, after: datetime) -> datetime:
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError("Cron expression must have 5 fields")
    _, mins = _parse_field(parts[0], 0, 59)
    _, hours = _parse_field(parts[1], 0, 23)
    dom_star, doms = _parse_field(parts[2], 1, 31)
    _, months = _parse_field(parts[3], 1, 12)
    dow_star, dows = _parse_field(parts[4], 0, 7, is_dow=True)

    # Quick impossibility check for month/dom when dow is wildcard
    if dow_star:
        possible = any(
            d <= calendar.monthrange(y, m)[1]
            for m in months
            for d in doms
            for y in (2024, 2025)
        )
        if not possible:
            raise ValueError("Impossible month/day-of-month combination")

    cur = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit_year = after.year + 8
    while cur.year <= limit_year:
        if cur.month not in months:
            nxt_m = cur.month + 1
            nxt_y = cur.year + (1 if nxt_m > 12 else 0)
            nxt_m = 1 if nxt_m > 12 else nxt_m
            cur = cur.replace(year=nxt_y, month=nxt_m, day=1, hour=0, minute=0)
            continue
        # Python weekday(): Mon=0..Sun=6 -> cron Sun=0, Mon=1..Sat=6
        cron_dow = (cur.weekday() + 1) % 7
        if dom_star and dow_star:
            day_ok = True
        elif not dom_star and not dow_star:
            day_ok = (cur.day in doms) or (cron_dow in dows)
        elif not dom_star:
            day_ok = cur.day in doms
        else:
            day_ok = cron_dow in dows
        if not day_ok:
            cur = (cur + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        if cur.hour not in hours:
            cur = (cur + timedelta(hours=1)).replace(minute=0)
            continue
        if cur.minute not in mins:
            cur += timedelta(minutes=1)
            continue
        return cur
    raise ValueError("No matching cron time within search horizon")
""",
    },
    "HARD-08-ASYNC-SUPERVISOR": {
        "actor.py": """import asyncio

class MailboxFullError(Exception):
    pass

class ActorDeadError(Exception):
    pass

class _ActorState:
    def __init__(self, actor_id: str, handler, maxsize: int, max_restarts: int):
        self.actor_id = actor_id
        self.handler = handler
        self.queue = asyncio.Queue(maxsize=maxsize)
        self.max_restarts = max_restarts
        self.restarts = 0
        self.dead = False
        self.task = None

class ActorSystem:
    def __init__(self):
        self._actors: dict[str, _ActorState] = {}
        self._counter = 0

    def spawn(self, handler, maxsize: int = 4, max_restarts: int = 2) -> str:
        self._counter += 1
        aid = f"actor-{self._counter}"
        st = _ActorState(aid, handler, maxsize, max_restarts)
        self._actors[aid] = st
        st.task = asyncio.create_task(self._worker(st))
        return aid

    async def _worker(self, st: _ActorState):
        while not st.dead:
            msg, fut = await st.queue.get()
            try:
                res = await st.handler(msg)
                if fut is not None and not fut.done():
                    fut.set_result(res)
            except asyncio.CancelledError:
                if fut is not None and not fut.done():
                    fut.cancel()
                raise
            except Exception as exc:
                if fut is not None and not fut.done():
                    fut.set_exception(exc)
                if st.restarts < st.max_restarts:
                    st.restarts += 1
                    st.task = asyncio.create_task(self._worker(st))
                    return
                st.dead = True
                while not st.queue.empty():
                    _, pending_fut = st.queue.get_nowait()
                    if pending_fut is not None and not pending_fut.done():
                        pending_fut.set_exception(ActorDeadError("Actor exceeded max restarts"))
                break

    def tell(self, actor_id: str, msg) -> None:
        st = self._actors.get(actor_id)
        if st is None or st.dead:
            raise ActorDeadError(f"Actor {actor_id} is dead")
        try:
            st.queue.put_nowait((msg, None))
        except asyncio.QueueFull as exc:
            raise MailboxFullError(f"Actor {actor_id} mailbox full") from exc

    async def ask(self, actor_id: str, msg, timeout: float = 1.0):
        st = self._actors.get(actor_id)
        if st is None or st.dead:
            raise ActorDeadError(f"Actor {actor_id} is dead")
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        try:
            st.queue.put_nowait((msg, fut))
        except asyncio.QueueFull as exc:
            raise MailboxFullError(f"Actor {actor_id} mailbox full") from exc
        return await asyncio.wait_for(fut, timeout=timeout)

    async def shutdown(self) -> None:
        tasks = []
        for st in self._actors.values():
            st.dead = True
            if st.task is not None and not st.task.done():
                st.task.cancel()
                tasks.append(st.task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
""",
    },
    "LOGIC-01-SAT-CSP-SOLVER": {
        "sat.py": """def solve_sat(num_vars: int, clauses: list[list[int]]) -> dict[int, bool] | None:
    def simplify(cl_list, assign):
        while True:
            unit_lit = None
            new_clauses = []
            for c in cl_list:
                satisfied = False
                rem = []
                for lit in c:
                    v = abs(lit)
                    if v in assign:
                        if (lit > 0 and assign[v]) or (lit < 0 and not assign[v]):
                            satisfied = True
                            break
                    else:
                        rem.append(lit)
                if satisfied:
                    continue
                if not rem:
                    return None
                if len(rem) == 1:
                    unit_lit = rem[0]
                new_clauses.append(rem)
            if unit_lit is None:
                return new_clauses
            v = abs(unit_lit)
            val = unit_lit > 0
            if v in assign and assign[v] != val:
                return None
            assign[v] = val
            cl_list = new_clauses

    def dpll(cl_list, assign):
        cl_list = simplify(cl_list, assign)
        if cl_list is None:
            return None
        if not cl_list:
            for i in range(1, num_vars + 1):
                assign.setdefault(i, False)
            return assign
        shortest = min(cl_list, key=len)
        var = abs(shortest[0])
        for val in (True, False):
            nxt = dict(assign)
            nxt[var] = val
            res = dpll(cl_list, nxt)
            if res is not None:
                return res
        return None

    return dpll([list(c) for c in clauses], {})
""",
    },
    "SIM-01-HFT-MARKET-MAKER": {
        "strategy.py": """class MarketMaker:
    def quote(self, mid: float, fair_est: float, vol: float, inventory: int, max_inv: int, t: int, T: int) -> tuple[float, float, int, int]:
        inv_ratio = inventory / max(1, max_inv)
        reservation = fair_est - inv_ratio * vol * 1.6
        half_spread = max(0.03, vol * 0.95 + 0.03 * abs(inv_ratio))
        bid = round(reservation - half_spread, 4)
        ask = round(reservation + half_spread, 4)
        bid_size = max(0, min(8, int(round(5 * (1.0 - max(0.0, inv_ratio))))))
        ask_size = max(0, min(8, int(round(5 * (1.0 + min(0.0, inv_ratio))))))
        if inventory >= max_inv - 1:
            bid_size = 0
        if inventory <= -max_inv + 1:
            ask_size = 0
        return (bid, ask, bid_size, ask_size)
""",
    },
    "SIM-02-QUANT-PORTFOLIO-OPT": {
        "portfolio.py": """def optimize_weights(returns: list[list[float]], prev_weights: list[float], tc: float = 0.002, w_max: float = 0.35) -> list[float]:
    T = len(returns)
    N = len(returns[0])
    means = [sum(returns[t][i] for t in range(T)) / T for i in range(N)]
    vars_ = [sum((returns[t][i] - means[i]) ** 2 for t in range(T)) / max(1, T - 1) + 1e-6 for i in range(N)]
    # Inverse-variance + positive-Sharpe tilt with turnover damping and w_max cap
    raw = [max(0.0, (1.0 / vars_[i]) * max(0.1, 1.0 + 300.0 * means[i])) for i in range(N)]
    s = sum(raw) or 1.0
    target = [x / s for x in raw]
    # Blend with prev_weights to control turnover, then project onto [0, w_max], sum=1
    w = [0.7 * target[i] + 0.3 * prev_weights[i] for i in range(N)]
    for _ in range(25):
        w = [max(0.0, min(w_max, x)) for x in w]
        diff = (1.0 - sum(w)) / N
        if abs(diff) < 1e-9:
            break
        w = [max(0.0, min(w_max, x + diff)) for x in w]
    s = sum(w)
    return [x / s for x in w] if s > 0 else [1.0 / N] * N
""",
    },
    "SIM-03-DELIVERY-VRPTW": {
        "router.py": """import math

def plan_routes(orders: list[dict], vehicles: list[dict], depot: tuple[float, float]) -> dict[str, list[str]]:
    remaining = {o["id"]: o for o in orders}
    routes = {v["id"]: [] for v in vehicles}
    v_state = {v["id"]: {"x": depot[0], "y": depot[1], "t": 0.0, "load": 0.0, "cap": v["capacity"], "spd": v["speed"]} for v in vehicles}

    while remaining:
        best = None
        for vid, st in v_state.items():
            for oid, o in remaining.items():
                if st["load"] + o["weight"] > st["cap"] + 1e-9:
                    continue
                dist = math.hypot(o["x"] - st["x"], o["y"] - st["y"])
                arr = max(st["t"] + dist / st["spd"], o["ready"])
                if arr > o["due"] + 15.0:
                    continue
                late = max(0.0, arr - o["due"])
                net_gain = o["reward"] - dist - 5.0 * late - 0.2 * (arr - st["t"])
                if net_gain <= 0:
                    continue
                if best is None or net_gain > best[0]:
                    best = (net_gain, vid, oid, arr + o["service"])
        if best is None:
            break
        _, vid, oid, finish_t = best
        o = remaining.pop(oid)
        routes[vid].append(oid)
        st = v_state[vid]
        st["x"], st["y"], st["t"], st["load"] = o["x"], o["y"], finish_t, st["load"] + o["weight"]
    return routes
""",
    },
    "SIM-04-TRAFFIC-SIGNAL-OPT": {
        "traffic.py": """class TrafficController:
    def decide(self, queues: dict[str, int], current_phase: str, elapsed_in_phase: int, t: int) -> str:
        ns_q = queues["N"] + queues["S"]
        ew_q = queues["E"] + queues["W"]
        if elapsed_in_phase < 4:
            return current_phase
        cur_q = ns_q if current_phase == "NS" else ew_q
        other_q = ew_q if current_phase == "NS" else ns_q
        other_phase = "EW" if current_phase == "NS" else "NS"
        if cur_q == 0 and other_q > 0:
            return other_phase
        if other_q > cur_q + 6 or (elapsed_in_phase >= 12 and other_q > cur_q + 2):
            return other_phase
        return current_phase
""",
    },
    "SIM-05-COMPLEX-SEARCH-INDEX": {
        "search.py": r"""import math, re

class SearchEngine:
    def __init__(self):
        self.docs = {}
        self.doc_tokens = {}
        self.title_tokens = {}
        self.df = {}
        self.avgdl = 1.0
        self.vocab = set()

    @staticmethod
    def _tok(text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    @staticmethod
    def _edit1(a: str, b: str) -> bool:
        if abs(len(a) - len(b)) > 1:
            return False
        if a == b:
            return True
        if len(a) == len(b):
            return sum(x != y for x, y in zip(a, b)) == 1
        if len(a) > len(b):
            a, b = b, a
        i = j = diffs = 0
        while i < len(a) and j < len(b):
            if a[i] != b[j]:
                diffs += 1
                if diffs > 1:
                    return False
                j += 1
            else:
                i += 1; j += 1
        return True

    def index(self, docs: list[dict]) -> None:
        self.docs = {d["id"]: d for d in docs}
        self.doc_tokens = {}
        self.title_tokens = {}
        self.df = {}
        self.vocab = set()
        total_len = 0
        for d in docs:
            did = d["id"]
            tt = self._tok(d["title"])
            bt = self._tok(d["body"])
            all_t = tt + bt
            self.title_tokens[did] = tt
            self.doc_tokens[did] = all_t
            total_len += len(all_t)
            for w in set(all_t):
                self.df[w] = self.df.get(w, 0) + 1
                self.vocab.add(w)
        self.avgdl = total_len / max(1, len(docs))

    def _bm25(self, did: str, term: str) -> float:
        N = len(self.docs)
        all_t = self.doc_tokens[did]
        tf = all_t.count(term) + 2.0 * self.title_tokens[did].count(term)
        if tf == 0:
            return 0.0
        df = self.df.get(term, 1)
        idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
        k1, b = 1.5, 0.75
        dl = len(all_t)
        return idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / self.avgdl))

    def _match_term(self, term: str) -> dict[str, float]:
        exact = {did: self._bm25(did, term) for did in self.docs if self._bm25(did, term) > 0}
        if exact:
            return exact
        fuzzy = {}
        for v in self.vocab:
            if self._edit1(term, v):
                for did in self.docs:
                    s = self._bm25(did, v)
                    if s > 0:
                        fuzzy[did] = max(fuzzy.get(did, 0.0), s * 0.8)
        return fuzzy

    def _match_phrase(self, phrase: str) -> dict[str, float]:
        p = phrase.lower()
        out = {}
        for did, d in self.docs.items():
            in_t = p in d["title"].lower()
            in_b = p in d["body"].lower()
            if in_t or in_b:
                out[did] = (2.0 if in_t else 0.0) + (1.0 if in_b else 0.0)
        return out

    def search(self, query: str, k: int = 10) -> list[str]:
        tokens = re.findall(r'"[^"]+"|\(|\)|AND|OR|NOT|[a-zA-Z0-9_]+', query)
        pos = [0]
        all_ids = set(self.docs.keys())

        def parse_or():
            left = parse_and()
            while pos[0] < len(tokens) and tokens[pos[0]] == "OR":
                pos[0] += 1
                right = parse_and()
                for did, sc in right.items():
                    left[did] = left.get(did, 0.0) + sc
            return left

        def parse_and():
            left = parse_not()
            while pos[0] < len(tokens) and (tokens[pos[0]] == "AND" or (tokens[pos[0]] not in ("OR", ")"))):
                if tokens[pos[0]] == "AND":
                    pos[0] += 1
                right = parse_not()
                left = {did: left[did] + right[did] for did in left if did in right}
            return left

        def parse_not():
            if pos[0] < len(tokens) and tokens[pos[0]] == "NOT":
                pos[0] += 1
                sub = parse_atom()
                return {did: 0.1 for did in all_ids if did not in sub}
            return parse_atom()

        def parse_atom():
            tok = tokens[pos[0]]
            pos[0] += 1
            if tok == "(":
                res = parse_or()
                if pos[0] < len(tokens) and tokens[pos[0]] == ")":
                    pos[0] += 1
                return res
            if tok.startswith('"') and tok.endswith('"'):
                return self._match_phrase(tok[1:-1])
            return self._match_term(tok.lower())

        if not tokens:
            return []
        scores = parse_or()
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return [did for did, _ in ranked[:k]]
""",
    },
}


def run_scored_sim(workdir: str, eval_script: str, timeout: int = 30) -> tuple[bool, float, str, dict]:
    """Executes a continuous-score simulation script and parses JSON {score, passed, metrics}."""
    sim_path = os.path.join(workdir, "_hidden_sim_eval.py")
    with open(sim_path, "w", encoding="utf-8") as f:
        f.write(eval_script)
    try:
        res = subprocess.run(
            [sys.executable, sim_path],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        raw = (res.stdout or "").strip()
        if res.returncode != 0 or not raw:
            return False, 0.0, (res.stdout + "\n" + res.stderr).strip(), {}
        last_line = raw.splitlines()[-1]
        data = json.loads(last_line)
        score = float(data.get("score", 0.0))
        passed = bool(data.get("passed", score >= 60.0))
        return passed, round(score, 2), raw, data.get("metrics", {})
    except subprocess.TimeoutExpired:
        return False, 0.0, "Simulation timed out", {}
    except Exception as exc:
        return False, 0.0, f"Simulation parse error: {exc}", {}


def run_hidden_tests(workdir: str, test_code: str, timeout: int = 30) -> tuple[bool, str]:
    """Writes hidden unit tests into workdir and executes them with unittest."""
    test_path = os.path.join(workdir, "_hidden_eval_test.py")
    with open(test_path, "w", encoding="utf-8") as f:
        f.write(test_code)
    try:
        res = subprocess.run(
            [sys.executable, "-m", "unittest", "_hidden_eval_test.py"],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        passed = res.returncode == 0
        output = (res.stdout + "\n" + res.stderr).strip()
        return passed, output
    except subprocess.TimeoutExpired:
        return False, "Hidden test execution timed out"


def _run_mock_driver(task: dict, workdir: str, mode: str) -> None:
    """Deterministic mock solver: baseline solves 1st task only; swda solves all."""
    task_id = task["id"]
    if mode == "swda" or task_id == "HARD-01-LEDGER-ATOMIC":
        files = _MOCK_SOLUTIONS.get(task_id, {})
        for rel_path, content in files.items():
            full_path = os.path.join(workdir, rel_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)


def _run_cli_driver(driver: str, prompt: str, workdir: str, mode: str,
                    model: str = None, timeout: int = 120) -> str:
    """Executes `omp` or `pi` CLI inside the isolated task sandbox."""
    if driver == "omp":
        bin_path = shutil.which("omp") or "/Users/carlos/.bun/bin/omp"
    elif driver == "pi":
        bin_path = shutil.which("pi")
    else:
        raise ValueError(f"Unsupported driver: {driver}")

    if not bin_path or not os.path.exists(bin_path):
        raise FileNotFoundError(f"CLI binary for driver '{driver}' not found on PATH")

    cmd = [bin_path, "--no-session", "-p", prompt]
    if model:
        cmd.extend(["--model", model])
    if mode == "baseline":
        # Override system prompt so SWDA rules are not injected in baseline mode
        cmd.extend(["--system-prompt", "You are a concise, accurate Python software engineer. Edit files directly to solve the task."])
        if driver == "omp":
            cmd.extend(["--append-system-prompt", ""])
    else:
        # In single-turn non-interactive benchmark mode, prevent Socratic Grilling from halting for user input
        if driver == "omp":
            cmd.extend(["--append-system-prompt", "\n\n[BENCHMARK_MODE]: Non-interactive single-turn execution. Do NOT ask clarifying questions or pause for HITL; resolve minor ambiguities autonomously and write the final code edits before exiting."])

    try:
        res = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=timeout)
        return (res.stdout or "") + (res.stderr or "")
    except subprocess.TimeoutExpired:
        return "TIMEOUT"


class ABBenchmarkRunner:
    def __init__(self, tasks_file: str = DEFAULT_CODING_TASKS_FILE,
                 driver: str = "mock", model: str = None, timeout: int = 120,
                 runs: int = 1, log_dir: str = None):
        self.tasks_file = tasks_file
        self.driver = driver
        self.model = model
        self.timeout = timeout
        self.runs = max(1, int(runs))
        self.log_dir = log_dir
        if self.log_dir:
            os.makedirs(self.log_dir, exist_ok=True)
        with open(tasks_file, "r", encoding="utf-8") as f:
            self.suite = json.load(f)

    def verify_starter_fails(self, task: dict) -> bool:
        """Sanity-checks that starter_files FAIL unit tests or score < 60 on scored_sim."""
        with tempfile.TemporaryDirectory(prefix="swda_red_") as tmpdir:
            for rel_path, content in task["starter_files"].items():
                full_path = os.path.join(tmpdir, rel_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
            if task.get("type") == "scored_sim":
                passed, score, _, _ = run_scored_sim(tmpdir, task["eval_script"])
                return (not passed) and score < 60.0
            passed, _ = run_hidden_tests(tmpdir, task["test_code"])
            return not passed

    def run_single_task(self, task: dict, mode: str) -> dict:
        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix=f"swda_{mode}_") as tmpdir:
            for rel_path, content in task["starter_files"].items():
                full_path = os.path.join(tmpdir, rel_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)

            cli_out = ""
            if self.driver == "mock":
                _run_mock_driver(task, tmpdir, mode)
            else:
                cli_out = _run_cli_driver(
                    driver=self.driver,
                    prompt=task["prompt"],
                    workdir=tmpdir,
                    mode=mode,
                    model=self.model,
                    timeout=self.timeout,
                )

            if task.get("type") == "scored_sim":
                passed, score, test_out, metrics = run_scored_sim(tmpdir, task["eval_script"])
            else:
                passed, test_out = run_hidden_tests(tmpdir, task["test_code"])
                score = 100.0 if passed else 0.0
                metrics = {}
        elapsed = round(time.monotonic() - start, 2)
        if not passed and self.log_dir:
            log_path = os.path.join(self.log_dir, f"{task['id']}_{mode}_{int(time.time())}.log")
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write(f"TASK={task['id']} MODE={mode} ELAPSED={elapsed}s SCORE={score}\n")
                lf.write(f"--- CLI_OUT_TAIL ---\n{cli_out[-2000:]}\n")
                lf.write(f"--- TEST_OUT ---\n{test_out[-2000:]}\n")
        return {
            "task_id": task["id"],
            "type": task.get("type", "unit_test"),
            "domain": task.get("domain", "general"),
            "difficulty": task.get("difficulty", "unknown"),
            "mode": mode,
            "passed": passed,
            "score": score,
            "metrics": metrics,
            "elapsed_sec": elapsed,
            "test_output": test_out,
        }

    def run_task_aggregated(self, task: dict, mode: str) -> dict:
        """Runs self.runs trials and aggregates mean score and Pass@k."""
        if self.runs <= 1:
            return self.run_single_task(task, mode)
        trials = [self.run_single_task(task, mode) for _ in range(self.runs)]
        mean_score = round(sum(t["score"] for t in trials) / len(trials), 2)
        any_passed = any(t["passed"] for t in trials)
        pass_count = sum(1 for t in trials if t["passed"])
        avg_elapsed = round(sum(t["elapsed_sec"] for t in trials) / len(trials), 2)
        return {
            "task_id": task["id"],
            "type": task.get("type", "unit_test"),
            "domain": task.get("domain", "general"),
            "difficulty": task.get("difficulty", "unknown"),
            "mode": mode,
            "passed": any_passed,
            "pass_count": pass_count,
            "runs": self.runs,
            "score": mean_score,
            "metrics": {"pass_at_k": any_passed, "trial_passes": f"{pass_count}/{self.runs}"},
            "elapsed_sec": avg_elapsed,
            "test_output": trials[-1]["test_output"],
        }

    def run_single_mode(self, mode: str) -> dict:
        tasks = self.suite.get("tasks", [])
        results = [self.run_task_aggregated(task, mode=mode) for task in tasks]
        n = len(tasks)
        passed = sum(1 for r in results if r["passed"])
        pct = round((passed / n) * 100.0, 1) if n else 0.0
        avg_score = round(sum(r["score"] for r in results) / n, 2) if n else 0.0
        return {
            "suite": self.suite.get("benchmark_suite", "SWDA-Coding-AB"),
            "driver": self.driver,
            "model": self.model or "default",
            "mode": mode,
            "total_tasks": n,
            "passed": passed,
            "pass_rate_pct": pct,
            "avg_score": avg_score,
            "results": results,
        }

    def generate_single_mode_report(self, data: dict) -> str:
        md = [
            f"# SWDA Coding Benchmark Report ({data['mode'].upper()} Only)",
            f"**Suite**: `{data['suite']}` | **Driver**: `{data['driver']}` | **Model**: `{data['model']}`",
            f"**Avg Score (0-100)**: `{data['avg_score']}` | **Pass Rate (>=60 pts)**: `{data['pass_rate_pct']}%` ({data['passed']}/{data['total_tasks']})\n",
            "| Task ID | Domain | Type | Score | Status | Time (s) |",
            "| :--- | :--- | :---: | :---: | :---: | :---: |",
        ]
        for r in data["results"]:
            st = "PASS" if r["passed"] else "FAIL"
            md.append(f"| `{r['task_id']}` | `{r['domain']}` | `{r['type']}` | **{r['score']:.1f}** | **{st}** | {r['elapsed_sec']} |")
        return "\n".join(md)

    def run_ab_comparison(self) -> dict:
        tasks = self.suite.get("tasks", [])
        baseline_results = []
        swda_results = []

        for task in tasks:
            baseline_results.append(self.run_task_aggregated(task, mode="baseline"))
            swda_results.append(self.run_task_aggregated(task, mode="swda"))

        n = len(tasks)
        base_pass = sum(1 for r in baseline_results if r["passed"])
        swda_pass = sum(1 for r in swda_results if r["passed"])
        base_pct = round((base_pass / n) * 100.0, 1) if n else 0.0
        swda_pct = round((swda_pass / n) * 100.0, 1) if n else 0.0
        delta_pct = round(swda_pct - base_pct, 1)
        base_avg_score = round(sum(r["score"] for r in baseline_results) / n, 2) if n else 0.0
        swda_avg_score = round(sum(r["score"] for r in swda_results) / n, 2) if n else 0.0
        delta_score = round(swda_avg_score - base_avg_score, 2)

        return {
            "suite": self.suite.get("benchmark_suite", "SWDA-Coding-AB"),
            "driver": self.driver,
            "model": self.model or "default",
            "total_tasks": n,
            "baseline_passed": base_pass,
            "baseline_pass_rate_pct": base_pct,
            "swda_passed": swda_pass,
            "swda_pass_rate_pct": swda_pct,
            "delta_pass_rate_pct": delta_pct,
            "baseline_avg_score": base_avg_score,
            "swda_avg_score": swda_avg_score,
            "delta_avg_score": delta_score,
            "baseline_results": baseline_results,
            "swda_results": swda_results,
        }

    def generate_markdown_report(self, data: dict) -> str:
        sign_p = "+" if data["delta_pass_rate_pct"] >= 0 else ""
        sign_s = "+" if data["delta_avg_score"] >= 0 else ""
        md = [
            f"# SWDA Coding A/B Benchmark Report",
            f"**Suite**: `{data['suite']}` | **Driver**: `{data['driver']}` | **Model**: `{data['model']}`",
            f"**Avg Score (0-100)**: Baseline `{data['baseline_avg_score']}` vs SWDA `{data['swda_avg_score']}` (**Delta: `{sign_s}{data['delta_avg_score']} pts`**)",
            f"**Pass Rate (>=60 pts)**: Baseline `{data['baseline_pass_rate_pct']}%` ({data['baseline_passed']}/{data['total_tasks']}) | "
            f"SWDA `{data['swda_pass_rate_pct']}%` ({data['swda_passed']}/{data['total_tasks']}) | "
            f"**Delta: `{sign_p}{data['delta_pass_rate_pct']}%`**\n",
            "| Task ID | Domain | Type | Baseline | SWDA | Score Gain | Base (s) | SWDA (s) |",
            "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
        for b, s in zip(data["baseline_results"], data["swda_results"]):
            b_tag = f"{b['score']:.1f} ({'PASS' if b['passed'] else 'FAIL'})"
            s_tag = f"{s['score']:.1f} ({'PASS' if s['passed'] else 'FAIL'})"
            diff = round(s["score"] - b["score"], 1)
            gain = f"+{diff}" if diff > 0 else f"{diff}"
            md.append(
                f"| `{b['task_id']}` | `{b['domain']}` | `{b['type']}` | **{b_tag}** | **{s_tag}** | `{gain}` | {b['elapsed_sec']} | {s['elapsed_sec']} |"
            )
        return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="SWDA Coding A/B Benchmark Evaluator")
    parser.add_argument("--tasks", default=DEFAULT_CODING_TASKS_FILE, help="Path to coding_tasks.json")
    parser.add_argument("--driver", choices=["mock", "omp", "pi"], default="mock", help="Execution driver")
    parser.add_argument("--mode", choices=["ab", "baseline", "swda"], default="ab", help="Run A/B comparison or a single mode")
    parser.add_argument("--model", default=None, help="Target model ID (passed to --model)")
    parser.add_argument("--timeout", type=int, default=120, help="Per-task timeout in seconds")
    parser.add_argument("--runs", type=int, default=1, help="Number of trials per task (Pass@k & mean score)")
    parser.add_argument("--log-dir", default=None, help="Directory to save failure/timeout trace logs")
    parser.add_argument("--report", default=None, help="Optional output path for Markdown report")
    args = parser.parse_args()

    runner = ABBenchmarkRunner(
        tasks_file=args.tasks,
        driver=args.driver,
        model=args.model,
        timeout=args.timeout,
        runs=args.runs,
        log_dir=args.log_dir,
    )
    if args.mode == "ab":
        data = runner.run_ab_comparison()
        report_md = runner.generate_markdown_report(data)
    else:
        data = runner.run_single_mode(args.mode)
        report_md = runner.generate_single_mode_report(data)
    print(report_md)

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"\nReport saved to: {args.report}")


if __name__ == "__main__":
    main()
