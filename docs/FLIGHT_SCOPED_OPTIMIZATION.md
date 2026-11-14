# Thompson Sampling：指定航班會員票價

> 状态：现行 · 对应代码：`member-thompson-v5-marketing`、`public-member-response-v1`、`weighted-member-panel-v3-motivation`、`adaptive-member-decisions-v4-hypotheses`、`analyst-retry-v1`、`whole-hkd-quotes-v1`、`member-marketing-fare-v1`、`backend/forecast.py`、`backend/pricing_scenarios.py`

更新：2026-11-15。這份規格描述目前唯一的定價方法：**Thompson Sampling**。正常需求預測仍由 NHPP 負責；會員放票沿用 [D28／D14／D7 三輪規則](THREE_ROUND_RELEASE.md)。顧客已入會，票價實驗不再次收會費；結果是合成情境中的基本票款，不是航空公司淨利潤。

## 頁面與實際操作

1. **Forecast seats**：選擇航線、日期／航班及觀測日，查看正常需求保護、NHPP 會員空間、今天可新增配額及已發布可訂座位。需求篩選以固定 D28 預測正常訂位率分類：Low <60%、Medium 60%–<85%、High ≥85%。類別不是釋位保證。
2. **Optimize prices**（`/adaptive-pricing`）：選擇航班及 D28／D14／D7。P₀ 自動取正常基本票價的 80% 上限。設定輪數、每輪新顧客人數、八類客群權重及驗證批數。離線合成顧客和 Live LLM 都使用同一 Thompson 選價器；差別只在顧客如何決定購買。
3. **Experiments**（`/admin#customers`）：只讀查看已保存 v5 實驗、每輪摘要及個別購買理由。顯示原始來源，瀏覽不增加 LLM 呼叫。
4. **Manage offers**：人工輸入所選航班／放票日的票價與新增座位，發布時重新核對價格上限、正常需求保護、已售位和前輪未售配額。Thompson 不自動發布、不自動改會員費，也不把實驗庫存當成會員網站庫存。
5. **Client**（`/members`）：搜尋已發布優惠、模擬入會與購票。大字為基本票價，小字另列必付費用及完整付款。

舊 Math／Math+LLM、共用市場、六階段 panel、連續定價與相應資料已移除；不再提供相容工作流程。程式庫目前只保留最新 Thompson 的定價程式與實驗資料，以及仍支援現行預測的 NHPP 證據。舊內容仍可由 Git 歷史追查。舊 `#optimization`／`#pricing`／`#panel`／`#market` 連結顯示頁面已不可用，不重導到其他資料；Optimize 只使用 `/adaptive-pricing`。已刪除實驗ID返回不可用，不替換為另一份結果。

## 初始價格、範圍和宣傳價

選定時點只讀當時可見的正常基本票價；售罄時使用最近更早的有效報價，缺值不是零元。新報價使用整數港元：

```text
normal_quote = floor(latest observable normal_base_fare)
cap = floor(0.8 × normal_quote)
P₀ = cap
```

搜尋在 `0..cap` 之間進行。先選出原始候選，再在獨立驗證前轉成宣傳價：

```text
ending9 = 10 × floor((floor(raw_price) + 1) / 10) - 1
final_member_fare = 0 if ending9 < 30 else ending9
```

| 原始會員價 | 最終基本票價 |
|---:|---:|
| 0–29 | 0 |
| 30–38 | 0（向下取整後為29） |
| 39 | 39 |
| 103 | 99 |
| 255 | 249 |
| 259 | 259 |

格式化不會加價，保留80%上限；HK$0只代表基本票價，沒有虛構宣傳收益。候選與初始備選都先格式化，再按實際報價驗證，不能把原價收益套在新價上。

### Explicit low-fare demonstration inputs

`zero-fare-stress-v1` is an optional, named pricing scenario, not a change to the Thompson model or the default eight customer groups. It tests whether learning can select a raw fare below HK$30 before the existing marketing conversion. It does not prescribe an answer or replace a failed customer response.

| CLI `--demo-scenario` | Required source snapshot | Assumed normal base fare | P₀ / cap | Private ticket-budget multiplier |
|---|---|---:|---:|---:|
| `low_fare_55` | `SYN-00017`, D7 | 55 | 44 | 0.10 |
| `low_fare_60` | `DEMO-HKG-OKA-20270515`, D14 | 60 | 48 | 0.10 |
| `low_fare_65` | `DEMO-HKG-NGO-20270515`, D7 | 65 | 52 | 0.10 |

These are deliberately constructed low-fare / low-disposable-budget demonstrations, not observed airline prices or estimated HK Express customer distributions. All three caps remain above HK$30. The original flight scope and history hash are saved; its inventory and NHPP quota stay fixed as experimental supply. The predictor is **not** recomputed under the assumed lower normal fare. The altered private budgets remain inside the customer environment and never enter the public-feature learner.

Reports, exports and the UI retain the scenario definition, source scope and input assumptions. Ordinary flight selection and publishing suggestions exclude these experiments; an explicit saved-run selection can display them. A candidate such as `HK$20 → HK$0` demonstrates the marketing rule even if confirmation returns `NO_OFFER`. A zero promotional candidate is not relabelled as a zero retained fare or proven revenue improvement. Default experiments, frozen data, prompts and previous reports remain unchanged.

Reproduce the first offline case with the ordinary runner:

```bash
python scripts/run_adaptive_pricing.py --mode synthetic --name DEMO_ZERO_PILOT0 --demo-scenario low_fare_55 --flight-id SYN-00017 --day 7 --rounds 20 --customers 32 --validation-repeats 3 --seed 26111501 --max-calls 0
```

The other cases use seeds `26111502` and `26111503` with their mapped snapshots. A currently authorized live replay uses `--mode live --max-calls 1800`; its complete preflight upper bound is 1,628 calls. A completed nonzero candidate or unsuccessful revenue comparison is retained as evidence, not retried to obtain a desired price.

## Adaptive member-only pricing

目前實驗版本為 `member-thompson-v5-marketing`。每位模擬顧客最多購買一張自己的機票；每輪使用新客群。配額由選定時點的 NHPP 及庫存規則導出，在一次價格搜尋和確認中保持固定。這不是把三輪放票重新當成可調價格策略。

### Target population and private motivation

New UI experiments fix the population to `flexible_deal_seekers`, with eight editable assumed shares: university students 24%, destination-agnostic deal hunters 20%, spontaneous solo travellers 16%, frequent bargain travellers 12%, flexible weekdays 10%, friends 8%, couples 6%, occasional deal-triggered travellers 4%. These are product-audience assumptions, not measured HK Express demographic shares. The current application accepts this eight-group population only. Previous population models and their experiment data have been removed from the working tree.

Each positive stratum gets one panel slot; remaining slots use largest-remainder allocation. A person's estimation weight is target share / stratum count. The target profile has broad date/destination flexibility and no mandatory fixed-date, urgent or business journey. Each member pays for one personal seat; companions have separate tickets outside this experiment.

Before any candidate price exists, the generator draws private hard budget, travel interest (low/medium/high), recent travel, destination appeal and strength of the stay-home/save alternative. A traveller can afford a fare but prefer not to make this optional trip. There is no imposed refusal quota or generated numeric willingness-to-pay target. The [customer v4 prompt](../llm_agent/prompts/adaptive_customer_v4_en.txt) uses English and the computed legal action/fallback lists. An invalid output stops dispatch and is audited; it is not silently repaired or replaced.

### Public-feature learning boundary

`backend/member_response.py` implements `public-member-response-v1`. The `learner_view` allows exactly customer ID, segment, declared flexibility and sampling weight. It excludes exact budget, private motivation, eligibility truth, outside-option text, future actions and LLM reasons. Public segment/flexibility are assumed observable in this prototype; real deployment would need a valid source for them.

```
q_i(p) = sigmoid(a + segment_intercept[g]
                 + c * log(1 + declared_flexibility_days) / log(29)
                 - softplus(b) * p / normal_base_fare)
```

This response averages over unobserved affordability and motivation. All exposed BUY_MEMBER/not-BUY_MEMBER outcomes enter learning, including an environment-forced affordability decline. The environment still enforces the private budget when executing the decision. Inventory denials are separate from purchase intentions; every search quote has positive initial member inventory. Private constraints never become probability masks or candidate boundaries inside the learner.

A proper Gaussian prior and local Laplace approximation represent parameter uncertainty. Repeated paired decisions from one person share at most one unit of likelihood power, preserving relative poststratification weights. Duplicate person/price/normal-price rows are deduplicated and conflicting duplicates rejected. Fitting a non-search phase is rejected. These are synthetic choices and an approximate posterior, not calibrated human demand.

### Fresh paired search and Thompson Sampling

For each of R rounds, the system proposes a price **before generating that round's people**, then draws M new stratified members with seed `seed + 1009*round`. Each person sees the candidate and initial price in separate reset worlds. The other price and earlier answers are absent from their observation. Both worlds share the same persona, latent synthetic choice draw and integer inventory-clearing priority. Quote evaluation order alternates by round. If both prices are identical, the single world is reused and contributes one observation per person. Repeating a price in a later round still generates new people and new evidence.

Proposals are evaluated on an independent 128-person **public-only support**, generated with seed `seed + 20000003`. The support distribution stays fixed during search; `target_customers=M` separately controls forecast market size. It contains no budgets. Round 1 uses `P0=floor(0.8*normal_quote)`. Ordinary later rounds use one joint Thompson parameter draw shared across every whole-HKD price `0..cap`. The numerical grid does not trigger LLM calls at every price. Parameter draws and public features are vectorized in bounded chunks.

For each draw, `q_bar=sum(weight_i*q_i)` and `K~Binomial(M,q_bar)`. The objective uses exact `p * E[min(Q,K)]` under that assumed count model, where Q is frozen NHPP member quota; it does not use `min(Q,E[K])`. Actual accepted transactions always use integer seats and whole-HKD fares. Weighted estimates never create physical seats.

### Feedback becomes a bounded experiment

The [analyst v2 prompt](../llm_agent/prompts/adaptive_analyst_v2_en.txt) returns a summary, reason counts, hypothesis, cited customer IDs and `suggested_direction` (lower/higher/hold/insufficient_evidence). Lower-price hypotheses require a cited refusal and reported price objection; higher-price hypotheses require a cited member purchase. It is never asked to invent a willingness-to-pay value or overwrite the purchase label.

Every third round reserves a hypothesis test slot. A valid previous-round direction restricts the **same Thompson-drawn curve** to integer candidates on that side of the previous price, within 25% of the fare cap. The model selects the highest predicted receipts within that bounded set. At a boundary or without evidence, ordinary Thompson search continues. This 1-in-3 allocation and 25% width are explicit design choices, not empirically optimal constants.

The proposed candidate is compared with the initial quote on that round's new people. `supported`/`not_supported`/`inconclusive` describes this provisional paired revenue comparison; it is not a causal comparison with the previous round's different people and not final adoption evidence. Reasons remain hypotheses, not extra observations. Every round gets its own analysis, even if the price repeats.

### Final choice, confirmation and accounting

The raw selected candidate comes only from tested prices; `recommendation.raw_price` preserves it. `recommendation.price` is its promotional quote after the rule above, which need not have appeared in search. Among those with at least the configured fraction (default 95%) of the best posterior mean **member receipts**, choose the one with most predicted member purchasers. The report separately exposes the revenue-maximizing and buyer-maximizing tested candidates. The dense full-domain chart is a model estimate, not a list of live-tested fares. The 95% model preference is not a guarantee of actual retained revenue.

Freeze the formatted selected candidate and the formatted initial fallback, then draw H>=3 fresh cohorts using `seed+500003+1009*j`. Formatted initial (e.g. raw P₀328 →319), formatted selected (e.g.255→249) and NO_OFFER are replayed on the same people within each confirmation cohort. The validation compares these actual formatted prices; it does not report raw-P₀ receipts as if collected at319. Search cohorts and their original P₀ controls remain unchanged. `validation.comparison_reference = formatted_initial_fare` and the before/after metadata make this distinction explicit. No holdout decision enters learning or chooses a replacement candidate. When no rationing occurs, comparisons use poststratified target-mix receipts. With capacity binding, or when reweighted expected ticket counts would exceed available inventory, use the actual feasible panel ledger consistently.

`adoption_result` is distinct from the model's selection:

- `ADOPT_CANDIDATE`: positive descriptive paired bootstrap lower bounds against both initial and NO_OFFER, with no negative cohort delta for either comparison.
- `KEEP_INITIAL`: the tested candidate equals initial or has lower average receipts.
- `INCONCLUSIVE`: insufficient confirmation to change the reference price.
- `NO_OFFER`: both initial and selected mean receipts fail to exceed the no-offer control.

Three cohorts and bootstrap intervals are a conservative **prototype rule**, not a statistically certified airline guarantee. No result automatically publishes an offer. The UI shows `retained_price` (a formatted quote or null), observed purchase rate and the member conversion required to match initial receipts. The break-even diagnostic subtracts selected regular-ticket receipts before dividing by candidate fare and cohort size; at zero fare it is null unless initial receipts are already matched, and feasibility is bounded by member quota as well as 100% of the cohort. It does not forecast how regular sales would change at that conversion rate.

### Audit, costs of experiments and optional human pilot

Fresh calls, cache hits, forced actions and failed attempts have separate counters. Both configured key slots share one finite limit, with at most eight parallel customer calls (default four). A **customer-decision** failure still stops further dispatches; in-flight calls may finish. Missing or invalid purchase decisions never become synthetic purchases.

The separate `analyst-retry-v1` policy permits **three analyst attempts per round: the initial request plus at most two retries**. Each dispatched retry consumes the same explicit budget. Validation repairs receive the concrete rejection and untrusted prior output, with the same recorded feedback; no customer cohort is replayed. Temporary transport failures can retry; permanent provider errors or exhausted budget may end attempts early. Audit-storage failures and unexpected implementation errors remain fatal.

After unsuccessful attempts, the round stores `analysis=null`, `analysis_status="unavailable"`, `analysis_source="analysis_unavailable"`, a concrete `analysis_error` and `analysis_attempts` metadata. The purchase outcomes, model updates and round are still saved. The next hypothesis slot falls back to ordinary Thompson Sampling instead of reusing an older direction. Independent confirmation still runs. This is not an invented analyst response, a failed purchase observation, or a claim that the LLM supported the price. A recovered response has status `available` and keeps the preceding failed attempts.

`analyst_retries` counts additional dispatched attempts; `analyst_unavailable` counts rounds lacking valid analysis. `failures` includes each failed attempt even if the round later recovers. `analysis_unavailable_rounds` names affected rounds. Historical reports keep their original provenance and outcomes, including old failures; this change does not resume them automatically.

Requests, raw responses, validation reasons, round/attempt identifiers, context hashes and accounting remain in ignored private SQLite and are redacted on export. Optimize and Member feedback show diagnostic summaries; opening a round's response disclosure reads the original audit through `GET /api/adaptive-pricing/runs/{id}/analysis-attempts?round=N`. Without `round`, the endpoint supplies metadata only. Transport errors with no response are labelled accordingly; rejected text is never displayed as a valid analysis. Viewing diagnostics makes no provider calls.

A complete live run now needs an explicit budget covering `R*(2*M+3) + 3*H*M` calls, including all allowed analyst retries. For R=10, M=16, H=3 this is **494 calls**; the default cap remains 600. The estimate deliberately overcounts identical-price reuse and forced choices. Minimum M covers every positive-weight segment. The final validation is read only once after selection. Same-price cache reuse is not new evidence, while a new person's answer is.

`synthetic` mode uses a declared random-utility oracle with private motivation coefficients in `adaptive_customers.synthetic_probability`; it is independent of the public response learner and is not human calibration. `scripts/benchmark_paired_pricing.py` runs prespecified offline comparisons on the current engine and never calls a provider.

`scripts/member_choice_calibration.py` prepares a private, blank human-response pilot and validates supplied answers. Participants receive one randomly assigned whole-HKD quote; their own voluntary travel preferences matter, rather than a dictated synthetic wallet. Exports include contextual hashes and anonymous IDs. Responses must be explicitly labelled `human_self_report`, whose authenticity is unverified. Summaries are descriptive, retain no respondent free text, and never feed the learner or final holdout automatically. A generated questionnaire is not collected human evidence.

```
python -m backend.server --port 8001
python scripts/run_adaptive_pricing.py --mode synthetic --rounds 6 --customers 16 --validation-repeats 3 --max-calls 0
python scripts/run_adaptive_pricing.py --mode live --rounds 6 --customers 16 --validation-repeats 3 --concurrency 4 --max-calls 342
python scripts/run_adaptive_pricing.py --export-run-id RUN_ID --output llm_agent/experiments/NEW_DIRECTORY
python scripts/benchmark_paired_pricing.py --output llm_agent/experiments/NEW_BENCHMARK
python scripts/member_choice_calibration.py --help
```

CLI accepts an optional `--name DEMO_LLM0`; POST `/api/adaptive-pricing/runs` accepts the same `name`. Names are 1–64 ASCII letters, digits, spaces, underscores, dots or hyphens, starting with a letter or digit. They are stored as `config.name` and shown in the saved-experiment selectors on Optimize and Member feedback. The unique `adaptive-…` run ID remains the audit identity; retries may share a display name but never overwrite an earlier attempt. A completed `NO_OFFER`, `INCONCLUSIVE` or `KEEP_INITIAL` is a valid result, not an execution failure to retry.

GET `/api/adaptive-pricing/status`, GET/POST `/api/adaptive-pricing/runs`, POST `/api/adaptive-pricing/scope`, and GET run `/events` or `/export` remain. Run state preserves profile, each search cohort, public training rows, separate prediction support, paired controls and final confirmation. Only current v5 experiments with the supported eight-group population are served; retained reports keep the prices and provenance recorded when they ran.

## 保存資料與目前證據

`backend/adaptive_store.py` 以 SQLite 保存 run、round、event；資料庫位於忽略的 `data/private/`。環境控制合法動作、整數座位與預算，LLM 原始請求／回應及驗證結果可追查。對外匯出會移除密鑰，使用 report、壓縮 audit 和檔案 manifest。

HTTP整份匯出仍保留32MiB上限。大型實驗可用CLI `--export-run-id RUN_ID --output NEW_DIRECTORY`：每頁讀取100筆既有審計，逐頁脫敏並串流壓縮，不會呼叫LLM。完整report、audit和manifest先寫臨時目錄，成功才改名；失敗清理臨時輸出，既有證據目錄不覆蓋。壓力情境的manifest亦保存scenario，方便辨別假設輸入。

目前可公開實驗索引在 [Thompson v5 證據](../llm_agent/experiments/README.md)。保留符合 v5／八類客群的成功、保留初始價及無定論結果；不可只挑收益上升的實驗。既有報告使用當時記錄的來源雜湊，介面整理不重寫其原始結果，也不把舊模型的 Live 成績套到現行版本。

公開集合現含24份保存結果：23完成及1失敗。服務啟動以`backend/published_experiments.py`讀取公開report／manifest，Saved experiments自動合併私有SQLite與公開目錄，同ID以私有為先；全新部署不需要API密鑰或匯入資料庫。公開文件只讀，審計按頁讀取，Analyst原始回覆按輪查詢；失敗結果保持失敗，沒有自動續跑或發布。檔案雜湊、版本、客群或終態不符合時回報錯誤，不以空白列表掩蓋。

CLI新增`--include-failed`，只允許明確匯出failed／interrupted終態，manifest標記`evidence_kind=execution_failure`；未完成輪次及缺少確認如實保留，不捏造holdout。完成報告允許「Analyst首次失敗、重試成功」的非零failures，但發布驗證會從audit重算calls、responses、failures等計數，再與report／manifest逐項比對。預設匯出仍要求completed；running／queued不能發布為保存證據。

NHPP 模型、生成資料、獨立驗證及失敗候選證據見 [NHPP v3](NHPP_V3_REVIEW.md)、[NHPP v2](NHPP_V2_REVIEW.md) 和 [擴大驗證](EXTENDED_VALIDATION.md)。它們驗證正常需求預測及保護，不直接證明 Thompson 的價格收益。

## 驗證方式

```sh
python scripts/check_container.py
# 另開終端啟動 python -m backend.server 後：
cd frontend
APP_URL=http://127.0.0.1:8000 npm run test:adaptive-pricing
APP_URL=http://127.0.0.1:8000 npm run test:optimization
APP_URL=http://127.0.0.1:8000 npm run test:flight-offers
```

瀏覽器檢查使用離線或 mocked 顧客；只有明確授權並設置有限 `--max-calls` 才進行真實 LLM 實驗。發布檢查驗證相對連結、NHPP 凍結證據與目前實驗 manifest；實際執行結果記於 [維護紀錄](ITERATION_2_PROGRESS.md)。
