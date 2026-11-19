# 测试卡（factor test card）— 测类表现展示方案

> 一因子一卡：判决先行、指标同尺、时序可读、诚实分层。
> 生成：`python tools/factor_card.py --ids <id,...|all24>` → `docs/cards/<id>.md`

## 1. 范式映射（参考 → 纪律改造）

| 参考平台 | 展示要素 | 本仓对应 | 改造理由 |
|---|---|---|---|
| WorldQuant BRAIN alpha 摘要页 | IS stats + submission verdict | **判决链**（stage1→stage2→walk-forward）+ 主指标表 | verdict 是产品的牙齿，放首屏 |
| alphalens tearsheet（Quantopian） | IC 时序、分位收益 | 月度 IC 双行图（月度+累计）+ G1/G5/TMB | 分层是代理，注明"非完整单调性" |
| 聚宽/米筐回测报告 | 净值/回撤/年度表 | walk-forward 块均值表 | 因子语境的"回撤"=时间局部死亡（滚动 12 月负 IC 触发） |
| PandaAI | 问一句看一图 | 卡自足可读（四问：是什么/多强/凭什么信/下一步） | 读者不跳转、不跑代码就能裁决 |

**刻意不做**：组合收益回测曲线、夏普、回撤金额。引擎不持有仓位假设；
任何收益数字必须出自冻结 run——展示层不制造它。

## 2. 卡结构（六段，顺序即读序）

1. **档案条**：id · 机制一句话 · 来源（cited / sandbox-forge / neighborhood-scan）· 扫描族计数（多重检验脚注入口）
2. **判决链**：`stage1 ✓ → stage2 ✗ → walk_forward ✓ | 状态 | stage2-v2 待拍板 → pass`。**双口径并陈**：stage2 永远显示冻结门（月度 icir>1.0）判决；拟议 stage2-v2（年化 1.0）单独标注"待拍板"，不冒充已入册
3. **主指标表**：OOS IC / IC 均值 / ICIR(年化) / 多空 G5−G1 / G1,G5 / 正 IC 月占比 / 样本——每行附口径一列（BRAIN IS Summary 的信息密度）
4. **月度 IC 图**：上行月度（8 档高度∝\|IC\|），下行累计（看单调性/衰减形状）；>60 月等距抽样不缩不隐
5. **walk-forward 块表**：每半年一块，块均 IC + 条形（负块 `-`）；判读行给触发次数/半衰比/正块数
6. **诚实脚注**：探索层声明、门禁预注册未调整、扫描挑选计入 deflation 计数、冻结 run 唯一主张路径

## 3. 工程属性

- 纯函数渲染（`qsa/factorcard.py`），byte-stable 可 golden 测试（`tests/test_factorcard.py`）
- 零依赖（stdlib；图用 Unicode 块字符，非 matplotlib）
- CLI `tools/factor_card.py`：库内 id 走 `build_catalog()`；邻域变体 id（`gap_sum_N/dist_high_N/mom_F_S/vol_N/rev_N`）由工厂重建，与 `docs/loops/scan_momentum.json` 同参
- 数据同源：`evaluate_factor_fast`（v0.2.0 矩阵引擎）+ `walkforward_verdict`——卡片数字=门禁数字，无第二口径

## 4. 当前卡集

- `docs/cards/` 27 张 = 库内 24 全因子 + 3 张样例（`gap_sum_252`、`gap_sum_378` 双过候选，`mom_504_63` 最强 oos 但双 fail——诚实失败卡）
- 卡是**探索层快照**：重跑生成不改变门禁记录（registry/run 记录才是正本）

## 5. 边界与不做

- 卡不进 README 首屏（README=稳定门面，五次纠偏）；卡集增长不触发 release
- 拍板 stage2-v2 后：冻结 run 的卡由 run 本体产出，头部状态改为"冻结"，本目录继续作探索层
- 多重检验：卡片只**标注**扫描计数（`scan_n`），不做校正主张——deflation 在 run 层执行
