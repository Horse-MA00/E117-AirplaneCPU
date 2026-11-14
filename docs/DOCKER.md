# 用 Docker 运行当前项目

> 状态：现行 · 对应代码：`compose.yaml`、`Dockerfile`、`backend/published_experiments.py`、`backend/adaptive_store.py`

容器包含当前 Admin／Client、NHPP 预测、Thompson 票价实验、SQLite、合成航班和当前证据。旧定价与用户场景引擎不再包含在工作树中。前端由 Python HTTP 服务直接提供，不需要额外 Node、Nginx、Redis 或数据库服务。

## 启动

使用 Docker Desktop 的 Linux containers 或 Linux Docker Engine，Compose 2.30+：

```sh
docker compose up --build -d --wait
```

- Admin：http://127.0.0.1:8000/admin
- Thompson：http://127.0.0.1:8000/adaptive-pricing
- Client：http://127.0.0.1:8000/members
- Health：http://127.0.0.1:8000/api/health

默认离线流程不需要密钥。容器以非root用户运行，宿主机端口仅发布至127.0.0.1；这不是生产身份验证、支付或公网部署。Linux容器提供`fcntl`，Windows开发者也可使用同一环境。

### 直接演示 Saved experiments

首次部署、没有`.env.local`及空白`app-data`卷也可打开Optimize prices的Saved experiments：启动时会验证并读取`llm_agent/experiments/*/manifest.json`及对应report／audit。当前包含24个现行v5实验（23完成、1失败），无需先运行优化或复制私人数据库。

- `DEMO_LLM0`–`DEMO_LLM9`：十条航线的真实LLM角色扮演记录，含每轮价格、确认结果和顾客回馈。
- `DEMO_ZERO0`–`DEMO_ZERO2`及三个`DEMO_ZERO_PILOT`：假设低票价／低预算的归零演示。显示HK$0候选与收入验证保留价的区别；不会自动发布免费票。
- 其余历史现行v5实验及一次失败记录也保留，失败记录仍是失败，不会自动继续调用。

从Optimize进入Member feedback可查看保存的理由；Analyst checks可按轮读取原始回覆和错误。浏览、切换轮次和读取审计均不发起LLM/OAG调用。公开目录只读，本机同ID实验优先，列表去重。新实验仍写入私有SQLite并依赖自己的持久卷；查看公开实验不复制全套审计到数据库。

完整索引和报告见[公开实验](../llm_agent/experiments/README.md)。已有部署更新源码后需重建镜像，旧镜像不会自动获得新报告。损坏或缺失的公开证据应修复后重新部署，不能以空白列表掩盖发布不完整。

镜像支持amd64／arm64，Python依赖固定在`requirements-docker.lock`。保留仓库LF规则，避免改变冻结模型或证据哈希。

## 可选配置

需要已授权的live LLM或OAG时，在忽略的`.env.local`配置自己的凭据；可参考`.env.example`。默认启动及健康检查不调用付费API。Compose使用`format: raw`；不要将展开环境变量的`docker compose config`输出发送给别人。只检查配置可用`docker compose config --quiet`。

修改凭据后需重新创建app以读取环境；修改代码后重新build：

```sh
docker compose up -d --force-recreate app
docker compose up --build -d --wait
```

若8000被占用，在仓库根目录忽略的`.env`设定`APP_PORT=18080`，然后以该端口访问。`.env`用于Compose参数，`.env.local`用于服务凭据。

## 持久化

`app-data`命名卷覆盖`/app/data/private`，保存示例会员、订单、库存、当前Thompson实验及私有缓存。停止、普通down或重建镜像保留该卷；不要同时启动多个app副本共享它。实验执行中不要重建服务。

```sh
docker compose ps
docker compose logs --tail=100 app
docker compose stop
docker compose start
docker compose down
```

本机`data/private`不会自动导入新容器。已提交的公开v5报告随源码自动出现在Saved experiments；NHPP证据及合成航班也随源码提供。账户、订单、已发布优惠及未导出的新实验只存在各自私有卷，不会由公开报告还原。成员机器的卷互不共享。

仅在明确要清空全部示例记录时才使用`docker compose down --volumes`；它会删除会员、订单及实验。可先停止应用，用Docker Desktop导出卷备份；恢复时核对UID/GID10001的读写权限。

## 检查

```sh
docker compose --profile test run --rm --build tests
```

测试入口与本机`python scripts/check_container.py`相同，检查当前后端、数据、文档及证据。测试服务不挂载演示数据卷，不注入服务密钥且无外网。当前清理的实际验证以[维护记录](ITERATION_2_PROGRESS.md)为准，不沿用已删除工具的旧Docker测试数量。

可选Playwright通过`APP_URL`指向容器；普通使用无需安装Node。当前页面与浏览器命令见[frontend说明](../frontend/README.md)。本次维护按项目要求使用原生环境测试，没有重新启动Docker。
