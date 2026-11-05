# 买车决策小程序 · 后端（FastAPI）

车型价格检索增强 + 购车费用测算 + 可负担性评估。

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows（CMD）；Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env            # 填入密钥启用实时价格（见下方"LLM 后端与检索源"）
python -m uvicorn app.main:app --reload --port 8000
```

- API 文档（Swagger）：http://localhost:8000/docs
- 健康检查：GET /health

---

## 本地启动后端服务（详细步骤）

### 1. 准备环境（首次）
```bash
cd miniapp-backend
python -m venv .venv
```

### 2. 安装依赖
```bash
# 仅本地开发只需 requirements.txt（含 fastapi/uvicorn/pydantic/httpx/pytest）
pip install -r requirements.txt
# requirements-prod.txt 只含 gunicorn，仅服务器 Linux 部署用，Windows 装不上，本地无需装
```

### 3. 配置密钥
```bash
cp .env.example .env
# 编辑 .env，至少填 DOUBAO_API_KEY 才能走实时联网取价；不填则自动走离线 Mock 兜底
```

### 4. 激活虚拟环境并启动
> ⚠️ **Git Bash / WSL 用户注意**：反斜杠 `\` 会被 bash 当作转义符吃掉。
> 请用 `source` + 正斜杠，不要直接敲 `.venv\Scripts\activate`。

```bash
# Git Bash / Linux / macOS（推荐写法）
source .venv/Scripts/activate        # Windows 用这一行
# source .venv/bin/activate          # Mac/Linux 用这一行

# 启动（带 --reload，改 .py 文件自动热重启）
python -m uvicorn app.main:app --reload --port 8000
```

看到下面两行即启动成功：
```
INFO: Application startup complete.
Uvicorn running on http://127.0.0.1:8000
```

### 5. 验证服务
- 浏览器打开 http://localhost:8000/docs （Swagger 在线调试）
- 或访问 http://localhost:8000/health

---

## 改代码后如何重启

- **改了 `.py` 文件**：启动时带了 `--reload`，uvicorn 会自动监听并热重启，**无需手动操作**。
  终端出现 `INFO: Reloading...` 即已重载，直接刷新/重新调接口即可。
- **改了 `.env`**：`.env` 在启动时读入内存，不会触发 `--reload`，**必须手动重启**：
  在运行 uvicorn 的终端按 `Ctrl+C` 停掉，再重新执行上面的 `python -m uvicorn ...` 命令。
- **彻底重来**：`Ctrl+C` 停掉 → 重新 `source .venv/Scripts/activate` → 重新启动命令。

### 端口 8000 被占用（Address already in use / [Errno 10048]）
通常是上一次 uvicorn 没真正退出。先结束占用进程再启动：
```bash
# 查占用 8000 的 PID
netstat -ano | findstr :8000
# 假设查到 PID 是 12345，结束它
taskkill /PID 12345 /F
```

### 常见启动失败原因
| 现象 | 原因 | 解决 |
|---|---|---|
| `command not found: .venvScriptsactivate` | Git Bash 下用了反斜杠 | 改用 `source .venv/Scripts/activate`（正斜杠） |
| `No module named uvicorn` | 没激活虚拟环境 / 不在后端目录 | 先 `cd miniapp-backend`，再 `source .venv/Scripts/activate` |
| `Address already in use` | 8000 被旧进程占着 | 见上方 `taskkill` 步骤 |
| 启动后立即退出 / 报错 | 多为 `.env` 缺失或 key 为空、依赖未装齐 | 检查 `.env` 与 `pip install -r requirements.txt` |

## 服务器（远程 Linux）启动与重启

生产用 gunicorn + systemd 守护（完整部署见 `deploy/DEPLOY.md`）。以下假设服务名 `miniapp`、项目目录 `/opt/miniapp-backend`、虚拟环境 `.venv`。

### 0. 从本地连接远程服务器

在**本地终端**（Windows 的 PowerShell / CMD / Git Bash，或 Mac/Linux 终端）执行：

```bash
# 基础 SSH 登录（将 81.70.149.19 换成你的服务器公网 IP；当前项目即 81.70.149.19）
ssh root@81.70.149.19
```
- 首次连接会提示 `Are you sure you want to continue connecting (yes/no/[fingerprint])?`，输入 `yes` 回车即可（只需确认一次）。
- 之后输入服务器 `root` 用户密码（或配置密钥免密）。
- 登录成功后提示符变成 `root@VM-...:/#`，**此后所有命令都在服务器上执行**；想回到本地输入 `exit` 回车。

**指定 SSH 端口（若改过默认 22）**
```bash
ssh -p <端口号> root@81.70.149.19      # 注意 ssh 端口是小写 -p
```

**使用密钥文件登录（免密码）**
```bash
ssh -i ~/.ssh/id_rsa root@81.70.149.19
```

**用 scp 上传 / 下载文件（仍在本地终端执行，不是服务器里）**
```bash
# 上传单个文件到服务器 /opt 目录
scp /本地/路径/file root@81.70.149.19:/opt/

# 上传整个目录（如 H5 构建产物、后端代码），-r 表示递归；末尾 /. 表示目录内容
scp -r /本地/路径/dist/build/h5/. root@81.70.149.19:/opt/miniapp-h5/

# 指定端口时用大写 -P（与 ssh 的 -p 不同，别搞混）
scp -P <端口号> -r /本地/目录 root@81.70.149.19:/opt/

# 从服务器下载文件到本地
scp root@81.70.149.19:/opt/miniapp-backend/.env /本地/路径/
```
> ⚠️ scp 的端口参数是**大写 `-P`**，ssh 的是小写 `-p`，极易混。

**服务器直连 GitHub 拉代码失败的替代**
服务器连 GitHub 常报 `GnuTLS recv error (-110)`（网络被 reset）或 `Permission denied (publickey)`（SSH 未配）。绕过方式：本地 `scp` 直传代码、或用国内镜像 `https://gitclone.com/github.com/...`。完整排查见 `deploy/DEPLOY.md`（服务器拉 GitHub 失败）。

### 首次启动（做成开机自启服务）
先手动验证 gunicorn 能起，再做成 systemd 服务：
```bash
cd /opt/miniapp-backend
source .venv/bin/activate
gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 127.0.0.1:8000 app.main:app   # 能起就 Ctrl+C（SQLite 需 -w 1）

# 复制仓库自带模板并启用开机自启 + 立即启动
cp deploy/systemd/miniapp.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now miniapp
systemctl status miniapp --no-pager    # 看到 active(running) 即成功
```

### 改代码 / 改 .env 后重启
```bash
systemctl restart miniapp               # 重载新代码与 .env（.env 启动时读，必须重启才生效）
systemctl status miniapp --no-pager     # 确认 active(running)
journalctl -u miniapp -n 30 --no-pager  # 看最近日志，确认无启动报错
```

### 查看状态与日志
```bash
systemctl status miniapp --no-pager     # 服务状态
journalctl -u miniapp -f                # 实时跟踪日志（Ctrl+C 退出）
```

### 没做成 systemd 服务（手动 gunicorn 前台跑的）
```bash
cd /opt/miniapp-backend && source .venv/bin/activate
gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 127.0.0.1:8000 app.main:app
```
> 注意：使用 SQLite（默认）时必须 **-w 1**，多 worker 会争抢写锁报 `database is locked`；切换到 MySQL 后可调回 `-w 2`。
> 若 `systemctl status miniapp` 报 `Unit miniapp.service not found`，说明当时没做上面的"首次启动"，先按首次启动步骤补齐即可。

### 前端 H5 / nginx 改动无需重启后端
改了 H5 静态文件只需重新构建并 scp 覆盖 `/opt/miniapp-h5`，再 `nginx -t && systemctl reload nginx`；后端与 nginx 配置未变则无需重启 `miniapp`。

---

## 核心接口

- `POST /api/queryCarPrice`  `{ "keyword": "比亚迪 海豹" }` → 车价（缓存→实时RAG→示例库兜底）
- `POST /api/calcPlan`  `CalcParams` → 测算结果 + 结论（买买买 / 理性考虑 / 买个 der）

## 用户系统 / 广场 / 审批

微信静默登录后自动分配用户名（`车友XXXXXX`）与文字头像（用户名首字 + 稳定底色），
用户可发布买车计划到广场，其他用户可按三档给出审批与意见。

| 接口 | 鉴权 | 说明 |
|---|---|---|
| `POST /api/auth/login` | 否 | 小程序：`{code}` → `{token, expires_in, user}` |
| `POST /api/auth/login/h5` | 否 | H5：`{device_id}` → 同上（浏览器端无微信身份，用设备标识建档） |
| `GET /api/users/me` | 是 | 当前用户信息 |
| `PATCH /api/users/me` | 是 | 修改用户名（2~16 字符，唯一；头像随首字更新） |
| `GET /api/me/summary` | 是 | 我的发布数 / 收到审批数 |
| `GET /api/me/posts` | 是 | 我的发布（分页） |
| `POST /api/posts` | 是 | 发布计划（服务端用 `run_plan` 重算，不信任前端结论） |
| `GET /api/posts` | 否 | 广场列表（`sort=latest\|hot`，分页） |
| `GET /api/posts/{id}` | 否 | 详情（含 `my_review` / `is_mine`） |
| `DELETE /api/posts/{id}` | 是 | 软删除，仅本人 |
| `POST /api/posts/{id}/reviews` | 是 | 提交审批（三档 + 10~200 字意见） |
| `PUT /api/posts/{id}/reviews/me` | 是 | 修改自己的审批 |
| `GET /api/posts/{id}/reviews` | 否 | 审批列表（分页） |

关键点：
- 财务数据（收入/支出/储蓄）默认不公开，仅发布者本人可见；发布时可勾选公开。
- 每个用户对同一条发布只能有一条审批，修改不会重复计数（并发重复提交会按「修改」幂等处理）。
- 不能审批自己的发布；发布与审批均有每日上限（`POST_DAILY_LIMIT` / `REVIEW_DAILY_LIMIT`），
  按**北京时间自然日**计算，且发布额度包含当天已删除的记录（删了再发不会重置额度）。
- 登录接口按客户端 IP 限流（`LOGIN_RATE_LIMIT_PER_MINUTE`，默认 20 次/分钟）。

相关环境变量（见 `.env.example`）：`WX_APPID` / `WX_SECRET`（微信登录，未配置时降级 mock 模式，仅限开发；
mock 模式下可设 `WX_MOCK_OPENID` 固定账号，否则小程序端每次登录都会新建用户）、
`JWT_SECRET`（生产必须随机，**仍为默认值且已配置微信凭据时服务会拒绝启动**）、`TOKEN_TTL_DAYS`、
`LOGIN_RATE_LIMIT_PER_MINUTE`、`DATABASE_URL`（默认 SQLite `./data/app.db`）。

> 数据库：默认 SQLite，适合单机小流量；**使用 SQLite 时 gunicorn 必须 `-w 1`**。
> 生产建议切换 MySQL（`DATABASE_URL=mysql+pymysql://...`，需额外安装 `pymysql`）后恢复多 worker。
> MVP 用 `create_all` 建表，后续可引入 Alembic 做版本化迁移。

### 密钥管理

- `.env` 已被 `.gitignore` 忽略（同时忽略 `.env.*`，仅保留 `.env.example` 模板），**不要提交任何真实密钥**。
- `WX_APPID` 会随小程序包公开，可提交；**`WX_SECRET`、`JWT_SECRET`、各类 API Key 属于机密**，只能写进 `.env`。
- 生产环境把真实配置放在项目目录之外：`/etc/miniapp/miniapp.env`（`chmod 600`），
  由 systemd `EnvironmentFile` 注入；项目目录内不要放 `.env`。
- 一旦密钥误入版本历史：先到微信公众平台重置 AppSecret / 轮换 API Key，再清理 git 历史
  （`git filter-repo`），仅删除文件不足以消除泄露。

## LLM 后端与检索源

通过 `.env` 的 `LLM_PROVIDER` 选择大模型。推荐 **豆包（火山引擎方舟）**——模型内置
`web_search` 联网搜索，只需一个 `DOUBAO_API_KEY`，无需单独的搜索服务。

| LLM_PROVIDER | 说明 | 需要 key |
|---|---|---|
| `doubao` | **火山引擎方舟（内置联网搜索，推荐）** | `DOUBAO_API_KEY`（即 ARK_API_KEY） |
| `deepseek` | DeepSeek（OpenAI 兼容，需配合外部搜索源） | `DEEPSEEK_API_KEY` + `SEARCH_PROVIDER` 对应 key |

- `doubao` 模式：`LLM_PROVIDER=doubao` + `DOUBAO_API_KEY` 即完整实时链路，单 key 搞定。
- `deepseek` 模式：实时链路 = `DEEPSEEK_API_KEY` **且** `search_ready()`（`SEARCH_PROVIDER` 对应 key 已填）；
  外部检索未就绪时启动会告警，并降级到示例库 / mock 片段。

可选 `SEARCH_PROVIDER`（仅 `deepseek` 模式需要）：

| provider | 说明 | 需要 key |
|---|---|---|
| `bocha` | **博查 Web Search API（国内，推荐）** | `BOCHA_API_KEY` |
| `tavily` | Tavily Search API（海外，备选） | `TAVILY_API_KEY` |
| `mock` | 内置离线片段（默认，非实时） | 无 |

> 合规提示：不建议直接抓取懂车帝 / 汽车之家等站点（robots 禁止 + 反爬 + 版权风险）。
> 生产请以官方开放平台 / 授权数据接口为准。

### 火山方舟：Agent Plan 套餐 vs 按量付费（两种接入通道）

豆包后端支持火山方舟的两种计费通道，二者 **API Key 不同、Base URL 不同，不能混用**：

| 通道 | Base URL | Key 来源 | 适配模型示例 |
|---|---|---|---|
| Agent Plan 套餐 | `https://ark.cn-beijing.volces.com/api/plan/v3` | Agent Plan 控制台专属 key（形如 `ark-xxxx-xxxx`） | `doubao-seed-2.1-lite`（实际解析为 `doubao-seed-2-1-lite-260915`） |
| 方舟按量付费（**默认**） | `https://ark.cn-beijing.volces.com/api/v3` | 方舟控制台「API Key 管理」新建的 `ark-` key | `doubao-seed-2-1-pro-260915` 或控制台接入点 |

> `DOUBAO_BASE_URL` 不配置时，后端**默认走按量路径 `/api/v3`**（见 `app/config.py`）。

**切到 Agent Plan 套餐（当前线上配置）**
```bash
DOUBAO_API_KEY=<Agent Plan 控制台专属 key>        # 注意：不是方舟按量 key
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/plan/v3
DOUBAO_MODEL=doubao-seed-2.1-lite
```

**切回方舟按量付费**
```bash
DOUBAO_API_KEY=<方舟控制台新建的按量 ark- key>     # 与 Agent Plan key 不是同一个
# DOUBAO_BASE_URL 删除或注释掉 → 自动回退默认 /api/v3 按量路径
DOUBAO_MODEL=doubao-seed-2-1-pro-260915          # 换成方舟按量平台确认存在的接入点名
```

> ⚠️ 切换要点：
> 1. 两套 key **不能混用**——把 Agent Plan 的 key 拿到 `/api/v3` 用会返回 `401`；反之亦然。
> 2. 模型名随通道不同：Agent Plan 的 `doubao-seed-2.1-lite` 在按量平台未必同名，切回按量时务必换成方舟控制台实际显示的接入点名，否则报"模型不存在"。
> 3. 改完 `.env` 必须**重启后端**（`Ctrl+C` + 重新启动 uvicorn）才能生效。

**验证是否真正接通实时取价**
```bash
curl http://localhost:8000/api/queryCarPrice -H "Content-Type: application/json" -d '{"keyword":"比亚迪 海豹"}'
```
- 返回 `source` 是真实网站（汽车之家 / 易车 / 官网等）、`fetched_at` 为刚查时间 → 链路通 ✅
- 返回示例/缓存数据 → 联网搜索未生效，检查 key / Base URL / 模型名是否匹配当前通道。

## 测试

```bash
pytest app/tests -q
```

## 说明

- 未配置任何 API key 时，自动走**离线 Mock + 内置示例车型库**兜底，保证全流程可跑通。
- `app/engine` 为纯函数计算/决策引擎，无副作用，已单测覆盖。
- 启动时打印 `LLM 来源` 日志（如 `豆包(火山方舟) 实时联网检索`），便于确认当前是实时还是离线；`deepseek` 模式会额外打印检索来源。
