# SWDD Output Schema Contract v1.0

> **用途**：本檔為 `template/integrated/ALL_IN_RULE.md` §0 條目 2（XML 標籤強邊界）的**可審閱 / subagent 可載入契約**。SOUL 在每次大版本變更時必須同步更新本檔。
> **生效日**：2026-07-02
> **版本**：v1.0

---

## 1. 全局強制（Global Constraints）

所有 subagent 與 SOUL 的輸出**必須**同時滿足以下三項：

1. **第一個非空字元**必須是某個允許的根標籤。
2. 根標籤**閉合後**，必須緊接一行 `[NEXT_STATE: PHASE_NAME | Zero-Chat Contract Active]`（無空行、無前後綴）。
3. 標籤外**任何字元**（包括空格、換行、Markdown 反引號、表情符號等）皆屬違規。

違規輸出將被 `§4.5 Action Realization Layer` 的後置 XML 攔截機制捕獲並要求 1 輪內 canonicalization 自我修正。

---

## 2. 允許的根標籤（Allowed Root Tags）

對應 `ALL_IN_RULE.md` §5 的六個 FSM Hook：

| 根標籤 | 對應 Hook | 觸發時機 |
|---|---|---|
| `<INTENT_GATE_RESULT>` | `[INTENT_GATE]` | 接收新任務時 |
| `<DESTRUCT_RESULT>` | `[PHASE_1_DESTRUCT]` | 使用 Swarm 時 |
| `<GATHER_RESULT>` | `[PHASE_2_GATHER]` | Destruct 完成後 |
| `<HYPERPLAN_RESULT>` | `[PHASE_3_HYPERPLAN]` | Gather 完成後 |
| `<SYSTEM_SPECIFICATION>` | `[PHASE_4_SYNTHESIS]` | Crucible PASSED 後 |
| `<TASK_SUMMARY_REPORT>` | （收束） | Dynamic_Compile 結束時 |

### 2.1 階段性內嵌標籤（非根標籤，可出現在 root tag 內）

- `<GATHER_CONSOLIDATION>`：Phase 6 內部使用
- `<DYNAMIC_COMPILE_RESULT>`：Phase 6 內部使用
- `<CLAUDE_REVIEW_RESULT>`：Phase 6 內部使用
- `<ACTION_REALIZATION_BLOCK>`：§4.5 subagent 上游攔截使用

---

## 3. 違規處置（Violation Handling）

| 違規類型 | 處置 |
|---|---|
| 標籤外有非空字元 | 後置 Action Realization 攔截 → 回傳錯誤訊息要求自我修正 |
| 缺少 `[NEXT_STATE: ...]` 宣告 | 同上 |
| 使用未列出的根標籤 | 同上 |
| 連續 2 次違規未修正 | 觸發 §7.0 Repetition 分類 → 角色切換至 Debugger |

---

## 4. 維護守則

- 版本升級時，**先更新本檔**再同步 `ALL_IN_RULE.md` 的條目 6 引用。
- 若增刪根標籤，必須同時更新本檔 §2 與 `ALL_IN_RULE.md` §5 Hook 列表。
- 本檔**不**屬於 installer.py 部署範圍（與 `template/modular/` 同源但不綁定）。
