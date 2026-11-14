# OAG 公開文件逐頁檢查清單

> 状态：记录（2026-11-11），内容不再修改


查核日期：2026-11-11（香港時間）。來源為 [官方完整索引](https://knowledge.oag.com/llms.txt)。

**534/534 個索引項目均成功取得有效 Markdown 正文；0 個仍受阻。** 這個數量包括分類目錄、文章及集中更新中的重複主題，不是 534 個 API 或資料集。

檢查分兩層：所有頁面均作章節／用途篩查及正文關鍵詞檢索（booking、fare、inventory、load factor、snapshot 等）；標示「深入」的頁面另核對與問題相關的欄位、口徑、時間粒度或方法。其餘頁標示「篩查」，不宣稱逐字精讀每個 UI 教學。頁面取得成功本身不是欄位適用性的證據，結論以 [研究報告](OAG_API_DATA_AUDIT_2026-11-11.md) 的來源與推論為準。

頁面中的影片／圖示及外鏈下載檔未全部另行展開；付費介面、帳戶權限及 live API 回應未測試。原始正文僅暫存在 OS temporary directory，repo 保留本清單與研究摘要。

共 81 個重點頁標示深入核對，其餘 453 個為篩查。

## Flight Info Direct

48 個索引項目；全部正文取得成功。

| 編號 | 官方頁面 | 檢查層級 | 與本案的判讀 |
| ---: | --- | --- | --- |
| 001 | [Flight Info Direct](https://knowledge.oag.com/docs/flight-info-direct) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 002 | [1. Getting Started](https://knowledge.oag.com/docs/getting-started-3) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 003 | [Flight Info Direct Useful Queries](https://knowledge.oag.com/docs/flight-info-direct-useful-queries) | 深入 | Snowflake 範例包含 bookings／fares；不同 view 的權限須分別確認。 |
| 004 | [Flight Info Direct Quick Start Guide](https://knowledge.oag.com/docs/flight-info-direct-quick-start-guide) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 005 | [Can Flight Info Direct query results be downloaded?](https://knowledge.oag.com/docs/can-flight-info-direct-query-results-be-downloaded) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 006 | [How often are the data sets updated?](https://knowledge.oag.com/docs/how-often-are-the-data-sets-updated) | 深入 | 舊 monthly FAQ；Weekly 新版以 2026 release 為準。 |
| 007 | [2. Using Snowflake](https://knowledge.oag.com/docs/using-snowflake) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 008 | [Understanding Snowflake Credits](https://knowledge.oag.com/docs/understanding-snowflake-credits) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 009 | [How do I connect Flight Info Direct to my system?](https://knowledge.oag.com/docs/how-do-i-connect-flight-info-direct-to-my-system) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 010 | [Why is my query taking so long to complete?](https://knowledge.oag.com/docs/why-is-my-query-taking-so-long-to-complete) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 011 | [What is a schedule snapshot (FILE_DATE)?](https://knowledge.oag.com/docs/what-is-a-schedule-snapshot-file-date) | 深入 | 時刻 FILE_DATE 快照，不是訂位交易快照。 |
| 012 | [Does Flight Info Direct require a high level of technical skills?](https://knowledge.oag.com/docs/does-flight-info-direct-require-a-high-level-of-technical-skills) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 013 | [What data visualisation/ business intelligence (BI) tools are supported by Flight Info Direct?](https://knowledge.oag.com/docs/what-data-visualisation-business-intelligence-bi-tools-are-supported-by-flight-info-direct) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 014 | [Do I need to be a Snowflake customer?](https://knowledge.oag.com/docs/do-i-need-to-be-a-snowflake-customer) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 015 | [Parsing JSON Data in Snowflake](https://knowledge.oag.com/docs/parsing-json-data-in-snowflake) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 016 | [Linking Schedules and Status Data in Flight Info Direct](https://knowledge.oag.com/docs/linking-schedules-and-status-data) | 深入 | 航班識別與容量可連接，沒有證明 booking 真實全量。 |
| 017 | [3. Data Sets](https://knowledge.oag.com/docs/data-sets) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 018 | [Schedules Direct: Data Fields Explained](https://knowledge.oag.com/docs/schedules-direct-data-fields-explained) | 深入 | 時刻與容量資料。 |
| 019 | [Status Direct: Data Fields Explained](https://knowledge.oag.com/docs/status-direct-data-fields-explained) | 深入 | 運行狀態及容量，actual seats 不是已售座位。 |
| 020 | [Passenger Bookings: Data Fields Explained](https://knowledge.oag.com/docs/passenger-bookings-data-fields-explained) | 深入 | Weekly 訂位日／航班資料；月度 Load Factor 與全渠道／版本限制。 |
| 021 | [Passenger Bookings for Airlines: Data Fields Explained](https://knowledge.oag.com/docs/passenger-bookings-for-airlines-data-fields-explained) | 深入 | Airlines 版另有授權與 view 範圍。 |
| 022 | [Connections Direct: Data Fields Explained](https://knowledge.oag.com/docs/connections-direct-data-fields-explained) | 深入 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 023 | [Emissions Schedules: Data Fields Explained](https://knowledge.oag.com/docs/emissions-schedules-data-fields-explained) | 深入 | 耗油／排放估算不是乘客燃油附加費。 |
| 024 | [Emissions Status: Data Fields Explained](https://knowledge.oag.com/docs/emissions-status-data-fields-explained) | 深入 | 耗油／排放估算不是乘客燃油附加費。 |
| 025 | [Market Trends: Data Fields Explained](https://knowledge.oag.com/docs/market-trends-data-fields-explained) | 深入 | 按 observation/departure week 聚合票價。 |
| 026 | [Master Data: Equipment Data Fields Explained](https://knowledge.oag.com/docs/master-data-equipment-data-fields-explained) | 深入 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 027 | [Master Data: Locations Data Fields Explained](https://knowledge.oag.com/docs/master-data-locations-data-fields-explained) | 深入 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 028 | [Master Data: Carriers Data Fields Explained](https://knowledge.oag.com/docs/master-data-carriers-data-fields-explained) | 深入 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 029 | [Fleet: Data Fields Explained](https://knowledge.oag.com/docs/fleet-data-fields-explained) | 深入 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 030 | [MCT: Data Fields Explained](https://knowledge.oag.com/docs/mct-data-fields-explained) | 深入 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 031 | [4. Release Notes](https://knowledge.oag.com/docs/release-note-1) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 032 | [Q3 2026 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q3-2026-release-notes-flight-info-direct) | 深入 | Predicted seats 是容量；Adjusted FILE_TYPE 為估算成熟度。 |
| 033 | [Q1 2026 Release Notes - Passenger Booking Data](https://knowledge.oag.com/docs/q1-2026-release-notes-passenger-booking-data) | 深入 | Weekly Unadjusted 新版：四批／月、航班級、2024 起。 |
| 034 | [Q4 2025 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q4-2025-release-notes-flight-info-direct) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 035 | [Q2 2025 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q2-2025-release-notes-flight-info-direct) | 深入 | Market Trends 是週聚合價格。 |
| 036 | [Q1 2025 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q1-2025-release-notes-flight-info-direct) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 037 | [Q4 2024 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q4-2024-release-notes-flight-info-direct) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 038 | [Q3 2024 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q3-2024-release-notes-flight-info-direct) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 039 | [Q2 2024 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q2-2024-release-notes-flight-info-direct) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 040 | [Q1 2024 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q1-2024-release-notes-flight-info-direct) | 深入 | Booking／Segment 與模型 Load Factor 交付，不是 Flight Info API 欄位。 |
| 041 | [Q3 2023 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q3-2023-release-notes-flight-info-direct) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 042 | [Q2 2023 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q2-2023-release-notes-flight-info-direct) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 043 | [Q4 2022 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q4-2022-release-notes-flight-info-direct) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 044 | [Q2 2022 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q2-2022-release-notes-flight-info-direct) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 045 | [Q1 2022 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q1-2022-release-notes-flight-info-direct) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 046 | [5. Administration and Support](https://knowledge.oag.com/docs/administration-and-support) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 047 | [What happens when I hit the credit limit in my reader account?](https://knowledge.oag.com/docs/what-happens-when-i-hit-the-credit-limit-in-my-reader-account) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |
| 048 | [How do I reset my password?](https://knowledge.oag.com/docs/how-do-i-reset-my-password) | 篩查 | Snowflake 使用、資料字典、更新或支援；相關核心字典另列深入核對。 |

## Flight Info API

34 個索引項目；全部正文取得成功。

| 編號 | 官方頁面 | 檢查層級 | 與本案的判讀 |
| ---: | --- | --- | --- |
| 049 | [Flight Info API](https://knowledge.oag.com/docs/%EF%B8%8Fflight-info-api) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 050 | [1. Getting Started](https://knowledge.oag.com/docs/getting-started-2) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 051 | [Flight Info API - Getting Started](https://knowledge.oag.com/docs/flight-info-api-getting-started) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 052 | [Flight Info API - Creating an Account](https://knowledge.oag.com/docs/flight-info-api-creating-an-account) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 053 | [Flight Info API - Requesting a Trial](https://knowledge.oag.com/docs/flight-info-api-requesting-a-trial) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 054 | [Flight Info API - Requesting a subscription](https://knowledge.oag.com/docs/flight-info-api-requesting-a-subscription) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 055 | [Master Data API Samples](https://knowledge.oag.com/docs/master-data-api-samples) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 056 | [Migration](https://knowledge.oag.com/docs/migration-1) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 057 | [Fvxml](https://knowledge.oag.com/docs/flight-info-api-migration-fvxml) | 深入 | API 遷移及額外 content 權限；沒有證實訂位／票價歷史。 |
| 058 | [2. Using the API](https://knowledge.oag.com/docs/using-the-api) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 059 | [Flight Info API - Response Layout & Descriptions](https://knowledge.oag.com/docs/flight-info-api-response-layout-descriptions) | 深入 | 完整 Flight Info response：時刻、艙等代碼、容量、狀態。 |
| 060 | [Flight Info API - Content Parameters](https://knowledge.oag.com/docs/flight-info-api-content-parameters) | 深入 | Seats／ActualSeats 定義為容量。 |
| 061 | [Flight Info Connections API - Response Layout & Descriptions](https://knowledge.oag.com/docs/flight-info-connections-api-response-layout-descriptions-1) | 深入 | 轉機行程及航段資訊；非售票交易。 |
| 062 | [Switching from Flight Info API v1 to v2: A Step-by-Step Guide](https://knowledge.oag.com/docs/switching-from-flight-info-api-v1-to-v2-a-step-by-step-guide) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 063 | [Schedules API - Response Layout & Descriptions](https://knowledge.oag.com/docs/schedules-api-response-layout-descriptions) | 深入 | 時刻有效期、艙等及容量。 |
| 064 | [Master Data API - Response Layout & Descriptions](https://knowledge.oag.com/docs/master-data-api-response-layout-descriptions) | 深入 | 航空公司、機場、機型參照資料。 |
| 065 | [3. Release Notes](https://knowledge.oag.com/docs/release-notes-1) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 066 | [Q3 2026 Release Notes](https://knowledge.oag.com/docs/flight-info-api-q3-2026-release-notes) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 067 | [Q2 2026 Release Notes](https://knowledge.oag.com/docs/flight-info-api-q2-2026-release-notes) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 068 | [Q1 2026 Release Notes](https://knowledge.oag.com/docs/flight-info-api-q1-2026-release-notes) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 069 | [Q2 2025 Release Notes](https://knowledge.oag.com/docs/flight-info-api-q2-2025-release-notes) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 070 | [Q4 2024 Release Notes](https://knowledge.oag.com/docs/flight-info-api-q4-2024-release-notes) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 071 | [Q3 2024 Release Notes](https://knowledge.oag.com/docs/flight-info-api-q3-2024-release-notes) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 072 | [Q2 2024 Release Notes](https://knowledge.oag.com/docs/flight-info-api-q2-2024-release-notes) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 073 | [Q1 2024 Release Notes](https://knowledge.oag.com/docs/flight-info-api-q1-2024-release-notes) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 074 | [Q4 2023 Release Notes](https://knowledge.oag.com/docs/flight-info-api-q4-2023-release-notes) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 075 | [Q2 2023 Release Notes](https://knowledge.oag.com/docs/flight-info-api-q2-2023-release-notes) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 076 | [4. Flight Info API FAQs](https://knowledge.oag.com/docs/flight-info-api-frequently-asked-questions) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 077 | [What are the different access levels for the API?](https://knowledge.oag.com/docs/what-are-the-different-access-levels-for-the-api) | 深入 | 額外 content 可能另收費；產品權限並不共用。 |
| 078 | [How am I charged for using flight info API?](https://knowledge.oag.com/docs/how-am-i-charged-for-using-flight-info-api) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 079 | [Can I start using the API as soon as I sign up?](https://knowledge.oag.com/docs/can-i-start-using-the-api-as-soon-as-i-sign-up) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 080 | [What are the Flight Info API Free Tier usage limits?](https://knowledge.oag.com/docs/how-long-does-the-free-trial-last-and-how-much-data-can-i-return) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 081 | [How can I trial the Flight Info Connections API](https://knowledge.oag.com/docs/how-can-i-trial-the-flight-info-connections-api) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |
| 082 | [How frequently is the data updated in the API?](https://knowledge.oag.com/docs/how-frequently-is-the-data-updated-in-the-api) | 篩查 | 帳戶／介面／版本／FAQ；未記載補足核心 booking／fare 歷史。 |

## Flight Info Alerts

54 個索引項目；全部正文取得成功。

| 編號 | 官方頁面 | 檢查層級 | 與本案的判讀 |
| ---: | --- | --- | --- |
| 083 | [Flight Info Alerts](https://knowledge.oag.com/docs/flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 084 | [1. Getting Started](https://knowledge.oag.com/docs/getting-started) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 085 | [Overview](https://knowledge.oag.com/docs/flight-info-alerts-overview) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 086 | [Developer Portal](https://knowledge.oag.com/docs/flight-info-alerts-developer-portal) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 087 | [Complete Profile](https://knowledge.oag.com/docs/flight-info-alerts-complete-profile) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 088 | [Create Alert](https://knowledge.oag.com/docs/flight-info-alerts-create-alert) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 089 | [Connect To Event Hub](https://knowledge.oag.com/docs/flight-info-alerts-connect-to-event-hub) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 090 | [Http Push(beta)](https://knowledge.oag.com/docs/flight-info-alerts-http-pushbeta) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 091 | [Change Indicators](https://knowledge.oag.com/docs/flight-info-alerts-change-indicators) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 092 | [Event Samples](https://knowledge.oag.com/docs/event-samples) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 093 | [V1](https://knowledge.oag.com/docs/v1) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 094 | [Schedule Events](https://knowledge.oag.com/docs/flight-info-alerts-event-samples-v1-schedule-events) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 095 | [Status Events](https://knowledge.oag.com/docs/flight-info-alerts-event-samples-v1-status-events) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 096 | [V2](https://knowledge.oag.com/docs/v2) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 097 | [Schedule Events](https://knowledge.oag.com/docs/flight-info-alerts-event-samples-v2-schedule-events) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 098 | [Status Events](https://knowledge.oag.com/docs/flight-info-alerts-event-samples-v2-status-events) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 099 | [Schedules Field Definitions](https://knowledge.oag.com/docs/flight-info-alerts-event-samples-schedules-field-definitions) | 深入 | Alerts 有 bookingClasses.quantity，但語義不足以確認全機剩餘庫存。 |
| 100 | [Status Field Definitions](https://knowledge.oag.com/docs/flight-info-alerts-event-samples-status-field-definitions) | 深入 | 狀態事件 capacity 定義不是已售／登機人數。 |
| 101 | [Migration](https://knowledge.oag.com/docs/migration) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 102 | [Fv Dynamic](https://knowledge.oag.com/docs/flight-info-alerts-migration-fv-dynamic) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 103 | [Fnb](https://knowledge.oag.com/docs/flight-info-alerts-migration-fnb) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 104 | [Fv Batch](https://knowledge.oag.com/docs/flight-info-alerts-migration-fv-batch) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 105 | [Fv Batch Aadoptimal](https://knowledge.oag.com/docs/flight-info-alerts-migration-fv-batch-aadoptimal) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 106 | [2. Release Notes](https://knowledge.oag.com/docs/release-notes) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 107 | [Q4 2026 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q4-2026-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 108 | [Q3 2026 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q3-2026-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 109 | [Q1 2026 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q1-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 110 | [Q3 and Q4 2025 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q3-and-q4-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 111 | [Q2 2025 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q2-2025-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 112 | [Q1 2025 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q1-2025-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 113 | [Q4 2024 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q4-2024-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 114 | [Q3 2024 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q3-2024-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 115 | [Q2 2024 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q2-2024-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 116 | [Q1 2024 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q1-2024-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 117 | [Q4 2023 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q4-2023-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 118 | [May 2023 Minor Release - Status Alerts Marketing & Codeshare information](https://knowledge.oag.com/docs/may-2023-minor-release-status-alerts-marketing-codeshare-information) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 119 | [Apr 2023 Minor Release - GA/Unscheduled Data](https://knowledge.oag.com/docs/apr-2023-minor-release-gaunscheduled-data) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 120 | [Q1 2023 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q1-2023-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 121 | [Feb 2023 Major Release - Status Alerts](https://knowledge.oag.com/docs/feb-2023-major-release-status-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 122 | [Q4 2022 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q4-2022-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 123 | [Q3 2022 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q3-2022-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 124 | [Q2 2022 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q2-2022-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 125 | [Q1 2022 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q1-2022-release-notes-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 126 | [Aug 2023 Minor Release - Flight Info Alerts Change Indicators](https://knowledge.oag.com/docs/aug-2023-minor-release-flight-info-alerts-change-indicators) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 127 | [3. Flight Info Alerts FAQs](https://knowledge.oag.com/docs/flight-info-alerts-frequently-asked-questions) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 128 | [What type of alerts can I create?](https://knowledge.oag.com/docs/what-type-of-alerts-can-i-create) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 129 | [Do I need a subscription with Azure to use Flight Info Alerts?](https://knowledge.oag.com/docs/do-i-need-a-subscription-with-azure-to-use-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 130 | [How long are events kept in the event hubs?](https://knowledge.oag.com/docs/how-long-are-events-kept-in-the-event-hubs) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 131 | [Why was my Flight Info Alerts subscription request rejected?](https://knowledge.oag.com/docs/why-was-my-flight-info-alerts-subscription-request-rejected) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 132 | [Are change events sent for marketing flights or codeshare services?](https://knowledge.oag.com/docs/are-change-events-sent-for-marketing-flights-or-codeshare-services) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 133 | [How does Flight Info Alerts Work?](https://knowledge.oag.com/docs/how-does-flight-info-alerts-work) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 134 | [What is an Event Hub?](https://knowledge.oag.com/docs/what-is-an-event-hub) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 135 | [I have another application that needs to consume Event Hub in isolation. Is this possible?](https://knowledge.oag.com/docs/i-have-another-application-that-needs-to-consume-event-hub-in-isolation-is-this-possible) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |
| 136 | [How am I charged for flight info alerts?](https://knowledge.oag.com/docs/how-am-i-charged-for-flight-info-alerts) | 篩查 | 時刻／狀態事件、遷移、更新或支援；非已驗證的售票事件。 |

## Analyser／Analyser+

217 個索引項目；全部正文取得成功。

| 編號 | 官方頁面 | 檢查層級 | 與本案的判讀 |
| ---: | --- | --- | --- |
| 137 | [Analyser](https://knowledge.oag.com/docs/analyser) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 138 | [Moving to Analyser+](https://knowledge.oag.com/docs/moving-to-analyser) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 139 | [Schedules Analyser in Analyser+](https://knowledge.oag.com/docs/schedules-analyser-in-analyser) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 140 | [Schedules Analyser](https://knowledge.oag.com/docs/schedules-analyser) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 141 | [1. Introduction to Schedules Analyser](https://knowledge.oag.com/docs/11-about-the-tool) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 142 | [2. Getting started](https://knowledge.oag.com/docs/2-getting-started) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 143 | [3. Reports](https://knowledge.oag.com/docs/3-reports) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 144 | [Schedules Capacity Report](https://knowledge.oag.com/docs/31-schedules-capacity-report) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 145 | [Capacity Report Parameters](https://knowledge.oag.com/docs/capacityreportparameters) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 146 | [Schedules Capacity Report Outputs](https://knowledge.oag.com/docs/312-report-outputs) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 147 | [Saving Reports and Scheduling](https://knowledge.oag.com/docs/313-saving-reports-and-scheduling) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 148 | [Schedules Bank Structure Report](https://knowledge.oag.com/docs/32-schedules-bank-structure-report) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 149 | [Bank Structure Report Outputs](https://knowledge.oag.com/docs/321-report-outputs) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 150 | [Schedules Changes Report](https://knowledge.oag.com/docs/33-schedules-changes-report) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 151 | [Schedules Changes Report Parameters](https://knowledge.oag.com/docs/331-schedules-changes-report) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 152 | [Power Table Report](https://knowledge.oag.com/docs/34-power-table-report) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 153 | [Top X Report](https://knowledge.oag.com/docs/35-top-x-report) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 154 | [4. Schedules Analyser FAQs](https://knowledge.oag.com/docs/schedules-analyser-faqs) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 155 | [Which Internet browser works best with OAG Schedules Analyser?](https://knowledge.oag.com/docs/which-internet-browser-works-best-with-oag-schedules-analyser) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 156 | [When is the data in OAG Schedules Analyser updated?](https://knowledge.oag.com/docs/when-is-the-data-in-oag-schedules-analyser-updated) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 157 | [What is the difference between pulling Published Carrier, Operating Carrier and Marketing Carrier?](https://knowledge.oag.com/docs/what-is-the-difference-between-pulling-published-carrier-operating-carrier-and-marketing-carrier) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 158 | [What is the difference between an O&D Pair and a Market Pair?](https://knowledge.oag.com/docs/what-is-the-difference-between-an-od-pair-and-a-market-pair) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 159 | [When I log out of Schedules Analyser, am I also logged out of OAG Analyser?](https://knowledge.oag.com/docs/when-i-log-out-of-schedules-analyser-am-i-also-logged-out-of-oag-analyser) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 160 | [Are there any size limits on downloading and exporting the report?](https://knowledge.oag.com/docs/are-there-any-size-limits-on-downloading-and-exporting-the-report) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 161 | [When selecting airport or city names or codes, there are sometimes more than one which looks right. Which one should I use?](https://knowledge.oag.com/docs/when-selecting-airport-or-city-names-or-codes-there-are-sometimes-more-than-one-which-looks-right-which-one-should-i-use) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 162 | [In the OAG Schedules Capacity report what counts as a hub airport?](https://knowledge.oag.com/docs/in-the-oag-schedules-capacity-report-what-counts-as-a-hub-airport) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 163 | [OAG Schedules Analyser offers a selection of pre-determined regions. What if I want to define my own regions?](https://knowledge.oag.com/docs/oag-schedules-analyser-offers-a-selection-of-pre-determined-regions-what-if-i-want-to-define-my-own-regions) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 164 | [In the ’Carrier Category’ field how does OAG decide if an airline is a mainstream carrier or a low cost carrier?](https://knowledge.oag.com/docs/in-the-carrier-category-field-how-does-oag-decide-if-an-airline-is-a-mainstream-carrier-or-a-low-cost-carrier) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 165 | [Can I select data for a group of routes, rather than one route at a time?](https://knowledge.oag.com/docs/can-i-select-data-for-a-group-of-routes-rather-than-one-route-at-a-time) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 166 | [Where surface data is included in OAG Schedules Analyser, where does this data come?](https://knowledge.oag.com/docs/where-surface-data-is-included-in-oag-schedules-analyser-where-does-this-data-come) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 167 | [What does the ‘User Preferences’ option do in the ‘My OAG’ drop down box in OAG Schedules Analyser?](https://knowledge.oag.com/docs/what-does-the-user-preferences-option-do-in-the-my-oag-drop-down-box-in-oag-schedules-analyser) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 168 | [Do I need to select an option or enter a selection in every box in the query screen?](https://knowledge.oag.com/docs/do-i-need-to-select-an-option-or-enter-a-selection-in-every-box-in-the-query-screen) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 169 | [Why does it sometimes take a while for the data to be extracted?](https://knowledge.oag.com/docs/why-does-it-sometimes-take-a-while-for-the-data-to-be-extracted) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 170 | [5. Schedules Analyser Glossary](https://knowledge.oag.com/docs/schedules-analyser-glossary-24) | 篩查 | Schedules 報表、容量、操作或說明。 |
| 171 | [Traffic Analyser](https://knowledge.oag.com/docs/traffic) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 172 | [1. Introduction](https://knowledge.oag.com/docs/traffic-1-introduction) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 173 | [About Traffic Analyser](https://knowledge.oag.com/docs/11-about-the-tool-2) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 174 | [Traffic Analyser Key Features](https://knowledge.oag.com/docs/traffic-12-key-features) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 175 | [Traffic Analyser Data Source](https://knowledge.oag.com/docs/13-source-of-data) | 深入 | GDS／估算市場／票價來源與月度時效。 |
| 176 | [2. Getting Started](https://knowledge.oag.com/docs/20-getting-started) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 177 | [3. Reports](https://knowledge.oag.com/docs/traffic-3-reports) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 178 | [O&D Report](https://knowledge.oag.com/docs/31-od-report) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 179 | [O&D Report Parameters](https://knowledge.oag.com/docs/traffic-311-parameters) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 180 | [O&D Report Outputs](https://knowledge.oag.com/docs/traffic-312-report-outputs) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 181 | [Segment Report](https://knowledge.oag.com/docs/32-segment-report) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 182 | [Power Table Report](https://knowledge.oag.com/docs/traffic-34-power-table-report) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 183 | [Top X Report](https://knowledge.oag.com/docs/traffic-35-top-x-report) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 184 | [Connections Report](https://knowledge.oag.com/docs/36-connections-report) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 185 | [Mix Report](https://knowledge.oag.com/docs/33-mix-report) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 186 | [4. Traffic Analyser Glossary](https://knowledge.oag.com/docs/glossary-of-terms) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 187 | [5. Traffic Analyser FAQs](https://knowledge.oag.com/docs/traffic-faqs) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 188 | [Which Internet browser works best with OAG Traffic Analyser?](https://knowledge.oag.com/docs/which-internet-browser-works-best-with-oag-traffic-analyser) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 189 | [When is the data in OAG Traffic Analyser updated?](https://knowledge.oag.com/docs/when-is-the-data-in-oag-traffic-analyser-updated) | 深入 | Traffic Analyser 月度載入延遲，不適用於新版 Weekly view 的全部範圍。 |
| 190 | [What is the difference between Adjusted Bookings and Unadjusted Bookings?](https://knowledge.oag.com/docs/what-is-the-difference-between-adjusted-bookings-and-unadjusted-bookings) | 深入 | Adjusted 是模型估算；Unadjusted 是 MIDT。 |
| 191 | [Do I need to select an option or enter a selection in every box in the query screen?](https://knowledge.oag.com/docs/do-i-need-to-select-an-option-or-enter-a-selection-in-every-box-in-the-query-screen-2) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 192 | [Why does it sometimes take a while for the data to be extracted?](https://knowledge.oag.com/docs/why-does-it-sometimes-take-a-while-for-the-data-to-be-extracted-1) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 193 | [Why is my report taking so long to process?](https://knowledge.oag.com/docs/why-is-my-report-taking-so-long-to-process-1) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 194 | [What is the difference between one-way and two-way?](https://knowledge.oag.com/docs/what-is-the-difference-between-one-way-and-two-way) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 195 | [What is the difference between O&D and Segment in the ‘traffic type’?](https://knowledge.oag.com/docs/what-is-the-difference-between-od-and-segment-in-the-traffic-type) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 196 | [Why does the data sometimes show adjusted bookings but no average fares, and sometimes there are average fares but no bookings?](https://knowledge.oag.com/docs/why-does-the-data-sometimes-show-adjusted-bookings-but-no-average-fares-and-sometimes-there-are-average-fares-but-no-bookings) | 深入 | 票價與 bookings 來源不同；零值可能代表無資料。 |
| 197 | [How is the average fare calculated?](https://knowledge.oag.com/docs/how-is-the-average-fare-calculated) | 深入 | Average fare 口徑與 online observed fare 不同。 |
| 198 | [Why are the only time periods which can be selected ‘year’, ‘quarter’ and ‘month’? There is no option to select a ‘week’ or a ‘day’.](https://knowledge.oag.com/docs/why-are-the-only-time-periods-which-can-be-selected-year-quarter-and-month-there-is-no-option-to-select-a-week-or-a-day) | 深入 | 舊 Traffic Analyser 最小月粒度；不泛化到新 Weekly view。 |
| 199 | [What is the default Minimum Connect Time (MCT)?](https://knowledge.oag.com/docs/what-is-the-default-minimum-connect-time-mct-1) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 200 | [What is meant by ‘Mix’ and ‘Point of interest’ in the Mix Report?](https://knowledge.oag.com/docs/what-is-meant-by-mix-and-point-of-interest-in-the-mix-report) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 201 | [What is the Point of Origin in the O&D report?](https://knowledge.oag.com/docs/what-is-the-point-of-origin-in-the-od-report) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 202 | [Why is the data in different tabs sometimes different?](https://knowledge.oag.com/docs/why-is-the-data-in-different-tabs-sometimes-different) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 203 | [What is the Advanced Carrier function?](https://knowledge.oag.com/docs/what-is-the-advanced-carrier-function) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 204 | [What is the Unserved function?](https://knowledge.oag.com/docs/what-is-the-unserved-function) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 205 | [When I log out of Traffic Analyser, am I also logged out of OAG Analyser?](https://knowledge.oag.com/docs/when-i-log-out-of-traffic-analyser-am-i-also-logged-out-of-oag-analyser) | 篩查 | Traffic 分析、報表、口徑或操作；原始需求與估算須區分。 |
| 206 | [Connections Analyser](https://knowledge.oag.com/docs/connections) | 篩查 | 轉機網絡與行程組合分析。 |
| 207 | [1. Introduction](https://knowledge.oag.com/docs/1-introduction-2) | 篩查 | 轉機網絡與行程組合分析。 |
| 208 | [About Connections Analyser](https://knowledge.oag.com/docs/11-about-the-tool-1) | 篩查 | 轉機網絡與行程組合分析。 |
| 209 | [Key Features](https://knowledge.oag.com/docs/12-key-features-1) | 篩查 | 轉機網絡與行程組合分析。 |
| 210 | [2. Getting Started](https://knowledge.oag.com/docs/2-getting-started-1) | 篩查 | 轉機網絡與行程組合分析。 |
| 211 | [3. Reports](https://knowledge.oag.com/docs/3-reports-1) | 篩查 | 轉機網絡與行程組合分析。 |
| 212 | [Connections Analysis Report](https://knowledge.oag.com/docs/31-connections-analysis-report) | 篩查 | 轉機網絡與行程組合分析。 |
| 213 | [Connections Analysis Report Parameters](https://knowledge.oag.com/docs/311-parameters) | 篩查 | 轉機網絡與行程組合分析。 |
| 214 | [Connections Analysis Report Options](https://knowledge.oag.com/docs/312-report-options) | 篩查 | 轉機網絡與行程組合分析。 |
| 215 | [Worked Examples – Custom MCTs, Phantom Flights & QSI](https://knowledge.oag.com/docs/315-worked-examples-custom-mcts-phantom-flights-qsi) | 篩查 | 轉機網絡與行程組合分析。 |
| 216 | [Missed Connections Report](https://knowledge.oag.com/docs/32-missed-connections-report) | 篩查 | 轉機網絡與行程組合分析。 |
| 217 | [Missed Connections Report Parameters](https://knowledge.oag.com/docs/321-report-parameters) | 篩查 | 轉機網絡與行程組合分析。 |
| 218 | [Worked Example – Missed Connections Report](https://knowledge.oag.com/docs/322-worked-example-missed-connections-report) | 篩查 | 轉機網絡與行程組合分析。 |
| 219 | [4. Connections Analyser Glossary of Terms](https://knowledge.oag.com/docs/connections-analyser-glossary-of-terms) | 篩查 | 轉機網絡與行程組合分析。 |
| 220 | [5. Connections Analyser FAQs](https://knowledge.oag.com/docs/connections-faqs) | 篩查 | 轉機網絡與行程組合分析。 |
| 221 | [Which Internet browser works best with OAG Connections Analyser?](https://knowledge.oag.com/docs/which-internet-browser-works-best-with-oag-connections-analyser) | 篩查 | 轉機網絡與行程組合分析。 |
| 222 | [Do I need to select an option or enter a selection in every box in the query screen?](https://knowledge.oag.com/docs/do-i-need-to-select-an-option-or-enter-a-selection-in-every-box-in-the-query-screen-1) | 篩查 | 轉機網絡與行程組合分析。 |
| 223 | [What is the source of data in Connections Analyser?](https://knowledge.oag.com/docs/what-is-the-source-of-data-in-connections-analyser) | 篩查 | 轉機網絡與行程組合分析。 |
| 224 | [What is the Job Bin?](https://knowledge.oag.com/docs/what-is-the-job-bin) | 篩查 | 轉機網絡與行程組合分析。 |
| 225 | [Are reports I have run in OAG Connections Analyser retained in the Job Bin when I log out?](https://knowledge.oag.com/docs/are-reports-i-have-run-in-oag-connections-analyser-retained-in-the-job-bin-when-i-log-out) | 篩查 | 轉機網絡與行程組合分析。 |
| 226 | [Why is my report taking so long to process?](https://knowledge.oag.com/docs/why-is-my-report-taking-so-long-to-process) | 篩查 | 轉機網絡與行程組合分析。 |
| 227 | [When I run my query there appears to be no data. Why is this?](https://knowledge.oag.com/docs/when-i-run-my-query-there-appears-to-be-no-data-why-is-this) | 篩查 | 轉機網絡與行程組合分析。 |
| 228 | [What is Circuity?](https://knowledge.oag.com/docs/what-is-circuity) | 篩查 | 轉機網絡與行程組合分析。 |
| 229 | [What is the default Minimum Connect Time (MCT)?](https://knowledge.oag.com/docs/what-is-the-default-minimum-connect-time-mct) | 篩查 | 轉機網絡與行程組合分析。 |
| 230 | [What is QSI?](https://knowledge.oag.com/docs/what-is-qsi) | 篩查 | 轉機網絡與行程組合分析。 |
| 231 | [What is a Phantom Flight?](https://knowledge.oag.com/docs/what-is-a-phantom-flight) | 篩查 | 轉機網絡與行程組合分析。 |
| 232 | [Can I use Connections Analyser to test the impact of changing the time of a flight?](https://knowledge.oag.com/docs/can-i-use-connections-analyser-to-test-the-impact-of-changing-the-time-of-a-flight) | 篩查 | 轉機網絡與行程組合分析。 |
| 233 | [When I log out of Connections Analyser, am I also logged out of OAG Analyser?](https://knowledge.oag.com/docs/when-i-log-out-of-connections-analyser-am-i-also-logged-out-of-oag-analyser) | 篩查 | 轉機網絡與行程組合分析。 |
| 234 | [Mapper](https://knowledge.oag.com/docs/mapper-1) | 篩查 | 航線地圖及展示操作。 |
| 235 | [1. Introduction](https://knowledge.oag.com/docs/1-introduction-5) | 篩查 | 航線地圖及展示操作。 |
| 236 | [About Mapper](https://knowledge.oag.com/docs/mapper-11-about-the-tool) | 篩查 | 航線地圖及展示操作。 |
| 237 | [Key Features](https://knowledge.oag.com/docs/mapper-12-key-features) | 篩查 | 航線地圖及展示操作。 |
| 238 | [2. Getting Started with Mapper](https://knowledge.oag.com/docs/mapper-2-getting-started) | 篩查 | 航線地圖及展示操作。 |
| 239 | [3. Mapper Report](https://knowledge.oag.com/docs/3-report) | 篩查 | 航線地圖及展示操作。 |
| 240 | [4. Running A Report in Mapper](https://knowledge.oag.com/docs/4-running-a-report) | 篩查 | 航線地圖及展示操作。 |
| 241 | [5. Customising a Map](https://knowledge.oag.com/docs/5-customising-a-map) | 篩查 | 航線地圖及展示操作。 |
| 242 | [6. Customising Using Google Map Styles](https://knowledge.oag.com/docs/6-customising-using-google-map-styles) | 篩查 | 航線地圖及展示操作。 |
| 243 | [7. Using the Unserved Destinations Function](https://knowledge.oag.com/docs/7-using-the-unserved-destinations-function) | 篩查 | 航線地圖及展示操作。 |
| 244 | [DOT](https://knowledge.oag.com/docs/dot) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 245 | [1. Introduction](https://knowledge.oag.com/docs/1-introduction-6) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 246 | [About DOT Analyser](https://knowledge.oag.com/docs/11-about-the-tool-3) | 深入 | US DOT 市場報表，非 UO 每日訂位軌跡。 |
| 247 | [Key Features](https://knowledge.oag.com/docs/12-key-features-3) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 248 | [The Reports](https://knowledge.oag.com/docs/13-the-reports) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 249 | [Traffic Reports (T100)](https://knowledge.oag.com/docs/131-traffic-reports-t100) | 深入 | T100 flown passengers，非前28天訂位快照。 |
| 250 | [Origin & Destination Reports (DB1B)](https://knowledge.oag.com/docs/132-origin-destination-reports-db1b) | 深入 | DB1B 市場票據樣本，非逐班價格／庫存曲線。 |
| 251 | [Financial Reports (Form 41)](https://knowledge.oag.com/docs/133-financial-reports-form-41) | 深入 | US Form41 財務報表，非 UO 每旅客增量成本。 |
| 252 | [2. Getting Started](https://knowledge.oag.com/docs/2-getting-started-2) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 253 | [3. T100 Segment Traffic Reports](https://knowledge.oag.com/docs/3-t100-segment-traffic-reports) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 254 | [Using the T100 Segment Traffic Powertable](https://knowledge.oag.com/docs/31-using-the-t100-segment-traffic-powertable) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 255 | [T100 Segment Traffic Home Screen](https://knowledge.oag.com/docs/311-t100-segment-traffic-home-screen) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 256 | [Domestic vs International Data](https://knowledge.oag.com/docs/312-domestic-vs-internationaldata) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 257 | [Dimensions & Metrics](https://knowledge.oag.com/docs/313-dimensions-metrics) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 258 | [Choosing the Period](https://knowledge.oag.com/docs/314-choosing-the-period) | 深入 | DOT 時間選擇為月／季／年，非逐日訂位。 |
| 259 | [Types of Flights](https://knowledge.oag.com/docs/315-types-of-flights) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 260 | [Carrier Selection](https://knowledge.oag.com/docs/316-carrier-selection) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 261 | [Origin & Destination](https://knowledge.oag.com/docs/317-origin-destination) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 262 | [Passengers and Freight](https://knowledge.oag.com/docs/318-passengers-and-freight) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 263 | [Equipment](https://knowledge.oag.com/docs/319-equipment) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 264 | [Running a Report](https://knowledge.oag.com/docs/3110-running-a-report) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 265 | [T100 Segment Traffic Report - Worked Example](https://knowledge.oag.com/docs/32-t100-segment-traffic-report-worked-example) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 266 | [4. T100 Market Traffic Reports](https://knowledge.oag.com/docs/4-t100-market-traffic-reports) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 267 | [Using the T100 Market Traffic Powertable](https://knowledge.oag.com/docs/41-using-the-t100-market-traffic-powertable) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 268 | [T100 Market Traffic Report - Worked Example](https://knowledge.oag.com/docs/42-t100-market-traffic-report-worked-example) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 269 | [5. O&D Traffic Reports](https://knowledge.oag.com/docs/5-od-traffic-reports) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 270 | [Using the O&D Traffic Reports (Detailed) Powertable](https://knowledge.oag.com/docs/51-using-the-od-traffic-reports-detailed-powertable) | 深入 | DB1B 10% 旅程樣本與報表。 |
| 271 | [O&D Traffic Report (Detailed) - Worked Example](https://knowledge.oag.com/docs/52-od-traffic-report-detailed-worked-example) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 272 | [Using the O&D Traffic Reports (Summary) Powertable](https://knowledge.oag.com/docs/53-using-the-od-traffic-reports-summary-powertable) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 273 | [6. Financial Reports (Form 41)](https://knowledge.oag.com/docs/6-financial-reports-form-41) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 274 | [O&D Traffic Report (Summary) - Worked Example](https://knowledge.oag.com/docs/62-od-traffic-report-summary-worked-example) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 275 | [Using the Financial Reports Powertable](https://knowledge.oag.com/docs/61-using-the-financial-reports-powertable) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 276 | [7. Traffic Summary Reports (Form 41)](https://knowledge.oag.com/docs/7-traffic-summary-reports-form-41) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 277 | [Using the Traffic Summary Reports Powertable](https://knowledge.oag.com/docs/71-using-the-traffic-summary-reports-powertable) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 278 | [T1 Airline Traffic Report](https://knowledge.oag.com/docs/72-t1-airline-traffic-report) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 279 | [T1 Airline Traffic - Worked Example](https://knowledge.oag.com/docs/73-t1-airline-traffic-worked-example) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 280 | [T2 Aircraft Traffic Report – Worked Example](https://knowledge.oag.com/docs/74-t2-aircraft-traffic-report-worked-example) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 281 | [T3 Airport Traffic Report – Worked Example](https://knowledge.oag.com/docs/75-t3-airport-traffic-report-worked-example) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 282 | [8. Appendix - Dimensions, Metrics & Categories](https://knowledge.oag.com/docs/8-appendix-dimensions-metrics-categories) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 283 | [T100 Segment Traffic Reports – Dimensions and Metrics](https://knowledge.oag.com/docs/81-t100-segment-traffic-reports-dimensions-and-metrics) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 284 | [T100 Market Traffic Reports – Dimensions and Metrics](https://knowledge.oag.com/docs/82-t100-market-traffic-reports-dimensions-and-metrics) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 285 | [O&D Traffic Reports (Detailed) – Dimensions and Metrics](https://knowledge.oag.com/docs/83-od-traffic-reports-detailed-dimensions-and-metrics) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 286 | [O&D Traffic Reports (Summary) – Dimensions and Metrics](https://knowledge.oag.com/docs/84-od-traffic-reports-summary-dimensions-and-metrics) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 287 | [Finance Reports (Form 41) - Dimensions, Metrics & Categories](https://knowledge.oag.com/docs/85-finance-reports-form-41-dimensions-metrics-categories) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 288 | [Traffic Summary Reports (Form 41) – Dimensions and Metrics](https://knowledge.oag.com/docs/86-traffic-summary-reports-form-41-dimensions-and-metrics) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 289 | [9. DOT Glossary](https://knowledge.oag.com/docs/dot-glossary-1) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 290 | [1 O&D Traffic Reports - Definitions & Terms Used](https://knowledge.oag.com/docs/1-od-traffic-reports-definitions-terms-used) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 291 | [O&D Detailed & Summary](https://knowledge.oag.com/docs/11-od-detailed-summary) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 292 | [T100 Traffic Reports - Definitions & Terms Used](https://knowledge.oag.com/docs/2-t100-traffic-reports-definitions-terms-used) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 293 | [Segment Traffic Reports](https://knowledge.oag.com/docs/21-segment-traffic-reports) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 294 | [Market Traffic Reports](https://knowledge.oag.com/docs/22-market-traffic-reports) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 295 | [Financial Reports – Definitions & Terms Used](https://knowledge.oag.com/docs/3-financial-reports-definitions-terms-used) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 296 | [B1 Balance Sheet – Large 20m Airlines](https://knowledge.oag.com/docs/31-b1-balance-sheet-large-20m-airlines) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 297 | [P1.2 Profit & Loss – Large 20m Airlines](https://knowledge.oag.com/docs/32-p12-profit-loss-large-20m-airlines) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 298 | [P5.1 Aircraft Operating Expenses – Large 20m Airlines](https://knowledge.oag.com/docs/33-p51-aircraft-operating-expenses-large-20m-airlines) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 299 | [P5.2 Aircraft Operating Expenses – Large 20m Airlines](https://knowledge.oag.com/docs/34-p52-aircraft-operating-expenses-large-20m-airlines) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 300 | [P6 Operating Expenses - Large 20m Airlines](https://knowledge.oag.com/docs/35-p6-operating-expenses-large-20m-airlines) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 301 | [P7 Operating Expenses - Large 20m Airlines](https://knowledge.oag.com/docs/36-p7-operating-expenses-large-20m-airlines) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 302 | [P10 Detailed Monthly Employee Statistics - Large 20m Airlines](https://knowledge.oag.com/docs/37-p10-detailed-monthly-employee-statistics-large-20m-airlines) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 303 | [P1(a) Annual Employee Totals - Large 20m Airlines](https://knowledge.oag.com/docs/38-p1a-annual-employee-totals-large-20m-airlines) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 304 | [P12(a) Fuel Consumption - Large 20m Airlines](https://knowledge.oag.com/docs/39-p12a-fuel-consumption-large-20m-airlines) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 305 | [B1.1 Balance Sheet – Small/Medium 20m Airlines](https://knowledge.oag.com/docs/310-b11-balance-sheet-smallmedium-20m-airlines) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 306 | [P1.1 Profit & Loss – Small/Medium 20m Airlines](https://knowledge.oag.com/docs/311-p11-profit-loss-smallmedium-20m-airlines) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 307 | [P5.1 Aircraft Operating Expense – Small/Medium 20m Airlines](https://knowledge.oag.com/docs/312-p51-aircraft-operating-expense-smallmedium-20m-airlines) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 308 | [P1(a) Annual Employee Totals – Small/Medium 20m Airlines](https://knowledge.oag.com/docs/313-p1a-annual-employee-totals-smallmedium-20m-airlines) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 309 | [T1 Airline Traffic](https://knowledge.oag.com/docs/314-t1-airline-traffic) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 310 | [T2 Aircraft Traffic](https://knowledge.oag.com/docs/315-t2-aircraft-traffic) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 311 | [T3 Airport Traffic](https://knowledge.oag.com/docs/316-t3-airport-traffic) | 篩查 | US DOT 流量／財務報表、欄位及示例；不補 UO 每日訂位。 |
| 312 | [Analyser+](https://knowledge.oag.com/docs/analyser-plus) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 313 | [Getting Started](https://knowledge.oag.com/docs/getting-started-1) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 314 | [New Capacity Report](https://knowledge.oag.com/docs/new-capacity-report) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 315 | [Schedules](https://knowledge.oag.com/docs/schedules-1) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 316 | [Widgets](https://knowledge.oag.com/docs/widgets) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 317 | [Charts](https://knowledge.oag.com/docs/charts) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 318 | [Insights](https://knowledge.oag.com/docs/insights) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 319 | [Maps](https://knowledge.oag.com/docs/maps) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 320 | [Reports](https://knowledge.oag.com/docs/reportd) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 321 | [Parameters](https://knowledge.oag.com/docs/parameters) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 322 | [Dimensions](https://knowledge.oag.com/docs/dimensions-metrics) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 323 | [Metrics](https://knowledge.oag.com/docs/metrics) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 324 | [Booking](https://knowledge.oag.com/docs/booking) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 325 | [Getting started with Bookings in Analyser+](https://knowledge.oag.com/docs/getting-started-with-bookings-in-analyser) | 深入 | Bookings 需要獨立訂閱；需求／容量報表。 |
| 326 | [Bookings parameters in Analyser+](https://knowledge.oag.com/docs/bookings-parameters-in-analyser) | 深入 | Adjusted／Unadjusted 與 route／segment 分析。 |
| 327 | [Bookings Templates in Analyser+ explained](https://knowledge.oag.com/docs/bookings-templates-in-analyser-explained) | 深入 | 需求／容量報表模板不是原始售票事件。 |
| 328 | [Status](https://knowledge.oag.com/docs/status) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 329 | [Getting started with Status Analyser+](https://knowledge.oag.com/docs/user-guide-analyser-flight-status-performance-features) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 330 | [Status Parameters and Definitions](https://knowledge.oag.com/docs/status-parameters-and-definitions) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 331 | [Feature Releases](https://knowledge.oag.com/docs/feature-releases) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 332 | [Snapshot Comparison](https://knowledge.oag.com/docs/snapshot-comparison) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 333 | [Getting Started with Snapshot Comparison in Analyser+](https://knowledge.oag.com/docs/getting-started-with-snapshot-comparison-in-analyser) | 深入 | Snapshot Comparison 只支援 Schedules metrics。 |
| 334 | [Snapshot Comparison Explained 📊](https://knowledge.oag.com/docs/snapshot-comparison-in-analyser) | 深入 | Bookings／Status 不能用此 snapshot comparison。 |
| 335 | [Release Notes](https://knowledge.oag.com/docs/release-notes-4) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 336 | [Q2 2026 Release Notes - Analyser+](https://knowledge.oag.com/docs/q2-2026-release-notes-analyser) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 337 | [Q1 2026 Release Notes - Analyser+](https://knowledge.oag.com/docs/q1-2026-release-notes-new-analyser) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 338 | [Analyser Functionality](https://knowledge.oag.com/docs/analyser-functionality) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 339 | [Saving Reports & Scheduling](https://knowledge.oag.com/docs/313-saving-reports-scheduling) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 340 | [Exporting](https://knowledge.oag.com/docs/314-exporting) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 341 | [My OAG](https://knowledge.oag.com/docs/traffic-4-my-oag) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 342 | [Saving Reports](https://knowledge.oag.com/docs/41-saving-scheduling-reports) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 343 | [Scheduling Reports](https://knowledge.oag.com/docs/traffic-42-scheduling-reports) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 344 | [Customising Data](https://knowledge.oag.com/docs/traffic-43-customising-data) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 345 | [User Preferences](https://knowledge.oag.com/docs/traffic-44-user-preferences) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 346 | [Reference Module](https://knowledge.oag.com/docs/analyser-reference-module) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 347 | [Airport Codes](https://knowledge.oag.com/docs/51-airport-codes) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 348 | [Airline Codes](https://knowledge.oag.com/docs/52-airline-codes-1) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 349 | [Aircraft Codes](https://knowledge.oag.com/docs/53-aircraft-codes) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 350 | [Alliance Codes](https://knowledge.oag.com/docs/54-alliance-codes-1) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 351 | [Seasons](https://knowledge.oag.com/docs/55-seasons-1) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 352 | [Country/Region Codes](https://knowledge.oag.com/docs/56-countryregion-codes-1) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |
| 353 | [Distance Calculator](https://knowledge.oag.com/docs/58-distance-calculator-1) | 篩查 | Analyser+ 或共用報表／參照操作；資料權限依產品。 |

## Pricing Products

77 個索引項目；全部正文取得成功。

| 編號 | 官方頁面 | 檢查層級 | 與本案的判讀 |
| ---: | --- | --- | --- |
| 354 | [Pricing Products](https://knowledge.oag.com/docs/pricing-products) | 篩查 | Pricing 資料字典、來源或 Snowflake 交付。 |
| 355 | [Pricing Data Sets](https://knowledge.oag.com/docs/pricing-data) | 篩查 | Pricing 資料字典、來源或 Snowflake 交付。 |
| 356 | [Airfares](https://knowledge.oag.com/docs/airfares) | 篩查 | Pricing 資料字典、來源或 Snowflake 交付。 |
| 357 | [About Airfares](https://knowledge.oag.com/docs/about-airfares) | 深入 | Airfares 交付與用途。 |
| 358 | [Airfares Data Dictionary](https://knowledge.oag.com/docs/airfares-data-dictionary) | 深入 | Standard／Premium 原始觀測欄位；YQ/YR 依來源；9+ seats 截斷。 |
| 359 | [Market Trend Data](https://knowledge.oag.com/docs/market-trend-data) | 篩查 | Pricing 資料字典、來源或 Snowflake 交付。 |
| 360 | [Data Sources](https://knowledge.oag.com/docs/data-sources) | 深入 | 網站報價、參照容量、典型訂位曲線與 Google Trends。 |
| 361 | [Market Indicators](https://knowledge.oag.com/docs/market-indicators) | 深入 | Passengers／Revenues 等指標為模型估算，非航司實測。 |
| 362 | [Market Trends Data Dictionary](https://knowledge.oag.com/docs/market-trends-data-dictionary) | 深入 | 週聚合市場票價。 |
| 363 | [Airfares in Snowflake](https://knowledge.oag.com/docs/altus-data) | 篩查 | Pricing 資料字典、來源或 Snowflake 交付。 |
| 364 | [Introduction](https://knowledge.oag.com/docs/introduction-1) | 篩查 | Pricing 資料字典、來源或 Snowflake 交付。 |
| 365 | [Signing in](https://knowledge.oag.com/docs/signing-in) | 篩查 | Pricing 資料字典、來源或 Snowflake 交付。 |
| 366 | [Connecting to Snowflake Using Third-Party Tools](https://knowledge.oag.com/docs/connecting-to-snowflake-using-third-party-tools) | 篩查 | Pricing 資料字典、來源或 Snowflake 交付。 |
| 367 | [Sample Queries](https://knowledge.oag.com/docs/sample-queries) | 篩查 | Pricing 資料字典、來源或 Snowflake 交付。 |
| 368 | [Credit Quota and Monitoring](https://knowledge.oag.com/docs/credit-quota-and-monitoring) | 篩查 | Pricing 資料字典、來源或 Snowflake 交付。 |
| 369 | [Altus Data Dictionary](https://knowledge.oag.com/docs/altus-data-dictionary) | 深入 | 逐航班按提前週數彙總，非每次原始報價。 |
| 370 | [GLAD Data Dictionary](https://knowledge.oag.com/docs/glad-data-dictionary) | 深入 | GLAD 歷史報價檔，時間採 Central European；需確認時區轉換。 |
| 371 | [Pricing Product Analytics](https://knowledge.oag.com/docs/pricing-product-analytics) | 篩查 | Airline PPS 價格比較／展示。 |
| 372 | [Airline PPS](https://knowledge.oag.com/docs/airline-pps-1) | 篩查 | Airline PPS 價格比較／展示。 |
| 373 | [About Airline PPS](https://knowledge.oag.com/docs/about-airline-pps) | 篩查 | Airline PPS 價格比較／展示。 |
| 374 | [Network Position](https://knowledge.oag.com/docs/network-position) | 深入 | RPI 是收益潛力估算，非真實未售票數。 |
| 375 | [Market Position](https://knowledge.oag.com/docs/market-position) | 篩查 | Airline PPS 價格比較／展示。 |
| 376 | [RBD Tracker](https://knowledge.oag.com/docs/rbd-tracker) | 深入 | RBD availability 是觀測比例／價格。 |
| 377 | [Code Shares](https://knowledge.oag.com/docs/code-shares) | 篩查 | Airline PPS 價格比較／展示。 |
| 378 | [Pharos](https://knowledge.oag.com/docs/pharos) | 篩查 | Pharos 價格採集／視覺化／更新。 |
| 379 | [About Pharos](https://knowledge.oag.com/docs/about-pharos) | 篩查 | Pharos 價格採集／視覺化／更新。 |
| 380 | [Pharos Displays](https://knowledge.oag.com/docs/pharos-displays) | 深入 | 歷史票價視圖；不要推論能重建未採集資料。 |
| 381 | [Using Pharos](https://knowledge.oag.com/docs/using-pharos) | 篩查 | Pharos 價格採集／視覺化／更新。 |
| 382 | [Data Series and Timeline](https://knowledge.oag.com/docs/data-series-timeline) | 篩查 | Pharos 價格採集／視覺化／更新。 |
| 383 | [Filter Settings](https://knowledge.oag.com/docs/filter-settings) | 篩查 | Pharos 價格採集／視覺化／更新。 |
| 384 | [Display Mode](https://knowledge.oag.com/docs/display-mode) | 篩查 | Pharos 價格採集／視覺化／更新。 |
| 385 | [Features](https://knowledge.oag.com/docs/features) | 深入 | Snapshot 是發起當下採價，非回溯任意日期。 |
| 386 | [User Defined Search (UDS)](https://knowledge.oag.com/docs/user-defined-search-uds) | 深入 | UDS 即時／預約採價，合約配額及90日訂單留存。 |
| 387 | [Pharos FAQs](https://knowledge.oag.com/docs/pharos-faqs) | 篩查 | Pharos 價格採集／視覺化／更新。 |
| 388 | [Release Notes](https://knowledge.oag.com/docs/release-notes-2) | 篩查 | Pharos 價格採集／視覺化／更新。 |
| 389 | [Q3 2026 Release Notes - Pharos](https://knowledge.oag.com/docs/q3-2026-release-notes-pharos) | 篩查 | Pharos 價格採集／視覺化／更新。 |
| 390 | [Q2 2026 Release Notes - Pharos](https://knowledge.oag.com/docs/q2-2026-release-notes-y-axis-zoom) | 篩查 | Pharos 價格採集／視覺化／更新。 |
| 391 | [Q1 2026 Release Notes - Historical Subscriptions Toggle](https://knowledge.oag.com/docs/q1-2026-release-notes-historical-subscriptions-toggle) | 深入 | 歷史訂閱90日 UI toggle，非全產品歷史限制。 |
| 392 | [Q3 2025 Release Notes - Pharos](https://knowledge.oag.com/docs/q3-2025-release-notes) | 深入 | 訂閱變更後保留90日 UI 資料。 |
| 393 | [Q2 2025 Release Notes - Pharos](https://knowledge.oag.com/docs/q2-2025-release-notes-pharos) | 深入 | 日內採價視覺化，視訂閱而定。 |
| 394 | [Channel Monitor](https://knowledge.oag.com/docs/channel-monitor) | 篩查 | Channel Monitor 渠道價格比較。 |
| 395 | [About Channel Monitor](https://knowledge.oag.com/docs/about-channel-monitor) | 篩查 | Channel Monitor 渠道價格比較。 |
| 396 | [Network](https://knowledge.oag.com/docs/network-1) | 深入 | 渠道價格比較與 RPI 估算。 |
| 397 | [Market](https://knowledge.oag.com/docs/market-1) | 篩查 | Channel Monitor 渠道價格比較。 |
| 398 | [RBD Tracker](https://knowledge.oag.com/docs/rbd-tracker-1) | 深入 | RBD 觀測可售性不是全機淨庫存。 |
| 399 | [Price Level Report](https://knowledge.oag.com/docs/price-level-report) | 篩查 | Channel Monitor 渠道價格比較。 |
| 400 | [Price Match Report](https://knowledge.oag.com/docs/price-match-report) | 篩查 | Channel Monitor 渠道價格比較。 |
| 401 | [Distribution Report](https://knowledge.oag.com/docs/distribution-report) | 篩查 | Channel Monitor 渠道價格比較。 |
| 402 | [Market Trends](https://knowledge.oag.com/docs/market-trends) | 篩查 | Market Trends 聚合指標與展示。 |
| 403 | [About Market Trends](https://knowledge.oag.com/docs/about-market-trends) | 篩查 | Market Trends 聚合指標與展示。 |
| 404 | [Heatmap](https://knowledge.oag.com/docs/heatmap) | 篩查 | Market Trends 聚合指標與展示。 |
| 405 | [Graphs](https://knowledge.oag.com/docs/graphs) | 篩查 | Market Trends 聚合指標與展示。 |
| 406 | [Vacation PPS](https://knowledge.oag.com/docs/vacation-pps) | 篩查 | Vacation PPS 套裝價格比較。 |
| 407 | [About Vacation PPS](https://knowledge.oag.com/docs/about-vacation-pps) | 篩查 | Vacation PPS 套裝價格比較。 |
| 408 | [Vacation Map View](https://knowledge.oag.com/docs/vacation-map-view) | 篩查 | Vacation PPS 套裝價格比較。 |
| 409 | [Property Table](https://knowledge.oag.com/docs/property-table) | 篩查 | Vacation PPS 套裝價格比較。 |
| 410 | [Property Graph](https://knowledge.oag.com/docs/property-graph) | 篩查 | Vacation PPS 套裝價格比較。 |
| 411 | [Customer Portal](https://knowledge.oag.com/docs/customer-portal) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 412 | [Online Order Module](https://knowledge.oag.com/docs/online-order-module) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 413 | [About Online Order Module](https://knowledge.oag.com/docs/about-online-order-module) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 414 | [Create an Order](https://knowledge.oag.com/docs/create-an-order) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 415 | [Add Markets](https://knowledge.oag.com/docs/add-markets) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 416 | [Upload Markets](https://knowledge.oag.com/docs/upload-markets) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 417 | [Applying and Uploading Conditions](https://knowledge.oag.com/docs/applying-uploading-conditions) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 418 | [Submit Order](https://knowledge.oag.com/docs/submit-order) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 419 | [Create Order Information Numbers](https://knowledge.oag.com/docs/create-order-information-numbers) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 420 | [Orders](https://knowledge.oag.com/docs/orders) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 421 | [Subscriptions](https://knowledge.oag.com/docs/subscriptions) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 422 | [Schedules](https://knowledge.oag.com/docs/schedules) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 423 | [Reports](https://knowledge.oag.com/docs/reports) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 424 | [Airfare Subscription Manager](https://knowledge.oag.com/docs/airfare-subscription-manager-1) | 深入 | transactions 為資料訂閱用量估算。 |
| 425 | [Recommendations Module](https://knowledge.oag.com/docs/recommendations-module) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 426 | [Introduction to the Recommendations Module](https://knowledge.oag.com/docs/introduction-to-the-recommendations-module) | 深入 | Recommendations 建議資料訂閱，不是會員售價。 |
| 427 | [How to use the Recommendations Module](https://knowledge.oag.com/docs/how-to-use-the-recommendations-module) | 深入 | 訂閱採集覆蓋／用量與推薦操作。 |
| 428 | [Release Notes](https://knowledge.oag.com/docs/release-notes-3) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 429 | [Q3 2026 - Airfare Subscription Manager](https://knowledge.oag.com/docs/q3-2026-airfare-subscription-manager) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |
| 430 | [Q4 2025 - Online Order Module](https://knowledge.oag.com/docs/q4-2025-online-order-module) | 篩查 | 資料訂閱／採集條件／用量管理或更新；非乘客購票交易。 |

## Industry Definitions

6 個索引項目；全部正文取得成功。

| 編號 | 官方頁面 | 檢查層級 | 與本案的判讀 |
| ---: | --- | --- | --- |
| 431 | [Industry Definitions](https://knowledge.oag.com/docs/industry-definitions) | 篩查 | IATA 欄位代碼參照。 |
| 432 | [IATA Operations Codes](https://knowledge.oag.com/docs/iata-operations-codes) | 篩查 | IATA 欄位代碼參照。 |
| 433 | [IATA In-flight Service Codes](https://knowledge.oag.com/docs/iata-in-flight-service-codes) | 篩查 | IATA 欄位代碼參照。 |
| 434 | [IATA Meal Codes](https://knowledge.oag.com/docs/iata-meal-codes) | 篩查 | IATA 欄位代碼參照。 |
| 435 | [IATA Service Type Codes](https://knowledge.oag.com/docs/iata-service-type-codes) | 篩查 | IATA 欄位代碼參照。 |
| 436 | [Restriction Codes](https://knowledge.oag.com/docs/restriction-codes) | 篩查 | IATA 欄位代碼參照。 |

## Flight Schedules Data

2 個索引項目；全部正文取得成功。

| 編號 | 官方頁面 | 檢查層級 | 與本案的判讀 |
| ---: | --- | --- | --- |
| 437 | [Flight Schedules Data](https://knowledge.oag.com/docs/flight-schedules-data) | 篩查 | 時刻／運行資料及歷史 flight-leg report。 |
| 438 | [WDF Record Layout](https://knowledge.oag.com/docs/wdf-record-layout) | 深入 | WDF 時刻格式、機型／容量欄位。 |

## Flight Status Data

9 個索引項目；全部正文取得成功。

| 編號 | 官方頁面 | 檢查層級 | 與本案的判讀 |
| ---: | --- | --- | --- |
| 439 | [Flight Status Data](https://knowledge.oag.com/docs/flight-status-data) | 篩查 | 時刻／運行資料及歷史 flight-leg report。 |
| 440 | [Understanding Flight Status States](https://knowledge.oag.com/docs/understanding-flight-status-states) | 篩查 | 時刻／運行資料及歷史 flight-leg report。 |
| 441 | [Daily Flight Leg Report](https://knowledge.oag.com/docs/daily-flight-leg-report) | 篩查 | 時刻／運行資料及歷史 flight-leg report。 |
| 442 | [Introduction](https://knowledge.oag.com/docs/introduction) | 深入 | 歷史 flight-leg report 為運行資料。 |
| 443 | [2. Report Configuration](https://knowledge.oag.com/docs/2-report-configuration) | 篩查 | 時刻／運行資料及歷史 flight-leg report。 |
| 444 | [3. Report Delivery](https://knowledge.oag.com/docs/3-report-delivery) | 篩查 | 時刻／運行資料及歷史 flight-leg report。 |
| 445 | [4. Time Period Covered](https://knowledge.oag.com/docs/4-time-period-covered) | 篩查 | 時刻／運行資料及歷史 flight-leg report。 |
| 446 | [5. Sample Report](https://knowledge.oag.com/docs/5-sample-report) | 篩查 | 時刻／運行資料及歷史 flight-leg report。 |
| 447 | [Glossary of Terms](https://knowledge.oag.com/docs/glossary-of-terms-1) | 深入 | Flight-leg report 標準欄位：時刻、運行及機型，不是銷售。 |

## Reference Data

3 個索引項目；全部正文取得成功。

| 編號 | 官方頁面 | 檢查層級 | 與本案的判讀 |
| ---: | --- | --- | --- |
| 448 | [Reference Data](https://knowledge.oag.com/docs/reference-data) | 篩查 | 航空公司參照資料格式。 |
| 449 | [Carrier File Record Layout](https://knowledge.oag.com/docs/carrier-file-record-layout) | 篩查 | 航空公司參照資料格式。 |
| 450 | [Carrier file with ICAO codes](https://knowledge.oag.com/docs/carrier-file-with-icao-codes) | 篩查 | 航空公司參照資料格式。 |

## Sample Data／Release Notes

15 個索引項目；全部正文取得成功。

| 編號 | 官方頁面 | 檢查層級 | 與本案的判讀 |
| ---: | --- | --- | --- |
| 451 | [Sample Data](https://knowledge.oag.com/docs/sample-data) | 篩查 | 樣本／時刻更新；未逐一展開外鏈壓縮檔。 |
| 452 | [WDF Sample Data](https://knowledge.oag.com/docs/wdf-sample-data) | 篩查 | 樣本／時刻更新；未逐一展開外鏈壓縮檔。 |
| 453 | [SSIM Sample Data](https://knowledge.oag.com/docs/ssim-sample-data) | 篩查 | 樣本／時刻更新；未逐一展開外鏈壓縮檔。 |
| 454 | [Seats 4-Cabin Sample Data](https://knowledge.oag.com/docs/seats-4-cabin-sample-data) | 篩查 | 樣本／時刻更新；未逐一展開外鏈壓縮檔。 |
| 455 | [Seats 3-Cabin Sample Data](https://knowledge.oag.com/docs/seats-3-cabin-sample-data) | 篩查 | 樣本／時刻更新；未逐一展開外鏈壓縮檔。 |
| 456 | [Flight Leg Report Sample Data](https://knowledge.oag.com/docs/flight-leg-report-sample-data) | 篩查 | 樣本／時刻更新；未逐一展開外鏈壓縮檔。 |
| 457 | [MCT Industry Mandate Without Defaults Sample Data](https://knowledge.oag.com/docs/mct-industry-mandate-without-defaults-sample-data) | 篩查 | 樣本／時刻更新；未逐一展開外鏈壓縮檔。 |
| 458 | [MCT Industry Mandate With Defaults Sample Data](https://knowledge.oag.com/docs/mct-industry-mandate-with-defaults-sample-data) | 篩查 | 樣本／時刻更新；未逐一展開外鏈壓縮檔。 |
| 459 | [Locations Sample Data](https://knowledge.oag.com/docs/locations-sample-data) | 篩查 | 樣本／時刻更新；未逐一展開外鏈壓縮檔。 |
| 460 | [Equipment Sample Data](https://knowledge.oag.com/docs/equipment-sample-data) | 篩查 | 樣本／時刻更新；未逐一展開外鏈壓縮檔。 |
| 461 | [DSTLOC (Combined  DST and Locations) Sample Data](https://knowledge.oag.com/docs/dstloc-combined-dst-and-locations-sample-data) | 篩查 | 樣本／時刻更新；未逐一展開外鏈壓縮檔。 |
| 462 | [DST File Sample Data](https://knowledge.oag.com/docs/dst-file-sample-data) | 篩查 | 樣本／時刻更新；未逐一展開外鏈壓縮檔。 |
| 463 | [Carrier File Sample Data](https://knowledge.oag.com/docs/carrier-file-sample-data) | 篩查 | 樣本／時刻更新；未逐一展開外鏈壓縮檔。 |
| 464 | [Release Notes](https://knowledge.oag.com/docs/release-notes-5) | 篩查 | 樣本／時刻更新；未逐一展開外鏈壓縮檔。 |
| 465 | [Q3 2026 Release Notes - WDF+](https://knowledge.oag.com/docs/q3-2026-release-notes-wdf) | 篩查 | 樣本／時刻更新；未逐一展開外鏈壓縮檔。 |

## Weather Conditions Data API

8 個索引項目；全部正文取得成功。

| 編號 | 官方頁面 | 檢查層級 | 與本案的判讀 |
| ---: | --- | --- | --- |
| 466 | [Weather Conditions Data API](https://knowledge.oag.com/docs/oag-flightview-weather-conditions-data-api) | 篩查 | 天氣及預報資料，無 booking／fare 核心標籤。 |
| 467 | [Overview](https://knowledge.oag.com/docs/overview) | 篩查 | 天氣及預報資料，無 booking／fare 核心標籤。 |
| 468 | [How to Access the Weather Conditions Web Service](https://knowledge.oag.com/docs/how-to-access-the-weather-conditions-web-service) | 篩查 | 天氣及預報資料，無 booking／fare 核心標籤。 |
| 469 | [Web Method Request Specification](https://knowledge.oag.com/docs/web-method-request-specification) | 篩查 | 天氣及預報資料，無 booking／fare 核心標籤。 |
| 470 | [Web Method Request for Demo](https://knowledge.oag.com/docs/web-method-request-for-demo) | 篩查 | 天氣及預報資料，無 booking／fare 核心標籤。 |
| 471 | [Current Conditions Data Elements](https://knowledge.oag.com/docs/current-conditions-data-elements) | 篩查 | 天氣及預報資料，無 booking／fare 核心標籤。 |
| 472 | [Forecast Conditions Data Elements](https://knowledge.oag.com/docs/forecast-conditions-data-elements) | 篩查 | 天氣及預報資料，無 booking／fare 核心標籤。 |
| 473 | [Icon Mapping](https://knowledge.oag.com/docs/icon-mapping) | 篩查 | 天氣及預報資料，無 booking／fare 核心標籤。 |

## Flight Status API for JSON/XML

14 個索引項目；全部正文取得成功。

| 編號 | 官方頁面 | 檢查層級 | 與本案的判讀 |
| ---: | --- | --- | --- |
| 474 | [Flight Status API for JSON and XML](https://knowledge.oag.com/docs/integration-guide-flight-status-api-for-json-and-xml) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 475 | [1. Introduction](https://knowledge.oag.com/docs/1-introduction) | 深入 | 舊 Flight Status API 用途／運行資料。 |
| 476 | [2. OAG Flight Status API Servers](https://knowledge.oag.com/docs/2-oag-flight-status-api-servers) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 477 | [3. Query Format](https://knowledge.oag.com/docs/4-query-format) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 478 | [3.1 Request Parameters](https://knowledge.oag.com/docs/41-request-parameters) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 479 | [3.1.1 Example Request Parameters](https://knowledge.oag.com/docs/411-request-parametersfor-standard-use-cases) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 480 | [4.2 Additional Customer Configurations](https://knowledge.oag.com/docs/42-additional-customer-configurations) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 481 | [5. Response Format](https://knowledge.oag.com/docs/response-format) | 深入 | 舊狀態 API response schema。 |
| 482 | [Appendix A: Valid Combinations of Request Parameters](https://knowledge.oag.com/docs/appendix-a-valid-combinations-of-request-parameters) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 483 | [Appendix B: Sample Query & Response in XML](https://knowledge.oag.com/docs/appendix-b-sample-query-response-in-xml) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 484 | [Appendix C: Sample Query & Response for Diversion in XML](https://knowledge.oag.com/docs/appendix-c-sample-query-response-for-diversion-in-xml) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 485 | [Appendix D: Sample Query and Response in JSON](https://knowledge.oag.com/docs/appendix-d-sample-query-and-response-in-json) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 486 | [Appendix F: IATA](https://knowledge.oag.com/docs/appendix-f-iata) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 487 | [Appendix E: Sample Query and Response for In-Air Flight in JSON](https://knowledge.oag.com/docs/appendix-e-sample-query-and-response-for-in-air-flight-in-json) | 篩查 | 舊運行狀態或資訊顯示介面。 |

## FVXML for FIDS

16 個索引項目；全部正文取得成功。

| 編號 | 官方頁面 | 檢查層級 | 與本案的判讀 |
| ---: | --- | --- | --- |
| 488 | [FVXML for FIDS](https://knowledge.oag.com/docs/fvxml-for-fids-1) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 489 | [1. Introduction](https://knowledge.oag.com/docs/1-introduction-4) | 深入 | 機場資訊顯示用 feed。 |
| 490 | [2. FlightView XML Servers](https://knowledge.oag.com/docs/2-flightview-xml-servers) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 491 | [3. Standard Use Cases](https://knowledge.oag.com/docs/3-standard-use-cases-1) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 492 | [4. Query Format](https://knowledge.oag.com/docs/4-query-format-1) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 493 | [4.1 Request Parameters](https://knowledge.oag.com/docs/41-request-parameters-1) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 494 | [4.1.1 Request Parameters for Standard Use Cases](https://knowledge.oag.com/docs/411-request-parameters-for-standard-use-cases) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 495 | [4.2 Response Parameters](https://knowledge.oag.com/docs/42-response-parameters) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 496 | [4.3 Additional Customer Configurations](https://knowledge.oag.com/docs/43-additional-customer-configurations) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 497 | [5. XML Response Format](https://knowledge.oag.com/docs/5-xml-response-format) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 498 | [5.1 Header](https://knowledge.oag.com/docs/51-header-1) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 499 | [5.2 Results Status](https://knowledge.oag.com/docs/52-results-status) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 500 | [5.3 Flight Elements](https://knowledge.oag.com/docs/53-flight-elements) | 深入 | FIDS 航班元素／狀態／時間欄位。 |
| 501 | [Appendix A: Sample Query & Response](https://knowledge.oag.com/docs/appendix-a-sample-query-response) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 502 | [Appendix B: Airport Codes](https://knowledge.oag.com/docs/appendix-b-airport-codes) | 篩查 | 舊運行狀態或資訊顯示介面。 |
| 503 | [Appendix C: Airline Codes](https://knowledge.oag.com/docs/appendix-c-airline-codes) | 篩查 | 舊運行狀態或資訊顯示介面。 |

## What's New?

28 個索引項目；全部正文取得成功。

| 編號 | 官方頁面 | 檢查層級 | 與本案的判讀 |
| ---: | --- | --- | --- |
| 504 | [What's New?](https://knowledge.oag.com/docs/whats-new) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 505 | [Q3 2026 - Airfare Subscription Manager](https://knowledge.oag.com/docs/q3-2026-airfare-subscription-manager-1) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 506 | [Q3 2026 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q3-2026-release-notes-flight-info-direct-1) | 深入 | 集中更新：容量模型及 preliminary/final adjusted。 |
| 507 | [Q3 2026 Release Notes - Pharos](https://knowledge.oag.com/docs/q3-2026-release-notes-pharos-1) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 508 | [Q2 2026 Release Notes - Analyser+](https://knowledge.oag.com/docs/q2-2026-release-notes-analyser-1) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 509 | [Q2 2026 Release Notes - Pharos](https://knowledge.oag.com/docs/q2-2026-release-notes-pharos) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 510 | [Q2 2026 Release Notes - Flight Info API](https://knowledge.oag.com/docs/q2-2026-release-notes-flight-info-api-1) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 511 | [Q1 2026 Release Notes - Analyser+](https://knowledge.oag.com/docs/q1-2026-release-notes-new-analyser-1) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 512 | [Q1 2026 Release Notes - Flight Info API](https://knowledge.oag.com/docs/q1-2026-release-notes-flight-info-api-1) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 513 | [Q1 2026 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q1-2026-release-notes-flight-info-alerts) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 514 | [Q1 2026 Release Notes - Passenger Booking Data](https://knowledge.oag.com/docs/q1-2026-release-notes-passenger-booking-data-1) | 深入 | 集中更新：Weekly booking 航班級與交付延遲。 |
| 515 | [Q1 2026 Release Notes - Historical Subscriptions Toggle](https://knowledge.oag.com/docs/q1-2026-release-notes-historical-subscriptions-toggle-1) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 516 | [Q1 2026 Release Notes - SSIM+](https://knowledge.oag.com/docs/q1-2026-release-notes-ssim) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 517 | [Q4 2025 - Online Order Module](https://knowledge.oag.com/docs/q4-2025-online-order-module-1) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 518 | [Q4 2025 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q4-2025-release-notes-flight-info-direct-1) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 519 | [Q4 2025 Release Notes - Flight Info API](https://knowledge.oag.com/docs/q4-2025-release-notes-flight-info-api-1) | 深入 | Carriers 主資料完整性改進。 |
| 520 | [Q3 and Q4 2025 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q3-and-q4-2025-release-notes-flight-info-alerts) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 521 | [Q3 2025 Release Notes - Circuity Limit Increased in Connections Data](https://knowledge.oag.com/docs/q3-2025-release-notes-circuity-limit-increased-in-connections-data) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 522 | [Q3 2025 Release Notes - Pharos](https://knowledge.oag.com/docs/q3-2025-release-notes-pharos) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 523 | [Q3 2025 Release Notes - Passenger Booking Data and Traffic Analyser](https://knowledge.oag.com/docs/q3-2025-release-notes-passenger-booking-data-and-traffic-analyser) | 深入 | Booking 艙等推算／回補邏輯改變，須留意版本。 |
| 524 | [Q2 2025 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q2-2025-release-notes-flight-info-direct-1) | 深入 | 集中更新：Market Trends 週聚合。 |
| 525 | [Q2 2025 Release Notes - Pharos](https://knowledge.oag.com/docs/q2-2025-release-notes-pharos-1) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 526 | [Q2 2025 Release Notes - Flight Info API](https://knowledge.oag.com/docs/q2-2025-release-notes-flight-info-api) | 深入 | API 運行篩選／設備類型及 v1 停用。 |
| 527 | [Q2 2025 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q2-2025-release-notes-flight-info-alerts-1) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 528 | [Q1 2025 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q1-2025-release-notes-flight-info-direct-1) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 529 | [Q1 2025 Release Notes - Flight Info Alerts](https://knowledge.oag.com/docs/q1-2025-release-notes-flight-info-alerts-1) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 530 | [Q4 2024 Release Notes - Flight Info Direct](https://knowledge.oag.com/docs/q4-2024-release-notes-flight-info-direct-1) | 篩查 | 集中版本更新；按所屬產品判讀。 |
| 531 | [Q4 2024 Traffic Analyser Online Fare Data](https://knowledge.oag.com/docs/q4-2024-traffic-analyser-online-fare-data) | 深入 | Online fares 來源改變，不能當逐張成交價。 |

## Customer FAQs

3 個索引項目；全部正文取得成功。

| 編號 | 官方頁面 | 檢查層級 | 與本案的判讀 |
| ---: | --- | --- | --- |
| 532 | [Customer FAQs](https://knowledge.oag.com/docs/customer-faqs) | 篩查 | 支援／維護流程。 |
| 533 | [Raising an Incident](https://knowledge.oag.com/docs/raising-an-incident) | 篩查 | 支援／維護流程。 |
| 534 | [Service Incidents and Maintenance Notifications](https://knowledge.oag.com/docs/service-incidents-and-maintenance-notifications) | 篩查 | 支援／維護流程。 |
