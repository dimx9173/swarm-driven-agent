# Release & Version Bump Process

> 本文件定義 SWDA 專案的版本 bump 與 release 標準流程。

---

## 版本號規範

| 層級 | 檔案 | 版本格式 | 說明 |
|---|---|---|---|
| **Python Package** | `setup.py` | `X.Y.Z` (e.g. `2.4.0`) | pip 安裝版本 |
| **Integrated Contract** | `template/integrated/ALL_IN_RULE.md` | `X.Y.Z-deterministic` | 對外一致性版本 |
| **Integrated Contract (EN)** | `template/integrated/ALL_IN_RULE.en.md` | `X.Y.Z-deterministic` | 英文版 |
| **Output Schema** | `docs/contracts/output-schema.md` | `vX.Y.Z` | 同步版本 |
| **Modular Contract** | `template/modular/RULE.md` | `X.Y.Z-engineering-hardened` | Modular 模板版本 |
| **Modular Contract (EN)** | `template/modular/RULE.en.md` | `X.Y.Z-engineering-hardened` | Modular 英文版 |
| **Modular Output Schema** | `docs/contracts/output-schema-modular.md` | `vX.Y.Z` | 同步版本 |

---

## Bump & Release 標準流程

### 事前檢查清單

```bash
# 1. 確認当前版本
git tag --sort=-v:refname | head -1
# 或
git describe --tags --exact-match

# 2. 確認所有變更已 commit
git status
```

### Step 1: 版本文件全量檢查（強制步驟）

每次 release 前，**必須**搜尋並檢查**所有**含有版本號的檔案。嚴禁只修改單一檔案而忽略其餘。

```bash
# 搜尋所有版本標記（勿省略任何一個）
grep -rn "v[0-9]\.[0-9]" --include="*.md" .
grep -rn "version:" --include="*.md" .
grep -rn "version=" --include="*.py" .
```

**每次 release 必須檢查的全部版本標記位置：**

| 檔案 | 位置 | 版本格式 |
|---|---|---|
| `setup.py` | `version="X.Y.Z"` | `X.Y.Z` |
| `docs/contracts/output-schema.md` | 抬頭 `vX.Y.Z` + 內文同步標記 | `vX.Y.Z` |
| `template/integrated/ALL_IN_RULE.md` | YAML frontmatter `version:` | `X.Y.Z-deterministic` |
| `template/integrated/ALL_IN_RULE.en.md` | YAML frontmatter `version:` | `X.Y.Z-deterministic` |
| `docs/contracts/output-schema-modular.md` | 抬頭 `vX.Y.Z` + 內文同步標記 | `vX.Y.Z` |
| `template/modular/RULE.md` | YAML frontmatter `version:` | `X.Y.Z-engineering-hardened` |
| `template/modular/RULE.en.md` | YAML frontmatter `version:` | `X.Y.Z-engineering-hardened` |

### Step 2: 決定版本層級

| 變更類型 | 版本遞增 |
|---|---|
| 新增 FSM 狀態、意圖分類、執行軌道等結構性變更 | **Major** (X+1.0.0) |
| 新增可選欄位、註解強化、非破壞性相容改動 | Minor (0.X.0) |
| 文件勘誤、格式修正、測試補充 | Patch (0.0.X) |

### Step 3: 執行 Bump

```bash
# 一次性修改所有版本（以 2.5.0 為例）
NEW_VERSION="2.5.0"

# setup.py
sed -i '' "s/version=\"[0-9.]*\"/version=\"$NEW_VERSION\"/" setup.py

# output-schema.md / output-schema-modular.md（兩處：抬頭 + 內文 vX.Y.Z）
sed -i '' "s/v[0-9]\.[0-9]\.[0-9]/v$NEW_VERSION/g" \
    docs/contracts/output-schema.md \
    docs/contracts/output-schema-modular.md

# integrated deterministic 版本
NEW_DET_VERSION="14.2.0-deterministic"  # 視本次變動範圍調整
sed -i '' "s/version: [0-9]*\.[0-9]*\.[0-9]*-deterministic/version: $NEW_DET_VERSION/" \
    template/integrated/ALL_IN_RULE.md \
    template/integrated/ALL_IN_RULE.en.md

# modular engineering-hardened 版本
NEW_MOD_VERSION="2.11.0-engineering-hardened"  # 視本次變動範圍調整
sed -i '' "s/version: [0-9]*\.[0-9]*\.[0-9]*-engineering-hardened/version: $NEW_MOD_VERSION/" \
    template/modular/RULE.md \
    template/modular/RULE.en.md
```

### Step 4: Commit, Tag, Push

```bash
git add -A
git commit -m "Release v$NEW_VERSION: <一句话英文摘要>"
git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION: <一句话英文摘要>"
git push origin master
git push origin "v$NEW_VERSION"
```

### Step 5: 驗證

```bash
git log --oneline -3
git describe --tags --exact-match
```

---

## 常見錯誤

### 忘記 bump 文件版本
> 文件版本落後於 package 版本，導致 agent 讀到過時的 FSM 結構定義。

**解決**：每次 `setup.py` version 改動時，**強制**搜尋 `grep -rn "v[0-9]\.[0-9]" docs/ template/` 並同步更新。

### force push 已發布的 tag
> 團隊成員的 local tag 與遠端不一致。

**預防**：tag push 前先 `git tag -d <tag> && git fetch --tags`，或使用 `git push origin <tag>` 而非 `git push --tags`。

### 版本號對應關係錯誤
> output-schema.md 的版本需與 ALL_IN_RULE.md 的 deterministic 版本對應；output-schema-modular.md 的版本需與 modular/RULE.md 的 engineering-hardened 版本對應。

**版本對應表（Integrated 套餐）：**
| output-schema.md | ALL_IN_RULE.md |
|---|---|
| v1.4.0 | v14.1.0-deterministic |
| v1.3.2 | v14.0.0-deterministic |

**版本對應表（Modular 套餐）：**
| output-schema-modular.md | modular/RULE.md |
|---|---|
| v1.4.0 | v2.10.0-engineering-hardened |
| v1.3.2 | v2.9.0-engineering-hardened |

---

## 範例對照表

### v2.4.0 Release（Integrated 套餐結構性變更）
```
setup.py:                              1.7.0  →  2.4.0
docs/contracts/output-schema.md:        v1.3.1 → v1.4.0
template/integrated/ALL_IN_RULE.md:   14.0.0-deterministic → 14.1.0-deterministic
template/integrated/ALL_IN_RULE.en.md: 14.0.0-deterministic → 14.1.0-deterministic
```

### v2.4.1 Release（Modular 套餐結構性變更）
```
docs/contracts/output-schema-modular.md: v1.3.2 → v1.4.0
template/modular/RULE.md:               2.9.0-engineering-hardened → 2.10.0-engineering-hardened
template/modular/RULE.en.md:           2.9.0-engineering-hardened → 2.10.0-engineering-hardened
```
