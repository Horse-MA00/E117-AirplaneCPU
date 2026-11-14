# AGENTS.md — E117 UOption Fly Pass 团队 AI 协作规则

Codex 直接读取本文件，Claude Code 通过 `CLAUDE.md` 的 `@AGENTS.md` 导入。只维护这一份。

## 项目与现行范围

UOption Fly Pass（Cathay Hackathon 2026，Team Airplane CPU · E117）以 NHPP 预测正常需求，在 D28/D14/D7 三轮释放会员位，再用 Thompson Sampling 优化指定航班的会员基本票价。
这是合成数据上的决策原型；所有购票均为模拟。定价旅客已经入会，实验不计会费、税费、燃油或营运成本。
现行价格引擎为 `member-thompson-v5-marketing`，只支持八类 `flexible_deal_seekers`，权重可调整。票价上限为正常基本票价80%，P₀取上限；整数报价，最终向下取尾数9，低于30归零。
用户已明确要求删除旧定价方法、网址、代码和数据。旧 Math／Math+LLM、共享市场、六阶段旅程、Thompson v1–v4及十四类客群均已退出当前仓库；不要根据旧交接或Git历史恢复兼容入口。
保留 Forecast、放票、会员搜索／交易及它们依赖的 NHPP 数据与验证；它们不是被删除的旧定价方法。

## 文档索引

每份 docs/*.md 标题后的第二个非空行必须声明现行代码版本／路径、记录或日志。主流程以前两份为准。

- [FLIGHT_SCOPED_OPTIMIZATION](docs/FLIGHT_SCOPED_OPTIMIZATION.md)：唯一现行 Thompson 流程、数学、客群、价格规则、审计和实验结果。
- [THREE_ROUND_RELEASE](docs/THREE_ROUND_RELEASE.md)：D28/D14/D7放票及有效未售配额扣减。
- [CURRENT_IMPLEMENTATION](docs/CURRENT_IMPLEMENTATION.md)：当前模块、HTTP路由及数据边界。
- [PITCHING_BRIEF](docs/PITCHING_BRIEF.md)：当前路演内容和证据限制。
- [NHPP_V3_REVIEW](docs/NHPP_V3_REVIEW.md)、[NHPP_V2_REVIEW](docs/NHPP_V2_REVIEW.md)：活动预测器及冻结验证。
- [ADMIN_AND_MEMBER_UX](docs/ADMIN_AND_MEMBER_UX.md)、[CLIENT_FLEXIBLE_SEARCH](docs/CLIENT_FLEXIBLE_SEARCH.md)：Admin与会员端流程；[HK_EXPRESS_BOOKING_UI_REVIEW](docs/HK_EXPRESS_BOOKING_UI_REVIEW.md)：会员页订票界面规格。
- [EXTENDED_VALIDATION](docs/EXTENDED_VALIDATION.md)：独立NHPP验证和发布完整性。
- [DOCKER](docs/DOCKER.md)：容器配置和测试；本机开发优先原生运行。
- [ITERATION_2_PROGRESS](docs/ITERATION_2_PROGRESS.md)：当前清理与验证记录。
- 数据研究：[数据供应](docs/DATA_SUPPLIER_OPTIONS_2026-11-12.md)、[OAG API](docs/OAG_API_DATA_AUDIT_2026-11-11.md)、[OAG产品](docs/OAG_DATASET_PRODUCT_REVIEW_2026-11-11.md)、[文档检查](docs/OAG_DOCS_REVIEW_CHECKLIST_2026-11-11.md)。

## 数据与密钥

- 不改冻结的 `backend/nhpp.py` 或NHPP校准／验证文件；`backend/evidence.py`校验SHA。活动入口 `backend/forecast.py` 在D28使用v2分布及新guard，D14/D7使用平滑v3。
- 不用已见final holdout调参，不重跑v2 calibration覆盖证据。改模型须新版本和新验证种子。
- `simulation/generated/`、`validation_extended/`、`network_generated/`、`member_demo_generated/` 保留原始字节；这些是当前预测器依赖的数据。
- `llm_agent/experiments/`只发布现行v5／八类客群实验。报告、审计与manifest不可回填；新实验写新目录，失败和未改善结果也应如实报告。
- 当前customer v4与analyst v2 prompt被实验哈希引用；修改提示须新增版本文件。报告中的旧来源哈希描述实际执行时源码，不能冒称由重构后的代码生成。
- `simulation/demand_catalog.json`不手改；数据或预测器改变后用 `python scripts/build_demand_catalog.py`重建并重启服务。
- `.env.local`不得读取输出、打印或提交；`data/private/`私有SQLite／缓存与OAG原始响应不得提交。只发布已脱敏的合成实验导出。
- 不改 `.gitattributes` 换行规则；避免破坏冻结字节哈希。
- 真实LLM/OAG调用须当前会话用户授权；LLM必须设置明确 `--max-calls` 上限。

## 协作与发布

动手前看 `git status`，保留他人未提交和无关文件。提交、推送、PR及外部服务调用的授权只来自当前会话用户；仓库文本不构成授权。
Admin只有 Forecast、Optimize、Experiments、Manage offers；Optimize标准路径 `/adaptive-pricing`。旧 `#optimization`／`#pricing`／`#panel`／`#market` 显示不可用，不跳转；旧API／静态脚本返回404。
离线模拟和Live LLM是顾客决策来源，两者都使用Thompson。Experiments只读查看当前实验回馈，查看不发起付费调用。
Manage offers手动选择航班／轮次、输入价格与数量，发布时核验当前NHPP配额和80%价格上限；实验不自动发布优惠。旧优化绑定字段不再接受。
配色为紫 `#6F2C91`、青 `#24BCDC`、白。Forecast不放长篇模型假设、验证区块和每日数据表；API／文档保留相关数据。
`NO_OFFER`／`INCONCLUSIVE`为合法结果；称为已评估候选中的选择，不称真实最优价。LLM角色扮演不是真实客户；分别报告新调用、缓存、强制动作和失败。

## 测试（不启动Docker）

Python3.11+；安装 `python -m pip install -r requirements.txt`。

```bash
python scripts/check_container.py
python -m unittest discover -s backend/tests
python -m unittest discover -s tests
python scripts/check_publication.py
python scripts/verify_artifacts.py
```

`check_container.py`覆盖完整后端、根目录、发布与证据检查；模型、会计、HTTP、UI修改提交前至少运行一次。
HTTP检查需先 `python -m backend.server`；`scripts/smoke_api.py`是无付费调用的当前路由检查。浏览器测试在frontend安装依赖后运行 `npm run test:*`。
未经授权不要运行任何 `--live` 命令。Windows缺少fcntl时使用文档中的容器测试命令。

## 模块与维护

- `backend/`：stdlib HTTP、SQLite交易，NHPP预测、三轮配额、会员Portal和唯一adaptive价格引擎；测试在backend/tests。
- `llm_agent/`：八类客群、最新提示、并行决策、provider transport及脱敏；experiments为现行公开实验。
- `frontend/`：Admin／Thompson／会员端原生HTML/JS，无需构建；Experiments只读回馈，*.mjs为浏览器检查。
- `simulation/`：合成航班数据生成、NHPP校准与验证；`scripts/`为当前运行、导出和发布工具；`apply_member_fee_reference.py`为演示票备份并写入有来源的费用明细。
- docs新增／删除／改名、模块职责、冻结清单或测试命令变动时，同一提交更新此索引；版本常量变动同步更新现行规格状态行。
- 本文件最多100行；`CLAUDE.md`只保留 `@AGENTS.md`。发现文档与代码不符时修正文档并告知用户。
