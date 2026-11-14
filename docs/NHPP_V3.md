# NHPP v3：整週對齊、放票顯著性門檻與兩輪之間的突增預警

> 状态：现行 · 对应代码：`nhpp-regime-mixture-v3`、`inter-round-tighten-only-v1`、`backend/nhpp_v3.py`

2026-11-14（Asia/Hong_Kong）。執行中的預測為 `nhpp-regime-mixture-v3`（`backend/nhpp_v3.py`），校準檔為 `simulation/generated/calibration_v3.json`。v2 的 `backend/nhpp.py` 一個位元組都沒改，`calibration_v2.json`、v2 final 及擴大驗證報告照舊以它驗證；所有 v2 報告未覆寫。

## 1. 修正的三個問題

| 問題 | v2 的程式行為 | v3 的行為 |
|---|---|---|
| 週末／假日近端需求爆發 | 只在 D28／D14／D7 重算預測；兩輪之間保護量只會隨正常票售出而減少，D28 釋出的配額要到 D14 才可能被擋下。預測不讀出發星期或假日。 | 兩輪之間每日執行按星期對齊的突增檢查；觸發時重算預測，**只可提高**正常需求保護量。週五至週日出發或明確標示假日的航班使用較高的近端衝擊先驗。 |
| 七天整週對齊 | 變點候選為 3／5／7／10／14 日；窗口實際截取 36 個區間（端點多算一天）；beta 似然逐日加權。 | 變點候選為 7／14／21／28 日；窗口正好 35 個每日區間（5 週）；beta 似然按 7 日區塊加權。 |
| 高客座率航班的小額放票 | 只要 `空位 − 保護量 > 0` 就放票，1–5 位的釋出量可能小於保護分位數的抽樣誤差。 | 引入漸近顯著性門檻：可釋位必須大於 `z × SE(保護量)`，否則不放票。 |

### 修正前的可重現證據

- **假變點：** 只有週內波動（兩個週末日為平日 2.5 倍）、沒有真實轉折時，v2 報告「5 日前下降」變點（ratio 0.51）。
- **窗口：** 任一 D28 歷史 `intervals = 36`；`SETTINGS['window_days']=35` 未被程式引用。
- **相位偏差：** 平坦趨勢加固定週內形狀，只改變決策日落在星期幾，v2 的 beta 在 −0.0064 至 −0.0008 間變動。只把窗口改成 35 日但仍逐日加權，差距反而更大；必須按週區塊加權。
- **抽樣誤差：** SYN-00256 D14（客座率 74.6%）在 seed 117 釋出 1 位；同一歷史換 30 個 seed，釋出量 0–5，53% 為 0。
- **滯後：** SYN-00184 在 D28 釋出 28 位，但 D28→D0 實際正常需求 156，超過當時 115 個空位。v2 若在 D24 重算已顯示應釋出 0；共用市場卻要到 D14 才重算。

`backend/tests/test_nhpp_v3_fixes.py` 把以上情況寫成 14 個回歸測試；在修正前的程式上 13 個失敗（剩下 1 個用來確認真實的整週水準上升仍可被偵測，防止修正過度）。

## 2. 演算法規格

### 2.1 窗口與週區塊

只使用 `d < D + 35` 的完整每日區間，即決策日 `D` 之前正好五週。每個區間記錄 `block = floor((D − d) / 7)`，最近 7 日為區塊 0。

### 2.2 beta 似然

Gamma(1, 1) 水準先驗下，原逐日邊際似然為 `Π g_i(β)^{c_i} / (1 + Σ g_i)^{1+C}`。v3 改為按週區塊：

\[
L(\beta)\propto \prod_b G_b(\beta)^{C_b}\,/\,(1+\textstyle\sum_i g_i(\beta))^{1+C},\quad
G_b=\sum_{i\in b} g_i,\ C_b=\sum_{i\in b}c_i
\]

`g_i` 是區間強度積分乘價格 exposure。週內各日的分配不提供趨勢資訊，因此固定的週內形狀不再被讀成斜率。Gamma 水準後驗仍使用全部計數及 exposure；右截斷區間仍以 `Pr(D ≥ 可售量)` 單獨處理。

### 2.3 變點

候選切點為 `[7, 14, 21, 28]` 日；其餘條件不變（較早段至少 7 個區間、合計至少 12 次、log-LR ≥ 5、水準比 ≥ 1.8 或 ≤ 0.55）。代價是已發生的水準轉折最快要 7 日後才會被當成變點重新估計；較快的反應由 2.5 節的預警負責。

### 2.4 週末／假日先驗

`peak_departure(rows)` 依序判斷：明確 override；任何列的 `is_public_holiday` 為真；最新 `departure_at` 是週五、六、日。假日**不會被推斷**，必須由已知的資料欄位提供。對 peak 航班，未來持續及短暫衝擊的先驗機率乘以 `1.5`（工程假設，並非估計值）。原始資料有 `departure_at`；共用市場的合成航班歷史沒有日曆欄位，因此在共用市場中為 `unknown_calendar`，不套用此先驗。

### 2.5 兩輪之間的突增預警（只收緊）

`surge_alarm(rows, D)` 比較最近 3 個完整日，與前 1–4 週**相同星期**的 3 日（至少 2 週有效、皆未受容量截斷）。以價格 exposure 正規化後計算兩段 Poisson log-LR；同時滿足最近 3 日 ≥ 6 次、水準比 ≥ 1.8、log-LR ≥ 4 才觸發。

共用市場在 D27–D1 中非放票日、仍有未售會員配額時每日檢查。觸發時：

1. 用當時可見歷史重跑 NHPP（如有 seat-feedback profile，非放票日使用下一個較長的已校準時點，與保護量校準慣例相同）；
2. `protection_remaining = max(原值, 新保護量)`，**從不放寬**；
3. 不新增、不取消、不重設任何配額批次。被擋下的有效未售配額仍保留，之後若下一輪的保護量下降，可以重新成交。

紀錄在每班 `monitor_history`，摘要另有 `monitor_forecast_calls` 及 `inter_round_monitor_version = inter-round-tighten-only-v1`；放票輪次的 `forecast_calls` 計數不變。Admin 示範的會員購票本來就以購票當日預測作上限，行為不變。

### 2.6 放票顯著性門檻

保護量 `H = q90 + allowance(q90)`。以 800 條路徑中 `q90` 的漸近標準誤：

\[
SE(q_{0.9})=\frac{Q(0.95)-Q(0.85)}{0.1}\sqrt{\frac{0.9\times0.1}{n_{\text{eff}}}},\quad n_{\text{eff}}=\min(800,\ \text{ESS})
\]

再以有限差分把它傳到含校準修正的 `H`，得到 `SE(H)`。原本的可釋位 `R = max(0, 空位 − H)` 只有在 `R > 1.645 × SE(H)`（單側 95%）時才發布，否則為 0。診斷欄位 `release_significance` 保存 `pre_threshold_release`、`threshold_seats`、`protection_standard_error`、`effective_draws` 及 `held_by_threshold`。

注意：期望空座率本身的蒙特卡洛標準誤約為 `sd/√800`，通常只有 0.1 位左右，用它做門檻幾乎擋不住任何釋出；決定放票量的抽樣噪聲來自保護分位數，所以門檻建立在分位數上。

## 3. 校準與一次性最終比較

```bash
python -m simulation.evaluate_nhpp_v3 calibration   # seed 20261115，與 v2 校準集相同
python -m simulation.evaluate_nhpp_v3 final         # seed 20261117，首次開啟，僅執行一次
```

校準方法與 v2 相同：每個時點取各合成情境相對殘差的 90% 上側次序統計量，再取最保守情境。v3 相對保護係數為 D28 **0.514**、D14 **1.116**、D7 **1.130**（v2：0.571／1.167／1.042）。v3 final 報告已存在時腳本會拒絕重跑。

240 班新航班（seed 20261117；v2 使用其凍結校準，同一批資料）：

| 時點／群組 | 需求 MAE v2 → v3 | 保護覆蓋 v2 → v3 | 平均可釋位 v2 → v3 | 釋出比例 v2 → v3 |
|---|---|---|---|---|
| D28 全部 | 31.46 → 33.28 | 97.1% → 97.5% | 8.39 → 7.66 | 21.3% → 17.5% |
| D28 突增 | 53.07 → 51.60 | 82.5% → 85.0% | 0.88 → 0.85 | 5.0% → 5.0% |
| D14 全部 | 14.65 → 15.55 | 99.6% → 99.6% | 13.22 → 12.44 | 30.8% → 25.4% |
| D14 突增 | 32.09 → 31.10 | 97.5% → 97.5% | 1.05 → 0.85 | 7.5% → 5.0% |
| D7 全部 | 8.39 → 8.57 | 98.8% → 99.2% | 23.79 → 22.66 | 42.9% → 39.6% |
| D7 突增 | 19.17 → 18.70 | 92.5% → 95.0% | 3.73 → 3.08 | 17.5% → 15.0% |

- 覆蓋率在所有時點都不低於 v2，代價是每班平均少釋出約 0.7–1.1 位；整體需求 MAE 略差，突增子群 MAE 略好。這是更保守的取捨，不是全面改善。
- 720 次 v3 預測中有 20 次被顯著性門檻擋下（D28 11、D14 6、D7 3）。
- 預警：D28–D14 間開始突增的 12 班中，11 班（91.7%）在 D14 前觸發，中位數比 D14 早 5 日。四種平穩情境在 D27–D1 任一非放票日觸發過的比例為 19.4%；其中帶正趨勢的 typical／high 航班較多。誤報只會觸發一次重新預測，保護量取兩者較大值，不會放出座位。
- SYN-00184（原始資料）在 v3 下 D28 不再釋出；但其最近 3 日計數很少，預警到 D16 才觸發，只比 D14 早 2 日。計數少的航班反應仍有限。
- 合成生成器沒有週內或假日效應，所以週末先驗在這批資料上只增加保守度（peak 航班 D28 平均釋出 7.09 對非 peak 8.16），不能當作已驗證的改善。

需求篩選目錄 `simulation/demand_catalog.json` 已用 v3 依規定以 `python scripts/build_demand_catalog.py` 重建：1,549 班中 Low／Medium／High 由 336／447／766 變為 334／456／759。目錄只讀 D28 觀測欄位，不含 `departure_at`，因此分類不受週末先驗影響。

會員示範資料夾 `simulation/member_demo_generated/`（包括 `headroom_validation.json`）是凍結資料，未改動；其中的 D28 可釋位提示仍是凍結 v2 審計的結果，只作航班預設選擇提示，實際預測、可釋位及發布都由 v3 即時計算。用 v3 重算時，該批 D28 有正釋出的航班由 126 減為 112，至少 25 位的航線由 70 減為 65，D14／D7 不變。

`nhpp_v3_calibration.json`、`nhpp_v3_final.json` 及 `calibration_v3.json` 最初以 v3 程式放在 `backend/nhpp.py` 時產生；為遵守 v2 檔案凍結規則，程式其後原樣移到 `backend/nhpp_v3.py`（只改了說明 v2 位置的 docstring），因此重新產生兩份報告以更新程式 hash。重新產生的 1,440 筆 final 預測紀錄、摘要、預警結果及保護係數與第一次逐項相同，沒有任何參數因看過 final 而調整。

## 4. 相容性與溯源

- 執行路徑（`server.py` 的 `forecast_for`、`shared_market.py`、`initial_policy.py`、`evaluate.py`、`demand_catalog.py`）改為匯入 `backend.nhpp_v3`。`backend/evidence.py`、`simulation/evaluate_nhpp_v2.py`、`simulation/extended_validation.py`、會員示範審計仍讀 `backend/nhpp.py`（v2），所以 v2 final／擴大驗證不受影響，`/api/evaluation/extended` 繼續回傳 v2 的 91.5%。
- 新實驗、最佳化及連續定價的 hash 清單改為凍結 `backend/nhpp_v3.py` 與 `calibration_v3.json`；舊的共用市場或最佳化實驗按設計拒絕以新程式續跑，舊報告原樣保留。
- `forecast()` 新增選用參數 `peak_departure_override`；輸出新增 `diagnostics.release_significance`、`diagnostics.calendar`、`window_days`、`weekly_block_days`。其餘欄位不變。
