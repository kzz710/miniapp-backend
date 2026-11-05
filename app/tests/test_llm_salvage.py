"""模型输出被截断时的版本抢救逻辑测试。"""
from app.services.llm import _salvage_field, _salvage_versions


def test_salvage_field_and_versions_from_truncated_json():
    text = (
        '{"found": true, "brand": "宝马", "model": "3系", '
        '"source": "BMW中国官网", "versions": ['
        '{"config": "2026款 320i", "energy_type": "gas", "guide_price": 30.0, "ref_discount_price": 28.0}, '
        '{"config": "2026款 330i", "energy_type": "gas", "guide_price": 36.0, "ref_discount_price": 33.0}, '
        '{"config": "2026款 340i", "energy_ty'
    )

    assert _salvage_field(text, "brand") == "宝马"
    assert _salvage_field(text, "model") == "3系"
    assert _salvage_field(text, "source") == "BMW中国官网"

    versions = _salvage_versions(text)
    assert [v["config"] for v in versions] == ["2026款 320i", "2026款 330i"]


def test_salvage_returns_empty_for_complete_text_without_versions():
    assert _salvage_versions('{"found": false}') == []
    assert _salvage_field('{"found": false}', "brand", "未知") == "未知"
