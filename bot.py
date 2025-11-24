# bot.py - JackpotHub final (invio segnali solo a utenti attivi; scalamento crediti SOLO su WIN = gol dopo invio)
# Requisiti: pyTelegramBotAPI, requests, python-dateutil
# ENV richieste:
# TELEGRAM_BOT_TOKEN, API_FOOTBALL_KEY (opzionale), MAIN_CHANNEL (es. @Jackpothub1), ADMIN_ID (tuo Telegram user id)

import os
import json
import time
import threading
import traceback
import random
from datetime import datetime, timedelta
from dateutil import tz

import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------------------------
# CONFIG
# -------------------------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
MAIN_CHANNEL = os.getenv("MAIN_CHANNEL", "@Jackpothub1")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None

SUPPORT_CONTACT = "@MRJackpotmania"   # dove gli utenti scrivono per VIP/manual
VIP_DAYS = 30
VIP_PRICE_STARS = 300

# Intervalli
CHECK_INTERVAL = 180         # monitor live ogni 3 minuti
RESULT_CHECK_INTERVAL = 180  # controllo risultati ogni 3 minuti
MINUTE_MIN = 75
CONDITIONS_REQUIRED = 3
MAX_ALERTS_PER_MATCH = 1

# soglie
THRESHOLDS = {
    "tiri_totali": 10,
    "tiri_5_min": 2,
    "corner": 6,
    "attacchi_pericolosi": 20,
    "pressione_off": 15,
    "trend_pct": 20
}

DB_FILE = "database.json"

# -------------------------
# Init bot
# -------------------------
if not TOKEN:
    raise RuntimeError("Environment variable TELEGRAM_BOT_TOKEN not set.")
bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

# -------------------------
# DB helpers
# -------------------------
def load_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        db = {
            "users": {},         # user_id -> {credits, level, paused, username, vip_expires}
            "pending_alerts": {},# alert_id -> {match_id, sent_ts, sent_score, recipients: {user_id: {signal_type}}}
            "alert_sent": {},    # match_id -> count
            "snapshots": {},     # match_id -> last_stats
            "admin_id": ADMIN_ID
        }
        save_db(db)
        return db

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def ensure_user(uid, username=None):
    db = load_db()
    s = str(uid)
    if s not in db["users"]:
        db["users"][s] = {
            "credits": 0,
            "level": "trial",  # trial / credit_user / premium
            "paused": False,
            "username": username or "",
            "vip_expires": None
        }
        save_db(db)
    return db["users"][s]

def is_vip(user_id):
    db = load_db()
    u = str(user_id)
    info = db["users"].get(u)
    if not info:
        return False
    vip_expires = info.get("vip_expires")
    if not vip_expires:
        return False
    try:
        return datetime.fromisoformat(vip_expires) > datetime.utcnow()
    except:
        return False

def grant_vip(user_id, days=VIP_DAYS):
    db = load_db()
    u = str(user_id)
    ensure_user(user_id)
    expires = datetime.utcnow() + timedelta(days=days)
    db["users"][u]["vip_expires"] = expires.isoformat()
    db["users"][u]["level"] = "premium"
    save_db(db)

# -------------------------
# Channel join check
# -------------------------
def is_member_of_channel(user_id):
    try:
        return bot.get_chat_member(MAIN_CHANNEL, user_id).status in ("member", "creator", "administrator")
    except Exception:
        return False

# -------------------------
# UI - simple menu
# -------------------------
def main_keyboard():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💳 Credits", "⭐ VIP")
    markup.row("⏸ Pause", "▶️ Resume")
    markup.row("ℹ️ How it works")
    return markup

# -------------------------
# /start handler
# -------------------------
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    uid = msg.from_user.id
    username = msg.from_user.username or ""
    ensure_user(uid, username)
    db = load_db()
    if not is_member_of_channel(uid):
        kb = InlineKeyboardMarkup()
        if isinstance(MAIN_CHANNEL, str) and MAIN_CHANNEL.startswith("@"):
            kb.add(InlineKeyboardButton("Unisciti al canale", url=f"https://t.me/{MAIN_CHANNEL[1:]}"))
        kb.add(InlineKeyboardButton("✔️ Ho completato", callback_data="confirm_join"))
        bot.send_message(uid, f"Per usare il bot devi essere iscritto al canale ufficiale: {MAIN_CHANNEL}\nDopo esserti unito premi 'Ho completato'.", reply_markup=kb)
        return

    # assegna 15 crediti trial se necessario
    u = db["users"].get(str(uid))
    if u and u.get("credits", 0) == 0 and u.get("level") == "trial":
        db["users"][str(uid)]["credits"] = 15
        save_db(db)
        bot.send_message(uid, "🎉 Hai ricevuto 15 crediti per il mese.")

    bot.send_message(uid, "Benvenuto! Usa il menu qui sotto.", reply_markup=main_keyboard())

@bot.callback_query_handler(func=lambda c: c.data == "confirm_join")
def callback_confirm_join(call):
    uid = call.from_user.id
    if is_member_of_channel(uid):
        db = load_db()
        if db["users"].get(str(uid), {}).get("credits", 0) == 0 and db["users"].get(str(uid), {}).get("level") == "trial":
            db["users"][str(uid)]["credits"] = 15
            save_db(db)
        bot.edit_message_text("✅ Accesso abilitato. Usa il menu.", call.message.chat.id, call.message.message_id)
        bot.send_message(uid, "Benvenuto! Usa il menu qui sotto.", reply_markup=main_keyboard())
    else:
        bot.answer_callback_query(call.id, "Non risulti ancora iscritto.", show_alert=True)

# -------------------------
# menu text handlers
# -------------------------
@bot.message_handler(func=lambda m: m.text == "💳 Credits")
def show_credits(msg):
    uid = msg.from_user.id
    ensure_user(uid)
    db = load_db()
    info = db["users"].get(str(uid), {})
    credits = info.get("credits", 0)
    level = info.get("level", "trial")
    vip = is_vip(uid)
    vip_text = f"\nVIP fino: {info.get('vip_expires')}" if vip else ""
    bot.send_message(uid, f"💳 Credits: {credits}\nLivello: {level}{vip_text}")

@bot.message_handler(func=lambda m: m.text == "⏸ Pause")
def pause(msg):
    uid = msg.from_user.id
    ensure_user(uid)
    db = load_db()
    db["users"][str(uid)]["paused"] = True
    save_db(db)
    bot.send_message(uid, "⏸ Ricezione segnali messa in pausa.")

@bot.message_handler(func=lambda m: m.text == "▶️ Resume")
def resume(msg):
    uid = msg.from_user.id
    ensure_user(uid)
    db = load_db()
    db["users"][str(uid)]["paused"] = False
    save_db(db)
    bot.send_message(uid, "▶️ Ricezione segnali riattivata.")

@bot.message_handler(func=lambda m: m.text == "ℹ️ How it works")
def how(msg):
    text = (
        "• Il bot monitora partite LIVE dal 75'.\n"
        "• Controlla 6 indicatori; strong se >=3 condizioni.\n"
        "• Paghi SOLO se dopo il segnale viene segnato almeno 1 gol (1 credito normal, 2 strong).\n"
        f"• VIP: contatta {SUPPORT_CONTACT} per attivazione manuale."
    )
    bot.send_message(msg.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "⭐ VIP")
def premium(msg):
    uid = msg.from_user.id
    ensure_user(uid)
    text = (
        f"VIP: {VIP_PRICE_STARS}⭐ per {VIP_DAYS} giorni (attivazione manuale).\n"
        f"Per attivare VIP contatta {SUPPORT_CONTACT}."
    )
    bot.send_message(uid, text)

# -------------------------
# Admin commands
# -------------------------
@bot.message_handler(commands=["setadmin"])
def cmd_setadmin(msg):
    uid = msg.from_user.id
    db = load_db()
    db["admin_id"] = uid
    save_db(db)
    bot.reply_to(msg, "Sei impostato come admin.")

@bot.message_handler(commands=["grantvip"])
def cmd_grantvip(msg):
    db = load_db()
    admin = db.get("admin_id")
    if msg.from_user.id != admin:
        bot.reply_to(msg, "Solo admin.")
        return
    parts = msg.text.split()
    if len(parts) < 3:
        bot.reply_to(msg, "Uso: /grantvip <user_id_or_@username> <days>")
        return
    target = parts[1]; days = int(parts[2])
    found = None
    db = load_db()
    if target.startswith("@"):
        t = target[1:].lower()
        for uid, info in db["users"].items():
            if info.get("username","").lower() == t:
                found = int(uid); break
    else:
        try:
            found = int(target)
        except:
            bot.reply_to(msg, "ID non valido"); return
    if not found:
        bot.reply_to(msg, "Utente non trovato."); return
    grant_vip(found, days=days)
    bot.reply_to(msg, f"VIP attivato per {found} ({days} giorni).")

@bot.message_handler(commands=["addcredits"])
def cmd_addcredits(msg):
    db = load_db()
    admin = db.get("admin_id")
    if msg.from_user.id != admin:
        bot.reply_to(msg, "Solo admin.")
        return
    parts = msg.text.split()
    if len(parts) < 3:
        bot.reply_to(msg, "Uso: /addcredits <user_id_or_@username> <amount>")
        return
    target = parts[1]; amount = int(parts[2])
    db = load_db()
    found = None
    if target.startswith("@"):
        t = target[1:].lower()
        for uid, info in db["users"].items():
            if info.get("username","").lower() == t:
                found = uid; break
    else:
        found = str(target)
    if not found or found not in db["users"]:
        bot.reply_to(msg, "Utente non trovato.")
        return
    db["users"][found]["credits"] = db["users"][found].get("credits",0) + amount
    save_db(db)
    bot.reply_to(msg, f"Aggiunti {amount} crediti a {found}.")

@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(msg):
    db = load_db()
    admin = db.get("admin_id")
    if msg.from_user.id != admin:
        bot.reply_to(msg, "Solo admin.")
        return
    text = msg.text.partition(" ")[2]
    if not text:
        bot.reply_to(msg, "Uso: /broadcast <testo>")
        return
    count = 0
    for uid, info in db["users"].items():
        try:
            bot.send_message(int(uid), f"📢 BROADCAST\n\n{text}")
            count += 1
        except:
            pass
    bot.reply_to(msg, f"Broadcast inviato a {count} utenti.")

@bot.message_handler(commands=["manual_alert"])
def cmd_manual_alert(msg):
    db = load_db()
    admin = db.get("admin_id")
    if msg.from_user.id != admin:
        bot.reply_to(msg, "Solo admin.")
        return
    text = msg.text.partition(" ")[2]
    if not text:
        bot.reply_to(msg, "Uso: /manual_alert <testo>")
        return
    alert_id = f"MAN_{int(time.time())}"
    # create pending and send as normal (normal signal)
    db = load_db()
    db.setdefault("pending_alerts", {})
    db["pending_alerts"][alert_id] = {
        "match_id": None,
        "sent_ts": datetime.utcnow().isoformat(),
        "sent_score": {"home":0,"away":0},
        "recipients": {}
    }
    save_db(db)
    send_alert_to_all(text, alert_id=alert_id, match_id=None, signal_type="normal")
    bot.reply_to(msg, "Alert manuale inviato.")

@bot.message_handler(commands=["status"])
def cmd_status(msg):
    db = load_db()
    total_users = len(db["users"])
    total_alerts = len(db["alert_sent"])
    bot.reply_to(msg, f"Utenti: {total_users}\nAlert match: {total_alerts}")

# -------------------------
# API parsing helpers
# -------------------------
def parse_match_stats_api(item):
    try:
        fixture = item.get("fixture", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        stats_list = item.get("statistics", [])
        minute = fixture.get("status", {}).get("elapsed") or 0
        match_id = fixture.get("id")
        tiri_tot = on_target = corners = dangerous = pressure = 0
        if isinstance(stats_list, list) and len(stats_list) >= 2:
            try:
                home_stats = stats_list[0].get("statistics", [])
                away_stats = stats_list[1].get("statistics", [])
                def map_stats(arr):
                    d = {}
                    for s in arr:
                        t = s.get("type","").lower()
                        v = s.get("value", 0) or 0
                        d[t] = v
                    return d
                h = map_stats(home_stats)
                a = map_stats(away_stats)
                tiri_tot = int(h.get("total shots", h.get("shots total", h.get("shots",0)))) + int(a.get("total shots", a.get("shots total", a.get("shots",0))))
                on_target = int(h.get("shots on target", h.get("on target",0))) + int(a.get("shots on target", a.get("on target",0)))
                corners = int(h.get("corners",0)) + int(a.get("corners",0))
                dangerous = int(h.get("dangerous attacks",0)) + int(a.get("dangerous attacks",0))
                pressure = int(h.get("pressure",0)) + int(a.get("pressure",0))
            except:
                pass
        stats = {
            "tiri_totali": tiri_tot,
            "tiri_in_porta": on_target,
            "corner": corners,
            "attacchi_pericolosi": dangerous,
            "pressione_off": pressure,
            "tiri_5_min": 0,
            "trend_pct": 0
        }
        return {
            "match_id": str(match_id),
            "minute": int(minute),
            "home": teams.get("home", {}).get("name"),
            "away": teams.get("away", {}).get("name"),
            "home_score": goals.get("home") or 0,
            "away_score": goals.get("away") or 0,
            "stats": stats
        }
    except Exception:
        return None

def get_live_matches_from_api():
    if not API_FOOTBALL_KEY:
        return []
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    params = {"live": "all"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        j = r.json()
        matches = []
        for item in j.get("response", []):
            parsed = parse_match_stats_api(item)
            if parsed:
                matches.append(parsed)
        return matches
    except Exception as e:
        print("API-Football error:", e)
        return []

# -------------------------
# simulate fallback
# -------------------------
def simulate_match():
    minute = random.randint(75, 90)
    stats = {
        "tiri_totali": random.randint(8, 22),
        "tiri_in_porta": random.randint(1, 12),
        "tiri_5_min": random.randint(0, 6),
        "corner": random.randint(0, 10),
        "attacchi_pericolosi": random.randint(10, 80),
        "pressione_off": random.randint(10, 55),
        "trend_pct": random.randint(0, 40)
    }
    return {
        "match_id": f"SIM_{int(time.time())}_{random.randint(1,9999)}",
        "minute": minute,
        "home": "Team A",
        "away": "Team B",
        "home_score": random.randint(0,2),
        "away_score": random.randint(0,2),
        "stats": stats
    }

# -------------------------
# alert decision & send
# (INVIO solo a utenti attivi, iscritti e con crediti>0 oppure VIP)
# -------------------------
def should_trigger_alert(match):
    if match.get("minute", 0) < MINUTE_MIN:
        return False, 0
    stats = match.get("stats", {})
    true_count = 0
    if stats.get("tiri_totali",0) >= THRESHOLDS["tiri_totali"]:
        true_count += 1
    if stats.get("tiri_5_min",0) >= THRESHOLDS["tiri_5_min"]:
        true_count += 1
    if stats.get("corner",0) >= THRESHOLDS["corner"]:
        true_count += 1
    if stats.get("attacchi_pericolosi",0) >= THRESHOLDS["attacchi_pericolosi"]:
        true_count += 1
    if stats.get("pressione_off",0) >= THRESHOLDS["pressione_off"]:
        true_count += 1
    if stats.get("trend_pct",0) >= THRESHOLDS["trend_pct"]:
        true_count += 1
    if true_count >= CONDITIONS_REQUIRED:
        return True, true_count
    if 1 <= true_count < CONDITIONS_REQUIRED:
        return True, true_count
    return False, 0

def format_alert_message(match, true_count, signal_type):
    s = match.get("stats", {})
    strength_text = "FORTE" if signal_type=="strong" else "NORMALE"
    text = (
        "‼️ *ALERT LIVE*\n\n"
        f"⚽ *{match.get('home')} - {match.get('away')}*  {match.get('home_score')} - {match.get('away_score')}\n"
        f"⏱ Minuto: *{match.get('minute')}*\n\n"
        "📊 Statistiche:\n"
        f"• Tiri totali: {s.get('tiri_totali',0)}\n"
        f"• Tiri ultimi 5': {s.get('tiri_5_min',0)}\n"
        f"• Corner: {s.get('corner',0)}\n"
        f"• Attacchi pericolosi: {s.get('attacchi_pericolosi',0)}\n"
        f"• Pressione: {s.get('pressione_off',0)}\n"
        f"• Trend (ultimi 10'): +{s.get('trend_pct',0)}%\n\n"
        f"⚠️ *ALTA PROBABILITÀ DI GOL* — Condizioni verificate: {true_count}/6\n"
        f"💠 Tipo segnale: *{strength_text}*\n\n"
        "ℹ️ Paghi solo se dopo l'invio viene segnato almeno 1 gol."
    )
    return text

def send_alert_to_all(text, alert_id, match_id, signal_type):
    db = load_db()
    db.setdefault("pending_alerts", {})
    db["pending_alerts"].setdefault(alert_id, {
        "match_id": match_id,
        "sent_ts": datetime.utcnow().isoformat(),
        "sent_score": {},
        "recipients": {}
    })
    # store sent_score will be set by caller
    for uid_str, info in db["users"].items():
        try:
            uid = int(uid_str)
            # only to users active (not paused), members of channel, and (vip or credits>0)
            if info.get("paused"):
                continue
            if not is_member_of_channel(uid):
                continue
            if is_vip(uid):
                bot.send_message(uid, text)
                db["pending_alerts"][alert_id]["recipients"][uid_str] = {"signal_type": signal_type}
            else:
                if info.get("credits",0) > 0:
                    bot.send_message(uid, text)
                    db["pending_alerts"][alert_id]["recipients"][uid_str] = {"signal_type": signal_type}
                else:
                    # skip users without credits
                    continue
        except Exception:
            pass
    save_db(db)

# -------------------------
# process result: charge only if goal(s) after send
# -------------------------
def process_alert_result(alert_id, final_home, final_away):
    db = load_db()
    pending = db.get("pending_alerts", {}).get(alert_id)
    if not pending:
        return
    sent_score = pending.get("sent_score", {})
    sent_total = sent_score.get("home",0) + sent_score.get("away",0)
    final_total = int(final_home) + int(final_away)
    goals_after = final_total - sent_total
    for uid_str, rec in pending.get("recipients", {}).items():
        try:
            uid = int(uid_str)
            if is_vip(uid):
                # notify VIP: no charge
                if goals_after > 0:
                    bot.send_message(uid, "🎉 WIN! Gol dopo il segnale. Nessuna detrazione (VIP).")
                else:
                    bot.send_message(uid, "❌ NO GOAL. Nessuna detrazione (VIP).")
                continue
            db_user = db["users"].get(uid_str, {})
            if goals_after > 0:
                cost = 1 if rec.get("signal_type","normal")=="normal" else 2
                # charge: if user has less than cost, charge what's available (or 0)
                credits_before = db_user.get("credits",0)
                deduct = min(cost, credits_before)
                db["users"][uid_str]["credits"] = credits_before - deduct
                bot.send_message(uid, f"🎉 WIN! Gol dopo il segnale. Ti sono stati scalati {deduct} crediti.")
            else:
                bot.send_message(uid, "❌ NO GOAL. Nessuna detrazione per questo segnale.")
        except Exception:
            pass
    # remove pending alert
    db_pending = db.get("pending_alerts", {})
    if alert_id in db_pending:
        del db_pending[alert_id]
    db["pending_alerts"] = db_pending
    save_db(db)

# -------------------------
# monitor: detect matches -> send alerts
# -------------
