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

### 首次启动（做成开机自启服务）
先手动验证 gunicorn 能起，再做成 systemd 服务：
```bash
cd /opt/miniapp-backend
source .venv/bin/activate
gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 127.0.0.1:8000 app.main:app   # 能起就 Ctrl+C

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
gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 127.0.0.1:8000 app.main:app
```
> 若 `systemctl status miniapp` 报 `Unit miniapp.service not found`，说明当时没做上面的"首次启动"，先按首次启动步骤补齐即可。

### 前端 H5 / nginx 改动无需重启后端
改了 H5 静态文件只需重新构建并 scp 覆盖 `/opt/miniapp-h5`，再 `nginx -t && systemctl reload nginx`；后端与 nginx 配置未变则无需重启 `miniapp`。

---

## 核心接口

- `POST /api/queryCarPrice`  `{ "keyword": "比亚迪 海豹" }` → 车价（缓存→实时RAG→示例库兜底）
- `POST /api/calcPlan`  `CalcParams` → 测算结果 + 结论（买买买 / 理性考虑 / 买个 der）

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
