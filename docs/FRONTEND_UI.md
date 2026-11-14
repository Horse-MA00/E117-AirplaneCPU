# 前端 UI 规格

> 状态：现行 · 对应代码：`frontend/ui-contract.json`、`frontend/admin-shell.css`、`frontend/styles.css`、`frontend/adaptive-pricing.css`、`frontend/members/portal.css`、`tests/test_frontend_contract.py`

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
2. Optimize：在可释放的座位上，用 Thompson Sampling 找会员基本票价，并用独立的模拟旅客验证（结论也可能是保留初始价或不放票）。
3. Manage offers：管理员确认并发布。
4. 会员端：旅客看到这个优惠并完成订票，库存和账目同步变化。

**Experiments 是辅助证据，不在主线上。** 2026-11-15 起它只展示"What members said"：Thompson 实验每一轮里模拟会员（离线模型或 LLM 扮演）的购买和拒绝理由，只读。旧的 Customer panel 和 Shared market 已被队友删除。

**会员端是展示品**，但它和 Admin 共用库存与账目。这个闭环本身就是演示的亮点。

### 0.3 由此推出的设计原则

1. **每屏一个主结论**：评委在 15 秒内能看懂的大数字或一句话，放在最显眼的位置。
2. **解释默认收起**：数据口径、公式、假设这类说明保留（评委提问时要用），但默认折叠或放到次要位置，不能挤占主结论。文字含义不变。
3. **适合投影**：字号够大、对比度够高，不靠小字和细线传达关键信息。
4. **演示不等待**：现场不能等优化或 LLM 跑完。演示路径要能直接打开已保存的结果（这个功能已有，信息架构要让它容易找到）。
5. **闭环看得见**：发布 → 会员端出现 → 订票后库存减少，这条链在画面上要清楚。
6. **诚实标注保留，但要轻**："合成数据""模拟"这类标注用统一的小标签，不用满屏说明文字。

### 0.4 待确认

- ~~现场操作演示，还是播放录屏？~~ 倾向**播放录屏**，可以控制时长并配音（用户 2026-11-14）。制作方式见 §0.5。
- ~~投影或屏幕分辨率？~~ 未知，按普通电视的 **16:9** 设计，以 **1920×1080** 视口为主要验收尺寸。
- Experiments 会在 demo 里出场，还是只在 benefits 或问答环节引用？（建议不进 demo）

### 0.5 演示视频的做法（提议，待确认）

Claude 模型不能直接生成视频或语音，但可以写程序把真实界面录成视频：

1. 用 Playwright 按演示脚本自动操作真实页面（1920×1080），录下画面。每次 UI 修改后可以重新生成，画面和最新代码一致。
2. 用 ffmpeg 剪辑：控制每个画面的停留时间、放大重点区域、加字幕。
3. 配音由团队成员录制（或另行使用 TTS 服务，需要账号和 API key），再合成进视频。

不用文生视频模型直接"画"界面：它会编造不存在的画面，评委看到的就不是真实产品了。

---

## 1. 重构规则

### 1.1 冻结的部分

下面这些在重构中**不能改变行为**。机器可检查的清单在 `frontend/ui-contract.json`，由 `tests/test_frontend_contract.py` 检查。

| 冻结内容 | 说明 | 检查方式 |
|---|---|---|
| 功能 | 每个页面现有的操作、状态和结果都要保留；可以换位置、换形式，不能删 | smoke 测试 + 截图对比 |
| 接口 | 浏览器调用的 19 个 API 端点、方法和请求字段（见 §2.2 和 `ui-contract.json`） | 契约测试：JS 里出现的 `/api/...` 必须和清单一致 |
| 数据含义 | 页面上每个数字的口径和文案含义（如"Protected for normal demand"） | 人工审查 |
| 跨模块事件 | `uoption:view` | 契约测试 |
| URL 与存储 | Admin 的 hash 路由、Optimize 的网址参数、会员端 `localStorage['uoption-member-demo-account']`（见 §2.3） | smoke 测试 |
| DOM 钩子 | JS 或 smoke 测试引用的 id：Admin 74 个、Optimize 74 个、会员端 53 个；以及 JS 用到的选择器和 class（见 `ui-contract.json` 的 `js_selectors`） | 契约测试：id 必须仍在 HTML 中 |

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
2. 启动后端后，§3.3 列出的 10 个 smoke 测试全部通过，`scripts/check_container.py` 通过。
3. 与 `docs/frontend-ui/baseline-2026-11-15/` 截图对比，确认没有丢失功能入口。
4. 改了设计系统或信息架构，就同步更新本文档 §4、§5，并在 §6 记一条。

---

## 2. 冻结清单（2026-11-15 合并 main 后）

2026-11-15 合并了 main 上队友的改动：Optimize 改用 Thompson Sampling 并移到独立页面 `/adaptive-pricing`；旧的数学轨定价、全期连续定价、Customer panel、Shared market、六阶段旅程及其页面、脚本、测试全部删除。下面是合并后的现状，`frontend/ui-contract.json` 已同步重建。2026-11-14 的旧清单见 git 历史。

### 2.1 页面与路由

| 页面 | 文件 | 路由 | 机制 |
|---|---|---|---|
| Admin `/admin`（`/` 相同） | `index.html`；脚本 `app.js`、`experiments.js`，依赖 `seat-status.js`、`demand-filter.js`、`thompson-navigation.js` | `#flights` Forecast seats、`#customers` Experiments（What members said）、`#members` Manage offers | `location.hash` 选中 `section#view-<route>.view`。退役的 `#optimization`、`#pricing`、`#panel`、`#market` 显示 `#view-unavailable`，不跳转 |
| Optimize `/adaptive-pricing` | `adaptive-pricing.html`、`adaptive-pricing.js`、`adaptive-pricing.css` | 无 hash；网址参数 `flight_id`、`forecast_day`、`run`、`round` | 独立页面，有自己的页头和导航 |
| 会员端 `/members` | `members/` | `#flights`、`#membership`、`#trips`、`#account` | 长页面锚点；`dialog#checkout` 订票弹窗。**本次不改** |

### 2.2 每个页面的功能与接口

| 页面 | 功能 | 接口 |
|---|---|---|
| 公共 | 数据集标签、LLM 是否已配置 | `GET /api/summary`、`GET /api/flights` |
| Forecast | 需求档位筛选、航班选择、D28/D14/D7/D1、四个座位指标、座位分配条、正常预订与票价图、去 Optimize（带航班和轮次） | `GET /api/flights/{id}`、`POST /api/forecast` |
| Optimize | 航线、航班、放票轮次；顾客决策来源（离线模拟 / Live LLM）；轮数、每轮人数；折叠的客群权重、并行数、调用上限、种子、验证批数；开始实验；已保存实验选择；进度；建议票价（含尾数 9 的最终宣传价）；逐轮表；价格与预期收入曲线；独立验证（对比初始价和不放票）；导出；去 Experiments 看会员回馈 | `GET /api/adaptive-pricing/status`、`POST /api/adaptive-pricing/scope`、`GET/POST /api/adaptive-pricing/runs`、`GET /api/adaptive-pricing/runs/{id}`、链接 `…/{id}/export` |
| Experiments | 选择已保存实验和轮次，阅读该轮摘要和每位会员的购买 / 拒绝理由；只读，不发起调用 | `GET /api/adaptive-pricing/runs`、`GET /api/adaptive-pricing/runs/{id}`、链接 `…/{id}/export` |
| Manage offers | 手动选择航线、航班、轮次，输入座位数和会员票价并发布（后端核对当前配额和 80% 上限）；去 Optimize 优化这班航班；设置会费；已发布优惠列表 | `POST /api/forecast`、`GET/POST /api/offers`、`GET/POST /api/member-portal/plan` |

### 2.3 页面之间的联系、URL 与存储

| 名称 | 作用 |
|---|---|
| `uoption:view` 事件 | `app.js` 切换页面后发出，`experiments.js` 在 `#customers` 时读取已保存实验 |
| `/adaptive-pricing?flight_id=&forecast_day=` | Forecast 和 Manage offers 打开 Optimize 时带入航班和轮次（`thompson-navigation.js`） |
| `/adaptive-pricing?run=&round=` | 恢复已保存的实验和轮次 |
| `/admin?run=&round=#customers` | 分享指定实验和轮次的会员回馈 |
| `localStorage['uoption-member-demo-account']` | 会员端演示账号 |

DOM 钩子：Admin 74 个、Optimize 74 个、会员端 53 个 id，见 `ui-contract.json`。

---

## 3. 现状评估（重构前基线）

### 3.1 截图

`docs/frontend-ui/baseline-2026-11-14/` 下有每个页面的整页截图，桌面 1440px 和手机 390px 各一张，另有会员端订票弹窗。截图时库里有一条已发布的演示优惠和一笔模拟订单。

合并 main 后的新基线在 `docs/frontend-ui/baseline-2026-11-15/`：Forecast、Optimize（`/adaptive-pricing`）、Experiments、Manage offers 和退役路由提示页，桌面 1920×1080 和手机 390px。2026-11-14 的旧基线保留，用来对照旧版。

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

### 3.3 smoke 测试基线（2026-11-15 合并后）

main 删除了 `smoke-continuous`、`smoke-contribution`、`smoke-english-journey`、`smoke-price-chart`，新增 `smoke-adaptive-pricing`。合并后在云端实测 10 个浏览器测试**全部通过**：`smoke`、`smoke-adaptive-pricing`、`smoke-demand-filter`、`smoke-flexible-search`、`smoke-flight-offers`、`smoke-member-portal`、`smoke-optimization`、`smoke-route-catalog`、`smoke-seat-supply`、`test-seat-status`。`scripts/check_container.py`（后端 182 项、根目录 24 项、发布与证据检查）也全部通过。

`smoke-demand-filter` 保留了 2026-11-14 加入的"等预测请求全部返回再计数"，修复了原先的时序问题。

重构的标准：每次改动后这 10 个测试和 `check_container.py` 保持全部通过。

---|---|---|
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

范围：**先只做 Admin**。会员端暂不改，以后单独讨论；届时沿用会员端现在的字体（`"Helvetica Neue", Helvetica, Arial, sans-serif`），视觉方向倾向样板 A"数据叙事"。两端分开设计，只共用品牌色。

### 4.1 Admin 方向

- **风格**：现代 SaaS 工具（样板 B）。高效、清晰：左侧导航、指标卡、细边框卡片、克制的层次，结论用紫色主卡突出。
- **字体**：Inter，字体文件放进仓库（`frontend/fonts/`，SIL Open Font License），不走 CDN。数字一律 `tabular-nums`。
- **主题**：只做浅色。投影和录屏都以浅色为准，不做深色模式。
- **画布**：以 1920×1080 为主要验收尺寸；390px 和 768px 仍须无横向滚动（smoke 测试会检查）。
- **语言**：界面只有英文，以后再考虑其他语言。

### 4.2 文件与 token（2026-11-15 已实现）

| 文件 | 内容 |
|---|---|
| `frontend/admin-shell.css` | Admin 和 Optimize 共用：Inter 字体、token、左侧边栏、顶部航班选择栏、页头、卡片、按钮、表单、提示、折叠区、表格 |
| `frontend/styles.css` | Admin 页面内容（Forecast、Publish、Results、Member feedback） |
| `frontend/adaptive-pricing.css` | Optimize 页面内容（结果、实验设置、图表、验证） |
| `frontend/fonts/` | Inter 400/500/600/700 的 woff2（拉丁字符，共约 96KB）和 `OFL.txt` 授权，来自 `@fontsource/inter` 5.1.1 |

数值只写在 `admin-shell.css` 的 `:root` 里，这里只写用途：

| token | 用途 |
|---|---|
| `--purple`、`--purple-dark`、`--purple-hover`、`--purple-wash`、`--purple-line` | 品牌紫：主按钮、选中状态、主结论卡；浅紫作选中背景 |
| `--cyan`、`--cyan-ink`、`--cyan-wash` | 品牌青：强调线、图表区间；`--cyan-ink` 用于需要对比度的文字和已发布座位 |
| `--ink`、`--ink-2`、`--muted`、`--faint` | 正文、次要文字、说明、最弱的标签 |
| `--line`、`--line-2`、`--field-line`、`--ground`、`--card` | 分隔线、输入框边框、页面底色、卡片底色 |
| `--ok`、`--warn`、`--bad`（及 `-wash`） | 状态色，和品牌色分开 |
| `--seat-*` | 座位分配条：已订、保护、会员可放、已发布、暂扣 |
| `--fs-*` | 字号阶梯：12 / 13.5 / 15 / 17 / 19（h2）/ 34（h1）/ 52（大数字） |
| `--space-*`、`--r-*` | 间距 4–40px；圆角 8 / 10 / 14px |
| `--sidebar`、`--bar`、`--gutter` | 侧边栏 272px、顶部选择栏 104px、页面左右留白 48px（窄屏 32 / 20px） |

断点：1300px（指标卡变两列）、1100px（首屏两栏变一栏、选择栏换行）、900px（侧边栏变成顶部横向导航）、700px（手机布局）。

---

## 5. 信息架构（Admin）

结构：**首屏结论 + 下方细节**（样板 E）。每个页面在 1920×1080 的第一屏里只放：结论（大数字或一句话）、最关键的一张图、去下一步的按钮。图表、明细表、口径说明放在下方，说明默认折叠。

2026-11-15 按合并后的代码修订：Optimize 是独立页面 `/adaptive-pricing`，旧工具已删除，Experiments 只剩会员回馈。

### 5.1 导航

Admin（`index.html`）和 Optimize（`adaptive-pricing.html`）使用**同一个左侧边栏外壳**：

| 分组 | 页面 | 地址 | 说明 |
|---|---|---|---|
| Release workflow | 1 Forecast seats | `/admin#flights` | 现有 |
| | 2 Optimize prices | `/adaptive-pricing` | 现有，独立页面 |
| | 3 Publish offers | `/admin#members` | 现有 Manage offers，只改显示名 |
| | 4 Results | `/admin#results` | **新增**，见 §5.3 |
| Evidence | Member feedback | `/admin#customers` | 现有 Experiments（What members said），只改显示名 |

侧边栏底部：数据集标签、LLM 是否已配置、"Open member site"。原来的"Reference tools"分组取消，因为旧工具已删除。退役路由的提示页（`#view-unavailable`）保留。

### 5.2 共用的航班选择器

页面顶部一条"当前航班"栏，在 4 个流程页面共用：需求档位 → 航线 → 航班 → 轮次（D28 / D14 / D7；Forecast 另可看 D1）。Member feedback 页面不显示这条栏。

- 在 Admin 的三个 hash 页面之间切换时，选择保存在页面状态里。
- 去 Optimize 和从 Optimize 回来时，用已有的网址参数 `flight_id`、`forecast_day` 传递（`thompson-navigation.js` 已支持）。
- 它替换现有的三套选择器：Forecast 的 `#forecast-demand`、`#flight-select`、`[data-day]`；Optimize 的 `#route`、`#flight`、`#release-day`；Manage offers 的航线 / 航班 / 轮次。这是本次重构里**唯一改变 JS 行为**的地方，要同步修改 `ui-contract.json` 和相关 smoke 测试，并在 §6 记录。

### 5.3 每页第一屏

| 页面 | 第一屏 | 下方 / 折叠 |
|---|---|---|
| 1 Forecast | 主卡：今天可放给会员的座位；3 张小卡：已售、保护、已发布；座位分配条；按钮 "Price these N seats →" | 正常预订图、票价图；折叠：保护座位的计算、正常销售基线 |
| 2 Optimize | 打开时**默认显示这班航班最近一次已保存的 Thompson 实验**。主卡：保留的会员票价（尾数 9 的最终宣传价）和结论（采用新价 / 保留初始价 / 不放票 / 无法判断）；小卡：对比初始价的收入变化、对比不放票的收入变化、会员购买人数；价格与预期收入曲线。按钮 "Publish at HK$xxx →"；次要按钮 "New experiment" 和已保存实验选择。没有已保存实验时，第一屏显示设置表单 | 逐轮结果表、独立验证明细、曲线数值；实验设置（有结果时折叠）；导出；"Read member feedback" |
| 3 Publish | 发布表单（座位数、会员票价，**手动输入**）、旁边显示这班航班最近一次 Thompson 结果作为参考、"会员会看到的样子"预览卡；按钮 "Publish"；发布后显示 "Open member site"（同一标签页打开） | 已发布优惠列表；会费设置 |
| 4 Results | 会员已售座位、剩余配额、会员机票收入（已售座位 × 会员票价，**不含会员费**，税费另列）；每条优惠一行；更新后的座位分配条 | 每条优惠的明细 |
| Member feedback | 实验和轮次选择、该轮摘要；会员理由列表 | 下载 |

Publish 的会员票价保持**手动输入**：`AGENTS.md` 规定"Manage offers 手动选择航班／轮次、输入价格与数量……实验不自动发布优惠"。页面只把 Thompson 结果作为参考显示，不自动填入。若要加"一键带入"，需和队友确认后再做。

### 5.4 演示闭环

Publish → 在同一标签页打开会员端 → 会员订票 → **用浏览器的"后退"回到 Admin** → 看 Results。会员端不加返回按钮。Results 页在 `pageshow`（含从浏览器缓存恢复）和 `hashchange` 时重新读取 `/api/offers`，保证回来时数字已更新。收入只用 `/api/offers` 里已有的 `quantity`、`remaining`、`base_fare`、`fees` 计算，不加新接口。

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
| 2026-11-14 | 演示倾向用录屏视频；按 16:9、1920×1080 设计和验收；基线截图保留 | 用户确认 |
| 2026-11-14 | 改版幅度：换一套视觉语言，品牌色不变；Admin 与会员端同一品牌、两种密度；不做一页看全的仪表盘 | 用户确认 |
| 2026-11-14 | 设计方法参考开源的 garden-skills `web-design-engineer`（改版协议、风格配方、反俗套清单），只借方法，不引入其 React/CDN 技术栈 | 与本项目的无框架、离线约束一致 |
| 2026-11-14 | **推翻"同一品牌、两种密度"**：Admin 和会员端分开设计，只共用品牌色。Admin 要高效清晰，会员端要简单直观 | 用户确认；两端目的不同 |
| 2026-11-14 | 先只做 Admin；会员端暂不改，以后沿用其现有字体 | 用户确认 |
| 2026-11-14 | Admin：SaaS 工具风格（样板 B）+ 首屏结论加下方细节（样板 E）；Inter 字体放进仓库；只做浅色；界面只有英文 | 用户确认 |
| 2026-11-14 | Admin 新增第 4 页 Results；通过浏览器后退从会员端回来；收入只算会员机票收入，不含会员费，不加新接口 | 用户确认 |
| 2026-11-14 | Optimize 默认显示该航班最近一次已保存的结果，"Run again" 是次要按钮；可以换航线 | 用户确认；录屏不用等计算 |
| 2026-11-14 | 4 个流程页面共用顶部的航班选择器；Customer panel、Shared market 放侧边栏 Evidence 分组，旧工具放 Reference tools | 用户确认 |
| 2026-11-14 | 顶部选择栏放大：选择框内"小标签 + 21px 取值"，Release round 加同款框、右移 44px 并与其他框对齐 | 用户确认（样稿第 3 版） |
| 2026-11-15 | 合并 main：Optimize 改为 Thompson 独立页面；旧定价、Customer panel、Shared market、六阶段旅程删除；`ui-contract.json` 改为覆盖 3 个页面 | 队友改动，用户要求同步 |
| 2026-11-15 | 侧边栏 Evidence 只剩 Member feedback（`#customers`），取消 Reference tools；侧边栏外壳同时用于 `/admin` 和 `/adaptive-pricing` | 旧工具已删除 |
| 2026-11-15 | Publish 的会员票价保持手动输入，只显示 Thompson 结果作参考 | 遵守 `AGENTS.md` 的团队规则；一键带入需另与队友确认 |
| 2026-11-15 | 实现 Admin 重构。共用选择栏去掉了 Publish 自己的 `#offer-route`、`#offer-flight`、`#offer-day`（契约同步删除）；Publish 改为直接跟随选择栏，选择栏变化时立即刷新发布限额，不依赖 Forecast 预测是否成功 | §5.2 的设计；修复了实现中发现的问题：预测失败时发布表单会停在旧轮次 |
| 2026-11-15 | 侧边栏步骤编号用 CSS 生成并设空的替代文字（`content: attr(data-step) / ""`），链接的可访问名称保持 "Optimize prices" 等原文 | 否则读屏和测试会读成 "2Optimize prices" |
| 2026-11-15 | Optimize 的放票轮次改为与 Admin 相同的按钮；原 `#release-day` 下拉框保留在页面中但视觉隐藏，由按钮驱动 | 两页选择栏外观一致，同时不改变已有脚本和测试的接口 |
| 2026-11-15 | Optimize 的结果说明（选价理由、尾数 9 规则、候选价格）收进结论卡里的"Why this fare"折叠区；实验进度在有结果时排到图表下方 | §0.3"解释默认收起" |
| 2026-11-15 | 测试同步修改：`smoke-flight-offers` 改用共用选择栏；`smoke-demand-filter` 的 Tab 顺序加入 Route，并放行字体文件；`smoke-adaptive-pricing` 导航数改为 5，折叠区里的说明改读 `textContent` | 都是本次界面改动的直接结果，断言的业务含义不变 |

---

## 7. 进度与问题

记录当前做到哪一步、遇到的问题和处理状态，方便别人接手。完成的条目保留，标注日期。

### 7.1 进度

| 日期 | 步骤 | 状态 |
|---|---|---|
| 2026-11-14 | 建立冻结清单、写本文档、截取重构前截图；修复两个 smoke 测试的时序问题 | 完成 |
| 2026-11-14 | 确认设计目的与受众（§0）；做出 4 种风格和 2 种结构的样板；确定 Admin 方向（§4.1）和信息架构（§5） | 完成 |
| 2026-11-14 | Admin 四个流程页 1920×1080 样稿，顶部选择栏改了两版 | 完成，用户确认 |
| 2026-11-15 | 合并 main（Thompson 改版），重建冻结清单和契约测试，补拍基线截图，按新代码修订本文档 | 完成 |
| 2026-11-15 | 实现 Admin 重构：Inter 与 token、侧边栏外壳（两个页面）、共用航班选择栏、Forecast / Optimize / Publish 首屏、新增 Results 页、Member feedback 换样式 | 完成；10 个浏览器测试和 `check_container.py` 全部通过；在真实服务上走通"发布 → 会员端订票 → 浏览器后退 → Results 显示已售"的闭环 |
| — | 用户验收、按反馈微调 | 进行中 |
| — | 演示视频（§0.5） | 未开始，等 UI 定稿 |
| — | 会员端重构 | 暂缓 |

### 7.2 已知问题

| 发现日期 | 问题 | 状态 |
|---|---|---|
| 2026-11-14 | `smoke-demand-filter`、`smoke-english-journey` 有时序问题 | 已修（2026-11-14） |
| 2026-11-14 | `smoke-continuous.mjs` 默认端口是 8765，其他测试是 8000；不设 `APP_URL` 会连不上 | 不再适用：main 已删除该测试（2026-11-15） |
| 2026-11-14 | 两个站点的颜色变量数值不一致，Admin 有约 20 个硬编码色值（§3.2） | Admin 已改用 `admin-shell.css` 的 token（2026-11-15）；会员端仍是自己的一套，留到会员端重构 |
| 2026-11-14 | 每次切换轮次，Admin 会为 Forecast 页面和 Manage offers 表单各发一次相同的预测请求 | 共用选择栏后仍是两次（Forecast 视图一次、发布限额一次）；结果正确，只是多一次请求，未改 |
| 2026-11-14 | 基线截图（2.5MB）提交在仓库里，并会被打进 Docker 镜像 | 用户决定保留（2026-11-14） |
| 2026-11-14 | 演示主线需要一个能得出"建议放票"（`OFFER`）的航班。实测 HKG→HND（`DEMO-HKG-HND-20270515`）和 HKG→ICN（`NET-HKG-ICN-20270521`）D28 数学轨都是 `NO_OFFER`，否则第 3、4 步无内容可演示 | 2026-11-15 更新：旧数学轨已删除。Thompson 结果总有一个"保留票价"（例如 HKG→KMQ 保留初始价 HK$319），除非结论是不放票，所以第 3、4 步通常有内容可演示；演示航班仍需挑选 |
| 2026-11-14 | 现有接口不能列出所有会员订单（只能按单个账号查），Results 页因此只显示每条优惠的放出、已售、剩余和收入 | 已按此设计样稿 |
