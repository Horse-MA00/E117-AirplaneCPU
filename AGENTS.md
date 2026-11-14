# AGENTS.md — E117 UOption Fly Pass 团队 AI 协作规则

Codex 直接读取本文件，Claude Code 通过 `CLAUDE.md` 中的 `@AGENTS.md` 导入本文件。只维护这一份。

## 项目定位

UOption Fly Pass（Cathay Hackathon 2026，Team Airplane CPU · E117）的做法：用 NHPP 预测正常需求，在 D28/D14/D7 分三轮释放会员座位，再在指定航班上比较会员票价和会费。
项目是**合成数据**上的决策原型，不是生产收益管理系统。所有购票都是模拟的。

## 当前主流程以这两份为准

- [docs/FLIGHT_SCOPED_OPTIMIZATION.md](docs/FLIGHT_SCOPED_OPTIMIZATION.md)：Admin 流程、指定航班优化（`flight-policy-feedback-v4-original-fare`，P₀ = 当时正常基本票价）、需求筛选、座位口径、会计公式。
- [docs/THREE_ROUND_RELEASE.md](docs/THREE_ROUND_RELEASE.md)：D28/D14/D7 放票规则；新一轮要扣除前几轮仍有效的未售配额。
- 其他文档与这两份冲突时，以这两份为准。修正经过和证据见 [MEMBER_SUPPLY_CORRECTIONS](docs/MEMBER_SUPPLY_CORRECTIONS_2026-11-14.md)（v3）和 [DEMAND_FILTER_AND_ORIGINAL_FARE](docs/DEMAND_FILTER_AND_ORIGINAL_FARE.md)（v4），只作背景参考；行为变更要同步写进 FLIGHT_SCOPED。

## 已过时，不要照着做

- `docs/PROJECT_PLAN.md`、`docs/TECHNICAL_DESIGN.md`、`docs/PRICING_SIMULATION_PLAN.md`：早期提案，含 LightGBM。现在只用 NHPP，**不加 LightGBM**。
- `docs/OPTIMIZATION_ENGINE.md`：v1 全期联合引擎，只供旧实验参考。
- `docs/CONTINUOUS_PRICING.md`：全期连续定价，属于参考工具，不是主流程。
- `docs/SHARED_MARKET_VALIDATION.md`、`docs/SHARED_MARKET_MATH_RESULTS.md`：shared-market-v2 的历史证据，不能用来验证 v3 三轮规则。
- `docs/LLM_BASELINE_EXPERIMENTS.md`：旧 prompt v2.1 的基线实验。
- `docs/IMPLEMENTATION_PROGRESS.md`、`docs/PROGRESS_*.md`、`docs/SIMULATOR.md`：早期进度记录。
- `src/`、`configs/`：早期独立模拟器和图表导出工具，不属于当前 app。
- `agent.md`：旧交接文档，只作背景。规则以本文件为准；最新进度看 `git log` 和 `docs/ITERATION_2_PROGRESS.md`。

## 不能动的东西

- **NHPP v2 已冻结**：不要改 `backend/nhpp.py`，`backend/evidence.py` 会校验它的 SHA；也不要改 `simulation/generated/calibration*.json`、`nhpp_v2_*.json`。
- 不要运行 `python -m simulation.evaluate_nhpp_v2 calibration` 重新调参，也不要拿 final holdout 反复调参。要改模型，就新开版本，并使用新的验证种子。
- 已提交的数据和 manifest 不要改：`simulation/generated/`、`simulation/validation_extended/`、`simulation/network_generated/`、`simulation/member_demo_generated/`、`simulation/continuous_price_validation/`。
- **历史实验报告保持原样**：`llm_agent/experiments/` 里已有的目录、`docs/validation/`、`docs/*ATTESTATION*.json`。新实验写到新目录；不要回填或"修复"旧报告。
- `llm_agent/prompts/` 下已有的 prompt 被实验哈希引用。要改就新建版本文件。
- `simulation/demand_catalog.json` 不要手改：数据或模型变化后用 `python scripts/build_demand_catalog.py` 重建，再重启服务。
- **`.env.local` 不能读出、打印或提交**，里面是 DeepSeek/OAG 密钥。`data/private/` 是被 Git 忽略的私有缓存和 SQLite，也不要提交。
- 不要改 `.gitattributes` 的换行规则，改了冻结文件的字节哈希会对不上。
- 不要发布 OAG 原始响应或任何密钥。真实 LLM 调用必须有用户授权，并设置明确的 `--max-calls` 上限。

## 测试（不启动 Docker）

准备环境：Python 3.11+，执行 `python -m pip install -r requirements.txt`，只需要 numpy 和 matplotlib。

```bash
python scripts/check_container.py                 # 一次跑完下面四项，与 Docker 测试相同
python -m unittest discover -s tests              # 发布/模拟数据测试，约 1 秒
python -m unittest discover -s backend/tests      # 后端 200+ 项，约 40 秒
python scripts/check_publication.py               # 所有 .md 相对链接 + 冻结证据
python scripts/verify_artifacts.py                # 实验与数据的 SHA256 校验
```

- 需要先启动服务（`python -m backend.server`，端口 8000）的检查：`python scripts/smoke_*.py`，以及在 `frontend/` 下运行 `npm ci` 后的 `npm run test:*`（Playwright）。
- smoke 脚本加 `--live` 会发起真实 provider 调用，未经授权不要用。
- Windows 原生环境缺少 `fcntl`，请改用 `docker compose --profile test run --rm --build tests`。
- 改了模型、会计、HTTP 或 UI 行为，提交前至少跑一遍 `check_container.py`。

## 目录与模块

- `backend/`：stdlib HTTP API（`server.py`）和 SQLite 持久化（`store.py`、`optimization_store.py`）。
  - 预测 `nhpp.py`（冻结）；放票 `release_policy.py`；座位口径 `seat_inventory.py`；指定航班优化 `optimization.py`、`scoped_market.py`、`initial_policy.py`；共享市场 `shared_market.py`；座位反馈 `seat_feedback.py`。
  - 测试在 `backend/tests/`。
- `frontend/`：Admin，原生 HTML/JS，路径 `/admin`；`frontend/members/` 是会员端，路径 `/members`。不需要构建，由后端直接提供；`*.mjs` 是浏览器 smoke 测试。
- `simulation/`：合成数据生成器、NHPP 评估脚本和已提交的冻结数据集。
- `llm_agent/`：旅客 Agent、prompt、provider 适配、审计；`experiments/` 是可公开的合成实验证据。
- `scripts/`：发布检查、证据校验、HTTP/容器 smoke、导出工具。`tests/`：根目录的发布和模拟器测试。
- `docs/`：架构、规则、验证和进度。完成的里程碑记到 `docs/ITERATION_2_PROGRESS.md`。

## 其他约定

- UI 配色：紫 `#6F2C91`、青 `#24BCDC`、白。Admin 四个入口：Forecast / Optimize / Experiments / Manage offers。
- `NO_OFFER` 是合法结论。候选只是"已评估候选中最好的"，不要称为真实最优价。LLM 输出是合成角色扮演，不是真实客户。
- 报告 LLM 结果时，新调用、缓存命中、强制动作、失败要分开统计。

## 维护本文件（Codex 和 Claude Code 都要遵守）

- 改动以下任一项时，**在同一个提交里**更新本文件：权威文档、过时文档、冻结清单、测试命令、目录或模块职责。
- 发现本文件与代码或文档不符时，先修正本文件，并在回复里告诉用户。
- 只写每次会话都需要的内容，**不超过 100 行**，细节写进 `docs/` 再链接过来。`tests/test_agent_instructions.py` 会检查行数。
- 只改 `AGENTS.md`。`CLAUDE.md` 永远只保留 `@AGENTS.md` 导入行，不要往里加内容。
