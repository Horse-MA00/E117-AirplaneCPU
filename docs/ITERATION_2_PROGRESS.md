# NHPP 突增預測與旅客場景第二輪實作

日期：2026-11-14。使用者授權直接修正、重新測試、更新技術文件並推送GitHub；新增完整LLM旅程與Codex subagent實際模擬。

目前狀態：以下里程碑按實作順序保留；最新完成狀態見文件末段。早期「進行中」不代表目前仍未完成。

## 計劃及評估紀律

- 原先47.62%突增覆蓋的測試集已被檢視，現在只作開發診斷；不再稱為新版本未見測試。
- 先保留v1，建立固定失敗回饋與最小案例；分別檢查未知未來衝擊、長窗口滯後、截斷及票價變動。
- 新版本在選定模型後凍結，以新生成seed的獨立校準／最終測試評估；報覆蓋、誤差、保護量及放位代價，不以關閉所有優惠掩蓋失敗。
- LLM由單次角色prompt擴展為有記憶的旅程與可驗證狀態轉移；逐次保存輸入、原始輸出、解析、錯誤、版本及來源。
- Codex subagent執行情境的結果標為codex_subagent_pilot；不冒稱第三方API呼叫或真人購買資料。

## 進度

- 已重現低覆蓋並保存v1基線；模型agent開始分離原因測試。
- 旅程模擬器、prompt、決策packet匯出／匯入與audit實作中。

### NHPP 第二輪完成；共享市場擴充中

- v2 已凍結，以新生成的240班作最終測試。D28突增保護覆蓋82.5%；同一批航班v1原16位保護為30%，v1經同規則重新校準為80%。舊47.62%屬另一批資料，不能直接作同樣本提升。
- D14／D7需求MAE改善，但D28需求MAE變差；D7尚未發生突增的12班子群只有75%覆蓋。完整限制保留於NHPP_V2_REVIEW.md，未看最終結果再調參。
- 定價器已改用v2的保護路徑和未截斷需求曲線，避免再次只使用單一beta丟失情境尾部；4個針對性測試通過。
- Codex子代理28世界正在分階段回傳真實LLM決策，原始回答和輸入雜湊保存。早期發現未來變更標籤洩露，v2.1後移除；原始紀錄不改寫。
- 使用者新增DeepSeek金鑰；私有設定完成，/models確認deepseek-flash可用，6次真實呼叫的完整旅程成功。112世界×6階段基線實驗正在按168次上限分批進行。
- 使用者進一步要求共用市場：新增獨立市場生成器、所有旅客共用庫存／時間／財務帳本、可交換的數學／LLM決策、少量候選真實LLM重播與行為檢查；保留既有單人旅程作基線，另建v3模組與資料。
- 此時既有兩組測試45+19通過，前端JavaScript語法檢查通過；新共享市場完成後會再整體驗證。

### 額外資料及實際模型回應已保存

- NHPP第一個里程碑已commit/push：b131fe5。
- 額外400000筆已生成及驗證，加原資料共600000筆／3315條歷程；新1200班×3時點×2版本=7200次評分。模型和校準完全未改。D28突增200班覆蓋91.5%（v1重新校準89.5%），D7未知跳變81.48%仍有缺口，詳見EXTENDED_VALIDATION.md。
- Codex子代理168份實際生成決策全部完成、校驗並匯出。DeepSeek112世界672份有效決策全部完成，0快取、1次DNS錯誤後續跑。資料在llm_agent/experiments/。
- DeepSeek發現4組相鄰票價提高卻由拒絕轉入會的同人情境；新行為檢查將用真實新呼叫檢驗重複、順序和語言，保留異常而非更改原回答。
- 共享市場引擎、Adapter及實驗管理器由獨立子代理實作；本地背景工作與Web API已加入，呼叫額度逐批上限100，暫停後需明確執行resume，沒有自動無限消費。

### 共用市場、擴大重播及真實LLM驗證完成

- 600000筆資料及Codex168／DeepSeek672份基線已commit/push：689b790。新增60份未快取行為probe，3/12同情境重複組不一致；初次60個DNS失敗嘗試亦保留，沒有當作有效回答。
- 40個種子×3政策共120個數學市場完成。新資料找出替代航班退款截止bug：修正後以同一外生種子完整重播120次，全部帳本／庫存／預算檢查通過。驗證30種子中FIXED勝25次，NO_OFFER勝5次；詳見SHARED_MARKET_MATH_RESULTS.md。
- 真實DeepSeek開發市場3政策完成：265次新有效呼叫、160次明示快取、500次唯一合法行動。正式獨立驗證3種子×3政策完成：1383次新有效呼叫、0快取、0失敗；完整輸入、raw response及action後果公開於llm_agent/experiments/。
- 以相同4個種子再完成12個規則市場，確認外生需求／人物／出行機會hash與LLM世界相同，將行為來源差異與市場差異分開。
- 舊v1中斷的開發記錄另外保留：240份有效新回應，另1個已記錄請求沒有回應，供應商端結果與用量未知；不算正式驗證。新v2中160次快取重播不是新獨立回答。
- 獨立程式審查未發現尚未解決的庫存、費用重收或財務守恒阻塞。實驗版本凍結漏列v2校準檔已修正；舊spec保留原樣，另存SHARED_MARKET_CALIBRATION_ATTESTATION.json，不冒稱原先已逐次記錄該hash。
- 74項backend＋19項既有資料／模擬測試通過，前端與API smoke通過，桌面和390px五個頁面檢查無橫向溢出。原始audit改為有界串流下載，半行追加回歸測試通過。
- 目前沒有再自動開啟付費LLM批次。NHPP／校準／客群假設沒有按驗證成績調整；模型未解的未知突增與日內會員截斷限制保留在技術審查中。

完整結果以SHARED_MARKET_VALIDATION.md、EXTENDED_VALIDATION.md及各實驗manifest為準。可執行`python scripts/verify_artifacts.py`重新檢查資料hash、列數、JSONL及完成市場的帳本檢查；不會呼叫外部服務。

### 三輪放票業務規則更新（2026-11-14）

- 使用者確認D28、D14、D7三輪增量放票：第二輪扣第一輪有效未售配額，第三輪扣前兩輪有效未售配額。NHPP及校準保持凍結，新增政策版本及逐輪配額批次。
- 已建立THREE_ROUND_RELEASE.md，記錄公式、三輪數字例子、FIFO、取消／到期、靜態SQLite示例補帳、非放票日及舊實驗邊界；README、技術架構及共享市場說明同步更新。
- 新`three_round_40seeds`實驗已完成40種子×3政策＝120個規則市場，含1080份航班結果、3240筆逐輪配額紀錄，七項帳本／庫存／預算檢查全部通過。30個驗證種子由NO_OFFER勝18次、FIXED勝12次；FIXED平均增量HK$195.57，CANDIDATE平均增量−HK$1,706.10。無新增LLM呼叫，舊v2結果保留不改；詳細數字見THREE_ROUND_RELEASE.md。
- 本次重新執行91項backend及19項既有資料／模擬測試，共110項全部通過；包含輪次扣除、取消不補發、目標縮小、過期、禁止倒退及併發不重發。獨立審查發現共同停售時間已過後仍可能建立立即過期的下一輪優惠，已修正並加入回歸測試。
- `scripts/smoke_three_round_api.py`實際HTTP測試通過：三輪發布5／3／2位，售出2位，D14結轉4、D7結轉6、最後有效未售8；拒絕D13發布、重複D7及倒退D14。新市場逐輪公式核對通過；D14有121筆、D7有178筆實際結轉案例，共36,987筆動作、0失敗及0外部provider呼叫。
- 整體API smoke重新通過：200000列、1105班、64組候選及HK$280示例購票。測試會跳過已執行輪次的航班，避免將既有QA庫存誤判為服務失敗。前端完整`--transactions`瀏覽器smoke亦通過；新畫面顯示三輪新增／結轉、當前可成交量及歷史實驗標示。
- 文件相對連結及`git diff --check`通過。本次沒有更改NHPP模型或校準，也沒有追加付費LLM實驗。

### Live LLM英文／HKD場景修正（2026-11-14）

- 重現原prompt允許人物語言、reason未檢查語言導致中／英／日混用及港元誤寫円。新版journey為`traveller-journey-v2.2-en`，shared adapter為`shared-market-customer-v3.1-en`；新理由全部要求英文及HKD，英文客群名稱保留原數值與RNG序列。
- 加入明確單趟旅程＋新會費預算、全體同行報價、會費前後節省，前端顯示六階段情境與獨立庫存限制。共享市場放票規則、NHPP、校準和成本沒有修改。
- 輸出合約在provider接受／有效快取寫入／外部Agent匯入前檢查；失敗原文留存、不改成規則決策。新舊prompt快取分開；舊suite不能混用新版續跑，歷史摘要保留原版本。
- 真實DeepSeek五人六階段：30新回覆、0快取、0失敗、73,625 tokens，全部英文HKD；原始audit及結果已匯出`english_journey_20261114`。加入比較資訊會影響決策，不能把新舊差異當作語言因果或真人購買率。
- 完整backend回歸最終105項全部通過（包括新增外部Agent英文匯入檢查）；14人84階段Chromium測試通過，390px無溢出，保留歷史原文。詳見LLM_SCENARIO_DESIGN.md與PROGRESS_FRONTEND.md。


## Continuous pricing implementation — 2026-11-14

The new continuous-price and probabilistic-user path is documented in [CONTINUOUS_PRICING.md](CONTINUOUS_PRICING.md). It uses the existing shared engine, a fixed membership fee/release share, bounded cent-resolution search, paired NO_OFFER, independent validation and sensitivity stresses. Historical fixed-tier and LLM reports remain unchanged. No online human learning or autonomous live repricing is implemented. Windows locks and frozen prompt byte copies are portable; checkout rules preserve frozen NHPP source bytes.
### 大型Panel及Admin／會員網站分離（2026-11-14）

- 新`backend/panel_jobs.py`支援預設100人、live最多100／rules最多1,000人。背景批次、三工作者、逐人checkpoint、部分結果分母、model／prompt／impl凍結及明確續跑；每批live預設60、最多120次有選擇的決策嘗試。唯一合法動作與provider／cache分開，不自動延長付費額度。
- Admin改為摘要、客群比較、搜尋／篩選／20人分頁及單人六階段；移除旅客加入／預訂控制，保留發布優惠與獨立保存的會員plan。會員入口`/members`新增航班搜尋、完整價格拆解、分步入會／預訂、My trips及本機測試身份；兩端共用SQLite已發布配額和帳本。
- 會費從伺服器plan取得，兼容`/api/members`也不再接受任意成交會費。已有會員不重收；過時價格會拒絕，購票仍重查NHPP保護及目前模擬日，最後一位競爭不超賣。客戶端確認成功後即保留receipt，之後讀取失敗不誤報為購買失敗或自動再購買。
- 118項backend測試全部通過。實際HTTP規模測試`panel-a859e0612fd24f0a`完成1,000人／6,000階段，耗時16.1秒，規則決策3,857、環境強制2,143、provider／cache／失敗均0，所有預算守恒；完整摘要與provenance在PANEL_SCALE_VALIDATION.json。另有100人／600階段實際瀏覽器測試。
- Admin完整瀏覽器smoke及發布交易通過；100人摘要、14組圖、分頁／篩選、單人英文詳情、部分結果／續跑、候選會費草稿及599.75小數明確保存已驗證。桌面、390／768px無頁面溢出。會員端已實際完成HKD399入會和HKD280訂票，重載可查；另外涵蓋費用變更、售罄、空資料、帳戶切換、成功後刷新失敗，零新增LLM呼叫。
- 新技術說明ADMIN_AND_MEMBER_UX.md及README／CURRENT_IMPLEMENTATION／LLM_SCENARIO_DESIGN／frontend README同步更新；NHPP、三輪放票規則、既有原始LLM實驗與模型校準未修改。這是本機Hackathon購票原型，沒有真實登入權限／付款／出票。

### 全面介面重設及雙軌逐輪優化（2026-11-14）

- 已由9996fcf快進至GitHub最新ffc997e，保留新機率旅客、連續單維票價搜尋、Windows鎖及原有證據；新增主流程同時搜尋會員費及會員基本票價。
- Admin改用紫／青／白四主入口，Forecast以座位分配、空座預測與票價曲線呈現；移除使用者指定的長篇說明／驗證／每日表。Client全面重設搜尋、價錢排序、入會、訂票及My trips，保留伺服器權威價格與庫存。
- 新SQLite保存run/world/round/event，數學／Live LLM各自逐輪搜尋、配對NO_OFFER與獨立holdout，會費和票價均可調；可設定輪數與每批呼叫上限，完成行動及狀態以同一交易保存。
- NHPP base保持凍結；獨立seat_feedback層用完成的訓練市場正常請求校正均值及額外保護，原空座Monte Carlo保留。修正覆蓋率口徑、價格建議下限、容量截斷與價格草稿語義。
- 149項backend測試、19項原模擬器測試、既有artifact checksum與新匯出source hash全部通過。Admin／Client及新優化器桌面手機瀏覽器測試通過，包含真實SQLite購買、存檔重載及分頁audit。
- 數學6輪14人：18個完整市場，3,131數學選擇＋2,415強制動作；雙軌各3輪2人：16市場，169新DeepSeek回覆、0快取／失敗，200數學選擇＋335強制動作。兩次實驗均保留NO_OFFER，沒有以較差方案冒充最佳會員價。
- 完整報告及原始輸出在joint_math_20261114／joint_live_20261114；資料庫／keys／OAG raw保持private。詳見JOINT_OPTIMIZATION_VALIDATION.md、OPTIMIZATION_ENGINE.md、PORTAL_REDESIGN_AND_OPTIMIZATION.md。

### Client 彈性日期與目的地搜尋（2026-11-14）

- 會員頁新增國家／地區和出發日期起訖，支援「下個月去日本，日期不限」；範圍包含兩端，也可單端或不限日期。保留機場及確切日期進階篩選，搜尋結果可沿用最低總票價排序。
- Next month 依香港日曆計算，跨年／閏年均處理；Temporal 使用原生或本機 bundle 備援，不依賴 CDN。明確提交搜尋，刷新保存條件；已選機場最後一個優惠消失時仍保留條件，顯示零結果，不偷偷放寬範圍。
- 日期倒置及超出四位年份範圍均阻止搜尋並保留上次有效結果；桌面雙欄、390px 手機單欄，英文介面及可見錯誤提示。
- 搜尋測試在 Chrome 157（原生 Temporal）及 Chromium 141（本機 polyfill）通過；原有會員／購票 smoke 通過。涵蓋地區切換、起訖／單端範圍、未知機場、跨時區、刷新移除優惠、清除、無結果和手機版。全部使用隔離 fixtures，沒有新 LLM 呼叫或真實購買。
- 技術與使用說明在 CLIENT_FLEXIBLE_SEARCH.md，frontend README 已同步。搜尋只使用已發布 SQLite 優惠；NHPP、三輪放票、優化器及購票校驗沒有修改。

### Client 航點選單及確切日期修復（2026-11-14）

- 新回歸測試先重現：Flying from／Destination 由已發布優惠產生，導致大部分航點消失；Exact departure date 也只能選優惠已有日期。根因是搜尋選項錯誤依賴可售庫存。
- 新 `members/airports.js` 獨立提供兩端同一份 38 機場搜尋目錄，按國家／地區分組：37 個官方已列出／公布機場（含 HKG 及 HFE），加使用者指定的 CTS。吉隆坡核對為 SZB；HFE 標示已公布啟航日，CTS 標示班表未確認，並在選單下方完整顯示狀態，避免手機截字隱藏資訊。來源及清單見 CLIENT_FLEXIBLE_SEARCH.md。
- 確切日改成原生日期輸入，可選優惠以外的日子；保留原有範圍搜尋，15–21 May 2027 包括兩端。沒有優惠的航點／日期只顯示無結果，不生成假票價或機位。
- 修正新增確切日輸入的驗證與焦點：五位年份、未填完整日期拒絕；填寫新範圍或合法確切日可恢復；若進階欄已收起，驗證會先展開再聚焦錯誤欄。
- 新 route-catalog 回歸於 Chrome 157 及 Chromium 141 通過，包含空／稀疏優惠下目錄完整、海外返回 HKG、未知代碼、自由選日、日期範圍、錯誤修復、刷新、重設及 390px 排版。既有 flexible-search／member-portal smoke 通過，獨立審查未留阻塞問題；全部 fixture 測試，零新增 LLM 呼叫或真實付款。
