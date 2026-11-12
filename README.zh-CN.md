# Quant Super Agent（量化超级智能体）

**可验证的 agentic 量化研究工厂——机器可查的证据、诚实结算、受控自主性。**

> 状态：v0.4——研究 loop + 可消融角色 + 牛熊评审已可运行。证据平面（证据卡 schema、verify 门禁、合成快照、确定性 forge 模拟）v0.2 落地；v0.3 落地门禁化研究 loop（预注册顺序、多重检验惩罚、一次性 OOS 窗口、沙盒因子挖掘、CSV 导入）；v0.4 新增可消融量化角色（data / factor / risk / manager，每个角色 = 人格 prompt + 一个机械检查）与准入前牛熊对抗评审（轮数可配），附确定性消融表。零依赖（见下"快速开始"）。结算层（v0.5）按路线图迁移（见 [Roadmap](docs/ROADMAP.md)）。仅供研究，不构成投资建议。

## 快速开始（v0.4）

纯 Python ≥ 3.10 标准库，零第三方依赖，全程离线、确定性。三个 demo 覆盖已交付范围：

```bash
python examples/run_lifecycle.py            # v0.2 全生命周期：订单→卡→门禁即 CI→PR→合并（toy 数据上结论通常为 fail——照样合并）
python examples/run_lifecycle.py --fib 7    # 注入"静默通过"造假，看门禁拦下合并
python examples/run_mining.py               # v0.3 研究 loop：LLM 因子挖掘、多重检验惩罚、归因驱动迭代
python examples/run_ablation.py             # v0.4 验收：角色 x 评审轮数消融表（种植信号→发现率，噪声→假阳率）
python -m qsa.ingest prices.csv mydata/    # 真实用户数据 → 合法快照
python -m unittest discover -s tests -v     # 110 项测试：门禁、FIB 注入、登记簿、惩罚、沙盒、挖掘、角色、评审、消融、确定性
```

## 为什么做这个

现有 agentic 量化框架产出的是**信号**，没有一个是**可验证的研究**：

- agent 报一个 "IC=0.08"，没有任何东西核对数据指纹、前视窗口、甚至这个数是否真的算过；
- 声称的业绩从不与实现业绩结算，幻觉 alpha 与真 alpha 无法区分；
- 自主重排/工具调用/策略解释没有护栏——我们实测过一次：agent 在明确承诺"不开工"后 **26 秒**违背承诺接单；
- LLM 不可复现被普遍承认，却很少被度量、从未被分解。

## 三大支柱

1. **机器可查的证据**（v0.2 已交付）：研究主张以结构化证据卡（H 假设卡 / E 实验卡）交付，必须过 CI 门禁——schema 完备、快照 sha256 指纹、无前视窗口；v0.3 起门禁还在沙盒里**重执行因子代码**并要求指标逐项吻合；v0.4 起还复核**声称的风控否决**（假否决 = 谎言）与**牛熊评审块**的一致性。过不了门的主张不存在。试点注入实验证实：门禁非静默拦截（详见 [Evidence](docs/EVIDENCE.md)）。
2. **诚实结算校准**（设计完成，v0.5 落地）：准入的因子进入结算台账，评估期末用"声称指标 vs 实现指标"结算，差距回流影响后续准入。系统的头号指标不是收益，是**校准曲线**与零造假记录。
3. **受控自主性**（试点验证，随 harness 层落地）：自主性是带护栏的旋钮——L0 observe / L1 suggest / L2 admit-gated / L3 autonomous（watchdog 实测检测→停止 0.21 秒）。设计源于我们抓到的真实事故（G-1），三层护栏经三臂×5 轮实验验证。

## 与同类项目对比

| | TradingAgents | ai-hedge-fund | RD-Agent | FinRL | **本项目** |
|---|---|---|---|---|---|
| 多角色 agent | ✔ | ✔ | ✔ | ✖ | ✔ **已交付 v0.4**（可消融角色 + 机械职责） |
| 牛熊对抗评审门 | ✔ | ✖ | ✖ | n/a | ✔ **已交付 v0.4**（可核查主张验证、声称否决复算） |
| 研究 loop（H→E→迭代） | ✖ | ✖ | ✔ | ✖ | ✔ **已交付 v0.3**（预注册+多重检验惩罚） |
| 主张级 CI 门禁 | ✖ | ✖ | 部分 | ✖ | ✔ **已交付**（schema+指纹+无前视+代码重算） |
| 多重检验控制 | ✖ | ✖ | ✖ | ✖ | ✔ **已交付 v0.3**（Bonferroni 家族 N 地板） |
| 结算/校准 | 雏形 | ✖ | ✖ | ✖ | 设计中（v0.5） |
| 自主性控制 | ✖ | ✖ | ✖ | — | 试点验证的设计（L0-L3+watchdog 0.21 秒） |
| 可复现协议 | 承认未度量 | ✖ | ✖ | 种子级 | ✔ 已交付（字节级确定性由测试断言） |

## 文档

[English README](README.md) · [架构](docs/ARCHITECTURE.md) · [造假注入基准规格](docs/BENCHMARK.md) · [试点证据](docs/EVIDENCE.md) · [路线图](docs/ROADMAP.md)

## 许可与声明

MIT。研究软件，不构成投资建议，不应使用真实资金交易。所有试点结果均来自仿真环境。

致谢：订单生命周期骨架模式源自 DeepSeek Harness 团队 MIT 协议的 dsh-superagent 研究原型（本项目为独立项目，与 DeepSeek 无隶属关系）；角色/辩论/结算思路受 TradingAgents、ai-hedge-fund、RD-Agent、FinRL 启发。
