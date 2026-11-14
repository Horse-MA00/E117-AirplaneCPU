# Client Portal：彈性日期及國家／地區搜尋

> 状态：现行 · 对应代码：`frontend/members/search.js`、`frontend/members/airports.js`

更新日期：2026-11-14。

## 使用方式

在 `/members` 的 **Find your next flight**：

1. **Flying from** 選出發機場，或保留 Any airport。
2. **Destination country / region** 選 Japan。
3. 按 **Next month**，自動填入香港日曆中下個月的第一天及最後一天；或自行輸入 **Earliest departure** 與 **Latest departure**。
4. 按 **Search flights**。結果同時搜尋目前目錄中所有屬於日本的目的地機場，旅客不必逐日、逐機場搜尋。
5. 可在結果的 **Sort by → Lowest ticket price** 找區間內最便宜的已發布會員票。

例如範圍設為 2027-05-01 至 2027-05-31，5 月 1 日的福岡與 5 月 31 日的大阪均符合；4 月 30 日及 6 月 1 日則不符合。這只是搜尋條件示例，頁面結果仍以當時已發布的航班為準。

使用者提出的 **15–21 May 2027** 是日期範圍：Earliest departure 填 `2027-05-15`，Latest departure 填 `2027-05-21`。若只要某一天，展開 **Choose a specific airport or date**，用 **Exact departure date (optional)** 的日曆選日。這個日曆可選任意有效日期，不再只列已發布優惠的日期。

## 規則與邊界

| 操作 | 行為 |
| --- | --- |
| Flying from／Destination airport | 使用同一份完整搜尋航點目錄，按國家／地區分組。沒有優惠、或刷新後優惠消失，機場仍可選；例如可搜尋日本出發返回 HKG。 |
| 選國家／地區 | 匹配該地區在搜尋航點目錄中的所有機場。沒有發布航班的地區仍可選，但顯示無結果。 |
| 自訂日期範圍 | 起訖日期均包括在內；搜尋的是單程出發日期，不是回程、入住日期或會員有效期。 |
| 只填 earliest / latest | 分別表示該日或以後／該日或以前，不會偷偷補另一個限制。 |
| Any dates | 清空所有日期限制，保留國家、機場及出發地；按 Search 才更新結果。 |
| Next month | 依真正的香港當前日期計算完整下一個月，支援跨年及閏年；不會移動到合成資料所在月份。 |
| Choose a specific airport or date | 可收窄目的地機場，或選確切一天。選確切日會將起訖設成同一天；修改日期範圍會清除確切日選項。 |
| 切換國家／地區 | 如果已選機場不屬於新地區，立即清除該機場限制；結果仍等 Search 後才更新。 |
| 結束日期早於開始日期 | 顯示英文錯誤並阻止搜尋，維持上次有效結果；更正或使用日期快捷鍵即可恢復。 |
| Refresh availability | 重新讀取已發布庫存，保留輸入及已套用的搜尋；結果摘要不會把未提交的輸入當成已套用條件。 |
| Clear search | 重設出發地、地區、機場、全部日期及 Available seats only，立即顯示全部已發布航班。 |
| 無匹配航班 | 清楚顯示 No matching flights，提供 Show all released flights 重設，不生成虛構報價。 |

## 搜尋航點目錄與核對

2026-11-14 核對 [HK Express 官方目的地](https://www.hkexpress.com/en/destinations) 與 [官方出發城市列表](https://www.hkexpress.com/zh/sitemap/flights-from-cities/page-1)，東京分開羽田／成田後共 37 個機場（含 HKG 及已公布的 HFE），再保留使用者指定的 CTS，合共 **38 個常駐可選機場**：

| 國家／地區 | IATA 機場代碼 |
| --- | --- |
| 香港 | HKG |
| 日本 | HND、NRT、KIX、NGO、FUK、OKA、HIJ、TAK、SDJ、KMQ、ISG；CTS 為使用者要求保留的未確認班表選項 |
| 韓國 | ICN、PUS、TAE、CJU |
| 中國台灣 | TPE、KHH、RMQ |
| 中國內地 | PKX、CZX、WUX、NGB、SYX、YIW、HFE |
| 泰國 | BKK、CNX、HKT |
| 越南 | HAN、DAD、PQC |
| 馬來西亞 | SZB、BKI、PEN |
| 菲律賓 | MNL、CRK |

- 吉隆坡使用 **SZB（Subang／梳邦）**，沒有把它誤設為 KUL。[官方吉隆坡航線公告](https://www.hkexpress.com/About-Us/Media-Centre/HK-Express-Launches-New-Route--to-Kuala-Lumpur-Subang-on-1-August)
- HFE 在官方列表中，公布於 **2026-12-03** 啟航、須待監管批准。選項標示 Announced，資料保存 `serviceStartsOn`；列入搜尋不代表當下已營運。[官方合肥公告](https://www.hkexpress.com/Plan/Special-Offers/Promotions/cm_flashsale_20260930)
- CTS 未在本次官方定期航點列表出現。使用者明確要求札幌，因此保留為 **Schedule unconfirmed**，不宣稱是已核實的定期航線。Cathay 先前年報提及札幌短期季節包機。[2023 年報](https://www1.hkexnews.hk/listedco/listconews/sehk/2024/0402/2024040204043.pdf)
- 舊原型認識的 DMK、SGN、CEB、SIN 保留名稱／地區映射，只有已發布優惠實際使用時才增加到選單；不將它們列入上述已核對航網。未知代碼仍歸入 Other published airports，不猜測所屬國家。

這是一份有核對日期的搜尋目錄，不是即時班表，也不代表任意兩機場間有直航。新增地點時更新 `members/airports.js` 的名稱、地區、狀態和文件來源。會員機位是否可訂始終取決於已發布優惠及後端庫存。

## 實作與資料來源

- `/api/member-portal/flights` 仍提供 SQLite 已發布優惠。前端只作條件篩選，不新增 API、資料表或虛擬庫存。
- `members/airports.js` 獨立維護機場目錄、地區、英文名稱及已公布／待確認狀態。兩端機場選單取「常駐目錄 ∪ 已觀測端點 ∪ 仍選中的端點」，不再從可售航班縮減成少數選項。
- `members/search.js` 負責地區匹配、日曆日期比較、格式化及下個月計算。
- 使用 `Temporal.PlainDate` 處理沒有時區的出發日期；「現在」先投影到 `Asia/Hong_Kong` 再取得下個月。使用者瀏覽器在其他時區也不會令日期偏移一天。
- 支援原生 Temporal 的瀏覽器直接使用原生；其他瀏覽器按需載入本機打包的 `temporal-polyfill`。已提交 bundle，不依賴外部 CDN、網絡字體或運行時 npm 安裝。
- 表單有可見標籤、fieldset/legend、原生 date/select、錯誤文字及鍵盤焦點。修改條件後需明確按 Search；390px 手機採單欄。
- D28／D14／D7 放票規則、NHPP 保護、會員費與購票價格校驗繼續由原有後端處理。搜尋下個月不代表會員配額已提前開放。

## 驗證

`npm run test:flexible-search` 使用隔離 fixtures，驗證日本多機場、日期兩端、單端範圍、精確機場／日期、跨國切換、未知機場、無匹配重設、刷新、無效日期修復、香港與洛杉磯時差、12 月至次年 1 月、閏年 2 月及 390px 排版。所有 API 被攔截，只允許讀取 fixture，不購票、不呼叫 LLM。

`npm run test:members` 同步通過既有入會／購票確認、價格變更、售罄、刷新失敗後保留成功紀錄、鍵盤操作及手機版回歸。測試中的購買請求由 fixture 回覆，沒有新真實付款或模型呼叫。

`npm run test:route-catalog` 先在修復前重現「兩端缺航點／確切日仍是優惠日期 select」，再驗證 sparse／空優惠時 38 個航點仍完整、返回 HKG、未發布航線不生出票價、未知代碼、自由選日及刷新保存、May 15–21 的包含邊界及清除。這組測試也只允許 fixture GET。
