# Admin 與會員購票介面

> 状态：现行 · 对应代码：`frontend/index.html`、`frontend/adaptive-pricing.html`、`frontend/experiments.js`、`frontend/app.js`、`frontend/members/index.html`、`member-thompson-v5-marketing`

更新：2026-11-15。所有介面使用英文及HKD；紫 `#6F2C91`、青 `#24BCDC`、白為主配色。Admin只保留目前Thompson流程，舊定價、panel、journey和共用市場頁面已刪除。所有付款及出票都是模擬。

2026-11-15 介面重構（版面與視覺規則見 [FRONTEND_UI](FRONTEND_UI.md)）：Admin 與 Optimize 共用左側導航，流程為 Forecast seats → Optimize prices → Publish offers（原 Manage offers，路由仍為 `#members`）→ Results（新增 `#results`），證據頁 Member feedback（原 Experiments，路由仍為 `#customers`）。四個流程頁共用頂部航班選擇欄（需求分類、航線、航班、放票輪次），在頁面之間保留選擇，並以 `?flight_id=&forecast_day=` 在 Admin 與 `/adaptive-pricing` 之間傳遞。

## Forecast seats

選擇需求分類、航線、日期／航班及觀測日。四張數字卡區分：

| 指標 | 含義 |
|---|---|
| NHPP recommended member seats | 正常訂位快照的空位減去正常需求保護量 |
| Forecast headroom | 考慮示例已售會員位後，仍可容許的會員空間 |
| New seats releasable today | 本輪扣除前輪有效未售配額後，可新增發布多少位 |
| Published seats bookable now | 已發布且通過目前實際庫存保護的可購買位 |

座位分配圖將已訂位、正常需求保護、已發布及未發布空間分開；下方顯示正常訂位預測和已觀測正常基本票價。非放票日可觀察預測，但不能新增配額；按鈕標示下一個有效D28／D14／D7。沒有會員供應時不啟動定價。

## Optimize prices

`/adaptive-pricing`是唯一票價實驗頁，Admin導航直接進入此頁。沒有指定實驗時，自動開啟該航班及輪次最近一次已完成的實驗；有保留票價時顯示「Publish at HK$…」，帶同一航班及輪次到 Publish offers（不自動填價）。Forecast與Manage offers會帶入航班及有效放票日。舊`#optimization`／`#pricing`／`#panel`／`#market`顯示頁面已不可用，不讀取舊資料，也不轉成另一個流程。

設定航線、航班／日期、放票輪次、價格輪數及每輪新會員數。所有實驗固定八類彈性優惠旅客；沒有Target customer scenario或Legacy選項，八類權重仍可調整。進階設定包括種子、獨立驗證批數、並行呼叫及明確的總呼叫上限。

`Simulated customers (offline)`和Live LLM只改變顧客決策來源；兩者都由Thompson Sampling選價。P₀由航班正常基本票價的80%上限導出。旅客已入會，票價實驗不收會費。

結果包含：

- 航班的正常票價、初始會員價和NHPP配額。
- 已保存的目前v5實驗、每輪價位、會員購買和基本票款。
- 模型估計的價格／預期收入曲線；不是每個點都真的呼叫LLM測試。
- 原始選價、向下取尾數9／低於30歸零後的候選價及獨立確認。
- 初始、候選與無優惠的配對比較，以及最後保留價／無定論／NO_OFFER。
- 新LLM呼叫、快取、強制動作與失敗的獨立計數。

已刪除的舊實驗ID會顯示不可用，不會偷偷換成另一份結果。保存結果及回饋瀏覽不啟動新實驗。

## Experiments：What members said

`/admin#customers`只顯示目前v5實驗的已保存回饋：選擇實驗和輪次，閱讀分析摘要與個別會員的購買／拒絕理由。可用`/admin?run=<run_id>&round=<round>#customers`分享。輸出以純文字呈現，並標示來源；它是合成角色回答，並非真人研究。

## Publish offers（`#members`，原 Manage offers）

管理員在頂部航班選擇欄選擇航線、日期／航班、放票日，查看當前配額，再人工輸入會員基本票價及新增位數。沒有自動套用功能：頁面只顯示同航班、同輪次最近一次已完成 Thompson 實驗的保留票價作參考，並可開啟該航班的 Thompson 實驗。右側即時預覽會員網站上的航班卡片和完整付款金額，只用於顯示。

發布會核對80%票價上限、整數價格、合法放票日、正常需求保護、前輪未售及已售會員位。每班每輪只能發行一次，不能倒退模擬時間。實驗完成不等於發布，會員網站只顯示正式儲存的優惠。

會員plan在此獨立管理。保存會費改變之後的新入會報價，不會向舊會員再收費，也不是Thompson的待優化參數。

## Client Portal

`/members`可設定起點、目的地或國家／地區，以及單日或彈性日期範圍；細節見[彈性搜尋](CLIENT_FLEXIBLE_SEARCH.md)。查詢只讀取已發布優惠，不會自動創造庫存。

1. 每張卡片大字顯示基本票價，下方列必付費用及完整付款。
2. 未入會者先確認當前會員費，再模擬入會；有效會員不再付一次會費。
3. 確認會員票，伺服器重新核對價格、會員狀態及可售庫存；瀏覽不保留座位。
4. 成功後在My trips查看SQLite保存行程；同一個本機demo ID可重新載入。

每次購買一名持卡人的一張會員票。未提供真實支付、航空出票、退款或取消操作。優惠售罄不會自動退會費。示例身份沒有生產環境的登入與權限隔離。

## 資料與檢查

會員plan、優惠批次及訂位共用SQLite；Thompson實驗則使用隔離的合成世界。帳本核對含必要費用，只有票價實驗的收入指標排除稅費與成本。

瀏覽器檢查涵蓋導航、當前v5回饋、空狀態、手機版、價格格式、表單和購票核價；實際檢查紀錄見[維護紀錄](ITERATION_2_PROGRESS.md)。API清單見[技術實作](CURRENT_IMPLEMENTATION.md#http介面)。

## Results（`#results`，2026-11-15 新增）

顯示所選航班的會員已售座位、剩餘配額、會員機票收入（已售座位 × 會員基本票價，不含會員費）及另列的強制費用，並以與 Forecast 相同的座位口徑顯示更新後的座位分配。數字只由 `/api/offers` 的 `quantity`、`remaining`、`base_fare`、`fees` 計算，沒有新增接口。從會員網站以瀏覽器「上一頁」返回時（包括頁面快取恢復）會重新讀取配額和預測。
