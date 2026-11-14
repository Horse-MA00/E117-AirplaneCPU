# D180 至 D0 訂位與正常票價模擬器

更新：2026-11-13（2026-11-14 由 docs/SIMULATOR.md 移至此處）。此為 `src/simulator.py` 與 `configs/simulation.json` 的早期獨立模擬器，仍由 `tests/test_simulator.py` 及 `scripts/generate_demo_data.py` 使用；現行 app 資料由 `simulation/` 生成。此為已實作的數據模擬器，不是需求預測器或會員定價引擎。用於檢查訂位和價格曲線，以及之後建立原型訓練資料。它沒有以真實 HK Express 訂位、票價或價格彈性校準。

## 執行

在儲存庫根目錄，使用 Python 3.12+：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/generate_demo_data.py --export-ensemble
python -m unittest discover -s tests -v
```

預設固定 seed 117，輸出三種需求各一條代表歷程，以及每種情境另外 200 條隨機歷程。共 600 條額外歷程、108,600 個額外快照；代表歷程另有 543 列。代表曲線固定取指定種子，不從 200 次模擬挑選最漂亮的結果。

```bash
python scripts/generate_demo_data.py --seed 118 --replicates 50 --output outputs/alternative
python scripts/generate_demo_data.py --replicates 1000 --export-ensemble --no-plots --output outputs/larger
```

相同配置、種子與依賴版本會產生相同數據。輸出目錄中的同名產物會更新；比較不同設定時使用不同 `--output`。較大規模會佔用較多記憶體；目前生成器把歷程保存在記憶體中，不是串流生成器。

## 真實資料與模擬資料

目前沒有可用的實際 Flight Info API 回應檔，因此預設航班也為假設：HKG→FUK、180 位、2027-05-12 出發，並非真實班表。所有訂位、價格和必付費用都是模擬值。API 憑證不需要放入此程式。

若取得獲授權的航班背景，可提供標準化 CSV：

```csv
flight_id,origin,destination,departure_at,capacity,source_kind
DEMO-001,HKG,FUK,2027-05-12T10:00:00+08:00,180,assumed_demo
```

```bash
python scripts/generate_demo_data.py --flights-csv data/private/flights.csv --output outputs/flight_background
```

`departure_at` 必須含時區，capacity 必須為正整數。這個介面不會直接解析原始 OAG JSON。只有確實來自授權匯出的背景才可標 `api_export`；訂位／票價仍標 simulated。使用事後已知容量模擬過往時，不能聲稱它是當時已知的容量。此版本假設全程容量固定。

## 每一天如何運行

配置位於 `configs/simulation.json`，計算位於 `src/simulator.py`。

1. 每條歷程抽一個隱藏熱度 `theta ~ Gamma(shape=25, scale=1/25)`，平均 1，跨航班變異由 shape 控制。
2. 預設每日需求形狀為 `w(d) ∝ 0.25 + exp(-d/45)`，在 180 個銷售區間上正規化；最後區間按實際時長調整。這是平滑的臨期加速假設，不是業界實證曲線。
3. 三種需求倍數：冷門 0.60、一般 1.00、熱門 1.60。參考價格下的基準總需求為 `capacity × 1.10 × multiplier × theta`，是未受座位上限限制的需求量，不是最終已售座位。
4. 每天先根據當前訂位率、已流逝時間、預設促銷及小幅持續價格噪聲產生正常報價；不讀取未來銷售。
5. 每日平均需求為 `base_total_demand × w(d) × (current_total_price/reference_total_price)^(-0.8)`。再抽 Poisson 需求。
6. 當天接受訂位 `min(demand_requests, capacity - booked_before)`。
7. 當天結束時，原有訂位以每日 0.0008 概率取消。取消釋放的位下一個區間才重新可售。新訂位不在成交當天取消。
8. 更新 `booked_after = booked_before + accepted_bookings - cancellations`，寫入下一個快照。

上述價格反應是模擬假設，不能用此輸出反過來宣稱測量到真實價格彈性。

## 價格如何變動

正常基本票價參考值 HK$500；燃油附加費假設 HK$100，稅及其他必付費用假設 HK$150。這不是實際收費或成本資料。

| 規則 | 預設 |
| --- | --- |
| 訂位率 0%／70%／85%／95% 起 | 基本票價倍率 1.0／1.2／1.5／1.9 |
| 最後 28 天／最後 7 天 | 額外加上參考基本票價的 10%／12% |
| D60 起，訂位率低於基準累積曲線 10 個百分點以上 | 打 75 折 |
| D75–D68／D21–D18 促銷 | 分別打 85／80 折；同時多個促銷取最大折扣 |
| 報價噪聲 | AR(1) persistence 0.85，創新標準差 0.015 |
| 四捨五入及上下限 | HK$10 一檔，基本票價 HK$100–2,000 |

折扣會與促銷相乘。以上是固定的模擬票價政策，不是收入最佳化結果。每日價格不必單調上升；退票、慢銷售和促銷都可能導致降價。冷門航班也可能因臨期規則而小幅漲價。

## 時間與售罄口徑

- D180 為空的初始狀態；D180 到 D0 共 181 個快照，180 個銷售區間。
- D1 是出發前 24 小時；預設 D0 是出發前 2 小時停售，所以最後一段是 22 小時。每日取消概率及需求強度按時長處理。
- 每列報價用於該快照之後的銷售區間；`gross_new_bookings_1d` 等欄則是上一個已完成區間的結果。D180 的過去流量為 0。
- D0 沒有下一個銷售區間，不提供報價。停售時可能仍有未售位。
- 售罄時 `is_available=false`、`quote_status=sold_out`，價格欄是空值，不是零。
- 售罄後若取消，下一天可重新報價。圖上可能出現短暫小段報價，並非資料錯誤。
- 潛在需求及未能接受的需求只保存在 truth 檔；售罄期間是在內部假設票價下的反事實需求，不是實際網站曝光或可購報價。

## 輸出

| 檔案 | 內容與用途 |
| --- | --- |
| `overview.png`／`.pdf` | D180–D0 三種情境訂位率、正常基本票價及總價 |
| `last28days.png`／`.pdf` | D28–D0 放大；此階段尚無會員優惠 |
| `snapshots.csv` | 三條代表歷程的可觀測狀態、價格、過去 1／7 天特徵 |
| `booking_events.csv` | 代表歷程的有效增訂與取消；不含隱藏需求 |
| `outcomes.csv` | 停售結果，只用於標籤或評估 |
| `simulation_parameters_truth.csv` | 情境、隨機種子、隱藏熱度等，不能當模型特徵 |
| `simulation_events_truth.csv` | 潛在需求、內部票價及未成交需求，只供模擬診斷 |
| `representative_summary.csv` | 三條代表歷程的關鍵日狀態 |
| `ensemble_outcomes.csv`／`ensemble_summary.csv` | 多次模擬的結果與彙總 |
| `ensemble/` | 加上 `--export-ensemble` 才輸出全部模擬歷程，格式同上 |
| `flights.csv`／`manifest.json` | 背景、實際運行設定、版本、來源及限制 |

CSV 為 UTF-8 BOM，便於中文試算表軟體開啟。金額 HKD、票價欄整數，訂位率為 0 到 1。

圖中實線是固定 seed 的代表航班；淡色帶是同情境模擬的 P10–P90，包含熱度與隨機波動，**不是已校準的預測區間**。兩種情境可以重疊；冷門／熱門指輸入需求倍率，不是事後強制指定的最終載客率。

同一種子在不同需求情境使用相同熱度和價格噪聲，便於比較；不同平均值的 Poisson 抽樣不代表同一批有身份的旅客。因此此版本不能直接作會員促銷的因果收益比較器。

## 後續模型接入

每列只使用當時已知資料作特徵。`simulation_*_truth`、最終結果、未來報價都不可輸入模型。`flight_id` 包含情境名稱，只作連接鍵，不能作類別特徵；同一背景複本需要放入同一訓練／測試分組。不能把同班 D28 放訓練、D7 放測試。

以正常銷售後續淨訂位為目標時，可以由 `outcomes.final_net_booked_seats - snapshots.net_booked_seats` 建標籤；它可能因取消為負，且在售罄航班受容量截斷。沒有觀測到成交不代表沒有需求。

此版本未實作 LightGBM、會員購買反應、會員票價、會員費、策略收益比較。沒有加入團體訂位、改期、換機、超售、no-show 或真實季節／假期影響。不要把 600 條模擬歷程稱為 600 班真實航班；它們是共用背景的隨機情境。

## 驗證

單元測試涵蓋重現性、181 個狀態與 180 個區間、容量上限與庫存守恆、取消、售罄需求截斷、最近 7 天與原始事件的一致性、價格拆分、停售空值、未來促銷不影響過去狀態，以及非法輸入拒絕。

這些檢查證明程式遵守設定規則，不證明規則符合真實航空市場。判斷視覺合理性時，應先看：D28 訂位量是否合乎團隊預期、冷門剩位是否過多、熱門是否過早售罄、價格階梯是否太強，再調整 `simulation.json` 比較結果。
