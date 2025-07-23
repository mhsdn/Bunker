import random
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Загружаем карточки из файла
import json

with open("cards.json", "r", encoding="utf-8") as f:
    cards = json.load(f)

games = {}  # словарь с текущими играми: chat_id -> {players: [], started: bool}

async def startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games and games[chat_id]["started"]:
        await update.message.reply_text("Игра уже идёт!")
        return
    games[chat_id] = {"players": [], "started": False}
    await update.message.reply_text("Игра создана! Игроки могут присоединяться командой /join")

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id not in games:
        await update.message.reply_text("Сначала создайте игру командой /startgame")
        return
    if user.id in games[chat_id]["players"]:
        await update.message.reply_text("Вы уже в игре!")
        return
    games[chat_id]["players"].append(user.id)
    await update.message.reply_text(f"{user.first_name} присоединился к игре!")

async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in games or not games[chat_id]["players"]:
        await update.message.reply_text("Сначала создайте игру и добавьте игроков")
        return
    if games[chat_id]["started"]:
        await update.message.reply_text("Игра уже началась!")
        return
    games[chat_id]["started"] = True

    players = games[chat_id]["players"]
    random.shuffle(players)

    for player_id in players:
        card = {
            "profession": random.choice(cards["professions"]),
            "age": random.choice(cards["ages"]),
            "health": random.choice(cards["healths"]),
            "hobby": random.choice(cards["hobbies"]),
            "baggage": random.choice(cards["baggages"]),
            "secret": random.choice(cards["secrets"]),
        }
        # Отправляем карточку игроку в личные сообщения
        await context.bot.send_message(chat_id=player_id, text=f"Ваша карточка:\n"
            f"Профессия: {card['profession']}\n"
            f"Возраст: {card['age']}\n"
            f"Здоровье: {card['health']}\n"
            f"Хобби: {card['hobby']}\n"
            f"Багаж: {card['baggage']}\n"
            f"Секрет: {card['secret']}\n"
        )

    await update.message.reply_text("Карточки розданы! Игра началась.")

def main():
    token = "7629863471:AAHZocohABMWr5A3IzQBpnBHiflGP6RLxtw"
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("startgame", startgame))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("begin", begin))

    app.run_polling()

if __name__ == "__main__":
    main()
