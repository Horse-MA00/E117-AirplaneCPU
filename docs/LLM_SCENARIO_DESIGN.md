# LLM 旅客情境與原始決策紀錄

2026-11-14。此版本把原先簡短的「入會／買票」面板擴展為六階段、可重播的旅客旅程，保存每一次實際模型輸入、原始輸出、驗證及狀態變動。DeepSeek `deepseek-flash` 已完成一位旅客六階段的真實 API smoke test；完整 112 世界實驗另有逐步進度紀錄，未完成前不能把預計呼叫數當成完成數。

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

模型是綁定當前實驗的一部分。實驗開始後不能改 prompt、人物或場景語義再把結果合併；改動應建立新版本和新實驗。

```bash
# 建立完整 14 人 × 4 個票價 × 2 個會費 = 112 個獨立世界
python -m llm_agent.experiment create \
  --output data/private/deepseek_factorial_20261114 --full

# 每次最多 30 次決策呼叫，3 個平行工作；可重複執行以續跑
python -m llm_agent.experiment run \
  --output data/private/deepseek_factorial_20261114 \
  --max-decisions 30 --workers 3

python -m llm_agent.experiment report \
  --output data/private/deepseek_factorial_20261114

# 明確要分享合成紀錄時才執行；不匯出認證 headers 或 API key
python -m llm_agent.experiment export \
  --output data/private/deepseek_factorial_20261114 \
  --destination llm_agent/experiments/deepseek_factorial_20261114
```

完整 112 世界各最多六個決策，共 672 次決策機會。快取重播不等於新增 Provider 呼叫。每批限制是上限；實際呼叫、完成、快取與失敗數以 audit 記錄為準。CLI 每批最多 168 次，最多五個工作者；UI 另由 API 設較小上限。

每個成功狀態立即保存，程序中斷可續跑。相同 suite 有 OS 排他鎖，避免兩個程序互相覆蓋狀態；共用 audit 寫入有執行緒鎖。失敗世界在本批暫停，不會自動重試直到得到喜歡的答案；下一批可在修復原因後明確重試。

## Codex 子 Agent pilot

```bash
# 14 人，每人兩組方案：P0/V199 與 P100/V599，共 28 個世界
python -m llm_agent.journey export \
  --output data/private/codex_pilot_20261114

# 子 Agent 只讀 system_prompt.txt 和當前 pending.jsonl。
# 不讀 state.json：其中有環境尚未揭露的未來事件。
# 回答逐列包含 packet_id、context_sha256 以及 decision。
python -m llm_agent.journey import \
  --output data/private/codex_pilot_20261114 \
  --responses data/private/codex_pilot_20261114/responses-stage-0.jsonl
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
