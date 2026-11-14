# E117：每日訂位曲線與歷史報價的替代資料來源

> 状态：记录（2026-11-12），内容不再修改


查核日期：2026-11-12。對象：HK Express（UO）；需求：同一出發航班 D28→D0 的每日有效訂位座位數／booked occupancy，以及同班、同條件的歷史 offered fare。僅查第一方公開資料；未聯絡供應商、購買或取得樣本。公開頁面的產品能力不是 UO 覆蓋或隊伍授權的承諾。

**結論：有值得索樣的替代供應商，但本輪沒有找到公開證據，能直接承諾提供 UO 全渠道、逐航班、每日 D28→D0 的完整淨訂位快照。** 建議優先經 Cathay Hackathon 主辦方向航司索取去識別化的航班彙總；歷史報價則另向 OAG／RDC／AirGain 驗證。Amadeus、Cirium、IATA 可補需求背景，但必須辨別間接訂位、票務交易及估算值。

## 供應商比較

| 候選／第一方來源 | 公開已證實 | 對本案的定位與未確認事項 |
|---|---|---|
| [Amadeus Booking Analytics](https://amadeus.com/en/airlines/products/booking-data-analytics) | 間接渠道 MIDT 訂位、訂位進展曲線、public fares；細至 flight number／booking class。 | 訂位曲線候選。不是 UO 官網／app 全量庫存的證據；每日歷史版本、取消／改票、UO 覆蓋及原始匯出均須確認。public fares 亦不能直接視作每筆實際成交價。 |
| [Cirium Diio Advance Bookings](https://www.cirium.com/analytics-services/diio-advance-bookings/) | 多 GDS 訂位；flight／route／market 粒度；歷史、當下及未來 booking analytics；**每週更新**且可匯出。 | 可比較 booking pattern；公開 cadence 不符合每日快照的直接保證。[Diio Mi](https://www.cirium.com/analytics-services/diio-mi/) 的 Schedule Snapshot 是班表版本，不能誤讀成每日訂位庫存。 |
| [Cirium Traffic and Fares](https://www.cirium.com/data/airline-traffic/) | GDS／MIDT 結合班表、政府及業界資料；包含 GDS-sourced NDC；有 O&D fare／service class。 | 市場需求與票價背景候選；不是已證實的逐班逐日可購買報價歷史，也不是直銷全量訂位。與 Advance Bookings 分開問產品與欄位。 |
| [IATA DDS](https://www.iata.org/en/services/data/passenger-traffic/direct-data-solutions/)／[ARC DDS](https://www2.arccorp.com/products-participation/products/direct-data-solutions/) | 航司貢獻資料、BSP、ASP 的 ticket sales；含直接及間接渠道；daily updates；segment／O&D／ticket 粒度。ARC 說明以貢獻航司 ticketing data 參與。 | 最值得由航司協助查問的 ticketing 候選。每日更新不等於每日保存完整在冊淨訂位；須查 UO 是否貢獻、直銷覆蓋、退改票狀態及 as-of 保留。未確認學生團隊可直接取得。 |
| [IATA MarketIS](https://www.iata.org/en/services/data/passenger-traffic/market-intelligence) | BSP 間接 ticketing 加內部模型估算；可看航段、旅程、銷售地、艙等及 average fare／estimated revenue。 | 適合市場量及平均票價基準。票務均價不是某天仍可購買的報價，估算流量不能作真實全機 booked occupancy 標籤。 |
| [RDC Apex](https://rdcaviation.com/products/apex/)／[fare coverage 公告](https://rdcaviation.com/news/rdc-aviation-expands-fare-data-coverage-to-467-airlines/) | Apex 含歷史及 forward fares、班表與路線盈利估算；2025-12-09 公告稱 fare dataset 覆蓋 467 航司，亦可獨立資料集交付。 | 歷史票價替代候選。須索取原始 observation time、flight/date、offered fare 定義、每日頻率、fare family／稅費及 UO coverage；本輪公開頁未證實這些細節，亦未證實每日淨訂位庫存。 |
| [RateGain AirGain Rate Intelligence](https://airgain.ai/products/rate-intelligence/) | 公開頁列 365 日歷史、模擬旅客搜尋採價、每筆 crawl timestamp；屬觀測報價。 | 歷史 offered fare 候選。同頁亦稱每個帳戶獨立採集、不重用別的客戶採價，故必須確認**新客戶能否獲得訂閱前既有 UO 歷史**，不能由「365 日歷史」推斷可回購任意路線。每日連續性、原始匯出與價格口徑仍待樣本。 |
| 航司 PSS／Revenue Management 資料匯出；技術例：[Navitaire RMIS 官方說明](https://www.navitaire.com/downloads/RMIS%20Brochure.pdf) | RMIS 可傳送 leg sold、journey booking、capacity／available unit 等變動事件，並向收益管理系統近即時串流。 | 最貼近有效訂位及庫存需求的來源方向。此為技術能力例子，**不是 UO 使用某系統或團隊可存取的證明**。需航司授權、初始快照和已保留事件／歷史；新串流不能自動補回過去。 |

依 Cirium 的[票務流程說明](https://www.cirium.com/thoughtcloud/decoding-airline-passenger-traffic-through-data/)，booked、ticketed、settled、flown 是不同狀態；MIDT 多為非航司直銷的 GDS 訂位。研究判斷：不能將任何市場資料的 booking count 除以全機容量，就直接稱為真實 booked occupancy。

## 最小樣本與驗收要求（本案建議，尚未發出）

先要求 10–20 個已完成 UO 航班驗證，再擴至 2–3 條 HKG 直飛航線、連續 8–12 週；單程、Economy、1 成人、香港 POS。這個小樣本用來驗收資料，並不足以證明全年預測表現。

1. **同班識別與時間**：operating carrier、flight number、departure date/time/timezone、origin／destination、cabin；每列 snapshot／observation time、首次可用時間及修訂版本。改時刻／改航班號要有穩定關聯。
2. **29 個觀測點**：D28、D27……D0 固定每日截點；D0 必須定義為起飛前可決策時間，不是離場後。供應商交付實際留存點與缺口表；每週值插值不能算每日真實快照。
3. **淨訂位定義**：座位佔用乘客數，不是 PNR 數；扣除截至當時的取消／轉出，納入有效轉入；交代 unpaid holds、嬰兒、團體位、超售及封鎖座位。明確標示 observed／estimated／sample，說明 UO 官網、app、旅行社等渠道覆蓋。
4. **容量與最終標籤**：每個截點可售容量、換機／封鎖變更、最終有效訂位；實際 boarded／no-show 另欄。`booked_occupancy = net_valid_booked_seats / applicable_capacity` 的分母需明確。最終未售與起飛空座不能混用。
5. **可比報價**：同班、同艙／fare family、渠道／POS、OW／RT、旅客數、幣別；base、tax、YQ／YR、總價、行李／必需費用、採集時間。不可拆分保留 null；查詢失敗、售罄、未採集分開，均不能填成零價格。
6. **通過條件**：可以穩定連結同班 29 個截點；全量訂位可與航司總數核對；取消／改票可重建；每筆在決策前已可得；價格條件一致。缺一項則降級為部分樣本、稀疏曲線或市場特徵，明示可用用途。費用、交付日、訓練／展示／共享／模型保留權及原始資料刪除期限另行確認。

## OAG 能如何支持模擬

OAG Airfares 有歷史觀測及時間欄位，交付 cadence 按訂閱配置；優先在通過覆蓋檢查後回放原始可比報價。產品規模及「每日採集」不保證指定 UO 航班 D28→D0 每日都有記錄。缺口需標記，任何補值亦需標成估計。[產品頁](https://www.oag.com/airfare-data)、[Airfares 字典](https://knowledge.oag.com/docs/airfares-data-dictionary)。

Weekly Unadjusted 的 2026 Q1 更新說明為每月 7／14／21／月底四批；它不是每天完整在冊庫存。booking transaction date 可研究樣本的購票提前期分佈，但尚未證實完整取消、UO 直銷與每個 as-of 版本；月度航線／航司 load factor 亦不是單班標籤。[Q1 release](https://knowledge.oag.com/docs/q1-2026-release-notes-passenger-booking-data-1)、[Passenger Bookings 字典](https://knowledge.oag.com/docs/passenger-bookings-data-fields-explained)。

以下是**建模提案，並非 OAG 的實測結果**：

- 設 D28 的初始有效訂位為 `B28`；若無航司快照，明示為情境假設。對之後每一天依次模擬新增需求 `A_d ~ Poisson(theta × g_d)`，以及取消 `C_d ~ Binomial(B_d, q_d)`；固定容量、無超售的簡化版本為 `B_next = min(K, B_d - C_d + A_d)`。換機、團體位及轉班另行建模；容量截斷後的已售量與未能接受的需求需分開。
- `g_d` 可用經驗證的 booking lead-time 樣本估計**該樣本渠道的形狀**；未證實渠道代表性時，不能宣稱是全 UO 曲線。`theta`、`B28`、取消率和全渠道修正仍須真實資料或明示假設；部分 booking counts 本身不能辨認完整訂位量。
- 每欄保留 `observed / estimated / simulated / assumed` 來源。真實歷史報價配上模擬 occupancy 可以驗證程式與決策流程，但兩條曲線的關係不是已量測的價格—需求關係，亦不能據此聲稱收益提升或安全放位已獲驗證。
- Flight Info API 的班表／容量資訊只能提供航班骨架及容量背景；單靠這些欄位無法校準上述每日訂位與票價兩條曲線。現有欄位審核見 [OAG API 資料查核](OAG_API_DATA_AUDIT_2026-11-11.md)。

建議索樣順序：航司全量快照優先；報價並行詢問 OAG、RDC、AirGain；Amadeus／Cirium 作訂位樣本替代，DDS 由航司協助核對可用性，MarketIS 作市場背景。這是依公開粒度與本案匹配度提出的次序，不是價格、交期或取得機會排名。
