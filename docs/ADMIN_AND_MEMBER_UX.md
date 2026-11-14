# Admin 與會員購票介面

> 状态：现行 · 对应代码：`customer-panel-v1`、`frontend/index.html`、`frontend/experiments.js`、`frontend/adaptive-pricing.html`、`frontend/members/index.html`

2026-11-15。Admin 的 Optimize prices 統一使用 Thompson Sampling；會員端及已保存資料保持原有交易規則。全部介面使用英文，金額使用 HKD；航班及購買仍為 Hackathon 合成示例，沒有實際付款或航空出票。

主配色為紫 `#6F2C91`、青 `#24BCDC`、白。Admin 使用 Forecast / Optimize / Experiments / Manage offers；Experiments 只顯示已保存的會員購票回饋。Client 提供票價排序、可售座位篩選、基本票價與費用明細及三步購票流程。最新演算法以 [航班優化流程](FLIGHT_SCOPED_OPTIMIZATION.md) 為準；下文保留交易 API 與舊 panel 規則。

## Optimize 單一入口（2026-11-15）

- Optimize 的標準路徑為 `/adaptive-pricing`，保留完整 Admin 導航。舊 `/admin?run=adaptive-…&round=4#optimization` 連結以取代歷史項目的方式轉到 Thompson，保留已保存實驗及輪次參數；不新增一次實驗。Forecast／Manage offers 的連結帶入所選航班及有效放票日。
- 移除舊 Math／Math+LLM 優化表單、雙軌結果、貢獻／成本圖及參考定價區塊。主 Admin 不再載入 `optimization.js`／`continuous.js`；相容 API、SQLite 及歷史證據保留原樣。
- Thompson 保留航線、日期／航班、D28／D14／D7、輪數、客群人數、權重、種子、驗證批數、並行及呼叫上限。新實驗固定使用八類彈性優惠旅客（`flexible_deal_seekers`），移除 Target customer scenario 選擇器及 Legacy 客群選項；八類權重仍可自行調整。`Simulated customers (offline)` 與 Live LLM 是顧客選擇的來源，兩者都由同一 Thompson Sampling 方法選價。
- 結果保留已保存實驗、逐輪表、價格／收入曲線、最終候選、獨立驗證及會員回饋連結。歷史結果沿用當時價格、算法和客群，包括舊十四類客群；只讀展示不提供重開 Legacy 客群的 UI 選項，也不套用新版宣傳價重寫資料。所有人均已入會，Optimize 不計會費，只比較基本票款；會員網站會費由 Manage offers 另行管理。
- Forecast 保留需求篩選、四個座位指標、座位分配及預測／票價圖。Thompson 用航線及航班選擇器載入當下配額；不能因航線屬 Low demand 而跳過零配額檢查。
- Manage offers 繼續讀取相容引擎的既有已驗證建議及檢查發布庫存。Thompson 尚未加入直接套用／發布連線；需自行審閱保留票價，再明確輸入優惠草稿。Optimize 的實驗不改寫會員 plan、已發布價格或座位。

## 最終宣傳票價

新定價實驗在選出原始候選後，先把會員基本票價向下取到尾數9；低於HK$30的結果改為HK$0（包括30–38向下取整得到29的情況）。前端顯示原始選價與最終宣傳價，驗證數字來自實際調整後票價，並非只修改顯示。Adaptive 的初始對照也先格式化；舊實驗保留原有價格與標籤。Manage offers 的既有相容引擎建議使用經驗證的最終票價；Thompson 結果仍需另行輸入草稿，人工輸入不會被靜默改價。

## 兩個入口

| 入口 | 使用者 | 可以做甚麼 |
|---|---|---|
| `/admin`（原 `/` 亦可使用；Optimize 進入 `/adaptive-pricing`） | 團隊／管理員 | 航班預測、Thompson 票價實驗、會員回饋、發布會員位及設定會員費 |
| `/members` | 模擬旅客 | 查詢已發布航班、查看完整價格、加入會員、確認預訂、查看已保存行程 |

兩者共用 SQLite 的已發布優惠、會員及訂位。Admin 發布配額後，會員端才可購買；購買會實際扣除這個示例資料庫的配額，Admin 重新讀取庫存即可看到變化。兩者是介面與路徑分開，並非已完成生產環境的身份驗證或權限隔離。示例身份為本機測試 ID，不收集旅客個人資料。

## Experiments：What members said

`/admin#customers` 只顯示自適應定價實驗的會員回饋：選擇已保存實驗及輪次，閱讀該輪分析摘要、分析來源與個別會員的購買／拒絕理由。它直接讀取已保存的資料；開頁、切換或重新整理都不啟動實驗或呼叫付費 LLM。無結果、讀取失敗及尚無完成輪次各有明確狀態。

`/admin?run=<run_id>&round=<round>#customers` 可分享指定實驗／輪次；未指定輪次時選最後一輪。摘要保持原始輸出並以純文字呈現，不能當作真實客戶研究。快取摘要、規則摘要及 LLM 摘要分開標示，個別決策保留來源。

自適應定價頁 `/adaptive-pricing` 的「Read member feedback in Experiments」連結攜帶當前 run ID。原「How the price changes」折線圖已移除；該頁保留輪次結果表、價格與收入關係圖及獨立驗證。六階段舊工具仍可由 `/admin#panel` 存取，共享市場保留在 `/admin#market`；兩者不再放在 Experiments 主頁。

## 大型 Customer panel

- 規則模式：1–1,000 人；Live LLM：1–100 人，預設面板100人。
- 每人仍為六階段獨立旅程，使用原本英文/HKD情境；擴大人數不會把14種假想需要變成已驗證的HK Express客群比例。
- 採背景批次執行，HTTP啟動請求立即返回run ID。每名旅客單獨保存checkpoint，重新整理頁面不會重開一輪。
- Live每批預設60次有選擇的決策嘗試，最多120次；這個上限包含快取讀取。介面另列真正provider dispatch、快取、唯一合法動作、規則決策和失敗，避免把所有階段都當成新LLM回覆。
- 唯一合法動作由環境執行，來源為`environment_forced`。有多個合法選擇才需要LLM。失敗會保留原文與已完成狀態，不用規則回覆代替。
- 額度耗盡或錯誤後暫停；只有明確按Continue才開下一批。背景輪詢不增加呼叫額度。最多三個工作者同時決策。
- 新panel凍結prompt、相關實作hash、模型及endpoint hash。版本改變後可以查看歷史，但不能續跑混合不同模型／規則。

Admin先顯示入會、曾購票、取消、完成進度，再按客群比較；可搜尋或篩選分頁名單，最後選一人查看六階段。入會分母排除既有會員與尚未決策的人；購票數包括後來取消者，取消另列。尚未完成的結果必須標為partial。

## 會員購票流程

1. 使用本機生成的demo ID，查閱有效會員及已訂行程。
2. 以起點、目的地和日期查詢Admin已發布優惠。沒有配額時顯示空狀態，不能在瀏覽或搜尋時偷偷建立庫存。
3. 每張票顯示會員基本票價、必付稅費及完整票價。正常票價只供同時點比較，這個會員網站不提供正常票結帳。
4. 未入會者先看到當前年費及首次購票合計，再明確確認模擬入會。既有有效會員不再付一次會費。
5. 再確認所選會員票。結帳以後端價格、最新模擬日及NHPP保護量檢查，SQLite交易避免搶最後一位時超賣。瀏覽不保留座位。
6. 成功後在My trips查看資料庫保存的訂位。重新整理或重開同一個本機demo ID仍能查看。

這版每次訂一位持卡人的會員票，未增加行李購買、同行者購票、退款或真實支付。會員費與航班付款是兩個明確步驟；入會後若航班售罄，會員仍然有效，不自動退款或假稱已出票。

## 價格及庫存的來源

`membership_plan`資料表保存會員端會費，預設HKD399。Admin在Offer management明確保存新會費；價格篩選或panel中的假想會費不會自動改變會員網站。舊會員保留實際已付費用，新用戶依當前plan入會。

會員入會POST不接受前端自行指定成交會員費；選填`expected_fee`核對使用者已看見的價格，若Admin改價則拒絕並要求重新確認。買票同樣可用`expected_total`核對總價。優惠票價來自已發布的不可變批次，不能靠送出`total:0`或倒退模擬日繞過檢查。

多輪同航班優惠共用保護上限。會員搜尋每航班選出最便宜的可售批次，其顯示數量為`min(該批未售, 當前可成交上限)`；不能把同航班各批的可售數量相加，否則會重複計入同一個安全額度。D28／D14／D7新增配額規則保持不變。

## API

| 方法 | 路徑 | 用途 |
|---|---|---|
| POST / GET | `/api/agents/panels` | 新背景panel／panel清單 |
| GET | `/api/agents/panels/{id}` | 進度、摘要、分組及精簡旅客列 |
| GET | `/api/agents/panels/{id}/people/{customer_id}` | 單人的完整六階段 |
| POST | `/api/agents/panels/{id}/resume` | 明確增加一批決策額度 |
| GET | `/api/member-portal/config` | 當前會員plan與示例範圍 |
| GET / POST | `/api/member-portal/plan` | 讀取／由Admin更新會費 |
| GET | `/api/member-portal/flights` | 已發布的航班、完整票價及可售量 |
| GET | `/api/member-portal/accounts/{id}` | 會員狀態及已訂行程 |
| POST | `/api/member-portal/join` | 按後端plan入會，只收一次 |
| POST | `/api/member-portal/book` | 按當前庫存與保護條件確認會員票 |

原`POST /api/agents/run`保留小型同步相容介面；新版Admin使用背景panel API，不受舊5人UI上限限制。Shared market和panel仍是不同實驗；會員網站的SQLite交易也不會覆寫已完成的LLM市場結果。

## 驗證

執行結果及具體數量見[最新進度](ITERATION_2_PROGRESS.md)。`backend/tests/test_panel_jobs.py`覆蓋批次、續跑、大小限制、來源計數及版本凍結；`backend/tests/test_member_portal.py`覆蓋後端會費、過時價格、庫存保護、跨輪模擬日、持久資料及最後一位併發。

`python scripts/smoke_member_portal.py`會對實際本機API建立一名測試會員、買一張已發布的示例票，並核對保存行程及會費不重收。它會改變示例庫存，但不會呼叫LLM或支付金錢。
