# 實驗傳輸、模擬時間與跨平台執行

> 状态：现行 · 对应代码：`backend/experiment_views.py`、`backend/adaptive_store.py`、`backend/simulation_clock.py`（`flight-as-of-v1`）、`llm_agent/file_lock.py`

更新：2026-11-15。本次維護改進畫面讀取、時間口徑及部署相容性；現行Thompson選價、NHPP分布／保護、提示版本和凍結數據保持原樣。測試的實際執行結果見[維護紀錄](ITERATION_2_PROGRESS.md)。

## 實驗資料按用途讀取

| 介面 | 畫面使用方式 | 返回內容 |
|---|---|---|
| `GET /api/adaptive-pricing/runs` | 選擇Saved experiments或查找發布參考 | 實驗設定、scope、狀態、精簡建議及確認結果；不帶posterior或曲線陣列 |
| `GET /api/adaptive-pricing/runs/{id}/progress` | 執行中約每1.5秒讀取一次 | 心跳、已保存輪數、呼叫計數、錯誤、候選及確認是否已存在 |
| `GET /api/adaptive-pricing/runs/{id}/view` | 初次載入、輪次／候選／確認／狀態改變或手動刷新 | 畫面需要的曲線、價格、結果、每輪摘要及顧客理由；省略完整observation、重複prompt context和posterior |
| `GET /api/adaptive-pricing/runs/{id}`、`/{id}/export` | 明確索取完整報告或匯出 | 原本完整報告；既有匯出大小限制仍有效 |
| `GET /api/adaptive-pricing/runs/{id}/analysis-attempts?round=N` | 打開某輪Analyst原始回覆 | 該輪脫敏原文及失敗／重試診斷；一般列表不攜帶原始回覆 |

投影只選取報告中已保存的值，不重新計算建議價、購買標籤或曲線點。Member feedback仍可逐人查看購買／拒絕理由；完整證據和原始回覆保持可查。任何讀取都不觸發provider呼叫或恢復失敗實驗。

私有SQLite新增 `adaptive_run_views` 保存小型摘要和心跳，保留 `adaptive_runs` 原四欄報告結構。正常保存會同一交易更新投影；舊資料庫第一次讀取時補建缺少的投影。資料庫trigger在其他寫入者直接新增、更新或刪除報告時清除舊投影，避免以過時結果回應。投影可重建，不能當成報告寫回。

一般心跳／列表不解碼完整私有報告；第一次補建舊紀錄仍需讀原文。`view`仍會讀取完整且已核驗的報告再精簡傳輸，因此這項改進降低日常網絡傳輸和輪詢解析量，並非把所有詳細讀取變成常數成本。公開實驗在啟動時核驗並快取摘要／心跳，詳情按需核驗讀取；不匯入私有資料庫，私有同ID紀錄依然優先。

若執行心跳超過120秒且無其他程序持有實驗鎖，程式重新取得完整報告，核對其仍然過期後才標記interrupted。不能把小型投影保存成完整報告，也不能在另一程序仍持鎖時誤終止它。

## 航班時間與會員時間分開

新航班交易由服務注入目錄班表，使用 `flight-as-of-v1`：

```text
D28 / D14 / D7 模擬時刻 = 目錄起飛時刻 − 對應天數
D0 模擬時刻 = 目錄起飛時刻 − 2小時
所有輪次共同停售時刻 = 目錄起飛時刻 − 2小時
```

起飛時間必須帶時區；顯示統一用香港時間。模擬時刻沿D28→D14→D7→D0前進，不取決於電腦啟動時刻。重新啟動服務不會延長優惠；瀏覽歷史預測不會倒退交易時鐘。發布和購票仍在交易內檢查有效未售配額、風險上限及庫存。

已存在的優惠或時鐘保留 `legacy-wall-clock-v0` 及原本絕對到期值，避免把舊訂單和配額重新解釋為另一時間。API公開 `clock_version`、`time_basis`、`simulation_as_of`、`sales_cutoff_at` 和 `membership_time_basis`。獨立測試或舊工具沒有注入班表resolver時使用舊口徑；已保存的新時鐘仍可由其固定班表欄位恢復。

會員六個曆月有效期、登入session、審計記錄時間仍用真實時間，並不隨航班時鐘前進。近期366班的資料截止固定在2026-11-15；未觀測的輪次保持不可用，時間經過不會補出新的訂位歷史。這些規則改進原型的一致性，不宣稱航班模擬狀態就是即時真實庫存。

## Windows相容性與依賴

相對檔案路徑在新增prompt／provenance metadata中統一為POSIX斜線，避免Windows反斜線使manifest查找或比對失敗；歷史實驗中的來源哈希不回填。受影響的可變工具和證據讀取明確使用UTF-8，避免繁體中文Windows預設CP950誤解碼英文／中文JSON及壓縮記錄。

現有程序鎖在Unix用 `fcntl`，Windows用 `msvcrt`；這次不新增另一套鎖或解除併發保護。Windows安裝requirements會補裝 `tzdata`，以支援 `ZoneInfo('Asia/Hong_Kong')`。程式未使用的Matplotlib及其容器環境設定／依賴已移除，NumPy保留。

原生Windows操作方式為 `py -3 -m venv .venv`、PowerShell執行 `.venv\Scripts\Activate.ps1`，再使用README所列pip安裝及Python啟動命令。跨平台單元檢查不能替代真實Windows整機驗證；實測平台與結果分開記錄。

## 清理邊界

移除已退役共享市場的孤立summary、舊會員展示attestation及仍呼叫退休API的 `scripts/smoke_three_round_api.py`；現行三輪規則繼續由後端測試覆蓋。清理不刪除目前24份v5公開實驗、NHPP校準／驗證、原始觀測或會員交易。近期資料目錄已納入制品核驗，維持原始字節。
