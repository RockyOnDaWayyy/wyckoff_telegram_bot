# Wyckoff & VSA Telegram Stock Analyzer Bot

Bot Telegram phân tích kỹ thuật chuyên sâu và khuyến nghị cổ phiếu tự động theo phương pháp **Wyckoff** và **VSA (Volume Spread Analysis)** cho sàn giao dịch HOSE. Bot được thiết kế để hỗ trợ nhà đầu tư ngắn hạn tìm kiếm điểm mua gom an toàn dựa trên quy luật Cung - Cầu và nỗ lực của dòng tiền thông minh (Smart Money).

---

## 🚀 Các Tính Năng Chính
1. **Phân tích Cấu trúc Wyckoff Tự động**: Nhận diện pha tích lũy (Phase A, B, C, D, E) và phát hiện các sự kiện quan trọng (Selling Climax - SCLX, Automatic Rally - AR, Spring, Sign of Strength - SOS, LPS/BUEC).
2. **Phân tích VSA (Volume Spread Analysis)**: Gắn nhãn các mẫu nến kỹ thuật chuyên sâu (Up-thrust, Pseudo Up-thrust, Stopping Volume, Spring Test, No Demand, Lack of Offer).
3. **Mô phỏng Định lượng 1 Tháng (Chống Overfitting)**: Tính toán hiệu suất ROI lịch sử, Tỉ lệ thắng (Win Rate) thực tế, và tỷ lệ Risk/Reward thực tế dựa trên mô phỏng nắm giữ 1 tháng cửa sổ trượt (rolling 1-month) trong 1 năm qua.
4. **Vẽ biểu đồ Wyckoff TV-Style**: Tự động tạo biểu đồ nến phong cách TradingView với tông tối chuyên nghiệp, đánh dấu các đường hỗ trợ/kháng cự động và gắn nhãn các sự kiện trực tiếp trên đồ thị.
5. **Tính năng Quét Thị trường (Market Scan)**: Tự động chạy quét toàn bộ sàn HOSE lúc 15h00 hàng ngày và lưu trữ danh sách mã khuyến nghị mua tốt nhất (ưu tiên Spring Type 3 cạn cung và SOS Breakout).
6. **Lệnh `/backtest <Mã>`**: Cho phép người dùng chạy mô phỏng kiểm thử lịch sử 1 năm trực tiếp trên bot đối với bất kỳ mã cổ phiếu nào để kiểm chứng hiệu quả trước khi giải ngân.

---

## 🛠️ Hướng Dẫn Cài Đặt

### 1. Chuẩn bị môi trường
Yêu cầu hệ thống đã cài đặt Python 3.10 trở lên.

```bash
# Clone repository về máy local
git clone <your-github-repo-url>
cd wyckoff_telegram_bot

# Khởi tạo môi trường ảo (venv)
python -m venv venv

# Kích hoạt môi trường ảo
# Trên Windows:
.\venv\Scripts\activate
# Trên macOS/Linux:
source venv/bin/activate

# Cài đặt các thư viện cần thiết
pip install -r requirements.txt
```

### 2. Cấu hình biến môi trường
Tạo file `.env` nằm ở thư mục gốc của dự án với các thông số sau:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id_for_notifications
```

---

## 💻 Hướng Dẫn Sử Dụng

### 1. Chạy ứng dụng locally
Chạy bot Telegram ở chế độ lắng nghe (polling):
```bash
python main.py
```

Chạy thử phân tích một mã cụ thể trên terminal:
```bash
python test_local.py
```

### 2. Các lệnh tương tác trên Telegram
*   `/start` - Khởi động bot và hiển thị danh sách lệnh.
*   `/analyze <MÃ_CP>` - Phân tích chi tiết, vẽ biểu đồ kỹ thuật và tính toán định lượng VaR/MDD (Ví dụ: `/analyze FPT`).
*   `/backtest <MÃ_CP>` - Chạy mô phỏng kiểm thử lịch sử 1 năm qua trên mã cổ phiếu đó (Ví dụ: `/backtest HPG`).
*   `/scan` - Xem kết quả quét và đề xuất mua mới nhất của sàn HOSE từ phiên giao dịch trước.
*   `/help` - Hướng dẫn chi tiết cách đọc hiểu các tín hiệu cấu trúc Wyckoff và nến VSA.

---

## 📊 Kết quả Mô phỏng Danh mục (Backtest)
Mô phỏng danh mục NAV 1 tỷ VND giải ngân tối đa 5 vị thế (20% NAV/vị thế) trên danh sách 20 cổ phiếu HOSE thanh khoản cao trong 1 năm (2025-2026):
*   **Tỷ suất lợi nhuận (ROI)**: **+8.74%**
*   **Tỷ lệ Risk/Reward thực tế**: **2.11:1** (Lãi trung bình khi thắng lớn hơn gấp đôi mức lỗ trung bình khi thua).
*   **Tỷ lệ thắng (Win Rate)**: **33.7%** (Chứng minh tính đúng đắn của việc quản trị rủi ro cắt lỗ sớm của Wyckoff).

---

## 📝 Giấy phép
Dự án được phân phối dưới giấy phép MIT License.
