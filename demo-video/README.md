# Demo video（约 60 秒）

用 Playwright 录真实页面，用 HyperFrames 加镜头、光标、字幕、配音和结尾动画，输出 1920×1080 MP4。UI 改动后重跑一遍即可得到与最新界面一致的视频。

> **注意**：下面的分镜和 `record.mjs` 是按合并 main **之前**的界面写的（2026-11-14 第一版草稿）。新 Admin（侧边栏、Thompson Optimize、手动输入的 Publish、Results 页）需要重写录制脚本后才能重录，见 [FRONTEND_UI §0.5](../docs/FRONTEND_UI.md)。

用于 5 分钟路演的 demo 段：前面的幻灯片已讲问题和方案，视频只演示 Admin 端和会员端怎么用；之后接 Benefits 幻灯片。视频内全部用英文。

## 分镜脚本

航班：HKG → Hiroshima（`DEMO-HKG-HIJ-20270515`），D28。数学轨、种子 117，结果可重现：建议会员基本票价 HK$370（正常票价 HK$740 的 50%），放 10 座，独立验证增量贡献为正。
旁白原文在 [`narration.json`](narration.json)（`caption` 是字幕，`say` 是 TTS 读的文字），这里只列要点。时间是草稿，以录制结果为准。

| 时间 | 画面 | 镜头与操作 | 旁白（英文） |
|---|---|---|---|
| 0–11s | Forecast seats，已选好 HIJ 航班 | 全画面停留 → 推近四个座位卡片和座位条（预订 66 / 保护 144 / 可放 20）→ 推近按钮，光标点击 "Optimize this release round" | forecast |
| 11–28s | Optimize prices | 全画面 → 推近 Start，点击 → 运行过程快进（约 30 秒压到 2.5 秒，右上角显示 Fast-forward）→ 滚动到价格—贡献曲线，推近，光标悬停最佳点 HK$370（虚线是无优惠基准）→ 滚动到 Final recommendation，点击 "Use these prices" | optimize-run、optimize-result |
| 28–35s | Manage offers | 全画面 → 推近建议和已填好的 10 座 / HK$370 → 点击 "Publish member offer" → 滚动到已发布列表（10 unspent quota） | publish |
| 35–47s | 会员端 `/members` | 全画面 → 推近搜索框，Destination 下拉框选 Japan（弹出菜单为后期绘制，选项文字取自真实页面）→ Search → 结果卡片 → Select flight → Join pass · HKD 399 → Confirm booking · HKD 620 → Booking complete | member-search、member-book |
| 47–54s | 切回 Admin 的 Manage offers | 点击 "Refresh inventory"，推近已发布列表：10 → 9 unspent quota | closing |
| 54–57s | 结尾 | 镜头拉远，紫青斜条扫过，停在紫底 UOption Fly Pass Logo 和 "Protect first. Release smart. Price with evidence." | 无 |

镜头规则（用户确认）：每进入一个页面先全画面停一下；点击前**先推近、再移光标**；点击后停在结果上，或平移到结果区域，再拉回全画面。不显示"合成数据"角标。

## 文件

| 文件 | 作用 |
|---|---|
| `narration.json` | 旁白与字幕、TTS 声音（Kokoro `af_heart`） |
| `record.mjs` | 用仓库当前代码另起一个干净的后端（独立 SQLite），用 Playwright 按分镜操作页面并录屏，记录每个动作的时间和元素位置 |
| `build.mjs` | `tts` 生成旁白；`compose` 把录屏帧合成 `screen.mp4` 并生成 HyperFrames 合成页；`render` 输出 MP4 |
| `composition/template.html` | 镜头、光标、点击涟漪、下拉菜单、字幕、快进标记和结尾动画 |

产出都在 `out/`（已被 Git 忽略）。录制使用独立的临时数据库，不会改动 `data/private/`。

## 运行

需要 Node.js 22+、ffmpeg、Python 3（numpy）。第一次运行：

```bash
cd demo-video && npm ci
```

```bash
python3 -m venv out/venv && out/venv/bin/pip install kokoro-onnx soundfile
```

之后每次重录：

```bash
cd demo-video && npm run all
```

`npm run all` 依次执行 `tts`、`record`、`compose`、`render`，最终文件是 `out/uoption-demo.mp4`。只改了旁白文字时也要重跑 `record`，因为每段操作的节奏跟着旁白时长走。

背景音乐：把团队选好的无版权曲目放在 `assets/music.mp3`（或 `.wav`）后重跑 `compose` 和 `render`，会以低音量铺在旁白下面；没有这个文件就不加音乐。

Chromium：默认使用 Playwright 自带的浏览器；如需指定，设置环境变量 `CHROMIUM_PATH`。
