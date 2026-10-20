"""Ba vai LLM: người dịch luật, kẻ lách luật, người vá luật.

Mỗi vai là một lần gọi OpenAI Responses API với structured outputs, nên kết quả luôn đúng khuôn trong schema.py.
Không có API key hoặc chưa cài thư viện openai thì available() trả False và server dùng chế độ dự phòng.
"""
from __future__ import annotations

import json
import os
from typing import List

from .engine import CATALOG, SHIP
from .schema import PatchResult, RedteamResult, Rule, TranslateResult

MODEL_FAST = os.getenv("MODEL_FAST", "gpt-6-luna")
MODEL_STRONG = os.getenv("MODEL_STRONG", "gpt-6.1-sol")
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))

_client = None


def available() -> bool:
    if not os.getenv("OPENAI_API_KEY"):
        return False
    try:
        import openai  # noqa: F401
    except ImportError:
        return False
    return True


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(timeout=TIMEOUT, max_retries=1)
    return _client


def _call(model: str, system: str, user: str, fmt):
    resp = _get_client().responses.parse(
        model=model,
        input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        text_format=fmt,
    )
    if resp.output_parsed is None:
        raise RuntimeError("Model không trả về kết quả đúng khuôn")
    return resp.output_parsed


# ---------- mô tả khuôn cho LLM ----------
VOCAB = f"""
TRƯỜNG ĐIỀU KIỆN (conditions.field):
- cart_total: tổng tiền hàng trong đơn, VND (value viết số liền: 300000)
- item_count: số món trả tiền trong đơn
- is_new_account: "true"/"false", tài khoản mới tạo
- payment_method: "cod" hoặc "prepaid"
- has_flash_item: "true"/"false", đơn có áo flash sale
Phép so sánh (op): gte, gt, lte, lt, eq, neq.

HÀNH ĐỘNG (actions.type, value là con số hoặc null):
- free_shipping: shop trả phí ship chiều đi ({SHIP:,}đ)
- discount_pct: giảm value % tiền hàng
- discount_vnd: giảm value đồng
- free_item: tặng value món, khách tự chọn quà
- coins_pct: hoàn value % thành xu
- flash_price: áo flash sale có giá value đồng khi mua trong giờ vàng
- free_return: đổi trả miễn phí trong value ngày, shop trả ship chiều về
- referral_reward_vnd: thưởng value đồng cho mỗi bên khi giới thiệu thành công
- review_voucher_vnd: tặng value đồng khi đánh giá 5 sao
- price_match: khách chứng minh nơi khác rẻ hơn thì hoàn chênh lệch
- cod_allowed: cho thanh toán khi nhận hàng

GIỚI HẠN (limits.type, value là con số hoặc null) — dùng để vá luật:
- recheck_after_cancel: huỷ bớt món thì tính lại điều kiện freeship
- deduct_shipping_if_below_threshold_after_return: trả bớt làm đơn dưới ngưỡng freeship thì trừ phí ship vào tiền hoàn
- require_tag_on_return: chỉ nhận trả khi còn tag
- inspect_before_refund: kiểm tra hàng trả về trước khi hoàn tiền (chặn hàng tráo)
- max_returns_per_month: tối đa value lần trả mỗi tháng
- new_customer_once_per_phone: ưu đãi khách mới chỉ một lần mỗi số điện thoại/địa chỉ
- max_discounts_per_order: tối đa value ưu đãi giảm giá mỗi đơn
- max_flash_qty_per_customer: tối đa value áo flash sale mỗi khách
- random_queue_flash: xếp hàng ngẫu nhiên 30 giây đầu flash sale (chặn tool)
- flash_requires_prepay: flash sale phải trả trước
- gift_price_lte_min_item: quà tặng không đắt hơn món rẻ nhất trong đơn
- return_requires_gift: trả hàng phải trả kèm quà, không thì trừ giá quà
- clawback_discount_on_partial_return: trả bớt món thì thu lại giảm giá combo
- coins_after_return_window: chỉ cộng xu sau hạn đổi trả
- referral_requires_distinct_person: người được giới thiệu phải khác SĐT, thiết bị
- referral_invite_only: chỉ thưởng lời mời gửi trực tiếp, mã công khai không tính
- prepay_after_failed_cod: bom value đơn thì phải trả trước
- cod_blacklist_by_phone: ghi nhận bom hàng theo SĐT thay vì tài khoản
- price_match_live_listing_only: chỉ nhận link sản phẩm còn bán, không nhận ảnh chụp
- price_match_excludes_own_flash: không so giá với flash sale của chính shop
- review_requires_photo_and_length: chỉ thưởng đánh giá có ảnh và đủ 20 chữ
- review_reward_after_return_window: phát thưởng đánh giá sau hạn đổi trả
"""

EVENTS = """
HÀNH VI KHÁCH (events.type), items là mã sản phẩm, lặp lại để mua nhiều cái:
- create_account: flag "new_phone" hoặc "same_phone"
- place_order: items; flag "prepaid" hoặc "cod", thêm ",flash" nếu mua trong giờ flash sale, thêm ",bot" nếu dùng tool tự động
- choose_gift: items[0] là món chọn làm quà
- cancel_items: huỷ các món trước khi giao
- deliver: nhận đơn gần nhất
- refuse_delivery: không nhận đơn gần nhất (bom hàng)
- return_items: trả các món; flag "tag" (còn tag), "no_tag" (đã dùng, mất tag), "swapped" (tráo hàng khác)
- spend_coins: tiêu hết xu đang có
- write_review: amount = số sao; flag "genuine" hoặc "copy_paste"
- claim_price_match: items[0], amount = giá rẻ hơn khách đưa ra; flag "live_listing", "screenshot" hoặc "own_flash"
- refer: amount = số người được giới thiệu; flag "self" (acc phụ của chính mình), "invite" (bạn thật), "public" (mã dán lên hội nhóm)
"""


def _catalog_text() -> str:
    return "\n".join(f"- {k}: {v['name']}, giá {v['price']:,}đ" + (", áo flash sale" if v.get("flash") else "")
                     for k, v in CATALOG.items())


def translate(text: str) -> TranslateResult:
    system = ("Bạn chuyển chính sách bán hàng do chủ một shop thời trang online ở Việt Nam viết thành luật theo khuôn JSON.\n"
              "Chỉ dùng các trường, hành động trong danh sách dưới. Giữ đúng mọi con số chủ shop viết, đổi '300k' thành 300000. "
              "Không tự thêm điều kiện chủ shop không nói. limits để rỗng.\n"
              "Nếu câu mơ hồ hoặc không diễn đạt được bằng khuôn, đặt understood=false, rule=null và ghi question.\n"
              "id là slug ngắn không dấu. restatement nhắc lại luật bằng một câu tiếng Việt đời thường.\n" + VOCAB)
    return _call(MODEL_FAST, system, f"Chính sách: {text}", TranslateResult)


def redteam(active: List[Rule], new_rule: Rule) -> RedteamResult:
    system = ("Bạn là khách hàng sành sỏi trong các hội nhóm săn sale ở Việt Nam, chuyên tìm kẽ hở trong chính sách của shop.\n"
              "Nhiệm vụ: tìm cách lợi dụng bộ luật để shop mất tiền, ưu tiên kẽ hở do LUẬT MỚI tạo ra, nhất là khi kết hợp "
              "với luật đang có. Chỉ dùng hành vi một khách bình thường làm được trên app (danh sách dưới). Không hack, "
              "không lừa đảo thẻ, không phạm pháp; chỉ lợi dụng câu chữ của chính sách.\n"
              "Mỗi mẹo cần: events là chuỗi hành vi cụ thể của kẻ lách luật; honest_events là chuỗi hành vi của một khách "
              "bình thường có cùng nhu cầu thật (ví dụ chỉ mua đúng món họ giữ lại; nếu trả hàng thì là trả hàng vì lý do "
              "chính đáng; nếu không có nhu cầu thật thì để rỗng). Hệ thống sẽ chạy cả hai chuỗi qua bộ máy tính tiền, "
              "mẹo nào không làm shop lỗ hơn khách bình thường sẽ bị loại, nên đừng bịa.\n"
              "Tối đa 5 mẹo, thực tế và gây lỗ nhiều nhất trước. bubble tối đa 6 chữ, giọng khách hàng. rule_ids là id "
              "các luật bị lợi dụng.\n" + VOCAB + EVENTS + "\nDANH MỤC SẢN PHẨM:\n" + _catalog_text())
    user = json.dumps({"luat_dang_bat": [r.model_dump(mode="json") for r in active],
                       "luat_moi": new_rule.model_dump(mode="json")}, ensure_ascii=False)
    return _call(MODEL_STRONG, system, user, RedteamResult)


def patch(rule: Rule, active: List[Rule], exploits: list) -> PatchResult:
    system = ("Bạn thiết kế chính sách cho shop. Dưới đây là một luật và các mẹo lách đã được xác minh là làm shop lỗ thật.\n"
              "Sửa luật để chặn từng mẹo: chỉ THÊM vào limits (có thể chỉnh conditions nếu thật cần), giữ nguyên id, tên, "
              "hành động chính. Thay đổi nhỏ nhất để khách mua bình thường gần như không bị ảnh hưởng. "
              "Giới hạn có hiệu lực cho toàn shop nên có thể dùng giới hạn liên quan tới luật khác.\n"
              "Mỗi mẹo một fix: explanation là một câu tiếng Việt cho chủ shop, tradeoff là cái giá phải trả.\n" + VOCAB)
    user = json.dumps({"luat_can_va": rule.model_dump(mode="json"),
                       "luat_khac_dang_bat": [r.model_dump(mode="json") for r in active],
                       "meo_da_xac_minh": exploits}, ensure_ascii=False)
    return _call(MODEL_STRONG, system, user, PatchResult)
