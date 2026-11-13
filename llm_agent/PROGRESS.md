# 旅客 Agent 實作進度

2026-11-14：新增六階段旅客狀態機、詳細 prompt、不可變 packet 匯出與 Codex 回覆匯入、Provider 原始輸入輸出 audit、快取來源、失敗保留、批次續跑和分享匯出。程式層由單元測試驗證，真實 Provider／Codex 實驗由 root 協調執行。

- 20 項 LLM 相關測試通過（包含九項既有相容性測試）。
- deterministic 14 人完整跑完 84 個階段，7 位新入會、2 位既有會員、13 位購票、2 位取消。這是規則輸出，不是 LLM 實驗結果。
- Codex pilot：28 世界已建立，原始 packets 已送真正子 Agent；完成數以該 suite 狀態為準。
- 原始 v2 subscription packet 有未來計劃變動標籤與非會員剩餘期限歧義；Agent 被明示不得提前使用，v2.1 後續 packets 已移除。舊 packets 未改寫。
- DeepSeek 真實 smoke：root 已確認 `deepseek-flash` 的一位旅客六階段全部成功，run ID `journey-17112f5a1da74a53`。
- 完整 factorial：root 已啟動 `journey-ee4cb77279c3`，112 世界、最多 672 個實際決策機會；不在此把預計數聲稱為完成數。執行中的 prompt/context 語義凍結。
- 已實作 DeepSeek 主機專用 thinking disabled、JSON 回應、`finish_reason=stop`、每批明確呼叫預算和每 suite OS 鎖。
- 沒有把真實 API key 寫入程式、人物或分享檔案；raw audit 保留輸入／輸出但排除認證資訊。

2026-11-14 共享市場更新：

- 已完成舊版 factorial 112 世界的 672 個真實有效 DeepSeek 決策，0 快取、一次 DNS 失敗後續跑；公開完整 audit 在 `experiments/deepseek_factorial_20261114/`。舊版實驗仍是獨立庫存，不能當共享市場驗證。
- 新增 shared-market v3 英中 prompt、相同 observation 的 deterministic/live adapter、強制動作跳過模型、嚴格合法 action/option 驗證、完整原始紀錄及明確無 fallback。
- 新增 `market_experiment`：事前固定政策與 seed、程式 hash 凍結、呼叫預算、OS lock、checkpoint、完整串流匯出、實際 normal→member 切換配對及背景拒絕差額、通過會計檢查才排名。
- 新增 `inspect_cases` 供 UI 讀取當前共享庫存、金額帳目、旅客預算及事件來源；未完成 case 也可檢視。
- 七項新 adapter/實驗測試通過；既有 20 項 LLM 測試再次通過。包含強制動作零呼叫、失敗原始回覆保留、截斷拒絕、快取來源、完整同行人數價格、續跑、會計一致性及三次失敗後停止 probe 呼叫。
- 真實 v3 behavioral probe 完成 60 次未使用快取的有效 DeepSeek 回覆，106,676 tokens。初次 sandbox DNS 的 60 次失敗嘗試保留，成功與失敗分開計數。三組重複輸入不一致，0 組順序翻轉、0 組語言翻轉、0 條向上加價卻由拒絕轉加入的價格序列；不能把這些診斷當成真實市場校準。
- 公開 probe 完整輸入／輸出及報告：`experiments/behavior_probes_20261114/`。未來 probe 系統性失敗會在最多三個並行嘗試後停止，不會向故障網路持續送完全部批次。
- Audit 秘密遮蔽優化為每次頂層呼叫只掃描一次環境設定，保持遞迴資料與原始 Provider 文字遮蔽；既有秘密遮蔽測試通過。
- 共享市場 40-seed deterministic 與真實開發 seed 實驗由 root 啟動；三個驗證 seed 事先固定，實際完成數待各 report 記錄。

2026-11-14 獨立共享市場驗證完成：

- 引擎 v2 修復替代航班較早起飛時的取消截止處理後，才建立三個獨立驗證 seed：20261311／20261312／20261313。舊 v1 市場結果保留並排除。
- 九個 live 政策世界全數完成，1,383 次全新 DeepSeek 回覆、零快取／失敗，另有 1,390 個環境強制動作；合計 2,773 次轉移、4,031,030 tokens。未超過合計 1,800 次外部嘗試預算，沒有追加新實驗。
- 公開完整 audit、spec、report 和 manifest：`experiments/shared_validation_20261311/`、`shared_validation_20261312/`、`shared_validation_20261313/`。
- 三個驗證 seed 均由 NO_OFFER 的 contribution 最高；FIXED 平均增量 −HKD1,172，CANDIDATE 平均增量 −HKD2,626.33。若只移除假設的 HKD1,500 計劃開支、保留全部已發生選擇，兩者分別變成 +328 及 −1,126.33；這是帳目敏感度，不是新增價格實驗。
- 候選政策 24 位新會員中，14 位至少完成一次會員票旅程；17 個完成會員旅次中，有 16 個與基準正常票旅次配對。所有九個世界的會計、庫存、容量、預算及單次會員收費檢查通過。
- 加上獨立列示的開發 seed，共 12 個 live 與 deterministic 配對世界的外部資料 SHA256 完全一致。規則在兩個 holdout 偏向 FIXED，LLM 三個均偏向 NO_OFFER；差異不能證明哪個更接近真實客戶。
- 詳細中文分析：`docs/SHARED_MARKET_VALIDATION.md`。機器可讀彙總：`experiments/shared_validation_summary.json`。
- 發現凍結設定漏記實際 `calibration_v2.json`。已由引擎 agent 提供事後 byte 比對及 frozen NHPP hash 證據，原始 specs 沒有回寫；不能宣稱補齊了當時逐呼叫快照。說明見 `docs/SHARED_MARKET_CALIBRATION_ATTESTATION.json`。
