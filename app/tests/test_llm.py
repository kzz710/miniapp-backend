"""LLM 层（豆包 / DeepSeek）配置与解析测试。"""
import pytest

from app import config
from app.services import llm


def test_live_mode_doubao_no_key(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "doubao")
    monkeypatch.setattr(config, "DOUBAO_API_KEY", "")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")
    assert config.live_mode() is False


def test_live_mode_doubao_with_key(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "doubao")
    monkeypatch.setattr(config, "DOUBAO_API_KEY", "x")
    assert config.live_mode() is True


def test_live_mode_deepseek_with_key(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "x")
    assert config.live_mode() is True


def test_extract_text_from_responses_message():
    data = {
        "output": [
            {"type": "web_search_call", "status": "completed"},
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": '{"found": true}'}],
            },
        ]
    }
    assert llm._extract_text_from_responses(data) == '{"found": true}'


def test_extract_text_fallback_walk():
    data = {
        "output": [
            {"type": "message", "role": "assistant",
             "content": [{"type": "output_text", "text": "hello"}]}
        ]
    }
    assert llm._extract_text_from_responses(data) == "hello"


@pytest.mark.asyncio
async def test_fetch_live_prices_doubao_no_key_returns_empty(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "doubao")
    monkeypatch.setattr(config, "DOUBAO_API_KEY", "")
    assert await llm.fetch_live_prices("比亚迪 海豹") == []


def test_coerce_energy():
    assert llm._coerce_energy("ev") == "ev"
    assert llm._coerce_energy("纯电") == "ev"
    assert llm._coerce_energy("electric") == "ev"
    assert llm._coerce_energy("混动") == "hybrid"
    assert llm._coerce_energy("油车") == "gas"
    assert llm._coerce_energy("未知xxx") == "gas"


def test_build_versions_multi_and_energy():
    data = {
        "brand": "比亚迪",
        "model": "海豹",
        "source": "https://example.com",
        "versions": [
            {
                "config": "550km 后驱版",
                "energy_type": "ev",
                "fuel_consumption": 0.0,
                "power_consumption": 13.0,
                "guide_price": 18.98,
                "ref_discount_price": 17.50,
            },
            {
                "config": "650km 四驱版",
                "energy_type": "纯电",
                "fuel_consumption": 0.0,
                "power_consumption": 14.5,
                "guide_price": 21.68,
                "ref_discount_price": 20.0,
            },
        ],
    }
    cars = llm._build_versions(data, "fallback")
    assert len(cars) == 2
    assert cars[0].energy_type == "ev"
    assert cars[1].energy_type == "ev"  # 纯电 -> ev 规整
    assert cars[1].power_consumption == 14.5
    assert cars[0].brand == "比亚迪" and cars[0].model == "海豹"


def test_build_versions_legacy_single_object():
    # 兼容旧版单对象格式（无 versions 字段）
    data = {
        "brand": "丰田",
        "model": "凯美瑞",
        "config": "2.0L 豪华版",
        "energy_type": "gas",
        "guide_price": 19.18,
        "ref_discount_price": 17.18,
        "source": "x",
    }
    cars = llm._build_versions(data, "x")
    assert len(cars) == 1
    assert cars[0].energy_type == "gas"
