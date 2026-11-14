# 用 Docker 运行整个项目

容器包含前端、Python API、NHPP、定价、用户模拟、已提交的合成数据与历史实验。
前端是静态文件，由同一个 API 服务提供，因此不需要额外的 Node、Nginx、Redis
或数据库服务。SQLite、实验检查点和缓存放在独立持久化卷。

## 启动

安装并启动 Docker Desktop（Windows 使用 Linux containers；Mac 使用对应 Intel
或 Apple Silicon 版本），或使用 Linux Docker Engine。需要 Docker Compose **2.30+**。

在仓库根目录执行：

```sh
docker compose up --build -d --wait
```

- 管理端：http://127.0.0.1:8000/admin
- 会员端：http://127.0.0.1:8000/members
- 健康检查：http://127.0.0.1:8000/api/health

默认无需 API key；所有购票都是模拟交易。容器以非 root 用户运行，在容器内监听
`0.0.0.0`，但宿主机只发布到 `127.0.0.1`，保留本机演示的 Host/Origin 限制。
这不会增加生产环境的登录、支付或公网部署能力。

所有团队成员运行 Linux 内的 `fcntl`，无需按 Mac/Windows 改写锁实现。
镜像不强制 CPU 架构，Docker 会选择本机的 amd64 或 arm64。基础镜像固定到
多架构摘要，Python 依赖版本固定在 `requirements-docker.lock`；本机的 Python、
NumPy 和换行设置不参与依赖安装。Git 中的 LF 规则仍需保留，以维护冻结模型哈希。

## 可选 API 配置

仅在需要 OAG 或 live LLM 时，将 `.env.example` 复制为 `.env.local` 并填入自己的
凭据。Compose 在运行时读取这个文件；不存在时仍能启动。使用 `format: raw`
保留值里的 `$`，写成不带引号的 `KEY=value`，不使用 shell 插值。

`.env.local`、本机数据库、缓存、虚拟环境、Git 历史、node_modules 和浏览器截图
均不进入构建上下文。默认启动和健康检查不会调用付费 API。不要分享包含展开环境
变量的 `docker compose config` 输出；检查配置只需 `docker compose config --quiet`。

修改凭据后运行 `docker compose up -d --force-recreate app`；单纯 restart 不会重读
Compose 注入的环境变量。修改源码后执行 `docker compose up --build -d --wait`。

## 端口

默认 8000。如果已被占用，在仓库根目录创建一个 Git 忽略的 `.env` 文件：

```dotenv
APP_PORT=18080
```

再启动 Compose，并访问 http://127.0.0.1:18080/admin 。这里的 `.env` 是 Compose
参数，`.env.local` 是可选服务凭据。Compose 自动使用相同的内外端口，以兼容已有
Origin 校验；不需要修改源码。只在 `.env.local` 设置 APP_PORT 不会修改端口映射。

## 数据和停止

```sh
docker compose ps
docker compose logs --tail=100 app
docker compose stop
docker compose start
docker compose down
```

`stop`、`down` 和重建镜像都保留 `app-data` 命名卷（默认完整名称
`uoption-fly-pass_app-data`）。卷覆盖 `/app/data/private`，保存会员、订单、库存、
用户面板、价格实验、原始审计和 OAG 缓存。不要同时启动多个 app 副本共享此卷。

重建前应等待实验完成；检查点保留不代表后台任务会自动续跑，按页面提供的续跑或重新运行操作处理。

本机旧 `data/private` **不会自动导入**。Docker 第一次运行是独立的空数据库，
已提交的合成航班和历史实验仍随镜像提供。不同成员机器上的卷也互不共享。

需要删除演示数据、重新开始时才执行 `docker compose down --volumes`；此命令会
删除会员、订单和实验记录。备份数据可先停止应用，再使用 Docker Desktop 的卷
导出功能；恢复后确认容器用户 UID/GID 10001 对数据有读写权限。

## 在容器内测试

无需在宿主机安装 Python：

```sh
docker compose --profile test run --rm --build tests
```

运行 backend 测试、原模拟器测试和所有冻结实验校验，任一失败均返回非零状态。
测试服务没有外网、没有服务密钥、也不挂载演示数据卷；测试数据使用独立临时目录。

对已启动的容器进行实际 HTTP 冒烟测试（会创建模拟会员、订单和两个有限实验）：

```sh
docker compose exec app python scripts/smoke_container.py
docker compose up -d --force-recreate --wait app
docker compose exec app python scripts/smoke_container.py --verify-only
```

非默认端口时在两次 smoke 命令后加入 `--url http://127.0.0.1:18080`。
这会检查两套页面、正常需求预测、发布配额、入会/购票、原生 `fcntl` 用户面板、
连续定价后台作业，以及容器重建后的订单和实验持久化，不调用 LLM。

已有 Playwright 脚本可以通过 `APP_URL` 指向容器，执行桌面和手机布局检查；
浏览器测试属于可选开发工具，普通启动不需要 Node 或 Playwright。

## 容器内执行其他模块

```sh
docker compose exec app python -m backend.evaluate --flight SYN-00001 --day 28
docker compose exec app python -m backend.oag --date 2026-11-15
```

第二条需要你配置 OAG 凭据并消耗配额，只在需要时执行。新实验输出指定到
`data/private/` 下才能在容器重建后保存；已提交的模型、校准和实验应视为冻结资料，
不要在运行容器中覆盖它们。更新依赖应同步修改约束文件并重新运行容器测试。

参考：[Docker Compose 环境变量](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/)、
[服务配置](https://docs.docker.com/reference/compose-file/services/)。

## 本次实际验证（2026-11-14）

- Linux amd64 完整构建，Python 3.11、固定 NumPy/Matplotlib 依赖；132 项 backend
  测试及 19 项模拟器测试全部通过，冻结实验文件校验通过。
- 管理端、连续定价、会员网站三套 Playwright 检查通过，包含手机布局；浏览器请求
  经宿主机 18080 端口进入真实容器，并完成模拟入会、购票和保存订单。
- 新 HTTP smoke 完成规则用户面板和连续定价；重建 app 并改回 8000 后验证订单、
  会员、已完成面板及定价结果仍在。原本机数据库未导入或修改。
- 镜像内 UID 10001、fcntl 可用；不包含 .env、.env.local、.git、.venv、node_modules、
  浏览器截图或本机数据库。测试服务无外网，没有新增 LLM 或 OAG 请求。
- Linux arm64 镜像构建成功；通过 Docker Desktop CPU 模拟执行的 22 项文件锁、
  HTTP 和连续定价关键测试全部通过。未在实体 Mac 上执行完整回归。

## 新 UI 与联合优化整合

Docker 分支已纳入 main 的 0573d40：新版 Admin/Client Portal、联合票价与会费优化、座位反馈、SQLite 审计。价格—总贡献曲线在 Optimize prices 页下方，保留固定会费的独立实验口径。新联合优化数据库同样位于 data/private，随命名卷持久化；启动方法不变。全部功能仍在一个应用容器中，无需另装 Node 或数据库。

完整测试为 151 项 backend 加 19 项原模拟器测试，共 170 项；amd64 构建及历史实验校验通过。arm64 构建和 14 项 HTTP/初始价格/座位反馈测试通过（模拟环境）。实验执行中不要重建容器；新源码改变 provenance 时旧任务只读，需新建实验，不能混用新旧规则续跑。

新版端到端检查包含六轮联合优化：18 个市场全部完成、零 provider 调用；管理端、会员端、价格曲线和联合优化浏览器检查通过。`scripts/smoke_container.py` 现在还验证联合优化 SQLite 持久化，可用 `--joint-run opt-...` 复用已完成的数学实验，避免重复运行。

本次整合期间 main 又更新到 1b4e98f，Docker 分支一并纳入国家／地区与日期范围搜索。Temporal 兼容 bundle 已随前端静态文件进入镜像，运行时不需要 npm 或 CDN；原生和强制本地 fallback 两条浏览器路径均通过，会员模拟购票回归通过。

## Apple Silicon 本机实际运行（2026-11-14）

本次从 `6ee01e5` 快进拉取 GitHub main 到 `db2ca0d`，然后在实体 Mac 的 Docker
Desktop 中完成原生 Linux **arm64** 构建和完整运行验证，不依赖 amd64 模拟。
构建镜像为 `uoption-fly-pass:local`，ID 前缀 `a1f22ed1b7b0`；容器用户 UID 为 10001。

本机原有 Python 服务占用 8000，因此 Git 忽略的 `.env` 保存 `APP_PORT=18080`：

- Admin：http://127.0.0.1:18080/admin
- Client：http://127.0.0.1:18080/members
- Health：http://127.0.0.1:18080/api/health

`docker compose up --build -d --wait --wait-timeout 180` 成功，容器
`uoption-fly-pass-app-1` 为 healthy。之后在项目目录使用普通 `docker compose`
命令即可沿用此本机端口；其他机器仍按自己的 `.env` 或默认 8000 运行。

验证结果：

- 隔离测试服务：151 项 backend、19 项原模拟器测试全部通过，冻结数据／历史实验校验通过。
- 容器实际 HTTP：NHPP、发布会员配额、模拟入会／购票、4 人规则面板、连续定价、
  3 轮联合数学优化全部完成；provider calls 为零。
- Chrome 157 经 18080 访问真实容器，Admin、会员界面、38 航点／日期搜索和价格收益图
  四套浏览器检查通过，包含 390px 手机布局。会员和航点特殊状态使用隔离 fixtures。
- HTTP smoke 完成后执行 `docker compose up -d --force-recreate --wait app`，再执行
  `docker compose exec -T app python scripts/smoke_container.py --url http://127.0.0.1:18080 --verify-only`，
  原会员、订单、面板、连续定价和联合优化结果均保留。

持久化验证记录在命名卷内的 `data/private/container-smoke.json`；本次联合优化为
`opt-c33af54c87b84089`。卷 `uoption-fly-pass_app-data` 独立于宿主机旧数据，
未自动迁入本机原有的会员、订单或私有实验。已提交的合成数据和历史实验随镜像提供。
API 配置仅由 `.env.local` 在运行时注入；镜像内确认不存在 `.env`、`.env.local`、
`.git`、虚拟环境、node_modules 或浏览器截图。本次无需修改容器化源码。
