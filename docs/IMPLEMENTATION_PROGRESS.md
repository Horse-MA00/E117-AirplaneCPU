# NHPP 平台實作進度

更新日期：2026-11-14（香港時間）。使用者已授權完整前後端、200000 列模擬資料、LLM 客群情境、測試與 GitHub 上傳。

## 範圍與決定

- 使用 NHPP；LightGBM 延後。
- frontend/：Swiss 視覺、航空公司分析、定價實驗、會員模擬購票。
- backend/：當時可知資料的預測、定價搜尋、HTTP API、SQLite 庫存。
- simulation/：可重現 200000 列每日快照與獨立 truth；不得聲稱真實航空訂位。
- llm_agent/：分層客群、明確提示、合法選擇驗證、可選 live provider。
- 全客群指需求情境覆蓋，並非已取得 HK Express 真實客群分布。
- OAG 只取得航班背景／容量；不能補造真實票價與訂位。

## 進度

1. 已檢視現有文件與舊模擬器，保留舊檔，新增分資料夾實作。
2. 已閱讀 OAG Portal Guide（1 頁）；確認 Flight Info 每30日1000次、每次10結果，Connections 共用配額；Master Data 每30日100次。連接器將設超時、有限重試及本地快取。
3. 已分工並行實作資料、NHPP／策略、前端；本地文件由各模組逐階段更新。
4. 尚未配置 LLM provider 金鑰；先完成可執行的行為模擬及 live 接口，不能將 deterministic 結果冒稱 LLM 呼叫。

詳細進度參見 PROGRESS_DATA.md、PROGRESS_MODELS.md、PROGRESS_FRONTEND.md。驗證與 GitHub 結果在每個完成階段追加。

## 完成資料階段

- 200000 列、1105 條航班歷程，六種需求情境；5項生成器測試通過。
- Git commit b9059da：資料與生成器、完整 manifest 和 SHA256；上傳進行中。
- OAG 實測成功：2026-11-15 UO/HKG 查詢，HTTP200，10筆資料；座位欄位為 seatingCapacity.predicted，不是訂位或確定實際容量。原始資料留在 data/private。
- LLM：14種客群情境、結構化提示、行動與預算驗證、live HTTPS接口已實作；目前沒有LLM金鑰，所以不偽稱已跑真人等效LLM市場。
- 後端：SQLite交易庫存、會員一次付費、同航班防重複購買、同來源HTTP接口已實作，正在整合測試。

## 端到端完成及模型評估

- GitHub階段提交00d9927已包含後端、LLM提示與交易接口；未提交憑證。
- 瀏覽器實測桌面1440px及手機390px：日期切換、192候選、成本更改、14客群、發優惠、入會及購票通過；無JS錯誤及頁面水平溢出。
- 真實HTTP smoke通過：200000列／1105班、192候選、停售NO_OFFER、購票總價、重複拒絕與私有路徑拒絕。
- 獨立180班校準＋180班最終測試：校準餘量16；最終原始P90覆蓋75%，加餘量83.89%，突增47.62%；未根據最終測試重新調參。
- 全倉審查已修正HTTP helper衝突、票價欄位／費用、提早套用策略、成本輸入別名、承諾配額顯示、D1優惠到期時間與過期會員處理。
- 外部請求禁止重新導向以防授權header轉送；錯誤回應清理，失敗不偽造LLM回覆。

## 最終回歸

- 25個backend/LLM/交易測試＋19個資料／舊模擬器測試，合計44個全部通過。
- 兩階段LLM HTTP adapter已用mock驗證呼叫、預算扣減、快取、錯誤清理、redirect拒絕；沒有對外LLM實測。
- 真實HTTP smoke在最後版本再次通過，192候選、停售、會員購票HK$280（30基本票價＋250必付費）、重複與私有檔案拒絕。
- `python -m backend.evaluate`成功產生可重播JSON；JavaScript語法檢查通過。
- 61個已追蹤檔案的本地憑證字串檢查無發現；.env.local及data/private未被追蹤。
- 提供README英文啟動說明、CURRENT_IMPLEMENTATION中文技術文件，以及OPTIMIZATION_REVIEW詳細差異及後續建議。
- 最後瀏覽器交易回歸已確認發出1位後可新增配額減少1；顯示原始75%與加保護餘量83.9%，並指出D28校準範圍。
- 前端提供可重跑smoke.mjs及Playwright lockfile；本機使用已安裝Chromium完成驗證。
- 切換航班／日期時清除舊候選結果，避免在新情境下顯示過期推薦。
