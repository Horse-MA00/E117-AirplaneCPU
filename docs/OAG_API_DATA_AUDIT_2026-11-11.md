# E117 — OAG 文件核查、數據需求與 Cathay 郵件草稿

> 状态：记录（2026-11-11），内容不再修改


查核日期：2026-11-11（香港時間）。用途：確認 UOption Fly Pass 的資料缺口，向主辦方申請 OAG Passenger Booking Data 與 OAG/Infare Airfare Data。這是公開文件研究，沒有登入產品、測試付費 API、取得數據或寄出郵件。

## 1. 結論

**Flight Info API 可提供航班、時刻、運行狀態及按權限提供座位容量；公開文件未列出我們需要的歷史訂位曲線及機票報價時間序列。單靠此 API 不足以訓練並驗證「28 天內何時開放、釋出多少位、收多少基本票價」。**

**OAG 的其他產品確實有相關資料。** Passenger Booking Data 的 Weekly Unadjusted View 有訂位日期、航班號及航段出發日期等欄位；Airfares 有觀測日期、航班、價格及部分費用拆分。正確的申請是取得這兩種產品的適用資料／小樣本，而不是單純提高 Flight Info API 額度。是否有 HK Express 的充分覆蓋、可用歷史版本、取消處理及研究使用權，仍須由 OAG 確認。

來源：[Flight Info API 欄位](https://knowledge.oag.com/docs/flight-info-api-response-layout-descriptions)、[Content Parameters](https://knowledge.oag.com/docs/flight-info-api-content-parameters)、[Passenger Bookings 字典](https://knowledge.oag.com/docs/passenger-bookings-data-fields-explained)、[Airfares 字典](https://knowledge.oag.com/docs/airfares-data-dictionary)。

## 2. 查閱範圍與方法

以 [OAG 官方完整索引](https://knowledge.oag.com/llms.txt) 的 **534 個公開頁面／目錄項目**為邊界，不只查搜尋結果或單一 response PDF。逐項取得公開 Markdown 正文，進行章節與全文相關欄位檢索；對 API 定義、產品資料字典、訂位／票價來源、時間粒度及相關 release notes 作深入核對。逐頁取得情況與檢查層級見 [檢查清單](OAG_DOCS_REVIEW_CHECKLIST_2026-11-11.md)。

範圍包含下列全部產品分區；不把同一 Knowledge Hub 中其他產品的功能視作 Flight Info API 已包含的功能。頁面連結到的每段影片、圖片、下載樣本或外部網站，沒有一律當作另一個需要逐字審核的文件；亦沒有驗證合約／帳戶才能看到的能力。這份報告不能保證未公開或客製資料不存在。

| 文件分區 | 索引項目數 | 與本項目的關係／核查重點 |
| --- | ---: | --- |
| Flight Info Direct | 48 | Snowflake 資料交付；13 個資料字典含 bookings、capacity、market trends；檢查新版週訂位及 preliminary/final adjusted 定義 |
| Flight Info API | 34 | 全部入門、遷移、使用說明、release notes 與 FAQ；航班資料與容量可用，沒有列出歷史訂位及票價資料集 |
| Flight Info Alerts | 54 | 時刻／運行狀態事件及變更；沒有證明事件流是售票／取消訂位事件流 |
| Analyser／Analyser+ | 217 | Schedules、Traffic、Connections、Mapper、DOT、Bookings、Status、Snapshot、匯出及 reference；分清報表聚合、估算與實際數據 |
| Pricing Products | 77 | Airfares、Market Trends、Snowflake Altus/GLAD、Airline PPS、Pharos、Channel Monitor、Vacation PPS、Customer Portal、版本更新；見 [產品深入核查](OAG_DATASET_PRODUCT_REVIEW_2026-11-11.md) |
| Industry Definitions | 6 | IATA 營運、服務、餐食、限制代碼；用於解讀欄位 |
| Flight Schedules Data | 2 | WDF 航班時刻格式，不是訂位交易 |
| Flight Status Data | 9 | 運行狀態、Daily Flight Leg Reports；歷史航班不等於歷史銷售 |
| Reference Data | 3 | 航空公司等參照資料 |
| Sample Data／相關 Release Notes | 15 | 時刻、容量、MCT、地點等範例及 WDF+；沒有將容量樣本當成真實訂位樣本 |
| Weather Conditions Data API | 8 | 天氣及預報，可作額外特徵，無法補足訂位與票價 |
| Flight Status API for JSON/XML | 14 | 舊版 flight-status 介面與 schema；非訂票／定價資料產品 |
| FVXML for FIDS | 16 | 機場航班資訊顯示資料 |
| What's New? | 28 | 另行核對集中更新，避免只看主章節漏掉其他版本說明 |
| Customer FAQs | 3 | 支援與維護流程，非資料集 |

### Flight Info API 的完整章節

- **Getting Started：** 5 篇文章，包括帳戶、試用、訂閱、Master Data 範例；另有 Migration 分類中的 FvXML 遷移指南。
- **Using the API：** 6 篇，逐一核對 Flight Info response、Content Parameters、Connections response、v1→v2、Schedules response、Master Data response。
- **Release Notes：** 主章節列出的 10 篇，從 Q2 2023 至 Q3 2026；另查 What's New 中額外的 API 變更頁，例如 Q4 2025 Carriers 更新。
- **FAQs：** 6 篇，涵蓋權限、收費、啟用、Free Tier、Connections 試用及更新頻率。

來源：[API 目錄](https://knowledge.oag.com/docs/%EF%B8%8Fflight-info-api)、[Using the API](https://knowledge.oag.com/docs/using-the-api)、[Release Notes](https://knowledge.oag.com/docs/release-notes-1)、[API FAQs](https://knowledge.oag.com/docs/flight-info-api-frequently-asked-questions)。

## 3. 會影響模型設計的區別

### 3.1 容量不等於剩餘庫存

`Seats` 是預測座位容量，`ActualSeats` 是實際機型／註冊飛機對應的座位容量。`totalSeats=180` 不能推論「還有 180 位未售」。普通 API 的 `bookingClasses` 定義是訂位艙等代碼／餐食，也沒有提供各日已售人數或成交票價。`Canceled` 狀態指航班取消，不是旅客取消預訂。[欄位定義](https://knowledge.oag.com/docs/flight-info-api-response-layout-descriptions)、[Content Parameters](https://knowledge.oag.com/docs/flight-info-api-content-parameters)。

補充：較新的 **Alerts Schedules** 文件另列 `bookingClasses[].quantity`，描述不足以確立它是全渠道即時可售庫存、淨訂位或售票事件。不能忽略此欄位，也不能用它自行反推 load factor。需要 OAG 說明含義與覆蓋。這個欄位出現在另一產品文件，不能據此聲稱普通 Flight Info API 已提供實際訂位資料。[Alerts Schedules Field Definitions](https://knowledge.oag.com/docs/flight-info-alerts-event-samples-schedules-field-definitions)。

### 3.2 Passenger Booking Data 有相關資料，但不能保證等於航空公司內部訂位表

2026 年的 Weekly Unadjusted View 有 `FILE_DATE`、`BOOKING_TRANSACTION_DATE`、航班號及各航段的出發日期／時間。版本說明記載每月 7、14、21 日及月底四批，另有約 1.5–2 天交付延遲，歷史自 2024 年 1 月開始。這對研究訂位提前期與曲線有用；四批更新不能直接稱為「每天的完整庫存快照」。[2026 Weekly View 更新](https://knowledge.oag.com/docs/q1-2026-release-notes-passenger-booking-data-1)。

`BOOKING_TRANSACTION_DATE` 是 PNR 原始訂位日期，`FILE_DATE` 是資料載入日期。若只用後來修訂過的資料依原始訂位日累加，未必能重現某天真正可見的淨訂位；取消、改票、刪除、回補與資料可用時間仍須確認。Unadjusted 是 MIDT/GDS 資料，Adjusted 是估算整體市場的模型資料，不能假定涵蓋 HK Express 全部官網／App 直銷。[Passenger Bookings 字典](https://knowledge.oag.com/docs/passenger-bookings-data-fields-explained)、[Adjusted／Unadjusted 解釋](https://knowledge.oag.com/docs/what-is-the-difference-between-adjusted-bookings-and-unadjusted-bookings)。

Load Factor View 的公開欄位是 travel month、航線、航空公司、座位及 passenger volumes，並非某日某一班機的實際最終滿座率。Adjusted Final 代表估算資料已完成調整，不能解讀為實際最終售票或登機清單。[Load Factor 字典](https://knowledge.oag.com/docs/passenger-bookings-data-fields-explained)。

### 3.3 Airfare Data 要申請逐筆觀測資料，並確認費用拆分

Standard 字典包含 `observation_date`、`observation_time`、航班／日期、`price_inc`、`price_exc`、`tax`、`currency`、艙等及來源等。當中 `tax` 可能包含稅、附加費和其他費用；`price_exc` 也不應不經驗證就當成團隊定義的純基本票價。

Premium 列有 `trip_fee_yq`、`trip_fee_yr` 等額外欄位（視來源是否可取得），適合進一步詢問「基本票價＋燃油附加費＋稅／其他費用」拆分。這些是觀測報價，不是每張實際成交票價。票價資料內的 availability／seat 欄位也可能截斷，例如 9 代表至少 9，不等於整架飛機只剩 9 位。[Airfares Data Dictionary](https://knowledge.oag.com/docs/airfares-data-dictionary)。

### 3.4 其他看似吻合的功能，仍有不同用途

- **Analyser+ Snapshot Comparison：** 官方明確只支援 Schedules metrics，不能選 Bookings 或 Status metrics。[說明](https://knowledge.oag.com/docs/getting-started-with-snapshot-comparison-in-analyser)。
- **Market Trends／Market Indicators：** 週聚合價格和部分模型估算的旅客／收入指標，可作市場參考，不可當成實際已售人數。[Market Trends 字典](https://knowledge.oag.com/docs/market-trends-data-dictionary)、[Market Indicators](https://knowledge.oag.com/docs/market-indicators)。
- **Altus：** 有逐航班但按提前週數聚合的 min/max/average，不等於每次歷史原始報價。[Altus 字典](https://knowledge.oag.com/docs/altus-data-dictionary)。
- **Traffic Analyser average fare：** 有 Travelport 票價統計及不同的 online fare 指標，口徑與時間粒度各異，不可用平均數冒充 D14 某班機當時報價。[平均票價定義](https://knowledge.oag.com/docs/how-is-the-average-fare-calculated)、[Online Fares 更新](https://knowledge.oag.com/docs/q4-2024-traffic-analyser-online-fare-data)。
- **Emissions／Fuel Burn：** 航班耗油／排放估計不是向乘客收取的 YQ/YR 燃油附加費。[Emissions 字典](https://knowledge.oag.com/docs/emissions-schedules-data-fields-explained)。

## 4. 建議向主辦方申請的範圍

主要申請 **Passenger Booking Data（優先 Weekly Unadjusted flight/leg-level history）＋ Airfare Data（優先原始歷史 fare observations；需要費用拆分時詢問 Premium）**。不用要求全球全量或必須即時 API；CSV、Parquet 或有權限的 Snowflake export 都可供原型使用。

建議先詢問 1–3 條 HK Express 航線，同一組航班的訂位與票價，最好 12 個月歷史；若準備時間或授權有限，先取得 1–3 個月的小樣本。3 個月有助接通／初步評估流程，不足以證明跨季節泛化。若沒有 UO，可接受標明為其他航空公司的相似低成本航線；不能據此宣稱已驗證 UO 效果。

每班機需有出發前 D28 至售票截止的觀測；每日理想，其他頻率須清楚標明。若只能提供每月四批訂位與週聚合票價，就按實際粒度設計較粗的 demo，不能填補後冒充真實每日資料。

同時請供應方確認：UO／航線覆蓋、GDS 與直銷比例、實際值／估算值、歷史版本與修訂處理、取消／改票口徑、跨表航班 join key、觀測／可用時間與時區，以及訓練、比賽展示及分享衍生結果的許可。隊伍已提交 request access；未獲確認。項目完全由隊員自費，沒有外部資助。

## 5. 給 Cathay 的英文郵件草稿（未寄出）

**Subject: Team E117 — Request for OAG Passenger Booking and Airfare Data Access**

Dear Cathay Hackathon Team,

Thank you for the update and for your continued support. Our main outstanding need is access to suitable data for our prototype.

We are Team E117, Airplane CPU, developing UOption Fly Pass. Our prototype recommends when to open member flight offers within 28 days before departure, how many seats to release, and what base fare to charge.

After reviewing OAG's documentation, we found that the Flight Info API provides flight schedules, operational status and seating capacity, but does not document the historical booking progression and airfare observations needed for this work. Seating capacity alone does not indicate how many seats remain unsold.

Could the Hackathon team help us obtain trial access or a small sample from these OAG products?

- **[Passenger Booking Data](https://www.oag.com/passenger-booking-data):** preferably the flight-level Weekly Unadjusted View, including booking dates, departure dates, flight identifiers, passenger volumes and historical file dates. We would also appreciate clarification on HK Express coverage, direct-sales coverage, and how cancellations and revisions are represented.
- **[Airfare Data](https://www.oag.com/airfare-data):** historical fare observations for matching flights, including observation dates/times, currency, cabin or fare class, total price, and base fare, taxes and fuel surcharges where available.

Ideally, the sample would cover a few HK Express routes and observations within the final 28 days before departure. A limited historical extract in CSV or Parquet would be sufficient to begin; we do not require a live API. An available sample from comparable low-cost routes would also be useful if HK Express data cannot be provided.

We have already submitted access requests through OAG's website, but access has not yet been confirmed. Our student team is entirely self-funded, so a complimentary educational sample or short-term Hackathon trial would be greatly appreciated.

With the event taking place on 14–15 November, could you please let us know whether either dataset can be made available in time, and whether it may be used for prototype model training and the Hackathon demonstration?

Thank you for your help.

Best regards,
Team Airplane CPU — E117

## 6. 我們需要的 dataset 表格

以下欄位名稱是團隊希望獲得的資料語義，不代表 OAG 已承諾全部提供。例子均為虛構；燃油／稅費數字不是現行收費。

| 優先級 | 資料集／資料類型 | 所需欄位與粒度 | 虛構例子 | 用途／產品適配情況 |
| --- | --- | --- | --- | --- |
| 核心 | 航班與座位容量 | 營運航空公司、航班號、出發日期／時間、起訖機場、機型、當時已知的座位容量、flight key、容量變更時間 | DEMO-001，HKG–FUK，容量 180 | 定義航班與供應上限；Flight Info API／Schedules Direct 可提供部分，實際可售容量及封鎖座位另確認 |
| 核心／主要申請 | 歷史訂位進展 | 每班機 × 觀測時點，D28 至售票截止的淨訂位／新增訂位、旅客數；或可重建的事件、載入／可用時間 | D28 已訂 90、D14 已訂 130、D7 已訂 150 | 預測正常需求、決定 WHEN／HOW MANY；Passenger Booking Weekly Unadjusted 有相關欄位，但非已確認的每日全渠道淨訂位快照 |
| 核心標籤 | 最終訂位／載客結果 | 每班機最終淨訂位、最終容量；登機人數、no-show 分開記錄；actual/modelled 標識 | 容量 180、最終售出 165、登機 161；未售 15 | 驗證餘位預測；OAG 月度航線 Load Factor 不等同此資料，實際航班級結果需另確認／航空公司樣本 |
| 核心正確性 | 訂位取消、改票與修訂 | 事件時間、原／新航班、旅客增減、取消／退款／改票標記；或供應方明確說明淨訂位已處理方式 | 新增 10、取消 2，淨增 8 | 防止把累計曾訂位當成仍有效訂位；Passenger Booking 公開字典尚未證明具備完整此類事件 |
| 核心／主要申請 | 歷史票價觀測 | 每航班 × 觀測日期時間，至少涵蓋 D28–截止；航班、票價、幣別、艙等／票種、渠道、單程／往返、乘客數、行李條件 | 同班機 D28 HK$630、D14 HK$750、D7 HK$900（總價） | WHAT FARE 的市場參考與基線；申請 Airfare Data 原始 observations，避免只拿週／月平均 |
| 核心價格拆分 | 基本票價、燃油附加費、稅／其他必收費 | base fare、YQ/YR、稅、其他費、含稅總價；標明包含項及旅程／航段計價單位 | 基本 500＋燃油 100＋稅費 150＝總價 750 | 正確展示 0／低基本票價但仍須付費；Airfares Premium 有相關欄位，來源可用性與拆分口徑待確認 |
| 決策效果驗證；缺少時用明示假設 | 歷史優惠與購買反應 | 優惠開放時間、價格、釋出量、曝光／符合資格人數、轉換、售出及取消；對照或實驗條件 | D14 開 8 位、基本票價 100、售出 6 位 | 驗證不同 WHEN／HOW MANY／WHAT 的效果及正常購票被取代風險；未在上述兩產品確認，通常需航空公司資料／實驗 |
| 商業情境；缺少時用明示假設 | 成本、附加收入與會員需求 | 每新增旅客成本、行李／餐飲等淨收入、正常票貢獻、會員數與日期／目的地偏好 | 新增旅客成本 60、附加服務淨收入 120 | 算增量貢獻、評估會費及供需；不是 Flight Info API 的售票資料，不作此次 OAG 申請的前置條件 |

跨表共同要求：相同航空公司／航班集合、可連接的航班識別、明確時區、觀測及資料實際可用時間、真實／估算／合成標記、資料字典、覆蓋說明及使用授權。假期／星期可另外建立日曆特徵。

**取得訂位及票價後，仍不等於已證明最優優惠價格或真實收益提升。** 無會員產品的實驗／反應資料時，Hackathon 可用歷史需求基線配合明示的購買反應與替代率情境展示三項決策，將模型預測驗證與商業假設分開報告。
