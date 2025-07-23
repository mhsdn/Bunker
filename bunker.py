import json
import os
import matplotlib.pyplot as plt
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

USER_DATA_FILE = "user_data.json"

# Загрузка и сохранение данных
def load_user_data():
    try:
        with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_user_data(data):
    with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Вопросы и ответы
questions = [
    "Как часто вы испытываете мало интереса или удовольствия от занятий, которые обычно доставляют радость?",
    "Как часто вы чувствуете себя усталым или без сил?",
    "Как часто вам трудно засыпать или слишком рано просыпаться?",
    "Как часто вы ощущаете, что всё в жизни теряет смысл?",
    "Как часто вы чувствуете себя нервным или беспокойным?",
    "Как часто вы чувствуете себя беспомощным или одиноким?"
]

answer_options = ["Никогда", "Несколько дней", "Более половины времени", "Практически каждый день"]

scores = {"Никогда": 0, "Несколько дней": 1, "Более половины времени": 2, "Практически каждый день": 3}

user_answers = {}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = load_user_data()
    name = user_data.get(str(user_id), {}).get("name", "друг")
    await update.message.reply_text(f"Привет, {name}! Я твой личный психолог-бот. Чем могу помочь?")

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Вот что я могу сделать:\n"
        "- Провести экспресс-диагностику состояния\n"
        "- Отслеживать твой прогресс\n"
        "- Сохранять твои баллы\n"
        "- Показывать график изменений\n"
        "- Установить имя: /setname Иван\n"
        "- Начать диагностику: /diagnosis"
    )

# Команда /setname
async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = " ".join(context.args)

    if name:
        user_data = load_user_data()
        if str(user_id) not in user_data:
            user_data[str(user_id)] = {}
        user_data[str(user_id)]["name"] = name
        save_user_data(user_data)
        await update.message.reply_text(f"Приятно познакомиться, {name}!")
    else:
        await update.message.reply_text("Пожалуйста, укажи своё имя после команды, например: /setname Иван")

# Начать диагностику /diagnosis
async def start_diagnosis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_answers[user_id] = []
    await ask_question(update, context, user_id, 0)

# Задать вопрос
async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, question_number: int):
    if question_number < len(questions):
        question = questions[question_number]
        keyboard = [
            [InlineKeyboardButton(option, callback_data=f"answer_{user_id}_{question_number}_{option}")]
            for option in answer_options
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.message:
            await update.message.reply_text(question, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.message.reply_text(question, reply_markup=reply_markup)
    else:
        await evaluate_answers(update, context, user_id)

# Обработка кнопок
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_parts = query.data.split("_")
    user_id = int(data_parts[1])
    question_number = int(data_parts[2])
    answer = "_".join(data_parts[3:])  # для ответов с подчеркиваниями

    user_answers[user_id].append(answer)

    if question_number + 1 < len(questions):
        await ask_question(update, context, user_id, question_number + 1)
    else:
        await evaluate_answers(update, context, user_id)

# Оценка ответов и сохранение истории
async def evaluate_answers(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    total_score = sum(scores[answer] for answer in user_answers[user_id])

    if total_score <= 5:
        result = "Ваше состояние в порядке."
    elif 6 <= total_score <= 10:
        result = "Есть признаки стресса. Попробуйте отдохнуть."
    elif 11 <= total_score <= 15:
        result = "Возможно умеренная депрессия. Подумайте о разговоре с психологом."
    else:
        result = "Вы можете испытывать тяжёлую депрессию. Рекомендуется обратиться за помощью."

    user_data = load_user_data()
    history = user_data.get(str(user_id), {}).get("history", [])
    history.append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "score": total_score
    })
    user_data[str(user_id)] = {"history": history, **user_data.get(str(user_id), {})}
    save_user_data(user_data)

    await generate_progress_graph(user_id, history)

    await update.callback_query.message.edit_text(
        f"Ваши результаты:\n\nОбщий балл: {total_score}\n\n{result}\n\nВот ваш прогресс:"
    )
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=open(f"progress_{user_id}.png", "rb"))

# Генерация графика прогресса
async def generate_progress_graph(user_id: int, history: list):
    scores_list = [entry["score"] for entry in history]
    dates = [entry["date"] for entry in history]

    plt.figure(figsize=(8, 6))
    plt.plot(dates, scores_list, marker='o', linestyle='-', color='blue')
    plt.title(f"Прогресс пользователя {user_id}")
    plt.xlabel("Дата")
    plt.ylabel("Баллы")
    plt.xticks(rotation=45)
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(f"progress_{user_id}.png")
    plt.close()

# Главная функция запуска бота
def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")  # Токен из .env

    if not token:
        print("Ошибка: TELEGRAM_BOT_TOKEN не установлен в .env файле")
        return

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("setname", set_name))
    application.add_handler(CommandHandler("diagnosis", start_diagnosis))
    application.add_handler(CallbackQueryHandler(button))

    print("Бот запущен...")  # Сообщение в консоль

    application.run_polling()

if __name__ == '__main__':
    main()
