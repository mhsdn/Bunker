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
    await update.message.reply_text(
        "🛡️ *Bunker Bot* — карточная игра на выживание!\n\n"
        "🎯 Цель: попасть в бункер, где всего 2 места.\n"
        "👥 Начать игру: /startgame (в групповом чате)\n"
        "✋ Присоединиться: /join\n\n"
        "🕰️ Игра начнётся, когда соберётся команда (мин. 5 игроков) или через 60 секунд.",
        parse_mode="Markdown"
    )

async def startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games and games[chat_id].get("started"):
        await update.message.reply_text("⚠️ Игра уже идёт!")
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
    }

    await update.message.reply_text(
        "🎲 *Игра создана!*\n\n"
        "👥 Игроки, присоединяйтесь командой /join\n"
        "⏳ Игра начнётся через 60 секунд или когда наберётся 15 игроков.",
        parse_mode="Markdown"
    )

    async def wait_and_start():
        await asyncio.sleep(60)
        if chat_id not in games:
            return
        if len(games[chat_id]["players"]) < 5:
            await context.bot.send_message(chat_id, "❌ Недостаточно игроков (минимум 5). Игра отменена.")
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
        await update.message.reply_text("✋ Вы уже в игре!")
        return

    games[chat_id]["players"].append(user.id)
    await update.message.reply_text(f"✅ *{user.first_name}* присоединился к игре!", parse_mode="Markdown")

    if len(games[chat_id]["players"]) == 15:
        await context.bot.send_message(chat_id, "🎉 Собрано 15 игроков! Игра начинается.")
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
                    "🎴 *Ваша карточка:*\n"
                    f"👷‍♂️ Профессия: {card['profession']}\n"
                    f"🎂 Возраст: {card['age']}\n"
                    f"❤️ Здоровье: {card['health']}\n"
                    f"🎨 Хобби: {card['hobby']}\n"
                    f"🎒 Багаж: {card['baggage']}\n"
                    f"🕵️ Секрет: {card['secret']}"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Не удалось отправить сообщение {player_id}: {e}")

    await context.bot.send_message(chat_id, "🃏 Карточки розданы! Игра начинается.\n"
                                           "Чтобы начать раунд, напишите /startround")

def get_card_buttons(exclude=[]):
    options = [("Профессия", "profession"), ("Хобби", "hobby"), ("Секрет", "secret"),
               ("Возраст", "age"), ("Багаж", "baggage"), ("Здоровье", "health")]
    buttons = []
    for text, key in options:
        if key not in exclude:
            buttons.append([InlineKeyboardButton(text, callback_data=f"reveal_{key}")])
    return InlineKeyboardMarkup(buttons)

async def startround(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in games or not games[chat_id]["started"]:
        await update.message.reply_text("⚠️ Игра не запущена. Используйте /startgame")
        return

    if len(games[chat_id]["players"]) <= 2:
        await update.message.reply_text("🏆 Игра окончена! В бункер попали 2 игрока.")
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
                text=f"🔎 Раунд {games[chat_id]['round']}! Выберите первую карту для показа:",
                reply_markup=get_card_buttons()
            )
        except Exception as e:
            print(f"Ошибка при рассылке меню выбора карт {player_id}: {e}")

    await update.message.reply_text(f"🔔 Раунд {games[chat_id]['round']} начался! Игроки выбирают карты.")
    asyncio.create_task(round_timer(chat_id, context))

async def round_timer(chat_id, context):
    await asyncio.sleep(60)
    if chat_id not in games:
        return

    revealed = games[chat_id]["revealed"]
    cards_data = games[chat_id]["cards_data"]
    players = games[chat_id]["players"]

    text = f"⏰ *Раунд {games[chat_id]['round']} завершён!*\n\n"
    for pid in players:
        player_name = await get_player_name(pid, context)
        if pid in revealed:
            cards_shown = revealed[pid]
            card_texts = [f"• *{c.capitalize()}*: {cards_data[pid].get(c, '???')}" for c in cards_shown]
            text += f"👤 *{player_name}:*\n" + "\n".join(card_texts) + "\n\n"
        else:
            text += f"👤 *{player_name}:* не показал карты\n\n"

    await context.bot.send_message(chat_id, text, parse_mode="Markdown")
    await start_voting(chat_id, context)

async def start_voting(chat_id, context: ContextTypes.DEFAULT_TYPE):
    if chat_id not in games:
        return
    players = games[chat_id]["players"]
    if len(players) <= 2:
        await context.bot.send_message(chat_id, "🏆 Игра окончена! Осталось 2 игрока.")
        await show_winners(chat_id, context)
        del games[chat_id]
        return

    buttons = []
    for pid in players:
        player_name = await get_player_name(pid, context)
        buttons.append([InlineKeyboardButton(player_name, callback_data=f"vote_{pid}")])

    keyboard = InlineKeyboardMarkup(buttons)

    await context.bot.send_message(
        chat_id,
        "🗳️ *Голосование:* выберите игрока для исключения.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

    if games[chat_id]["voting_task"]:
        games[chat_id]["voting_task"].cancel()
    games[chat_id]["voting_task"] = asyncio.create_task(voting_timer(chat_id, context))

async def voting_timer(chat_id, context):
    await asyncio.sleep(30)
    if chat_id not in games:
        return
    await end_voting(chat_id, context)

async def end_voting(chat_id, context):
    votes = games[chat_id]["votes"]
    if not votes:
        await context.bot.send_message(chat_id, "⚠️ Голосование не состоялось — никто не исключён.")
        await startround_intern(chat_id, context)
        return

    vote_counts = {player: len(voters) for player, voters in votes.items()}
    max_votes = max(vote_counts.values())
    candidates = [p for p, c in vote_counts.items() if c == max_votes]

    if len(candidates) > 1:
        await context.bot.send_message(chat_id, "🤝 Голосование завершилось ничьей — никто не исключён.")
        await startround_intern(chat_id, context)
        return

    excluded = candidates[0]
    player_name = await get_player_name(excluded, context)

    games[chat_id]["players"].remove(excluded)
    del games[chat_id]["cards_data"][excluded]
    if excluded in games[chat_id]["revealed"]:
        del games[chat_id]["revealed"][excluded]
    if excluded in games[chat_id]["votes"]:
        del games[chat_id]["votes"][excluded]

    await context.bot.send_message(chat_id, f"🚪 Игрок *{player_name}* исключён из игры.", parse_mode="Markdown")

    if len(games[chat_id]["players"]) <= 2:
        await context.bot.send_message(chat_id, "🏆 Игра окончена! Осталось 2 игрока.")
        await show_winners(chat_id, context)
        del games[chat_id]
        return

    await startround_intern(chat_id, context)

async def startround_intern(chat_id, context):
    games[chat_id]["round"] += 1
    games[chat_id]["revealed"] = {}
    games[chat_id]["votes"] = defaultdict(set)

    players = games[chat_id]["players"]
    for player_id in players:
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=f"🔎 Раунд {games[chat_id]['round']}! Выберите первую карту для показа:",
                reply_markup=get_card_buttons()
            )
        except Exception as e:
            print(f"Ошибка при рассылке меню выбора карт {player_id}: {e}")

    await context.bot.send_message(chat_id, f"🔔 Раунд {games[chat_id]['round']} начался! Игроки выбирают карты.")
    asyncio.create_task(round_timer(chat_id, context))

async def get_player_name(user_id, context):
    try:
        member = await context.bot.get_chat_member(user_id, user_id)
        return member.user.first_name
    except:
        return "Игрок"

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = update.effective_chat.id if update.effective_chat else None

    if not chat_id:
        await query.answer("❌ Ошибка: невозможно определить чат.")
        return

    if chat_id not in games:
        await query.answer("⚠️ Игра не активна.")
        return

    data = query.data

    if data.startswith("reveal_"):
        card_type = data[len("reveal_"):]
        player_id = user.id

        if player_id not in games[chat_id]["players"]:
            await query.answer("✋ Вы не в игре!")
            return

        revealed = games[chat_id]["revealed"].setdefault(player_id, [])
        if len(revealed) >= 2:
            await query.answer("⛔ Вы уже показали 2 карты!")
            return

        if card_type in revealed:
            await query.answer("⚠️ Вы уже показали эту карту!")
            return

        revealed.append(card_type)
        await query.answer(f"✔️ Вы показали карту: {card_type.capitalize()}")

        if len(revealed) == 1:
            await context.bot.send_message(player_id, "Выберите вторую карту или /skip, чтобы пропустить:", reply_markup=get_card_buttons(exclude=revealed))
        else:
            await context.bot.send_message(player_id, "Вы показали 2 карты, ждите завершения раунда.")

        return

    if data.startswith("vote_"):
        target_id = int(data[len("vote_"):])
        voter_id = user.id

        if voter_id not in games[chat_id]["players"]:
            await query.answer("✋ Вы не в игре!")
            return

        if target_id not in games[chat_id]["players"]:
            await query.answer("⚠️ Этот игрок не в игре.")
            return

        if target_id == voter_id:
            await query.answer("❌ Нельзя голосовать за себя!")
            return

        for voters in games[chat_id]["votes"].values():
            voters.discard(voter_id)
        games[chat_id]["votes"][target_id].add(voter_id)
        await query.answer("🗳️ Вы проголосовали за исключение игрок
