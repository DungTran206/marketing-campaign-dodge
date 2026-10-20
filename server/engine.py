"""Bộ máy luật: chạy một chuỗi sự kiện của một khách qua bộ luật, tính shop lời hay lỗ.

Mẹo lách chỉ được tính khi chạy ra lỗ thật so với một khách bình thường có cùng nhu cầu.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .schema import ActionType, Event, EventType, FieldName, LimitType, Op, Rule

SHIP = 30_000  # phí vận chuyển mỗi chiều

CATALOG: Dict[str, dict] = {
    "tee":   {"name": "Áo thun basic", "price": 150_000, "cost": 110_000, "flash": True},
    "shirt": {"name": "Sơ mi",         "price": 250_000, "cost": 120_000},
    "jeans": {"name": "Quần jeans",    "price": 320_000, "cost": 160_000},
    "dress": {"name": "Váy dự tiệc",   "price": 450_000, "cost": 220_000},
    "cap":   {"name": "Mũ lưỡi trai",  "price": 90_000,  "cost": 40_000},
    "socks": {"name": "Tất",           "price": 40_000,  "cost": 15_000},
}

VERIFY_MIN_LOSS = 10_000      # lỗ ít nhất ngần này mới coi là mẹo thật
BLOCKED_RATIO = 0.25          # vá xong còn lỗ không quá 25% so với trước (hoặc dưới 10k) là chặn được


def _num(s: str) -> Optional[float]:
    try:
        return float(str(s).replace(".", "").replace(",", ""))
    except ValueError:
        return None


def _n(v) -> Optional[float]:
    """Giá trị số của một giới hạn; None nếu giới hạn không có con số."""
    if v is None or isinstance(v, bool):
        return None
    return float(v)


def _cmp(a, op: Op, b) -> bool:
    if isinstance(a, bool) or isinstance(a, str):
        if isinstance(a, bool):
            b = str(b).strip().lower() == "true"
        else:
            b = str(b).strip().lower()
        return a == b if op in (Op.eq, Op.gte, Op.lte) else a != b
    bn = _num(b)
    if bn is None:
        return False
    return {Op.gte: a >= bn, Op.gt: a > bn, Op.lte: a <= bn, Op.lt: a < bn, Op.eq: a == bn, Op.neq: a != bn}[op]


class Sim:
    def __init__(self, rules: List[Rule]):
        self.rules = rules
        self.paid = self.refunds = self.carrier = self.cogs = self.rewards = 0.0
        self.orders: List[dict] = []
        self.log: List[str] = []
        self.new_account_pending = False
        self.phone_flag = "new_phone"
        self.account_no = 0
        self.failed_cod: Dict[int, int] = {}
        self.newbie_used = False
        self.returns = 0
        self.flash_qty = 0
        self.coins_balance = 0.0
        self.referral_count = 0

    # ---------- rule helpers ----------
    def limit(self, t: LimitType):
        """Giới hạn áp dụng chung: luật nào đang bật có giới hạn này là có hiệu lực."""
        for r in self.rules:
            for l in r.limits:
                if l.type == t:
                    return l.value if l.value is not None else True
        return None

    def has_action(self, t: ActionType):
        for r in self.rules:
            for a in r.actions:
                if a.type == t:
                    return r, a
        return None

    def matching(self, ctx: dict):
        for r in self.rules:
            if all(_cmp(ctx[c.field.value], c.op, c.value) for c in r.conditions):
                for a in r.actions:
                    yield r, a

    @staticmethod
    def threshold(rule: Rule, field: FieldName) -> Optional[float]:
        for c in rule.conditions:
            if c.field == field and c.op in (Op.gte, Op.gt):
                return _num(c.value)
        return None

    # ---------- pricing ----------
    def _order_ctx(self, items: List[str], payment: str, prices: List[float]) -> dict:
        return {
            "cart_total": sum(prices),
            "item_count": len(items),
            "is_new_account": self.new_account_pending,
            "payment_method": payment,
            "has_flash_item": any(CATALOG[i].get("flash") for i in items),
        }

    def _price_order(self, o: dict):
        ctx = self._order_ctx(o["items"], o["payment"], o["prices"])
        subtotal = ctx["cart_total"]
        discounts = []
        o["ship_free"] = o.get("ship_free_locked", False)
        o["pct"] = 0.0
        o["gift_allowed"] = 0
        o["coins_pct"] = 0.0
        for r, a in self.matching(ctx):
            if a.type == ActionType.discount_pct and a.value:
                discounts.append(("pct", subtotal * a.value / 100))
                o["pct"] = a.value
                o["combo_min"] = self.threshold(r, FieldName.item_count) or 0
            elif a.type == ActionType.discount_vnd and a.value:
                if self.limit(LimitType.new_customer_once_per_phone) and any(
                    c.field == FieldName.is_new_account for c in r.conditions
                ):
                    if o.get("newbie_applied") is None:
                        if self.newbie_used:
                            self.log.append("Mã khách mới bị từ chối: số điện thoại đã dùng mã")
                            o["newbie_applied"] = False
                            continue
                        self.newbie_used = True
                        o["newbie_applied"] = True
                    elif not o["newbie_applied"]:
                        continue
                discounts.append(("vnd", min(a.value, subtotal)))
            elif a.type == ActionType.free_shipping:
                if not o.get("ship_checked"):
                    o["ship_free"] = True
                    o["ship_free_locked"] = True
                    o["ship_threshold"] = self.threshold(r, FieldName.cart_total)
            elif a.type == ActionType.free_item and a.value:
                o["gift_allowed"] = int(a.value)
            elif a.type == ActionType.coins_pct and a.value:
                o["coins_pct"] = a.value
        o["ship_checked"] = True
        cap = self.limit(LimitType.max_discounts_per_order)
        if cap and len(discounts) > int(cap):
            discounts = sorted(discounts, key=lambda d: -d[1])[: int(cap)]
            self.log.append("Chỉ áp dụng ưu đãi lớn nhất cho đơn")
        if not any(k == "pct" for k, _ in discounts):
            o["pct"] = 0.0
        o["subtotal"] = subtotal
        o["discount"] = min(sum(v for _, v in discounts), subtotal)
        o["ship_fee"] = 0 if o["ship_free"] else SHIP
        o["due"] = o["subtotal"] - o["discount"] + o["ship_fee"]

    # ---------- events ----------
    def place_order(self, e: Event):
        flags = (e.flag or "prepaid").split(",")
        payment = "cod" if "cod" in flags else "prepaid"
        in_flash = "flash" in flags
        items = [i for i in e.items if i in CATALOG]
        if not items:
            self.log.append("Đơn rỗng, bỏ qua")
            return
        flash = self.has_action(ActionType.flash_price)
        prices = []
        kept = []
        for i in items:
            p = CATALOG[i]["price"]
            if in_flash and flash and CATALOG[i].get("flash") and flash[1].value:
                cap = _n(self.limit(LimitType.max_flash_qty_per_customer))
                if "bot" in flags and self.limit(LimitType.random_queue_flash):
                    cap = 2 if cap is None else min(cap, 2)
                if cap is not None and self.flash_qty >= cap:
                    continue
                self.flash_qty += 1
                p = flash[1].value
            kept.append(i)
            prices.append(p)
        if len(kept) < len(items):
            self.log.append(f"Giới hạn flash sale: chỉ mua được {len(kept)}/{len(items)} món")
        if not kept:
            return
        if payment == "cod":
            if not self.has_action(ActionType.cod_allowed):
                self.log.append("Shop không nhận COD, đơn bị từ chối")
                return
            if self.limit(LimitType.flash_requires_prepay) and in_flash and any(CATALOG[i].get("flash") for i in kept):
                self.log.append("Flash sale phải trả trước, đơn COD bị từ chối")
                return
            if self.limit(LimitType.prepay_after_failed_cod):
                n = _n(self.limit(LimitType.prepay_after_failed_cod)) or 1
                key = -1 if self.limit(LimitType.cod_blacklist_by_phone) else self.account_no
                if self.failed_cod.get(key, 0) >= n:
                    self.log.append("Khách từng bom hàng, đơn COD bị từ chối")
                    return
        o = {"items": kept, "prices": prices, "payment": payment, "gift": None, "delivered": False,
             "refused": False, "returned": [], "coins": 0.0, "review_reward": 0.0, "paid": 0.0,
             "account": self.account_no}
        self._price_order(o)
        self.new_account_pending = False
        if payment == "prepaid":
            self.paid += o["due"]
            o["paid"] = o["due"]
        self.orders.append(o)

    def _last(self, delivered: Optional[bool] = None) -> Optional[dict]:
        for o in reversed(self.orders):
            if o["refused"]:
                continue
            if delivered is None or o["delivered"] == delivered:
                return o
        return None

    def choose_gift(self, e: Event):
        o = self._last(False)
        if not o or not o["gift_allowed"] or not e.items or e.items[0] not in CATALOG:
            return
        g = e.items[0]
        if self.limit(LimitType.gift_price_lte_min_item):
            cheapest = min(o["items"], key=lambda i: CATALOG[i]["price"])
            if CATALOG[g]["price"] > CATALOG[cheapest]["price"]:
                self.log.append("Quà phải rẻ hơn hoặc bằng món rẻ nhất, đổi sang " + CATALOG[cheapest]["name"])
                g = cheapest
        o["gift"] = g

    def cancel_items(self, e: Event):
        o = self._last(False)
        if not o:
            return
        for i in e.items:
            if i in o["items"]:
                k = o["items"].index(i)
                o["items"].pop(k)
                o["prices"].pop(k)
        before_due = o["due"]
        if self.limit(LimitType.recheck_after_cancel) and o.get("ship_threshold"):
            if sum(o["prices"]) < o["ship_threshold"]:
                o["ship_free_locked"] = False
                o["ship_checked"] = False
                self.log.append("Huỷ bớt xong đơn dưới ngưỡng, freeship bị tính lại")
        self._price_order(o)
        if o["payment"] == "prepaid":
            self.paid += o["due"] - before_due
            o["paid"] += o["due"] - before_due

    def deliver(self, e: Optional[Event] = None):
        o = self._last(False)
        if o:
            self._deliver_order(o)

    def _deliver_order(self, o: dict):
        if o["gift_allowed"] and not o["gift"]:
            o["gift"] = min(o["items"], key=lambda i: CATALOG[i]["price"])
        o["delivered"] = True
        self.carrier += SHIP
        self.cogs += sum(CATALOG[i]["cost"] for i in o["items"])
        if o["gift"]:
            self.cogs += CATALOG[o["gift"]]["cost"]
        if o["payment"] == "cod":
            self.paid += o["due"]
            o["paid"] = o["due"]
        if o["coins_pct"] and not self.limit(LimitType.coins_after_return_window):
            o["coins"] = (o["subtotal"] - o["discount"]) * o["coins_pct"] / 100
            self.coins_balance += o["coins"]

    def refuse_delivery(self, e: Event):
        o = self._last(False)
        if not o:
            return
        o["refused"] = True
        self.carrier += 2 * SHIP
        key = -1 if self.limit(LimitType.cod_blacklist_by_phone) else o["account"]
        self.failed_cod[key] = self.failed_cod.get(key, 0) + 1

    def _ensure_delivered(self):
        if self._last(False):
            self.deliver()

    def return_items(self, e: Event):
        self._ensure_delivered()
        o = self._last(True)
        if not o:
            return
        if not self.has_action(ActionType.free_return):
            self.log.append("Shop không có chính sách đổi trả, không trả được")
            return
        flag = e.flag or "tag"
        if flag == "no_tag" and self.limit(LimitType.require_tag_on_return):
            self.log.append("Hàng trả mất tag, bị từ chối")
            return
        if flag == "swapped" and self.limit(LimitType.inspect_before_refund):
            self.log.append("Kiểm tra thấy hàng bị tráo, không hoàn tiền")
            return
        cap = _n(self.limit(LimitType.max_returns_per_month))
        if cap is not None and self.returns >= cap:
            self.log.append("Vượt số lần trả hàng trong tháng")
            return
        avail = list(zip(o["items"], o["prices"]))
        for i in o["returned"]:
            for k, (it, _) in enumerate(avail):
                if it == i:
                    avail.pop(k)
                    break
        ret = []
        for i in e.items:
            for k, (it, p) in enumerate(avail):
                if it == i:
                    ret.append((it, p))
                    avail.pop(k)
                    break
        if not ret:
            return
        sub = o["subtotal"] or 1
        ret_value = sum(p for _, p in ret)
        refund = ret_value - o["discount"] * ret_value / sub
        remaining = [it for it, _ in avail]
        rem_value = sum(p for _, p in avail)
        ret = [it for it, _ in ret]
        if o["pct"] and self.limit(LimitType.clawback_discount_on_partial_return) and len(remaining) < o.get("combo_min", 0):
            claw = o["discount"] * rem_value / sub
            refund -= claw
            self.log.append(f"Thu lại giảm giá combo {claw:,.0f}đ")
        if o["ship_free"] and o.get("ship_threshold") and rem_value < o["ship_threshold"] and remaining and \
                self.limit(LimitType.deduct_shipping_if_below_threshold_after_return):
            refund -= SHIP
            self.log.append("Đơn còn lại dưới ngưỡng freeship, trừ phí ship vào tiền hoàn")
        if o["gift"] and not remaining and self.limit(LimitType.return_requires_gift):
            refund -= CATALOG[o["gift"]]["price"]
            self.log.append("Giữ lại quà tặng nên bị trừ giá quà")
        # hoàn xu chưa tiêu nếu trả cả đơn
        if not remaining and o["coins"]:
            back = min(self.coins_balance, o["coins"])
            self.coins_balance -= back
            o["coins"] -= back
        self.refunds += max(0.0, refund)
        self.carrier += SHIP
        for i in ret:
            c = CATALOG[i]["cost"]
            self.cogs -= c if flag == "tag" else (0.5 * c if flag == "no_tag" else 0)
        o["returned"].extend(ret)
        self.returns += 1

    def spend_coins(self, e: Event):
        self.rewards += self.coins_balance
        self.coins_balance = 0.0

    def write_review(self, e: Event):
        self._ensure_delivered()
        o = self._last(True)
        hit = self.has_action(ActionType.review_voucher_vnd)
        if not o or not hit or (e.amount or 0) < 5 or o.get("reviewed"):
            return
        o["reviewed"] = True
        if (e.flag or "genuine") == "copy_paste" and self.limit(LimitType.review_requires_photo_and_length):
            self.log.append("Đánh giá không có ảnh hoặc quá ngắn, không được thưởng")
            return
        if self.limit(LimitType.review_reward_after_return_window):
            o["review_reward"] = hit[1].value or 0
        else:
            self.rewards += hit[1].value or 0

    def claim_price_match(self, e: Event):
        self._ensure_delivered()
        o = self._last(True)
        if not o or not self.has_action(ActionType.price_match) or not e.items:
            return
        flag = e.flag or "live_listing"
        if flag == "screenshot" and self.limit(LimitType.price_match_live_listing_only):
            self.log.append("Chỉ nhận link sản phẩm còn bán, ảnh chụp bị từ chối")
            return
        if flag == "own_flash" and self.limit(LimitType.price_match_excludes_own_flash):
            self.log.append("Không so giá với flash sale của chính shop")
            return
        item = e.items[0]
        if item not in o["items"]:
            return
        paid_price = dict(zip(o["items"], o["prices"]))[item]
        self.refunds += max(0.0, paid_price - (e.amount or paid_price))

    def refer(self, e: Event):
        hit = self.has_action(ActionType.referral_reward_vnd)
        if not hit:
            return
        flag = e.flag or "invite"
        if flag == "self" and self.limit(LimitType.referral_requires_distinct_person):
            self.log.append("Người được giới thiệu trùng thiết bị và SĐT, không thưởng")
            return
        if flag == "public" and self.limit(LimitType.referral_invite_only):
            self.log.append("Mã dán công khai không được thưởng")
            return
        self.rewards += 2 * (hit[1].value or 0) * max(1, int(e.amount or 1))

    def create_account(self, e: Event):
        self.account_no += 1
        self.new_account_pending = True
        self.phone_flag = e.flag or "new_phone"

    def finish(self):
        for o in list(self.orders):
            if not o["delivered"] and not o["refused"]:
                self._deliver_order(o)
        for o in self.orders:
            if not o["delivered"]:
                continue
            fully_returned = o["returned"] and len(o["returned"]) >= len(o["items"])
            if o["review_reward"] and not o["returned"]:
                self.rewards += o["review_reward"]
            if o["coins_pct"] and self.limit(LimitType.coins_after_return_window) and not fully_returned:
                self.rewards += (o["subtotal"] - o["discount"]) * o["coins_pct"] / 100
        self.rewards += self.coins_balance  # xu chưa tiêu vẫn là khoản shop nợ khách
        self.coins_balance = 0

    def profit(self) -> float:
        return self.paid - self.refunds - self.carrier - self.cogs - self.rewards


HANDLERS = {
    EventType.create_account: Sim.create_account,
    EventType.place_order: Sim.place_order,
    EventType.choose_gift: Sim.choose_gift,
    EventType.cancel_items: Sim.cancel_items,
    EventType.deliver: Sim.deliver,
    EventType.refuse_delivery: Sim.refuse_delivery,
    EventType.return_items: Sim.return_items,
    EventType.spend_coins: Sim.spend_coins,
    EventType.write_review: Sim.write_review,
    EventType.claim_price_match: Sim.claim_price_match,
    EventType.refer: Sim.refer,
}


def simulate(rules: List[Rule], events: List[Event]) -> dict:
    s = Sim(rules)
    for e in events:
        HANDLERS[e.type](s, e)
    s.finish()
    return {
        "profit": round(s.profit()),
        "paid": round(s.paid), "refunds": round(s.refunds), "carrier": round(s.carrier),
        "cogs": round(s.cogs), "rewards": round(s.rewards), "log": s.log,
    }


def measure(rules: List[Rule], events: List[Event], honest: List[Event]) -> dict:
    """Thiệt hại = lợi nhuận với khách bình thường - lợi nhuận với kẻ lách luật."""
    ex = simulate(rules, events)
    ho = simulate(rules, honest)
    loss = ho["profit"] - ex["profit"]
    return {"loss": loss, "exploit_profit": ex["profit"], "honest_profit": ho["profit"],
            "verified": loss >= VERIFY_MIN_LOSS, "log": ex["log"]}


def is_blocked(loss_before: float, loss_after: float) -> bool:
    return loss_after < VERIFY_MIN_LOSS or loss_after <= BLOCKED_RATIO * loss_before
