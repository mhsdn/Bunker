import os
import random
import json
import asyncio
from collections import defaultdict
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
)

load_dotenv()

with open("cards.json", "r", encoding="utf-8") as f:
    cards = json.load(f)

games = {}  # chat_id -> game data

# Функция для кнопок старта
def start_buttons(chat_id):
    if chat_id in games:
        game = games[chat_id]
        if game["started"]:
            return InlineKeyboardMarkup([[InlineKeyboardButton("Игра идёт", callback_data="noop")]])
        else:
            buttons = [
                [InlineKeyboardButton("Присоединиться", callback_data="join_game")]
            ]
            # Только создатель может стартовать игру
            if game.get("creator_id"):
                buttons.append([InlineKeyboardButton("Начать игру", callback_data="begin_game")])
            return InlineKeyboardMarkup(buttons)
    else:
        return InlineKeyboardMarkup([[InlineKeyboardButton("Создать игру", callback_data="create_game")]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        "👋 Привет! Я — *Bunker Bot*, карточная игра на выживание.\n\n"
        "🎯 Цель — попасть в бункер, где 2 места.\n"
        "Используй кнопки ниже для управления игрой.",
        reply_markup=start_buttons(chat_id),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = update.effective_chat.id if update.effective_chat else None

    data = query.data

    # Заглушка для noop
    if data == "noop":
        await query.answer()
        return

    if data == "create_game":
        if chat_id in games and games[chat_id].get("started"):
            await query.answer("Игра уже идёт!")
            return
        games[chat_id] = {
            "players": [],
            "started": False,
            "round": 0,
            "revealed": {},
            "cards_data": {},
            "votes": defaultdict(set),
            "task": None,
            "voting_task": None,
            "creator_id": user.id,
        }
        await query.message.edit_text(
            "🎲 Игра создана! Нажмите 'Присоединиться', чтобы вступить.\n"
            "Для старта игры нажмите 'Начать игру' (только создатель).",
            reply_markup=start_buttons(chat_id)
        )
        await query.answer("Игра создана!")
        return

    if data == "join_game":
        if chat_id not in games:
            await query.answer("Игра не создана, нажмите 'Создать игру'.")
            return

        if user.id in games[chat_id]["players"]:
            await query.answer("Вы уже в игре!")
            return

        if games[chat_id]["started"]:
            await query.answer("Игра уже началась, нельзя присоединиться.")
            return

        games[chat_id]["players"].append(user.id)
        await query.answer("Вы присоединились к игре!")
        # Обновляем сообщение с кнопками и списком игроков
        player_names = []
        for pid in games[chat_id]["players"]:
            try:
                member = await context.bot.get_chat_member(chat_id, pid)
                player_names.append(member.user.first_name)
            except:
                player_names.append("Игрок")

        await query.message.edit_text(
            "🎲 Игра создана!\n\nИгроки:\n- " + "\n- ".join(player_names) + "\n\n"
            "Нажмите 'Присоединиться', чтобы вступить.\n"
            "Для старта игры нажмите 'Начать игру' (только создатель).",
            reply_markup=start_buttons(chat_id)
        )
        # Если набралось 15, запускаем игру автоматически
        if len(games[chat_id]["players"]) >= 15:
            await begin_game(chat_id, context)
            await query.message.edit_text("🎉 Набрано 15 игроков! Игра начинается.")
        return

    if data == "begin_game":
        if chat_id not in games:
            await query.answer("Игра не создана.")
            return
        if user.id != games[chat_id]["creator_id"]:
            await query.answer("Только создатель игры может её начать.")
            return
        if games[chat_id]["started"]:
            await query.answer("Игра уже началась.")
            return
        if len(games[chat_id]["players"]) < 5:
            await query.answer("Нужно минимум 5 игроков для старта.")
            return
        await query.answer("Игра запускается!")
        await begin_game(chat_id, context)
        await query.message.edit_text("🃏 Карточки розданы! Игра начинается.\nДля начала раунда нажмите /startround")
        return

    # Далее кнопки для reveal_, vote_ и др. (оставим текущую логику)

    if chat_id not in games:
        await query.answer("Игра не активна.")
        return

    if data.startswith("reveal_"):
        card_type = data[len("reveal_"):]
        player_id = user.id

        if player_id not in games[chat_id]["players"]:
            await query.answer("Вы не в игре!")
            return

        revealed = games[chat_id]["revealed"].setdefault(player_id, [])
        if len(revealed) >= 2:
            await query.answer("Вы уже показали 2 карты!")
            return

        if card_type in revealed:
            await query.answer("Вы уже показали эту карту!")
            return

        revealed.append(card_type)
        await query.answer(f"Вы показали карту: {card_type.capitalize()}")

        if len(revealed) == 1:
            # Предлагаем показать вторую карту
            await context.bot.send_message(player_id, "Выберите вторую карту или /skip, чтобы пропустить:", reply_markup=get_card_buttons(exclude=revealed))
        else:
            await context.bot.send_message(player_id, "Вы показали 2 карты, ждите завершения раунда.")

        return

    if data.startswith("vote_"):
        target_id = int(data[len("vote_"):])
        voter_id = user.id

        if voter_id not in games[chat_id]["players"]:
            await query.answer("Вы не в игре!")
            return

        if target_id not in games[chat_id]["players"]:
            await query.answer("Этот игрок не в игре.")
            return

        if target_id == voter_id:
            await query.answer("Нельзя голосовать за себя!")
            return

        # Удаляем предыдущие голоса этого пользователя
        for voters in games[chat_id]["votes"].values():
            voters.discard(voter_id)
        games[chat_id]["votes"][target_id].add(voter_id)
        await query.answer("Вы проголосовали за исключение игрока.")
        return

async def begin_game(chat_id, context: ContextTypes.DEFAULT_TYPE):
    games[chat_id]["started"] = True
    games[chat_id]["round"] = 0
    games[chat_id]["revealed"] = {}
    games[chat_id]["cards_data"] = {}
    games[chat_id]["votes"] = defaultdict(set)
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
        games[chat_id]["cards_data"][player_id] = card
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=(
                    "🎴 Ваша карточка:\n"
                    f"👨‍🔧 Профессия: {card['profession']}\n"
                    f"🎂 Возраст: {card['age']}\n"
                    f"❤️ Здоровье: {card['health']}\n"
                    f"🎨 Хобби: {card['hobby']}\n"
                    f"🎒 Багаж: {card['baggage']}\n"
                    f"🕵️ Секрет: {card['secret']}\n"
                )
            )
        except Exception as e:
            print(f"Не удалось отправить сообщение {player_id}: {e}")

    await context.bot.send_message(chat_id, "🃏 Карточки розданы! Игра начинается.\n"
                                           "Чтобы начать раунд, напишите /startround")

def get_card_buttons(exclude=[]):
    options = ["profession", "hobby", "secret", "age", "baggage", "health"]
    buttons = []
    for opt in options:
        if opt not in exclude:
            buttons.append([InlineKeyboardButton(opt.capitalize(), callback_data=f"reveal_{opt}")])
    return InlineKeyboardMarkup(buttons)

# Остальной код оставляем без изменений (startround, voting, skip_second_card, get_player_name, main и т.п.)

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Ошибка: TELEGRAM_BOT_TOKEN не найден в .env")
        return

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    # Убираем команды startgame, join и startround из чат-группы, оставим только /start и /skip для пропуска второй карты
    app.add_handler(CommandHandler("skip", skip_second_card))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bunker bot запущен и готов к работе!")
    app.run_polling()

if __name__ == "__main__":
    main()
