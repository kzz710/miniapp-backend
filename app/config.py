"""配置：从环境变量读取，支持 .env 文件。"""
import os

from dotenv import load_dotenv

load_dotenv()

# LLM 后端：deepseek 或 doubao。
# - deepseek：OpenAI 兼容 chat/completions，需配合外部搜索源（Bocha/Tavily）。
# - doubao  ：火山引擎方舟 Responses API，内置 web_search 联网搜索，只需一个 key。
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").lower()

# DeepSeek（OpenAI 兼容接口），LLM_PROVIDER=deepseek 时使用
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 豆包（火山引擎方舟 Responses API，内置联网搜索），LLM_PROVIDER=doubao 时使用
# DOUBAO_API_KEY 即方舟控制台获取的 ARK_API_KEY
DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY", "")
DOUBAO_BASE_URL = os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
# 默认模型同时支持工具调用与联网搜索；可在方舟控制台替换为指定推理接入点或版本
DOUBAO_MODEL = os.getenv("DOUBAO_MODEL", "doubao-seed-1.6-250615")

# 搜索源（仅 LLM_PROVIDER=deepseek 时用于 RAG 检索增强）。
# - bocha : 博查 Web Search API（国内服务，推荐，降低海外依赖）
# - tavily: Tavily Search API（海外，备选）
# - mock  : 内置离线片段（默认，无 key 也能跑通，但非实时）
SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "mock").lower()
BOCHA_API_KEY = os.getenv("BOCHA_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# 车价缓存 TTL（秒），默认 24 小时
CACHE_TTL = int(os.getenv("CACHE_TTL", "86400"))

# 服务端口
PORT = int(os.getenv("PORT", "8000"))

# 安全月供占可支配收入比例（默认 30%，可在此或请求参数调整）
DEFAULT_SAFE_RATIO = 0.3


def _llm_has_key() -> bool:
    if LLM_PROVIDER == "doubao":
        return bool(DOUBAO_API_KEY)
    return bool(DEEPSEEK_API_KEY)


def live_mode() -> bool:
    """是否启用真实 LLM 实时检索（对应 key 存在才算 live）。"""
    return _llm_has_key()


def llm_label() -> str:
    """人类可读的 LLM 来源描述，用于启动日志。"""
    if LLM_PROVIDER == "doubao":
        return "豆包(火山方舟) 实时联网检索" if DOUBAO_API_KEY else "豆包(未配置 key→降级示例库)"
    return "DeepSeek 实时检索" if DEEPSEEK_API_KEY else "DeepSeek(未配置 key→降级示例库)"


def search_ready() -> bool:
    """真实检索后端是否就绪（仅 deepseek 模式需要；provider=mock 或 key 缺失都算未就绪）。"""
    if SEARCH_PROVIDER == "bocha":
        return bool(BOCHA_API_KEY)
    if SEARCH_PROVIDER == "tavily":
        return bool(TAVILY_API_KEY)
    return False


def search_label() -> str:
    """人类可读的搜索后端描述，用于启动日志。"""
    if SEARCH_PROVIDER == "bocha":
        return "博查(国内) 实时检索" if BOCHA_API_KEY else "博查(未配置 key→降级 mock)"
    if SEARCH_PROVIDER == "tavily":
        return "Tavily(海外) 实时检索" if TAVILY_API_KEY else "Tavily(未配置 key→降级 mock)"
    return "内置 mock 片段（非实时）"
