"""Kiểm tra bộ máy luật bằng 20 mẹo mẫu: chưa vá thì phải lỗ, vá xong thì phải chặn được.

Chạy: python -m pytest -q
"""
import copy

import pytest

from server.engine import is_blocked, measure
from server.fallback import KNOWN, TEMPLATES, patch_fallback, translate_fallback


@pytest.mark.parametrize("x", KNOWN, ids=[x["id"] for x in KNOWN])
def test_exploit_loses_money_then_patch_blocks_it(x):
    rules = [copy.deepcopy(TEMPLATES[k]) for k in x["needs"]]
    before = measure(rules, x["events"], x["honest"])
    assert before["verified"], f"{x['id']}: chưa vá mà không lỗ ({before})"
    patched, fixes = patch_fallback(rules[0], [x["id"]])
    after = measure([patched] + rules[1:], x["events"], x["honest"])
    assert is_blocked(before["loss"], after["loss"]), f"{x['id']}: vá rồi vẫn lỗ {after['loss']} (trước {before['loss']})"
    assert fixes and fixes[0].explanation


def test_honest_customer_is_not_flagged():
    rules = [TEMPLATES["combo"], TEMPLATES["return"]]
    from server.fallback import E
    honest = [E("place_order", ["shirt", "jeans"]), E("deliver")]
    assert not measure(rules, honest, honest)["verified"]


def test_translate_keeps_numbers():
    r = translate_fallback("freeship cho đơn từ 500k").rule
    assert r.conditions[0].value == "500000"
    assert translate_fallback("mua 2 tặng 1").rule.id == "bogo"
    assert translate_fallback("đánh giá 5 sao tặng 20k").rule.id == "review"
    assert not translate_fallback("trả góp 0%").understood
