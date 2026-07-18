# Matt Pocock Skills Framework — AI 工程化與 SOP 實踐指南

> **文件屬性**：AI 工程學參考資料與行為指引
> **關聯文件**：
> *   [Karpathy 行為準則](karpathy-guidelines.md)
> *   [Ponytail 懶人開發法](ponytail.md)
> *   [SWDD 做事方法 (SKILL.md)](../../template/modular/SKILL.md)

---

## 1. 背景與核心哲學 (Philosophy)

**`mattpocock/skills`** 是由 TypeScript 領域知名專家 Matt Pocock 發起的一套 **AI 協同開發工程學工作流（SOP）**。

其核心口號是：
> **"Real engineering, not vibe coding."** (追求真實工程學，反對憑感覺程式碼編寫)

該專案旨在解決 AI 輔助開發（如 Cursor, Claude Code, Codex）中最常見的四大致命缺陷：
1.  **意圖偏移 (Instruction Drift)**：模型偏離使用者原始需求，盲目大面積修改代碼。
2.  **紙面防禦 (Symptomatic Fixes)**：模型傾向於用 `null check` 等紙面防禦掩蓋錯誤，而非解決根本原因 (Root Cause)。
3.  **樂觀路徑 (Optimistic Path)**：僅處理 happy path，忽略異常與資源釋放。
4.  **連鎖失控重構 (Runaway Refactor)**：修改一個小 bug 卻連帶重構了無關的數十個檔案，導致極高回歸風險。

---

## 2. 技能分類與運作機制 (Taxonomy)

Pocock 將 Agent 的客製化技能 (Skills) 依據**主控權**劃分為兩大類：

```
┌──────────────────────────────────────────────────────────┐
│                      AI Agent Tool                       │
└────────────┬───────────────────────────────┬─────────────┘
             │                               │
             ▼ 使用者指令觸發                 ▼ 語意觸發詞引導
    【User-Invoked Skills】         【Model-Invoked Skills】
    (Reachable via slash commands)  (Reachable via trigger phrasing)
    - /grill-me                     - /tdd
    - /to-spec                      - /diagnosing-bugs
    - /implement                    - /codebase-design
    - /wayfinder                    - /code-review
```

*   **User-invoked (使用者觸發)**：
    必須由使用者手動輸入斜線指令（如 `/grill-me`）。此時會**強制模型暫停任何代碼編寫**，直接進入特定的訪談或分析 SOP。
*   **Model-invoked (模型觸發)**：
    當模型在對話中偵測到特定的情境（例如使用者回報程式崩潰、或者是模型想寫新功能時），會在 System Prompt 引導下**自動伸手調用**對應技能（如 tdd 或 diagnosing-bugs）。

---

## 3. 核心工程技能剖析 (Core Skills Deep Dive)

### 3.1 `/grilling` (拷問模式)
當使用者提出新構想或大變更時，Agent 必須以「蘇格拉底式」提問對使用者的設計進行極限壓力測試：
1.  **逐枝解析**：沿著決策樹的每一個分支進行提問，一次只問一個問題，禁止一次拋出多個問題（會造成使用者困惑）。
2.  **預先推薦**：提問時，Agent 必須提供其推薦的解答與理由，供使用者快速決策。
3.  **探測優先**：若問題的答案是物理事實（例如「既存的資料表欄位是什麼」），Agent 必須主動查閱檔案系統，嚴禁提問。只有設計決策（Decisions）才需提問。
4.  **確認後執行**：在使用者確認「達成共識」前，絕對禁止開始編寫代碼。

### 3.2 `/tdd` (測試驅動開發)
實行嚴格的紅-綠-重構迴圈（Red-Green-Refactor Loop），核心在於 **"Seam (邊界/接縫)"** 的觀念：
*   **Seam (邊界)**：指進行測試的公共邊界，也就是可以觀察到行為但無需觸及內部的接口。
*   **三大防範反模式 (Anti-patterns)**：
    1.  *Implementation-coupled (實現耦合)*：過度 mock 內部細節，導致一重構內部結構測試就壞，即便行為沒變。
    2.  *Tautological (同義反覆)*：測試的 Assert 邏輯與業務代碼算法完全一樣（例如 snapshot 抄襲），導致測試自我證明，永遠無法捕獲 bug。
    3.  *Horizontal slicing (橫向切片)*：一次寫完所有測試再寫實作。應採 **Vertical slicing (縱向切片)**，每次只寫一個 failing test（Red 狀態），寫最小代碼使其通過（Green 狀態），像**示蹤彈 (Tracer bullets)** 一樣前進。

### 3.3 `/diagnosing-bugs` (科學除錯迴圈)
面對疑難 Bug 與效能衰退時的嚴謹排查 SOP，分為六個 Phase：

#### Phase 1: 建立緊密的反饋迴圈 (Tight Feedback Loop)
*   **核心理念**：除錯的關鍵在於建立一個極速的 pass/fail 訊號。如果沒有訊號，看再多代碼也無濟於事。
*   **迴圈四要素**：
    1.  *Red-capable (可紅)*：能確實走到 bug 路徑，在 bug 存在時顯示為 Red，修復後顯示為 Green。
    2.  *Deterministic (確定性)*：每次運行結果一致，消除 flake 隨機性。
    3.  *Fast (快速)*：執行時間以秒計，而非分鐘。
    4.  *Agent-runnable (自動運行)*：無需人工介入。
*   *在該反饋迴圈建立並執行前，嚴禁進行任何假說或代碼修改。*

#### Phase 2: 重現與極小化 (Reproduce & Minimise)
*   重現使用者所說的「相同症狀」，而非附近的其他錯誤。
*   **極小化**：每次砍掉一個輸入、設定或步驟，重跑迴圈。直到剩下「少任何一項 bug 就會變綠」的最小 load-bearing (承重) 條件。

#### Phase 3: 提出可證偽假說 (Hypothesise)
*   在測試前，必須列出 **3~5 個排序的假說**，並提交給使用者確認。
*   假說必須是 **Falsifiable (可證偽的)**，必須符合格式：「如果 X 是原因，那麼改變 Y 會使 bug 消失，或者改變 Z 會使 bug 惡化」。

#### Phase 4: 變更單一變數與標記 (Instrument)
*   每次僅變更一個變數，優先使用 debugger 中斷點而非狂打日誌。
*   **標記日誌**：若必須打 log，強制帶有唯一隨機 tag (如 `[DEBUG-a4f2]`)。除錯結束後，用 `grep` 一次性將所有帶 tag 的 debug logs 清理乾淨，杜絕垃圾日誌殘留。

#### Phase 5: 在正確的邊界編寫回歸測試 (Fix + Regression)
*   在寫修復代碼前，先將 Phase 2 的極小化重現案例轉寫為 regression test，看它變紅，修復後看它變綠。

#### Phase 6: 清理與事後檢討 (Cleanup + Post-mortem)
*   清理所有 `[DEBUG-...]` 日誌，並問自己：「如何能在架構上預防此 bug？」

---

## 4. SWDA (Swarm-Driven Agent) 的啟發與對照

我們將 Matt Pocock 的 Skills 思想進行了**代理化 (Agentic)** 與**狀態機化 (FSM)** 的升級，形成了雙核心 SWDA 框架：

| Matt Pocock Skills | SWDA 運行時對應 (FSM & Subagents) |
|---|---|
| `/grilling` ➔ `/to-spec` | **`[PHASE_3_HYPERPLAN]` (對抗熔爐)**：由 Builder 與 Destroyer 對抗設計，並由 Referee (裁判) 指標評分與熔斷。 |
| `/to-tickets` | **`[PHASE_4_SYNTHESIS]` (共識昇華)**：將 Spec-Driven (介面與副作用) 與 Test-Driven (TDD 測試腳本) 封裝為實作藍圖。 |
| `/implement` (TDD + Review) | **`[PHASE_DYNAMIC_COMPILE]` (雙代理執行)**：在物理隔離沙箱中，由 Test Writer 撰寫失敗測試，Developer 編寫代碼使其通過，Reviewer 審查合併。 |
| `[DEBUG-...]` Tag | **`[Trajectory Regulation Gate]` (執行後守門)**：自動校驗 XML 標籤外雜質，防範退化，執行 cleanup 確保 master 分支乾淨。 |
