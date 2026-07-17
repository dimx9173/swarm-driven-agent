# Template Bundle Comparison

> **目的**：避免未來 Agent 將 `template/integrated/` 與 `template/modular/` 兩個子目錄誤認為同步的 master/derivative 關係。
> **產生日**：2026-07-02（源於用戶明示聲明兩者為獨立套餐方案）
> **狀態**：Architect 確認生效

---

## 1. 結構總覽

```
template/
├── integrated/
│   └── ALL_IN_RULE.md         ← 單檔整合套餐（v1.6.1-all-in-one）
└── modular/
    ├── SOUL.md                ← 認知引擎套餐（v13.1.3-deterministic）
    ├── RULE.md                ← 運行合約套餐（v2.7.0-agent-optimized）
    └── SKILL.md               ← SWDD 框架套餐（v2.5.0-deterministic-actionable）
```

---

## 2. 套餐差異對照

| 維度 | integrated | modular |
|---|---|---|
| **檔案數** | 1 個（ALL_IN_RULE.md） | 3 個（SOUL + RULE + SKILL） |
| **設計哲學** | 單檔全部載入，便於一次性 prompt ingestion | 分檔組合，彈性高但需 subagent 自行載入 |
| **適用場景** | **其他通用 LLM 工具**（Kilo / Claude Code / Cursor / OpenCode 等）| **openclaw / hermes agent runtime**（經 `installer.py` 部署） |
| **版本獨立性** | v1.6.1 自有版本號 | 各自獨立版本號（13.1.3 / 2.7.0 / 2.5.0） |
| **被 installer.py 引用** | ❌ 否 | ✅ 是（見 `installer.py` 第 11-13 行） |
| **中英文支援** | 提供中文版 (`ALL_IN_RULE.md`) 與英文版 (`ALL_IN_RULE.en.md`) | 提供中文審查版 (`SOUL.md`/`RULE.md`/`SKILL.md`) 與英文安裝版 (`SOUL.en.md`/`RULE.en.md`/`SKILL.en.md`) |
| **適用任務複雜度** | 中小型任務最佳 | 大型多代理編排任務最佳 |
| **上下文開銷** | 一次性較高 | 可分批載入，總量相同但峰值較低 |

### 2.1 部署機制（Architect 明示，2026-07-02）

| 維度 | integrated | modular |
|---|---|---|
| **部署方式** | **手動安裝**——使用者自行將檔案放到目標 LLM 工具的 prompt / system message 目錄 | **腳本安裝**——透過 `installer.py` 自動寫入既有 agent workspace |
| **更新流程** | 重新複製檔案覆蓋，無 merge 邏輯 | installer.py 內建 `merge_soul_content` 等增量合併機制 |
| **失敗恢復** | 手動 rollback（git checkout + 重新覆蓋） | installer.py 內建 backup / revert 流程（見 `installer.py` `~615` 行） |
| **適用客群** | 用戶自有的通用 LLM 工具（Kilo / Claude Code / Cursor / OpenCode 等） | **openclaw / hermes agent runtime** 的使用者（由 `installer.py` 部署到 `~/.openclaw/` 或 `~/.hermes/`） |

→ **這是兩套餐的關鍵差異**：integrated 是「檔案即產品」（手動複製給通用 LLM 用），modular 是「以腳本為產品的發佈工具鏈」（自動部署到 openclaw/hermes agent）。

### 2.2 部署目標對照（Architect 明示，2026-07-02）

| 套餐 | 部署目標 | 安裝動作 | 路徑特徵 |
|---|---|---|---|
| **integrated** | **所有非 openclaw/hermes 的 LLM 工具**（目前已知：Kilo / Claude Code / Cursor / OpenCode 等） | 使用者手動複製 `ALL_IN_RULE.md` 內容到目標工具的 system prompt / custom instructions | 工具廠商定義 |
| **modular** | **openclaw / hermes** agent runtime 專用 | 透過 `installer.py` 掃描 `~/.openclaw/` 與 `~/.hermes/` 並寫入 `SOUL.md / RULE.md / SKILL.md` | `~/.openclaw/workspace{,s,-front-end}/SOUL.md` 或 `~/.hermes/{,profiles/*}/SOUL.md` |

→ **精確分流原則**：「`template/modular` 專為 openclaw/hermes；其他 tool 用 `template/integrated/ALL_IN_RULE.md`」。未來若新增 agent runtime（如 Claude Code Workspace 類產品），應**新增獨立套餐**而非擴張 modular 的範疇。

---

## 3. 被外部引用的真實狀況（grep 證據）

| 路徑 | 引用點數 | 主要消費者 |
|---|---|---|
| `template/modular/SOUL.md` | 140+ 命中 | `installer.py` 創建新 agent 的 SOUL 模板（openclaw/hermes） |
| `template/modular/RULE.md` | 60+ 命中 | `installer.py` 創建新 agent 的 RULE 模板（openclaw/hermes） |
| `template/modular/SKILL.md` | 30+ 命中 | `installer.py` 創建新 agent 的 SKILL 模板（openclaw/hermes） |
| `template/integrated/ALL_IN_RULE.md` | 0 程式碼命中 | 通用 LLM 工具的單檔手動載入（Kilo / Claude Code / Cursor / OpenCode） |

→ **程式碼層面只有 modular 套餐被使用**（服務 openclaw/hermes），integrated 套餐完全是為了給**通用 LLM 工具**做一站式載入設計。

---

## 4. 開發約束（重要）

### 4.1 修改時的套餐識別

在動任何 `template/**/*.md` 前，**先確認你面對的是哪一個套餐**：

- **改 `integrated/ALL_IN_RULE.md`**：手動部署，變更只影響願意重新複製檔案的使用者。風險最低。
- **改 `modular/SOUL.md`**：透過 `installer.py merge_soul_content` 增量合併到既有 agent（見 installer.py `~176` 行）
- **改 `modular/RULE.md`** 或 `modular/SKILL.md`**：直接覆蓋，無 merge 邏輯

### 4.2 禁止行為

- ❌ **禁止將 integrated 的內容拷貝 / 鏡像到 modular 任一檔案**：兩者是獨立的設計決策，並非源流關係
- ❌ **禁止把 modular 三件視為「拆分版的 ALL_IN_RULE」**：它們的版本號、結構、編輯節奏都不一致
- ❌ **禁止跨套餐同步 commit / 同步維護**：每次變更只 commit 到一個套餐
- ❌ **禁止把 modular 的 merge / backup 邏輯強加到 integrated**：兩者部署管道本質不同

### 4.3 鼓勵行為

- ✅ 在跨套餐共享的概念出現時，在兩個套餐**各自**新增短段引用而非拷貝內容
- ✅ 版本升級時**各自 bump**，不要聯動
- ✅ 修改 `template/modular/*` 前**必跑** `python test_installer.py` 驗證發佈管道未壞

### 4.4 修改影響半徑

| 改動位置 | 部署管道風險 | 影響範圍 | 必跑驗證 |
|---|---|---|---|
| `template/integrated/ALL_IN_RULE.md` | 無（手動） | 願意重新複製給通用 LLM 工具的使用者（Kilo / Claude Code / Cursor / OpenCode 等） | 自我審查單檔可讀性 |
| `template/modular/SOUL.md` | 中（merge 邏輯複雜） | 所有 openclaw / hermes agent | `test_installer.py::test_merge_soul_content` |
| `template/modular/RULE.md` | 高（直接覆蓋） | 所有 openclaw / hermes agent | `test_installer.py` 全套 + 對下游 agent 抽樣 |
| `template/modular/SKILL.md` | 高（直接覆蓋） | 所有 openclaw / hermes agent | `test_installer.py` 全套 + 對下游 agent 抽樣 |
| `installer.py` 本身 | 極高 | openclaw / hermes 的整個發佈管道 | `test_installer.py` 全套必跑 |

---

## 5. 判斷小測驗

當你不確定面對的是哪個套餐時，跑以下命令：

```bash
ls -la template/integrated template/modular
```

然後問自己：

1. **這個路徑下有幾個檔案？**
   - 1 個 → integrated
   - 3 個 → modular
2. **grep `installer.py`**：是否出現這個檔案的路徑？
   - 出現 → modular 套餐
   - 不出現 → integrated 套餐（或兩者皆有）

---

## 6. 變更歷史

| 日期 | 異動 | 觸發原因 |
|---|---|---|
| 2026-07-02 | 新建本文件 | 用戶明示「ALL_IN_RULE 與 RULE/SKILL/SOUL 是獨立套餐」，需防止後續混淆 |
| 2026-07-02 | 同日將 4 個檔案從 `template/` 根目錄遷移至 `template/integrated/` 與 `template/modular/` 子目錄 | 同上 |
| 2026-07-02 | 同步更新 `installer.py` 第 11-13 行的路徑常數 | 安裝腳本不能引用失效路徑 |
| 2026-07-02 | 補增 §2.1「部署機制」表 | 用戶進一步明示：integrated = 手動安裝；modular = 腳本（installer.py）安裝 |
| 2026-07-02 | 補增 §4.4「修改影響半徑」表 | 凸顯兩套餐的 deploy blast radius 差異，避免未來誤判改動風險 |
| 2026-07-02 | 精確化「適用場景」「適用客群」並新增 §2.2「部署目標對照」表 | 用戶明示「`template/modular` 專為 openclaw/hermes；其他 tool 用 `template/integrated/ALL_IN_RULE.md`」——這是兩套餐分流的核心鐵律 |
