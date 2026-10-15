"""搜索后端分派与降级测试。"""
import pytest

from app import config
from app.services import search


def test_search_ready_mock_is_false(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_PROVIDER", "mock")
    assert config.search_ready() is False


def test_search_ready_bocha_no_key_is_false(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_PROVIDER", "bocha")
    monkeypatch.setattr(config, "BOCHA_API_KEY", "")
    assert config.search_ready() is False


def test_search_ready_bocha_with_key_is_true(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_PROVIDER", "bocha")
    monkeypatch.setattr(config, "BOCHA_API_KEY", "fake-key")
    assert config.search_ready() is True


@pytest.mark.asyncio
async def test_web_search_mock_returns_two_items(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_PROVIDER", "mock")
    results = await search.web_search("比亚迪 海豹")
    assert len(results) == 2
    assert all("snippet" in r and "url" in r for r in results)


@pytest.mark.asyncio
async def test_web_search_bocha_without_key_falls_back_to_mock(monkeypatch):
    # 未配置 key 时，bocha 后端应降级到 mock 片段，不抛错
    monkeypatch.setattr(config, "SEARCH_PROVIDER", "bocha")
    monkeypatch.setattr(config, "BOCHA_API_KEY", "")
    results = await search.web_search("丰田 凯美瑞")
    assert len(results) == 2  # mock 兜底
