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
