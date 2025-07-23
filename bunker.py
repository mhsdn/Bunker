import os
import random
import json
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

# Загрузка переменных из .env
load_dotenv()

# Загрузка карточек из файла
with open("cards.json", "r", encoding="utf-8") as f:
    cards = json.load(f)

# Хранилище игр
games = {}  # chat_id -> {players: [], started: bool}


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я — *Bunker Bot*, бот для карточной ролевой игры на выживание.\n\n"
        "🎲 Здесь ты можешь:\n"
        "• Создать игру в групповом чате\n"
        "• Позвать друзей\n"
        "• Получить случайную роль с характеристиками:\n"
        "  🧑 Профессия\n"
        "  🎂 Возраст\n"
        "  ❤️ Здоровье\n"
        "  🎨 Хобби\n"
        "  🎒 Багаж\n"
        "  🕵️ Секрет\n\n"
        "🚀 Как начать:\n"
        "1. Добавь меня в групповой чат\n"
        "2. Введи /startgame\n"
        "3. Игроки нажимают «Присоединиться»\n"
        "4. Когда все готовы — нажмите «Начать игру»\n"
        "5. Карточки придут каждому в личку 🤫\n\n"
        "Готовы выживать в бункере? Поехали!",
        parse_mode="Markdown"
    )


# === Команда /startgame ===
async def startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games and games[chat_id]["started"]:
        await update.message.reply_text("Игра уже идёт!")
        return
    games[chat_id] = {"players": [], "started": False}

    keyboard = [
        [InlineKeyboardButton("Присоединиться", callback_data="join_game")],
        [InlineKeyboardButton("Начать игру", callback_data="begin_game")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Игра создана! Нажмите кнопку ниже, чтобы присоединиться или начать игру.",
        reply_markup=reply_markup,
    )


# === Обработка нажатий кнопок ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    user = query.from_user

    if query.data == "join_game":
        if chat_id not in games:
            await query.edit_message_text("Сначала создайте игру командой /startgame")
            return
        if user.id in games[chat_id]["players"]:
            await query.answer("Вы уже в игре!", show_alert=True)
            return
        games[chat_id]["players"].append(user.id)
        await query.answer(f"{user.first_name} присоединился к игре!")

        # Обновляем список игроков
        players_names = []
        for player_id in games[chat_id]["players"]:
            try:
                member = await context.bot.get_chat_member(chat_id, player_id)
                players_names.append(member.user.first_name)
            except:
                players_names.append("Игрок")
        await query.edit_message_text(
            "Игра создана! Текущие игроки:\n" + "\n".join(players_names),
            reply_markup=query.message.reply_markup,
        )

    elif query.data == "begin_game":
        if chat_id not in games or not games[chat_id]["players"]:
            await query.answer("Сначала создайте игру и добавьте игроков!", show_alert=True)
            return
        if games[chat_id]["started"]:
            await query.answer("Игра уже началась!", show_alert=True)
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
            try:
                await context.bot.send_message(
                    chat_id=player_id,
                    text=(
                        f"🃏 *Ваша карточка:*\n"
                        f"Профессия: {card['profession']}\n"
                        f"Возраст: {card['age']}\n"
                        f"Здоровье: {card['health']}\n"
                        f"Хобби: {card['hobby']}\n"
                        f"Багаж: {card['baggage']}\n"
                        f"Секрет: {card['secret']}"
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"❌ Не удалось отправить сообщение игроку {player_id}: {e}")

        await query.edit_message_text("✅ Карточки розданы! Игра началась.")


# === Запуск бота ===
def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ Ошибка: TELEGRAM_BOT_TOKEN не найден в .env")
        return

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("startgame", startgame))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("✅ Bunker Bot запущен и готов к работе!")
    app.run_polling()


if __name__ == "__main__":
    main()
