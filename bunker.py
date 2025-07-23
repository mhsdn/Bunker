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

# --- Кнопки главного меню (только Создать игру и Присоединиться) ---
def main_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("Создать игру", callback_data="create_game")],
        [InlineKeyboardButton("Присоединиться к игре", callback_data="join_game")],
    ]
    return InlineKeyboardMarkup(buttons)

# --- Кнопки выбора карт для показа ---
def get_card_buttons(exclude=None):
    exclude = exclude or []
    card_types = ["profession", "hobby", "fact1", "fact2", "baggage", "health"]
    buttons = []
    for card in card_types:
        if card not in exclude:
            buttons.append(InlineKeyboardButton(card.capitalize(), callback_data=f"reveal_{card}"))
    # Разбиваем кнопки по 2 в ряд
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(keyboard)

# --- Кнопки голосования (игроки, которые голосуют против) ---
def get_vote_buttons(chat_id):
    if chat_id not in games:
        return None
    players = games[chat_id]["players"]
    buttons = []
    for pid in players:
        buttons.append([InlineKeyboardButton(f"Игрок {pid}", callback_data=f"vote_{pid}")])
    return InlineKeyboardMarkup(buttons)

# --- Обработчики команд и колбеков ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Добро пожаловать в Bunker bot!\nВыберите действие:",
        reply_markup=main_menu_keyboard()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat.id
    data = query.data

    await query.answer()

    if data == "create_game":
        if chat_id in games and games[chat_id].get("started", False):
            await query.edit_message_text("Игра уже идёт!", reply_markup=main_menu_keyboard())
            return
        games[chat_id] = {
            "players": [],
            "started": False,
            "cards_shown": {},  # player_id -> [cards показанные]
            "votes": {},  # player_id -> кол-во голосов
        }
        await query.edit_message_text("Игра создана! Нажмите 'Присоединиться к игре', чтобы войти.", reply_markup=main_menu_keyboard())

    elif data == "join_game":
        if chat_id not in games:
            await query.edit_message_text("Сначала создайте игру.", reply_markup=main_menu_keyboard())
            return
        if user.id in games[chat_id]["players"]:
            await query.answer("Вы уже в игре!")
            return
        if len(games[chat_id]["players"]) >= 15:
            await query.answer("Максимальное количество игроков (15) уже достигнуто.")
            return
        games[chat_id]["players"].append(user.id)
        await query.answer("Вы присоединились к игре!")
        await query.edit_message_text(f"Игрок {user.first_name} присоединился!\nВсего игроков: {len(games[chat_id]['players'])}", reply_markup=main_menu_keyboard())

    elif data.startswith("reveal_"):
        # Пользователь хочет показать карту
        card_type = data[len("reveal_"):]
        player_id = user.id

        # Проверяем игру и игрока
        if chat_id not in games or player_id not in games[chat_id]["players"]:
            await query.answer("Вы не участвуете в игре.")
            return

        shown = games[chat_id]["cards_shown"].setdefault(player_id, [])
        if card_type in shown:
            await query.answer("Вы уже показывали эту карту.")
            return

        if len(shown) >= 2:
            await query.answer("Вы уже показали 2 карты в этом раунде.")
            return

        # Генерируем карту для игрока
        if card_type not in cards:
            await query.answer("Неизвестный тип карты.")
            return
        card_value = random.choice(cards[card_type+"s"]) if card_type+"s" in cards else "Неизвестно"

        shown.append(card_type)

        await query.answer(f"Вы показали карту: {card_type.capitalize()} — {card_value}")
        await query.message.reply_text(f"{user.first_name} показывает карту:\n{card_type.capitalize()}: {card_value}")

        # Если это первая карта, предложим показать вторую
        if len(shown) == 1:
            await query.message.reply_text(
                "Вы можете показать ещё одну карту.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Показать другую карту", callback_data="show_second_card")],
                    [InlineKeyboardButton("Закончить показ карт", callback_data="end_showing")]
                ])
            )
        else:
            await query.message.reply_text("Вы показали 2 карты. Ждите следующего раунда.")

    elif data == "show_second_card":
        # Показываем кнопки выбора второй карты, исключая уже показанную
        player_id = user.id
        if chat_id not in games or player_id not in games[chat_id]["players"]:
            await query.answer("Вы не участвуете в игре.")
            return
        shown = games[chat_id]["cards_shown"].get(player_id, [])
        keyboard = get_card_buttons(exclude=shown)
        await query.message.reply_text("Выберите карту для показа:", reply_markup=keyboard)

    elif data == "end_showing":
        await query.message.reply_text("Спасибо, ждите следующего раунда.")

    elif data.startswith("vote_"):
        # Голосование за исключение игрока
        voted_id = int(data[len("vote_"):])
        voter_id = user.id

        if chat_id not in games or voter_id not in games[chat_id]["players"]:
            await query.answer("Вы не участвуете в игре.")
            return

        if voted_id not in games[chat_id]["players"]:
            await query.answer("Игрок отсутствует в игре.")
            return

        votes = games[chat_id].setdefault("votes", {})
        votes[voted_id] = votes.get(voted_id, 0) + 1

        await query.answer(f"Вы проголосовали против игрока {voted_id}")

        # Можно добавить логику подсчёта голосов и исключения игрока

    else:
        await query.answer("Неизвестная команда.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ("Bunker bot - игра о выживании в бункере.\n\n"
            "Команды:\n"
            "/start - показать главное меню\n"
            "В меню выберите создать игру или присоединиться к игре.\n"
            "Вы можете показывать до 2 карт за раунд и голосовать за исключение игроков.\n"
            "Максимум игроков: 15, минимум для старта: 5.\n"
            "Удачи!")
    await update.message.reply_text(text)

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Ошибка: TELEGRAM_BOT_TOKEN не найден в .env")
        return

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bunker bot запущен и готов к работе!")
    app.run_polling()

if __name__ == "__main__":
    main()
