# 額外40萬筆合成資料及擴大驗證

2026-11-14。使用者要求增加測試資料後，保持NHPP v2及其保護校準不變，預先指定20261121和20261122兩個新種子。沒有使用這次結果重新調參。

## 資料規模

- 原有20萬筆展示資料保留；兩批新資料各20萬筆，共新增40萬筆，合計60萬筆。
- 新增2210條航班歷程，與原1105條合計3315條。身份由seed與flight_id共同構成。
- 每批抽前600班評估，共1200班；D28、D14、D7各評一次，v1及v2合計7200次預測評分。
- snapshot、truth、manifest及checksum保存在simulation/validation_extended/seed-{seed}；逐次評分保存forecast_records.jsonl.gz。

## 相同新航班的比較

|時點|v1需求MAE|v2需求MAE|v1突增保護覆蓋|v2突增保護覆蓋|v2突增覆蓋95% Wilson區間|v1平均釋位|v2平均釋位|
|---|---:|---:|---:|---:|---|---:|---:|
|D28|27.63|30.28|89.5%|91.5%|86.8%–94.6%|6.12|6.56|
|D14|18.85|14.97|96.5%|97.0%|93.6%–98.6%|9.62|13.80|
|D7|10.67|8.45|91.5%|91.5%|86.8%–94.6%|18.03|23.63|

兩個版本都使用已凍結的同一套分情境校準程序；表中v1不是原來固定加16位的舊規則。每個時點有200條突增航班。區間只是合成樣本覆蓋比例的描述，不能保證真實市場90%保護。

## 必須一併報告的代價

- 原先240班final中的D28突增覆蓋為82.5%（40班）；擴大樣本為91.5%（200班）。保留兩份證據，不以較好的一份取代另一份。
- D28整體需求MAE仍由27.63惡化至30.28；保守未知跳變假設讓部分正常航班高估。D14／D7整體需求MAE改善。
- D7仍未發生跳變的81班：v2保護覆蓋81.48%，低於重新校準v1的85.19%；未知未來跳變仍是未解缺口。
- 假設所有釋出會員位均售出，D28平均新增正常客擠出量為v1 0.018、v2 0.155位／班；較多放位伴隨風險。
- 額外資料使用相同生成器家族，增加的是同一模擬假設下的樣本量，不能代替真實資料或全新需求機制的驗證。

重現：`python -m simulation.extended_validation`。已存在報告會拒絕覆寫；現有報告、manifest及逐筆評分可以直接檢查。

## 發布完整性檢查（原 EVIDENCE_PUBLICATION）

`python scripts/check_publication.py` checks repository Markdown links and the
mandatory frozen extended-evaluation package. It works without Git in a complete
extracted source archive. `--git-ref HEAD` checks a clean Git export, so an
untracked local file cannot hide a missing publication. Docker builds and the
container test entry point also run the check.

The extended-evaluation manifest pins the report, individual forecast records,
and both input datasets. Verification checks file hashes and independently
reconstructs the reported sample size and D28 surge coverage. A missing directory,
missing referenced document, altered report or incomplete evidence package fails
instead of being silently skipped. Existing frozen data is preserved; this fix
does not regenerate, recalibrate or improve the model.

`/api/evaluation/extended` returns the existing report when its required evidence
is available. Missing required files or an invalid report/manifest returns HTTP503 with
`status: unavailable` and a relative artifact path. No replacement result or
invented metric is returned. Restore the full source package to resolve that
condition; an API key is not needed. API reads check required-file presence and
report integrity; full publication verification hashes all data payloads.
