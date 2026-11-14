# Admin 與會員購票介面

> 状态：现行 · 对应代码：`customer-panel-v1`、`frontend/index.html`、`frontend/members/index.html`

2026-11-14。這次更新擴大 Customer panel、重新安排 Admin 資訊，並加入獨立會員購票網站。全部介面使用英文，金額使用 HKD；航班及購買仍為 Hackathon 合成示例，沒有實際付款或航空出票。

後續全面重設已完成：主配色改為紫 `#6F2C91`、青 `#24BCDC`、白。Admin 使用 Forecast / Optimize / Experiments / Manage offers；Optimize 已加入數學／LLM 雙軌價格搜尋與 SQLite 保存，原 Customer panel 和 Shared market 移至 Experiments。Client 加入票價排序、只看可售座位、清楚的完整票價／會員費及三步購票流程。最新畫面及演算法以 [航班優化流程](FLIGHT_SCOPED_OPTIMIZATION.md) 為準；下文保留原交易 API 與 panel 規則。

## 最新簡化操作（2026-11-14）

- Forecast 保留四個座位指標、座位分配及預測／票價圖；移除底部三輪明細、已發布批次表、β 說明及 Admin footer。D28／D14／D7 的後端扣減規則不變。
- Optimize 不再要求輸入 P₀／V₀、輪數、旅客數或進階搜尋參數。P₀ 由該航班資料導出，新指定航班實驗的會費由後端固定 HK$399。預設為 14 位旅客、2 個搜尋市場、6 輪 Live LLM、50% 放票比例；數學模型仍使用公式與細網格。LLM 總呼叫額度和每批額度保留。
- Manage offers 選定航班後自動載入該航班／輪次的結果。已通過驗證者顯示票價與建議座位；尚未執行者提供帶入航班及輪次的 Optimize 連結。NO_OFFER、執行中及舊版本結果各有狀態，不當作可發布建議。返回頁面會重新讀取結果。
- 固定 HK$399 只適用於新指定航班 Optimize；歷史結果及會員網站已保存的 plan 不會被瀏覽或試算偷偷改價。套用建議後，發布時仍核對實際會員 plan 的會費。

## 兩個入口

| 入口 | 使用者 | 可以做甚麼 |
|---|---|---|
| `/admin`（原 `/` 亦可使用） | 團隊／管理員 | 航班預測、價格篩選、客群分析、共享市場實驗、發布會員位及設定會員費 |
| `/members` | 模擬旅客 | 查詢已發布航班、查看完整價格、加入會員、確認預訂、查看已保存行程 |

兩者共用 SQLite 的已發布優惠、會員及訂位。Admin 發布配額後，會員端才可購買；購買會實際扣除這個示例資料庫的配額，Admin 重新讀取庫存即可看到變化。兩者是介面與路徑分開，並非已完成生產環境的身份驗證或權限隔離。示例身份為本機測試 ID，不收集旅客個人資料。

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
