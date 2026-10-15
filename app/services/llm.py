"""LLM 接入：车型检索增强(RAG) + 结构化价格抽取。

支持两种后端（由 LLM_PROVIDER 切换）：
- deepseek：OpenAI 兼容 chat/completions，需配合外部搜索源（Bocha/Tavily）。
- doubao  ：火山引擎方舟 Responses API，内置 web_search 联网搜索，只需一个 key。

关键约束（技术方案第 7 节）：绝不让模型凭记忆报当前价。
离线（无对应 key）时返回 None，由上层 car_price 走示例库兜底。
"""
import json
from typing import Optional

import httpx

from app import config
from app.types import CarPrice
from app.utils.helpers import now_iso, slugify
from app.utils.validate import parse_json_strict, validate_price
from app.services.sample_cars import find_sample


_EXTRACT_PROMPT = (
    "你是一个汽车报价助手。请只依据联网/搜索到的公开信息回答，禁止编造。"
    "若查到该车型的当前价格，输出严格 JSON："
    "{"
    '"found": true, '
    '"brand": "品牌", '
    '"model": "车型", '
    '"source": "价格来源站点或URL", '
    '"versions": ['
    "{"
    '"config": "配置/版本名（如 2024款 550km 后驱版）", '
    '"energy_type": "gas|ev|hybrid", '
    '"fuel_consumption": 0.0, '
    '"power_consumption": 0.0, '
    '"guide_price": 0.0, '
    '"ref_discount_price": 0.0'
    "}"
    "]"
    "}，"
    "规则："
    "1) energy_type 必须按版本实际动力类型判断：纯电→ev，纯油→gas，插混/油混→hybrid；"
    "电车 fuel_consumption=0、power_consumption 填百公里电耗(kWh/100km)，油车相反，混动两者都填（油耗时填 L/100km）。"
    "2) 若用户仅给品牌+车型（如「比亚迪 海豹」）未指定具体版本，列出该车型在售主要版本（最多 6 个）；"
    "若已指定具体版本，则只返回该版本（单个元素）。"
    "3) guide_price 为指导价(万元)，ref_discount_price 为参考优惠价/终端价(万元)；查不到优惠价可等于指导价。"
    "4) 仅输出 JSON，不要任何解释文字。"
    "若查不到明确价格，输出 {\"found\": false}。"
)


async def fetch_live_prices(keyword: str) -> list[CarPrice]:
    """统一入口：按 LLM_PROVIDER 分派，返回该车型全部版本（可能为空）。"""
    if config.LLM_PROVIDER == "doubao":
        return await doubao_rag(keyword)
    return await deepseek_rag(keyword)


def _coerce_energy(et: str) -> str:
    """把模型返回的能源类型规整为 gas/ev/hybrid 之一，未知默认 gas。"""
    et = str(et or "").strip().lower()
    if et in ("gas", "ev", "hybrid"):
        return et
    # 常见中文/英文别名兜底
    if "电" in et or "ev" in et or "纯电" in et or "electric" in et:
        return "ev"
    if "混" in et or "hybrid" in et or "插混" in et or "油混" in et:
        return "hybrid"
    return "gas"


def _build_versions(data: dict, fallback_source: str) -> list[CarPrice]:
    """从模型抽出的 dict 构造版本列表；价格校验不合法的版本会被跳过。

    兼容两种格式：
    - 新版：data["versions"] 为数组；
    - 旧版（单版本）：data 直接带 config/guide_price/...，视为单元素数组。
    """
    brand = str(data.get("brand", ""))
    model = str(data.get("model", ""))
    source = str(data.get("source") or fallback_source)

    raw_versions = data.get("versions")
    if not isinstance(raw_versions, list):
        # 旧版单对象格式：用顶层字段拼一个版本
        if data.get("config") is not None:
            raw_versions = [data]
        else:
            raw_versions = []

    out: list[CarPrice] = []
    for v in raw_versions:
        if not isinstance(v, dict):
            continue
        # 单版本兼容：energy_type/价格可能既在顶层也在版本里
        energy_type = v.get("energy_type", data.get("energy_type", "gas"))
        try:
            car = CarPrice(
                car_id=slugify(f"{brand}-{model}-{v.get('config','')}"),
                brand=brand,
                model=model,
                config=str(v.get("config", "")),
                guide_price=float(v.get("guide_price", data.get("guide_price", 0.0))),
                ref_discount_price=float(
                    v.get("ref_discount_price", data.get("ref_discount_price", 0.0))
                ),
                energy_type=_coerce_energy(energy_type),
                fuel_consumption=float(v.get("fuel_consumption", 0.0)),
                power_consumption=float(v.get("power_consumption", 0.0)),
                source=source,
                fetched_at=now_iso(),
            )
        except (TypeError, ValueError):
            continue
        if validate_price(car):
            out.append(car)
    return out


# ---------- DeepSeek（需外部搜索源） ----------

async def _deepseek_chat(messages: list, json_mode: bool = False) -> Optional[dict]:
    """调用 DeepSeek chat/completions（OpenAI 兼容）。失败返回 None。"""
    if not config.DEEPSEEK_API_KEY:
        return None
    payload = {"model": config.DEEPSEEK_MODEL, "messages": messages, "temperature": 0}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{config.DEEPSEEK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


async def deepseek_rag(keyword: str) -> list[CarPrice]:
    """DeepSeek + 外部搜索源（Bocha/Tavily/mock）的检索增强。"""
    if not config.DEEPSEEK_API_KEY:
        return []

    # 外部检索未就绪时，下面只能基于 mock 片段回答，结果不可靠，显式告警。
    if not config.search_ready():
        print(
            "[警告] 检索后端未就绪（SEARCH_PROVIDER="
            f"{config.SEARCH_PROVIDER}），将使用非实时 mock 片段喂模型，"
            "价格结果不可靠。请配置 BOCHA_API_KEY 或 TAVILY_API_KEY。"
        )

    # 1) 让模型把查询意图转成搜索词
    r1 = await _deepseek_chat(
        [
            {
                "role": "system",
                "content": "你帮用户把购车价格查询意图转成一条简洁的搜索词（含年份/车型/落地价）。只输出搜索词，不要解释。",
            },
            {"role": "user", "content": f"用户想查：{keyword} 的当前指导价、优惠价与落地价"},
        ]
    )
    query = keyword
    if r1:
        try:
            query = r1["choices"][0]["message"]["content"].strip()
        except Exception:
            pass

    # 2) 应用执行检索
    from app.services.search import web_search

    results = await web_search(query)
    if not results:
        return []

    # 3) 仅基于检索片段，抽取结构化价格
    ctx = "\n".join(f"- {r['title']} {r['url']}\n  {r['snippet']}" for r in results)
    r2 = await _deepseek_chat(
        [
            {"role": "system", "content": _EXTRACT_PROMPT},
            {"role": "user", "content": f"原始查询：{keyword}\n搜索结果：\n{ctx}"},
        ],
        json_mode=True,
    )
    if not r2:
        return []
    try:
        content = r2["choices"][0]["message"]["content"]
    except Exception:
        return []

    data = parse_json_strict(content)
    if not data or not data.get("found"):
        return []
    return _build_versions(data, results[0]["url"])


# ---------- 豆包（火山方舟，内置联网搜索） ----------

def _extract_text_from_responses(data: dict) -> str:
    """从 Responses API 返回中拼出助手最终文本。

    兼容 web_search 工具调用产生的多 item（可能包含 web_search_call 等中间步骤，
    真正的回答在 type=message / role=assistant 的 output_text 中）。
    """
    out = (data or {}).get("output") or []
    texts: list[str] = []
    for item in out:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message" and item.get("role") == "assistant":
            for c in item.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "output_text":
                    texts.append(c.get("text", ""))
    if texts:
        return "\n".join(texts)

    # 兜底：递归查找任意 output_text
    def _walk(node):
        if isinstance(node, dict):
            if node.get("type") == "output_text" and isinstance(node.get("text"), str):
                texts.append(node["text"])
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(data)
    return "\n".join(texts)


async def doubao_rag(keyword: str) -> list[CarPrice]:
    """豆包（火山方舟 Responses API）内置 web_search 联网搜索 + 抽取。

    注意：方舟原生 web_search 工具要求
    - input[].content 必须是 [{type:"input_text", text:...}] 数组（不能是纯字符串），
      否则方舟会误判工具不可用并返回 ToolNotOpen；
    - web_search 工具需带 max_keyword（1~50，控制单轮关键词搜索次数）。
    """
    if not config.DOUBAO_API_KEY:
        return []
    payload = {
        "model": config.DOUBAO_MODEL,
        "stream": False,
        "tools": [{"type": "web_search", "max_keyword": 5}],
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"{_EXTRACT_PROMPT}\n\n原始查询：{keyword}",
                    }
                ],
            }
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{config.DOUBAO_BASE_URL}/responses",
                headers={
                    "Authorization": f"Bearer {config.DOUBAO_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code >= 400:
                # 把方舟返回的错误码/信息打出来，便于定位（未开通模型 / 未开通联网插件等）
                try:
                    err = resp.json().get("error", {})
                    code = err.get("code", "")
                    msg = err.get("message", resp.text)
                except Exception:
                    code, msg = str(resp.status_code), resp.text
                print(f"[doubao] 请求失败 HTTP {resp.status_code} | code={code} | {msg}")
                return []
            data = resp.json()
    except Exception as e:
        print(f"[doubao] 请求异常：{e}")
        return None

    text = _extract_text_from_responses(data)
    if not text:
        return []
    parsed = parse_json_strict(text)
    if not parsed or not parsed.get("found"):
        return []
    return _build_versions(parsed, parsed.get("source") or "")
