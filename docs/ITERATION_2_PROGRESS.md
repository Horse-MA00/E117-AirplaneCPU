# 当前实现维护记录

> 状态：日志，只追加新条目，不改旧条目

本日志自2026-11-15起记录当前实现；更早记录可查Git历史。

## 2026-11-15 · 只保留当前 Thompson 定价流程

按使用者明确要求，清理范围从隐藏旧UI扩大为删除旧URL、代码及定价数据。当前工作树仅保留Thompson v5／八类弹性客群及其数据；对应README、架构、UI、路演与测试入口同步更新。此前包含旧方法的进度记录已从工作树移除，可由Git历史追查；不重写提交历史。

保留：

- NHPP活动预测（D28的v2分布／新guard、D14／D7的平滑v3），核心合成航班、校准、未通过候选及独立验证证据。
- D28／D14／D7配额结转、人工发布、会员plan与模拟购票。
- `member-thompson-v5-marketing`、公开特征学习、八类权重、离线／Live顾客、有限并行、逐轮回馈和独立确认。
- 六份已完成且符合当前版本／客群的实验，含一份Live、五份离线；成功、保留初始及无定论结果均保留，见[证据索引](../llm_agent/experiments/README.md)。本次仅导出现有记录，没有新增付费调用。

移除旧定价引擎、会费联合优化、共用市场、panel／journey、连续定价、旧Thompson及旧客群实验，连同旧API／页面／脚本和误导性的文档入口。旧实验ID不再作为可读取的当前结果。发布仍由管理员明确操作，Thompson不会自动修改会员网站库存或会费。

## 保留的验证背景

NHPP的校准与独立测试结果未改变；活动组合和风险代价见[NHPP v3记录](NHPP_V3_REVIEW.md)，更早的凍结分布与扩大评估见[NHPP v2](NHPP_V2_REVIEW.md)、[扩大验证](EXTENDED_VALIDATION.md)。这些指标用于正常需求保护，不是价格或全年会员盈利证明。

当前Live v5报告记录213次provider调用、0缓存、245次强制动作及0失败。候选273格式化269，在三批新顾客确认后采用；其余五份离线结果保留不采用／无定论。所有数值来自原始报告，本次代码整理未重新运行这些市场。

## 当前清理验证

完整原生检查通过182项后端及20项根目录测试；包括旧API／静态脚本404、旧优化绑定拒绝、当前版本实验隔离、provider跳转限制、配额与会员交易。发布检查只接受当前v5／八类客群证据，六份导出的SHA及审计核验全部通过。

六组浏览器检查通过：当前Thompson、人工发布、需求筛选、配额、Admin主流程和已保存实验载入；旧hash入口保持不可用且不跳转，桌面与390／768px手机布局通过。原生HTTP smoke通过1,549班目录、Forecast与Thompson scope、旧API／文件404；没有发起付费调用。

私有SQLite删除10个旧版本／旧客群实验，保留6次当前实验和2,106条事件；逐笔payload与导出前一致。旧定价私有缓存和前次含旧记录的备份已删除；会员交易数据库、OAG私有数据及密钥保留且不提交。已移除28个旧公开实验目录，新增6个当前v5导出目录；没有回写历史收益或以新版本冒充旧实验结果。

以上是本轮软件验证，和213次已保存Live调用的实验结果分别统计。Thompson方程、当前提示、NHPP模型与核心数据字节未改；八类人物生成在12组种子／人数对照中与清理前完全一致。

## 2026-11-14 Member journey branch

Created feature/member-demo-journey without merging main. Added bookable Japan return pairs, two-ticket cost planning, return suggestions, available-date shortcuts, first-purchase totals and fare-rights explanations. Portal API adds supplied departure timestamps. Six prepublished demo offers remain in the persistent database. No new payment or atomic round-trip system.
- Member page simplification: removed upfront return-pair recommendations and the two-flight plan at user request. Kept search, fee transparency and post-purchase return suggestions on `feature/member-demo-journey`.
- Added sourced demo fee estimates for the six pitch offers: YR fuel, government/airport charges and Japan e-payment; stored breakdowns match settlement totals, with dated FX and booked-offer repricing protection.
- 2026-11-15: documented HK Express search, airport and calendar UI observations with the post-search CAPTCHA evidence limit. Implemented a compact member booking layout, airport swap, published-date total-price strip, total-price sorting and sticky checkout actions; kept the removed round-trip recommendation absent.

## 2026-11-15 · 会员搜索合并机场／国家，非会员按钮显示总额

按用户手动测试意见：起点与目的地各为一个「机场或整个国家」选单（起点也可选国家），删除 Flexible dates & destination region 折叠区中的独立国家选单与精确日期，出发日期只用范围（单日即起讫同日）。未入会者结账按钮显示「Membership + ticket total」，并注明第一步只收会费、之后另行确认机票。`test:members`、`test:member-journey`、`test:flexible-search`、`test:route-catalog` 已同步更新并通过。
会员票卡片与结账明细在会员基本票价旁以删除线显示同航班普通基本票价（读屏读作「Normal base fare」），并标注节省金额与折扣百分比；普通票价取 `normal_base_fare`，缺失时以 `normal_total − mandatory_fees` 推算，不高于会员价时不显示。

## 2026-11-15 · 半年会员与两类示范登入

会员页 booking hero 四角统一16px圆角，桌面及390px手机均保留。默认计划改为HK$399／六个历月；前台、Admin和结账同步显示6 months，后端依香港时间计算新会员到期日，处理月底和闰年；已有会员付款与到期日保持原记录。

新增 `/members/login`，提供已购会员和初始未购会员两个公开示范账号，详情见[操作文档](ADMIN_AND_MEMBER_UX.md#client-portal)。快捷按钮填入账号后仍须明确登录；24小时HttpOnly／SameSite=Lax cookie绑定身份，SQLite只保存session token哈希。刷新、切换、登出及过期均由后端核对，跨账号操作拒绝。Guest入会后不因再次登录而重置；删除会员UI的任意ID输入与localStorage身份选择。仍为本机原型，开发ID接口和Admin不是生产权限系统。

验证：完整 `scripts/check_container.py` 通过198项后端、20项根目录测试，发布与冻结证据检查通过。九组受影响的浏览器fixture检查及新增 `npm run test:member-login` 均通过；后者使用临时SQLite和本机服务验证真实cookie、无效密码、跨账号隔离、登出、会籍保留和手机布局。桌面／手机截图已人工查看。未调用LLM/OAG，未消耗现有演示座位，未改预测／定价算法或冻结数据。原有未提交文档修改保留。

## 2026-11-15 · 新版 Admin UI 整合至 main

选择性引入 `claude/frontend-fixes` 的 `5699a99`，基于 main 的 `55506db`。该分支自共同基点 `f57e37c` 以来没有修改后端；main 已增加示范登录与六个历月会员，因此保留 main 的全部后端、`llm_agent/`、`simulation/` 和整个 `frontend/members/`，逐文件比对无差异。不合并分支中的旧后端状态。

Admin 采用 Inter、侧栏、共用需求／航线／航班／轮次选择栏，保留 Forecast 和 Thompson 优化；发布页增加会员卡预览，Results 汇总已发布优惠、已售会员位及基本票款，Member feedback 保持只读。无新后端接口或模型改动。

整合修复：

- 分支中的年度文案与测试 fixture 对齐现行六个月方案；修改会费后预览即时刷新。
- 空需求筛选或更换航班时清除旧发布目标、预测及待返回请求，防止在旧航班发布；恢复已保存实验时对齐需求筛选、航线、航班与轮次按钮。
- Results 将未消耗的配额明确标成 Unspent member quota，不能视作实时可订量；座位条保留暂扣类别，处理需求保护超过当前容量的状态。
- 移除重复嵌套的实验表单；前端契约对齐现行 Cookie 登录接口，不恢复旧任意 ID 会员 UI。

验证：`scripts/check_container.py` 通过 **198 项后端 + 24 项根目录测试（共 222 项）**，发布及冻结证据校验通过。12 个浏览器测试脚本及 1 个强制 Temporal fallback 变体全部通过，涵盖 Admin、Optimize、发布、Results、需求筛选、座位保护，以及保留的 Client 搜索、购票旅程和登录。已查看 1920×1080 桌面与 390px 手机版截图，无横向溢出或页面脚本错误。

浏览器优化检查只读取既有离线结果；登录检查使用临时数据库。未发起 LLM／OAG 调用，未建立新价格实验或消耗现有演示库存。用户原有未提交的技术文档及其他文件保持在工作区，本次提交只包含 Admin 整合及其对应文档、测试。

## 2026-11-15 · 移除 D1，发布现行文档修改

Admin 与 Optimize 顶部删除 D1 快捷按钮／停用占位，只保留 D28／D14／D7。删除 D1 专用的视图禁用逻辑，Admin URL 的 `forecast_day=1` 不再选中 D1，使用默认 D28。逐日预测、观察滑杆及冻结数据保持原样；Client Portal和后端代码未改。

按用户本次要求，一并发布此前未提交的六份现行项目文档修改：AGENTS、README、Client 搜索说明、完整技术速读与 Present 指南、NHPP v3说明及三轮配额职责纠正。技术指南同步当前 main 基准、Admin入口名称和验证数量。旧交接、外部原始PDF、历史发布／数据压缩包及测试输出保留本地。

验证：完整 `scripts/check_container.py` 通过198项后端、24项根目录测试（共222项），发布和冻结证据检查通过。四项浏览器检查 `test:smoke`、`test:adaptive-pricing`、`test:demand-filter`、`test:flight-offers` 全部通过；额外只读检查确认两页按钮均为D28／D14／D7，旧D1 URL回到D28且选中状态正确。原生8001服务已恢复运行。没有LLM／OAG调用、新实验或实际示例库存交易。

## 2026-11-15 · Admin 完整 From／To 与航班编号

Admin 与 Optimize 的 Route 改为 From → To，复用 Client 的完整机场／国家目录及实际航班双端机场。两个选框支持 Anywhere、国家及单个机场，不随Demand缩减；Flight 按三个条件共同筛选，显示日期、完整合成flight_id，宽范围另加航线。保留D28／D14／D7以及现行Client页面，删除不再使用的Route搜索脚本与样式。

空组合保持用户选择并清除旧预测、发布目标和优化scope；显式加载已保存实验恢复该航班，自动加载最新结果保持原地区范围。共享helper统一日期显示，不因浏览器时区改变日期。桌面From／To并排，手机依照键盘顺序排列。

验证：`scripts/check_container.py` 通过198项后端及24项根目录测试，发布及冻结证据检查通过。六组浏览器检查通过：Demand、Adaptive pricing、Flight offers、Seat supply、真实Admin流程和已保存离线实验读取。覆盖完整目录、地区／Anywhere、返程、同日不同编号、空结果及过期请求拦截；最终样式再次通过Demand与真实Admin手机检查。Client、后端、冻结数据没有修改；没有LLM／OAG调用、新实验或库存交易。

## 2026-11-15 · Analyst有限重试与不中断Thompson

原因已由原始audit离线重现：Analyst报价格异议数0却建议lower，旧版验证拒绝后中断整个run。现在`analyst-retry-v1`每轮最多首次加两次重试；验证修正使用同一feedback及具体错误、前次不可信回覆，临时transport错误有短暂退避。永久错误或预算耗尽可提前结束，所有派送共用max_calls。预估上界改为`R*(2*M+3)+3*H*M`，默认10轮／16人／3批确认上界494。

Analyst仍不可用时存`analysis=null`、error、attempt metadata和unavailable轮号，顾客决策及本轮模型更新不丢失；后续普通Thompson选价，最终独立确认照常执行。顾客回覆失败、audit写入失败或非预期内部错误仍停止，包括尚未派送的并行请求。没有伪造摘要、购买标签或重跑同一客群补结果。冻结prompt文件保持原字节，新增policy metadata记录行为变化；旧失败实验不回填、不自动恢复。

新增只读`analysis-attempts`审计投影，默认metadata，指定round才读原始回覆；旧audit也能还原尚未成为完整round的失败阶段。Optimize和Member feedback显示具体错误、重试及分析不可用，原生details按需显示已脱敏原文，以textContent阻止HTML执行；无新回覆、cache及传输失败不会伪装成模型输出。Client和NHPP未修改。

验证：新adapter、worker、审计API与浏览器测试先在旧行为失败，再修复通过。完整原生`check_container.py`通过216项后端＋24项根目录，共240项；发布链接及冻结SHA验证通过。完整worker mock测试让3轮Analyst各失败3次，记录9次失败、6次重试、3轮分析不可用，仍完成Thompson及独立确认。测试同时覆盖恢复成功、预算边界、永久／暂时错误、原始回覆保存、audit／内部失败停止排队、历史audit投影与大小上限。

浏览器`test:analyst-diagnostics`、`test:adaptive-pricing`、真实服务`test:smoke`通过；额外在实际旧失败实验验证第10轮具体错误／原文及已保存顾客选择在两页均可读，未启动新实验。桌面／390px截图检查通过，包含恶意HTML作为纯文字、迟到响应隔离、加载失败重试。整个修复没有真实LLM／OAG调用或库存交易；确认无活动实验后重启原生8000服务。

推送前发现main更新至`167d1d2`，合并保留新的地点搜索、屏宽缩放及品牌字标；唯一文档冲突保留双方章节。合并后240项完整检查再次通过；Analyst诊断、Optimize、Demand／地点搜索及真实Admin浏览器检查再次通过，没有覆盖远端UI改动。

## 2026-11-15 · DEMO_LLM0–9 十航班 Live 演示实验

按用户指定的十个航班与D28／D14／D7快照运行，名称固定为`DEMO_LLM0`至`DEMO_LLM9`。引擎为`member-thompson-v5-marketing`，provider model为`deepseek-flash`，保留八类`flexible_deal_seekers`默认假设权重。每航班10轮、每轮16位新模拟会员、3批各16位独立验证会员、并发4、seed117；单次尝试上限600次、整批含失败尝试上限10,000次调用。每个验证批比较格式化初始价、格式化候选价和no-offer。

新增可选`config.name`与CLI `--name`，Optimize和Member feedback的已保存实验选单显示名称。内部run ID保持唯一，失败尝试不覆盖；完成但不采纳候选价的实验不会为追求改善而重跑。

| 名称 | 香港出发目的地 | 航班 ID | 轮次 | 原始P₀ | 验证初始价 | 验证候选价 | 最终保留价 | 结论 | Live调用 |
|---|---|---|---:|---:|---:|---:|---:|---|---:|
| DEMO_LLM0 | 福冈 FUK | `SYN-00017` | D7 | 552 | 549 | 229 | 229 | ADOPT_CANDIDATE | 217 |
| DEMO_LLM1 | 冲绳 OKA | `DEMO-HKG-OKA-20270515` | D14 | 528 | 519 | 229 | 229 | ADOPT_CANDIDATE | 232 |
| DEMO_LLM2 | 名古屋 NGO | `DEMO-HKG-NGO-20270515` | D7 | 480 | 479 | 279 | 279 | ADOPT_CANDIDATE | 255 |
| DEMO_LLM3 | 釜山 PUS | `DEMO-HKG-PUS-20270515` | D28 | 496 | 489 | 279 | 279 | ADOPT_CANDIDATE | 239 |
| DEMO_LLM4 | 富国岛 PQC | `DEMO-HKG-PQC-20270515` | D28 | 480 | 479 | 279 | 279 | ADOPT_CANDIDATE | 251 |
| DEMO_LLM5 | 札幌 CTS | `DEMO-HKG-CTS-20270515` | D7 | 408 | 399 | 289 | 399 | INCONCLUSIVE | 281 |
| DEMO_LLM6 | 大阪 KIX | `DEMO-HKG-KIX-20270515` | D14 | 376 | 369 | 269 | 269 | ADOPT_CANDIDATE | 283 |
| DEMO_LLM7 | 东京成田 NRT | `DEMO-HKG-NRT-20270515` | D7 | 368 | 359 | 259 | 259 | ADOPT_CANDIDATE | 291 |
| DEMO_LLM8 | 首尔 ICN | `NET-HKG-ICN-20270521` | D14 | 632 | 629 | 279 | 279 | ADOPT_CANDIDATE | 180 |
| DEMO_LLM9 | 岘港 DAD | `SYN-00367` | D28 | 472 | 469 | 279 | 279 | ADOPT_CANDIDATE | 257 |

以上都是港币基本票价。P₀取正常基本票价80%整数上限；候选及初始备选均在独立验证前执行尾数9／低于30归零的现行规则。最终保留价与搜索候选价分开报告。

| 名称 | 验证初始价加权平均票款 | 验证候选价加权平均票款 | 初始购买率 | 候选购买率 |
|---|---:|---:|---:|---:|
| DEMO_LLM0 | 897.92 | 2589.23 | 10.22% | 70.67% |
| DEMO_LLM1 | 1005.71 | 2585.16 | 12.11% | 70.56% |
| DEMO_LLM2 | 1336.94 | 2599.04 | 17.44% | 58.22% |
| DEMO_LLM3 | 1208.37 | 2380.80 | 15.44% | 53.33% |
| DEMO_LLM4 | 1183.66 | 2579.20 | 15.44% | 57.78% |
| DEMO_LLM5 | 2206.03 | 2425.03 | 34.56% | 52.44% |
| DEMO_LLM6 | 1948.32 | 2553.71 | 33.00% | 59.33% |
| DEMO_LLM7 | 2176.34 | 2661.37 | 37.89% | 64.22% |
| DEMO_LLM8 | 201.28 | 2658.56 | 2.00% | 59.56% |
| DEMO_LLM9 | 1309.03 | 2480.00 | 17.44% | 55.56% |

票款为每批16人的目标客群加权基本票价收入，取3个独立验证批均值，既不是整班售罄收入，也不是计入成本后的净利润。候选列即使有较高均值，也必须通过现行跨批确认门槛才会采用。札幌候选价289的加权平均改善为HK$219.00，但描述性跨批区间含负值，因此结果为INCONCLUSIVE，保留399，不把候选289当作最终推荐。

全部10个实验完成；整次实验失败尝试0次。实际provider调用2486次（顾客2385、Analyst 101）；缓存0次，环境强制动作2015次，失败调用1次，Analyst重试1次，最终分析不可用0轮。DEMO_LLM0第4轮首次分析未通过校验，第二次通过；原始失败回覆保留。

每个航班160位搜索会员和48位验证会员互不重叠；不同航班使用相同种子设置，不将跨航班的人物重复当成新的市场样本。部分动作由假设预算或资格直接限制，不能把所有动作均称为LLM自由选择，更不能把角色扮演视为真实HK Express客户证据。未为了改善结果更改prompt、权重、NHPP或价格算法。

本机SQLite保存原始请求、回覆、重试与每轮结果；每个完成实验另外导出report、压缩audit和manifest至`data/private/demo_llm_batch_20261115/DEMO_LLM*/`，整批清单为同目录`batch.json`。数据保持本机私有；本次未发布优惠或改变会员购票库存。运行时源码哈希保存在每份报告，不能以未来代码覆盖其来源。

验证：217项后端＋24项根目录测试，共241项通过；发布链接与冻结证据校验通过。命名UI的mock浏览器检查通过；真实Admin只读浏览器检查确认10个完成的Live实验在Optimize和Member feedback均按名称显示。另对全部10份导出逐一核对manifest、28项源码哈希、审计请求／响应／失败计数、搜索验证分离、配额、整数报价、实收及加权票款，均通过。

| 名称 | 本机审计 run ID |
|---|---|
| DEMO_LLM0 | `adaptive-212f9b8009354aa2` |
| DEMO_LLM1 | `adaptive-770a77ffdf744c26` |
| DEMO_LLM2 | `adaptive-a16becb4c5a84a42` |
| DEMO_LLM3 | `adaptive-128ca771fab84936` |
| DEMO_LLM4 | `adaptive-ee1d9908431843be` |
| DEMO_LLM5 | `adaptive-35be7f49b42541fa` |
| DEMO_LLM6 | `adaptive-ce0a1b83a58b4656` |
| DEMO_LLM7 | `adaptive-07bce337bd4b4574` |
| DEMO_LLM8 | `adaptive-b58d9adf0b8645e4` |
| DEMO_LLM9 | `adaptive-e1e48590ec734852` |

## 2026-11-15 · 低价情境与算法归零示范

新增显式`zero-fare-stress-v1`情境入口，并沿用相同Thompson、八类客群、冻结customer v4／analyst v2 prompt及宣传价函数。三个情境假设正常基本票价55／60／65、私人票价预算为默认值的10%，初始上限44／48／52仍高于30；没有写入目标输出价或购买标签。每组20轮、每轮32位新模拟会员、3批各32位独立确认、并发4，种子26111501／26111502／26111503。

来源分别为SYN-00017 D7、DEMO-HKG-OKA-20270515 D14、DEMO-HKG-NGO-20270515 D7。保留各自原NHPP配额58／81／112作固定实验供给，并保存原scope及hash；没有在假设低正常价下重新做NHPP预测。预算仅在顾客环境缩放，公开learner仍只有原来的四个字段。默认航班与原有实验不使用这些假设。

| 名称 | 顾客来源 | 假设正常价 | 初始P₀ | 算法原始候选 | 宣传价 | 收入验证保留价 | 验证结果 | 原价严格低于30 |
|---|---|---:|---:|---:|---:|---:|---|---|
| DEMO_ZERO_PILOT0 | Offline | 55 | 44 | 18 | 0 | 39 | KEEP_INITIAL | 是 |
| DEMO_ZERO_PILOT1 | Offline | 60 | 48 | 20 | 0 | 39 | KEEP_INITIAL | 是 |
| DEMO_ZERO_PILOT2 | Offline | 65 | 52 | 18 | 0 | 49 | KEEP_INITIAL | 是 |
| DEMO_ZERO0 | Live LLM | 55 | 44 | 30 | 0 | 39 | KEEP_INITIAL | 否：尾数9后的边界案例 |
| DEMO_ZERO1 | Live LLM | 60 | 48 | 29 | 0 | 39 | KEEP_INITIAL | 是 |
| DEMO_ZERO2 | Live LLM | 65 | 52 | 29 | 0 | 49 | KEEP_INITIAL | 是 |

六个实验均真实运行并保存。离线三组满足严格的「算法原价<30→0」。Live结果依实际输出分类；原价30等边界值先按现行规则变29再归零，不能冒称算法选出了低于30。所有完成结果保留，不因未达到示范目标或收入未改善而重跑。

**零元是自动转换后的宣传候选，不是收入验证保留价。** 这些实验的独立确认仍使用原有票款门槛，因此不会为了展示零元而篡改KEEP_INITIAL／NO_OFFER。也没有给宣传效果或未来收益捏造数值。

Live新调用2082次（顾客2020、Analyst 62），缓存0次，环境强制动作2268次，失败调用2次，Analyst重试2次，最终分析不可用0轮。整次Live执行失败尝试0次。每次预算1800、整批含失败尝试7200；离线三组不发起provider调用。

第一份Live实验完成后audit超过HTTP32MiB整份匯出限制，未重跑该实验。CLI改为每页100笔既有事件串流脱敏与gzip，先写临时目录、完整后改名；保留HTTP限制和不覆盖旧证据规则。修复后从SQLite补齐首份导出，并继续另外两组。

Admin显式载入这些命名实验时显示假设价格、预算10%及固定来源NHPP配额。普通航班最新结果、发布参考和发布捷径排除此类情境；查看时不能误启动普通实验，New experiment先恢复原scope。Client库存与已发布优惠不被实验修改。

验证：253项完整回归测试（223后端＋30根目录）、发布与冻结证据检查通过；两组mock浏览器检查、六份实际结果的只读网页检查通过。六份证据均核对manifest、源码hash、客群分离、预算缩放、库存与票款，且用保存的购买标签重播全部20轮Thompson及最终选价，再重新计算收入验证，结果一致。严格raw<30的示范判定与证据完整性分别报告；边界案例的判定不被改成通过。

原始报告、audit及manifest保存在`data/private/zero_fare_demos_20261115_synthetic/`及`data/private/zero_fare_demos_20261115_live/`。它们是构造输入下的离线／LLM角色扮演，并非真实HK Express需求、价格或收益证据。

| 名称 | 本机审计 run ID |
|---|---|
| DEMO_ZERO_PILOT0 | `adaptive-0e3e39e82042426c` |
| DEMO_ZERO_PILOT1 | `adaptive-55a378142aa24343` |
| DEMO_ZERO_PILOT2 | `adaptive-13f94e8449fd441e` |
| DEMO_ZERO0 | `adaptive-ad921ba299364aef` |
| DEMO_ZERO1 | `adaptive-82bc572307eb4e77` |
| DEMO_ZERO2 | `adaptive-0b98e5068a1e4060` |


## 2026-11-15 · 全部现行实验发布与无密钥部署演示

交付集合包含本机全部24份现行v5／八类客群终态实验：23完成、1失败。保留原六份公开证据，新增DEMO_LLM0–9、DEMO_ZERO0–2、DEMO_ZERO_PILOT0–2，以及离线完成`adaptive-3858026a10104926`和Live失败`adaptive-c5c1ac811b2b4f9d`。本次只导出／复制既有数据，新provider调用0；失败结果没有重跑、补填确认或改成成功。

全部report、脱敏audit.jsonl.gz及manifest约198.8MB，最大单文件约15.8MB。原六份公开文件和十六份已有私人导出保留原始字节；另外两份从保存SQLite串流导出。来源哈希描述运行时版本，不因本次重构改写。全部680,364条合成观测及冻结NHPP证据仍随仓库保留，未重生成或改动。私有SQLite、缓存、密钥、真实OAG原始回覆、用户账户／订单不上传。

新增`backend/published_experiments.py`：服务启动核验目录完整性、manifest、SHA256、大小、版本、客群和终态，再把公开记录作为Saved experiments只读来源。私有同ID记录优先且列表去重；report按需读，audit按页流式读，原始Analyst回覆按轮查询。公开证据不导入数据库、不恢复运行、不自动发布优惠。缺失目录、未完整导出、重复ID、非终态、损坏文件及非有限JSON等明确失败，不能假装没有保存实验。

导出新增显式`--include-failed`并保留历史错误；manifest区分completed／execution_failure，没有完成确认就不宣称holdout证据。验证器从audit重新核对调用、响应、失败、缓存、强制动作、token、轮次和确认结果。三次恢复的Analyst失败和一次终止失败都如实保留。24份历史累计4945次provider调用，不能误称本次发布产生了这些调用。

验证结果：

- `scripts/check_container.py`完整通过：238后端＋42根目录，共280项Python测试；链接、24份manifest、冻结NHPP证据与audit一致性通过。
- 独立比对24份report、72页audit、24份Analyst汇总及15轮原始回覆，与本机SQLite相同（仅添加公开来源只读标记）；载入目录约0.92秒。查看公开记录后私有实验表和事件表仍为0行。
- 从不包含`.env.local`或`data/private`的源码副本启动原生服务器，环境只含PATH／LANG／PYTHONNOUSERSITE，provider transport被测试明确禁止；不启动Docker。
- 该干净部署的API smoke通过，1549班航班及预测可用。真实Chrome确认Saved experiments的24个选项、16个DEMO名称、正常Live结果、Offline／Live归零情境、一次恢复重试的两份原始回覆及旧失败轮的原始错误。新模型调用0，修改请求0。
- 浏览器初次脚本点击早于Analyst异步metadata完成而超时；等待metadata请求完成后重测通过。未改变报告或伪造回覆以满足测试。

演示：部署后打开`/adaptive-pricing`的Saved experiments，优先DEMO_LLM0／1；Member feedback查看理由。零价用DEMO_ZERO1／2，明确呈现29→0候选和39／49收入确认保留价。归零情境仍与普通航班推荐及发布隔离。操作和全部报告链接见[部署文档](DOCKER.md)及[公开实验索引](../llm_agent/experiments/README.md)。

截图检查补充：归零情境的说明原位于完成后折叠的设置中，现移至结果价格上方的可见段落，列明假设票价、10%预算和固定来源NHPP配额。按modern-web-guidance accessibility指引保留原生可见文字；桌面／手机可见性、无横向溢出及切回普通实验清除标示均通过浏览器检查。
