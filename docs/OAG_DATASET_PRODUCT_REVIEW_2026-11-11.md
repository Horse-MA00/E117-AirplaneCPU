# OAG Booking / Airfare 對 E117 UOption Fly Pass 的適用性

> 状态：记录（2026-11-11），内容不再修改


查核日期：2026-11-11。範圍：OAG 官方產品頁、Knowledge Hub 字典、更新記錄與交付說明。本文區分「文件已證實」「仍需供應商確認」及「本案建議」；未取得實際 UO 樣本或商業授權。

**結論：值得索取限定樣本，但尚不能承諾 OAG 單獨足以訓練 UO 的每日餘位決策。** 最新文件已證實有航班級 Weekly Unadjusted booking 歷史，也有帶觀測時間的原始 airfare；尚未證實 UO 直銷全量、D28 至起飛每日完整快照、取消／改票版本及最終實際登機人數。因此可優先測試「正常訂位增長與市場報價特徵」，真正的可放會員座位仍宜由航司庫存／營運結果校準。依據及限制如下。

## 已查官方頁面與個別發現

| 官方來源 | 已證實內容 | 本案的限制／待確認 |
|---|---|---|
| [Passenger Booking Data 產品頁](https://www.oag.com/passenger-booking-data) | 宣稱 830+ carriers、歷史自 2010、往前一年；Direct 每週、Analytics 每月；可按 carrier、flight、route、booking/travel date 配置。 | 產品總歷史不等於所有精細欄位都追溯至 2010；覆蓋家數不證明 UO 或其直銷全量。 |
| [Q1 2026 Passenger Booking release，2026-01-28](https://knowledge.oag.com/docs/q1-2026-release-notes-passenger-booking-data-1) | Weekly Unadjusted View：每月 7、14、21、月底四次，可能再延遲 1.5–2 天；從 2024-01 起；支援航班號、逐 leg 日期／時間及最多六航段。 | 這是可用的精細歷史，不是每日更新；文件未保證歷史每一版都保留當時可見值。 |
| [Passenger Bookings 字典，更新 2026-09-03](https://knowledge.oag.com/docs/passenger-bookings-data-fields-explained) | 分 Forward Looking MIDT、Backward Looking Full Market、Booking／Segment、Load Factor、Weekly Unadjusted。Weekly 的 `BOOKING_TRANSACTION_DATE` 是 PNR 原始預訂日；`FILE_DATE` 是資料載入日，另有處理年月／日。Load Factor 是月份 × 航線 × 航司。 | 交易日不能直接當 `available_at`；月度 load factor 不能作單班最終載客標籤。公開欄位未證實 gross bookings、cancellations、no-shows、boarded。 |
| [Passenger Bookings for Airlines 字典，2026-10-20](https://knowledge.oag.com/docs/passenger-bookings-for-airlines-data-fields-explained) | 另有 airline 版，列 Backward Full Market Booking／Segment 及 Load Factor。 | 需確認 hackathon／airline 授權可取得哪個 view，不能把一般字典的 Weekly MIDT 視作已獲授權。 |
| [Traffic Analyser Data Source，更新 2024-10-14](https://knowledge.oag.com/docs/13-source-of-data) | Unadjusted 為 GDS 資料；Adjusted 結合 GDS 與外部資料經演算法估算市場。Analytics 的 prelim／final 有月度延遲；Travelport average fare 與 online fare 是不同概念。 | Adjusted Final 的「final」指估算版本完成，並非逐班實際登機。此頁舊月度 cadence 不應覆蓋 2026 Weekly 新產品。 |
| [Flight Info Direct Useful Queries](https://knowledge.oag.com/docs/flight-info-direct-useful-queries) | Booking 範例按 `FILE_DATE` 查「每年一月看到的六月 bookings」。 | 證明產品有按載入版本查詢的用法；仍須確認 Weekly 歷史保留、回補、修訂及當時交付時間。 |
| [Airfare Data 產品頁](https://www.oag.com/airfare-data) | 10+ 年歷史、可觀測未來一年出發的報價；公開售票渠道觀測，帶時間；頻率依訂閱；可交付 Snowflake、feed、files、analytics。 | 是可購買報價觀測，不是已售票成交價；「未來一年」不是預測一年後價格。未證實 UO 指定站點、日期及 fare family 完整性。 |
| [Airfares Data Dictionary](https://knowledge.oag.com/docs/airfares-data-dictionary) | Standard 有觀測時間、航班、艙等、幣種、`price_inc`／`price_exc`／`tax`；`tax` 混合稅、附加費，拆不出時可能為空。Premium 有 UTC 觀測時間、`trip_fee_yq`／`trip_fee_yr`、fare family、included／excluded extras；部分欄位依來源可得性。Seat 值 9 表示至少 9。 | 需測 UO 的稅／燃油／行李缺值率及口徑；不能將售票網站的截斷可售數當全機剩餘座位。 |
| [About Airfares，更新 2026-05-20](https://knowledge.oag.com/docs/about-airfares) | Files 可經 SFTP 或 AWS／GCS／Azure 等雲端儲存交付；另有 Snowflake 與 Analytics。 | 索取 CSV／Parquet 限定樣本可減少接入成本；是否支援具體格式、費用與時限仍需確認。 |
| [Airfare Subscription Manager](https://knowledge.oag.com/docs/airfare-subscription-manager-1) | 可指定 site、carrier、route、POS、cabin、OW／RT、departure range、collection frequency／time window。 | 「平台每天採集數十億筆」不保證某一 UO 航班每日都有資料；請回覆實際 observation coverage。 |
| [Market Trends 字典](https://knowledge.oag.com/docs/market-trends-data-fields-explained) | 按 observation week、departure week、航線、航司、艙等聚合；最低／平均總價亦經聚合。 | 適合市場背景，不足以替代單班 D28→D0 原始 fare observations。 |
| [Seats Data](https://www.oag.com/flight-data-seats) | 提供預測及實際座位配置、艙等容量，使用 tail number 與模型，最多每日更新。 | 容量不等於當時可售庫存；仍須確認歷史 as-of capacity、換機、封鎖座位與最終有效容量。 |

版本判讀：舊 [更新頻率 FAQ（2025-04-29）](https://knowledge.oag.com/docs/how-often-are-the-data-sets-updated) 仍寫 Passenger Bookings monthly；本案採用較新、明確適用 Weekly Unadjusted 的 2026 release，而不把整個 booking 產品都說成每日或每週即時資料。

## 對 WHEN／HOW MANY／WHAT 的判斷

以下是本案建模推論，不是 OAG 的產品保證。

| 決策 | OAG 可提供的候選證據 | 缺口與使用界線 |
|---|---|---|
| WHEN：D28 至起飛何時開放 | Weekly booking 版本、預訂提前天數、原始 fare 觀測 | 每週資料可以支持較粗時間節點；逐日回測需當時可見的快照，或能按可用時間、取消／改票事件可靠重建的訂位狀態。不能用最終修訂資料回填假裝當時已知。 |
| HOW MANY：放多少會員座位 | 正常 booking pickup 特徵、市場需求、capacity | 需要同航班同時間的全渠道有效訂位與容量，及最終 booked／boarded 分開標籤。Adjusted 月度市場估值或網站「9+ seats」均不足以驗證安全放位。 |
| WHAT：零／低 base fare，加稅與燃油 | 可比艙等、品牌、渠道的歷史公開報價及部分費用拆分 | 報價沒有揭示在另一價格下會新增多少會員需求，也不能直接量化蠶食全價票。會員轉換、履約成本及正常票收入仍需航司資料或明示模擬假設。 |

建議嚴格分開兩個結果：`final_unsold = final_sellable_capacity - final_valid_bookings`；`empty_at_departure = final_operated_capacity - boarded_passengers`。兩者含義不同，後者包含 no-show 影響，不能用作前者的同義標籤。改機、超售、封鎖座位亦需明確處理。

## 建議限定樣本請求（尚未發送）

先要 coverage matrix 與小樣本，再擴資料量；以下是需求，並非宣稱 OAG 已提供。

1. **範圍**：UO／HK Express、HKG 出發的 2–3 條直飛航線，由供應商挑選確有資料的路線；選連續 8–12 週已完成航班，含淡旺日；Economy、單程、1 成人、香港 POS。先提供 10–20 航班驗證欄位，通過後才擴至 300–1,000 航班。若需衡量季節泛化，再申請 12 個月。
2. **Booking**：該批航班 D28 至 D0 所有實際保留版本，優先每日；若只有每月四批，保留原始批次，不插值冒充日快照。要 operating carrier、flight number、departure date/time/timezone、route、cabin、有效在冊訂位、增訂／取消／改票語義、資料渠道、observed／estimated 標記、snapshot time、首次可用時間、修訂時間／版本、最終有效訂位。請明答 UO 官網／app／其他直銷是否包含及覆蓋率；若沒有便列明。
3. **最終結果／容量**：同批航班的當時容量、最終有效容量、實際登機人數、no-shows、取消及換機。若 OAG 無此資料，請直答 unavailable，另向航司取樣，勿以估計 load factor 補成真實標籤。
4. **Airfare**：同班 D28→D0 全部保留觀測，至少每天一次的既有觀測；UO 直接渠道優先，附來源及缺口表；要 observation UTC、delivery time、原幣與 ISO currency、base／含稅總額／稅費／YQ／YR、cabin／fare family、行李與其他必需費用、OW／RT、旅客數與 POS。不可拆分時保留 null 與原因，不將燃油預設為零。請給一筆可重算總額的費用例子。
5. **交付與權限**：請確認可用 view／feed、欄位字典版本、CSV／Parquet 或 Snowflake、可交付日、費用；是否允許 hackathon 訓練、隊內共享、向評審展示衍生指標、保留模型及後續原型，以及原始資料的保留／刪除期限。公開產品頁未提供足以承諾這些權利的條款。

驗收先問四件事：同一航班能否跨版本穩定連結；UO 直銷是否真實觀測且覆蓋充分；回測每列是否確實在決策時間前可得；booking、capacity、fares、final outcomes 是否能在一致粒度對齊。前兩者失敗，應將 OAG 定位為市場輔助資料，不能包裝成 UO 真實庫存訓練集。

## Pricing 全子分類篩查補充

以官方 [Knowledge Hub 索引](https://knowledge.oag.com/llms.txt) 的 Pricing Products 分支為範圍：77 個目錄／文章條目（研究清單序號 354–430）已全部取得有效 Markdown 正文，完成用途、章節及相關欄位篩查；原始 Airfares、Altus、GLAD、Market Trends 字典與資料來源／估算方法另作深入核對。最初受轉址及請求頻率限制的頁面，降低請求頻率後已取得並補查。這是針對資料適用性的全分區篩查，不是對每個介面操作步驟、插圖或影片逐字審核。API、Direct、Alerts、Analyser 等分支與逐頁清單見 [主報告](OAG_API_DATA_AUDIT_2026-11-11.md)。

| 子分類（含目錄頁） | 本輪本地可讀／條目數 | 補充結果 |
|---|---:|---|
| Pricing／Airfares | 5/5 | 已覆蓋原始 Standard／Premium 字典與交付。 |
| Market Trend Data | 4/4 | [Data Sources](https://knowledge.oag.com/docs/data-sources) 的 capacity 為參考代理值，booking curves 為典型曲線；[Market Indicators](https://knowledge.oag.com/docs/market-indicators) 雖有 Passenger Flown、PAX Forecasted、Revenues Booked 等名稱，其方法明列價格波動、搜尋趨勢與演算法。不能把這些指標當航司實測標籤。 |
| Airfares in Snowflake／Altus／GLAD | 8/8 | [Altus 字典](https://knowledge.oag.com/docs/altus-data-dictionary) 是逐航班按出發前週數彙整 min／max／avg 與觀測數，非原始逐筆快照。[GLAD](https://knowledge.oag.com/docs/glad-data-dictionary) 是歷史檔案觀測資料，時間欄位採 Central European 時區。登入、第三方連接及 credits 頁是交付／用量說明。 |
| Analytics／Airline PPS | 7/7 | [RBD Tracker](https://knowledge.oag.com/docs/rbd-tracker) 的 availability 是 RBD 被觀測比例或價格；[Network Position](https://knowledge.oag.com/docs/network-position) 的 RPI 為收益潛力估算，不是真實未售票數；Market／Codeshare 是價格比較。 |
| Pharos（含更新記錄） | 16/16 | [Price Evolution](https://knowledge.oag.com/docs/pharos-displays) 能看歷史價格變化，[intraday 更新](https://knowledge.oag.com/docs/q2-2025-release-notes-pharos) 支援日內多次觀測。[UDS](https://knowledge.oag.com/docs/user-defined-search-uds) 是即時／預約採價，可匯出 CSV／XLSX、訂單留存 90 日且受合約配額限制；不能據此假設可重建未採集的過去。其餘頁為價格圖表、篩選及比較設定。 |
| Channel Monitor | 8/8 | Market、RBD、Price Level／Match、Distribution 都是渠道報價比較；[RBD Tracker](https://knowledge.oag.com/docs/rbd-tracker-1) 並未定義完整座位餘量；Network 的 RPI 同樣是潛力估算。 |
| Market Trends UI | 4/4 | Heatmap／Graphs 呈現聚合指標；[Graphs](https://knowledge.oag.com/docs/graphs) 指 UI 歷史自 2021 年中，與產品資料歷史不能混用。 |
| Vacation PPS | 5/5 | [About](https://knowledge.oag.com/docs/about-vacation-pps)、Map、Property Table／Graph 是機票／酒店／租車套裝價格比較，沒有本案的訂位標籤。 |
| Customer Portal／Order／ASM | 14/14 | 建立／上傳 market、設定採集條件、提交及管理資料訂閱；[ASM](https://knowledge.oag.com/docs/airfare-subscription-manager-1) 的 transactions 是資料訂閱用量估計，不能視作乘客購票交易。 |
| Recommendations Module | 3/3 | [Introduction](https://knowledge.oag.com/docs/introduction-to-the-recommendations-module) 及操作指南是推薦增修資料訂閱／採集覆蓋，不是會員售價或放位推薦。 |
| Portal release notes | 3/3 | [Q3 2026 ASM 更新](https://knowledge.oag.com/docs/q3-2026-airfare-subscription-manager) 是訂閱管理、用量估算、匯出；Q4 2025 更新是採集 POS 設定。 |

Pharos 的 [Q3 2025 歷史保留更新](https://knowledge.oag.com/docs/q3-2025-release-notes-pharos) 與 [Q1 2026 historical toggle](https://knowledge.oag.com/docs/q1-2026-release-notes-historical-subscriptions-toggle) 說明最近 90 日歷史訂閱的 UI 存取；不能推論所有 Airfare 原始歷史只有 90 日，亦不能反過來假設 Pharos 可直接匯出產品所稱全部 10+ 年。

查核方法補充：Knowledge Hub 初始直開遭 redirect loop；透過官方 Markdown 端點、站點版本 cookie 與降低請求頻率，最終已取得全部 534 個索引項目正文，無遺留受阻項目。本文結合正文與網頁工具讀到的官方產品頁核實。僅使用 OAG 第一方來源，未將原始文件全文複製進 repo。未公開說明的欄位／coverage／權限一律保留為待確認，不以「未搜到」斷言供應商不存在該能力。
