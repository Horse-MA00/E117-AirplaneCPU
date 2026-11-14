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
