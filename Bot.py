import time
from telegram import Bot
from telegram.ext import Updater, CommandHandler

# Inserisci il tuo TOKEN
TOKEN = "INSERISCI_IL_TUO_TOKEN_QUI"

bot = Bot(token=TOKEN)

def start(update, context):
    update.message.reply_text("🔥 Bot attivo! Aspetto le partite...")

def check_stats():
    # Qui in futuro metteremo la vera API delle statistiche
    # Per ora simuliamo
    example_stats = {
        "minute": 78,
        "shots": 16,
        "dangerous_attacks": 55,
        "corners": 7
    }

    # CONDIZIONE: dopo il 75', molte offensive
    if (
        example_stats["minute"] >= 75 and
        example_stats["shots"] >= 12 and
        example_stats["dangerous_attacks"] >= 45
    ):
        return "📢 Segnale: Possibile Gol! Statistiche alte 🔥"

    return None

def loop(context):
    signal = check_stats()
    if signal:
        context.bot.send_message(chat_id=context.job.context, text=signal)

def run_bot(update, context):
    chat_id = update.message.chat_id
    update.message.reply_text("⏳ Avvio il monitoraggio statistiche…")
    context.job_queue.run_repeating(loop, interval=30, first=5, context=chat_id)

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("run", run_bot))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
