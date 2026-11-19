# 测试总览 · 现有全部因子效果

> 快照 fixture A股Top300主表　·　样本 41–58 月 × 300 标的　·　判决门=冻结 stage2 + walk-forward（stage2-v2 年化口径待拍板）　·　共 59 项，诊断双过 3 项　·　库内名与扫描名同参重合 6 对（双实现数字一致，交叉验证）

## 幸存者（stage2-v2 诊断 + walk-forward 双过，待拍板）

| 因子 | OOS IC | ICIR(年化) | 多空G5−G1 | 正IC月 | 模拟PnL | 卡 |
|---|---|---|---|---|---|---|
| **mom_gap_12m** | +0.0733 | 1.16 | +0.16 | 62% | 年化 +15.3% / Sharpe 1.19（费后） | [卡](mom_gap_12m.md) |
| **gap_sum_252** | +0.0733 | 1.16 | +0.16 | 62% | 年化 +15.3% / Sharpe 1.19（费后） | [卡](gap_sum_252.md) |
| **gap_sum_378** | +0.0637 | 1.32 | +0.20 | 61% | 年化 +19.4% / Sharpe 1.54（费后） | [卡](gap_sum_378.md) |

## 族级对比（各族最强变体，按 OOS IC）

```
momentum     ██  +0.1152  (mom_504_63, 16 变体)
overnight    ▇▇  +0.0967  (gap_sum_189, 11 变体)
near-high    ▇▇  +0.0906  (dist_high_504, 8 变体)
volatility   ▅▅  +0.0657  (sharpe_20d, 8 变体)
volume       ▄▄  +0.0360  (pv_corr_20d, 5 变体)
reversal     ▁▁  -0.0035  (rev_1w, 8 变体)
skew         ▁▁  -0.0119  (max_ret_20d, 2 变体)
friction     ▁▁  -0.0147  (zero_ret_freq_21d, 1 变体)
```

## 全部测试项

| 因子 | 族 | OOS IC | ICIR(年化) | stage2 | s2-v2 | walk-fwd |
|---|---|---|---|---|---|---|
| mom_504_63 | momentum | +0.1152 | 0.86 | ✗ | ✗ | ✗ |
| mom_504_0 | momentum | +0.1132 | 0.61 | ✗ | ✗ | ✗ |
| mom_504_21 | momentum | +0.1012 | 0.61 | ✗ | ✗ | ✗ |
| gap_sum_189 | overnight | +0.0967 | 1.14 | ✗ | ✓ | ✗ |
| dist_high_504 | near-high | +0.0906 | 0.61 | ✗ | ✗ | ✗ |
| dist_52w_high | near-high | +0.0758 | 0.42 | ✗ | ✗ | ✗ |
| dist_high_252 | near-high | +0.0758 | 0.42 | ✗ | ✗ | ✗ |
| mom_gap_12m | overnight | +0.0733 | 1.16 | ✗ | ✓ | ✓ |
| gap_sum_252 | overnight | +0.0733 | 1.16 | ✗ | ✓ | ✓ |
| gap_sum_504 | overnight | +0.0711 | 1.10 | ✗ | ✓ | ✗ |
| mom_189_63 | momentum | +0.0692 | 0.77 | ✗ | ✗ | ✗ |
| dist_high_189 | near-high | +0.0677 | -0.03 | — | — | ✗ |
| sharpe_20d | volatility | +0.0657 | -0.57 | — | — | ✗ |
| gap_sum_63 | overnight | +0.0652 | 0.60 | ✗ | ✗ | ✗ |
| dist_high_378 | near-high | +0.0651 | 0.69 | ✗ | ✗ | ✗ |
| gap_sum_378 | overnight | +0.0637 | 1.32 | ✗ | ✓ | ✓ |
| chan_pos_20d | near-high | +0.0628 | -0.08 | — | — | ✗ |
| mom_189_0 | momentum | +0.0568 | 0.02 | — | — | ✗ |
| gap_sum_126 | overnight | +0.0565 | 0.92 | ✗ | ✗ | ✗ |
| mom_252_63 | momentum | +0.0545 | 0.75 | ✗ | ✗ | ✗ |
| mom_252_0 | momentum | +0.0530 | 0.27 | — | — | ✗ |
| intraday_21d | overnight | +0.0431 | -0.79 | — | — | ✗ |
| vol_of_vol | volatility | +0.0396 | 0.71 | ✗ | ✗ | ✗ |
| mom_189_21 | momentum | +0.0369 | 0.27 | ✗ | ✗ | ✗ |
| pv_corr_20d | volume | +0.0360 | -0.10 | — | — | ✗ |
| mom_126_63 | momentum | +0.0354 | -0.03 | ✗ | ✗ | ✗ |
| mom_12_1 | momentum | +0.0335 | 0.42 | ✗ | ✗ | ✗ |
| mom_252_21 | momentum | +0.0335 | 0.42 | ✗ | ✗ | ✗ |
| dist_high_63 | near-high | +0.0324 | -0.30 | — | — | ✗ |
| mom_126_0 | momentum | +0.0324 | -0.73 | — | — | ✗ |
| dist_high_126 | near-high | +0.0293 | -0.29 | — | — | ✗ |
| signed_vol_20d | volume | +0.0271 | -0.35 | — | — | ✗ |
| mom_378_63 | momentum | +0.0208 | 0.63 | ✗ | ✗ | ✗ |
| mom_378_0 | momentum | +0.0192 | 0.40 | ✗ | ✗ | ✗ |
| mom_126_21 | momentum | +0.0121 | -0.57 | — | — | ✗ |
| mom_378_21 | momentum | +0.0047 | 0.43 | ✗ | ✗ | ✗ |
| volume_trend | volume | +0.0021 | 0.78 | ✗ | ✗ | ✗ |
| vol_ratio_5_20 | volume | -0.0023 | 0.22 | ✗ | ✗ | ✗ |
| rev_1w | reversal | -0.0035 | 0.62 | ✗ | ✗ | ✗ |
| rev_5 | reversal | -0.0035 | 0.62 | ✗ | ✗ | ✗ |
| vol_20d | volatility | -0.0052 | 1.00 | ✗ | ✗ | ✗ |
| vol_20 | volatility | -0.0052 | 1.00 | ✗ | ✗ | ✗ |
| rev_63 | reversal | -0.0114 | 1.05 | ✗ | ✗ | ✗ |
| max_ret_20d | skew | -0.0119 | 1.30 | ✗ | ✗ | ✗ |
| run_length | reversal | -0.0122 | 0.53 | ✗ | ✗ | ✗ |
| amihud_21d | volume | -0.0134 | -0.74 | — | — | ✗ |
| zero_ret_freq_21d | friction | -0.0147 | 1.18 | ✗ | ✗ | ✗ |
| vol_10 | volatility | -0.0153 | 0.77 | ✗ | ✗ | ✗ |
| hl_range_20d | volatility | -0.0236 | 0.97 | ✗ | ✗ | ✗ |
| gap_freq_21d | overnight | -0.0258 | 1.07 | ✗ | ✗ | ✗ |
| rev_10 | reversal | -0.0293 | 0.93 | ✗ | ✗ | ✗ |
| gap_vol_21d | overnight | -0.0346 | 0.82 | ✗ | ✗ | ✗ |
| skew_20d | skew | -0.0363 | 0.56 | ✗ | ✗ | ✗ |
| vol_60 | volatility | -0.0389 | 0.84 | ✗ | ✗ | ✗ |
| overnight_gap_21d | overnight | -0.0478 | 0.83 | ✗ | ✗ | ✗ |
| vol_120 | volatility | -0.0479 | 0.65 | ✗ | ✗ | ✗ |
| rev_1m | reversal | -0.0532 | 0.73 | ✗ | ✗ | ✗ |
| rev_21 | reversal | -0.0532 | 0.73 | ✗ | ✗ | ✗ |
| ret_vol_scaled_21d | reversal | -0.0629 | 0.64 | ✗ | ✗ | ✗ |

---
诚实脚注：stage2 列为冻结门（月度 icir>1.0）判决；s2-v2 列为拟议年化口径（待拍板，未入册）；both=✓✓ 不构成对外主张，正式结论唯一路径是冻结 run。指标与单卡/门禁同源同口径（evaluate_factor_fast + walkforward_verdict）。
