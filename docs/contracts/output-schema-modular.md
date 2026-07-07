# SWDD Modular Output Schema Contract v1.1

> **用途**：本檔為 `template/modular/RULE.md` §0 條目 2（XML 標籤強邊界）的**可審閱 / subagent 可載入契約**，專供 **openclaw / hermes agent runtime** 使用。SOUL 應在每次大版本變更時同步更新本檔，並與 `SOUL.md` 的 sda-begin/end 標記區塊保持版本一致。
> **生效日**：2026-07-07
> **版本**：v1.1
> **與 integrated 套餐的關係**：本檔為 modular 套餐專屬，**不與 `output-schema.md`（integrated）共用**。兩者根標籤名稱雖部分重疊，但 §2 內嵌指令語法不同。

---

## 1. 全局強制（Global Constraints）

所有 subagent 與 SOUL 的輸出**必須**同時滿足以下三項：

1. **第一個非空字元**必須是某個允許的根標籤。
2. 根標籤**閉合後**，必須緊接一行 `[NEXT_STATE: PHASE_NAME | Zero-Chat Contract Active]`（無空行、無前後綴）。`PHASE_NAME` 採用 §0 條目 4 定義的方括號形式（例：`[PHASE_3_HYPERPLAN]`）。
3. 標籤外**任何字元**（包括空格、換行、Markdown 反引號、表情符號）皆屬違規。

違規輸出將被 `§4.5 Action Realization Layer` 的後置 XML 攔截機制捕獲並要求 1 輪內 canonicalization 自我修正。

---

## 2. 允許的根標籤（Allowed Root Tags）

對應 `modular/RULE.md` §5 的六個 FSM Hook：

| 根標籤 | 對應 Hook | 觸發時機 |
|---|---|---|
| `<INTENT_GATE_RESULT>` | `[INTENT_GATE]` | 接收新任務時 |
| `<DESTRUCT_RESULT>` | `[PHASE_1_DESTRUCT]` | USE_SWARM_WORKFLOW=True 時 |
| `<GATHER_RESULT>` | `[PHASE_2_GATHER]` | Destruct 完成後 |
| `<HYPERPLAN_RESULT>` | `[PHASE_3_HYPERPLAN]` | Gather 完成後 |
| `<SYSTEM_SPECIFICATION>` | `[PHASE_4_SYNTHESIS]` | Crucible PASSED 後 |
| `<TASK_SUMMARY_REPORT>` | （收束） | Dynamic_Compile 結束時 |

### 2.1 階段性內嵌標籤（非根標籤，可出現在 root tag 內）

| 內嵌標籤 | 出現位置 | 用途 |
|---|---|---|
| `<GATHER_CONSOLIDATION>` | §5 Hook 6 內部 | 多 subagent 情報彙整 |
| `<DYNAMIC_COMPILE_RESULT>` | §5 Hook 6 內部 | 開發 subagent 物理執行指令容器（含 `COMMAND_EXECUTE_START/END` 標記） |
| `<CLAUDE_REVIEW_RESULT>` | §5 Hook 6 內部 | 審查 subagent 結果（含 `REVIEW_STATUS` / `REVIEWS_FEEDBACK` 兩鍵） |
| `<ACTION_REALIZATION_BLOCK>` | §4.5 上游攔截 | Task Dispatch Validator 拒絕任務時的封裝 |

### 2.2 modular 特有的子指令區塊（**與 integrated 不同**）

`<DYNAMIC_COMPILE_RESULT>` 在 modular 中必須包含**物理執行邊界標記**：

```xml
<DYNAMIC_COMPILE_RESULT>
COMMAND_EXECUTE_START
[實體 subagent 指令]
COMMAND_EXECUTE_END
</DYNAMIC_COMPILE_RESULT>
```

→ 缺少任一標記視為格式毀損，必須 canonicalization 修正。

---

## 3. 違規處置（Violation Handling）

| 違規類型 | 處置 |
|---|---|
| 標籤外有非空字元 | 後置 Action Realization 攔截 → 回傳錯誤訊息要求自我修正 |
| 缺少 `[NEXT_STATE: ...]` 宣告 | 同上 |
| 使用未列出的根標籤 | 同上 |
| 缺少 `COMMAND_EXECUTE_START/END` 邊界 | 同上（modular 專屬） |
| 連續 2 次違規未修正 | 觸發 §7.0 Repetition 分類 → 角色切換至 Debugger |
| 對 §4 Firewall 違規 | 透過 `http://localhost:9720` 提請物理確認（modular 專屬） |

---

## 4. 與 SOUL.md sda 標記的同步協議

`SOUL.md` 內含 `<!-- sda-begin -->` 與 `<!-- sda-end -->` 區塊，由 `installer.py merge_soul_content` 函式處理。若本契約檔變更，**必須**：

1. 更新本檔版本號（§ 抬頭）
2. 更新 `SOUL.md` 的 sda 區塊以反映契約版本差異
3. 同步更新 `installer.py` 的 `extract_version` 邏輯（若版本命名格式變更）

→ 跳過任一步驟會導致 `installer.py` 對 SOUL.md 的 merge 結果與 RULE.md 期望不一致。

---

## 5. 維護守則

- 版本升級時，**先更新本檔**再同步 `RULE.md` 的 §0 条目 6 引用。
- 若增刪根標籤，必須同時更新本檔 §2 與 `RULE.md` §5 Hook 列表。
- 本檔**屬於** installer.py 部署範圍的對應文件（與 `template/modular/RULE.md` 同步），但 installer.py 自身**不讀取**本檔；同步由 repo 內的 git 操作保證。