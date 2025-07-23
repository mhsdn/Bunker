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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎲 Создать игру", callback_data="startgame")],
        [InlineKeyboardButton("➕ Присоединиться", callback_data="join")],
        [InlineKeyboardButton("❓ Правила", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(
            "👋 Привет! Я — *Bunker Bot*, карточная игра на выживание.\n\n"
            "Выберите действие кнопкой ниже:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    elif update.callback_query:
        await update.callback_query.message.edit_text(
            "👋 Привет! Я — *Bunker Bot*, карточная игра на выживание.\n\n"
            "Выберите действие кнопкой ниже:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    chat_id = update.effective_chat.id

    await query.answer()

    # Создаем dummy message для вызова команд, чтобы использовать существующую логику
    class DummyMessage:
        def __init__(self, chat_id, user):
            self.chat = type('Chat', (), {'id': chat_id})()
            self.from_user = user
        async def reply_text(self, text):
            await context.bot.send_message(chat_id, text)

    dummy_message = DummyMessage(chat_id, query.from_user)
    dummy_update = Update(update.update_id, message=dummy_message)

    if data == "startgame":
        await startgame(dummy_update, context)

    elif data == "join":
        await join(dummy_update, context)

    elif data == "help":
        await query.message.edit_text(
            "❓ *Правила игры Bunker Bot:*\n\n"
            "🎯 Цель — попасть в бункер, где всего 2 места.\n"
            "🃏 В каждом раунде игроки показывают карты и голосуют за исключение.\n"
            "🚀 Начать игру — нажмите «Создать игру».\n"
            "➕ Присоединиться — нажмите «Присоединиться».\n"
            "Для ручного управления доступны команды /startgame, /join и /startround.",
            parse_mode="Markdown"
        )

async def startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games and games[chat_id].get("started"):
        await update.message.reply_text("Игра уже идёт!")
        return

    games[chat_id] = {
        "players": [],
        "started": False,
        "round": 0,
        "revealed": {},
        "cards_data": {},
        "votes": defaultdict(set),  # target_player_id -> set of voter ids
        "task": None,
        "voting_task": None,
    }

    await update.message.reply_text(
        "🎲 Игра создана! Игроки, присоединяйтесь командой /join\n"
        "⏳ Игра начнётся через 60 секунд или сразу, если наберётся 15 игроков."
    )

    async def wait_and_start():
        await asyncio.sleep(60)
        if chat_id not in games:
            return
        if len(games[chat_id]["players"]) < 5:
            await context.bot.send_message(chat_id, "❌ Недостаточно игроков (нужно минимум 5). Игра отменена.")
            del games[chat_id]
        else:
            await begin_game(chat_id, context)

    games[chat_id]["task"] = asyncio.create_task(wait_and_start())

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in games:
        await update.message.reply_text("⚠️ Сначала создайте игру командой /startgame")
        return
    if user.id in games[chat_id]["players"]:
        await update.message.reply_text("Вы уже присоединились!")
        return

    games[chat_id]["players"].append(user.id)
    await update.message.reply_text(f"✅ {user.first_name} присоединился к игре!")

    if len(games[chat_id]["players"]) == 15:
        await context.bot.send_message(chat_id, "🎉 Набрано 15 игроков! Игра начинается.")
        if games[chat_id]["task"]:
            games[chat_id]["task"].cancel()
        await begin_game(chat_id, context)

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

async def startround(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in games or not games[chat_id]["started"]:
        await update.message.reply_text("Игра не запущена, создайте игру командой /startgame")
        return

    if len(games[chat_id]["players"]) <= 2:
        await update.message.reply_text("Игра окончена! В бункер попали 2 игрока.")
        await show_winners(chat_id, context)
        del games[chat_id]
        return

    games[chat_id]["round"] += 1
    games[chat_id]["revealed"] = {}
    games[chat_id]["votes"] = defaultdict(set)

    players = games[chat_id]["players"]
    for player_id in players:
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=f"Раунд {games[chat_id]['round']}!\nВыберите первую карту для показа:",
                reply_markup=get_card_buttons()
            )
        except Exception as e:
            print(f"Ошибка при рассылке меню выбора карт {player_id}: {e}")

    await update.message.reply_text(f"Раунд {games[chat_id]['round']} начался! Игроки выбирают карты.")
    asyncio.create_task(round_timer(chat_id, context))

async def round_timer(chat_id, context):
    await asyncio.sleep(60)
    if chat_id not in games:
        return

    revealed = games[chat_id]["revealed"]
    cards_data = games[chat_id]["cards_data"]
    players = games[chat_id]["players"]

    text = f"⏰ Раунд {games[chat_id]['round']} завершён! Вот раскрытые карты:\n\n"
    for pid in players:
        if pid in revealed:
            cards_shown = revealed[pid]
            card_texts = []
            for c in cards_shown:
                val = cards_data[pid].get(c, "???")
                card_texts.append(f"*{c.capitalize()}*: {val}")
            player_name = await get_player_name(pid, context)
            text += f"👤 {player_name}:\n" + "\n".join(card_texts) + "\n\n"
        else:
            player_name = await get_player_name(pid, context)
            text += f"👤 {player_name}: не показал карты\n\n"

    await context.bot.send_message(chat_id, text, parse_mode="Markdown")
    await start_voting(chat_id, context)

async def start_voting(chat_id, context: ContextTypes.DEFAULT_TYPE):
    if chat_id not in games:
        return
    players = games[chat_id]["players"]
    if len(players) <= 2:
        await context.bot.send_message(chat_id, "Игра окончена! Осталось 2 игрока.")
        await show_winners(chat_id, context)
        del games[chat_id]
        return

    buttons = []
    for pid in players:
        player_name = await get_player_name(pid, context)
        buttons.append([InlineKeyboardButton(player_name, callback_data=f"vote_{pid}")])

    markup = InlineKeyboardMarkup(buttons)
    await context.bot.send_message(chat_id, "🗳 Голосуйте, кого исключить:", reply_markup=markup)

    # Таймер на голосование (например 60 сек)
    games[chat_id]["voting_task"] = asyncio.create_task(voting_timer(chat_id, context))

async def voting_timer(chat_id, context):
    await asyncio.sleep(60)
    if chat_id not in games:
        return

    votes = games[chat_id]["votes"]
    players = games[chat_id]["players"]

    # Подсчёт голосов
    max_votes = 0
    excluded_player = None
    for pid, voter_set in votes.items():
        if len(voter_set) > max_votes:
            max_votes = len(voter_set)
            excluded_player = pid

    if excluded_player:
        player_name = await get_player_name(excluded_player, context)
        await context.bot.send_message(chat_id, f"❌ Игрок {player_name} исключён из игры.")
        games[chat_id]["players"].remove(excluded_player)
        del games[chat_id]["cards_data"][excluded_player]
    else:
        await context.bot.send_message(chat_id, "🔔 Никто не получил достаточного количества голосов. Исключений нет.")

    # Очистка голосов и раскрытых карт для следующего раунда
    games[chat_id]["votes"] = defaultdict(set)
    games[chat_id]["revealed"] = {}

    # Запуск нового раунда автоматически
    if len(games[chat_id]["players"]) > 2:
        await context.bot.send_message(chat_id, "⏳ Следующий раунд начинается...")
        await startround(Update(update_id=0, message=DummyMessage(chat_id, None)), context)
    else:
        await context.bot.send_message(chat_id, "Игра окончена! Осталось 2 игрока.")
        await show_winners(chat_id, context)
        del games[chat_id]

async def show_winners(chat_id, context):
    if chat_id not in games:
        return
    players = games[chat_id]["players"]
    winners = []
    for pid in players:
        player_name = await get_player_name(pid, context)
        winners.append(player_name)
    text = "🏆 Победители — игроки, попавшие в бункер:\n" + "\n".join(winners)
    await context.bot.send_message(chat_id, text)

async def get_player_name(user_id, context):
    try:
        user = await context.bot.get_chat(user_id)
        return user.first_name or str(user_id)
    except Exception:
        return str(user_id)

async def reveal_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    data = query.data

    await query.answer()

    if chat_id not in games or not games[chat_id]["started"]:
        await query.message.reply_text("Игра не запущена.")
        return

    if user_id not in games[chat_id]["players"]:
        await query.message.reply_text("Вы не участвуете в этой игре.")
        return

    card_type = data.split("_")[1]
    revealed = games[chat_id]["revealed"].setdefault(user_id, [])
    if card_type in revealed:
        await query.message.reply_text("Эта карта уже раскрыта.")
        return

    revealed.append(card_type)
    card = games[chat_id]["cards_data"][user_id]
    value = card.get(card_type, "???")
    await query.message.reply_text(f"🔍 Ваша карта — *{card_type.capitalize()}*: {value}", parse_mode="Markdown")

    # Предлагаем раскрыть еще, если меньше 2
    if len(revealed) < 2:
        await query.message.reply_text("Выберите ещё карту для показа:", reply_markup=get_card_buttons(exclude=revealed))
    else:
        await query.message.reply_text("Вы раскрыли 2 карты, ждите остальных.")

async def vote_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    data = query.data

    await query.answer()

    if chat_id not in games or not games[chat_id]["started"]:
        await query.message.reply_text("Игра не запущена.")
        return

    if user_id not in games[chat_id]["players"]:
        await query.message.reply_text("Вы не участвуете в этой игре.")
        return

    target_id = int(data.split("_")[1])
    if target_id == user_id:
        await query.message.reply_text("Вы не можете голосовать за себя.")
        return

    votes = games[chat_id]["votes"]

    # Проверяем, не голосовал ли уже пользователь
    for voters in votes.values():
        if user_id in voters:
            await query.message.reply_text("Вы уже проголосовали.")
            return

    votes[target_id].add(user_id)
    player_name = await get_player_name(target_id, context)
    await query.message.reply_text(f"Вы проголосовали за {player_name}.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ *Правила игры Bunker Bot:*\n\n"
        "🎯 Цель — попасть в бункер, где всего 2 места.\n"
        "🃏 В каждом раунде игроки показывают карты и голосуют за исключение.\n"
        "🚀 Начать игру — нажмите «Создать игру» или /startgame.\n"
        "➕ Присоединиться — нажмите «Присоединиться» или /join.\n"
        "Для начала раунда используйте /startround.",
        parse_mode="Markdown"
    )

class DummyMessage:
    def __init__(self, chat_id, user):
        self.chat = type('Chat', (), {'id': chat_id})()
        self.from_user = user

    async def reply_text(self, text):
        # Используем bot.send_message напрямую, т.к. это эмуляция
        pass

def main():
    application = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("startgame", startgame))
    application.add_handler(CommandHandler("join", join))
    application.add_handler(CommandHandler("startround", startround))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(CallbackQueryHandler(menu_callback_handler, pattern="^(startgame|join|help)$"))
    application.add_handler(CallbackQueryHandler(reveal_card, pattern="^reveal_"))
    application.add_handler(CallbackQueryHandler(vote_handler, pattern="^vote_"))

    print("Бот запущен")
    application.run_polling()

if __name__ == "__main__":
    main()
