# 买车决策小程序 · 后端（FastAPI）

车型价格检索增强 + 购车费用测算 + 可负担性评估。

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows；Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env            # 填入密钥启用实时价格（见下方“LLM 后端与检索源”）
python -m uvicorn app.main:app --reload --port 8000
```

- API 文档（Swagger）：http://localhost:8000/docs
- 健康检查：GET /health

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

## 测试

```bash
pytest app/tests -q
```

## 说明

- 未配置任何 API key 时，自动走**离线 Mock + 内置示例车型库**兜底，保证全流程可跑通。
- `app/engine` 为纯函数计算/决策引擎，无副作用，已单测覆盖。
- 启动时打印 `LLM 来源` 日志（如 `豆包(火山方舟) 实时联网检索`），便于确认当前是实时还是离线；`deepseek` 模式会额外打印检索来源。
