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
