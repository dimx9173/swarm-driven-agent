# Host Circuit Breaker & Step Budget Specification

---

## 1. 概述 (Overview)

本文件定義物理宿主 (Host Client / Agent Runner，如 OpenClaw, ACP, Python Driver) 與 SWDA Prompt 狀態機之間的 **物理硬熔斷協議 (Host Circuit Breaker Protocol)**。

為防範 LLM 在複雜推理任務中發生過度思考 (Overthinking) 或無限死循環 (Thinking Loops)，物理宿主必須主動記錄對話輪數與 FSM 狀態轉移次數，並於達到預算上限時強制進行手握與熔斷。

---

## 2. 分階段步驟預算與熔斷矩陣 (Phase Budget Matrix)

物理宿主必須監控 Agent 產出的 `<INTENT_GATE_RESULT>`、`<DESTRUCT_RESULT>`、`<GATHER_RESULT>`、`<HYPERPLAN_RESULT>` 與 `<TASK_SUMMARY_REPORT>`，並維護目前 FSM 階段與 Step Counter：

| FSM 階段 (FSM Phase) | 最大步驟預算 (Max Step Limit) | 超限監控觸發條件 | 宿主處置與降級機制 (Host Action) |
| :--- | :--- | :--- | :--- |
| **INTENT_GATE** | **1 步** | INTENT_GATE 階段產生次數 $> 1$ | 物理強制將 `EXECUTION_TRACK` 設為 `FAST_PASS` 或提請人類決策。 |
| **PHASE_1 & PHASE_2 (GATHER)** | **3 步** | GATHER 階段連續輸出 $\ge 3$ 次 | 強制發送指令注入：`"GATHER Step budget (3) reached. Proceed to PHASE_3 immediately using existing context."` |
| **PHASE_3 (HYPERPLAN)** | **5 輪** | Builder 與 Destroyer 對抗迴圈 $\ge 5$ 輪 | 強制判定對抗結束，要求 Referee 取當前分數最高之方案輸出，轉移至 `PHASE_4`。 |
| **PHASE_DYNAMIC_COMPILE** | **5 次修復** | TDD/實體測試失敗重試 $\ge 5$ 次 | 物理觸發 `git reset --hard` 回滾代碼變更，並要求 Agent 輸出 `<BUDGET_EXHAUSTION_REPORT>`。 |

---

## 3. 手握協議 (Handshake Protocol)

### 3.1 LLM 主動降級手握
當 LLM 自行偵測到無法收斂或預算耗盡時，會輸出：

```xml
<BUDGET_EXHAUSTION_REPORT>
EXHAUSTED_PHASE: HYPERPLAN
STEP_COUNT_REACHED: 5
REASON: Builder and Destroyer reached deadlock on database transaction isolation levels.
CURRENT_BEST_PROPOSAL: Optimistic locking with version timestamp.
REMAINING_RISKS: High concurrency write conflict under extreme load.
HITL_DIRECTIVE: Select between (A) Optimistic Locking or (B) Pessimistic Locking with performance penalty.
</BUDGET_EXHAUSTION_REPORT>
[NEXT_STATE: HITL_SUSPEND | Budget Exhausted]
```

物理宿主收到 `[NEXT_STATE: HITL_SUSPEND]` 後，必須：
1. 暫停 Agent 輪詢迴圈。
2. 提取 `<BUDGET_EXHAUSTION_REPORT>` 中的 `HITL_DIRECTIVE` 呈現給人類工程師。
3. 等待人類指令以恢復對話或結案。

### 3.2 宿主物理強制熔斷 (Host-Forced Override)
若 LLM 因失控而無視預算，未能輸出 `<BUDGET_EXHAUSTION_REPORT>`，物理宿主在達到硬上限（例如總輪數 $> 15$ 次或單階段超出預算 1 步）時，必須執行 **Active Interception**：
1. 截斷 LLM 當前輸出。
2. 自動回滾受影響之 Git 工作區檔案 (`git checkout -- .`)。
3. 注入系統修補 Prompt，要求模型產出 `<BUDGET_EXHAUSTION_REPORT>` 並切換為 `HITL_SUSPEND` 狀態。
