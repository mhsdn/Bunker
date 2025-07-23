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
from telegram.constants import ParseMode

load_dotenv()

with open("cards.json", "r", encoding="utf-8") as f:
    cards = json.load(f)

games = {}  # chat_id -> game data

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Привет!*\n\n"
        "_Я — Bunker Bot, карточная игра на выживание._\n\n"
        "🎯 *Цель* — попасть в бункер, где всего 2 места.\n"
        "🚀 Напиши /startgame в групповом чате, чтобы начать.",
        parse_mode=ParseMode.MARKDOWN
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
        "votes": defaultdict(set),
        "task": None,
        "voting_task": None,
    }

    await update.message.reply_text(
        "🎲 *Игра создана!*\n"
        "Игроки, присоединяйтесь командой /join\n"
        "⏳ Игра начнётся через 60 секунд или сразу, если наберётся 15 игроков.",
        parse_mode=ParseMode.MARKDOWN
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
    await update.message.reply_text(f"✅ *{user.first_name}* присоединился к игре!", parse_mode=ParseMode.MARKDOWN)

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
                    "🎴 *Ваша карточка:*\n"
                    f"👨‍🔧 *Профессия:* {card['profession']}\n"
                    f"🎂 *Возраст:* {card['age']}\n"
                    f"❤️ *Здоровье:* {card['health']}\n"
                    f"🎨 *Хобби:* {card['hobby']}\n"
                    f"🎒 *Багаж:* {card['baggage']}\n"
                    f"🕵️ *Секрет:* {card['secret']}\n"
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            print(f"Не удалось отправить сообщение {player_id}: {e}")

    await context.bot.send_message(chat_id, "🃏 *Карточки розданы! Игра начинается.*\nЧтобы начать раунд, напишите /startround", parse_mode=ParseMode.MARKDOWN)

def get_card_buttons(exclude=[]):
    options = [
        ("profession", "👨‍🔧 Профессия"),
        ("hobby", "🎨 Хобби"),
        ("secret", "🕵️ Секрет"),
        ("age", "🎂 Возраст"),
        ("baggage", "🎒 Багаж"),
        ("health", "❤️ Здоровье"),
    ]
    buttons = []
    for key, label in options:
        if key not in exclude:
            buttons.append([InlineKeyboardButton(label, callback_data=f"reveal_{key}")])
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
                text=f"Раунд *{games[chat_id]['round']}!*\nВыберите первую карту для показа:",
                reply_markup=get_card_buttons(),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            print(f"Ошибка при рассылке меню выбора карт {player_id}: {e}")

    await update.message.reply_text(f"Раунд *{games[chat_id]['round']}* начался! Игроки выбирают карты.", parse_mode=ParseMode.MARKDOWN)
    asyncio.create_task(round_timer(chat_id, context))

async def round_timer(chat_id, context):
    await asyncio.sleep(60)
    if chat_id not in games:
        return

    revealed = games[chat_id]["revealed"]
    cards_data = games[chat_id]["cards_data"]
    players = games[chat_id]["players"]

    text = f"⏰ Раунд *{games[chat_id]['round']}* завершён! Вот раскрытые карты:\n\n"
    for pid in players:
        if pid in revealed:
            cards_shown = revealed[pid]
            card_texts = []
            for c in cards_shown:
                val = cards_data[pid].get(c, "???")
                card_texts.append(f"*{c.capitalize()}*: {val}")
            player_name = await get_player_name(pid, context)
            text += f"👤 *{player_name}*:\n" + "\n".join(card_texts) + "\n\n"
        else:
            player_name = await get_player_name(pid, context)
            text += f"👤 *{player_name}*: не показал карты\n\n"

    await context.bot.send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN)
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
        buttons.append([InlineKeyboardButton(f"🚪 {player_name}", callback_data=f"vote_{pid}")])

    keyboard = InlineKeyboardMarkup(buttons)

    await context.bot.send_message(
        chat_id,
        "🗳️ *Голосование:* выберите игрока, которого хотите исключить из игры.",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN,
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
        await context.bot.send_message(chat_id, "Голосование не состоялось — никто не исключён.")
        await startround_intern(chat_id, context)
        return

    vote_counts = {player: len(voters) for player, voters in votes.items()}
    max_votes = max(vote_counts.values())
    candidates = [p for p, c in vote_counts.items() if c == max_votes]

    if len(candidates) > 1:
        await context.bot.send_message(chat_id, "Голосование завершилось ничьей — никто не исключён.")
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

    await context.bot.send_message(chat_id, f"🚪 Игрок *{player_name}* исключён из игры.", parse_mode=ParseMode.MARKDOWN)

    if len(games[chat_id]["players"]) <= 2:
        await context.bot.send_message(chat_id, "Игра окончена! Осталось 2 игрока.")
        await show_winners(chat_id, context)
        del games[chat_id]
        return

    await startround_intern(chat_id, context)

async def startround_intern(chat_id, context):
    # Запускаем следующий раунд автоматически
    games[chat_id]["round"] += 1
    games[chat_id]["revealed"] = {}
    games[chat_id]["votes"] = defaultdict(set)

    players = games[chat_id]["players"]
    for player_id in players:
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=f"Раунд *{games[chat_id]['round']}!*\nВыберите первую карту для показа:",
                reply_markup=get_card_buttons(),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            print(f"Ошибка при рассылке меню выбора карт {player_id}: {e}")

    await context.bot.send_message(chat_id, f"Раунд *{games[chat_id]['round']}* начался! Игроки выбирают карты.", parse_mode=ParseMode.MARKDOWN)
    asyncio.create_task(round_timer(chat_id, context))

async def get_player_name(user_id, context):
    try:
        user = await context.bot.get_chat(user_id)
        return user.first_name
    except:
        return "Игрок"

async def show_winners(chat_id, context):
    players = games[chat_id]["players"]
    text = "🎉 *Победители:*\n"
    for pid in players:
        name = await get_player_name(pid, context)
        text += f"👤 {name}\n"
    await context.bot.send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat.id

    if chat_id not in games:
        await query.edit_message_text("Игра не найдена или закончена.")
        return

    if data.startswith("reveal_"):
        card_key = data[len("reveal_"):]
        if user_id not in games[chat_id]["players"]:
            await query.answer("Вы не в игре!", show_alert=True)
            return

        if user_id not in games[chat_id]["revealed"]:
            games[chat_id]["revealed"][user_id] = []

        if card_key in games[chat_id]["revealed"][user_id]:
            await query.answer("Эту карту уже показывали", show_alert=True)
            return

        games[chat_id]["revealed"][user_id].append(card_key)

        card_value = games[chat_id]["cards_data"][user_id].get(card_key, "???")
        await query.edit_message_text(
            f"Вы показали карту *{card_key.capitalize()}*: {card_value}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_card_buttons(exclude=games[chat_id]["revealed"][user_id])
        )
    elif data.startswith("vote_"):
        voted_id = int(data[len("vote_"):])
        if user_id not in games[chat_id]["players"]:
            await query.answer("Вы не в игре!", show_alert=True)
            return
        if voted_id == user_id:
            await query.answer("Нельзя голосовать за себя!", show_alert=True)
            return

        # Удаляем предыдущие голоса пользователя
        for voters in games[chat_id]["votes"].values():
            voters.discard(user_id)

        games[chat_id]["votes"][voted_id].add(user_id)
        voted_name = await get_player_name(voted_id, context)
        await query.answer(f"Вы проголосовали за {voted_name}")

async def main():
    TOKEN = os.getenv("TOKEN")
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("startgame", startgame))
    application.add_handler(CommandHandler("join", join))
    application.add_handler(CommandHandler("startround", startround))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Бот запущен")
    await application.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
