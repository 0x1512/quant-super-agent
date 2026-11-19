# Quant Super Agent — 可信量化研究闭环

> 论文标题: *Quant Super Agent: A Verifiable Agentic Quant Research Factory*
> 论文地址: [arXiv:2601.04736](https://arxiv.org/abs/2601.04736) · [github.com/0x1512/quant-super-agent](https://github.com/0x1512/quant-super-agent)

**定位:Quant Super Agent = DeepSeek Super Agent(dsh-superagent)的 quant 版**——一个 orchestrator + 一队 worker,研究订单进来、研报出去;优先级恒为 易上手 > 产能 > 可验证 > 风控。

![tests](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/0x1512/quant-super-agent/main/docs/badge/tests.json) ![license](https://img.shields.io/badge/license-MIT-blue) ![python](https://img.shields.io/badge/python-3.10%2B-blue)

<!-- BEGIN STATUS CARD — 由 docs/STATUS.json 经 `make readme-render` 渲染；手改会在发版时被覆盖 -->
**发版口径卡 — v0.2.0（2026-11-19）** · 机器生成，冻结至下一次发版。

| 截至 v0.2.0 | |
|---|---|
| 测试套件 | 544 项测试，离线确定性 —— `make verify`（实时数量见上方徽章） |
| 参考全量跑 | 78 个候选 → 14 张 settle 订单，minute-level, auto-sized worker crew，300-ticker × 1210-day 钉死面板 |
| 并行性 | 4.0x parallel vs sequential, byte-identical for any N |
| 对话增量 | bar-only follow-ups rescore zero rows; universe recomputes finish in tens of seconds |

数字住 [EVIDENCE](docs/EVIDENCE.md) · [NEWS](docs/NEWS.md) · [CASES](docs/CASES.md) · [TOUR_NUMBERS.json](docs/TOUR_NUMBERS.json)（再生与漂移检查：`make tour`）。本卡是本 README 唯一的数字内容，只经 `make release-readme` 变更。
<!-- END STATUS CARD -->

**四问开门见山:**

- **得到什么**:一句话意图 → 带指纹的研究计划树 + 具名编制(GateKeeper / RepoSmith / FlowMapper / SmokeRunner)+ 一次打分的因子进攻 + settle 成冻结参数的订单;追问(「门槛提到 0.05」「剔除小盘」)只复用或只重算被改动影响的部分。
- **多快**:参考全量跑在单机**分钟级**收口,worker 编制自动扩;仅改门槛的追问零行重算。产能以量级表述而非秒表数字——钉死口径见上方发版口径卡。
- **凭什么信**:每条主张都是机器复算的证据卡(数据指纹、无前瞻、因子代码沙盒重放);重试被 deflation 下限约束,闭环无法给自己 p-hack;准入从未触及的视界上结算,反刍规则只紧不松;注入基准把失效模式测出来而非假设掉。
- **现在做什么:**

```bash
git clone https://github.com/0x1512/quant-super-agent.git && cd quant-super-agent
make offense-full   # 参考全量跑:计划树、编制、settle 订单(或诚实零)
make tour           # 从工件再生所有演示数字;漂移即报警
```

> 本 README 是**稳定门面**(能力动词 + 命令即证据),逐轮测量数字住 [NEWS](docs/NEWS.md) / [EVIDENCE](docs/EVIDENCE.md) / [CASES](docs/CASES.md);门面政策见 [README_POLICY.md](docs/README_POLICY.md)。仅研究用途,非投资建议。

---

## 快速开始

环境:Python ≥ 3.10,运行期零第三方依赖。每行注明产物与自验命令,数字由你自己跑出来:

```bash
python3 -m unittest discover -s tests -v      # 整套机器契约(实时数量见徽章)

# 版本验收(每个脚本都是确定性回归契约,CI 矩阵 3.10–3.13 全跑)
python3 examples/run_evidence_plane.py        # v0.2 证据平面:诚实卡通过、注入卡被拒且错误指明字段
python3 examples/run_research_loop.py         # v0.3 研究闭环:预注册、沙盒、去重、Bonferroni 收缩、一次性 OOS
python3 examples/run_roles.py                 # v0.4 角色与辩论:角色链、消融表、裁判降级
python3 examples/run_settlement.py            # v0.5 结算与校准:90 天视界、哈希链账本、只紧不松
python3 examples/run_fib.py                   # v0.6 注入基准:17 场景 × 2 基线 + 门禁
python3 examples/run_calibration.py           # v0.7 校准与预算读数:结算、衰减斜率、净/毛
python3 examples/run_discovery.py             # v0.7 发现率@B:共享账本下的收缩曲线 + 包线
python3 examples/run_frontier.py              # v0.7 α-前沿:功效 vs 假阳率 + 包线
python3 examples/run_orders.py                # v1.2 订单簿:门→黑板→fork 卡→生命周期→漂移拦截→recall
python3 examples/run_offense.py               # v1.3 进攻层:因子库×残差目标→交互/变异→订单(冒烟,数十秒级)
python3 examples/run_offense.py --full        # v1.3 全量:钉死 fixture,300 票×1210 日
python -m qsa.planner "小盘股隔夜反转,沙盒生成补缺口"   # v1.4 意图 → 指纹化计划树
make tour                                     # 再生每个演示数字;漂移即报警
python3 -m qsa.ingest myprices.csv mydata/    # 你的数据:CSV → 合法带指纹快照
```

---

## 能力地图(动词化,数字住证据页)

- **规划研究**:一句话意图编译为指纹化计划树与具名编制;重跑 recall 已 settle 的工作而非重算。
- **打分候选因子**:带出处的因子库(WQ101 子集/幅度波动/流动性)+ 成对交互 + 窗口变异,全部按**残差目标**(对 zoo 幸存者正交化)打分——克隆因子零分。
- **听清追问**:仅改门槛 → 缓存榜单重判、零行重算;改宇宙 → 只重算被移动的行,kept/added/dropped 写明;无法解析的请求 → 拒绝而非猜测。
- **补缺口**:沙盒 forge 环把机器检测到的缺口用 AST 白名单代码补上,同一残差口径打分,行行带 `sandbox-forge` 源标记与代码哈希。
- **结算主张**:准入从未触及的视界上结算,进哈希链账本 + 校准曲线 + **只紧不松**反刍规则。
- **拒绝自己的失效**:预注册排序、deflation 下限、一次性 OOS 窗口;注入基准(FIB)把失效模式测出来,判定标准与原始日志公开。
- **并行安全**:自动扩编的 worker 分片候选池;并行与顺序路径任意 N 字节级一致。

每一层的实现与验收位置(模块、验收脚本、测试)见 [EVIDENCE.md](docs/EVIDENCE.md) 各版本表。

## 案例(索引;档案在 CASES.md)

| # | 案例 | 一句话 |
|---|---|---|
| 1 | Top-300 基线 | 口径卡背后那条参考全量跑 |
| 2 | 小盘残差进攻 | 一条命令全面板,沙盒生成因子过线 |
| 3 | Forge 翻身 | 一个被测出的缺口 → 沙盒生成的候选 |

档案(日期、计划指纹、复现命令、完整数字):[CASES.md](docs/CASES.md)。

## 设计不变量

1. **确定性**:运行期零第三方依赖、零墙钟、零网络;同一输入字节级可复现(测试断言 + CI 矩阵 3.10–3.13 保证)。
2. **可复算**:每条主张可被独立门禁复算;任何与代码/数据指纹不符的指标被拒绝且错误指明字段。
3. **只紧不松**:校准与多重检验只能收紧门槛,绝不放松。
4. **证据优先**:交付主张必须随附估计器;未覆盖的 FIB 类显式标注为范围外。

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
| v0.7 | 预算等式估计器:沙盒 v2(volumes)、coverage/宇宙钉死、成本容量核算、队列衰减斜率、discovery@B + α-前沿 + 包线 | ✅ 已交付 |
| v0.8 | 组合主张:P 卡、组合、walk-forward folds、真实数据结算 | 计划中 |
| v1.0 | 三大经典场景端到端 — 规范:docs/V1_SCENARIOS.md | 🔶 Scenario A 已交付(诚实判定 not_replicated);B/C 计划中 |
| v1.1 | 因子工厂快车道:公开文献因子一键排序 + 可交易性回测 | ✅ 已交付 |
| v1.2 | 组织记忆层:黑板 + infra 门 + 订单状态机 + fork 拍板卡 | ✅ 已交付 |
| v1.3 | 进攻层:引用因子库 + 残差目标 + 交互/变异,一条命令,诚实零 | ✅ 已交付 |
| v1.3.x | 补丁线(自 v1.3 起):新能力面才升 minor | 🔶 计划中 |
| v1.4 | 对话与自编排平面:意图入口、计划树、自动编制、对话增量、修复阶梯、沙盒 forge、分层报告、tour 漂移报警 | ✅ 已交付 |

完整版:[docs/ROADMAP.md](docs/ROADMAP.md)。逐轮数字:[NEWS.md](docs/NEWS.md)。

## 文档导航

- [门面政策](docs/README_POLICY.md) — 数字住哪、README 能说什么、怎么改(20 项机制)
- [论文主张](docs/THESIS.md) · [架构](docs/ARCHITECTURE.md) · [注入基准](docs/BENCHMARK.md) · [判定标准](docs/RUBRICS.md)
- [证据](docs/EVIDENCE.md) · [逐轮 NEWS](docs/NEWS.md) · [案例档案](docs/CASES.md) · [状态页](docs/STATUS.md)
- [因子库](docs/FACTOR_LIBRARY.md) · [v1.0 场景](docs/V1_SCENARIOS.md) · [路线图](docs/ROADMAP.md)
- [开发面状态 README.dev.md](README.dev.md)(自由更新,非门面)

---

## 引用

```bibtex
@misc{quant-super-agent-2026,
  title  = {Quant Super Agent: A Verifiable Agentic Quant Research Factory},
  author = {Quant Super Agent Contributors},
  year   = {2026},
  note   = {证据平面, 门禁研究闭环, 角色, 辩论, 结算, 校准, FIB 基准, 预算估计器, 订单簿, 进攻层, 对话平面},
  url    = {https://github.com/0x1512/quant-super-agent}
}
```

MIT 许可。本研究软件不构成投资建议,不应交易真实资金;所有试点结果均在仿真环境取得。
