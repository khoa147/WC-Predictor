
import os, json, requests, io, csv
from datetime import datetime, timezone, timedelta

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

VN_TZ = timezone(timedelta(hours=7))
K_FACTOR = {"FIFA World Cup": 60, "UEFA Euro": 50, "friendly": 20, "default": 40}
DEFAULT_ELO = 1500


def get_k(tournament: str) -> int:
    for key, val in K_FACTOR.items():
        if key.lower() in tournament.lower():
            return val
    return K_FACTOR["default"]


def expected_score(elo_a: float, elo_b: float) -> float:
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))


def compute_elo_ratings(rows: list) -> dict:
    ratings = {}
    for row in rows:
        home, away = row["home_team"], row["away_team"]
        try:
            hs, as_ = float(row["home_score"]), float(row["away_score"])
        except (ValueError, TypeError):
            continue
        r_h = ratings.get(home, DEFAULT_ELO)
        r_a = ratings.get(away, DEFAULT_ELO)
        neutral = row.get("neutral", "FALSE") == "TRUE"
        adj_h = r_h if neutral else r_h + 100
        e_h = expected_score(adj_h, r_a)
        s_h = 1.0 if hs > as_ else (0.5 if hs == as_ else 0.0)
        gd = abs(hs - as_)
        gd_mult = 1 if gd <= 1 else (1.5 if gd == 2 else (1.75 if gd == 3 else 1.75 + (gd-3)/8))
        k = get_k(row.get("tournament", ""))
        ratings[home] = r_h + k * gd_mult * (s_h - e_h)
        ratings[away] = r_a + k * gd_mult * ((1-s_h) - (1-e_h))
    return ratings


def predict_from_elo(elo_h: float, elo_a: float) -> dict:
    win_prob = expected_score(elo_h, elo_a)
    diff = abs(elo_h - elo_a)
    draw_prob = max(0.08, min(0.32, 0.28 - diff/4000))
    if win_prob > 0.5:
        home_win = win_prob - draw_prob / 2
        away_win = 1 - home_win - draw_prob
    else:
        away_win = (1 - win_prob) - draw_prob / 2
        home_win = 1 - away_win - draw_prob
    home_win = max(0.05, home_win)
    away_win = max(0.05, away_win)
    total = home_win + draw_prob + away_win
    return {
        "home_win_pct": round(home_win/total*100, 1),
        "draw_pct": round(draw_prob/total*100, 1),
        "away_win_pct": round(away_win/total*100, 1),
    }


def get_recent_form(rows: list, team: str, n: int = 5) -> str:
    matches = [r for r in rows
               if team in (r["home_team"], r["away_team"])
               and r["home_score"] not in ("", "NA")
               and r["away_score"] not in ("", "NA")][-n:]
    form = []
    for r in matches:
        try:
            hs, as_ = float(r["home_score"]), float(r["away_score"])
        except Exception:
            continue
        if r["home_team"] == team:
            form.append("W" if hs > as_ else ("D" if hs == as_ else "L"))
        else:
            form.append("W" if as_ > hs else ("D" if hs == as_ else "L"))
    return "".join(form) if form else "N/A"


def load_match_history() -> list:
    url = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return list(csv.DictReader(io.StringIO(resp.text)))


def parse_match_to_vn(m: dict) -> dict:
    """Chuyển trận đấu sang ngày + giờ Việt Nam thực tế"""
    date_str = m.get("date", "")
    time_str = m.get("time", "")
    try:
        tp, tz_p = time_str.split(" ")
        h, mi = map(int, tp.split(":"))
        tz_off = int(tz_p.replace("UTC", ""))
        utc_h = h - tz_off          # giờ UTC
        vn_h = (utc_h + 7) % 24     # giờ VN
        day_offset = (utc_h + 7) // 24  # sang ngày hôm sau nếu = 1
        base = datetime.strptime(date_str, "%Y-%m-%d")
        vn_date = (base + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        local_time = f"{vn_h:02d}:{mi:02d}"
    except Exception:
        vn_date = date_str
        local_time = "TBD"
    return {
        "home": m["team1"], "away": m["team2"],
        "time": local_time,
        "date_vn": vn_date,
        "stage": m.get("group", m.get("round", "World Cup 2026")),
    }


def get_dates_to_fetch() -> list:
    """PREDICT_DATE env → thứ 6 lấy 4 ngày → mặc định hôm nay (theo giờ VN)"""
    predict_date = os.environ.get("PREDICT_DATE", "").strip()
    if predict_date:
        print(f"📌 Chạy thủ công: {predict_date}")
        return [predict_date]
    now = datetime.now(VN_TZ)
    if now.weekday() == 4:  # Thứ 6
        return [(now + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(4)]
    return [now.strftime("%Y-%m-%d")]


def get_matches(dates: list) -> list:
    url = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    matches = []
    for m in data.get("matches", []):
        parsed = parse_match_to_vn(m)
        # Lọc theo ngày VN thực tế (không phải ngày gốc UTC)
        if parsed["date_vn"] in dates:
            matches.append(parsed)

    # Sắp xếp theo ngày VN rồi giờ VN
    matches.sort(key=lambda x: (x["date_vn"], x["time"]))
    print(f"✅ {len(matches)} trận (theo giờ VN)")
    return matches


def analyze_with_gemini(home, away, elo_h, elo_a, form_h, form_a, probs):
    import time
    prompt = f"""World Cup 2026: {home} vs {away}
ELO: {home}={round(elo_h)} | {away}={round(elo_a)}
Form 5 trận: {home}={form_h} | {away}={form_a}
Xác suất: {home} thắng {probs['home_win_pct']}% | Hòa {probs['draw_pct']}% | {away} thắng {probs['away_win_pct']}%

Viết 2 câu nhận xét ngắn tiếng Việt. Chỉ trả lời JSON:
{{"comment":"2 câu nhận xét","scoreline":"X-Y","confidence":{round(max(probs['home_win_pct'],probs['away_win_pct']))}}}"""

    for attempt in range(3):
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        if resp.status_code == 429:
            wait = 15 * (attempt + 1)
            print(f"  ⏳ Rate limit, chờ {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        break

    data = resp.json()
    if "candidates" not in data:
        raise ValueError(data.get("error", {}).get("message", str(data)))
    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except Exception:
        import re
        match = re.search(r"\{[\s\S]*\}", raw)
        return json.loads(match.group()) if match else {"comment": "", "scoreline": "?-?", "confidence": 50}


def format_message(results: list, dates: list) -> str:
    day_names = {0:"Thứ 2",1:"Thứ 3",2:"Thứ 4",3:"Thứ 5",4:"Thứ 6",5:"Thứ 7",6:"Chủ Nhật"}
    multi = len(dates) > 1

    if multi:
        d0 = datetime.strptime(dates[0], "%Y-%m-%d").strftime("%d/%m")
        d1 = datetime.strptime(dates[-1], "%Y-%m-%d").strftime("%d/%m/%Y")
        header = f"📅 {d0} - {d1} — {len(results)} trận"
    else:
        header = f"📅 {datetime.strptime(dates[0], '%Y-%m-%d').strftime('%d/%m/%Y')} — {len(results)} trận"

    lines = ["⚽ *DỰ ĐOÁN WORLD CUP 2026*", header, "━━━━━━━━━━━━━━━━━━"]

    current_date = None
    for i, item in enumerate(results, 1):
        m = item["match"]
        r = item["result"]
        home, away = m["home"], m["away"]
        probs = r["probs"]
        ai = r["ai"]

        # Header ngày mới
        if multi and m["date_vn"] != current_date:
            current_date = m["date_vn"]
            dt = datetime.strptime(current_date, "%Y-%m-%d")
            lines += ["", f"📆 *{day_names[dt.weekday()]} {dt.strftime('%d/%m')}*"]

        h_pct, d_pct, a_pct = probs["home_win_pct"], probs["draw_pct"], probs["away_win_pct"]
        winner_line = (f"🏆 *{home}* thắng" if h_pct > a_pct
                       else f"🏆 *{away}* thắng" if a_pct > h_pct
                       else "🤝 *Hòa*")
        conf = ai.get("confidence", round(max(h_pct, a_pct)))
        bar = "🟩" * round(conf/10) + "⬜" * (10 - round(conf/10))

        lines += [
            f"\n*{i}. {home} 🆚 {away}*",
            f"🕐 {m['time']} VN  |  {m['stage']}",
            "",
            f"{winner_line}  ({ai.get('scoreline','?-?')})",
            f"{bar} {conf}%",
            "",
            f"📊 {home}: {h_pct}%  |  Hòa: {d_pct}%  |  {away}: {a_pct}%",
            f"🔢 ELO: {home} *{round(r['elo_home'])}* vs {away} *{round(r['elo_away'])}*",
            f"📈 Form: {home} `{r['form_home']}`  |  {away} `{r['form_away']}`",
        ]
        if ai.get("comment"):
            lines += ["", f"💬 _{ai['comment']}_"]
        lines.append("━━━━━━━━━━━━━━━━━━")

    lines += ["", "🤖 _ELO + Gemini AI_", "_⚠️ Dự đoán tham khảo!_"]
    return "\n".join(lines)


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID, "text": message,
        "parse_mode": "Markdown", "disable_web_page_preview": True,
    }, timeout=15)
    resp.raise_for_status()
    print(f"✅ Telegram: {resp.json().get('ok')}")


def main():
    import time
    print(f"🚀 Bắt đầu {datetime.now(VN_TZ).strftime('%H:%M ngày %Y-%m-%d')}")

    print("📥 Tải lịch sử kết quả...")
    history = load_match_history()
    print(f"✅ {len(history)} trận lịch sử")

    print("⚙️ Tính ELO...")
    elo_ratings = compute_elo_ratings(history)

    dates = get_dates_to_fetch()
    matches = get_matches(dates)
    print(f"📋 {len(matches)} trận ngày {dates}")

    if not matches:
        send_telegram(f"⚽ *WORLD CUP 2026*\n📅 {dates[0]}\n\n😴 Không có trận đấu.")
        return

    results = []
    for idx, match in enumerate(matches):
        home, away = match["home"], match["away"]
        print(f"🔍 {home} vs {away} ({match['date_vn']} {match['time']} VN)...")

        if idx > 0:
            print(f"  ⏸ Chờ 20s...")
            time.sleep(20)

        elo_h = elo_ratings.get(home, DEFAULT_ELO)
        elo_a = elo_ratings.get(away, DEFAULT_ELO)
        form_h = get_recent_form(history, home)
        form_a = get_recent_form(history, away)
        probs = predict_from_elo(elo_h, elo_a)
        print(f"  ELO {home}={round(elo_h)} | {away}={round(elo_a)} → {probs}")

        try:
            ai = analyze_with_gemini(home, away, elo_h, elo_a, form_h, form_a, probs)
            print(f"  ✅ {ai.get('scoreline')} ({ai.get('confidence')}%)")
        except Exception as e:
            print(f"  ❌ Gemini lỗi: {e}")
            ai = {"comment": "", "scoreline": "?-?",
                  "confidence": round(max(probs["home_win_pct"], probs["away_win_pct"]))}

        results.append({"match": match, "result": {
            "probs": probs, "ai": ai,
            "elo_home": elo_h, "elo_away": elo_a,
            "form_home": form_h, "form_away": form_a,
        }})

    send_telegram(format_message(results, dates))
    print("🎉 Hoàn thành!")


if __name__ == "__main__":
    main()
