# Published evidence and incomplete source packages

Verified 14 November 2026 against `main` at `2426484` before this correction.

The committed README's 29 relative links resolve in the Git tree. Its supporting
documentation, `simulation/README.md`, `simulation/validation_extended/` and
`llm_agent/experiments/` are present in a clean `git archive`; `.gitattributes`
does not exclude them from exports. A missing-files copy was therefore not
reproduced from that commit's full source archive. A separately distributed
partial copy still requires replacement with the full archive.

The new Docker build check did identify one smaller packaging omission:
`agent.md` was excluded while two included technical documents linked to it.
The build allowlist now includes that public handoff document as well.

There was a reproducible validation defect: removing the entire extended-evaluation
directory made the API return HTTP200 with `{"status":"pending"}`, while
`scripts/verify_artifacts.py` passed because its directory glob found zero files.
The evidence had not become a pending job; the source package was incomplete.

## Required checks

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

## Meaning of the result

The 1,200-flight evaluation contains 200 sustained-surge flights. At D28, NHPP v2's
guarded protection covers 183 of those 200, giving 91.5%. This is a synthetic
subgroup result, not an overall real-airline accuracy score. The earlier 240-flight
final cohort and its 82.5% surge coverage remain separate evidence.

`/api/evaluation/extended` returns the existing report when its required evidence
is available. Missing required files or an invalid report/manifest returns HTTP503 with
`status: unavailable` and a relative artifact path. No replacement result or
invented metric is returned. Restore the full source package to resolve that
condition; an API key is not needed. API reads check required-file presence and
report integrity; full publication verification hashes all data payloads.

Source: [extended evaluation](EXTENDED_VALIDATION.md),
[report](../simulation/validation_extended/report.json),
[manifest](../simulation/validation_extended/manifest.json).

## Verification for this correction

- Publication check: 40 Markdown files, 141 relative links, 17 synthetic experiment
  manifests and all 12 extended-evaluation payloads passed. The scored records
  reproduce 1,200 histories, 7,200 predictions and 183/200 D28 surge coverage.
- An isolated Docker image built successfully with the check running during its
  build. No Git directory, provider credentials or private host data were needed.
- The offline container suite passed 175 backend tests and 26 simulator/publication
  tests, including 14 new evidence/publication regressions. Frozen artifact checks
  also passed; no datasets or model calibration were regenerated.
- Real loopback HTTP requests inside the isolated container returned 200 and the
  original report for a complete package, and 503 with `status: unavailable` for
  an intentionally missing evidence directory.
- The publication tests also export a clean Git archive: an untracked local file
  cannot make a committed README link pass; committing that file makes it pass.
