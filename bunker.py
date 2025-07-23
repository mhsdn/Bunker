import os
import random
import json
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

load_dotenv()

with open("cards.json", "r", encoding="utf-8") as f:
    cards = json.load(f)

games = {}  # chat_id -> game data

# --- Кнопки главного меню ---
def main_menu_keyboard(chat_id):
    buttons = [
        [InlineKeyboardButton("Создать игру", callback_data="create_game")],
        [InlineKeyboardButton("Присоединиться к игре", callback_data="join_game")],
        [InlineKeyboardButton("Начать игру", callback_data="start_game")],
        [InlineKeyboardButton("Начать раунд", callback_data="start_round")],
        [InlineKeyboardButton("Правила игры", callback_data="rules")],
    ]
    return InlineKeyboardMarkup(buttons)

# --- Кнопки выбора карт ---
def get_card_buttons(exclude=None):
    exclude = exclude or []
    card_types = ["profession", "hobby", "fact1", "fact2", "baggage", "health"]
    buttons = []
    for card in card_types:
        if card not in exclude:
            buttons.append(InlineKeyboardButton(card.capitalize(), callback_data=f"reveal_{card}"))
    return InlineKeyboardMarkup([buttons[i:i+2] for i in range(0, len(buttons), 2)])

# --- Кнопки голосования ---
def get_vote_buttons(chat_id):
    if chat_id not in games:
        return None
    players = games[chat_id]["players"]
    buttons = []
    for pid in players:
        # Используем id для callback и имя — для текста кнопки
        buttons.append([InlineKeyboardButton(f"Игрок {pid}", callback_data=f"vote_{pid}")])
    return InlineKeyboardMarkup(buttons)

# --- Обработчики ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Добро пожаловать в Bunker bot!\nВыберите действие:",
        reply_markup=main_menu_keyboard(update.effective_chat.id)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat.id
    data = query.data

    await query.answer()  # подтверждаем получение

    if data == "create_game":
        if chat_id in games and games[chat_id].get("started", False):
            await query.edit_message_text("Игра уже идёт!", reply_markup=main_menu_keyboard(chat_id))
            return
        games[chat_id] = {"players": [], "started": False}
        await query.edit_message_text("Игра создана! Нажмите 'Присоединиться к игре', чтобы войти.", reply_markup=main_menu_keyboard(chat_id))

    elif data == "join_game":
        if chat_id not in games:
            await query.edit_message_text("Сначала создайте игру.", reply_markup=main_menu_keyboard(chat_id))
            return
        if user.id in games[chat_id]["players"]:
            await query.answer("Вы уже в игре!")
            return
        games[chat_id]["players"].append(user.id)
        await query.answer("Вы присоединились к игре!")
        await query.edit_message_text(f"Игрок {user.first_name} присоединился!", reply_markup=main_menu_keyboard(chat_id))

    elif data == "start_game":
        if chat_id not in games or len(games[chat_id]["players"]) < 5:
            await query.answer("Недостаточно игроков (минимум 5).")
            return
        if games[chat_id]["started"]:
            await query.answer("Игра уже началась.")
            return
        games[chat_id]["started"] = True
        await query.edit_message_text("Игра началась! Можно запускать раунды.", reply_markup=main_menu_keyboard(chat_id))

    elif data == "start_round":
        if chat_id not in games or not games[chat_id].get("started", False):
            await query.answer("Игра не запущена.")
            return
        await query.edit_message_text("Раунд начинается! Каждому игроку отправлены карты в ЛС.")
        # Отправляем игрокам карточки и кнопки выбора карт
        for player_id in games[chat_id]["players"]:
            card = {
                "profession": random.choice(cards["professions"]),
                "hobby": random.choice(cards["hobbies"]),
                "fact1": random.choice(cards["facts"]),
                "fact2": random.choice(cards["facts"]),
                "baggage": random.choice(cards["baggages"]),
                "health": random.choice(cards["healths"]),
            }
            games[chat_id].setdefault("cards", {})[player_id] = card
            games[chat_id].setdefault("revealed", {})[player_id] = []
            try:
                await context.bot.send_message(player_id, "Выберите первую карту для показа:", reply_markup=get_card_buttons())
            except Exception as e:
                print(f"Не удалось отправить сообщение игроку {player_id}: {e}")

    elif data.startswith("reveal_"):
        card_type = data[len("reveal_"):]
        player_id = user.id
        if chat_id not in games or player_id not in games[chat_id]["players"]:
            await query.answer("Вы не в игре.")
            return

        revealed = games[chat_id]["revealed"].get(player_id, [])
        if len(revealed) >= 2:
            await query.answer("Вы уже показали 2 карты.")
            return
        if card_type in revealed:
            await query.answer("Вы уже показали эту карту.")
            return
        revealed.append(card_type)
        games[chat_id]["revealed"][player_id] = revealed
        await query.answer(f"Вы показали карту: {card_type.capitalize()}")
        if len(revealed) == 1:
            # Предлагаем показать вторую карту или пропустить
            keyboard = get_card_buttons(exclude=revealed)
            keyboard.inline_keyboard.append([InlineKeyboardButton("Пропустить", callback_data="skip_second")])
            await context.bot.send_message(player_id, "Выберите вторую карту или пропустите:", reply_markup=keyboard)
        else:
            await context.bot.send_message(player_id, "Вы показали 2 карты, ждите завершения раунда.")

    elif data == "skip_second":
        player_id = user.id
        if chat_id not in games or player_id not in games[chat_id]["players"]:
            await query.answer("Вы не в игре.")
            return
        revealed = games[chat_id]["revealed"].get(player_id, [])
        if len(revealed) == 0:
            await query.answer("Сначала покажите первую карту.")
            return
        if len(revealed) == 2:
            await query.answer("Вы уже показали 2 карты.")
            return
        # Просто пропускаем вторую карту
        games[chat_id]["revealed"][player_id] = revealed
        await query.answer("Вторая карта пропущена. Ждите завершения раунда.")
        await context.bot.send_message(player_id, "Вы решили не показывать вторую карту. Ждите завершения раунда.")

    elif data == "rules":
        rules_text = (
            "Правила игры:\n"
            "1. Минимум 5, максимум 15 игроков.\n"
            "2. Запуск игры при достижении 5 игроков с таймером 60 сек или сразу при 15 игроках.\n"
            "3. Каждый раунд игроки показывают 1-2 карты из набора: Профессия, Хобби, Факт 1, Факт 2, Багаж, Здоровье.\n"
            "4. После раунда голосование на исключение игрока.\n"
            "5. Игра продолжается, пока не останется 2 игрока.\n"
        )
        await query.edit_message_text(rules_text, reply_markup=main_menu_keyboard(chat_id))

    else:
        await query.answer("Неизвестная команда.")

async def vote_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat.id
    data = query.data

    if not data.startswith("vote_"):
        await query.answer()
        return

    target_id = int(data[len("vote_"):])
    voter_id = user.id

    if chat_id not in games or voter_id not in games[chat_id]["players"]:
        await query.answer("Вы не в игре.")
        return

    if target_id not in games[chat_id]["players"]:
        await query.answer("Этот игрок не в игре.")
        return

    if target_id == voter_id:
        await query.answer("Нельзя голосовать за себя.")
        return

    # Удаляем предыдущие голоса от этого пользователя
    for voters in games[chat_id].setdefault("votes", {}).values():
        voters.discard(voter_id)
    games[chat_id].setdefault("votes", {}).setdefault(target_id, set()).add(voter_id)

    await query.answer("Ваш голос учтён.")

async def show_votes(chat_id, context):
    if chat_id not in games:
        return
    votes = games[chat_id].get("votes", {})
    results = []
    for pid, voters in votes.items():
        results.append(f"Игрок {pid}: {len(voters)} голосов")
    text = "Результаты голосования:\n" + "\n".join(results)
    await context.bot.send_message(chat_id, text)

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Ошибка: TELEGRAM_BOT_TOKEN не найден в .env")
        return

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CallbackQueryHandler(vote_handler, pattern="^vote_"))

    print("Bunker bot запущен и готов к работе!")
    app.run_polling()

if __name__ == "__main__":
    main()
