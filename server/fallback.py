"""Chế độ dự phòng: 11 luật mẫu và 20 mẹo lách viết sẵn.

Dùng khi chưa có API key, khi API lỗi, hoặc làm lưới an toàn lúc demo.
Mỗi mẹo đều được bộ máy luật chạy thử như mẹo do LLM tìm ra, không được ưu tiên gì.
"""
from __future__ import annotations

import copy
import re
from typing import Dict, List, Optional, Set

from .schema import (Action, ActionType, Condition, Event, EventType, Exploit, FieldName, Fix, Limit, LimitType,
                     Op, Rule, TranslateResult)


def C(field, op, value):
    return Condition(field=FieldName(field), op=Op(op), value=str(value))


def A(t, v=None):
    return Action(type=ActionType(t), value=v)


def L(t, v=None):
    return Limit(type=LimitType(t), value=v)


def E(t, items=None, amount=None, flag=None):
    return Event(type=EventType(t), items=items or [], amount=amount, flag=flag)


TEMPLATES: Dict[str, Rule] = {
    "freeship": Rule(id="freeship", name="Freeship đơn từ 300k", conditions=[C("cart_total", "gte", 300000)],
                     actions=[A("free_shipping")], limits=[]),
    "return": Rule(id="return", name="Đổi trả miễn phí 7 ngày", conditions=[], actions=[A("free_return", 7)], limits=[]),
    "newbie": Rule(id="newbie", name="Khách mới giảm 50k", conditions=[C("is_new_account", "eq", "true")],
                   actions=[A("discount_vnd", 50000)], limits=[]),
    "combo": Rule(id="combo", name="Mua 2 món giảm 10%", conditions=[C("item_count", "gte", 2)],
                  actions=[A("discount_pct", 10)], limits=[]),
    "points": Rule(id="points", name="Hoàn 5% xu mỗi đơn", conditions=[], actions=[A("coins_pct", 5)], limits=[]),
    "flash": Rule(id="flash", name="Flash sale áo thun 99k", conditions=[], actions=[A("flash_price", 99000)], limits=[]),
    "referral": Rule(id="referral", name="Giới thiệu bạn, mỗi bên 30k", conditions=[],
                     actions=[A("referral_reward_vnd", 30000)], limits=[]),
    "cod": Rule(id="cod", name="Thanh toán khi nhận hàng", conditions=[], actions=[A("cod_allowed")], limits=[]),
    "pricematch": Rule(id="pricematch", name="Thấy rẻ hơn, hoàn chênh lệch", conditions=[],
                       actions=[A("price_match")], limits=[]),
    "review": Rule(id="review", name="Đánh giá 5 sao tặng 20k", conditions=[], actions=[A("review_voucher_vnd", 20000)],
                   limits=[]),
    "bogo": Rule(id="bogo", name="Mua 2 tặng 1", conditions=[C("item_count", "gte", 2)], actions=[A("free_item", 1)],
                 limits=[]),
}

# thứ tự dò: câu cụ thể thắng câu chung chung
MATCH = [
    ("bogo", r"mua\s*\d+\s*tặng"),
    ("combo", r"((mua\s*\d|\d\s*món|combo).*(giảm|%))|(giảm.*(mua\s*\d|\d\s*món))"),
    ("cod", r"\bcod\b|thanh toán khi nhận|nhận hàng (rồi |mới )?trả tiền"),
    ("pricematch", r"rẻ hơn|chênh lệch|đảm bảo giá|price match"),
    ("review", r"đánh giá|review|\d\s*sao"),
    ("referral", r"giới thiệu|mời bạn|referral"),
    ("return", r"đổi trả|trả hàng|hoàn trả|đổi hàng"),
    ("freeship", r"free\s*ship|miễn phí (ship|vận chuyển|giao)|phí ship"),
    ("newbie", r"khách mới|người mới|lần đầu|tài khoản mới"),
    ("flash", r"flash|giá sốc"),
    ("points", r"\bxu\b|tích điểm|cashback|hoàn tiền\s*\d+\s*%"),
]


def _money(text: str) -> Optional[int]:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(k|nghìn|ngàn|tr|triệu)\b", text, re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return int(v * (1_000_000 if m.group(2).lower() in ("tr", "triệu") else 1000))


def _pct(text: str) -> Optional[float]:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
    return float(m.group(1).replace(",", ".")) if m else None


def translate_fallback(text: str) -> TranslateResult:
    t = text.strip()
    key = next((k for k, pat in MATCH if re.search(pat, t, re.I)), None)
    if not key:
        return TranslateResult(understood=False, rule=None, restatement="",
                               question="Chế độ dự phòng chỉ hiểu 11 loại chính sách mẫu (freeship, đổi trả, khách mới, "
                                        "mua 2 giảm giá, mua 2 tặng 1, hoàn xu, flash sale, giới thiệu bạn, COD, cam kết "
                                        "giá rẻ, thưởng đánh giá). Dán API key để hiểu câu bất kỳ.")
    r = copy.deepcopy(TEMPLATES[key])
    money, pct = _money(t), _pct(t)
    if key == "freeship" and money:
        r.conditions[0].value = str(money)
        r.name = f"Freeship đơn từ {money // 1000}k"
    elif key == "newbie" and money:
        r.actions[0].value = money
        r.name = f"Khách mới giảm {money // 1000}k"
    elif key == "combo" and pct:
        r.actions[0].value = pct
        r.name = f"Mua 2 món giảm {pct:g}%"
    elif key == "points" and pct:
        r.actions[0].value = pct
        r.name = f"Hoàn {pct:g}% xu mỗi đơn"
    elif key == "flash" and money:
        r.actions[0].value = money
        r.name = f"Flash sale áo thun {money // 1000}k"
    elif key == "referral" and money:
        r.actions[0].value = money
        r.name = f"Giới thiệu bạn, mỗi bên {money // 1000}k"
    elif key == "review" and money:
        r.actions[0].value = money
        r.name = f"Đánh giá 5 sao tặng {money // 1000}k"
    return TranslateResult(understood=True, question=None, rule=r,
                           restatement=f"{r.name}. (Chế độ dự phòng: khớp vào luật mẫu, kiểm tra lại các con số.)")


def kinds_of(rule: Rule) -> Set[str]:
    k = set()
    for a in rule.actions:
        t = a.type
        if t == ActionType.free_shipping: k.add("freeship")
        elif t == ActionType.free_return: k.add("return")
        elif t == ActionType.discount_vnd and any(c.field == FieldName.is_new_account for c in rule.conditions): k.add("newbie")
        elif t == ActionType.discount_pct: k.add("combo")
        elif t == ActionType.coins_pct: k.add("points")
        elif t == ActionType.flash_price: k.add("flash")
        elif t == ActionType.referral_reward_vnd: k.add("referral")
        elif t == ActionType.cod_allowed: k.add("cod")
        elif t == ActionType.price_match: k.add("pricematch")
        elif t == ActionType.review_voucher_vnd: k.add("review")
        elif t == ActionType.free_item: k.add("bogo")
    return k


def _x(id, needs, name, bubble, how, events, honest, limits, fix, tradeoff):
    return {"id": id, "needs": needs, "name": name, "bubble": bubble, "how": how, "events": events,
            "honest": honest, "limits": limits, "fix": fix, "tradeoff": tradeoff}


KNOWN = [
    _x("cancel", ["freeship"], "Đủ ngưỡng rồi huỷ bớt", "Đủ 300k rồi, huỷ bớt",
       "Bỏ thêm món cho đủ ngưỡng để được freeship, rồi huỷ món đó trước khi shop giao.",
       [E("place_order", ["shirt", "cap"]), E("cancel_items", ["cap"]), E("deliver")],
       [E("place_order", ["shirt"]), E("deliver")],
       [L("recheck_after_cancel")], "Tính lại freeship theo giá trị đơn sau khi huỷ.", "Không đáng kể"),
    _x("shipret", ["freeship", "return"], "Đủ ngưỡng rồi trả bớt", "Trả món độn, giữ freeship",
       "Mua thêm món cho đủ ngưỡng freeship, nhận hàng xong gửi trả món đó.",
       [E("place_order", ["shirt", "cap"]), E("deliver"), E("return_items", ["cap"], flag="tag")],
       [E("place_order", ["shirt"]), E("deliver"), E("place_order", ["cap"]), E("deliver"),
        E("return_items", ["cap"], flag="tag")],
       [L("deduct_shipping_if_below_threshold_after_return")],
       "Nếu sau khi trả đơn còn dưới ngưỡng thì trừ phí ship chiều đi vào tiền hoàn.",
       "Khách trả hàng thật sự sẽ nhận lại ít hơn 30k"),
    _x("wardrobe", ["return"], "Mặc xong rồi trả", "Mặc đi tiệc xong trả",
       "Mua váy mặc đi tiệc, hôm sau gửi trả miễn phí.",
       [E("place_order", ["dress"]), E("deliver"), E("return_items", ["dress"], flag="no_tag")], [],
       [L("require_tag_on_return")], "Chỉ nhận trả khi còn nguyên tag.", "Khách lỡ cắt tag sẽ không trả được"),
    _x("swap", ["return"], "Trả hàng tráo", "Trả cái quần cũ thay vào",
       "Gửi trả một món cũ hoặc hàng nhái thay cho món mới đã nhận.",
       [E("place_order", ["jeans"]), E("deliver"), E("return_items", ["jeans"], flag="swapped")], [],
       [L("inspect_before_refund")], "Kiểm tra hàng trả về và đối chiếu tem của shop trước khi hoàn tiền.",
       "Hoàn tiền chậm hơn 1–2 ngày"),
    _x("multiacc", ["newbie"], "Tạo nhiều tài khoản", "Acc thứ 3 rồi nè",
       "Lập tài khoản mới mỗi lần mua để lấy lại mã khách mới.",
       [x for _ in range(3) for x in (E("create_account", flag="same_phone"), E("place_order", ["shirt"]), E("deliver"))],
       [E("create_account", flag="new_phone")] + [x for _ in range(3) for x in (E("place_order", ["shirt"]), E("deliver"))],
       [L("new_customer_once_per_phone")], "Mỗi số điện thoại và địa chỉ giao chỉ dùng mã khách mới một lần.",
       "Hai người dùng chung số sẽ chỉ một người được mã"),
    _x("resell", ["flash"], "Gom hàng đi bán lại", "Ôm 20 cái đi bán lại",
       "Mua sạch áo flash sale để bán lại giá cao trên mạng.",
       [E("place_order", ["tee"] * 20, flag="prepaid,flash")], [E("place_order", ["tee"] * 2, flag="prepaid,flash")],
       [L("max_flash_qty_per_customer", 2)], "Mỗi khách mua tối đa 2 sản phẩm flash sale.", "Không đáng kể"),
    _x("bot", ["flash"], "Dùng tool săn hàng", "Tool bấm 0,1 giây",
       "Chạy tool tự động bấm mua ở giây đầu tiên, khách thật vào thì đã hết hàng.",
       [E("place_order", ["tee"] * 10, flag="prepaid,flash,bot")], [E("place_order", ["tee"] * 2, flag="prepaid,flash")],
       [L("random_queue_flash")], "Xếp hàng ngẫu nhiên trong 30 giây đầu thay vì ai nhanh người đó được.",
       "Khách bấm nhanh không còn lợi thế"),
    _x("codhold", ["flash", "cod"], "Giữ hàng bằng COD", "Đặt COD giữ chỗ đã",
       "Đặt hết áo flash sale bằng COD để giữ chỗ, sau đó đổi ý thì không nhận.",
       [E("place_order", ["tee"] * 10, flag="cod,flash"), E("refuse_delivery")], [],
       [L("flash_requires_prepay")], "Flash sale bắt buộc thanh toán trước.", "Khách không có ví điện tử khó mua flash"),
    _x("giftpick", ["bogo"], "Chọn quà đắt nhất", "Quà là cái váy nha",
       "Mua 2 món rẻ nhất, rồi chọn món tặng là chiếc váy đắt nhất shop.",
       [E("place_order", ["socks", "socks"]), E("choose_gift", ["dress"]), E("deliver")],
       [E("place_order", ["socks", "socks"]), E("choose_gift", ["socks"]), E("deliver")],
       [L("gift_price_lte_min_item")], "Món tặng phải có giá bằng hoặc thấp hơn món rẻ nhất trong đơn.", "Không đáng kể"),
    _x("giftret", ["bogo", "return"], "Giữ quà, trả hàng", "Trả 2 món, giữ quà",
       "Mua 2 nhận 1 món tặng, rồi trả 2 món đã mua để lấy lại tiền nhưng giữ món tặng.",
       [E("place_order", ["shirt", "shirt"]), E("choose_gift", ["shirt"]), E("deliver"),
        E("return_items", ["shirt", "shirt"], flag="tag")], [],
       [L("return_requires_gift")], "Trả hàng phải trả kèm món tặng, không thì trừ giá món tặng vào tiền hoàn.",
       "Khách làm hỏng quà sẽ bị trừ tiền"),
    _x("buy2ret1", ["combo", "return"], "Mua 2 trả 1", "Mua 2 trả 1, lời 10%",
       "Mua 2 món để được giảm giá, rồi trả 1 món nhưng vẫn giữ phần giảm trên món còn lại.",
       [E("place_order", ["shirt", "jeans"]), E("deliver"), E("return_items", ["jeans"], flag="tag")],
       [E("place_order", ["shirt"]), E("deliver"), E("place_order", ["jeans"]), E("deliver"),
        E("return_items", ["jeans"], flag="tag")],
       [L("clawback_discount_on_partial_return")], "Khi trả bớt món, thu lại phần giảm giá combo.",
       "Khách trả 1 món vì lỗi size sẽ nhận lại ít hơn một chút"),
    _x("coinret", ["points", "return"], "Lấy xu rồi trả hàng", "Xu về rồi, trả hàng",
       "Mua để nhận xu, tiêu xu ngay, rồi trả hàng lấy lại toàn bộ tiền.",
       [E("place_order", ["dress"]), E("deliver"), E("spend_coins"), E("return_items", ["dress"], flag="tag")],
       [E("place_order", ["dress"]), E("deliver"), E("return_items", ["dress"], flag="tag")],
       [L("coins_after_return_window")], "Chỉ cộng xu sau khi hết hạn đổi trả.", "Khách phải chờ 7 ngày mới có xu"),
    _x("selfref", ["referral"], "Tự giới thiệu chính mình", "Mình giới thiệu mình",
       "Tạo tài khoản phụ, tự giới thiệu để nhận thưởng cả hai phía.",
       [E("refer", amount=1, flag="self")], [],
       [L("referral_requires_distinct_person")],
       "Chỉ thưởng khi người được giới thiệu khác số điện thoại, khác thiết bị và đã nhận hàng.", "Không đáng kể"),
    _x("reffarm", ["referral"], "Rải mã lên hội nhóm", "Mã mình trên 50 group",
       "Đăng mã giới thiệu lên các group săn sale, nhận thưởng từ người vốn đã định mua.",
       [E("refer", amount=30, flag="public")], [],
       [L("referral_invite_only")], "Chỉ thưởng cho lời mời gửi trực tiếp trong app, mã dán công khai không được thưởng.",
       "Chương trình lan chậm hơn"),
    _x("bomb", ["cod"], "Bom hàng COD", "Đặt chơi, không nhận",
       "Đặt hàng COD rồi không nhận, shop chịu phí ship hai chiều.",
       [x for _ in range(5) for x in (E("place_order", ["dress"], flag="cod"), E("refuse_delivery"))], [],
       [L("prepay_after_failed_cod", 1)], "Khách đã bom một đơn thì phải thanh toán trước cho đơn sau.",
       "Khách lỡ bận không nhận một lần cũng phải trả trước"),
    _x("bombnew", ["cod"], "Đổi acc để bom tiếp", "Acc mới, bom tiếp",
       "Bị chặn COD thì tạo tài khoản mới cùng số điện thoại để tiếp tục bom hàng.",
       [x for _ in range(4) for x in (E("create_account", flag="same_phone"), E("place_order", ["dress"], flag="cod"),
                                      E("refuse_delivery"))], [],
       [L("prepay_after_failed_cod", 1), L("cod_blacklist_by_phone")],
       "Ghi nhận bom hàng theo số điện thoại và địa chỉ, không theo tài khoản.", "Không đáng kể"),
    _x("fakeprice", ["pricematch"], "Ảnh chụp giá giả", "Ảnh này thật mà",
       "Sửa ảnh chụp màn hình một shop khác với giá rẻ hơn để đòi hoàn chênh lệch.",
       [E("place_order", ["jeans"]), E("deliver"), E("claim_price_match", ["jeans"], amount=250000, flag="screenshot")],
       [E("place_order", ["jeans"]), E("deliver")],
       [L("price_match_live_listing_only")], "Chỉ nhận link sản phẩm còn bán trên sàn, hệ thống tự kiểm tra giá.",
       "Khách phải gửi link thay vì ảnh"),
    _x("selfmatch", ["pricematch", "flash"], "So với chính flash sale", "Shop mình bán 99k mà",
       "Mua áo giá gốc, rồi đòi hoàn chênh lệch so với giá flash sale của chính shop.",
       [E("place_order", ["tee"]), E("deliver"), E("claim_price_match", ["tee"], amount=99000, flag="own_flash")],
       [E("place_order", ["tee"]), E("deliver")],
       [L("price_match_excludes_own_flash")], "Không áp dụng cam kết giá với flash sale của chính shop.", "Không đáng kể"),
    _x("reviewspam", ["review"], "Đánh giá rác", "\"Shop uy tín\" x5",
       "Viết đánh giá 5 sao copy-paste một câu cho mọi đơn để lấy thưởng.",
       [x for _ in range(5) for x in (E("place_order", ["socks"]), E("deliver"),
                                      E("write_review", amount=5, flag="copy_paste"))],
       [x for _ in range(5) for x in (E("place_order", ["socks"]), E("deliver"))],
       [L("review_requires_photo_and_length")], "Chỉ thưởng đánh giá có ảnh thật và đủ 20 chữ.",
       "Ít khách viết đánh giá hơn"),
    _x("reviewret", ["review", "return"], "5 sao rồi trả hàng", "Lấy thưởng xong trả",
       "Đánh giá 5 sao ngay khi nhận để lấy thưởng, sau đó vẫn trả hàng.",
       [E("place_order", ["jeans"]), E("deliver"), E("write_review", amount=5, flag="genuine"),
        E("return_items", ["jeans"], flag="tag")],
       [E("place_order", ["jeans"]), E("deliver"), E("return_items", ["jeans"], flag="tag")],
       [L("review_reward_after_return_window")], "Chỉ phát thưởng đánh giá sau khi hết hạn đổi trả.",
       "Khách chờ 7 ngày mới nhận thưởng"),
]
KNOWN_BY_ID = {x["id"]: x for x in KNOWN}


def _rule_ids_for(needs: List[str], rules: List[Rule]) -> List[str]:
    out = []
    for n in needs:
        for r in rules:
            if n in kinds_of(r):
                out.append(r.id)
                break
    return out


def redteam_fallback(active: List[Rule], new_rule: Rule) -> List[Exploit]:
    all_rules = active + [new_rule]
    have: Set[str] = set().union(*(kinds_of(r) for r in all_rules))
    fresh = kinds_of(new_rule)
    out = []
    for x in KNOWN:
        if set(x["needs"]) <= have and fresh & set(x["needs"]):
            out.append(Exploit(id=x["id"], name=x["name"], bubble=x["bubble"], how=x["how"],
                               rule_ids=_rule_ids_for(x["needs"], all_rules), events=x["events"],
                               honest_events=x["honest"]))
    return out


def patch_fallback(rule: Rule, exploit_ids: List[str]):
    r = copy.deepcopy(rule)
    fixes = []
    for eid in exploit_ids:
        x = KNOWN_BY_ID.get(eid)
        if not x:
            continue
        for lim in x["limits"]:
            if not any(l.type == lim.type for l in r.limits):
                r.limits.append(lim)
        fixes.append(Fix(exploit_id=eid, explanation=x["fix"], tradeoff=x["tradeoff"]))
    return r, fixes
