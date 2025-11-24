import telebot
import os
import logging
import sys

# ▶️ ATTIVA I LOG SU RENDER
logging.basicConfig(
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logging.info("🔄 Il bot sta iniziando l'avvio...")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    logging.error("❌ ERRORE: TELEGRAM_BOT_TOKEN non trovato nelle variabili d'ambiente!")
    raise SystemExit

bot = telebot.TeleBot(TOKEN)
logging.info("✅ TeleBot inizializzato correttamente.")

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Il bot è attivo su Render!")
    logging.info(f"👌 Start eseguito da {message.chat.id}")

logging.info("🚀 Avvio del polling...")
bot.polling(non_stop=True)
