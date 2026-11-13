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
