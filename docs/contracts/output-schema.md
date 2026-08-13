# SWDD Output Schema Contract v1.5.0

> **用途**：本檔為 `template/integrated/ALL_IN_RULE.md` §0 條目 2（XML 標籤強邊界）的**可審閱 / subagent 可載入契約**。SOUL 在每次大版本變更時必須同步更新本檔。
> **生效日**：2026-08-13
> **版本**：v1.5.0（同步 ALL_IN_RULE.md v14.2.0）

---

## 1. 全局強制（Global Constraints）

所有 subagent 與 SOUL 的輸出**必須**同時滿足以下三項：

1. **第一個非空字元**必須是某個允許的根標籤。
2. 根標籤**閉合後**，必須緊接一行 `[NEXT_STATE: PHASE_NAME | Zero-Chat Contract Active]`（無空行、無前後綴）。
3. 標籤外**任何字元**（包括空格、換行、Markdown 反引號、表情符號等）皆屬違規。

---

## 2. 允許的根標籤與內部結構（Allowed Root Tags & Inner Fields）

為確保小模型在長上下文或低難度推理下依然能精確輸出結構，以下為 7 個核心 XML 標籤的內部結構定義。你必須嚴格遵守以下結構與欄位名稱：

### 2.1 `<INTENT_GATE_RESULT>` (意圖與執行軌道分析)
```xml
<INTENT_GATE_RESULT>
INTENT_CLASSIFICATION: [CASUAL_CHAT | QUICK_QUERY | FULL_REFACTOR | BUG_FIX | FEATURE_DEV | SECURITY_AUDIT | CONFIG_CHANGE | DEPENDENCY_UPDATE]
EXECUTION_TRACK: [FAST_PASS | LITE_MODE | SWARM_MODE]
RESOURCE_LOCK_REQUIRED: [True | False]
USE_SWARM_WORKFLOW: [True | False]
AUDITOR_SAFETY_STATUS: [PASSED | BLOCKED_INJECTION | RE_CLASSIFY]
STRATEGY_TRACK: [描述分發子代理與審計子代理達成共識的調度路徑，FAST_PASS 填 Direct Response]
</INTENT_GATE_RESULT>
[NEXT_STATE: FAST_PASS_EXIT | LITE_MODE | PHASE_1_DESTRUCT | Zero-Chat Contract Active]
```

### 2.2 `<DESTRUCT_RESULT>` (任務降維拆解)
```xml
<DESTRUCT_RESULT>
INCIDENT_SUMMARY: [一句話精確定義核心需求或 Bug]
TASK_SUBAGENT_ALPHA_CORE: [分派給 Alpha 子代理的獨立研調指令]
TASK_SUBAGENT_BETA_EDGE: [分派給 Beta 子代理的獨立研調指令]
TASK_SUBAGENT_GAMMA_LATERAL: [分派給 Gamma子代理的獨立研調指令]
</DESTRUCT_RESULT>
[NEXT_STATE: PHASE_2_GATHER | Zero-Chat Contract Active]
```

### 2.3 `<GATHER_RESULT>` (資訊探測彙整)
```xml
<GATHER_RESULT>
CODEBASE_GRAPH_CONTEXT:
- [拓撲探測 Subagent 產出：AST 關係、調用鏈與變更邊界]
RELEVANT_MEMORIES_ANTI_PATTERNS:
- [記憶與知識檢索 Subagent 產出：Mimir / mempalace 反模式與 KIs 指引]
DATABASE_STATE_SCHEMAS:
- [資料庫與狀態探針 Subagent 產出：資料表結構、API 與狀態定義]
DESIGN_DOCUMENTS_AND_SPECS:
- [設計文件巡檢 Subagent 產出：既存設計規格、歷史架構決策與設計文件約束]
GLOBAL_CONTEXT_SUMMARY:
- [主控彙整：當前系統全貌、安全邊界與各子代理探測結論的交叉比對]
</GATHER_RESULT>
[NEXT_STATE: PHASE_3_HYPERPLAN | Zero-Chat Contract Active]
```

### 2.4 `<HYPERPLAN_RESULT>` (對抗式方案審查)
```xml
<HYPERPLAN_RESULT>
CRUCIBLE_STATUS: [FAILED | PASSED]
CRUCIBLE_SCORE: [當前裁判評定的總分與扣分原因說明]
VULNERABILITY_FOUND: [True | False]
ATTACK_POINTS: [條列詳細描述 Destroyer 發現的漏洞、崩潰點或效能瓶脅]
REQUIRED_FIXES: [條列說明 Builder 必須修正調整的具體技術方向]
</HYPERPLAN_RESULT>
[NEXT_STATE: PHASE_4_SYNTHESIS | Zero-Chat Contract Active]
```

### 2.5 `<SYSTEM_SPECIFICATION>` (共識昇華實作藍圖)
```xml
<SYSTEM_SPECIFICATION>
1. Architecture Decision Record (ADR)
- Context: [修復背景與系統異常狀態]
- Decision: [最終決策與採用的策略，以及在對抗中被紅軍擊潰的方案與原因]

2. Spec-Driven Contract
- Target Files & Symbols: [修改的目標檔案、類別或函數名稱，每一行核心變更必須帶有內容雜湊 Content Hash 以防錯位]
- Interface Contract: [輸入/輸出參數、異常處理與副作用定義，包含異常捕捉與資源釋放機制]
- Design Constraint Alignment: [如何對應 Phase 2 收集的既存設計文件與 DB schemas 約束]

3. Test-Driven (TDD) Contract
- Test Script Path: [預期寫入的 TDD 測試腳本路徑]
- Red-State Assertions: [具體預期會失敗 of TDD 斷言案例 (含正常、異常與邊界值)]
- Run Commands: [執行測試的具體 Terminal 命令]

4. Target Skill & Execution Directive
- Required Subagent: [指定所需調用的 subagent 類型，例如開發或審查 subagent]
- Continuation State: [寫入 boulder-state 追蹤器，防範 Token 超限]
- Directive Target: [交辦任務的具體目標與上述 Spec/TDD 合約的綁定關係]
</SYSTEM_SPECIFICATION>
[NEXT_STATE: PHASE_DYNAMIC_COMPILE | Zero-Chat Contract Active]
```

### 2.6 `<TASK_SUMMARY_REPORT>` (任務物理執行總結)
```xml
<TASK_SUMMARY_REPORT>
TASK_STATUS: [SUCCESS | FAILED]
FILES_MODIFIED:
- [列出所有修改的檔案路徑與主要函數]
TEST_RESULTS_PHYSICAL:
- [物理執行 TDD 測試與 self-check 驗證命令的輸出摘要]
REMAINING_CONCERNS:
- [列出此變更可能引發的潛在風險、副作用或未盡事項]
</TASK_SUMMARY_REPORT>
[NEXT_STATE: None | Zero-Chat Contract Active]
```

### 2.7 `<ACTION_REALIZATION_BLOCK>` (預檢攔截阻斷)
```xml
<ACTION_REALIZATION_BLOCK>
reason: [失敗的校驗項編號 + 一句話說明]
required_action: [具體補救指引]
bypass_allowed: [True | False]  # True 表示 HITL 可覆寫
</ACTION_REALIZATION_BLOCK>
[NEXT_STATE: None | Zero-Chat Contract Active]
```

### 2.8 `<BUDGET_EXHAUSTION_REPORT>` (預算耗盡熔斷報告)
```xml
<BUDGET_EXHAUSTION_REPORT>
EXHAUSTED_PHASE: [INTENT_GATE | GATHER | HYPERPLAN | DYNAMIC_COMPILE]
STEP_COUNT_REACHED: [1 | 3 | 5]
REASON: [說明預算耗盡與無法收斂之根因]
CURRENT_BEST_PROPOSAL: [摘要當前評分最高或最小可用之實作方案]
REMAINING_RISKS: [條列說明未決死角或未通過之測試斷言]
HITL_DIRECTIVE: [提請人類工程師決策之具體選擇題與處置建議]
</BUDGET_EXHAUSTION_REPORT>
[NEXT_STATE: HITL_SUSPEND | Budget Exhausted]
```
