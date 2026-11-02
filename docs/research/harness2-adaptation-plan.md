# SWDA 改造路線圖：借鏡 Google Research Harness² (arXiv:2610.14224)

> **文件目的**：基於 Google Research `Harness²: Recursive Agent Harnessing for an Open World` 論文與開源框架（`google-research/harness2`）分析，將其「雙層遞歸（Task-Level & Harnessing-Level Recursion）」、「元件成本階梯（Component Cost Hierarchy）」與「迴圈內強制控制（Tool-Loop Hooks）」映射到 SWDA 既有雙模態架構（Prime-SWDA Runtime + SWDD 契約模板）。
> **產出日**：2026-11-02
> **參考來源**：`https://github.com/google-research/harness2` (`arXiv:2610.14224`)
> **狀態**：已裁決（選項 A：全量分軌落地，同步更新 modular 與 integrated）

---

## 0. 架構同構性與缺口診斷 (Gap Analysis)

`SWDA` 與 `Harness²` 共享同一核心命題——**「凍結底層模型權重，透過進化外圍 Harness 提升模型在開放世界工程任務的表現」**：

| 維度 | Harness² 核心機制 | SWDA 既有元件 | 缺口與升級目標 |
|---|---|---|---|
| **元件表面積與成本階梯** | 8 大元件；強制 **Script / Hook / Skill (按需) > Subagent (隔離) > Always-on Prose (最貴)** | `swda/prime/harness.py` (`KINDS = prompt, memory, skill, subagent`) | 擴充 `script` 與 `hook`；實作 `select_cheapest_lever()` 避免把所有反模式塞入常駐 `memory`。 |
| **迴圈內強制與降噪** | `PostToolUse` Hook 支援 `block`、Output Trimming（修剪過長輸出）、Targeted Error Hint（重複錯誤附加提示） | `swda/core/hooks.py` (`run_post` 僅旁觀，忽略回傳值) | 升級 `run_post()` 支援修剪 stdout/stderr、附加 `hint` 與 `block` 回饋；提供預設 Trimmer 與 Reconcile 鉤子。 |
| **表面積與契約驗證** | 3 條鐵律：**Skill Trigger Line**、**Script 實體存在與防路徑逃逸**、**Grader Verdict 零洩漏** | `swda/workflows/harness_walk.py` | 於 `ContinualHarness` 新增 `validate_surface()`，攔截無觸發行的死技能（Dead Skills）、孤兒腳本與評判標準洩漏。 |
| **任務層對比與防過度工程** | **INV/DOM 雙軸提議** + **匿名洗牌選優 (`selection.py`)** + **`KEEP_BASE`（保留原狀）** | `swda/workflows/crucible.py` | 區分 `INV`（通用工程）與 `DOM`（領域規格）批評；支援匿名洗牌對比（`assign_anon_candidates`）與 `KEEP_BASE` 裁決，保護 Deliverable Shape。 |
| **進化層經驗庫結構** | 按 Domain 分桶 + `INDEX.md` 輕量觸發索引 + 強制 `(cue, lesson, evidence)` 三元組 | `ContinualHarness` 扁平 YAML + `SKILL.md` PHASE 8 RETRO | 強制檢驗 `(cue, lesson, evidence)` 三元組、自動維護輕量級 `INDEX.md`，並同步更新 `RULE.md` / `SKILL.md` / `ALL_IN_RULE.md`。 |

---

## 1. 總修改清單（分軌隔離）

遵循 `AGENTS.md` §4 **邊界隔離鐵律**與 `RULE.md` §2.3 **極簡鐵律（零新增第三方依賴，純標準庫實作）**：

| ID | 優先級 | 軌道 | 目標檔案 | 核心內容 |
|---|---|---|---|---|
| **P1-A** | P1 | Track 1 (Runtime) | `swda/prime/harness.py`, `tests/test_prime_integrate.py` | 擴充 `KINDS` (`script`, `hook`)、成本感知路由 `select_cheapest_lever`、`(cue, lesson, evidence)` 驗證、`INDEX.md` 生成與 `validate_surface` |
| **P1-B** | P1 | Track 1 (Runtime) | `swda/core/hooks.py`, `swda/prime/repl.py`, `swda/workflows/tdd_runner.py`, `tests/test_hooks.py` | `run_post()` 支援 `trimmed_stdout`、`hint`、`decision: block`；新增 `make_output_trimmer_hook` 與 `make_post_write_reconcile_hook` |
| **P2-A** | P2 | Track 1 (Runtime) | `swda/workflows/crucible.py`, `tests/test_workflows.py` | `INV`/`DOM` 維度標記、`assign_anon_candidates` 確定性匿名洗牌、`KEEP_BASE` 與 Deliverable Shape 保護 |
| **P1-C** | P1 | Track 2 (Contract) | `template/modular/RULE.md` (+ `.en.md`), `template/integrated/ALL_IN_RULE.md` (+ `.en.md`) | §3 新增「Harness 元件成本階梯 (Component Cost Hierarchy)」與「Skill Trigger Line 鐵律」 |
| **P2-B** | P2 | Track 2 (Contract) | `template/modular/SKILL.md` (+ `.en.md`), `docs/contracts/output-schema*.md`, `tests/test_swda_rules.py` | PHASE 3 納入 Deliverable Shape 與 `KEEP_BASE` 防過度工程原則；PHASE 8 RETRO 對齊 `(CUE, EVIDENCE, LESSON, TARGET_COMPONENT)` 結構 |

---

## 2. 驗證標準 (Goal-Driven Verification)

1. **Runtime 測試覆蓋**：
   - `pytest tests/test_prime_integrate.py tests/test_hooks.py tests/test_workflows.py` 100% 通過。
2. **Contract 與中英結構對齊**：
   - `python3 tools/check_zh_en_parity.py` 通過（0 Drift）。
   - `python3 tools/check_fsm_graph.py` 通過（12 節點全連通）。
   - `python3 tools/stamp_versions.py --check` 通過。
   - `pytest tests/test_swda_rules.py` 100% 通過。
