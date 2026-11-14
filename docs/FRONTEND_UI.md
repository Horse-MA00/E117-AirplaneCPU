# 前端 UI 规格

> 状态：现行 · 对应代码：`frontend/ui-contract.json`、`frontend/styles.css`、`frontend/members/portal.css`、`tests/test_frontend_contract.py`

这份文档管前端**长什么样、怎么搭**：重构规则、冻结的功能与接口、设计系统、信息架构和设计决定。
前端**做什么**（交互流程、产品取舍、面板上限）以 [ADMIN_AND_MEMBER_UX](ADMIN_AND_MEMBER_UX.md) 和 [CLIENT_FLEXIBLE_SEARCH](CLIENT_FLEXIBLE_SEARCH.md) 为准；接口返回的字段以 [CURRENT_IMPLEMENTATION](CURRENT_IMPLEMENTATION.md) 的路由表为准。

2026-11-14 起，前端在 `claude/frontend-fixes` 分支上重构，范围包括视觉、排版、字体，以及信息架构和布局。功能不变。

---

## 0. 设计目的与受众

用户 2026-11-14 确认。后面所有设计和信息架构决定都以这一节为准。

### 0.1 给谁看、在什么场合

- **主要受众是 Cathay Hackathon 评委**，不是日常使用的收益分析师。
- 场合是 5 分钟 presentation：headline → problem → solution → **demo（60～90 秒）** → benefits，重点是 solution、demo、benefits。
- 也就是说，demo 每个画面大约只有 15～20 秒。评委不会细读页面上的小字。

### 0.2 演示主线

**Forecast seats → Optimize prices → Manage offers → 会员端订票**

1. Forecast：这班航班有多少座位必须留给普通旅客，还剩多少可以安全地给会员。
2. Optimize：在可释放的座位上，什么会员价能带来增量收益（也可能结论是不放票）。
3. Manage offers：管理员确认并发布。
4. 会员端：旅客看到这个优惠并完成订票，库存和账目同步变化。

**Experiments 是辅助证据，不在主线上。** 它用模拟旅客检验优惠：Customer panel 让规则模型或 LLM 扮演的旅客走完六个阶段的决策（看到优惠、是否入会、是否购票等），并保存每次模型的原始回答；Shared market 让多名旅客在同一库存里先后行动。队友加入这部分是为了增强说服力。

**会员端是展示品**，但它和 Admin 共用库存与账目。这个闭环本身就是演示的亮点。

### 0.3 由此推出的设计原则

1. **每屏一个主结论**：评委在 15 秒内能看懂的大数字或一句话，放在最显眼的位置。
2. **解释默认收起**：数据口径、公式、假设这类说明保留（评委提问时要用），但默认折叠或放到次要位置，不能挤占主结论。文字含义不变。
3. **适合投影**：字号够大、对比度够高，不靠小字和细线传达关键信息。
4. **演示不等待**：现场不能等优化或 LLM 跑完。演示路径要能直接打开已保存的结果（这个功能已有，信息架构要让它容易找到）。
5. **闭环看得见**：发布 → 会员端出现 → 订票后库存减少，这条链在画面上要清楚。
6. **诚实标注保留，但要轻**："合成数据""模拟"这类标注用统一的小标签，不用满屏说明文字。

### 0.4 待确认

- 现场操作演示，还是播放录屏？
- 投影或屏幕分辨率是多少？
- Experiments 会在 demo 里出场，还是只在 benefits 或问答环节引用？

---

## 1. 重构规则

### 1.1 冻结的部分

下面这些在重构中**不能改变行为**。机器可检查的清单在 `frontend/ui-contract.json`，由 `tests/test_frontend_contract.py` 检查。

| 冻结内容 | 说明 | 检查方式 |
|---|---|---|
| 功能 | 每个页面现有的操作、状态和结果都要保留；可以换位置、换形式，不能删 | smoke 测试 + 截图对比 |
| 接口 | 浏览器调用的 37 个 API 端点、方法和请求字段（见 §2.2） | 契约测试：JS 里出现的 `/api/...` 必须和清单一致 |
| 数据含义 | 页面上每个数字的口径和文案含义（如"Protected for normal demand"） | 人工审查 |
| 跨模块事件 | `uoption:view`、`uoption:optimize-flight`、`uoption:prepare-policy`、`uoption:provider` | 契约测试 |
| URL 与存储 | Admin 的 hash 路由、`?pricing_run=`、会员端 `localStorage['uoption-member-demo-account']` | smoke 测试 |
| DOM 钩子 | JS 或 smoke 测试引用的 id：Admin 230 个，会员端 53 个；以及 JS 用到的选择器和 class（见 `ui-contract.json` 的 `js_selectors`） | 契约测试：id 必须仍在 HTML 中 |

DOM 钩子可以**移动**到新的位置、换外层结构，但不能删除或改名。确实要改时，在**同一个提交**里同步修改 JS、smoke 测试和 `ui-contract.json`，并在 §6 记录原因。

### 1.2 可以改的部分

- 颜色以外的全部视觉：字体、字号、行高、间距、圆角、阴影、边框、图标、动效。
- 组件的样子：按钮、表单、卡片、表格、指标卡、标签页、对话框、图表外观。
- 布局：栅格、断点、区块顺序和分组、哪些内容默认折叠。
- 信息架构：导航结构、页面内的分区和先后顺序。改动前先在 §5 写方案，和用户确认。
- 文案的措辞可以改，但不能改变数字的含义；改了文案要同步改 smoke 测试里的断言。

### 1.3 硬约束

- **品牌色保留**：紫 `#6F2C91`、青 `#24BCDC`、白（用户 2026-11-14 确认）。
- **不引入框架、不加构建步骤**：保持原生 HTML/CSS/ES modules，由后端直接提供。Docker 镜像里没有 Node。
- **不依赖 CDN**：项目必须离线可用。字体用系统字体栈，或把字体文件放进仓库（必须确认授权允许再分发）。
- **安全**：接口返回的值用 `textContent`、SVG 节点和原生控件渲染，不用 `innerHTML` 拼接。
- **可访问性不能倒退**：保留 skip link、表单 label、键盘可操作、焦点可见、`aria-current`、原生 `<dialog>` 的 Esc 和焦点返回、`prefers-reduced-motion`、`forced-colors`。正文对比度至少 4.5:1。
- **移动端**：390px 宽时不能出现横向滚动（smoke 测试会检查）。

### 1.4 每次改动的验收

1. `python -m unittest tests.test_frontend_contract tests.test_docs_index` 通过。
2. 启动后端后，§3.3 列出的 13 个 smoke 测试全部通过。
3. 与 `docs/frontend-ui/baseline-2026-11-14/` 截图对比，确认没有丢失功能入口。
4. 改了设计系统或信息架构，就同步更新本文档 §4、§5，并在 §6 记一条。

---

## 2. 冻结清单（重构前，2026-11-14）

### 2.1 页面与路由

| 站点 | 入口文件 | 路由 | 机制 |
|---|---|---|---|
| Admin `/admin`（`/` 相同） | `frontend/index.html`，脚本 `app.js`、`optimization.js`、`continuous.js` | `#flights` Forecast seats、`#optimization` Optimize prices、`#pricing` 旧价格对比（隐藏入口）、`#customers` Customer panel、`#market` Shared market、`#members` Manage offers | `location.hash` 选中 `section#view-<route>.view`，其余设为 `hidden`。`#customers` 和 `#market` 在顶部导航里合并为 Experiments（`data-nav="experiments"`） |
| 会员端 `/members` | `frontend/members/index.html`，脚本 `members/portal.js` | `#flights` 搜索与结果、`#membership` 会员卡、`#trips` 我的行程、`#account` 演示账号 | 一个长页面内的锚点；`dialog#checkout` 是订票确认弹窗 |

### 2.2 每个页面的功能与接口

`{x}` 表示路径参数；"链接"表示页面上的下载或查看链接，不是 `fetch`。完整请求字段见 `ui-contract.json`。

| 页面 | 功能 | 接口 |
|---|---|---|
| 公共（Admin） | 数据集标签、LLM 是否已配置 | `GET /api/summary`、`GET /api/flights` |
| Forecast seats | 需求档位筛选、选航班、D28/D14/D7/D1 时间轴、四个座位指标、座位分配条、正常预订与票价两张图、跳转优化 | `GET /api/flights/{id}`、`POST /api/forecast` |
| Optimize prices | 选航线/航班/放票轮次/需求档位、载入低需求示例、数学或 LLM 模式与额度、开始/刷新/续跑、进度、价格与贡献图、逐轮结果、最终建议、收入成本、导出与决策记录、"用这个价格"送到 Manage offers | `GET/POST /api/optimization/runs`、`GET /api/optimization/runs/{id}`、`POST …/{id}/resume`、链接 `…/{id}/export`、`…/{id}/events`、`POST /api/optimization/initial-policy` |
| Optimize 内的参考实验（折叠） | 全期连续定价曲线 | `POST /api/pricing/runs`、`GET /api/pricing/runs/{id}` |
| `#pricing` 旧价格对比 | 票价 × 会费热力图、推荐策略、候选比较与 CSV 导出、压力测试、送到共享市场 | `POST /api/optimize` |
| Customer panel | 新建面板（离线/实时、人数、票价、会费、额度）、进度与续跑、加入情况、分群结果、旅客表格分页、单个旅客六阶段旅程、历史记录与原始决策下载 | `GET /api/personas`、`GET/POST /api/agents/panels`、`GET /api/agents/panels/{id}`、`GET …/{id}/people/{customer}`、`POST …/{id}/resume`、`GET /api/agents/runs`、链接 `/api/agents/runs/{id}/export` |
| Shared market | 新建/续跑共享市场、三策略对比、账本、座位库存、放票轮次、单个旅客全期轨迹 | `GET/POST /api/market/runs`、`GET /api/market/runs/{id}`、`GET …/{id}/cases/{case}`、`POST …/{id}/resume` |
| Manage offers | 为选中航班放出会员座位（可绑定优化结果）、设置会费、已发布优惠列表 | `POST /api/forecast`、`GET /api/optimization/suggestions`、`GET/POST /api/offers`、`GET/POST /api/member-portal/plan` |
| 会员端 | 按出发地/国家地区/日期区间搜索（下月、任意日期、精确机场与日期）、排序和只看有座、航班卡片、会员卡与加入会员、三步订票弹窗、我的行程、切换或新建演示账号 | `GET /api/member-portal/config`、`GET /api/member-portal/flights`、`GET /api/member-portal/accounts/{customer}`、`POST /api/member-portal/join`、`POST /api/member-portal/book` |

### 2.3 跨模块事件、URL 与存储

| 名称 | 发出 → 接收 | 作用 |
|---|---|---|
| `uoption:view` | `app.js` → `optimization.js` | 切到 Optimize 时刷新实验列表并重画图 |
| `uoption:optimize-flight` | Forecast 的 "Optimize this release round"、Manage offers 的建议链接 → `optimization.js` | 带着航班和轮次进入 Optimize |
| `uoption:prepare-policy` | Optimize 的最终建议 → `app.js` | 把建议价格填进 Manage offers 表单（只复制价格草稿） |
| `uoption:provider` | `app.js` → `optimization.js` | 广播 LLM 是否已配置 |
| `?pricing_run=` | `continuous.js` | 刷新后恢复参考实验 |
| `localStorage['uoption-member-demo-account']` | `members/portal.js` | 记住演示账号；读写失败时退回临时身份 |

---

## 3. 现状评估（重构前基线）

### 3.1 截图

`docs/frontend-ui/baseline-2026-11-14/` 下有每个页面的整页截图，桌面 1440px 和手机 390px 各一张，另有会员端订票弹窗。截图时库里有一条已发布的演示优惠和一笔模拟订单。

### 3.2 视觉现状

- **两套 token 各写各的，数值已经不一致**：

  | 用途 | Admin `styles.css` | 会员端 `portal.css` |
  |---|---|---|
  | 正文色 ink | `#261C2C` | `#282133` |
  | 次要文字 muted | `#6A6271` | `#686270` |
  | 分隔线 line | `#E6E0EA` | `#e3dfe8` |
  | 浅底 wash | `#F7F7FA` | `#F7F7F8` |
  | 深青（文字用） | 硬编码 `#087D96` | `--cyan-ink: #087088` |
  | 其他 | `--purple-wash` | `--purple-dark` |

  Admin 还有约 20 个硬编码色值没有走变量。
- **字体**：两边都是 `"Helvetica Neue", Helvetica, Arial, sans-serif`。字号、字重没有统一阶梯，大标题、指标数字、正文之间的层级靠每处单独定义。
- **断点杂乱**：Admin 用了 1180、1100、1050、900、700、600 等 6 个以上断点，还有几个区间查询；会员端用 1050、760。
- **CSS 难维护**：`styles.css` 约 50KB，大部分写在很长的单行里。
- **信息密度不均**：Optimize 页面桌面整页约 7,000px 高，手机约 10,000px；Forecast 约 1,700px。Optimize 是信息架构要重点处理的页面。
- **两个站点风格不统一**：Admin 顶部是紫色整条页头；会员端是白底页头加紫色 hero。是否保持不同风格，见 §4 待定事项。

### 3.3 smoke 测试基线

在云端环境实测（Playwright + 本地 Chromium，后端端口 8000）：

| 测试 | 结果 | 备注 |
|---|---|---|
| `smoke.mjs`（含 `--transactions`） | 通过 | |
| `smoke-continuous.mjs` | 通过 | 默认端口写成了 8765，要设 `APP_URL=http://127.0.0.1:8000` |
| `smoke-contribution.mjs` | 通过 | |
| `smoke-demand-filter.mjs` | 通过（已修） | 原先不稳定：切换轮次会发两次预测请求（Forecast 页面和 Manage offers 表单各一次），测试只等到第一次就记下计数，第二次晚到被误算成过期请求。已改为等请求停止后再比较，点击 D7 后也同样等待，让这条检查真正能抓到过期请求 |
| `smoke-english-journey.mjs` | 通过（已修） | 原先总是失败：点击导航后地址已变成 `#members`，但页面要等 `hashchange` 之后才切换，测试检查得太早。已改为等表单出现后再断言 |
| `smoke-flexible-search.mjs` | 通过 | |
| `smoke-flight-offers.mjs` | 通过 | |
| `smoke-member-portal.mjs`（含 `--real`） | 通过 | |
| `smoke-optimization.mjs` | 通过 | |
| `smoke-price-chart.mjs` | 通过 | |
| `smoke-route-catalog.mjs` | 通过 | |
| `smoke-seat-supply.mjs` | 通过 | |
| `test-seat-status.mjs` | 通过 | |

修复后 13 个测试全部通过，每个修过的测试连续跑 8 次都通过。重构的标准是：每次改动后 13 个保持全部通过。

---

## 4. 设计系统

> 待定。方向和参考风格等用户确认后再填。

规划的结构：

- **token 单一来源**：新建两个站点共用的 `frontend/tokens.css`，在 `:root` 定义颜色、字体、字号阶梯、间距、圆角、阴影、断点相关的值。数值只写在 CSS 里，本文档只写每个 token 的用途和使用规则。
- **颜色**：品牌紫、品牌青、白，加上从它们推出的中性色、状态色（成功、警告、错误）和图表色。所有文字色和背景色组合要满足对比度要求。
- **字体**：系统字体栈或自托管字体（二选一，待定）；数字使用等宽数字（`font-variant-numeric: tabular-nums`）。
- **字号与间距**：固定阶梯，不写零散数值。
- **组件**：按钮、输入框、选择框、指标卡、表格、标签页、折叠区、对话框、提示条、空状态、加载状态、图表。
- **布局**：统一的内容宽度、栅格和 2～3 个断点。

待确认：

- Admin（分析工具）和会员端（消费者订票）用同一套组件不同密度，还是两种风格？
- 视觉参考或想要的感觉。

---

## 5. 信息架构

> 待定。每个页面的调整方案先写在这里，和用户确认后再动代码。

已知重点：

- Optimize 页面过长，设置、进度、结果、参考工具混在一页。
- Experiments 下的 Customer panel 和 Shared market 用页内二级导航切换。
- `#pricing` 旧价格对比只能从 Optimize 底部的链接进入。

---

## 6. 决策记录

按时间追加，写明决定和原因。

| 日期 | 决定 | 原因 |
|---|---|---|
| 2026-11-14 | 重构范围包括视觉、排版、字体、信息架构和布局；功能、接口、数据含义不变 | 用户确认 |
| 2026-11-14 | 保留品牌色紫 `#6F2C91`、青 `#24BCDC`、白 | 用户确认 |
| 2026-11-14 | 冻结清单写成 `frontend/ui-contract.json` 并用 `tests/test_frontend_contract.py` 检查 | 只写在文档里挡不住重排时误删 JS 依赖的元素 |
| 2026-11-14 | 不引入前端框架和构建步骤，字体不走 CDN | 项目要求后端直接提供静态文件、离线可用；换框架等于重写功能 |
| 2026-11-14 | 文档用简体中文 | 用户确认 |
| 2026-11-14 | 先修好两个不可靠的 smoke 测试，再动 UI | 重构要靠测试判断有没有改坏，测试本身必须可靠 |
| 2026-11-14 | 主要受众是评委；演示主线 Forecast → Optimize → Manage offers → 会员端；Experiments 是辅助证据；说明文字默认收起 | 用户确认（§0） |

---

## 7. 进度与问题

记录当前做到哪一步、遇到的问题和处理状态，方便别人接手。完成的条目保留，标注日期。

### 7.1 进度

| 日期 | 步骤 | 状态 |
|---|---|---|
| 2026-11-14 | 建立冻结清单（`ui-contract.json` + 契约测试）、写本文档、截取重构前截图 | 完成 |
| 2026-11-14 | 修复 `smoke-demand-filter`、`smoke-english-journey` 的时序问题（只改测试的等待方式，未改产品代码） | 完成 |
| 2026-11-14 | 确认设计目的与受众（§0） | 完成 |
| — | 确定设计方向（视觉参考、两个站点是否统一风格） | 暂缓，等用户提供参考 |
| — | 设计系统：共用 `tokens.css`、字体、字号与间距阶梯、组件 | 未开始 |
| — | 信息架构：先从 Optimize 页面写方案（§5） | 暂缓，用户决定先不动 |

### 7.2 已知问题

| 发现日期 | 问题 | 状态 |
|---|---|---|
| 2026-11-14 | `smoke-demand-filter`、`smoke-english-journey` 有时序问题 | 已修（2026-11-14） |
| 2026-11-14 | `smoke-continuous.mjs` 默认端口是 8765，其他测试是 8000；不设 `APP_URL` 会连不上 | 未处理 |
| 2026-11-14 | 两个站点的颜色变量数值不一致，Admin 有约 20 个硬编码色值（§3.2） | 留给设计系统阶段处理 |
| 2026-11-14 | 每次切换轮次，Admin 会为 Forecast 页面和 Manage offers 表单各发一次相同的预测请求 | 记录在案；属于功能层面，不在 UI 重构范围内 |
| 2026-11-14 | 基线截图（2.5MB）提交在仓库里，并会被打进 Docker 镜像 | 待用户决定是否改为只提交截图脚本 |
