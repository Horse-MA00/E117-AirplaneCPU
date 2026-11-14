# LLM 旅客情境與原始決策紀錄

2026-11-14 更新。Customer Agent 面板使用六階段、可重播的旅客旅程，保存每一次實際模型輸入、原始輸出、驗證及狀態變動。最新輸出契約為 `traveller-journey-v2.2-en`：英文理由與客群名稱、HKD 金額。歷史 `v2.1` 的完整 112 世界／672 個 DeepSeek 決策已完成，見 [基線實驗](LLM_BASELINE_EXPERIMENTS.md)；它們仍是舊版證據，不會因新 prompt 上線而自動成為新版測試結果。

## 為甚麼以前出現中英日混合，現在如何統一

原先人物資料的 `language` 隨機使用 `zh-HK`、`en` 或 `ja`，system prompt 又明確允許理由使用人物語言，因此日文與中文不是前端翻譯產生的。客群名稱本身也以中文儲存。日文回應把港元誤稱為「円」，則是另一個幣別錯誤。

新版把人物背景與報告語言分開：

- 人物原有 `language` 只表示背景，不能用它推斷預算或願付價格；所有新決策的 `reason` 使用英文。
- 客群名稱使用英文；動作仍為 `JOIN_PASS`、`BUY_MEMBER` 等既有代碼。
- 全部預算、會費、票價、附加費及退款以 HKD 計算；不能因目的地在日本或人物語言為日文而換成 JPY。
- prompt 與結構化 context 說明完整價格、預算範圍及可用性限制。輸出在執行前接受驗證；失敗原文仍保存，不能偷偷替換成規則決策或翻譯後冒充原始模型回答。
- 舊 audit、舊實驗及其中的原始中日文保持原樣。新 prompt 改變 request hash，舊快取不會作為新 prompt 的回應使用。要取得新版顯示結果，需執行新版場景。

統一語言有助閱讀及比較，不會令生成選擇自動變成真實客戶行為，也不能保證所有簡短理由的算術或判斷正確。可執行金額、資格和庫存由環境驗證。

## 背景面板與規模

目前Admin使用`backend/panel_jobs.py`：預設100人，Live最多100人、規則最多1,000人，六階段逐人保存。新背景面板跳過唯一合法行動的provider呼叫，標為`environment_forced`，與上面的30次全階段provider驗證不同；兩者不可混算來源。Live每批預設60、最多120個有選擇的決策嘗試，快取亦計入批次額度，真正dispatch與cache另列。必須明確Continue才能續跑，原始紀錄、失敗及版本證據保持可查。介面及API見[Admin與會員流程](ADMIN_AND_MEMBER_UX.md)。

## 情境與客群範圍

14 個基礎人物覆蓋彈性低預算、學生、固定假期、高頻休閒、家庭、雙人、探親訪友、臨時必要出行、自費商務、跨市場、同行小組、協助需求、低頻旅行及無匹配航線。每個人物有明確預算、旅行頻次、可旅行日期、同行人數、行李、最低安排時間與既有會員狀態。

這是對不同需要的覆蓋，不是 HK Express 真實客群分布。群體比例、旅遊頻次、可用性預期與預算均為情境設定。不能用國籍、語言、年齡或協助需求推斷願付價格。現在的跨市場人物仍使用 HKG 出發的示例班表；真正入境方向、多段行程、競爭航空公司及更廣的航線需要新增明確 fixture，不能宣稱本次已模擬全部實際市場。

## 六階段旅程

| 階段 | 模型看見甚麼 | 可以做甚麼 | 環境處理 |
| --- | --- | --- | --- |
| 會員發現與評估 | 完整會費、365 天期、預期旅行、會員不保證有位、同行者規則、總預算 | 入會、拒絕；既有會員保留會籍 | 會費只扣一次；既有會員不再扣錢 |
| D28 報價 | 正常票、會員票、替代日期／目的地、完整稅費行李、座位及協助確認 | 正常買票、會員買票、等待、拒絕 | 驗證日期、最低提前期、同行座位、會員資格與預算 |
| D14 報價 | 新正常價格、會員位售罄案例、替代選項 | 可行選項、等待、拒絕；已購票者保留 | 不把售罄會員票列為合法購買 |
| D7 報價 | 更少座位、較高正常價、剩餘會員位、短提前期 | 可行購買或拒絕；已購票者保留 | 不再提供無限等待，不重複購買同一旅程 |
| D3 計劃變動 | 當下才揭露不能成行、日期不確定或沒有變動；明確取消規則 | 保留或取消已購票 | 只退設定的可退稅款扣手續費；不退會費、基本票價或行李費 |
| 會員期末 | 這次旅程的購買、取消、總支出及未來需要 | 續會意向、不續會、日後考慮 | 只記意向，不產生續費或虛構新交易 |

第一版追蹤一個細緻旅程，而非虛構一整年的交易。訂閱時的期內價值與期末未來旅行仍是期望；財務優化器另負責完整會員期的市場模擬。兩者不應混合成「模型已觀察到全年使用」。

## 面板實際使用的示例與讀法

預設會員基本票價為 HKD70、會費為 HKD399／365 日。以下是環境內的測試劇本；Agent 在每一步只看到當下報價，不提前看到下一輪：

| 項目 | 目前設定 | 用意 |
| --- | --- | --- |
| 主行程 | HKG → FUK，2027-05-30 10:30 | 測試日期、時間與目的地是否合適 |
| 替代行程 | HKG → KIX，2027-05-31 18:30，正常基本票價比主行程低 HKD100 | 測試旅客是否願意接受可行的替代日期／目的地 |
| 主行程正常基本票價 | D28：HKD600；D14：HKD650；D7：HKD800 | 測試等待時的價格與機會成本 |
| 主行程示例會員位 | D28：4；D14：0；D7：1 | 測試早訂、售罄及後期少量可用的不同情境 |
| 每人必付費用 | HKD250 | 避免把零基本票價理解為零總價 |
| 託運行李 | 每件 HKD80；數量由人物情境設定 | 比較整組旅客完整付款 |
| 既有會員 | 14 人中的第 3、7 人已入會，剩餘 120 日 | 測試已有會籍時不再次收費 |
| 預算 | 本次旅程、全體同行人可用總額，包含這次新會費 | 驗證先入會後，剩餘預算是否還能付機票 |

這些設定不是實際 HK Express 售價、時刻或會員條款。以沒有行李的單人為例，D28 會員票完整付款為 `70 + 250 = HKD320`，正常票為 `600 + 250 = HKD850`；新會員第一次的合計支出為 `399 + 320 = HKD719`。預算 HKD807 的人可負擔這次入會及買票，但之後只餘 HKD88，亦可能因供應不確定而拒絕入會。拒絕入會後仍可買 HKD750 的次日大阪正常票。

「3 expected trips / term」表示全年預期三次，並不表示系統已安排或售出三次，也不代表上述 HKD807 是整年的旅遊預算。若三次均成功使用同等優惠，理論淨節省是 `3 × (850 − 320) − 399 = HKD1,191`；這個條件算例不能改寫成三次一定能用，也不能無依據稱為「淨節省有限」。

新版Admin以摘要、客群比較和可搜尋分頁名單顯示結果，選中一人後查看完整六階段。Membership欄是入會決定；Booking欄顯示買票及後來取消狀態。拒絕入會後仍可買正常票，沒有矛盾；已付款後取消仍保留最初購票紀錄。舊版長卡片與其保存的result仍可從歷史audit查閱。

**獨立旅程與共享市場的界線：**這一頁每個人物有獨立示例庫存，4／0／1 不是其他畫面人物搶購後的結果，也不是 NHPP 計算的實際放票數。新版共享市場才執行 [D28／D14／D7 三輪配額](THREE_ROUND_RELEASE.md)，以所有旅客共用的航班和歷史有效未售配額計算新增供應。Customer Agent 適合讀取個別行為理由；共享市場適合比較搶票、庫存後果及收益。

## 價格與約束

每個報價列出持卡人基本票價、同行者正常基本票價、每位旅客必付費用與行李。會員資格只覆蓋持卡人，其他同行者沒有自動優惠。零基本票價仍需要支付稅費與適用行李費。同行人數大於剩餘座位時，整個選項不可購買。

人物的預算是整個旅程可用金額。每個狀態滿足：

`剩餘預算 = 初始預算 − 本次會費 − 機票總支出 + 已收到退款`

買票後的 D14／D7 不會再次購買。取消後保留已取消記錄，但不會重複退款。會員期末不扣續費。這些規則由程式執行，LLM 只能提出行動，無法自行修改庫存和財務帳本。

## Prompt 與資料邊界

`llm_agent/prompts/journey_system.txt` 定義旅客身份、合法選項、時間資訊、預算、同行規則、等待風險、取消及續會意向。它要求短理由而非隱藏推理過程。每個 user message 是當下的結構化 context，包含可選與不可選報價，以及不可選原因。

未來報價排程保留在環境中，不提供給 Agent。`v2.1` 移除了人物內提前顯示的未來計劃變動標籤；只有到計劃變動階段才揭露。未入會者的既有會員剩餘期限顯示 null。

原始 Codex pilot 的 v2 訂閱 packets 已經匯出，包含未來變動標籤；當時 Agent 收到「不可使用此未來欄位」的指示。這是原始 pilot 的限制，不能抹去。其 packets 和 hash 保留，後續 packets 使用修正的 v2.1，沒有靜默改寫既有模型輸入。

## 三種執行來源

| source | 實際行為 | 可以聲稱甚麼 |
| --- | --- | --- |
| `deterministic_assumption` | 固定數學／規則決策，沒有呼叫 LLM | 可驗證狀態機與展示假設 |
| `codex_subagent_pilot` | 真正的 Codex 子 Agent 讀 immutable packets 並寫回答 | 子 Agent 在該情境下的生成選擇；不是外部 Provider API 紀錄 |
| `provider_live` | 實際 HTTPS Chat Completions 回應 | 指定模型、prompt、輸入下的實際模型回覆 |

所有來源都不是實際 HK Express 消費者行為。Provider 失敗、截斷或行動非法時不會偷偷改成 deterministic 決策。

## 真實 Provider 執行

伺服器環境變數為 `LLM_API_URL`、`LLM_API_KEY`、`LLM_MODEL`，只存在本地私有設定。模型可配置；本次使用經 `/models` 核對可用的 `deepseek-flash`。只有 `api.deepseek.com` 主機的請求加入 `thinking: {type: "disabled"}`；其他供應商不會收到這個擴充欄位。回應要求 JSON，且 `finish_reason` 必須是 `stop` 才能接受，截斷的有效 JSON 也不採用。

模型是綁定當前實驗的一部分。實驗開始後不能改 prompt、人物或場景語義再把結果合併；改動應建立新版本和新實驗。新版 suite 保存 `prompt_version` 與 `system_prompt_sha256`，續跑、重新輸出 pending packets、匯入回應前會核對版本、雜湊及凍結的 `system_prompt.txt`。舊版或缺少有效證據的 suite 可繼續查閱報告，不能以新版契約接續，亦不會被改寫成新版成果。

```bash
# 建立完整 14 人 × 4 個票價 × 2 個會費 = 112 個獨立世界
python -m llm_agent.experiment create \
  --output data/private/deepseek_factorial_english_v22 --full

# 每次最多 30 次決策呼叫，3 個平行工作；可重複執行以續跑
python -m llm_agent.experiment run \
  --output data/private/deepseek_factorial_english_v22 \
  --max-decisions 30 --workers 3

python -m llm_agent.experiment report \
  --output data/private/deepseek_factorial_english_v22

# 明確要分享合成紀錄時才執行；不匯出認證 headers 或 API key
python -m llm_agent.experiment export \
  --output data/private/deepseek_factorial_english_v22 \
  --destination llm_agent/experiments/deepseek_factorial_english_v22
```

完整 112 世界各最多六個決策，共 672 次決策機會。快取重播不等於新增 Provider 呼叫。每批限制是上限；實際呼叫、完成、快取與失敗數以 audit 記錄為準。CLI 每批最多 168 次，最多五個工作者；UI 另由 API 設較小上限。

每個成功狀態立即保存，程序中斷可續跑。相同 suite 有 OS 排他鎖，避免兩個程序互相覆蓋狀態；共用 audit 寫入有執行緒鎖。失敗世界在本批暫停，不會自動重試直到得到喜歡的答案；下一批可在修復原因後明確重試。

## Codex 子 Agent pilot

```bash
# 14 人，每人兩組方案：P0/V199 與 P100/V599，共 28 個世界
python -m llm_agent.journey export \
  --output data/private/codex_pilot_english_v22

# 子 Agent 只讀 system_prompt.txt 和當前 pending.jsonl。
# 不讀 state.json：其中有環境尚未揭露的未來事件。
# 回答逐列包含 packet_id、context_sha256 以及 decision。
python -m llm_agent.journey import \
  --output data/private/codex_pilot_english_v22 \
  --responses data/private/codex_pilot_english_v22/responses-stage-0.jsonl
```

匯入會驗證 packet ID、原始 context hash、當前狀態及合法動作。批次全部合法才提交狀態；失敗原始輸出仍會保留。`pending.jsonl` 推進到下一階段，歷史 `packets-stage-N.jsonl` 保持可查。舊回應不能再次套用或跨世界混用。

28 世界 pilot 同時改變 P 與 V，不能分離票價和會費的因果效果。112 世界是四個 P 與兩個 V 的 factorial 設計，可以作同一人物的受控比較，但仍不是實際市場彈性。這個小型角色扮演不應拿去擬合實際需求係數或校準收益優化器。

不同人物與反事實世界各自使用情境庫存。合計訂票數不代表他們在同一班實際飛機上競爭座位，也不能直接當成共享庫存清算結果。

## 原始紀錄與匯出

私有記錄在 `data/private/llm_runs/<run_id>/`：

- `metadata.json`：模型、來源、prompt 版本、進度與摘要。
- `events.jsonl`：完整 request body（system/user messages，沒有 headers）、原始 response text/JSON、模型 usage、延遲、快取來源、驗證結果、失敗及狀態變更。
- 面板完整執行另有 `result.json`；大型實驗保存於其 suite 的 `state.json`、`pending.jsonl`、`summary.json`。

在任何驗證前，原始回應都會寫入。HTTP 錯誤內容、非 JSON、非法行動及非正常結束也會保留。紀錄會移除認證欄位，並遮蔽當前環境中的 API key、token 和 secret 值。單次原始回應上限 2 MB，超限保留截斷內容並拒絕決策。

`audit.list_runs()` 和 `audit.read_run(run_id)` 提供安全查閱，run ID 不接受路徑字元。分享匯出包含 `audit.jsonl.gz`、`report.json`、`worlds.json` 及 SHA-256 manifest。`worlds.json` 包含環境設定與完成後狀態，供事後審查；不能反過來提供給尚在決策的 Agent。

## 驗證

`backend/tests/test_llm_journey.py` 覆蓋：六階段預算守恆、會費一次、既有會員、家人正常票價、售罄、最低安排時間、取消退款、不重複買票、未來事件隱藏、packet hash、錯誤批次不改狀態、錯誤輸出保存、Provider 快取來源、認證遮蔽、截斷輸出拒絕、批次續跑及匯出。舊 `runner.run()` 的 legacy 模式仍供相容性測試；產品端應使用 `scenario_mode="journey"`。

`backend/tests/test_journey_versioning.py` 覆蓋新版 prompt 凍結、舊版續跑與匯入拒絕、prompt 雜湊缺失／改變、凍結檔案遭修改時停止 Provider 呼叫，以及歷史報告保留原始版本。

## 英文版本實際驗證（2026-11-14）

新版 `traveller-journey-v2.2-en` 以相同 seed117、前五位人物、P70/V399，實際呼叫 `deepseek-flash` 完成六階段：30份新有效回覆、0快取、0失敗，供應商回報73,625 total tokens。所有接受的理由為英文、金額使用HKD。四名原未入會者均選擇入會，另一名保留既有會員；五人都曾購票，一人後來取消。這是該情境的新回覆，不能推論真實轉換率。

本次除語言外也補充了預算範圍和程式計算的全體同行報價，因此不能把相較舊版的行動差異全部歸因於語言。語言／幣別驗證器檢查非拉丁文字、常見外幣代碼／符號與reason_code；它不是完整自然語言辨識器，也不能證明所有敘述算術或消費偏好正確。英文使用拉丁字母的其他語言仍可能通過字元層檢查，需持續觀察真實回應。

原始輸入、原始輸出、狀態變化、完整畫面結果與SHA-256保存在 [english_journey_20261114](../llm_agent/experiments/english_journey_20261114/)，私有run為 `journey-7aefaac1284f4f99`。既有多語言實驗未翻譯或覆寫。新程式以prompt與context雜湊隔離快取；舊suite不可套用新版prompt續跑，但仍可讀取歷史報告。

驗證涵蓋中日文與JPY拒絕、失敗原文留存、不更新狀態、不存有效快取、快取再驗證、英文標點、同seed數值保持、外部Agent匯入、舊suite續跑拒絕。前端另以14人84階段檢查英文卡片、預算／會員標示、鍵盤操作、歷史原文保留與390px佈局。

## 歷史 v2.1 基線實驗（原 LLM_BASELINE_EXPERIMENTS：Codex與DeepSeek旅程基線實驗）

原文搬移，數字未改；這是舊 prompt v2.1 的證據，不代表現行 v2.2-en。證據目錄：[`codex_pilot_20261114/`](../llm_agent/experiments/codex_pilot_20261114/)、[`deepseek_factorial_20261114/`](../llm_agent/experiments/deepseek_factorial_20261114/)。

2026-11-14。全部人物與行程是假想設定；API回應是真正呼叫得到的模型輸出，並非真人觀測。此批保留獨立單人庫存，新的共用市場另作實驗。

### 實際執行

- Codex子代理：28世界、6階段，共168份親自生成的JSON決策；原始回答、輸入packet及雜湊已保留。使用同一Codex子代理會話分階段處理，不是168名獨立真人或獨立模型樣本。
- DeepSeek：官方/models確認deepseek-flash；使用非thinking模式、temperature=0、JSON輸出和每次600token上限。完整112世界×6階段=672份有效決策，0快取命中。
- 中途1次DNS失敗保存於audit後暫停，從檢查點重新請求該步；沒有填入離線答案。成功回應的provider報告用量為1,515,811tokens（input1,456,225、output59,586），不包含另一次6呼叫連線smoke。
- 輸出公開於llm_agent/experiments/，包含壓縮完整audit、worlds、report和checksum；授權header與金鑰不在資料中。

### DeepSeek完整價費矩陣

|會員基本票價P|年費V|新入會／12名未入會者|已購票世界／14|取消|續會意向|
|---:|---:|---:|---:|---:|---:|
|0|199|7|13|2|6|
|0|599|2|13|2|2|
|30|199|6|13|2|7|
|30|599|2|13|2|2|
|70|199|8|13|2|7|
|70|599|4|13|2|2|
|100|199|7|13|2|8|
|100|599|4|13|2|1|

每組另有2名既有會員，沒有在本次重收會員費。已購票數包括後來取消者；續會只是未扣費意向。每個世界獨立庫存，因此不能把104次買票視為同一航班售出104位。

### 實驗促成的修正

1. Codex試跑發現早期context含future change_scenario，以及未入會者也顯示剩餘120日。v2.1開始移除未來事件資訊，未入會者期限為null；舊packet保持原樣並記錄限制。
2. Codex指出date_uncertain沒有概率／影響人數，以及下期預算沒有定義。共享市場將以明確事件與當期會員期帳本承載後果，未來續會仍只作附條件意向。
3. 單人旅程的後期多為唯一合法行動；共享市場會直接執行並標為environment_forced，避免浪費LLM呼叫或冒充新偏好證據。
4. 各價費組均13/14買到票，無法測出多人競爭；新增共用庫存、多人同時期查詢、多次出行與完整會員期財務帳本。
5. 提高票價後入會人數有時反而增加。相鄰價位有 4 個同人同會費由DECLINE轉JOIN的情境；保存於paired_cost_anomalies.json，會以新呼叫重複／選項順序／語言探測，不將這批回應直接擬合成真實需求彈性。

### 可重播而非真人ground truth

模型理由能指出日期、同行、費用和庫存的考量，但不證明其心理偏好正確。14類角色只是需求情境覆蓋，無真實HK Express客群比例；v2旅程的航班均由HKG出發，入境客情境的真正跨境路線仍需共享市場擴展。只有真實曝光及購買、或同題真人試驗能校準市場反應。

官方接口參考：[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)、[Models](https://api-docs.deepseek.com/api/list-models/)。共享市場請參考後續SHARED_MARKET文件；這份報告不把單人旅程結果當成收益排名。
