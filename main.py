import asyncio
import os
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# ==================== НАСТРОЙКИ ====================
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Установите переменную окружения BOT_TOKEN")

# Замените на свои реальные ссылки
WEBINAR_LINK = "https://zoom.us/j/1234567890?pwd=EXAMPLE123"  # ← ссылка на Zoom / Telegram
MENTOR_USERNAME = "@trading_mentor"  # ← ваш username для продажи курса

# ==================================================

registered_users: set[int] = set()  # будет храниться в bot_data


def format_webinar_time(dt: datetime) -> str:
    """Форматируем дату на русском (например: Понедельник 19:00)"""
    weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    return f"{weekdays[dt.weekday()]} {dt.strftime('%H:%M')}"


async def broadcast_message(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Рассылка всем записавшимся (с автоматической очисткой заблокировавших)"""
    registered = context.bot_data.setdefault("registered", set())
    for user_id in list(registered):
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
        except Exception:
            registered.discard(user_id)  # пользователь заблокировал бота


async def schedule_webinar_jobs(context: ContextTypes.DEFAULT_TYPE, webinar_dt: datetime) -> None:
    """Планируем все автоматические напоминания и старт вебинара"""
    now = datetime.now()

    # Удаляем старые джобы, чтобы не было дублирования
    for job_name in ["webinar_1h", "webinar_10m", "webinar_start"]:
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()

    # Напоминание за 1 час
    t1 = webinar_dt - timedelta(hours=1)
    if t1 > now:
        context.job_queue.run_once(
            callback=reminder_job,
            when=t1,
            data={
                "message": "🚨 ВНИМАНИЕ! Твой бесплатный вебинар по трейдингу начнётся уже через 1 час!\n\n"
                           "Подготовь блокнот и кофе — будет очень насыщенно 🔥"
            },
            name="webinar_1h",
        )

    # Напоминание за 10 минут
    t2 = webinar_dt - timedelta(minutes=10)
    if t2 > now:
        context.job_queue.run_once(
            callback=reminder_job,
            when=t2,
            data={
                "message": "⏰ Осталось всего 10 минут до старта вебинара!\n\n"
                           "Занимай место в зале прямо сейчас 👇"
            },
            name="webinar_10m",
        )

    # Старт вебинара
    context.job_queue.run_once(
        callback=start_webinar_job,
        when=webinar_dt,
        data={
            "message": f"🎬 ВЕБИНАР НАЧИНАЕТСЯ ПРЯМО СЕЙЧАС!\n\n"
                       f"Ссылка: {WEBINAR_LINK}\n\n"
                       f"Не опаздывай — первые 10 минут самые важные!"
        },
        name="webinar_start",
    )


async def reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await broadcast_message(context, context.job.data["message"])


async def start_webinar_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await broadcast_message(context, context.job.data["message"])


# ====================== ХЕНДЛЕРЫ ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[InlineKeyboardButton("Записаться на вебинар", callback_data="register")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}! 👋\n\n"
        "Хочешь освоить трейдинг и открыть для себя новые возможности на финансовых рынках?\n\n"
        "На **бесплатном вебинаре** от опытного трейдера ты получишь:\n"
        "• Практические инструменты анализа рынка\n"
        "• Готовые стратегии входа и выхода\n"
        "• Понимание психологии торговли\n\n"
        "🚀 **Места строго ограничены — всего 50 участников!**\n\n"
        "Не упусти шанс! Нажми кнопку ниже и запишись прямо сейчас.",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


async def register_user(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Общая логика регистрации (используется и командой, и кнопкой)"""
    registered = context.bot_data.setdefault("registered", set())

    if user_id in registered:
        await context.bot.send_message(chat_id=user_id, text="✅ Ты уже записан на вебинар!")
        return

    registered.add(user_id)

    webinar_time: datetime | None = context.bot_data.get("webinar_time")

    if webinar_time and webinar_time > datetime.now():
        time_str = format_webinar_time(webinar_time)
        text = (
            f"✅ Поздравляем! Ты успешно записан на вебинар по трейдингу! 🎉\n\n"
            f"📅 Дата и время: {time_str}\n\n"
            f"Места почти закончились — осталось всего несколько свободных слотов!\n\n"
            f"Мы пришлём тебе напоминания и ссылку автоматически."
        )
    else:
        text = "✅ Ты записан! Время вебинара будет объявлено в ближайшее время."

    await context.bot.send_message(chat_id=user_id, text=text)


async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(context, update.effective_user.id)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "register":
        await register_user(context, query.from_user.id)


async def set_webinar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("❌ Использование: /setwebinar <секунды до старта>")
        return

    try:
        seconds = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Укажи число секунд!")
        return

    webinar_dt = datetime.now() + timedelta(seconds=seconds)
    context.bot_data["webinar_time"] = webinar_dt

    await schedule_webinar_jobs(context, webinar_dt)

    await update.message.reply_text(
        f"✅ Время вебинара успешно установлено!\n\n"
        f"Старт: {webinar_dt.strftime('%d.%m.%Y %H:%M')}\n"
        f"Напоминания и ссылка будут отправлены автоматически всем записавшимся."
    )


async def reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    webinar_time: datetime | None = context.bot_data.get("webinar_time")
    if not webinar_time or webinar_time <= datetime.now():
        await update.message.reply_text("Вебинар ещё не запланирован или уже прошёл.")
        return

    left = webinar_time - datetime.now()
    hours = int(left.total_seconds() // 3600)
    minutes = int((left.total_seconds() % 3600) // 60)

    await update.message.reply_text(
        f"⏰ Напоминание!\n\n"
        f"Вебинар по трейдингу начнётся через {hours} ч. {minutes} мин.\n"
        f"📅 {format_webinar_time(webinar_time)}\n\n"
        f"Будь онлайн — будет полезно!"
    )


async def webinar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = f"🎥 Ссылка на вебинар по трейдингу:\n\n{WEBINAR_LINK}\n\nПрисоединяйся прямо сейчас!"
    await broadcast_message(context, text)
    await update.message.reply_text("✅ Ссылка отправлена всем записавшимся.")


async def offer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        f"🔥 Вебинар завершён! Надеюсь, ты получил реальную ценность.\n\n"
        f"Хочешь продолжить и получить **полный платный курс** по трейдингу с моими проверенными стратегиями, "
        f"шаблонами и личной поддержкой?\n\n"
        f"Курс включает:\n"
        f"• Глубокий разбор продвинутых стратегий\n"
        f"• Доступ к закрытым материалам\n"
        f"• Персональные рекомендации\n\n"
        f"Места в курсе строго ограничены!\n\n"
        f"Напиши мне в личные сообщения прямо сейчас и забронируй место:\n"
        f"{MENTOR_USERNAME}"
    )
    await broadcast_message(context, text)
    await update.message.reply_text("✅ Продающее предложение отправлено всем записавшимся.")


# ====================== MAIN ======================

def main() -> None:
    application = Application.builder().token(TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register_command))
    application.add_handler(CommandHandler("setwebinar", set_webinar))
    application.add_handler(CommandHandler("reminder", reminder))
    application.add_handler(CommandHandler("webinar", webinar_command))
    application.add_handler(CommandHandler("offer", offer))

    # Кнопки
    application.add_handler(CallbackQueryHandler(handle_callback))

    print("🤖 Бот запущен и готов к работе!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()