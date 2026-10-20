"""Khuôn luật: mọi luật, mẹo lách và bản vá đều phải nằm trong các danh sách cố định dưới đây.

LLM chỉ được "điền vào khuôn". Nhờ vậy bộ máy luật (engine.py) luôn chạy được thứ LLM trả về.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class FieldName(str, Enum):
    cart_total = "cart_total"          # tổng tiền hàng trong đơn (VND)
    item_count = "item_count"          # số món trả tiền trong đơn
    is_new_account = "is_new_account"  # "true" / "false"
    payment_method = "payment_method"  # "cod" / "prepaid"
    has_flash_item = "has_flash_item"  # "true" / "false"


class Op(str, Enum):
    gte = "gte"
    gt = "gt"
    lte = "lte"
    lt = "lt"
    eq = "eq"
    neq = "neq"


class ActionType(str, Enum):
    free_shipping = "free_shipping"              # shop trả phí ship chiều đi
    discount_pct = "discount_pct"                # giảm value % tiền hàng
    discount_vnd = "discount_vnd"                # giảm value đồng
    free_item = "free_item"                      # tặng value món (khách chọn)
    coins_pct = "coins_pct"                      # hoàn value % thành xu
    flash_price = "flash_price"                  # áo flash sale có giá value đồng trong giờ vàng
    free_return = "free_return"                  # đổi trả miễn phí trong value ngày
    referral_reward_vnd = "referral_reward_vnd"  # thưởng value đồng cho mỗi bên khi giới thiệu
    review_voucher_vnd = "review_voucher_vnd"    # tặng value đồng khi đánh giá 5 sao
    price_match = "price_match"                  # thấy rẻ hơn thì hoàn chênh lệch
    cod_allowed = "cod_allowed"                  # cho thanh toán khi nhận hàng


class LimitType(str, Enum):
    recheck_after_cancel = "recheck_after_cancel"
    deduct_shipping_if_below_threshold_after_return = "deduct_shipping_if_below_threshold_after_return"
    require_tag_on_return = "require_tag_on_return"
    inspect_before_refund = "inspect_before_refund"
    max_returns_per_month = "max_returns_per_month"
    new_customer_once_per_phone = "new_customer_once_per_phone"
    max_discounts_per_order = "max_discounts_per_order"
    max_flash_qty_per_customer = "max_flash_qty_per_customer"
    random_queue_flash = "random_queue_flash"
    flash_requires_prepay = "flash_requires_prepay"
    gift_price_lte_min_item = "gift_price_lte_min_item"
    return_requires_gift = "return_requires_gift"
    clawback_discount_on_partial_return = "clawback_discount_on_partial_return"
    coins_after_return_window = "coins_after_return_window"
    referral_requires_distinct_person = "referral_requires_distinct_person"
    referral_invite_only = "referral_invite_only"
    prepay_after_failed_cod = "prepay_after_failed_cod"
    cod_blacklist_by_phone = "cod_blacklist_by_phone"
    price_match_live_listing_only = "price_match_live_listing_only"
    price_match_excludes_own_flash = "price_match_excludes_own_flash"
    review_requires_photo_and_length = "review_requires_photo_and_length"
    review_reward_after_return_window = "review_reward_after_return_window"


class Condition(BaseModel):
    field: FieldName
    op: Op
    value: str = Field(description='Số viết liền không dấu chấm (300000), hoặc "true"/"false", hoặc "cod"/"prepaid"')


class Action(BaseModel):
    type: ActionType
    value: Optional[float] = Field(description="Con số của hành động, null nếu không cần")


class Limit(BaseModel):
    type: LimitType
    value: Optional[float] = Field(description="Con số của giới hạn, null nếu không cần")


class Rule(BaseModel):
    id: str
    name: str = Field(description="Tên ngắn tiếng Việt, ví dụ 'Freeship đơn từ 300k'")
    conditions: List[Condition]
    actions: List[Action]
    limits: List[Limit]


class EventType(str, Enum):
    create_account = "create_account"        # flag: "new_phone" | "same_phone"
    place_order = "place_order"              # items; flag: "prepaid"/"cod", thêm ",flash" nếu mua giờ vàng, ",bot" nếu dùng tool
    choose_gift = "choose_gift"              # items[0] = món chọn làm quà
    cancel_items = "cancel_items"            # items huỷ trước khi giao
    deliver = "deliver"                      # nhận hàng
    refuse_delivery = "refuse_delivery"      # không nhận hàng (bom)
    return_items = "return_items"            # items; flag: "tag" | "no_tag" | "swapped"
    spend_coins = "spend_coins"              # tiêu hết xu đang có
    write_review = "write_review"            # amount = số sao; flag: "genuine" | "copy_paste"
    claim_price_match = "claim_price_match"  # items[0]; amount = giá rẻ hơn; flag: "live_listing" | "screenshot" | "own_flash"
    refer = "refer"                          # amount = số người; flag: "self" | "invite" | "public"


class Event(BaseModel):
    type: EventType
    items: List[str] = Field(description="Mã sản phẩm trong danh mục, lặp lại để mua nhiều cái")
    amount: Optional[float]
    flag: Optional[str]


class Exploit(BaseModel):
    id: str = Field(description="slug ngắn, chữ thường, gạch dưới")
    name: str = Field(description="Tên mẹo kiểu dân mạng hay gọi")
    bubble: str = Field(description="Câu khách nói, tối đa 6 chữ")
    how: str = Field(description="Một câu mô tả cách làm")
    rule_ids: List[str] = Field(description="id các luật bị lợi dụng")
    events: List[Event] = Field(description="Chuỗi hành động của kẻ lách luật")
    honest_events: List[Event] = Field(description="Chuỗi hành động của một khách bình thường có cùng nhu cầu, để so sánh")


class TranslateResult(BaseModel):
    understood: bool
    question: Optional[str] = Field(description="Nếu chưa hiểu: câu cần hỏi lại chủ shop")
    restatement: str = Field(description="Nhắc lại luật bằng một câu tiếng Việt đời thường")
    rule: Optional[Rule]


class RedteamResult(BaseModel):
    exploits: List[Exploit]


class Fix(BaseModel):
    exploit_id: str
    explanation: str = Field(description="Một câu tiếng Việt giải thích bản vá cho chủ shop")
    tradeoff: str = Field(description="Cái giá phải trả, ví dụ khách thật phiền hơn chỗ nào. Không có thì ghi 'Không đáng kể'")


class PatchResult(BaseModel):
    rule: Rule
    fixes: List[Fix]
