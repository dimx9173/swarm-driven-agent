# Swarm-Driven Agent (SWDA) Installer & Workflow

A universal, local-first installer and manager for **SWDA** (Swarm-Driven Agent) configurations and **SWDD** (Swarm-Driven Development) workflows. It simplifies scanning, version checking, upgrading, and creating Hermes and OpenClaw agents on your local machine.

---

## 🌟 Architecture & Nomenclature

To ensure consistent logic and governance, this project strictly distinguishes between the agent's runtime structure and its development methodology:

| Term | Context | File | Purpose |
| :--- | :--- | :--- | :--- |
| **SWDA** | Swarm-Driven Agent | [SOUL.md](template/modular/SOUL.md) | Streamlined entry point focusing strictly on **System Identity** (定位) and dual-core references. |
| **SWDA Contract** | System Contract | [RULE.md](template/modular/RULE.md) | Defines FSM transition hooks, attention anchors, memory decay, safety firewalls, and self-diagnosis. |
| **SWDD** | Swarm-Driven Development | [SKILL.md](template/modular/SKILL.md) | The supreme development meta-skill (methodology) describing parallel planning, Builder/Destroyer reviews, and sandbox execution. |

---

## 🚀 Key Features

* 🔒 **Local-first installer**: operates on your file system, merges FSM rules into agent profiles while preserving `# 1. 系統定位`, with timestamped backups and idempotent reinstalls.
* 🧠 **Swarm gates with proof**: FSM + Builder/Destroyer/Referee Crucible + tristate delivery gate (`valid`/`unverifiable`/`invalid`) + session scanner proving the harness was walked (`swda verify-session`).
* 📊 **Version tracking & status check**: semantic version parsing comparing installed files against templates (`Not Installed` / `Update Available` / `Up-to-date`); tracking file corrupt-loud with atomic writes.
* ➕ **Agent creation**: spin up new Hermes/OpenClaw/OMP/Pi agents from scratch with a single command.
* 🛡️ **Auto-backup system**: timestamped backups (e.g. `SOUL.md.20260624_150000.bak`) before editing any file.
* 🧩 **Prime-agent merges (stdlib, no daemon)**: admission-handle subagents, versioned harness store (local/global), compaction summaries, persistent goals — single process, host orchestrates, SWDA guards.
---

## 📂 Repository Layout

```
swarm-driven-agent/
├── installer.py     # CLI installer engine & helper functions
├── setup.py         # Installer packaging for the swda CLI command
├── swda/
│   ├── core/        # fsm, blackboard+RBAC handles, firewall allowlist, circuit breaker, hooks
│   ├── prime/       # rlm dispatcher, repl (+hooks), harness (versioned store, local/global)
│   ├── workflows/   # crucible, reconcile (tristate), harness_walk (session scanner),
│   │                 # tdd_runner (+sandbox), compact, goal
│   ├── agents/      # spawn (admission-handle subagents + inbox)
│   └── telemetry.py # mock/real split metrics
├── swda-mcp/        # thin MCP bridge (only non-stdlib package): 4 stateless tools
├── template/
│   ├── integrated/  # ALL_IN_RULE.{md,en.md} — single-file bundle (contract v14.4.0)
│   └── modular/     # SOUL/RULE/SKILL (+ .en) — script-installed bundle
├── docs/
│   ├── contracts/   # output-schema{,-modular}.md
│   ├── architecture/# circuit-breaker-spec, refactor plan/walkthrough
│   └── papers/      # life-harness notes
├── tests/           # 174 tests (unittest discover -s tests)
└── .gitignore
```

---

## 🎨 Architecture Visualizations

A curated gallery of the SWDD / SWDA cognitive architecture, rendered as standalone SVG diagrams (no external assets, fully scalable).

### 1. Swarm Architecture — Dual-Core Topology
The **SOUL** core at the center orchestrating six peripheral subagents (Alpha / Beta / Gamma / Builder / Destroyer / Mempalace). Concentric rotating rings symbolize the FSM state space; glowing dashed lines represent the data-flow contract between the soul and its swarm.

![Swarm Architecture](./images/01-swarm-architecture.svg)

### 2. The Crucible — Adversarial Spec Forge
A **Builder × Destroyer** arena where the specification document is hammered between the two perspectives. The autorubric score `S = Σ wᵢ · cᵢ` gates acceptance, with a hard **3-round circuit breaker** that escalates to HITL on failure.

![The Crucible](./images/02-crucible-battle.svg)

### 3. Finite State Machine — Hook Transition Flow
The complete **6-hook SOUL FSM** (`INTENT_GATE → DESTRUCT → GATHER → HYPERPLAN → SYNTHESIS → DYNAMIC_COMPILE`) with explicit loopbacks, continuation arc, and the 3-stage swarm execution.

![FSM Flow](./images/03-fsm-flow.svg)

### 4. Mempalace — Knowledge Palace
A 3D cathedral representing the **memory palace**: central dome (mempalace core) surrounded by floating **wing-orbs** (backend, decisions, meetings, anti-patterns, specs, prompts) connected via **tunnels**. Every drawer is a verbatim chunk of knowledge, retrievable via semantic search.

![Mempalace](./images/04-mempalace.svg)

### 5. Ebbinghaus Memory Decay — Retention Curve
The retention function `R(t) = P · F^c · e^(−λ·t)` plotted as a glowing decay curve, with the **GC threshold at R = 0.15** marked as a red dashed line. Beyond this, memory nodes are evicted from the active context and archived to the global read-only store.

![Ebbinghaus Decay](./images/05-ebbinghaus-decay.svg)

---

## 🛠️ 安裝與更新（Install & Update）

單一入口 `swda` 同時提供兩套功能：**Prime 執行引擎**（`run`/`reconcile`/`models`/`stats`/`scan`/`repl`/`refine`）與**安裝器**（`install`/`update`/`doctor`/`version`/`self-update`/`discover`/`learn`）。安裝器命令會自動轉交 `installer.main()`，行為與 `python3 installer.py …` 完全一致。

### 0. 安裝 `swda` 指令
在 repo 根目錄執行一次：
```bash
pip install -e .
# macOS 若被 externally-managed-environment 擋下：
pip install --break-system-packages -e .
```
裝好後 `swda` 全域可用。驗證：`swda version` 顯示 `3.0.0` 且 `[UP TO DATE]`。

> 雙入口對照：`swda <cmd>` ≡ `python3 installer.py <cmd>`（安裝器類）≡ `python3 -m swda.cli <cmd>`（兩類皆可）。

### 1. 首次安裝（install）
```bash
swda install                  # 互動式：掃描本機 agents，選號安裝
swda install -y --type all    # 全裝：hermes + openclaw + omp + pi + prime（缺目錄自動建）
swda install -y --type omp    # 只裝 OMP（~/.omp/agent/APPEND_SYSTEM.md）
swda install workspace        # 依名稱安裝（逗號分隔，不可有空格）
```
安裝時自動備份（`*.bak` 時間戳）、合併時保留你的 `# 1. 系統定位`，合約以 `<!-- swda-begin/end -->` 單份寫入（重裝冪等，不會堆疊）。
安裝成功的 agent 會登記到 `~/.swda/installed_agents.json`，之後 `doctor`/`update` 只看這份名單。

### 2. 健康檢查（doctor）
```bash
swda doctor            # 只檢查已登記 agents：Up-to-date / Update Available / Not Installed
swda doctor --fix -y   # 把已登記且過期的 agents 全部升級到模板版本
```
版本比對規則：modular（hermes/openclaw）比 `SOUL/RULE/SKILL` 三件；integrated（OMP/Pi 的 `APPEND_SYSTEM.md`）只比 `ALL_IN_RULE` 合約版本。

### 3. 更新 agents（update）
```bash
swda update -y                    # 全部已登記 agents 升級
swda update -y workspace          # 只升級指定名稱（位置參數，逗號分隔）
swda update -y --type omp         # 只升級指定類型
swda update -y openclaw:workspace # 精確匹配 type:name
```
注意：`swda update` **不等於** CLI 自升級，它只更新 agents 的合約文件。要升級 `swda` 工具本身，看下一節。

### 4. 自升級 CLI（self-update）
```bash
swda self-update    # = swda update --cli：git pull + pip install -e . 重裝
swda version        # 查本地 vs 遠端版本
```
`self-update` 需在有 git remote 的 repo 目錄執行；測試模式可用 `SWDA_TEST_MODE=1` 跳過真實 pull。

### 5. 新建 agent（--create）
```bash
swda install --create my_coder --type openclaw --identity "Python refactoring assistant." -y
swda install --create my_analyst --type hermes -y
swda install --create my_profile --type omp -y
```
落點：`--type` 省略預設 `openclaw`；`hermes` → `~/.hermes/profiles/<name>`；`openclaw` → `~/.openclaw/workspaces/<name>`；`omp`/`pi`/`prime` → `~/.omp|pi|prime/agent[/profiles/<name>]`（`default`/`agent` 直接用根目錄）。`--identity` 省略則用預設中文 identity。建完自動登記追蹤。

### 6. 解除安裝（uninstall）
```bash
swda install -u -y workspace        # 移除指定 agent 的合約，還原 System Identity，並取消登記
swda install -u -y all              # 移除全部已掃描 agents
```
解除安裝會備份原檔、剝掉 `swda-begin/end` 區塊（modular 另刪 `RULE.md`、`skills/swarm/SKILL.md`），只留你的 `# 1. 系統定位`。

### 7. 執行引擎常用指令（Prime）
```bash
swda scan                        # 唯讀掃描本機 agents（不寫檔、不看登記名單）
swda stats                       # telemetry 儀表板（.swda/metrics.jsonl 聚合，mock/real 分桶）
swda reconcile [--json] <file.py> # 交 gates：valid(0)/unverifiable(2)/invalid(1)，invalid 打回 Crucible
swda verify-session <session.jsonl> [--mcp-json ...] [--contract ...] [--strict]  # 證明某 OMP session 真走過 harness（--strict：unverified 即失敗）
swda run [--mock] [--json] "task desc"  # 走 GATHER→HYPERPLAN→CRUCIBLE→SYNTHESIS（真 LLM 需 .env；--json 给 CI）
swda models                      # 列出 gateway live model ids
python3 -m unittest discover -s tests  # 全套迴歸（目前 177 tests）
```

### 7c. 記憶 scope（local/global）
`ContinualHarness.scoped` 雙層：workspace `.swda/harness/`（local，預設）+ `~/.swda/harness/`（global，需 `scope="global"` 顯式寫入）。讀合併、local 優先；goal/telemetry 保持 workspace-local。

### 7b. OMP 接 swda-mcp（Delivery-Gate 工具）
`swda-mcp` 是獨立 thin MCP 包（`swda-mcp/`，唯一破零依賴處），暴露 4 個無狀態工具：
`swda_reconcile`（SYNTHESIS 交付門，mandatory）、`swda_firewall_audit`（optional）、
`swda_stats`、`swda_models`。`run`/`refine` 故意不暴露。
在 `~/.omp/agent/mcp.json` 註冊：
```json
"swda-mcp": {
  "command": "/Users/carlos/miniconda3/bin/python3",
  "args": ["-m", "swda_mcp.server"],
  "cwd": "/Users/carlos/pywork/swarm-driven-agent/swda-mcp",
  "env": {"PYTHONPATH": "/Users/carlos/pywork/swarm-driven-agent",
          "SWDA_REPO": "/Users/carlos/pywork/swarm-driven-agent"}
}
```
驗證：`swda verify-session <session.jsonl> --mcp-json ~/.omp/agent/mcp.json --contract ~/.omp/agent/APPEND_SYSTEM.md`

### 7d. prime-agent：裝合約 + 接 swda-mcp
installer 第五類：`swda install -y --type prime`（落點 `~/.prime/agent/APPEND_SYSTEM.md`，
`--create` 走 `profiles/<name>`）。skill wrapper 在 `swda-mcp/prime-skill/swda-skill/`
（`SKILL.md` + `pyproject.toml` + `src/swda/__init__.py` + `references/wiring.md`）：
拷到 `~/.prime/agent/skills/swda/` 後 `/reload`，kernel 內 `await swda.reconcile(file, root)`。
前置：啟動 prime-agent 前 `export SWDA_REPO` + `PYTHONPATH`（kernel MCP env 只吃 tagged reference）。

### 8. 常見問題
- `APPEND_SYSTEM.md` 異常變大（如破千行）→ 舊版堆疊殘留，重跑一次 `swda update -y` 即 dedup 為單份（~300 行）；見 `tests/test_effectiveness.py`。
- `swda run` 真 LLM 很慢 → 正常：1 輪 Crucible = builder/destroyer/referee 共 3 次 gateway call，最多 3 輪；先用 `--mock` 驗流程。

---

## 📄 License

This project is licensed under the MIT License.
