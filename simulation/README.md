# 每日機票與空座模擬

目前合計600000筆：下文original generated/為200000筆，validation_extended/有兩批各200000筆。新NHPP請使用evaluate_nhpp_v2；文末v1數字保留為歷史。詳見[擴大驗證](../docs/EXTENDED_VALIDATION.md)。

本模組生成 **200,000 筆**每日快照。1,104 班有完整 D180–D0 的 181 筆；最後一班保留 D175–D0 的 176 筆，合計正好 200,000。最後一班同樣從 D180 開始模擬，只省略最初五筆輸出。所有航班均包含完整 D28–D0 決策期。

```bash
python -m simulation.generate
python -m simulation.generate --validate-only
python -m simulation.evaluate_nhpp_v2 development
# Calibration is explicit; do not overwrite or tune against the committed final report.
python -m simulation.evaluate_nhpp_v2 calibration
python -m unittest discover -s tests -p 'test_simulation_data.py' -v
```

`--rows`、`--seed`、`--output` 可調。資料為 UTF-8 CSV gzip；壓縮時間戳固定，因此相同依賴版本和 seed 產生相同位元組。

## 生成方式

使用固定、外生的階梯正常票價，結合指數需求強度。每個區間用積分而非中點近似計算均值；抽 Poisson 請求後按剩餘容量接受訂位。已存在的訂位在區間結束時按 Binomial 取消，新訂位當天不取消，退位下一段才能使用。

隱藏參數包括航班需求規模、正／零／負 beta、低／一般／高需求、持續需求跳升和三日短期脈衝。給定這些參數及票價路徑時，請求是分段 NHPP；跨航班混合隨機參數後，不應稱為一個固定強度 NHPP。容量截斷的成交量也不是潛在需求本身。

**這些情境、機型容量、日期、路線、票價、HK$250 必付費用、價格彈性及取消率全部是模擬假設。** 沒有以真實 HK Express 購買、訂位或票價資料校準。目的地代碼只用作不同背景，並不聲稱這些班表是真實航班。API 班表若加入，仍不能將模擬購買標成真實。

## 檔案與資料口徑

| 檔案 | 內容 |
| --- | --- |
| `generated/snapshots.csv.gz` | 每日可觀測快照，正好 200,000 筆 |
| `generated/truth.csv.gz` | 隱藏參數、未截斷請求及失去的需求，只作模擬驗證 |
| `generated/flights.json` | 航班索引和事後摘要；scenario 與 final 欄位不可作預測輸入 |
| `generated/sample.csv` | 前六種情境各 D28–D0 的 174 筆例子 |
| `generated/manifest.json` | 來源、seed、列數、假設、檔案 SHA-256 |

每列 `gross_bookings`、`cancellations` 和 `interval_days` 都描述**進入此快照前剛完成的區間**；當列價格用於接下來的區間。D180 的流量與 exposure 為零；D0 是起飛前兩小時停售，最後區間為 22 小時。`empty_rate = available_seats / capacity` 是未售座位比率，沒有模擬 no-show，不等同真實登機後空座率。

售罄及停售時的票價是空值，不能當成 HK$0。`mandatory_fees` 是此情境的費用設定，售罄也會保留，但不代表可購報價。所有狀態滿足 `booked_seats + available_seats = capacity`；從前一列到下一列滿足已訂位＋新增－取消。

可用 demo：SYN-00001 低需求、SYN-00002 一般、SYN-00003 高需求、SYN-00004 持續跳升、SYN-00005 脈衝、SYN-00006 衰退。情境標籤是隱藏生成背景；預測器只能看到截止觀測日的快照。

後續模型驗證應按航班分組，再保留不同需求形狀和跳變情境作壓力測試。不能用本模擬器產生資料、再以知道真實 beta 的同一公式評估自己。真實客群行為及真實售罄截斷仍需另外校準。

## 初始 NHPP 評估

`evaluate_nhpp.py` 從資料中選擇 180 班，模型只看 D28 當下及更早的快照。D28 之後的成交、最終空座及隱藏潛在需求獨立取出評分。`generated/nhpp_evaluation.json` 同時保留整體、分情境及每班結果。

目前這一版測試的正常需求 MAE 為 29.2813，最近七天速率基線為 34.0488；最終未售座位 MAE 為 10.4363。名義 P90 在這批情境的實際覆蓋率只有 **70.56%**，持續跳升情境為 **16%**。這些結果揭示未知未來衝擊及模型錯配；不可將程式的 P90 宣稱為已驗證 90% 保護。低需求子群的基線誤差也比目前 NHPP 小，並非 NHPP 在每個情境都勝出。

未來若根據這份結果調整模型，應把這份結果視為開發／診斷集，另外生成新情境及 seed 作最終測試。評估腳本不會自動調參，也不把隱藏 beta 或未來票價提供給模型。

## 分開校準與最終測試

`calibrate_nhpp.py` 使用固定 seed 271117，把 180 班校準航班和另外 180 班測試航班分開。先在校準集計算「實際潛在需求 − 原始 P90」的上側次序統計量，取得非負的全局保護餘量 **16 座**，保存後才跑測試集。

測試集的需求 MAE 為 29.2387，七天基線為 35.1529，最終未售座位 MAE 為 13.0674。原始 P90 覆蓋率為 75.00%，加入 16 座保護後為 **83.89%**；其中持續跳升情境仍只有 **47.62%**。因此調整後仍沒有達到 90%，不能改稱已驗證的 90% 保證。未根據這個測試集再調餘量。

`calibration.json` 保存餘量、兩組航班 ID、模型程式及資料 manifest 的 SHA-256。`calibration_evaluation.json` 保存校準原始預測；`nhpp_holdout.json` 保存最終測試及原始／調整後覆蓋率。校準只驗證 D28；短期預測沿用同一完整餘量只是保守工程策略，尚未分天驗證。模型或生成設定改動後，舊校準不應被視為已重新驗證。
