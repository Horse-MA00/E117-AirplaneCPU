# Demo video（约 50 秒）

用 Playwright 录真实页面，用 HyperFrames 加镜头、光标、字幕、配音和结尾动画，输出 1920×1080 MP4。UI 改动后重跑一遍即可得到与最新界面一致的视频。

用于 5 分钟路演的 demo 段：前面的幻灯片已讲问题和方案，视频只演示 Admin 端和会员端怎么用；之后接 Benefits 幻灯片。视频内全部用英文。

## 分镜脚本

航班：HKG → Fukuoka（`SYN-00017`），D7。Optimize 打开仓库里已保存的 Thompson 实验 DEMO_LLM0（不用现场计算）：推荐会员基本票价 HK$229（正常票价 HK$690），独立验证面板上比无优惠多 +HK$2,589.23 加权收入。
旁白原文在 [`narration.json`](narration.json)（`caption` 是字幕，`say` 是 TTS 读的文字），这里只列要点。时间以录制结果为准。

| 时间 | 画面 | 镜头与操作 | 旁白 |
|---|---|---|---|
| 0–11s | Forecast seats，已选好航班和 D7 | 全画面 → 推近座位条（已订 81 / 保护 41 / 可放 58）→ 推近 "New seats releasable today 58 seats" → 点击 "Optimize this release round" | forecast |
| 11–25s | Optimize prices（`/adaptive-pricing`） | 全画面 → 推近价格—收入曲线 → 推近 HK$229 → 推近 "vs no offer +HK$2,589.23" → 点击 "Publish at HK$229" | optimize |
| 25–31s | Publish offers | 推近表单，在 Member base fare 里逐字输入 229（右侧预览同步变化）→ Publish member offer → 推近 "Published. Next:"，点击 Open member site | publish |
| 31–42s | 会员端登录和订票 | 点击 "Use member account" → Sign in → 推近航班卡片（HKD 690 划掉 → HKD 229）→ Select flight → Confirm → Booking complete | member |
| 42–49s | Admin 的 Results | 推近 "Member seats sold 1" 和 "Member ticket revenue HK$229" | results |
| 49–52s | 结尾 | 镜头拉远，紫青斜条扫过，停在紫底 UOption Fly Pass Logo 和 "Protect first. Release smart. Price with evidence." | 无 |

镜头规则（用户确认）：每进入一个页面先全画面停一下；点击前**先推近、再移光标**；点击后停在结果上，或平移到结果区域。页面加载的等待时间从视频里剪掉，换页处用短暂的淡入淡出。不显示"合成数据"角标。

## 文件

| 文件 | 作用 |
|---|---|
| `narration.json` | 旁白与字幕、TTS 声音（Kokoro `af_heart`）和语速（1.15） |
| `record.mjs` | 用仓库当前代码另起一个干净的后端（独立 SQLite），用 Playwright 按分镜操作页面并录屏，记录每个动作的时间和元素位置 |
| `build.mjs` | `tts` 生成旁白；`compose` 把录屏帧合成 `screen.mp4` 并生成 HyperFrames 合成页；`render` 输出 MP4 |
| `composition/template.html` | 镜头、光标、点击涟漪、字幕和结尾动画；也支持后期绘制的下拉菜单和快进标记（当前分镜没有用到） |

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
