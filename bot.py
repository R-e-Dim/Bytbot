import asyncio
import logging
import os
import sqlite3
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

TOKEN = "8874249243:AAHCO9bEJAQKU-S-xdSrwlP0YFt0enqPcuo"
ADMIN_ID = 463567235

bot = Bot(token=TOKEN)
router = Router()

def init_db():
    conn = sqlite3.connect("couple_bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shopping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT,
            added_by TEXT,
            status TEXT DEFAULT 'active'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS water (
            user_name TEXT PRIMARY KEY,
            amount INTEGER DEFAULT 0,
            date TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            assigned_to TEXT,
            deadline TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()

init_db()

class Form(StatesGroup):
    waiting_for_shopping_item = State()
    waiting_for_task_title = State()

def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Список покупок", callback_data="menu_shopping"),
         InlineKeyboardButton(text="💧 Трекер воды", callback_data="menu_water")],
        [InlineKeyboardButton(text="📋 Домашние задачи", callback_data="menu_tasks"),
         InlineKeyboardButton(text="📊 Сводка за день", callback_data="menu_summary")]
    ])

def get_user_status(user_id: int) -> str:
    if user_id == ADMIN_ID:
        return 'approved'
    
    conn = sqlite3.connect("couple_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM users WHERE user_id=?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else 'new'

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    status = get_user_status(user_id)

    if status == 'approved':
        await message.answer(
            "👋 Привет! Добро пожаловать в ваш общий бот.\nВыберите нужный раздел в меню ниже:",
            reply_markup=get_main_menu()
        )
    elif status == 'pending':
        await message.answer("⏳ Ваш запрос на доступ отправлен владельцу бота. Ожидайте подтверждения.")
    elif status == 'blocked':
        await message.answer("❌ Вам отказано в доступе к этому боту.")
    else:
        conn = sqlite3.connect("couple_bot.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, username, full_name, status) VALUES (?, ?, ?, 'pending')",
            (user_id, message.from_user.username or "", message.from_user.first_name)
        )
        conn.commit()
        conn.close()

        await message.answer("⏳ Вы запросили доступ к боту. Ожидайте, пока владелец подтвердит его.")

        if ADMIN_ID != 0:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Разрешить", callback_data=f"approve_{user_id}"),
                    InlineKeyboardButton(text="❌ Запретить", callback_data=f"block_{user_id}")
                ]
            ])
            await bot.send_message(
                ADMIN_ID,
                f"🔔 **Новый запрос на доступ!**\n\nИмя: {message.from_user.first_name}\nUsername: @{message.from_user.username or 'нет'}\nID: `{user_id}`",
                reply_markup=kb,
                parse_mode="Markdown"
            )

@router.callback_query(F.data.startswith(("approve_", "block_")))
async def handle_access_request(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("У вас нет прав для этого действия.", show_alert=True)
        return

    action, target_user_id = callback.data.split("_")
    target_user_id = int(target_user_id)
    new_status = 'approved' if action == 'approve' else 'blocked'

    conn = sqlite3.connect("couple_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status=? WHERE user_id=?", (new_status, target_user_id))
    conn.commit()
    conn.close()

    if action == 'approve':
        await callback.message.edit_text(callback.message.text + "\n\n✅ **Статус: Доступ разрешен**", parse_mode="Markdown")
        try:
            await bot.send_message(target_user_id, "🎉 Ваш доступ подтвержден! Нажмите /start, чтобы открыть меню.")
        except:
            pass
    else:
        await callback.message.edit_text(callback.message.text + "\n\n❌ **Статус: Доступ запрещен**", parse_mode="Markdown")
        try:
            await bot.send_message(target_user_id, "❌ Владелец отклонил ваш запрос на доступ.")
        except:
            pass
    
    await callback.answer()

# --- СПИСОК ПОКУПОК ---
@router.callback_query(F.data == "menu_shopping")
async def show_shopping(callback: CallbackQuery):
    if get_user_status(callback.from_user.id) != 'approved':
        await callback.answer("Нет доступа!", show_alert=True)
        return
    conn = sqlite3.connect("couple_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, item, added_by FROM shopping WHERE status='active'")
    items = cursor.fetchall()
    conn.close()

    text = "🛒 **Список покупок:**\n\n"
    keyboard = []
    if items:
        for row_id, item, added_by in items:
            text += f"• {item} (добавил(-а): {added_by})\n"
            keyboard.append([InlineKeyboardButton(text=f"✅ Куплено: {item}", callback_data=f"buy_{row_id}")])
    else:
        text += "Список пуст 🎉\n"

    keyboard.append([InlineKeyboardButton(text="➕ Добавить покупку", callback_data="add_shopping")])
    keyboard.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")

@router.callback_query(F.data.startswith("buy_"))
async def buy_item(callback: CallbackQuery):
    row_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect("couple_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE shopping SET status='completed' WHERE id=?", (row_id,))
    conn.commit()
    conn.close()
    await callback.answer("Товар куплен и удален из списка! 🎉")
    await show_shopping(callback)

@router.callback_query(F.data == "add_shopping")
async def ask_shopping_item(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название товара, который нужно купить:")
    await state.set_state(Form.waiting_for_shopping_item)
    await callback.answer()

@router.message(Form.waiting_for_shopping_item)
async def process_shopping_item(message: Message, state: FSMContext):
    if get_user_status(message.from_user.id) != 'approved':
        return
    item_name = message.text
    user_name = message.from_user.first_name

    conn = sqlite3.connect("couple_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO shopping (item, added_by) VALUES (?, ?)", (item_name, user_name))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(f"✅ Товар «{item_name}» успешно добавлен! Нажмите /start, чтобы вернуться в меню.")

# --- ТРЕКЕР ВОДЫ ---
@router.callback_query(F.data == "menu_water")
async def show_water(callback: CallbackQuery):
    if get_user_status(callback.from_user.id) != 'approved':
        await callback.answer("Нет доступа!", show_alert=True)
        return
    
    user_name = callback.from_user.first_name
    today = datetime.now().strftime("%Y-%m-%d")
    
    conn = sqlite3.connect("couple_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT amount, date FROM water WHERE user_name=?", (user_name,))
    row = cursor.fetchone()
    
    if row:
        amount, db_date = row
        if db_date != today:
            amount = 0
            cursor.execute("UPDATE water SET amount=0, date=? WHERE user_name=?", (today, user_name))
            conn.commit()
    else:
        amount = 0
        cursor.execute("INSERT INTO water (user_name, amount, date) VALUES (?, 0, ?)", (user_name, today))
        conn.commit()
        
    conn.close()
    
    text = f"💧 **Трекер воды на сегодня:**\n\nВы выпили: **{amount * 250} мл** ({amount} стак.) 🥤\n\n*Рекомендуемая норма: ~2 литра (8 стаканов)*"
    
    keyboard = [
        [InlineKeyboardButton(text="➕ Выпить стакан (250 мл)", callback_data="add_water")],
        [InlineKeyboardButton(text="🔄 Сбросить счетчик", callback_data="reset_water")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "add_water")
async def add_water(callback: CallbackQuery):
    user_name = callback.from_user.first_name
    today = datetime.now().strftime("%Y-%m-%d")
    
    conn = sqlite3.connect("couple_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT amount, date FROM water WHERE user_name=?", (user_name,))
    row = cursor.fetchone()
    
    if row:
        amount, db_date = row
        if db_date != today:
            amount = 1
            cursor.execute("UPDATE water SET amount=1, date=? WHERE user_name=?", (today, user_name))
        else:
            amount += 1
            cursor.execute("UPDATE water SET amount=? WHERE user_name=?", (amount, user_name))
    else:
        amount = 1
        cursor.execute("INSERT INTO water (user_name, amount, date) VALUES (?, 1, ?)", (user_name, today))
        
    conn.commit()
    conn.close()
    
    await callback.answer("+1 стакан воды! 💧")
    await show_water(callback)

@router.callback_query(F.data == "reset_water")
async def reset_water(callback: CallbackQuery):
    user_name = callback.from_user.first_name
    today = datetime.now().strftime("%Y-%m-%d")
    
    conn = sqlite3.connect("couple_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE water SET amount=0, date=? WHERE user_name=?", (today, user_name))
    conn.commit()
    conn.close()
    
    await callback.answer("Счетчик воды сброшен!")
    await show_water(callback)

# --- ДОМАШНИЕ ЗАДАЧИ ---
@router.callback_query(F.data == "menu_tasks")
async def show_tasks(callback: CallbackQuery):
    if get_user_status(callback.from_user.id) != 'approved':
        await callback.answer("Нет доступа!", show_alert=True)
        return
    conn = sqlite3.connect("couple_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM tasks WHERE status='pending'")
    tasks = cursor.fetchall()
    conn.close()

    text = "📋 **Домашние задачи:**\n\n"
    keyboard = []
    if tasks:
        for row_id, title in tasks:
            text += f"• {title}\n"
            keyboard.append([InlineKeyboardButton(text=f"✅ Выполнено: {title}", callback_data=f"done_task_{row_id}")])
    else:
        text += "Все задачи выполнены! 🎉\n"

    keyboard.append([InlineKeyboardButton(text="➕ Добавить задачу", callback_data="add_task")])
    keyboard.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")

@router.callback_query(F.data.startswith("done_task_"))
async def finish_task(callback: CallbackQuery):
    row_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect("couple_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET status='completed' WHERE id=?", (row_id,))
    conn.commit()
    conn.close()
    await callback.answer("Задача выполнена! 👍")
    await show_tasks(callback)

@router.callback_query(F.data == "add_task")
async def ask_task_title(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название новой задачи:")
    await state.set_state(Form.waiting_for_task_title)
    await callback.answer()

@router.message(Form.waiting_for_task_title)
async def process_task_title(message: Message, state: FSMContext):
    if get_user_status(message.from_user.id) != 'approved':
        return
    task_title = message.text

    conn = sqlite3.connect("couple_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (title) VALUES (?)", (task_title,))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(f"✅ Задача «{task_title}» успешно добавлена! Нажмите /start, чтобы вернуться в меню.")

# --- НАВИГАЦИЯ И ЗАГЛУШКИ ---
@router.callback_query(F.data == "main_menu")
async def return_to_main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "👋 Главное меню. Выберите нужный раздел:",
        reply_markup=get_main_menu()
    )
    await callback.answer()

@router.callback_query(F.data == "menu_summary")
async def stub_summary(callback: CallbackQuery):
    keyboard = [[InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]]
    await callback.message.edit_text(
        "🚧 Этот раздел находится в разработке и скоро появится!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()

# Веб-сервер с автоматическим определением порта для Render
async def handle(request):
    return web.Response(text="Bot is running!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    
    await web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
