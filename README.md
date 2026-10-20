# Shop và Kẻ Lách Luật

Chủ shop gõ một chính sách bằng tiếng Việt. AI dịch thành luật, cho "kẻ lách luật" tìm kẽ hở, bộ máy tính tiền chạy thử từng mẹo để xác minh shop lỗ thật, rồi AI đề xuất bản vá.

> **Lưu ý luật thi:** hackathon không cho nộp code viết sẵn. Bản này để cả team **tập dượt và hiểu cách làm**. Ngày thi phải dựng lại từ đầu bằng Codex.

## Chạy lần đầu (khoảng 10 phút)

Cần Python 3.11 trở lên.

```bash
cd shop-lach-luat
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

Tạo file cấu hình:

```bash
# Windows:      copy .env.example .env
# macOS/Linux:  cp .env.example .env
```

Mở file `.env`, dán API key vào sau `OPENAI_API_KEY=`. Chưa có key thì cứ để trống, game vẫn chạy ở chế độ dự phòng.

Chạy server:

```bash
uvicorn server.main:app --reload
```

Mở trình duyệt vào **http://localhost:8000**. Góc phải trên cho biết đang dùng OpenAI hay chế độ dự phòng.

## Thử gì đầu tiên

1. Gõ "mua 2 giảm 10%" → Dịch thành luật → Đúng ý, đưa vào phòng thử nghiệm → Ban hành.
2. Gõ "đổi trả miễn phí 7 ngày" → thử nghiệm. Kẻ lách luật sẽ tìm ra kiểu "mua 2 trả 1", do hai luật kết hợp.
3. Thử "Ban hành, không vá" để xem mẹo lan dần, rồi bật "AI tự vá".
4. Có API key rồi thì gõ chính sách lạ, ví dụ "khách VIP mua lần thứ 3 được tặng mũ", xem AI tự nghĩ ra mẹo gì ngoài 20 mẹo có sẵn.

## Cấu trúc

| File | Làm gì |
| --- | --- |
| `server/schema.py` | Khuôn luật: danh sách cố định các điều kiện, hành động, giới hạn, hành vi khách |
| `server/engine.py` | Bộ máy tính tiền: chạy chuỗi hành vi qua bộ luật, tính shop lời lỗ |
| `server/llm.py` | 3 vai gọi OpenAI: dịch luật, kẻ lách luật, người vá luật |
| `server/fallback.py` | 11 luật mẫu và 20 mẹo viết sẵn cho chế độ dự phòng |
| `server/main.py` | Server: các đường gọi `/api/...`, lưu kết quả vào `cache.json` |
| `static/index.html` | Trang game |
| `tests/test_engine.py` | Kiểm tra: 20 mẹo chưa vá phải lỗ, vá xong phải chặn được |

Chạy kiểm tra: `python -m pytest -q`

## Cách một mẹo được xác minh

Kẻ lách luật không chỉ mô tả mẹo bằng lời mà phải đưa ra **chuỗi hành vi cụ thể** (đặt đơn gì, trả món nào...) và chuỗi hành vi của **một khách bình thường** có cùng nhu cầu. Bộ máy tính tiền chạy cả hai:

- Shop lỗ hơn khách bình thường ít nhất 10.000đ → mẹo được tính.
- Không lỗ → mẹo bị loại, hiện dòng "Loại ..." trong phòng thử nghiệm.
- Sau khi vá, chạy lại đúng chuỗi đó: còn lỗ dưới 10.000đ hoặc giảm ít nhất 75% → coi là chặn được.

## Gặp lỗi

| Hiện tượng | Cách xử lý |
| --- | --- |
| Góc phải ghi "Không kết nối được server" | Server chưa chạy hoặc mở nhầm file. Phải mở qua http://localhost:8000, không mở file HTML trực tiếp |
| Ghi "Chế độ dự phòng" dù đã dán key | Kiểm tra file tên đúng là `.env` (không phải `.env.txt`), rồi tắt server chạy lại |
| Phòng thử nghiệm báo "Gọi OpenAI lỗi" | Đọc dòng lỗi: sai key, hết credit, hoặc tên model không tồn tại. Đổi `MODEL_FAST`, `MODEL_STRONG` trong `.env` theo trang model của OpenAI |
| Chờ lâu quá | Model mạnh có thể mất 20–60 giây. Lúc code thử đặt cả hai model là model rẻ |
| Muốn AI nghĩ lại từ đầu | Xoá file `cache.json` |

## Chi phí

Mỗi lần thử nghiệm một luật gọi OpenAI 2–3 lần, khoảng 0,10 USD với model mạnh. Nhớ **đặt giới hạn chi tiêu** trong trang quản lý tài khoản OpenAI.
