# SWDD 改造路線圖：借鏡 Life-Harness (arXiv:2605.22166v2)

> **文件目的**：基於 Life-Harness 論文分析，將其「Runtime Interface Adaptation」範式映射到 SWDD 既有架構，提出可審批的具體修改提案。
> **產出日**：2026-07-02
> **相對論文**：`../papers/2605.22166-life-harness.md`
> **狀態**：提案，待 Architect (HITL) 裁決

---

## 0. 改造前提聲明

### 0.1 結構同構性驗證

論文四層架構與 SWDD 既有元件存在一一對應，**雙方共享同一深層結構假設**——「凍結決策核心，在介面層承載可進化策略」：

| Life-Harness | SWDD 既有元件 | 既有／提案 |
|---|---|---|
| Environment Contract Layer | XML 標籤強邊界 §0, §2 | 既有（強化） |
| Procedural Skill Layer (BM25) | Mimir 反模式經驗應用 §3.2 | 既有（升級檢索機制） |
| Action Realization Layer | Ark AI Firewall §4 | 既有（加 dispatch 預檢） |
| Trajectory Regulation Layer | Watchdog + Adaptive HITL §7 | 既有（加退化分類） |

### 0.2 不應移植的部分（明確排除）

- **BM25 純詞袋檢索**：SWDD 處理程式碼語意任務，dense retrieval（LSP-aware）更合適
- **完全 deterministic 假設**：SWDD 處理開放式決策，不滿足論文前提
- **Coding agent (Codex) 作為 evolver**：成本過高且引入黑箱依賴
- **harness 程式碼全自動進化**：對核心合約而言風險過大

---

## 1. 總修改清單（依優先級）

| ID | 優先級 | 提案 | 目標檔案 | 變更行數估計 |
|---|---|---|---|---|
| **P1-A** | P1 | Mimir 升級為可檢索式反模式庫 | `ALL_IN_RULE.md` §3.2 | +8~12 行 |
| **P1-B** | P1 | Action Realization 預檢 subagent 模式 | `ALL_IN_RULE.md` §6 新增小節 | +25~35 行 |
| **P2-A** | P2 | Watchdog 退化分類（repetition/stagnation/budget） | `ALL_IN_RULE.md` §7 | +15~20 行 |
| **P2-B** | P2 | Environment Contract 顯式化為可讀檔案 | 新增 `docs/contracts/*.md` + 引用 | +10 行 + 新檔 |
| **P3-A** | P3 | Cross-Session Harness 遷移實驗 | 純研究任務，無檔案變更 | 0 |

---

## 2. 提案詳述

### P1-A：Mimir 升級為可檢索式反模式庫

**目標**：將現有「手動 Few-Shot 注入」升級為「自動檢索式注入」，借鏡 Life-Harness 的 Procedural Skill Layer。

**現狀（§3.2 原文摘錄）**：
```
### 3.2 Mimir 反模式經驗應用
*   當你在 Crucible 階段被駁回，或在實體代碼驗證中遭遇失敗時，
    你必須立即將該次失敗模式提取為「反模式記錄 (Anti-pattern)」。
*   你必須將此記錄強制寫入全域知識圖譜（如透過 mempalace），
    在後續任務中作為 Few-Shot 樣本加載，以實現直覺共享。
```

**問題**：
- 「作為 Few-Shot 樣本加載」是**手動的、未結構化的**——無法判斷何時該注入哪些反模式
- 未定義**檢索觸發條件**與**注入位置**（違反 Arachne 優化原則）
- 無衰減機制（與 §3.1 Ebbinghaus 公式脫節）

**提案新增段落**（插入於 §3.2 末尾，行 61 後）：

```markdown
#### 3.2.1 Procedural Skill 檢索機制（借鏡 Life-Harness Skill Layer）
*   **結構化反模式庫**：所有反模式記錄必須以 YAML 結構儲存，
    至少包含 `id`、`trigger_context`、`failure_mode`、`remediation`、
    `frequency`、`last_seen` 六欄。
*   **檢索觸發時機**：
    1. INTENT_GATE 階段：根據意圖分類檢索對應反模式子集
    2. Crucible FAILED 後：在修補方案前注入相關歷史失敗案例
    3. subagent dispatch 前：依任務類型檢索 subagent 角色反模式
*   **檢索實作與冷啟動**：MVP 採簡單的**標籤與 metadata 關鍵字比對 (Tag-based/Metadata matching)**，避免引入複雜的外部語意檢索或詞袋庫造成冷啟動延遲；後續可升級為 LSP-aware semantic search。
*   **Arachne 注入策略**：檢索結果必須放在 Prompt 窗口的**最末端（即 Task Context 之前，緊貼任務指令）**，以防 lost-in-the-middle 效應，並在執行前保留最大的 LLM 注意力聚焦，無須在前端與末端重複注入以節省 Token。
*   **衰減整合**：每筆反模式的優先級 P 遵循 §3.1 的 Ebbinghaus 公式；
    為與 mempalace 狀態持久化對齊，衰減步數 t 以 `dt = current_timestamp - last_seen`（以實體時間差）進行計算；當 R(t) < 0.15 時自動從 active set 歸檔到 cold archive。
```

**影響範圍**：
- 修改 1 個檔案，1 個小節
- 不破壞既有 Ebbinghaus 公式（向後相容）
- 不引入新依賴（使用內建標籤匹配）

**Goal-Driven Verification**：
1. 讀者能在 §3.2.1 中找到六欄結構定義 → verify: `grep "trigger_context|failure_mode|remediation" template/integrated/ALL_IN_RULE.md`
2. 讀者能說出三個檢索觸發時機 → verify: 程式化 grep "INTENT_GATE|Crucible|subagent dispatch"
3. 讀者能找到標籤匹配 → LSP 升級路徑 → verify: `grep "LSP-aware semantic search"`
4. 讀者能找到 Arachne 注入位置約束 → verify: `grep "最末端.*Task Context"`

**風險標記**：
- ⚠️ 如果 BM25 檢索品質差，可能注入錯誤反模式導致「**Optimistic Path 反模式**」（依 §7.1）
- ⚠️ 緩解：MVP 階段保留「手動 review 機制」，僅在 ≥3 筆歷史反模式時啟用自動檢索

---

### P1-B：Task Dispatch Validator 與 Action Realization 預檢

**目標**：在 subagent dispatch 與 Ark Firewall 之外，新增「任務前置校驗」與「輸出介面合規校驗」環節，直接阻斷確定性失敗。

**現狀問題**：
- §4 Ark Firewall 偏重運行時的「命令特徵字串比對」（如 `rm -rf`）
- §6 Refute-or-Promote 偏重行為的「PoC 重現驗證」
- **缺口**：缺乏對 subagent **前置任務邊界**的硬性檢查，以及**輸出 schema 的強合約攔截**。

**提案新增小節**（插入於 §4 與 §5 之間，作為新的 §4.5）：

```markdown
### 4.5 Task Dispatch Validator 與 Action Realization（借鏡 Life-Harness Action Layer）

為防止任務範疇失控或格式毀損，必須引進前置驗證與後置攔截機制：

*   **前置 Task Dispatch Validator (任務派發預檢)**：
    在派遣開發或審查 subagent 之前，主控程序 (SOUL) 必須先對任務包進行結構化合約校驗。
    - **校驗方式**：為減少 Token 與延遲開銷，**邊界檢查與依賴審查等規則優先採用 Python 腳本進行靜態代碼校驗**。僅在涉及主觀邏輯（如可逆性、測試契約完整性）時，才調用輕量級預檢 subagent。
    - **校驗清單**：
      1. **任務邊界檢查 (靜態)**：輸入與輸出路徑是否嚴格限制在工作區內（防止 §7.1 Kitchen Sink）。
      2. **副作用與依賴審查 (靜態)**：若有新增依賴，是否在 §2.5 鐵律中通過安全掃描與白名單確認。
      3. **測試契約完整性 (LLM)**：是否已產出明確的 TDD acceptance criteria 與驗證腳本路徑。
      4. **可逆性與復原評估 (LLM)**：重大變更是否聲明 undo 方案，否則需觸發 Adaptive HITL 物理確認。
    - **預檢攔截 (Block) 輸出**：若任一項未通過則 Block 並回傳：
      ```
      <ACTION_REALIZATION_BLOCK>
      reason: [失敗的校驗項編號 + 一句話說明]
      required_action: [具體補救指引]
      bypass_allowed: [True | False]  # True 表示 HITL 可覆寫
      </ACTION_REALIZATION_BLOCK>
      ```

*   **後置 Action Realization Layer (輸出合約攔截)**：
    在 subagent 執行完畢並回傳 XML 數據後，主控程序在寫入檔案或調用工具前，必須執行實體校驗：
    - **解析驗證**：自動解析輸出區塊。若發現 XML 根標籤未閉合、格式毀損、或根標籤外有額外字符，立即攔截。
    - **校正與回饋**：不直接發送至環境執行，而是將 XML 格式錯誤訊息回傳給 subagent，要求其在 1 輪內完成 canonicalization 自我修正。
```

**影響範圍**：
- 修改 1 個檔案，新增 1 個小節
- 不破壞既有 §4 Firewall（七條 TC 規則）
- 不破壞既有 §5 FSM（新增為 subagent dispatch 流程的前/後置步驟）

**Goal-Driven Verification**：
1. 讀者能找到新小節位置 → verify: `grep "Task Dispatch Validator" template/integrated/ALL_IN_RULE.md`
2. 讀者能列出四項校驗清單 → verify: `grep -c "^\\s*[0-9]\\." template/integrated/ALL_IN_RULE.md` ≥ 4 in section
3. 讀者能找出靜態代碼校驗與 LLM 預檢的區分 → verify: `grep "優先採用 Python 腳本進行靜態代碼校驗" template/integrated/ALL_IN_RULE.md`
4. 讀者能找到後置輸出合約攔截定義 → verify: `grep "後置 Action Realization Layer" template/integrated/ALL_IN_RULE.md`

**風險標記**：
- ⚠️ 預檢本身可能引入 Token 開銷——緩解：只對寫入任務預檢，跳過純讀取任務
- ⚠️ 可能變成 §7.1 **The Wrong Abstraction**（過度泛化）——緩解：MVP 階段僅強制 §4.5 第 1、4 兩項（邊界 + 測試契約），其餘為 optional

---

### P2-A：Watchdog 退化分類與實體狀態雜湊

**目標**：將現有單純的「5 步工具級循環檢測」升級為三種**退化模式分類**，配合精確的實體狀態雜湊 (State Hash) 與對應的恢復策略。

**現狀（§7 節錄）**：
```
*   **工具級循環檢測**：在 5 步執行窗口內，若使用相同或語意極相似
    參數調用同一工具達 3 次或以上，立即暫停並觸發自我修正。
```

**問題**：
- 僅偵測「工具級調用重複」，忽略了實體文件系統或終端狀態的停滯不前。
- 缺乏對「語意相似但參數略異（如微調指令）」或「預算與 Token 快耗盡」的分類。
- 缺乏針對特定退化模式的具體應變措施（只模糊提及「自我修正」）。

**提案新增段落**（插入 §7.1 之前）：

```markdown
### 7.0 Trajectory 退化分類（借鏡 Life-Harness Trajectory Regulation）

Watchdog 必須區分三類退化模式，以精確的證據鏈進行檢測與分類恢復：

| 模式 | 偵測訊號 | 恢復策略 |
|---|---|---|
| **Repetition** | 相同動作或指令語意 Hash $\ge 3$ 次 / 5 步窗口 | 觸發**角色切換 (Role Gating)**：強制重啟 subagent，依據任務類型切換至 Debugger/Reviewer 範本，並在 System Prompt 強制加重注入相關失敗案例的反向提示。 |
| **Stagnation** | 連續 $N$ 步實體 **State Hash** 無變化 | 主動回退 (Rollback) 至上一次 State Hash 變動的狀態點，清除緩存，並強制啟用 §3.2 Mimir 檢索相關反模式。 |
| **Budget Exhaustion** | 剩餘 token 數 $<$ 20% 閾值，或執行步數達 85% 限制 | 暫停當前自動執行，觸發 Adaptive HITL 物理對話，提示用戶縮減當前任務邊界或手動介入決策。 |

*   **實體 State Hash 定義**：
    為了防範 LLM 僅靠 Thought 欄位變化來規避停滯檢測，實體 State Hash 必須由實體環境特徵計算得出：
    $$\text{State Hash} = \text{Hash}(\text{當前 Git Diff} \oplus \text{最後 2 次 terminal 輸出的 stdout} \oplus \text{當前操作的檔案路徑與大小})$$
*   **偵測頻率**：每次 subagent 執行結束時檢查一次；每 5 步全局窗口檢查一次。
*   **誤報率控制**：每次退化警報必須附帶 $\ge 1$ 個可觀察的實體 hash 變動證據，禁止僅憑模型直覺判斷。
*   **與 §7「工具級循環檢測」的關係**：本節為工具級檢測的**上位分類與應對指導**，當偵測到工具循環後，必須先套入此分類，再執行對應的恢復策略。
```

**影響範圍**：
- 修改 1 個檔案，§7 增加子小節
- 不破壞既有「5 步循環檢測」（向後相容，作為 Repetition 的子情況）
- 新增 1 個表格

**Goal-Driven Verification**：
1. 讀者能列出三類退化模式 → verify: `grep "Repetition\\|Stagnation\\|Budget Exhaustion" template/integrated/ALL_IN_RULE.md`
2. 讀者能找到對應恢復策略 → verify: `grep "恢復策略" template/integrated/ALL_IN_RULE.md`
3. 讀者能找到偵測頻率規範 → verify: `grep "5 步全局窗口" template/integrated/ALL_IN_RULE.md`

**風險標記**：
- ⚠️ 表格化新增可能破壞「極簡」鐵律——緩解：採用緊湊表格（已展示），不加任何說明性段落
- ⚠️ 容易與既有 §7 循環檢測混淆——已明確聲明「上位分類」關係

---

### P2-B：Environment Contract 顯式化為可讀檔案

**目標**：將 §0「XML 標籤強邊界」從「注意」升級為「可被 subagent 讀取的契約檔」，避免依賴 SOUL 的注意力。

**現狀**：
- §0 條目 2：「你的所有輸出必須包裹在對應 FSM 階段的 XML 標籤內...標籤外不得夾帶任何字元（包括空格或換行）」
- 這是**對 LLM 的注意力指令**，但**沒有人類可審閱 / subagent 可載入的契約檔**

**提案**：

#### 步驟 1：建立 `docs/contracts/output-schema.md`（新檔案，~40 行）

範例骨架：
```markdown
# SWDD Output Schema Contract v1

## 全局強制

所有輸出必須符合以下結構：
1. 第一個非空字元必須是某個允許的根標籤
2. 根標籤閉合後，必須緊接一行 `[NEXT_STATE: ...]`（無空行）
3. 標籤外任何字元（包括空格、換行）皆為違規

## 允許的根標籤

[此處列出 §5 的六個 XML 標籤及其用途]

## 違規處置

[對應 §0 條目 5「客觀中立」+ §7 Watchdog]
```

#### 步驟 2：在 `ALL_IN_RULE.md` §0 加入引用

新增條目 6：
```
6.  **契約檔錨定 (Contract Anchoring)**：上述 XML 標籤規範的完整契約
    定義位於 `docs/contracts/output-schema.md`，subagent 必須在派遣時
    載入此檔案而非依賴「注意」。SOUL 應在每次大版本變更時同步更新契約檔。
```

**影響範圍**：
- 新增 1 個檔案（`docs/contracts/output-schema.md`）
- 修改 §0，新增 1 條
- 不破壞既有任何 XML 標籤定義

**Goal-Driven Verification**：
1. 讀者能找到契約檔 → verify: `ls docs/contracts/output-schema.md`
2. 契約檔含全局強制條款 → verify: `grep "根標籤\\|NEXT_STATE" docs/contracts/output-schema.md`
3. §0 含契約錨定條目 → verify: `grep "Contract Anchoring\\|契約檔錨定" template/integrated/ALL_IN_RULE.md`

**風險標記**：
- ⚠️ 新增檔案 = 違反「ALWAYS prefer editing existing files」——緩解：契約檔屬於全新範疇（docs/ 而非合約本體），無既有檔案可編輯
- ⚠️ 維護成本：SOUL 變更時易漏同步契約檔——緩解：明確聲明「每次大版本變更時同步」

---

### P3-A：Cross-Session Harness 遷移實驗

**狀態**：研究提案，**不需修改任何檔案**。

**目標**：借鏡論文「僅由 Qwen3-4B 軌跡進化 → 套用到 17 個模型」的設計，在 SWDD 內做一次實驗：
- 收集一個 SWDD session 的 subagent 派發軌跡
- 蒸餾出 subagent 角色合約片段
- 套用到不同 LLM provider（cross-provider portability test）
- 驗證是否仍生效

**預期產出**：
- 實驗報告：`docs/research/cross-session-harness-experiment.md`
- 數據支撐：未來是否「採用 Life-Harness 風格的可進化 subagent 角色庫」的決策依據

**此提案的開關條件**：P1-A、P1-B、P2-A 至少完成兩項後才啟動。

---

## 3. 變更衝擊評估（Runaway Refactor 自檢）

### 3.1 行數估算 vs 既有架構

| 提案 | 變更行數 | 佔 ALL_IN_RULE.md 比例 (248 行) |
|---|---|---|
| P1-A | +12 | +4.8% |
| P1-B | +35 | +14.1% |
| P2-A | +20 | +8.1% |
| P2-B | +10 (ALL_IN_RULE) + 40 (新檔) | +4.0% (ALL_IN_RULE) |
| **合計** | **ALL_IN_RULE +77 (31%)；新檔 +40** | **落在「微創」邊界內** |

→ **通過 Runaway Refactor 自檢**：單次最大變更（§4.5 新增）僅新增 35 行，未觸及既有任何段落。

### 3.2 對「極簡鐵律」的合規性

| 提案 | 是否前瞻性設計（Speculative） | 是否單次使用抽象 |
|---|---|---|
| P1-A | 否（對應既有 §3.2 功能的明確強化） | 否（Mimir 為全局元件） |
| P1-B | 部分（5 項檢查中，2 項為 optional，避免「為將來設計」） | 否 |
| P2-A | 否（彌補既有 §7 循環檢測的盲點） | 否 |
| P2-B | 否（解耦「注意力指令」與「可審閱契約」） | 否 |

→ 通過「Simplicity First」自檢。

### 3.3 對「客觀中立與邏輯直言」鐵律的合規性

提案中所有引入術語（BM25、退化分類、預檢）均為論文既有實證或工程慣例，**未創造未經驗證的內部 jargon**。

---

## 4. 決策矩陣（供 HITL 裁決）

請 Architect 對以下問題逐一裁決：

| 問題 | 選項 |
|---|---|
| Q1：是否採納 P1-A「Mimir 檢索化」？ | A) 全量採納（自建 Tag 檢索 + 實體時間衰減）　B) 僅採納 Tag 檢索機制，暫緩衰減整合　C) 暫緩 |
| Q2：是否採納 P1-B「Task Validator & Action Realization」？ | A) 全量採納（靜態/LLM 混合預檢 + 後置 XML 合合約攔截）　B) 僅採納後置 XML 攔截與靜態預檢　C) 暫緩 |
| Q3：是否採納 P2-A「退化分類與實體 Hash」？ | A) 全量採納（Repetition + Stagnation + Budget + 實體 State Hash）　B) 僅採納 Repetition 與 Budget，暫緩 State Hash 計算　C) 暫緩 |
| Q4：是否採納 P2-B「契約檔錨定」？ | A) 全量採納（新建 `docs/contracts/output-schema.md` + §0 引用）　B) 僅修改 §0 文字，不建立獨立契約檔　C) 暫緩 |
| Q5：採納順序？ | A) 全部並列　B) P1-A $\rightarrow$ P1-B $\rightarrow$ P2-A $\rightarrow$ P2-B 漸進式順序　C) 客製 |
| Q6：是否需要版本升級？ | A) 1.1.1 $\rightarrow$ 1.2.0 (Minor)　B) 維持 1.1.1　C) 1.1.2 (Patch) |

---

## 5. 接受裁決後的執行路徑

一旦 Architect 對 §4 的問題作出選擇，本路線圖將轉化為：

```
SYSTEM_SPECIFICATION (Phase 4 Synthesis)
  ├── ADR-001: Mimir 檢索化升級
  ├── ADR-002: Action Realization 預檢
  ├── ADR-003: Watchdog 退化分類
  └── ADR-004: Contract 顯式化

DYNAMIC_COMPILE (Phase 6 Swarm)
  ├── 派遣開發 subagent → 執行 §中§的微創變更
  ├── 派遣審查 subagent → 對 diff 做 Surgical 自檢
  ├── 派遣測試 subagent → 對 §3 Goal-Driven Verification 跑 grep 驗證
  └── 產出 TASK_SUMMARY_REPORT → 含本路線圖執行情況
```

---

## 6. 文件交叉引用

> **2026-07-02 路徑更新**：原始錯誤假設「ALL_IN_RULE.md 與 RULE/SKILL/SOUL 是同步的 master/derivative 關係」已被 Architect 否決。**兩者為獨立套餐**（見 `../architecture/bundle-comparison.md`）。本路線圖的所有 P1/P2 提案目前**僅以 `template/integrated/ALL_IN_RULE.md` 為單一改造目標**；如要將變更同步到 `template/modular/` 套餐，需由 Architect 明確授權另開任務。

| 引用 | 用途 |
|---|---|
| `../papers/2605.22166-life-harness.md` | 原始論文結構化筆記 |
| `../../template/integrated/ALL_IN_RULE.md` | 改造目標主檔案（integrated 套餐，v1.0 已執行） |
| `../../template/modular/RULE.md` | 運行合約（modular 套餐，v2.0 已執行） |
| `../../template/modular/SOUL.md` | 認知引擎（modular 套餐）— **不在改造範圍**（屬 §1 雙核心架構，非運行合約） |
| `../../template/modular/SKILL.md` | SWDD 框架（modular 套餐）— **不在改造範圍**（屬做事方法層，非運行合約） |
| `../../installer.py` | 模板發佈器（僅引用 `template/modular/`） |
| `../../docs/contracts/output-schema.md` | integrated 契約檔（v1.0） |
| `../../docs/contracts/output-schema-modular.md` | modular 契約檔（v2.0） |

---

## 7. 變更歷史

| 版本 | 日期 | 異動 |
|---|---|---|
| v0.1 | 2026-07-02 | 初稿建立，待 HITL 裁決 |
| **v1.0-executed** | 2026-07-02 | **全部 4 項提案已落地**（見下表） |

### v1.0 執行落地對照表（integrated 套餐）

| 提案 | 狀態 | Commit | 目標檔案 | 行數變化 |
|---|---|---|---|---|
| P1-A（§3.2.1 Mimir 檢索化） | ✅ DONE | `35dbfe3` | `template/integrated/ALL_IN_RULE.md` | 248 → 258（+10） |
| P1-B（§4.5 Dispatch Validator + Action Realization） | ✅ DONE | `28ccce6` | `template/integrated/ALL_IN_RULE.md` | 258 → 286（+28） |
| P2-A（§7.0 退化分類 + State Hash） | ✅ DONE | `416584a` | `template/integrated/ALL_IN_RULE.md` | 286 → 303（+17） |
| P2-B（§0 條目 6 + output-schema contract） | ✅ DONE | `02964d6` | `template/integrated/ALL_IN_RULE.md` + `docs/contracts/output-schema.md` | 303 → 304（+1）+ 新檔 58 行 |

**總計**：`ALL_IN_RULE.md` 248 → 304 行（+56 行，+22.6%），新契約檔 58 行；4 個獨立 commit；所有 §2 Goal-Driven Verification 4/4 通過；`test_installer.py` 6/6 仍通過（modular 套餐未觸碰）。
**版本**：依 Q6 = B 維持 `1.1.1-all-in-one`（patch-level，不觸發 semver bump）。

---

### v2.0-executed：modular 套餐鏡像（2026-07-02，Architect 觸發）

> **觸發**：用戶於 v1.0 完成後追加指令「`@template/modular` 也要整合優化」——授權將同 4 項提案鏡像至 modular 套餐（target: openclaw/hermes）。**未複製 integrated 內容**，而是按 modular 的 §5 結構（方括號 FSM Hook 命名、`http://localhost:9720` 端點、SOUL.md sda 標記機制）重新撰寫。

| 提案 | 狀態 | Commit | 目標檔案 | 行數變化 |
|---|---|---|---|---|
| P1-A'（§3.2.1 modular） | ✅ DONE | `53ffe87` | `template/modular/RULE.md` | 256 → 266（+10） |
| P1-B'（§4.5 modular） | ✅ DONE | `3435dc5` | `template/modular/RULE.md` | 266 → 296（+30） |
| P2-A'（§7.0 modular） | ✅ DONE | `e408e3a` | `template/modular/RULE.md` | 296 → 313（+17） |
| P2-B'（§0 条目 6 + modular contract） | ✅ DONE | `cd03796` | `template/modular/RULE.md` + `docs/contracts/output-schema-modular.md` | 313 → 314（+1）+ 新檔 88 行 |

**總計**：`RULE.md` 256 → 314 行（+58，+22.7%），新 modular 契約檔 88 行；4 個獨立 commit；所有 Goal-Driven Verification 4/4 + 5/5 通過；`test_installer.py` 6/6 全程通過（modular 部署管道未壞）。
**版本**：依 Q6 = B 維持 `2.2.1-agent-optimized`（patch-level，不觸發 semver bump）。

#### 兩套餐鏡像對照（用於審查 reviewer 確認）

| 變更點 | integrated/ALL_IN_RULE.md | modular/RULE.md | 差異 |
|---|---|---|---|
| §3.2.1 YAML 欄位 | 6 欄基本結構 | 6 欄 + 顯式標記 frequency/last_seen 為 §3.1 Ebbinghaus 輸入 | modular 強調衰減整合 |
| §4.5 Firewall 關係 | 無 §4 引用（獨立小節） | 顯式聲明與 §4 Firewall 正交 | modular 因 §4 含 TC-01~07 表格需明確區隔 |
| §7.0 Budget Exhaustion | 觸發 Adaptive HITL | 觸發 Adaptive HITL **（透過 §0 的 `http://localhost:9720`）** | modular 走實體端點 |
| 契約檔命名 | `output-schema.md` | `output-schema-modular.md` | 顯式區分（防混淆） |
| 契約檔特色 | 含 6 個根標籤 + 4 個內嵌標籤 | 額外含 `COMMAND_EXECUTE_START/END` 邊界（modular §5 Hook 6 特有） | modular 反映其實體執行語法 |
| sda 標記同步 | N/A | §4 顯式協議：契約變更 → SOUL.md sda 區塊同步 → installer.py 邏輯同步 | modular 因有 installer.py merge 流程需多一步 |

**P3-A**（Cross-Session Harness 遷移實驗）：屬研究任務，不需檔案變更；前置依賴（P1-A/P1-B/P2-A）已滿足 3/3，現可獨立發起研究 session。

---

### v2.0-release (2026-07-07)
| 版本 | 日期 | 異動 |
|---|---|---|
| **v2.0-release** | 2026-07-07 | **流程規則優化與 FSM 對齊發佈**（Task Dispatch Validator 與 Action Realization 落地，SKILL.md 8 步對齊與 Mimir 檢索優化） |
| **v2.0.1-patch** | 2026-07-07 | **修復 pipx update 錯誤**（增加環境無 pip 時自動執行 pipx reinstall swda 備用方案） |

### v2.0 執行落地對照表
- `ALL_IN_RULE.md` 升級至 `1.2.1-all-in-one`
- `RULE.md` 升級至 `2.3.1-agent-optimized`
- `SKILL.md` 升級至 `2.2.1 (Deterministic-Actionable)`
- `docs/contracts/output-schema.md` 升級至 `v1.1`
- `docs/contracts/output-schema-modular.md` 升級至 `v1.1`
- `setup.py` 升級至 `1.2.1`
