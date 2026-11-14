# 每日機票與空座模擬

目前保存 **680,364筆**合成每日觀測。售票目錄為1,549班／280,364筆，其餘400,000筆保留作獨立NHPP評估。所有票價、訂位、取消及顧客反應都是模擬假設；OAG班表／容量背景不會將它們變成真實航空訂位。

| 目錄 | 筆數／用途 |
|---|---|
| `generated/` | 原200,000筆展示觀測、truth與凍結NHPP報告 |
| `network_generated/` | 222班／40,182筆航線日期補充 |
| `member_demo_generated/` | 222班／40,182筆低／中需求與高需求對照 |
| `validation_extended/` | 兩批各200,000筆獨立擴大評估及逐筆預測 |

原始200,000筆包含1,104班完整D180–D0的181筆，加最後一班D175–D0的176筆。最後一班仍由D180開始模擬，只省略最初五筆輸出；所有航班均有完整D28–D0。

## 生成過程

固定外生的階梯正常票價，結合時間變化的需求強度。每個日區間先積分強度得到期望，再抽Poisson請求，按剩餘容量接受訂位。區間結束時對原有訂位抽Binomial取消；當天新訂位不取消，退位下段才能使用。

隱藏條件包含需求規模、正／零／負增長、持續跳升、短期脈衝與衰退。給定強度路徑時是分段NHPP；混合隨機路徑之後，不再是一條固定強度Poisson過程。容量截斷的實際成交也不等於全部需求。

機型容量、日期、航線、價格、費用、價格彈性與取消率均為情境假設，沒有使用真實HK Express訂位或票價校準。資料生成器知道的truth不能回流當作預測特徵。

## 觀測口徑

- `gross_bookings`、`cancellations`、`interval_days`描述進入此快照前完成的區間；當列價格用於下一區間。
- D180流量和exposure為零。D0是起飛前兩小時停售，最後區間為22小時。
- `empty_rate = available_seats / capacity`是未售座位比率；沒有模擬no-show，不是登機後空座率。
- 售罄／停售時票價空值不能當作零元。費用欄保留不表示仍可訂票。
- 守恆：`booked_seats + available_seats = capacity`；下一日訂位等於上一日加新增再減取消。
- `truth.csv.gz`及航班的事後scenario／final欄只作驗證；模型僅讀截止所選日可見歷史。

每批manifest保存種子、假設、列數與SHA256。已提交的輸入、校準、失敗候選及最終評估均保持凍結，不能為得到較好結果重跑覆寫。

## 現行NHPP驗證

活動入口`backend/forecast.py`在D28使用v2分布與新安全餘量，在D14／D7使用平滑v3。第二輪校準和獨立測試、D28候選回退及覆蓋／放票量的取捨見[NHPP v3說明](../docs/NHPP_V3_REVIEW.md)。較早的[NHPP v2](../docs/NHPP_V2_REVIEW.md)和[1,200班擴大驗證](../docs/EXTENDED_VALIDATION.md)仍是活動預測來源所需的證據，保留原本較差結果。

清理舊定價實驗不會刪除這些NHPP數據。價格學習的目前v5結果另存於[Thompson實驗](../llm_agent/experiments/README.md)，不能將需求保護覆蓋率當成票價收益證明。

## 檢查與新資料

```sh
python -m simulation.generate --validate-only
python scripts/check_publication.py
python scripts/verify_artifacts.py
```

要研究新的生成條件，使用新種子和新的輸出目錄，例如：

```sh
python -m simulation.generate --rows 200000 --seed 20261125 --output data/private/new-simulation
```

不要對已提交final holdout反覆調參或重新執行凍結校準。新模型須另定版本、新校準集和未見測試；擴大相同模擬器的樣本仍不能代替真實購買數據。
