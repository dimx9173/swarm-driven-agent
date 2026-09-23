# TypeSafe Jev（System One Model）特色与能力分析

> 研究日期：2026-09-23；对象：TypeSafe AI 首个 System One 模型 **Jev**（2026-09-15 官方发布，early access）
> 主要一手来源：TypeSafe 官方博客 + 官方 Docs；二手仅作补充。

## 1. 一句话定位

Jev 不是聊天 LLM，而是一个**面向软件直接消费的结构化决策模型**：非结构化 state 进，类型安全的概率化决策出。官方表述为 "frontier-intelligence function call: unstructured state in, typed probabilistic decisions out"。

- 创始人 Diogo Almeida（前 OpenAI 研究员，ChatGPT 背后 RLHF 方法贡献者之一），创业动因是 "LLM 擅长 chat，但 automation 没来"。
- 命名：System One 取自 Kahneman《Thinking, Fast and Slow》System 1（快直觉）；Jev 取自 William Stanley Jevons（Jevons 悖论：效率提升带来需求爆发）。

来源：https://typesafe.ai/blog/introducing-system-one-models-and-jev

## 2. 核心特色

### 2.1 不生成字符串，只返回类型安全结构值
- LLM 输出 strings（chat、代码、幻觉、拒答、结构化值混杂），需解析 + 校验，仍有脱轨风险。
- Jev 输出在调用前已定义 schema，**数学上不可能出现 type error**，也不会幻觉出未定义选项。官方称这是 automation 的 table stakes。
- 单次请求可混合多种 question，并行、隔离地对同一 state 求值，加 question 几乎不增加延迟、不产生 context-rot。

来源：官方博客对照表；https://docs.typesafe.ai/introduction

### 2.2 三个 AI primitives（question 类型）
| 类型 | 语义 | 返回 |
|---|---|---|
| Choice | 从列表选一项（分类/路由/分支） | `choice` + `probabilities` + `confidence` |
| Score | 按 rubric 打分 | `score` + `probabilities` + `confidence` |
| Noul | 该陈述为真吗？ | `noul`（0–1） |

设计建议：问原子化小问题（gut-check），复杂判断拆成多个 question 再用代码里的公式/逻辑组合权重，而非写大 prompt。

来源：https://docs.typesafe.ai/introduction

### 2.3 校准的置信度（calibrated confidence）
- 每次输出自带概率分布 + confidence。Higher confidence = higher accuracy，且相似输入返回相似答案（一致性）。
- 对比：LLM 即使被要求给 confidence 也常过度自信、不一致；若模型 95% 能做对但说不清 5% 在哪，就无法自动化。
- 工程用法：代码按 confidence 决定是否行动、走哪条分支、是否转人工。

来源：官方博客对照表 Confidence 行；https://docs.typesafe.ai/introduction ；概念页 /confidence

### 2.4 并行采样 + 全新训练方法 RLCD
- 架构：new model architecture + parallel sampler（hardware-aware），一次 query 并行产出全部输出，而非逐 token 自回归。
- 训练：Reinforcement Learning for Calibrated Decisions（RLCD）。对照：
  - RLHF：优化人类偏好（chat/writeup 好看）。
  - RLVR：优化可验证奖励（数学证明、kernel 优化等可自动校验场景）。
  - RLCD：优化 System One 任务上的**认识论诚实的概率**（epistemically honest probabilities）。
- 官方未公开架构细节。第三方解读：RLCD 是 RLHF 的替代路线，不优化"让人喜欢"，而优化"概率诚实"。

来源：官方博客；https://www.mindstudio.ai/blog/typesafe-jev-rlcd-vs-rlhf ；https://explainx.ai/blog/how-does-jev-work-rlcd-system-one-model-explained-2026

## 3. 性能与成本（官方 claim + nuance）

| 维度 | LLM（官方写法） | Jev（官方 claim） |
|---|---|---|
| 速度 | 端到端 3–329s（frontier） | **70ms–500ms**，同等 System One 智能下 40x–200x 更快；workflow eval 口径 193.6x |
| 成本 | 输入 $0.20–$10 / MTok，输出约输入 5x | 输入 **$0.042 / MTok**，输出免费（too cheap to meter）；workflow 口径 444.6x 更便宜 |
| 类型错误/幻觉 | 始终存在风险 | schema 保证 0%，数学不可能 |

官方自带的 nuance（必须一起读）：
- 速度/成本 eval 在团队西海岸 laptop 上跑；成本是否补贴需长期验证，但预期降价而非涨价。
- 193.6x / 444.6x 来自自家 4 个 production-like workflow eval，参考答案是 GPT-6 Astra + Fable 5.1 的平均（偏向 OpenAI/Anthropic，被测方用 System One adapter wrapper 约束 LLM 输出结构化决策——该 wrapper 更准但更慢更贵）。
- Workflow 内容非训练分布，但出自自家 capabilities team，可能存在 bias。
- Hallucination 0% 非实证，是 schema 保证；LLM 侧数字来自 OpenRouter，可能有路由 bias。
- Side-by-side demo 刻意用短 dense state + 人可读 key，突出并行采样优势；与 GPT-5.6 Terra（default reasoning）对比，仅 Churn likelihood 一处分歧。

来源：官方博客 Evidence 章节；https://evals.typesafe.ai/ ；https://www.marktechpost.com/2026/09/19/typesafe-ai-releases-jev

## 4. 能力边界：擅长 vs 不擅长

擅长（官方推荐）：
- AI-Powered Workflows / smart if-statements：classify、route、score、extract、branch，替代手写 brittle 规则。
- Map-reduce over big data：PB 级数据转特征/洞察。
- Realtime：100ms 级，UX 敏感路径。
- Verify everything：给 LLM prompt/推理轨迹/输出打分、做 judge、guardrail、jailbreak 检测。

不擅长 / 放弃的能力：
- 不做开放式文本生成（give up string generation），无 chat/copilot/写代码 agent 式用途。
- 需要长链条深思熟虑推理的大问题，应拆成原子 question + 代码组合，而非指望单次深推理。
- Cardinality 上限 255，高基数 Choice 用两阶段（先独立打分再显式选择），偶发慢。
- Doom demo 是结构化 state（文本数据结构）而非图像；Wikiracing 对比的是 LLM 非推理/最低推理档，全推理档差距会缩小。

来源：官方博客 Use cases + Fun Demos nuance

## 5. API 心智模型

- 一个 endpoint 处理一切：`state`（非结构化程序状态，强调 structured program state 而非 sequential messages）+ `questions` 数组 → 一次返回全部 typed answers + probabilities + confidence。
- 官方提供 System One LLM adapter（https://github.com/typesafe-ai/system-one-adapter-python），把 LLM 约束成兼容接口，用于对照评测与迁移。
- Playground 有可分享的 side-by-side query（console.typesafe.ai/playground?share=...）。

## 6. 结论与风险提示

- Jev 的真正创新不是"更聪明的 chat"，而是**接口范式切换**：把 AI 变成软件可依赖的 typed function call，用 RLCD + 并行采样换速度、成本、可组合性。
- 采用前必做：拿自己的 workflow 跑 evals.typesafe.ai 同款方法复测，用自家数据验证校准度（calibration curve），不要只看 193x/444x headline。
- 当前状态 early access，需排 waitlist；长期价格可持续性官方自己也承认待证明。
- 第三方曾有人用 Qwen2.5 数小时复刻出部分 structured-decision 特性（Medium 帖），说明"结构化决策"本身可模仿，Jev 壁垒在校准质量 + 延迟/成本 Pareto，而非概念不可复制。

## 7. 实战参考：jev-use（第三方 Agent 集成）

开源仓库 https://github.com/shitianfang/jev-use （MIT，JS，v0.8+）：Claude Code / Codex / pi 插件 + npm 库 + MCP server（两个工具 `jev_judge` / `jev_gate`），把"无需产出文本的 agent 步骤"交给 Jev，LLM 退为 planner/writer。实测口径 p50 ~230ms、约 $0.02/千次判断。

### 7.1 库用法（trio API 对照官方三个 primitives）
```js
import { Jev, check, pick, rate } from "jev-use";
const { answers } = await jev.judge(state, {
  next:   pick("Next action?", { merge: "...", rerun: "...", hold: "..." }),  // Choice
  risk:   rate("How risky?", ["routine", "worth a look", "incident"]),        // Score
  passed: check("Did the run fully succeed?"),                                // Noul (0–1)
});
// answers.next → { answer: "merge", confidence: 0.93, confidenceFrom: "reported", escalate: false }
```

### 7.2 路由规则（其 SKILL.md 核心："facts 在哪 × 是否阻塞"）
| facts 位置 | 不阻塞（可继续干活） | 阻塞（必须先定才能继续） |
|---|---|---|
| 已在上下文 | `jev_judge`，围绕同一 state 的全部问题**合并一次调用**（实测 12 问一批 224ms vs 逐个 2662ms，12 倍） | `jev_gate` 判断该动作；若拦每个 tool call，装成 PreToolUse hook 一次搞定（24 条命令 17.1s、**0 LLM token**，对照 supervisor LLM 46.9s / $0.2366） |
| 在文件/工具输出里 | 脚本 pipe 给 `jev-use judge` CLI——数据根本不进对话 | 同 CLI，按其打印的 verdict 行动 |
| 需要你新写（文本/代码/无法枚举的选项） | LLM 自己来 | LLM 自己来 |
原则：state 即全部上下文（把相关事实塞进 state）；别路由鸡毛小事；尊重 `escalate:true` 回递（`writing`/`open_ended`=结构上归你、`oversized`=state 太大、`unsure`=答案只是先验仍可用作 hint、`unreachable`=当 Jev 不存在照常走）。

### 7.3 实测数据（2026-09-19，自家 bench，-- 全部一手测量并附 caveat）
- 单判断 30 连呼 p50 223ms / p95 364ms；gate 6 safe + 6 dangerous 12/12 正确。
- 命令门控（PreToolUse hook）vs supervisor LLM 同 24 命令：17.1s/0 token/$0.0000194 per decision vs 47s/93 万 token（98.7% 是 cache read）/$0.009857 —— **510x 便宜**；代价差异：supervisor 24/24 全对，hook 23/24（同一个 `sed -i` 边界案例）。
- 校准发现（重要）：vendor 报的 confidence head **对 choice 就是分布 margin 的重缩放**（残差 ≤0.015），非独立信号；score 多级时 head 无法从分布还原（107 例中 40 例高于 top 概率）。Vercel 网关转发 head，`noul/boolean` 无 head（0/24）。门槛取 reported@0.5 / estimated@0.4；0.75 会把升级率推到 39% 而准确率无增益。
- 总体命中率：454 判定 82.2% 与参考（claude-opus-5）一致；其中未升级的 89.5%，被升级的若是自己答只有 51% 会对 —— **escalation 在干真活**。分 族：completion 100%、HN 94.2%、gate 80.9%（危险命令 0 漏放，错误全是过度拒绝）、triage 76.6%（误差 ±1 级内）、**context 压缩 keep/drop 只有 56.3%（低于多数类基线）** —— 规则在你脑子里不在 state 里时不要交给 Jev。
- 公平对照前必须重新定义基线：pony headline "86 decisions/20s vs 6 (haiku)" 是裸调口径；enum+关思考后差距只有 **3x**，存活的优势是 16x 成本 + 答案 in-set by construction；质量本回合计 24–30/40 五臂打平，且发现 Jev 在 80 次里 0 次选过 `stay`（从未见过的选项=静默失败，需查答案分布不看仅准确率）。
- 高基数（>25 选项）margin 只有 0.02–0.08，几乎全 `unsure`；gate 结论依赖 state（`JEV_GATE_STATE` 加一句"环境里有生产凭据"就把 `git add -A` 从静默放行变成 ask）；redact 移除密钥后，`curl -H Authorization GET /v1/health` 从 deny 0.73-0.80 翻为 allow/ask —— gate 审的是**动作**不是 shell 卫生；空输出/静默成功打分不果断（0.74 vs 显式绿色的 0.97–0.99）。

### 7.4 对采用者的教训（该库明确写出的反直觉点）
1. Jev 是 **rate win 不是 token win**：单次决策 token 花得更多，省钱前提是判定**不进对话**（走 CLI/管道/hook，让数据绕过上下文）。
2. 批处理的收益是 12x 级别，一个 state 的所有问题必入一呼。
3. 阈值必须自调：作者自己的 8/8 clear-vs-borderline 校准实验都没分开，`unsure` 只是粗信号。
4. 答案分布要审（静默没选出正确项的情形真实存在）。
5. 摘要/聚合产出（如压缩摘要"216 tests"把真实 58 写错）——凡是涉及生成新文本的残留步骤仍然会在 LLM 端出错。

来源：仓库 README / bench/RESULTS.md / skills/jev-use/SKILL.md / src/judge.ts

## 来源清单
1. TypeSafe 官方发布：https://typesafe.ai/blog/introducing-system-one-models-and-jev
2. TypeSafe Docs Introduction：https://docs.typesafe.ai/introduction （完整索引 https://docs.typesafe.ai/llms.txt）
3. Workflow evals 站：https://evals.typesafe.ai/
4. RLCD vs RLHF 解读：https://www.mindstudio.ai/blog/typesafe-jev-rlcd-vs-rlhf
5. 架构解读：https://explainx.ai/blog/how-does-jev-work-rlcd-system-one-model-explained-2026
6. MarkTechPost 发布报道：https://www.marktechpost.com/2026/09/19/typesafe-ai-releases-jev
7. Beam.ai 速览：https://beam.ai/agentic-insights/jev-typesafe-ai-agents
8. MindStudio 发布解读：https://www.mindstudio.ai/blog/jev-system-one-model-launch
9. jev-use（第三方 Agent 集成实测）：https://github.com/shitianfang/jev-use

## 8. SWDA × Jev 搭配討論（Kimi / Codex 雙視角合成，2026-09-23）

草案 v0 六接點經 Kimi（工程落地）與 Codex（架構/FSM）背靠背評審；雙方 verdict 均為「方向可行、需修正」，合成如下。

### 8.1 雙方一致認可（直接可做）
| 接點 | SWDA 落點 | 形式 |
|---|---|---|
| 防火牆預檢 | `swda/core/hooks.py` PreToolUse hook | Jev Choice(allow/deny) **只能 add deny/ask，永不能 allow 放行**；最終執行權在 `firewall.py` `audit_command` 硬規則（官方自陳 "best-effort, not a security boundary"，Jev 為第二層概率網） |
| INTENT_GATE 預分類 | `fsm.py` INTENT_GATE（budget=1） | Choice 6 類 + 顯式 unsure 桶；只控制資源檔位（`rlm.py` CATEGORY_ROLES），不控制安全路徑 |
| 修 N 次仍紅→HITL | PHASE_6 IMPLEMENT（budget=5） | Jev 只判「再試 or 升級」，lint/typecheck 保持 deterministic |

### 8.2 需修正後才能做
1. **批量規則改寫**（Kimi Major）：「所有呼叫走批量」與 PreToolUse 逐事件模式矛盾（hook 每命令一呼，~712ms/條在關鍵路徑）。改為「同 state 多 question 才批量」：INTENT_GATE 分類 + 歧義偵測共用同一 state 合一批；gate 標記逐事件 + timeout + 現成 `circuit_breaker.py` StepCounter 綁定 + 逾時降級（Jev 掛了只走 deterministic firewall）。
2. **Socratic grilling 門控不依賴 noul**（Kimi Critical）：Vercel 網關 noul/boolean head 0/24 缺失（訊號不存在，非準確率問題）；且 context 族 56.3% 低於基線。改用 Choice 雙選（需追問/不需追問）+ unsure 回遞 LLM；或僅 TypeSafe 直連啟用。FSM 無需自環（Codex 指控過度）：grilling 迭代發生在 PHASE_2 phase 內、受 StepCounter budget=3 約束，不觸發 `VALID_TRANSITIONS`；若 Jev 驅動的追問需要更多步，調 budget 而非改 DAG。
3. **Referee 第二意見縮為 binary**（雙方合流）：`crucible.py:203-231` `_parse_verdict` 只認 `{passed, score, reason, round}`，需加可選欄位 `jev_score/jev_confidence`；choice head=margin 重縮放非獨立訊號、score 多級 37% 給矛盾訊號 →仲裁協議定為「**Jev 與 LLM 一致→採信省成本；不一致→一律 LLM 複審**」，並只問 binary pass/fail（回避多級 head 不可還原）。
4. **衛生處理順序**（Kimi Major）：redact 會翻轉 verdict（deny 0.73→allow 0.51）。管線定序：原始命令先過 Jev gate；redact 只作用於 LLM 可見內容，不作用於 gate 輸入；secret/exfil 偵測維持 `BLOCKED_PATTERNS` deterministic scanner。

### 8.3 前置條件（不滿足就不要接）
- **網關能力探針**：head 到達率因 provider 而異（Vercel 轉發 choice/score、丟 noul；OpenRouter 未測），切網關=重探針+重標定。
- **閾值方法論**：每 call site 50-200 例真實流量標註集，guard metrics（升級率 ≤15%、危險命令漏放=0）下調參；起點 reported@0.5/estimated@0.4，0.75 已證偽。
- **成本核帳**：per-session 預算模型（state 序列化 token 也在帳上），對標 haiku-strict（公平基線僅 3x 延遲、16x 成本差，510x 是 strawman 口徑）；Jev 不贏就不接該 call site。

### 8.4 評審來源
- Codex 視角（FSM/verdict 解析/防火牆分層）：local://codex-discuss.md（final text 併入本節）
- Kimi 視角（網關 head/批量/redact/閾值）：local://kimi-discuss.md

## 9. 已落地實作（PRPCC: opencode plan → claude code → codex review）

依 §8 結論實作，程式碼在 `swda/prime/jev.py`、`swda/workflows/crucible.py`、`tests/test_jev.py`（38 測試；全套 255 tests OK）。

### 9.1 啟用與 URL/模型自訂（全部可用環境變數覆寫）
啟用條件：任一 key 存在即自動啟用；全無則零行為變化（`is_enabled()==False` → `judge()` 回 `{}`、hook 回 `None`、arbitration 跳過）。

| 變數 | 作用 |
|---|---|
| `JEV_API_KEY` | 完全自訂端點（優先級最高，搭配下面三項） |
| `JEV_BASE_URL` | 覆寫所選 provider 的 base URL |
| `JEV_MODEL` | 覆寫模型 id |
| `JEV_JUDGE_PATH` | 請求路徑（預設 `/v1/judge`） |
| `TYPESAFE_API_KEY` / `TYPESAFE_BASE_URL` / `TYPESAFE_MODEL` | TypeSafe 直連（預設 `https://api.typesafe.ai`, `jev-1.13`） |
| `OPENROUTER_API_KEY` / `OPENROUTER_BASE_URL` / `OPENROUTER_MODEL` | OpenRouter（預設 `https://openrouter.ai/api/v1`, `typesafe/jev-1.13`） |
| `AI_GATEWAY_API_KEY` / `AI_GATEWAY_BASE_URL` / `AI_GATEWAY_MODEL` | Vercel AI Gateway（預設 `https://ai-gateway.vercel.sh/v1`, `typesafe-ai/jev`） |
| `JEV_CONFIDENCE_THRESHOLD` | 信心門檻（預設 0.5） |

範例：
```bash
# 自架 / 代理端點
export JEV_API_KEY=... JEV_BASE_URL=https://jev.internal.example.com JEV_MODEL=jev-1.13
# 或只換某 provider 的 URL
export AI_GATEWAY_API_KEY=... AI_GATEWAY_BASE_URL=https://gw.internal/v1
```

### 9.2 三個接點與接線現況（PRPCC 第二輪後更新）
- **PreToolUse gate**（`jev_pre_tool_hook`）：deny-only，回 `None` 或 `{'decision':'block',...}`，永不放行；gates `bash/shell/repl/execute/tdd/run_tests`。**已接線**：`swda run --jev-gate` 與 `swda repl --jev-gate` 旗標掛上 HookRegistry 綁定執行路徑（run 經 `tdd_runner.set_default_hooks`，repl 經 `PrimeREPL(hooks=...)`）。
- **Crucible 第二意見**（`_arbitrate_verdict`）：只在 Jev 主動反對 LLM-passed verdict 時 fail-closed，寫入 `jev_score`（noul pass 機率）與 `jev_confidence`；LLM failed 保持 failed，Jev 不可達不改 verdict。**已接線**：`swda run` 的隱藏路徑，Jev key 存在即生效。
- **INTENT_GATE hint**（`intent_hint`）：**已接線**為 `swda jev-intent "<request>"` 子命令 — 回印分類字串 / `unsure` / `none`（無 key）。workflow pack（omp/pi/hermes/openclaw 的 intent 文件）已註明此為 optional hint。

⚠ 宿主注意：接點活在 **`swda` Python 套件**裡。hermes/openclaw（contract+skill，無 Python runtime 整合）需經 CLI bridge（`swda jev-intent`、`swda run --jev-gate`）使用；兩 host 的 skill 文件已同步記載。OMP/Pi 若未走 `swda run` 而是用 host 原生 subagent/命令流程，Crucible 第二意見同樣不會觸發 — 只有走 CLI `swda run` 才會。

### 9.3 PRPCC 證據鏈
- Stage 1（opencode/minimax）：`PLAN.md`（409 行，files/symbols + contract + out-of-scope + test commands）。
- Stage 2（claude/qwen3.8-flash）：落地三檔；orchestrator 修 3 處測試基建後 jev 34/34、全套 251 OK。
- Stage 3（codex review）：第 1 輪 FAIL（P1 crucible 未捕 `http.client.HTTPException`、P2 `tdd.run_tests` 逃過 gate、P3 dead fields）→ 修復後第 2 輪 PASS；再補 P2 `jev_score` 語意修正 + URL 自訂，最終 38 jev tests / 255 全套 OK。
