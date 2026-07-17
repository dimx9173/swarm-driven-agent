---
title: Swarm-Driven Development (SWDD) - 多代理協同開發框架
description: 一個用於高質量軟體工程的多代理群體智能工作流程。具有並行規劃、對抗式規格審查（熔爐 Crucible）以及規格驅動實作的特點。
version: 2.5.0 (Deterministic-Actionable)
tags: [orchestration, swarm-intelligence, workflow, architecture, quality-assurance, multi-agent]
related:
  - "SOUL 認知引擎運行時: [SOUL.md](SOUL.md)"
  - "RULE 運行合約: [RULE.md](RULE.md)"
---

# Swarm-Driven Development (SWDD): 多代理協同開發框架 (Universal Framework)

## 1. 概述 (Overview)

**Swarm-Driven Development (SWDD)** 是一個系統化的群體智慧工作流程，旨在利用多個 AI 代理（一個群體 "swarm"）來解決複雜的工程問題。它專注於 **規格優先 (specification-first)** 的開發，使用對抗式流程在進行任何代碼實作之前「硬化（Harden）」架構與設計決策。

在 AGI 雙核心架構下，**[SOUL.md](SOUL.md)** 負責頂層設計與狀態轉移，而 **SWDD** 則是具體的 **做事方法 (做事方法論，Meta-Skill)**。SWDD 指引 Agent 經歷各個有限狀態機 (FSM) 階段，確保結構化的解析、對抗評審與實體測試驗證。

### 核心原則 (Core Principles)
1. **規格優先 (Spec-First)**：在架構規格書（SPEC）通過「熔爐（Crucible）」前，嚴禁編寫任何業務代碼。
2. **非對稱思辯辯論 (Asymmetric Dialectic)**：分派隔離的角色（Builder vs. Destroyer）以消除認知寬大效應偏差。
3. **並行研調 (Parallel Intelligence)**：派發並行且獨立的研調 Swarm 子代理（Alpha、Beta、Gamma）快速探索方案空間。
4. **驗證中心 (Verification-Centric)**：每個狀態轉移皆包含實體自動化校驗或多代理協同驗證。

---

## 2. SWDD 生命週期與 SOP 執行指引 (The SWDD Lifecycle)

SWDD 的 6 個概念階段嚴格對應到 [RULE.md](RULE.md) 中定義的 SOUL FSM Hooks：

### PHASE 1: DESTRUCT (並行研究 Swarm)
指派並行且完全隔離的研調 Swarm 子代理（Alpha/Beta/Gamma）進行多維度發散研究。各子代理必須在獨立的工作區中進行，嚴禁在 Phase 1 共享資訊或產生早期對齊。
*   **Alpha 建構子代理 (The Standard)**：研究業界最佳實踐、標準庫框架與主流 canonical 解法。
*   **Beta 破壞子代理 (The Adversary)**：專職挖掘潛在破壞點，包含併發 race conditions、極限邊界漏洞、技術債與安全威脅。
*   **Gamma 創新子代理 (The Innovator)**：尋求跨領域技術類比與非常規的 Alternative 替代方案。

### PHASE 2: GATHER (資訊探測與彙整)
彙整來自 Alpha、Beta 和 Gamma 的研調事實。指派 4 個並行檢索子代理：
*   **拓撲探測子代理**：使用代碼圖譜工具追蹤代碼依賴關係與變更邊界。
*   **記憶與知識檢索子代理**：檢索歷史反模式與知識庫項目 (Knowledge Items)。
*   **資料庫與狀態探針子代理**：查詢系統資料庫 Tables、Redis schemas 與 API 契約。
*   **設計文件巡檢子代理**：巡檢既存設計規格書與 ADR 決策。
*   **動作**：將探測結果封裝至 `<ANCHORED_MEMORY_AND_CONTEXT>` 標籤中，作為後續設計依據。

### PHASE 3 & 4: THE CRUCIBLE (對抗式方案審查)
在 `[PHASE_3_HYPERPLAN]` 狀態下執行的對抗式辯論：
1.  **Builder 子代理 (架構設計)**：利用收集的資訊，提出正式的架構設計規格書 (Architecture Specification)。規格書必須包含：*數據流與 API 契約*、*核心邏輯與虛擬碼*、*假設與限制*。
2.  **Destroyer 子代理 (熔爐對抗)**：對 Builder 的規格書實施漏洞攻擊，檢查死鎖、性能瓶頸與安全漏洞。
3.  **Referee 裁判子代理**：監控對話日誌，若 Builder 規格書連續 2 輪評分無提升或第 3 輪仍為 FAILED，立即啟動熔斷器，生成 Trade-off 權衡矩陣提請人類 (HITL) 裁決。

### PHASE 5: SYNTHESIS (最終藍圖與驗證)
將通過 Crucible 認證的共識封裝為設計文檔與實作藍圖（儲存為 ADR 記錄），深度融合以下設計契約：
*   **規格驅動合約 (Spec-Driven Contract)**：定義嚴格的 API 與介面契約。列出目標檔案、被修改函數簽章、輸入/輸出參數與副作用。
*   **測試驅動合約 (Test-Driven Contract)**：將驗收條件轉換為具體測試案例，規劃 TDD 測試腳本的路徑，列出預期會失敗（Red State）的正向、反向與邊界斷言（Assertions）案例與執行命令。

### PHASE 6: IMPLEMENT & REVIEW (多代理協同實作與物理執行)
1.  **執行前預檢閘**：檢查任務包是否包含 `<ANCHORED_MEMORY_AND_CONTEXT>`，TDD 失敗腳本是否就緒。不符則拒絕派遣，回退上限 2 次，超限則觸發 HITL 介入。
2.  **實體沙箱隔離**：強制在臨時隔離目錄或一次性容器中執行。
3.  **TDD 雙代理執行**：
    *   **測試編寫子代理 (Test Writer)**：撰寫測試腳本，運行並確認其物理處於失敗狀態（Red State）。
    *   **代碼開發子代理 (Developer)**：在嚴禁修改測試腳本的前提下，編寫業務代碼以通過所有測試（Green State）。
4.  **審查與驗證 (Reviewer)**：審查測試覆蓋率與代碼簡潔度，測試失敗則自動修復（重試上限 3 次，超限則觸發 HITL 介入）。

---

## 3. 何時啟用 SWDD

面對程式開發、代碼修改、依賴變更與配置調整任務時，SWDD 是預設的強硬路徑。單代理直接執行僅限於非功能性的純文檔/註釋更新。

| 專案類型 | 啟用 SWDD? | 運作邏輯 |
| :--- | :---: | :--- |
| **純文檔/註解編輯** | 否 | Markdown 拼字修正或排版調整。 |
| **Bug 修復 (即使 1 行)** | **是** | 防範回歸，執行代碼契約校驗與測試。 |
| **新增模組/功能** | **是** | 防止架構漂移，提供嚴格的 TDD 與介面合約。 |
| **重構遺留代碼** | **是** | 描繪隱藏依賴，建立 AST 變更邊界。 |
| **安全關鍵路徑** | **是** | 必須通過 Refute-or-Promote 審查與沙箱重現驗證。 |
