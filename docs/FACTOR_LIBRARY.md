# v1.3 因子库（Offense Layer）与残差目标

> 版本：v1.3 · 代码：`qsa/factorlib.py`（目录+构造）、`qsa/offense.py`（残差目标、成对交互、变异搜索）、`examples/run_offense.py`（一条命令流水线）。
> 纪律：每条因子带出处与公式；构造只读 ≤ t 的数据（与沙盒同一约定）；快照缺列的因子族自动不构建（`build_catalog(available)` 按面板过滤）；所有排序与结算由 `run_offense.py` 机器产出，本文不手写任何 IC 数字。

## 1. 目录（30 项，全部机器可构建）

### WorldQuant 101 子集（12 条）

来源：Kakushadze, *101 Formulaic Alphas* (2015), arXiv:1601.00991。选取标准：纯 OHLCV 可算、无需 ex-rights/industry 外部数据。

| id | 公式（论文原式） |
|---|---|
| wq_a2 | -1·corr(rank(Δln(V,2)), rank((C-O)/O), 6) |
| wq_a3 | -1·corr(rank(O), rank(V), 10) |
| wq_a6 | -1·corr(O, V, 10) |
| wq_a8 | -1·rank(sum(O,5)·sum(ret,5) − delay(sum(O,5)·sum(ret,5),10)) |
| wq_a12 | sign(ΔV,1)·(−1·ΔC,1) |
| wq_a13 | -1·rank(cov(rank(C),rank(V),5)) |
| wq_a14 | -rank(Δret,3)·corr(O,V,10) |
| wq_a15 | -1·sum(rank(corr(rank(H),rank(V),3)),3) |
| wq_a16 | -1·rank(cov(rank(H),rank(V),5)) |
| wq_a19 | -sign((C−delay(C,7))+ΔC,7)·(1+rank(1+sum(ret,250))) |
| wq_a23 | (sum(H,20)/20 < H) ? −ΔH,2 : 0 |
| wq_a24 | (Δsma(C,100),100 / delay(C,100) ≤ 0.05) ? −(C−ts_min(C,100)) : −ΔC,3 |

### 真幅度/波动族（8 条）— 需要 high/low 面板

| id | 公式 | 出处 |
|---|---|---|
| parkinson_vol_20d | mean(ln(H/L)²,20)/(4·ln2)；flip（低波动异常） | Parkinson (1980), J. Business |
| garman_klass_20d | 0.5·mean(ln(H/L)²,20) − (2ln2−1)·mean(ln(C/O)²,20)；flip | Garman & Klass (1980), J. Business |
| rogers_satchell_20d | mean(ln(H/C)ln(H/O)+ln(L/C)ln(L/O),20)；flip | Rogers & Satchell (1991), Ann. Appl. Prob. |
| range_ratio_20d | parkinson_20d / std(ret,20)² | range-vs-close 方差比（Alizadeh-Brandt-Diebold 2002 的精神） |
| stoch_k_14d | (C−min(L,14))/(max(H,14)−min(L,14))；flip（超买反转） | Lane 随机 %K（经典 TA） |
| shadow_upper_20d | mean((H−max(O,C))/(H−L),20)；flip | 蜡烛解剖（经典 TA） |
| body_eff_20d | mean(ln(C/O),20)/mean(|ln(C/O)|,20) | 蜡烛解剖（经典 TA） |

### 流动性族（6 条）— 需要 amount/vwap 面板

| id | 公式 | 出处 |
|---|---|---|
| amihud_dollar_21d | mean(|ret|/amount,21)；flip（流动性溢价） | Amihud (2002), J. Fin. Markets |
| vwap_premium_5d | mean((C−vwap)/vwap,5) | 微观结构常识 |
| vwap_vol_corr_10 | -corr(rank(C/vwap),rank(V),10) | 量价背离（101 精神） |
| amount_spike_5_60 | mean(amount/mean(amount,60),5)；flip（脉冲反转） | — |
| ln_amount_z_20d | -zscore(mean(ln(amount),20))；flip（小流动性溢价） | — |
| （族说明） | vwap 在停单日可能为空；数据面按“全有或全无”面板列处理 | — |

### 参数化族（7 条，`FAMILIES` + `window_variants`）

| id | 公式 | 用途 |
|---|---|---|
| mom_gap_12m / mom_12m | close−shift(close,252) 减去 21d gap 累计 / shift(close,252)/close−1 | 动量基线（v1.1 工厂同源） |
| dist_high_252d | close/rmax(close,252) | 距高点（均值反转族） |
| sharpe_21d | mean(ret,21)/std(ret,21) | 风险调整动量 |
| intraday_21d | mean(ln(C/O),21) | 日内收益 |
| vol_of_vol_20d | std(ret²,20)/std(ret,20) | 波动之波动 |

窗口变体（`window_variants(["mom","mom_gap"],["dist_high","sharpe","intraday","vol_of_vol"], …)`）在 3/6/9/18/24 与 10/42/63/126/252 上展开，构成变异搜索空间（run_offense 固定用 30 个变体）。

## 2. 残差目标（offense 的核心判据）

**动机**：zoo（v1.1）已把 24 个文献因子的裸 IC 榨干；继续报“裸 IC 更高”几乎必然是幸存者克隆。所以 v1.3 的判定对象是**对基正交化后的信号**：

```
对每个交易日 d：
  y = 候选信号在 d 的横截面值
  X = 7 个 zoo 幸存者在 d 的横截面值（列标准化）
  y_res = y − OLS(y | X) 的残差
IC 用 y_res 对次月收益做月度 spearman（与 replication 同一约定）
```

- 克隆（与幸存者相关性≈1 的信号）残差≈0 → IC≈0 → 不给分。
- 正交增量（新信息）才有残差 IC → 才配拿快车道门票。
- 实现：`qsa/offense.py::residualize`（逐日横截面 OLS，手动实现，与 numpy 双因子 OLS 在 1e-9 内一致，见测试）。

## 3. 三条挖掘通道

| 通道 | 构造 | 数量（run_offense 默认） |
|---|---|---|
| library | 目录全量，缺列族自动过滤 | 30 |
| interactions | top-k 幸存者的两两乘积/比率/价差，各自再残差化 | C(7,2) 中可构造的 18 项（run 取前 18） |
| mutations | 参数化族 × 固定窗口网格 | 30 |

**预注册门槛**（`run_offense.py` 常量，未做事后调参）：
`residual oos IC > 0.03 且 n_months ≥ 12`。门槛之上的候选发 settle 订单（订单参数冻结，与订单状态机同一套纪律）；**没有候选过门槛就是诚实的零**，报告如实写 0 张。

## 4. 一条命令

```bash
# 冒烟（300 日 × 15 幸存者，~1 min）：验证流水线全通，预期可能就是 0 张
python examples/run_offense.py

# 全量（钉死 fixture，300 票 × 1210 日，~6 min）
python examples/run_offense.py --full --work /tmp/offense_full
```

产出：`report.md`（残差 leaderboard + 因子库清单 + 订单数）、`orders.jsonl`（每赢家一张冻结参数的 settle）、`blackboard.jsonl`（一条 order_note）。

## 5. 数据面前提

- `qsa/ingest.py` 支持可选面板列 `high/low/amount/vwap`（all-or-nothing：要么每行都有，要么整列不请求；见 `tests/test_ingest_panels.py`）。
- 快照缺列时 `build_catalog(available)` 只返回可构建的子集，旧快照（close/open/volume）行为不变。
- 钉死 fixture 的扩展面板由 `examples/data/derive_extra_fixture.py` 从原始缓存派生（qfq 因子恢复验证过：f_close≈f_open 中位偏差 1e-6）。

## 6. 诚实边界（必读）

1. 残差 IC 过门槛 = **快车道资格**，不是 alpha 证据。对外的任何收益主张仍欠 v1.0 全程（成本、容量、drawdown、三关、双跑、注入控制）。
2. 库扫描本身是多重检验：30+18+30 个候选共享同一个 1210 日面板。run_offense 不做事后 deflation（那是 v1.0 工序，已排期为 v1.3.1 补丁），所以 leaderboard 的头部数字天然偏乐观——这正是订单里写“gauntlet still required”的原因。
3. 公式引用 = 论文原式转写，置信度标注在目录 `source` 字段；任何公式与论文不符都应视为 bug 并修。
4. 本文与 `run_offense.py --full` 的机器输出互为镜像：报告里的每个数字都可以用同一命令重放。
