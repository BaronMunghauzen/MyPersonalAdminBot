import asyncio
import os
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Настройка логгирования
logging.basicConfig(level=logging.INFO)


# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Ваш user_id

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Планировщик задач
scheduler = AsyncIOScheduler()

# Подключение к базе данных
DATABASE = "tasks.db"

# Клавиатура для управления
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Добавить задачу"), KeyboardButton(text="Завершенные задачи")],
        [KeyboardButton(text="Задачи по категориям"), KeyboardButton(text="Мои невыполненные задачи")],
        [KeyboardButton(text="Удалить задачу"), KeyboardButton(text="Завершить задачу")],
        [KeyboardButton(text="Удалить категорию")],
    ],
    resize_keyboard=True,
)

# Админская клавиатура
admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Добавить задачу"), KeyboardButton(text="Завершенные задачи")],
        [KeyboardButton(text="Задачи по категориям"), KeyboardButton(text="Мои невыполненные задачи")],
        [KeyboardButton(text="Удалить задачу"), KeyboardButton(text="Завершить задачу")],
        [KeyboardButton(text="Удалить категорию")],
        [KeyboardButton(text="Статистика")],
    ],
    resize_keyboard=True,
)



# Состояния для FSM (Finite State Machine)
class TaskStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_due_date = State()
    waiting_for_category = State()
    waiting_for_new_category = State()
    waiting_for_recurrence = State()
    editing_task = State()


# Инициализация базы данных
async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, is_active BOOLEAN DEFAULT 1)"
        )
        await db.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            "id INTEGER PRIMARY KEY, "
            "user_id INTEGER, "
            "title TEXT, "
            "description TEXT, "
            "status TEXT DEFAULT 'active', "
            "category TEXT, "
            "due_date TEXT, "
            "completed_at TEXT"  # Новый столбец для даты завершения
            ")"
        )
        await db.commit()
        await db.execute(
            "CREATE TABLE IF NOT EXISTS recurring_tasks (id INTEGER PRIMARY KEY, task_id INTEGER, interval TEXT, next_date TEXT)"
        )
        await db.execute(
            "CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT)"
        )
        await db.commit()


# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)", (user_id, username))
        await db.commit()

    if user_id == ADMIN_ID:  # Если пользователь — админ
        await message.answer("Добро пожаловать в Task Manager, админ!", reply_markup=admin_keyboard)
    else:
        await message.answer("Добро пожаловать в Task Manager!", reply_markup=main_keyboard)


## Добавление задачи
@dp.message(F.text == "Добавить задачу")
async def add_task(message: types.Message, state: FSMContext):
    await message.answer("Введите название задачи:")
    await state.set_state(TaskStates.waiting_for_title)

@dp.message(TaskStates.waiting_for_title)
async def process_task_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Введите описание задачи:")
    await state.set_state(TaskStates.waiting_for_description)

@dp.message(TaskStates.waiting_for_description)
async def process_task_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)

    # Получаем список существующих категорий пользователя
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT DISTINCT name FROM categories WHERE user_id = ?", (user_id,))
        categories = await cursor.fetchall()

    # Создаем клавиатуру с существующими категориями и кнопкой для добавления новой
    keyboard_buttons = [
        [KeyboardButton(text=category[0])] for category in categories if category[0]  # Существующие категории
    ]
    keyboard_buttons.append([KeyboardButton(text="Добавить новую категорию")])  # Кнопка для добавления новой категории

    keyboard = ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True,
    )

    await message.answer("Выберите категорию задачи или добавьте новую:", reply_markup=keyboard)
    await state.set_state(TaskStates.waiting_for_category)

@dp.message(TaskStates.waiting_for_category, F.text != "Добавить новую категорию")
async def process_task_category(message: types.Message, state: FSMContext):
    category = message.text
    await state.update_data(category=category)

    # Переходим к выбору периодичности
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Ежедневно")],
            [KeyboardButton(text="Еженедельно")],
            [KeyboardButton(text="Каждые две недели")],
            [KeyboardButton(text="Ежемесячно")],
            [KeyboardButton(text="Без повторения")],
        ],
        resize_keyboard=True,
    )
    await message.answer("Выберите периодичность задачи:", reply_markup=keyboard)
    await state.set_state(TaskStates.waiting_for_recurrence)

@dp.message(TaskStates.waiting_for_category, F.text == "Добавить новую категорию")
async def ask_for_new_category(message: types.Message, state: FSMContext):
    await message.answer("Введите название новой категории:")
    await state.set_state(TaskStates.waiting_for_new_category)

@dp.message(TaskStates.waiting_for_new_category)
async def process_new_category(message: types.Message, state: FSMContext):
    new_category = message.text
    user_id = message.from_user.id

    async with aiosqlite.connect(DATABASE) as db:
        # Проверяем, существует ли такая категория для данного пользователя
        cursor = await db.execute(
            "SELECT id FROM categories WHERE user_id = ? AND name = ?",
            (user_id, new_category),
        )
        existing_category = await cursor.fetchone()

        if existing_category:
            # Если категория уже существует, просто используем её
            await message.answer(f"Категория '{new_category}' уже существует. Используем её.")
        else:
            # Если категории нет, добавляем её в базу данных
            await db.execute("INSERT INTO categories (user_id, name) VALUES (?, ?)", (user_id, new_category))
            await db.commit()
            await message.answer(f"Новая категория '{new_category}' добавлена.")

    # Обновляем данные в состоянии
    await state.update_data(category=new_category)

    # Переходим к выбору периодичности
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Ежедневно")],
            [KeyboardButton(text="Еженедельно")],
            [KeyboardButton(text="Каждые две недели")],
            [KeyboardButton(text="Ежемесячно")],
            [KeyboardButton(text="Без повторения")],
        ],
        resize_keyboard=True,
    )
    await message.answer("Выберите периодичность задачи:", reply_markup=keyboard)
    await state.set_state(TaskStates.waiting_for_recurrence)

@dp.message(TaskStates.waiting_for_recurrence)
async def process_task_recurrence(message: types.Message, state: FSMContext):
    recurrence = message.text
    user_id = message.from_user.id
    data = await state.get_data()

    # Сохраняем задачу
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "INSERT INTO tasks (user_id, title, description, category) VALUES (?, ?, ?, ?)",
            (user_id, data["title"], data["description"], data["category"]),
        )
        task_id = cursor.lastrowid

        # Если задача повторяющаяся, сохраняем информацию о повторении
        if recurrence != "Без повторения":
            next_date = calculate_next_date(recurrence)
            await db.execute(
                "INSERT INTO recurring_tasks (task_id, interval, next_date) VALUES (?, ?, ?)",
                (task_id, recurrence, next_date),
            )
        await db.commit()

    if user_id == ADMIN_ID:  # Если пользователь — админ
        await message.answer(f"Задача добавлена! Периодичность: {recurrence}", reply_markup=admin_keyboard)
    else:
        await message.answer(f"Задача добавлена! Периодичность: {recurrence}", reply_markup=main_keyboard)
    await state.clear()

def calculate_next_date(interval: str) -> str:
    today = datetime.now()
    if interval == "Ежедневно":
        next_date = today + relativedelta(days=1)
    elif interval == "Еженедельно":
        next_date = today + relativedelta(weeks=1)
    elif interval == "Каждые две недели":
        next_date = today + relativedelta(weeks=2)
    elif interval == "Ежемесячно":
        next_date = today + relativedelta(months=1)  # Корректный расчет для ежемесячных задач
    else:
        next_date = today
    return next_date.strftime("%Y-%m-%d")

async def create_recurring_tasks():
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT task_id, interval, next_date FROM recurring_tasks WHERE next_date = ?", (today,))
        recurring_tasks = await cursor.fetchall()

        for task in recurring_tasks:
            task_id, interval, next_date = task
            # Создаем новую задачу на основе повторяющейся
            cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            original_task = await cursor.fetchone()

            if original_task:
                user_id, title, description, status, category = original_task[1:6]
                status = 'active'
                await db.execute(
                    "INSERT INTO tasks (user_id, title, description, status, category) VALUES (?, ?, ?, ?, ?)",
                    (user_id, title, description, status, category),
                )
                # Обновляем следующую дату для повторяющейся задачи
                new_next_date = calculate_next_date(interval)
                await db.execute(
                    "UPDATE recurring_tasks SET next_date = ? WHERE id = ?",
                    (new_next_date, task_id),
                )
        await db.commit()

# Планировщик для создания повторяющихся задач
def schedule_recurring_tasks():
    scheduler.add_job(create_recurring_tasks, "cron", hour=0, minute=0)  # Запуск каждый день в 00:00

# Просмотр задач
@dp.message(F.text == "Мои невыполненные задачи")
async def show_tasks(message: types.Message):
    user_id = message.from_user.id

    async with aiosqlite.connect(DATABASE) as db:
        # Получаем только активные задачи
        cursor = await db.execute(
            "SELECT tasks.id, tasks.title, tasks.description, tasks.category, recurring_tasks.interval "
            "FROM tasks "
            "LEFT JOIN recurring_tasks ON tasks.id = recurring_tasks.task_id "
            "WHERE tasks.user_id = ? AND tasks.status = 'active'",
            (user_id,),
        )
        tasks = await cursor.fetchall()

    if tasks:
        # Группируем задачи по категориям
        tasks_by_category = {}
        for task in tasks:
            category = task[3]  # Категория задачи
            if category not in tasks_by_category:
                tasks_by_category[category] = []
            tasks_by_category[category].append(task)

        # Формируем сообщение с задачами по категориям
        tasks_text = "Ваши невыполненные задачи:\n"
        for category, tasks_in_category in tasks_by_category.items():
            tasks_text += f"\nВ категории {category}:\n"
            for index, task in enumerate(tasks_in_category, start=1):
                task_id, title, description, category, interval = task
                # Добавляем информацию о периодичности, если она есть
                interval_info = f" ({interval})" if interval else ""
                tasks_text += f"{index}. {title}{interval_info}\n    📝 {description}\n"

        await message.answer(tasks_text)
    else:
        await message.answer("У вас нет активных задач.")

# Получение списка задач с пагинацией
async def get_tasks(user_id: int, page: int = 0, limit: int = 5):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND status = 'active' ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, page * limit),
        )
        tasks = await cursor.fetchall()
        return tasks


# Создание inline-клавиатуры с пагинацией
def build_tasks_keyboard(tasks: list, page: int, action: str):
    builder = InlineKeyboardBuilder()
    for task in tasks:
        builder.add(InlineKeyboardButton(text=task[2], callback_data=f"{action}_{task[0]}"))

    # Кнопки пагинации
    if page > 0:
        builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{action}_prev_{page}"))
    if len(tasks) == 5:  # Если есть следующая страница
        builder.add(InlineKeyboardButton(text="➡️ Вперед", callback_data=f"{action}_next_{page}"))

    builder.adjust(1)  # 1 кнопка в строке
    return builder.as_markup()


# Обработчик для кнопки "Задачи по категориям"
@dp.message(F.text == "Задачи по категориям")
async def show_categories(message: types.Message):
    user_id = message.from_user.id
    today_data = datetime.now().strftime("%Y-%m-%d")

    # Получаем список уникальных категорий пользователя
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT DISTINCT category FROM tasks WHERE user_id = ? and (completed_at is null or completed_at = ?)", (user_id, today_data,))
        categories = await cursor.fetchall()

    if categories:
        # Создаем inline-клавиатуру с категориями
        keyboard = InlineKeyboardBuilder()
        for category in categories:
            if category[0]:  # Проверяем, что категория не пустая
                keyboard.add(InlineKeyboardButton(text=category[0], callback_data=f"category_{category[0]}"))
        keyboard.adjust(1)  # 1 кнопка в строке
        await message.answer("Выберите категорию:", reply_markup=keyboard.as_markup())
    else:
        await message.answer("У вас нет задач с категориями.")

# Обработчик для выбора категории
@dp.callback_query(F.data.startswith("category_"))
async def show_tasks_by_category(callback: types.CallbackQuery):
    today_data = datetime.now().strftime("%Y-%m-%d")
    user_id = callback.from_user.id
    category = callback.data.split("_")[1]  # Получаем выбранную категорию

    # Получаем задачи из выбранной категории
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT id, user_id, title, description, status FROM tasks WHERE user_id = ? AND category = ? and (completed_at is null or completed_at = ?)",
                                  (user_id, category, today_data))
        tasks = await cursor.fetchall()

    if tasks:
        tasks_text = ""
        for index, task in enumerate(tasks, start=1):
            status_emoji = "✅" if task[4] == "completed" else "⏳"  # Смайлик для статуса
            tasks_text += f"{index}. {status_emoji} {task[2]}\n    📝 {task[3]}\n"  # Название задачи
        await callback.message.answer(f"Задачи в категории '{category}':\n{tasks_text}")
    else:
        await callback.message.answer(f"В категории '{category}' нет задач.")
    await callback.answer()

# Удаление задачи
@dp.message(F.text == "Удалить задачу")
async def delete_task(message: types.Message):
    user_id = message.from_user.id
    tasks = await get_tasks(user_id, page=0)

    if tasks:
        keyboard = build_tasks_keyboard(tasks, page=0, action="delete")
        await message.answer("Выберите задачу для удаления:", reply_markup=keyboard)
    else:
        await message.answer("У вас нет задач для удаления.")


# Обработчик для удаления задачи
@dp.callback_query(F.data.startswith("delete_"))
async def handle_delete_task(callback: types.CallbackQuery):
    data = callback.data.split("_")
    user_id = callback.from_user.id

    if data[1] == "prev" or data[1] == "next":
        # Пагинация
        page = int(data[2])
        if data[1] == "prev":
            page -= 1
        elif data[1] == "next":
            page += 1

        tasks = await get_tasks(user_id, page=page)
        keyboard = build_tasks_keyboard(tasks, page=page, action="delete")
        await callback.message.edit_text("Выберите задачу для удаления:", reply_markup=keyboard)
    else:
        # Удаление задачи
        task_id = int(data[1])
        async with aiosqlite.connect(DATABASE) as db:
            await db.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
            await db.commit()

        await callback.message.answer("Задача удалена!")
        await callback.answer()


# Завершение задачи
@dp.message(F.text == "Завершить задачу")
async def complete_task(message: types.Message):
    user_id = message.from_user.id
    tasks = await get_tasks(user_id, page=0)

    if tasks:
        keyboard = build_tasks_keyboard(tasks, page=0, action="complete")
        await message.answer("Выберите задачу для завершения:", reply_markup=keyboard)
    else:
        await message.answer("У вас нет задач для завершения.")


# Обработчик для завершения задачи
@dp.callback_query(F.data.startswith("complete_"))
async def handle_complete_task(callback: types.CallbackQuery):
    data = callback.data.split("_")
    user_id = callback.from_user.id

    if data[1] == "prev" or data[1] == "next":
        # Пагинация
        page = int(data[2])
        if data[1] == "prev":
            page -= 1
        elif data[1] == "next":
            page += 1

        tasks = await get_tasks(user_id, page=page)
        keyboard = build_tasks_keyboard(tasks, page=page, action="complete")
        await callback.message.edit_text("Выберите задачу для завершения:", reply_markup=keyboard)
    else:
        # Завершение задачи
        task_id = int(data[1])
        completed_at = datetime.now().strftime("%Y-%m-%d")  # Текущая дата
        async with aiosqlite.connect(DATABASE) as db:
            await db.execute(
                "UPDATE tasks SET status = 'completed', completed_at = ? WHERE id = ? AND user_id = ?",
                (completed_at, task_id, user_id),
            )
            await db.commit()

        await callback.message.answer("Задача завершена!")
        await callback.answer()


# Получение списка дат с завершенными задачами
async def get_completed_dates(user_id: int, page: int = 0, limit: int = 5):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT DISTINCT completed_at FROM tasks WHERE user_id = ? AND status = 'completed' AND completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, page * limit),
        )
        dates = await cursor.fetchall()
        return [date[0] for date in dates]


# Создание inline-клавиатуры с пагинацией
def build_dates_keyboard(dates: list, page: int):
    builder = InlineKeyboardBuilder()
    for date in dates:
        if date:  # Проверяем, что date не равно None
            builder.add(InlineKeyboardButton(text=str(date), callback_data=f"completed_{date}"))

    # Кнопки пагинации
    if page > 0:
        builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"prev_{page}"))
    if len(dates) == 5:  # Если есть следующая страница
        builder.add(InlineKeyboardButton(text="➡️ Вперед", callback_data=f"next_{page}"))

    builder.adjust(2)  # 2 кнопки в строке
    return builder.as_markup()


# Обработчик для кнопки "Завершенные задачи"
@dp.message(F.text == "Завершенные задачи")
async def show_completed_dates(message: types.Message):
    user_id = message.from_user.id
    dates = await get_completed_dates(user_id, page=0)

    if dates:
        keyboard = build_dates_keyboard(dates, page=0)
        await message.answer("Выберите дату для просмотра завершенных задач:", reply_markup=keyboard)
    else:
        await message.answer("У вас нет завершенных задач.")

# Обработчик для выбора даты завершенных задач
@dp.callback_query(F.data.startswith("completed_"))
async def show_completed_tasks(callback: types.CallbackQuery):
    date = callback.data.split("_")[1]
    user_id = callback.from_user.id

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id, user_id, title, description, status, category, completed_at FROM tasks WHERE user_id = ? AND status = 'completed' AND completed_at = ?",
            (user_id, date),
        )
        tasks = await cursor.fetchall()

    if tasks:
        # Группируем задачи по категориям
        tasks_by_category = {}
        for task in tasks:
            category = task[5]  # Категория задачи
            if category not in tasks_by_category:
                tasks_by_category[category] = []
            tasks_by_category[category].append(task)

        # Формируем сообщение с задачами по категориям
        tasks_text = f"Завершенные задачи на {date}:\n"
        for category, tasks_in_category in tasks_by_category.items():
            tasks_text += f"\nВ категории {category}:\n"
            for index, task in enumerate(tasks_in_category, start=1):
                tasks_text += (
                    f"{index}. 📌 {task[2]}\n"  # Название задачи
                    f"   📝 {task[3]}\n"  # Описание задачи
                )

        await callback.message.answer(tasks_text)
    else:
        await callback.message.answer(f"На {date} нет завершенных задач.")


# Обработчик для пагинации
@dp.callback_query(F.data.startswith(("prev_", "next_")))
async def handle_pagination(callback: types.CallbackQuery):
    action, page = callback.data.split("_")
    page = int(page)
    user_id = callback.from_user.id

    if action == "prev":
        page -= 1
    elif action == "next":
        page += 1

    dates = await get_completed_dates(user_id, page=page)
    keyboard = build_dates_keyboard(dates, page=page)
    await callback.message.edit_text("Выберите дату для просмотра завершенных задач:", reply_markup=keyboard)


# Отключение бота
@dp.message(F.text == "Отключить бота")
async def disable_bot(message: types.Message):
    user_id = message.from_user.id

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        await db.commit()

    await message.answer("Бот отключен. Чтобы снова включить, отправьте /start.")


# Обработчик для кнопки "Статистика"
@dp.message(F.text == "Статистика", F.from_user.id == ADMIN_ID)
async def admin_stats(message: types.Message):
    async with aiosqlite.connect(DATABASE) as db:
        # Получаем количество пользователей
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        total_users = await cursor.fetchone()

        # Получаем количество задач
        cursor = await db.execute("SELECT COUNT(*) FROM tasks")
        total_tasks = await cursor.fetchone()

        # Получаем количество завершенных задач
        cursor = await db.execute("SELECT COUNT(*) FROM tasks WHERE status = 'completed'")
        completed_tasks = await cursor.fetchone()

    # Формируем сообщение со статистикой
    stats_text = (
        f"📊 Статистика:\n"
        f"👤 Пользователи: {total_users[0]}\n"
        f"📝 Всего задач: {total_tasks[0]}\n"
        f"✅ Завершенных задач: {completed_tasks[0]}"
    )
    await message.answer(stats_text)

# Обработчик для кнопки "Удалить категорию"
@dp.message(F.text == "Удалить категорию")
async def delete_category(message: types.Message):
    user_id = message.from_user.id

    # Получаем список уникальных категорий пользователя
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT DISTINCT name FROM categories WHERE user_id = ?", (user_id,))
        categories = await cursor.fetchall()

    if categories:
        # Создаем inline-клавиатуру с категориями
        keyboard = InlineKeyboardBuilder()
        for category in categories:
            keyboard.add(InlineKeyboardButton(text=category[0], callback_data=f"delet_category_{category[0]}"))
        keyboard.adjust(1)  # 1 кнопка в строке
        await message.answer("Выберите категорию для удаления:", reply_markup=keyboard.as_markup())
    else:
        await message.answer("У вас нет категорий для удаления.")

# Обработчик для удаления категории
@dp.callback_query(F.data.startswith("delet_category_"))
async def handle_delete_category(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    category_name = callback.data.split("_")[2]  # Получаем название категории
    print(category_name)
    async with aiosqlite.connect(DATABASE) as db:
        # Удаляем категорию из таблицы categories
        await db.execute("DELETE FROM categories WHERE user_id = ? AND name = ?", (user_id, category_name))
        await db.commit()

    await callback.message.answer(f"Категория '{category_name}' удалена.")
    await callback.answer()

# Перенос невыполненных задач на следующий день
# async def move_unfinished_tasks():
#     today = datetime.now().strftime("%Y-%m-%d")
#     tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
#
#     async with aiosqlite.connect(DATABASE) as db:
#         await db.execute(
#             "UPDATE tasks SET due_date = ? WHERE due_date = ? AND status = 'active'",
#             (tomorrow, today),
#         )
#         await db.commit()
#
#     logging.info(f"Задачи перенесены на {tomorrow}")
#
#
# # Планировщик для переноса задач
# def schedule_task_mover():
#     scheduler.add_job(move_unfinished_tasks, "cron", hour=0, minute=0)

# Обработчик для неизвестных команд
@dp.message()
async def handle_unknown(message: types.Message):
    await message.answer("Извините, я не понимаю эту команду. Используйте меню.")


# Запуск бота
async def main():
    await init_db()
    # schedule_task_mover()
    schedule_recurring_tasks()
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == '__main__':

    asyncio.run(main())
