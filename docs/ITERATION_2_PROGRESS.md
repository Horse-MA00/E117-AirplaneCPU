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
