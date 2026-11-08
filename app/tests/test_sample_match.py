"""示例库匹配：品牌+车型双约束，避免「比亚迪 汉」误配「海豹」。"""
from app.services.sample_cars import find_sample


def test_find_sample_requires_model_not_brand_only():
    assert find_sample("比亚迪 汉") is None


def test_find_sample_brand_and_model():
    car = find_sample("比亚迪 海豹")
    assert car is not None
    assert car.brand == "比亚迪"
    assert car.model == "海豹"


def test_find_sample_unique_model_only():
    car = find_sample("海豹")
    assert car is not None
    assert car.model == "海豹"
