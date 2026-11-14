# Quant Super Agent — 可信量化研究闭环

> 论文标题: *Quant Super Agent: A Verifiable Agentic Quant Research Factory*
> 论文地址: [arXiv:2601.04736](https://arxiv.org/abs/2601.04736) · [github.com/0x1512/quant-super-agent](https://github.com/0x1512/quant-super-agent)
>
> **状态: v1.2 已交付**(证据平面 + 研究闭环 + 可消融角色 + 对抗辩论 + 结算账本与校准曲线 + FIB 注入基准 + 预算等式估计器 + **真实数据研报复现 v1.0** + **因子工厂快车道 v1.1** + **组织记忆层 v1.2:黑板/infra 门/订单状态机/fork 拍板卡**)。论文中的每一层能力在仓库里都有对应实现,且可离线复现。
>
> 本 README 是仓库导航与版本进度看板。论文的完整主张在 `docs/THESIS.md`(含对论文原文的逐条对照);架构在 `docs/ARCHITECTURE.md`;各版本的公开验收记录在 `docs/EVIDENCE.md`;FIB 场景与判定标准在 `docs/BENCHMARK.md` 与 `docs/RUBRICS.md`。

---

## 目录

- [仓库结构](#仓库结构)
- [快速开始](#快速开始)
- [能力地图与对应论文主张](#能力地图与对应论文主张)
- [设计不变量](#设计不变量)
- [路线图](#路线图)
- [引用](#引用)

---

## 仓库结构

```
quant-super-agent/
├── README.md                    # 本文件(导航 + 进度)
├── README.zh-CN.md              # 本文件中文版
├── pyproject.toml               # 依赖声明(运行期零第三方依赖;CI 矩阵 3.10–3.13)
├── qsa/                         # 核心包(零第三方依赖,纯标准库,确定性)
│   ├── registry.py              # 预注册登记簿:append-only 哈希链,拒绝后补登记/改历史
│   ├── sandbox.py               # 因子沙箱:AST 白名单,截断契约 v1/v2(无未来数据可看)
│   ├── engine.py                # 统一评估引擎:t-stat / IC / 分层 / 覆盖 / 换手 / 容量,全卡同口径
│   ├── metrics.py               # 指标实现(t 统计、滚动相关、滚动均值、分位数)
│   ├── evidence.py              # 证据卡:结构 + 数据指纹 + 哈希链
│   ├── verify.py                # 门禁:复算、schema、指纹、沙箱重放、账本对账、防篡改
│   ├── forge.py                 # 确定性数据锻造:种子世界 + 植入信号
│   ├── ledger.py                # 通用 append-only 哈希链账本(注册簿与结算共用)
│   ├── settlement.py            # 结算:固定 90 天视界,引擎重算,哈希链账本
│   ├── calibration.py           # 校准:声称 vs 兑现分箱,斜率/偏差/失准率,只紧不松反刍规则
│   ├── roles.py                 # 可消融角色(R1–R8):注册→假设→挖掘→证据→评审→辩论
│   ├── ablation.py              # 消融:角色关断、降级裁判、角色互换
│   ├── debate.py                # 结构化多空辩论 + 裁判裁决(纯规则版)
│   ├── fib.py                   # Fabrication Injection Benchmark:17 场景 × 2 基线 + 门禁,全确定性
│   ├── budget.py                # 预算读出:预算等式各项从管道状态机械读出(ĪC/B_eff/覆盖/TC/衰减)
│   ├── manifest.py              # 数据快照清单 + 指纹 + 校验
│   ├── ingest.py                # 离线 CSV → 快照(含 per_side_bps 成本模型)
│   ├── snapshot.py              # 快照加载、按种子/日期确定性续写、体积与成本
│   ├── mining.py                # 因子挖掘:种子候选、沙箱执行、去重、登记簿感知
│   ├── factorzoo.py             # v1.1 因子工厂:24 个公开文献模板因子,O(N) 滚动核,零依赖
│   ├── backtest.py              # v1.1 可交易性回测:费后/NW Sharpe(PSD 下限)/换手/容量/回撤/triple-gate
│   ├── replication.py           # v1.0 研报复现:口径表、双算对账、分歧归因、预注册判定
│   ├── blackboard.py            # v1.2 黑板:跨会话记忆,哈希链防篡改,blocker 拉闸
│   ├── orders.py                # v1.2 订单状态机:admit 冻结参数哈希,终态不可重启,事件哈希链
│   ├── infragate.py             # v1.2 infra 门(5 项离线预检) + fork 拍板卡(append-only)
│   └── cli.py                   # 命令行入口
├── examples/                    # 可运行示例 / 验收脚本(全部确定性,可当回归契约)
│   ├── run_evidence_plane.py    # v0.2 验收:证据卡 + 门禁
│   ├── run_research_loop.py     # v0.3 验收:闭环 + 多重检验
│   ├── run_roles.py             # v0.4 验收:角色 + 辩论 + 消融表
│   ├── run_settlement.py        # v0.5 验收:结算账本 + 校准曲线
│   ├── run_fib.py               # v0.6 验收:FIB 场景表 + 判定标准
│   ├── run_calibration.py       # v0.7 演示:52 笔结算 + 校准 + 预算等式各项读数
│   ├── run_discovery.py         # v0.7 演示:discovery@B 曲线 + 包线(广度净核查)
│   ├── run_frontier.py          # v0.7 演示:α-前沿(P̂)曲线 + 包线
│   ├── run_replication.py       # v1.0 研报复现端到端(真实钉死数据,诚实判定,双跑字节一致)
│   ├── run_factory.py           # v1.1 因子工厂快车道(24 因子排序 + 可交易性回测)
│   ├── run_orders.py            # v1.2 订单簿:门→黑板→fork 卡→25 单生命周期→漂移拦截→recall
│   └── build_demo_video.py      # v1.2 自播放演示视频生成(所有数字来自真实工件)
├── tests/                       # 单元测试(238 项,确定性)
├── ci/                          # CI 回归契约(验收脚本在 CI 中运行)
└── docs/
    ├── THESIS.md                # 论文主张清单:对原文逐条标注(核心文件)
    ├── ARCHITECTURE.md          # 架构:模块边界、数据流、不变量
    ├── BENCHMARK.md             # FIB 注入基准:场景目录、基线、判定标准(17 场景)
    ├── RUBRICS.md               # 判定标准:可复算的 pass/fail 规则
    ├── EVIDENCE.md              # 公开验收记录:v0.2–v0.7 各版本结果
    ├── V1_SCENARIOS.md          # v1.0 三大场景规范:研报复现/观点验证/行情归纳,30 项编号目标
    └── fib_v07_run.json         # v0.7 FIB 全量运行原始输出(17 场景 × 3 裁判)
```

---

## 快速开始

```bash
# 环境:Python ≥ 3.10,运行期零第三方依赖
python3 -m unittest discover -s tests -v      # 238 项测试,全部确定性

# 版本验收(每个脚本都是确定性回归契约,CI 矩阵 3.10–3.13 全跑)
python3 examples/run_evidence_plane.py        # v0.2 证据平面:诚实卡通过、注入卡被拒且错误指明字段
python3 examples/run_research_loop.py         # v0.3 研究闭环:预注册、沙箱、去重、Bonferroni 收缩、一次性 OOS
python3 examples/run_roles.py                 # v0.4 角色与辩论:角色链、消融表、裁判降级
python3 examples/run_settlement.py            # v0.5 结算与校准:90 天视界、哈希链账本、只紧不松
python3 examples/run_fib.py                   # v0.6 注入基准:17 场景 × 2 基线 + 门禁
python3 examples/run_calibration.py           # v0.7 校准与预算读数:52 笔结算、衰减斜率、净/毛
python3 examples/run_discovery.py             # v0.7 发现率@B:共享账本下的收缩曲线 + 包线
python3 examples/run_frontier.py              # v0.7 α-前沿:功效 vs 假阳率 + 包线
python3 examples/run_orders.py               # v1.2 订单簿:门→黑板→fork 卡→25 单→漂移拦截→recall
```

---

## 能力地图与对应论文主张

论文把可信 agentic 量化研究分解为若干层;每层的"主张"在 `docs/THESIS.md` 中对原文逐条标注,这里给出实现与验收位置。

### 1. 证据平面 (v0.2,已交付)

- **证据卡**(`evidence.py`):每条主张是一个结构化的 H 卡(假设)与 E 卡(证据),带数据指纹与哈希链。诚实卡通过,注入卡(幽灵指标、单位错位、静默通过)被拒且错误指明被触字段。
- **门禁**(`verify.py`):schema 校验、数据指纹对账、沙箱重放(防前瞻)、账本对账、防篡改。
- 验收:`examples/run_evidence_plane.py`;测试:`tests/test_evidence.py`、`tests/test_verify.py`。

### 2. 研究闭环 (v0.3,已交付)

- **预注册排序**(`registry.py`):append-only 登记簿拒绝假设未先登记的实验、重复 ID、后补修改(FIB 类 9)。
- **多重检验收缩**(`mining.py`):同一族第 N 次探索,统计量必须过 N 的 Bonferroni 下限。第 10 个"新想法"面对的是第 1 个面对不了的下限;降门槛重试被机械拒绝(FIB 类 11)。
- **沙箱化因子代码**(`sandbox.py`):LLM 写的因子在 AST 白名单 + 截断契约下运行:v1 `factor(closes≤t, tickers, dates≤t, i)` 或 v2 `factor(closes≤t, volumes≤t, tickers, dates≤t, i)`(量能感知因子;v1 代码原样可跑)。前瞻需要越狱沙箱,而非靠 bug(FIB 类 2:指标与代码不符被重算拒绝)。
- 验收:`examples/run_research_loop.py`;测试:`tests/test_registry.py`、`tests/test_sandbox.py`、`tests/test_mining.py`。

### 3. 可消融角色 + 辩论 (v0.4,已交付)

- **角色**(`roles.py`):R1–R8(注册→假设→挖掘→证据→评审→辩论)可关断、可降级、可互换;消融表量化每一角色的贡献。
- **辩论**(`debate.py`):结构化多空辩论 + 裁判裁决,纯规则、确定性。
- 验收:`examples/run_roles.py`;测试:`tests/test_roles.py`、`tests/test_ablation.py`、`tests/test_debate.py`。

### 4. 结算账本 + 校准 (v0.5,已交付)

- **结算**(`settlement.py`):被承认的因子不是"完成",而是在准入从未触及的固定 90 天视界上结算——世界从同一种子确定性续写,因子在沙箱重跑,兑现指标来自与准入同一个引擎(绝不来自卡)。结果进入**哈希链结算账本**,每条记录在审计下可重建、可复算。
- **校准**(`calibration.py`):声称 vs 兑现分箱曲线,斜率/偏差/失准率。反刍规则只收紧、不放松:一族结算失准过频时,该族准入门槛 ×1.25。
- 验收:`examples/run_settlement.py`;测试:`tests/test_settlement.py`、`tests/test_calibration.py`。

### 4a. Fabrication Injection Benchmark (v0.6,已交付;v0.7 扩展)

- **FIB**(`fib.py`):把压力下的失效模式测出来,而不是假设。`docs/BENCHMARK.md` 的注入类——幽灵指标、静默通过、单位错位、后补降门槛、账本篡改、结算伪造、**cherry-universe(宇宙偷换)**、**cost-blind(净/毛混报)**……——被机械化成确定性 PR 提交(一对手足 H/E 卡 + 一处脚本化变异),经三个裁判路由:无门禁单 agent、仅 schema 评审、完整门禁。验收表:完整门禁 17/17 全捕获且错误指明字段,仅 schema 基线 3/17(结构性谎言),无门禁基线 0/17;诚实负结果在三个裁判下全部合并。
- 判定标准:`docs/RUBRICS.md`;结果:`docs/EVIDENCE.md` P5/P6;原始输出:`docs/fib_v07_run.json`。
- 验收:`examples/run_fib.py`;测试:`tests/test_fib.py`。

### 4b. 预算等式估计器 (v0.7,已交付)

- **预算等式**:`E[IR] ≈ ĪC·√B_eff·P̂·TC·e^{(λℓ−δ)t}`。v0.7 的纪律:**一项能力只在随附估计器时交付**。`qsa/budget.py` 从管道状态机械读出各项:
  - **B(discovery@B)**:一族、共享账本;试验累积时发现率 1.000 → 0.571(账本自己的 Bonferroni 下限在抬),假阳保持 0/8(`run_discovery.py`)。
  - **P̂(α-前沿)**:在植入/纯噪声世界上,准入门槛从低到高扫功效 vs 假阳率(构造上知道真值);P̂ = 功效/(功效+假阳率)。门槛抬升时功效 0.861 → 0.417,P̂ 0.912 → 1.000(`run_frontier.py`)。
  - **TC(净成本结算)**:每边 bps 钉进带指纹的 manifest,换手与净价差由引擎计算、由门禁复算;52 笔校准扫描上,玩具反转在 10 bps 下保持**净/毛 = 0.2001**——FIB 22(净报成毛)被复算捕获。
  - **λℓ−δ(队列衰减斜率)**:兑现对声称按声称分箱 OLS;90 天视界上 0.9019(温和泄漏)。
  - **包线**:discovery(N)·P̂(N)·√N——净核查的广度;弱效应族在 N\*=1 达峰(永远摊不平核查),强效应族在 N\*≈2.6e5。工作点是族的性质,工具如实给出。
- 测试:`tests/test_budget.py`;演示:`examples/run_discovery.py`、`examples/run_frontier.py`。

### 5. 有界自治 (pilot 已验证;随框架层交付)

- L0–L3 自治等级 + watchdog 检测→停止(实测 0.21 s)+ 零外溢(完整保护组 5/5 干净窗口)。设计在 `docs/THESIS.md` G-1 一节逐条对照。

---

## 设计不变量

1. **确定性**:运行期零第三方依赖、零墙钟、零网络;同一输入字节级可复现(测试断言 + CI 矩阵 3.10–3.13 保证)。
2. **可复算**:每条主张可被独立门禁复算;任何与代码/数据指纹不符的指标被拒绝且错误指明字段。
3. **只紧不松**:校准与多重检验只能收紧门槛,绝不放松。
4. **证据优先**:交付主张必须随附估计器;未覆盖的 FIB 类显式标注为范围外。
5. **中文注释/说明**:代码与文档保持双语(EN + zh-CN)同步。

---

## 路线图

| 版本 | 范围 | 状态 |
|---|---|---|
| v0.1 | 设计 + 基准规范 + 证据文档 | ✅ 已交付 |
| v0.2 | 证据平面:卡 + verify 门禁 + 确定性 forge | ✅ 已交付 |
| v0.3 | 研究闭环:registry、deflation、sandboxed mining、一次性 OOS、CSV ingest | ✅ 已交付 |
| v0.4 | 可消融量化角色 + bull/bear 评审门禁 + 消融表 | ✅ 已交付 |
| v0.5 | 结算账本 + 校准曲线 + 只紧不松反刍规则 | ✅ 已交付 |
| v0.6 | FIB 注入基准 harness + 判定标准 | ✅ 已交付;下一步外部框架跑 |
| v0.7 | 预算等式估计器,重新锚定到迁移理论:沙盒 v2(volumes)、coverage/宇宙钉死、成本容量核算(门禁复算净指标)、队列衰减斜率、discovery@B + α-前沿 + 包线 | ✅ 已交付 |
| v0.8 | 组合主张:P 卡、组合、walk-forward folds、真实数据结算 | 计划中 |
| v1.0 | 三大经典场景端到端:研报复现 · 观点验证 · 行情归纳总结,每个场景含无门禁通用 agent 对照实验 — 规范:docs/V1_SCENARIOS.md(30 项编号目标) | 🔶 Scenario A 已交付(诚实判定 not_replicated,双跑字节一致);B/C 计划中 |
| v1.1 | 因子工厂快车道:24 个公开文献因子,一键排序 + 可交易性回测 | ✅ 已交付(17/24 OOS 死亡;论文制品继续) |
| v1.2 | 组织记忆层:黑板(哈希链跨会话记忆)+ infra 门 + 订单状态机(admit 冻结参数,漂移即拒)+ fork 拍板卡 + 自播放演示视频 | ✅ 已交付 |

**关键数字**(全部由确定性脚本复现):v0.7 — 52 笔结算;衰减斜率 0.9019;净/毛 0.2001(10 bps);discovery 1.000→0.571(B 1→13);功效 0.861→0.417、P̂ 0.912→1.000;FIB 17 场景全捕获。v1.0/v1.1/v1.2(真实钉死数据 300 票 × 5 年)— 研报复现判定 not_replicated(D1/D2 fail,D3 归因成立);24 因子 17 个 OOS 死亡,幸存 dist_52w_high +0.076 / mom_gap_12m +0.073 / vol_of_vol +0.040(订单簿复算同值);25 单生命周期,7 settle / 18 refuse,漂移拦截 1 次,重跑 recall 24/24。

---

## 引用

```bibtex
@misc{quant-super-agent-2026,
  title  = {Quant Super Agent: A Verifiable Agentic Quant Research Factory},
  author = {Quant Super Agent Contributors},
  year   = {2026},
  note   = {证据平面, 门禁研究闭环, 角色, 辩论, 结算, 校准, FIB 基准, 预算估计器, v0.7},
  url    = {https://github.com/0x1512/quant-super-agent}
}
```
