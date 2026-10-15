"""检索源：为 RAG 提供实时网页片段（可插拔后端）。

设计目标：把"搜索"从单一 Tavily 解耦，支持国内可用的检索服务，降低海外依赖。

后端（由环境变量 SEARCH_PROVIDER 选择，见 app/config.py）：
- bocha : 博查 Web Search API（国内公司，返回中文网页片段，推荐）
- tavily: Tavily Search API（海外，备选）
- mock  : 内置离线片段（默认；无 key 也能跑通，但价格非实时）

所有后端统一返回 [{title, url, snippet, date}, ...]，供 deepseek_rag 消费。

合规说明：
- 不建议直接抓取懂车帝/汽车之家等站点：其 robots.txt 禁止抓取、且有反爬，
  对商业小程序存在版权与数据合规风险。生产请以官方开放平台/授权数据接口为准。
- 若改用直连搜索页解析，请在获取数据授权后实现，并自行承担合规责任。
"""
from typing import List

import httpx

from app import config
from app.utils.helpers import now_iso


async def web_search(query: str) -> List[dict]:
    """返回 [{title, url, snippet, date}, ...]。按 SEARCH_PROVIDER 分派。"""
    provider = config.SEARCH_PROVIDER
    if provider == "bocha":
        results = await _search_bocha(query)
        if results:
            return results
        # 未配置 key 或请求失败 → 降级到 mock，保证流程不中断
        return _search_mock(query)
    if provider == "tavily":
        results = await _search_tavily(query)
        if results:
            return results
        return _search_mock(query)
    # 默认 mock
    return _search_mock(query)


async def _search_tavily(query: str) -> List[dict]:
    """Tavily Search API（海外，备选）。无 key 或失败返回空。"""
    if not config.TAVILY_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": config.TAVILY_API_KEY,
                    "query": query,
                    "max_results": 5,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                    "date": r.get("published_date", ""),
                }
                for r in data.get("results", [])
            ]
    except Exception:
        return []


async def _search_bocha(query: str) -> List[dict]:
    """博查 Web Search API（国内，推荐）。无 key 或失败返回空。

    文档：POST https://api.bochaai.com/v1/web-search
    鉴权：Authorization: Bearer <BOCHA_API_KEY>
    请求体：{"query": ..., "freshness": "noLimit", "summary": true, "count": 5}
    响应：data.webPages.value[] -> {name, url, snippet|summary, dateLastCrawled}
    """
    if not config.BOCHA_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.bochaai.com/v1/web-search",
                headers={
                    "Authorization": f"Bearer {config.BOCHA_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "query": query,
                    "freshness": "noLimit",
                    "summary": True,
                    "count": 5,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        pages = data.get("data", {}).get("webPages", {}).get("value", [])
        out: List[dict] = []
        for r in pages:
            snippet = r.get("summary") or r.get("snippet") or ""
            if not snippet and r.get("name"):
                snippet = r.get("name", "")
            out.append(
                {
                    "title": r.get("name", ""),
                    "url": r.get("url", ""),
                    "snippet": snippet,
                    "date": r.get("dateLastCrawled", ""),
                }
            )
        return out
    except Exception:
        return []


def _search_mock(query: str) -> List[dict]:
    """离线 mock：仅用于演示流程，非实时价格。"""
    return [
        {
            "title": f"{query} 最新落地价与优惠",
            "url": "https://example.com/price",
            "snippet": f"{query} 指导价约 18 万，参考优惠价约 17 万，近期有小幅优惠。",
            "date": now_iso(),
        },
        {
            "title": f"{query} 汽车之家车主成交价",
            "url": "https://car.autohome.com.cn",
            "snippet": f"{query} 车主真实成交价区间约 17~19 万。",
            "date": now_iso(),
        },
    ]
