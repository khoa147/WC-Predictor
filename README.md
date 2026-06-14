# ⚽ WC2026 AI Predictor — Telegram Bot

Tự động phân tích và dự đoán kết quả World Cup 2026 bằng Claude AI, gửi qua Telegram lúc **14:00 giờ Việt Nam** mỗi ngày.

---

## 🚀 Setup (5 bước)

### Bước 1 — Tạo Telegram Bot

1. Mở Telegram, tìm **@BotFather**
2. Gửi `/newbot` → đặt tên → nhận **BOT_TOKEN** (dạng `123456:ABCdef...`)
3. Tìm **@userinfobot** → gửi bất kỳ tin nhắn → nhận **CHAT_ID** của bạn
   - Nếu muốn gửi vào group: thêm bot vào group, gửi tin nhắn, rồi vào:
     `https://api.telegram.org/bot<TOKEN>/getUpdates` để lấy group chat_id (số âm)

### Bước 2 — Lấy Anthropic API Key

1. Vào [console.anthropic.com](https://console.anthropic.com)
2. **API Keys** → **Create Key** → copy key

### Bước 3 — Tạo GitHub Repository

```bash
git init
git add .
git commit -m "init wc2026 predictor"
gh repo create wc2026-predictor --public --push
```

Hoặc tạo repo trên github.com rồi push lên.

### Bước 4 — Thêm Secrets vào GitHub

Vào repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Thêm 3 secrets:

| Secret name | Giá trị |
|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-...` |
| `TELEGRAM_BOT_TOKEN` | `123456:ABCdef...` |
| `TELEGRAM_CHAT_ID` | ID của bạn hoặc group |

### Bước 5 — Test chạy thủ công

Vào tab **Actions** → **WC2026 Daily Predictor** → **Run workflow** → **Run workflow**

Nếu thấy ✅ và có tin nhắn Telegram → thành công!

---

## ⏰ Lịch chạy tự động

Workflow chạy lúc **07:00 UTC = 14:00 giờ Việt Nam** mỗi ngày.

Muốn đổi giờ, sửa dòng `cron` trong `.github/workflows/daily_predict.yml`:
```yaml
- cron: "0 7 * * *"   # 14:00 VN
- cron: "0 6 * * *"   # 13:00 VN
- cron: "30 6 * * *"  # 13:30 VN
```

---

## 📱 Tin nhắn Telegram mẫu

```
⚽ DỰ ĐOÁN WORLD CUP 2026
📅 12/06/2026 — 2 trận
━━━━━━━━━━━━━━━━━━

1. Brazil 🆚 Mexico
🕐 22:00 VN  |  Group D

🏆 Brazil thắng  (2-0)
🟩🟩🟩🟩🟩🟩🟩⬜⬜⬜ 72%

📊 Brazil: 65%  |  Hòa: 20%  |  Mexico: 15%

📌 Yếu tố chính:
  • Brazil hàng công mạnh hơn rõ rệt
  • Mexico thiếu vắng trụ cột giữa sân
  • Lịch sử đối đầu nghiêng về Brazil

💬 Brazil đang trong phong độ cao...
━━━━━━━━━━━━━━━━━━
```

---

## 🔧 Cấu trúc dự án

```
wc2026-predictor/
├── .github/
│   └── workflows/
│       └── daily_predict.yml   # GitHub Actions cron job
├── src/
│   └── predictor.py            # Script chính
├── requirements.txt
└── README.md
```

---

<!-- updated -->
<!-- trigger cron -->


