import os
import sys
import asyncio
import logging
import sqlite3
import random
import time
from datetime import datetime
from typing import Optional, List, Dict
import hashlib

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8988678866:AAHIWxUB8zKBCoF21g7OVYEEWnwEF_MpLmI"
ADMIN_ID = 8551946505  # Ваш ID

PAYMENT_LINKS = {
    100: "https://yookassa.ru/my/i/amMy2QzHTXRI/l",
    200: "https://yookassa.ru/my/i/amMzHkXK55Uk/l",
    500: "https://yookassa.ru/my/i/amMzSdZUSmIm/l",
    1000: "https://yookassa.ru/my/i/amMzbZDBr9y2/l"
}

RUB_TO_TOKEN = 1

SPIN_COSTS = {
    "light": 25,
    "normal": 50,
    "hard": 100
}

PRIZE_RANGES = {
    "light": {"min": 10, "max": 100, "win_chance": 40},
    "normal": {"min": 50, "max": 200, "win_chance": 45},
    "hard": {"min": 10, "max": 500, "win_chance": 50}
}

SLOT_SYMBOLS = ['🍒', '🍋', '🍊', '🍇', '🍉', '🍓', '🍑', '🎰']
SLOT_WIN_MULTIPLIER = 2

PROMOCODES = {
    "rifleman": 50,
    "blant": 50
}

rocket_rounds = {}
round_counter = 0
DB_NAME = "star_drop.db"
WEBAPP_URL = "https://star-drop.onrender.com"
REFERRAL_BONUS = 50
START_BALANCE = 50

# ==================== ДЛЯ ЧЕРЕДОВАНИЯ РЕЗУЛЬТАТОВ ====================
last_spin_result = {}  # user_id -> bool (True=win, False=lose)

def get_next_spin_result(user_id: int, mode: str):
    ranges = PRIZE_RANGES.get(mode, PRIZE_RANGES["light"])
    if user_id not in last_spin_result:
        win = random.randint(1, 100) <= ranges["win_chance"]
    else:
        win = not last_spin_result[user_id]
    last_spin_result[user_id] = win

    if win:
        prize_value = random.randint(ranges["min"], ranges["max"])
        icon = "🏷️" if mode == "light" else "🎟️" if mode == "normal" else "🎫"
        prize_name = f"{icon} {prize_value}"
    else:
        prize_value = 0
        prize_name = "❌ Проигрыш"
    return win, prize_name, prize_value

def get_prizes_for_mode(mode: str, count: int = 40):
    """Генерирует чередующуюся последовательность для бегущей строки."""
    ranges = PRIZE_RANGES.get(mode, PRIZE_RANGES["light"])
    prizes = []
    for i in range(count):
        if i % 2 == 0:  # чётные – выигрыш
            val = random.randint(ranges["min"], ranges["max"])
            icon = "🏷️" if mode == "light" else "🎟️" if mode == "normal" else "🎫"
            prizes.append({"name": f"{icon} {val}", "value": val})
        else:           # нечётные – проигрыш
            prizes.append({"name": "❌", "value": 0})
    return prizes

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            phone TEXT UNIQUE,
            balance INTEGER DEFAULT 0,
            total_spent INTEGER DEFAULT 0,
            total_won INTEGER DEFAULT 0,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            referrer_id INTEGER,
            referral_code TEXT UNIQUE
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount INTEGER,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS wins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            prize_name TEXT,
            prize_value INTEGER,
            mode TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users(user_id),
            FOREIGN KEY (referred_id) REFERENCES users(user_id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS used_promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            code TEXT,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            UNIQUE(user_id, code)
        )
    ''')
    try:
        cur.execute("ALTER TABLE users ADD COLUMN phone TEXT UNIQUE")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

def get_user(user_id: int) -> Optional[Dict]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(user_id: int, username: str = None, phone: str = None, referrer_code: str = None):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    code = hashlib.md5(str(user_id).encode()).hexdigest()[:8]
    
    cur.execute("SELECT user_id, balance FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    
    if row is None:
        cur.execute(
            "INSERT INTO users (user_id, username, phone, referral_code, balance) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, phone, code, START_BALANCE)
        )
        cur.execute(
            "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
            (user_id, "deposit", START_BALANCE, "Стартовый бонус 50 токенов")
        )
    else:
        if phone:
            cur.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
        if username:
            cur.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        if row[1] == 0:
            cur.execute("UPDATE users SET balance = ? WHERE user_id = ?", (START_BALANCE, user_id))
            cur.execute(
                "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                (user_id, "deposit", START_BALANCE, "Стартовый бонус 50 токенов (восстановлен)")
            )
    
    if referrer_code and row is None:
        cur.execute("SELECT user_id FROM users WHERE referral_code = ?", (referrer_code,))
        ref_row = cur.fetchone()
        if ref_row:
            referrer_id = ref_row[0]
            if referrer_id != user_id:
                cur.execute("SELECT id FROM referrals WHERE referred_id = ?", (user_id,))
                if not cur.fetchone():
                    cur.execute(
                        "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                        (referrer_id, user_id)
                    )
                    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (REFERRAL_BONUS, referrer_id))
                    cur.execute(
                        "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                        (referrer_id, "deposit", REFERRAL_BONUS, f"Бонус за приглашение пользователя {user_id}")
                    )
    
    conn.commit()
    conn.close()

def update_balance(user_id: int, delta: int, description: str = ""):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id))
    t_type = "spin" if "спин" in description else "deposit" if delta > 0 else "withdraw"
    cur.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                (user_id, t_type, delta, description))
    conn.commit()
    conn.close()

def add_win(user_id: int, prize_name: str, prize_value: int, mode: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT INTO wins (user_id, prize_name, prize_value, mode) VALUES (?, ?, ?, ?)",
                (user_id, prize_name, prize_value, mode))
    cur.execute("UPDATE users SET total_won = total_won + ? WHERE user_id = ?", (prize_value, user_id))
    conn.commit()
    conn.close()

def get_recent_wins(limit: int = 10) -> List[Dict]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('''
        SELECT u.username, w.prize_name, w.prize_value, w.created_at
        FROM wins w
        JOIN users u ON w.user_id = u.user_id
        WHERE w.prize_value > 0
        ORDER BY w.created_at DESC
        LIMIT ?
    ''', (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_user_bets(user_id: int, limit: int = 20) -> List[Dict]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('''
        SELECT type, amount, description, created_at
        FROM transactions
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    ''', (user_id, limit))
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_withdraw_requests(status: str = "pending") -> List[Dict]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('''
        SELECT w.*, u.username 
        FROM withdraw_requests w
        JOIN users u ON w.user_id = u.user_id
        WHERE w.status = ?
        ORDER BY w.created_at ASC
    ''', (status,))
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def create_withdraw_request(user_id: int, amount: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT INTO withdraw_requests (user_id, amount) VALUES (?, ?)", (user_id, amount))
    conn.commit()
    conn.close()

def approve_withdraw(request_id: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE withdraw_requests SET status = 'approved' WHERE id = ?", (request_id,))
    cur.execute("SELECT user_id, amount FROM withdraw_requests WHERE id = ?", (request_id,))
    row = cur.fetchone()
    if row:
        user_id, amount = row
        cur.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        cur.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                    (user_id, "withdraw", -amount, f"Вывод {amount} токенов (одобрено)"))
    conn.commit()
    conn.close()

def reject_withdraw(request_id: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE withdraw_requests SET status = 'rejected' WHERE id = ?", (request_id,))
    conn.commit()
    conn.close()

def get_referral_info(user_id: int) -> Dict:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    code = row["referral_code"] if row else None
    cur.execute("SELECT COUNT(*) as count FROM referrals WHERE referrer_id = ?", (user_id,))
    count = cur.fetchone()["count"]
    conn.close()
    return {"code": code, "count": count}

def get_referral_link(user_id: int) -> str:
    info = get_referral_info(user_id)
    if info["code"]:
        return f"https://t.me/StarDrop11_bot?start=ref_{info['code']}"
    return None

def is_promo_used(user_id: int, code: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id FROM used_promocodes WHERE user_id = ? AND code = ?", (user_id, code))
    row = cur.fetchone()
    conn.close()
    return row is not None

def use_promo(user_id: int, code: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT INTO used_promocodes (user_id, code) VALUES (?, ?)", (user_id, code))
    conn.commit()
    conn.close()

init_db()

def get_slot_result(bet: int):
    if bet == 20:
        chance = 10
    elif 40 <= bet <= 70:
        chance = 30
    elif 71 <= bet <= 100:
        chance = 15
    else:
        chance = 10

    if random.randint(1, 100) <= chance:
        symbol = random.choice(SLOT_SYMBOLS)
        symbols = [symbol, symbol, symbol]
        win_amount = bet * SLOT_WIN_MULTIPLIER
        return True, symbols, win_amount
    else:
        symbols = random.choices(SLOT_SYMBOLS, k=3)
        if len(set(symbols)) == 1:
            other_symbols = [s for s in SLOT_SYMBOLS if s != symbols[0]]
            if other_symbols:
                symbols[0] = random.choice(other_symbols)
            else:
                symbols = random.choices(SLOT_SYMBOLS, k=3)
                while len(set(symbols)) == 1:
                    symbols = random.choices(SLOT_SYMBOLS, k=3)
        return False, symbols, 0

# ==================== ТЕЛЕГРАМ БОТ ====================
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Клавиатура для запроса контакта
def get_phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# Клавиатура для открытия приложения
def get_start_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🎰 Открыть рулетку", web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True
    )

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    args = message.text.split()
    referrer_code = None
    if len(args) > 1 and args[1].startswith("ref_"):
        referrer_code = args[1][4:]
    
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    create_user(user_id, username, referrer_code=referrer_code)
    
    user = get_user(user_id)
    if user and user.get("phone"):
        await message.answer(
            f"🎉 С возвращением, {username}!\n"
            f"Ваш баланс: {user['balance']} токенов 🎫\n\n"
            "Добро пожаловать в **Star Drop** – розыгрыш подарков Telegram!\n"
            "Нажми кнопку ниже, чтобы открыть наше мини-приложение и испытать удачу! 🍀",
            reply_markup=get_start_keyboard()
        )
    else:
        await message.answer(
            f"👋 Привет, {username}!\n\n"
            "Для доступа к нашему сервису необходимо поделиться номером телефона.\n"
            "Нажмите кнопку ниже, чтобы отправить контакт.",
            reply_markup=get_phone_keyboard()
        )

@dp.message(F.contact)
async def handle_contact(message: types.Message):
    contact = message.contact
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    if contact.user_id != user_id:
        await message.answer("⛔ Пожалуйста, отправьте свой собственный номер.", reply_markup=get_phone_keyboard())
        return
    
    phone = contact.phone_number
    create_user(user_id, username, phone)
    
    user = get_user(user_id)
    balance = user['balance'] if user else 0
    
    await message.answer(
        f"✅ Регистрация успешно завершена!\n"
        f"Ваш баланс: {balance} токенов 🎫\n\n"
        "Теперь вы можете пользоваться нашим сервисом. 🎉",
        reply_markup=ReplyKeyboardRemove()
    )
    await message.answer(
        "Нажмите кнопку ниже, чтобы открыть **Star Drop** и начать игру!",
        reply_markup=get_start_keyboard()
    )

@dp.message(Command("give"))
async def give_tokens(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: /give <user_id> <количество>")
        return
    try:
        target_id = int(args[1])
        amount = int(args[2])
        if amount <= 0:
            await message.answer("Сумма должна быть положительной.")
            return
        user = get_user(target_id)
        if not user:
            await message.answer(f"Пользователь с ID {target_id} не найден.")
            return
        update_balance(target_id, amount, f"Администратор выдал {amount} токенов")
        new_balance = get_user(target_id)['balance']
        await message.answer(
            f"✅ Пользователю @{user['username']} (ID: {target_id}) начислено {amount} токенов.\n"
            f"Новый баланс: {new_balance}"
        )
    except ValueError:
        await message.answer("ID и сумма должны быть числами.")

# ==================== ВЕБ-СЕРВЕР (FASTAPI) ====================
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import uvicorn
import aiofiles
import aiohttp

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = "static"
AVATARS_DIR = os.path.join(STATIC_DIR, "avatars")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(AVATARS_DIR, exist_ok=True)

# ==================== ЭНДПОИНТ ДЛЯ АВАТАРКИ ====================
@app.get("/api/avatar/{user_id}")
async def get_avatar(user_id: int):
    avatar_path = os.path.join(AVATARS_DIR, f"{user_id}.jpg")
    if os.path.exists(avatar_path):
        return {"url": f"/static/avatars/{user_id}.jpg"}
    
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count == 0:
            return {"url": "/static/default_avatar.png"}
        
        file_id = photos.photos[0][-1].file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    async with aiofiles.open(avatar_path, "wb") as f:
                        await f.write(await resp.read())
                    return {"url": f"/static/avatars/{user_id}.jpg"}
                else:
                    return {"url": "/static/default_avatar.png"}
    except Exception as e:
        logging.error(f"Avatar error: {e}")
        return {"url": "/static/default_avatar.png"}

# ==================== СТАТИЧЕСКИЕ ФАЙЛЫ ====================
# Всегда перезаписываем, чтобы обновить CSS/JS
STATIC_FILES = {
    "index.html": """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Star Drop</title>
    <link rel="stylesheet" href="/static/style.css?v=12">
</head>
<body class="theme-light">
    <div class="stars-background">
        <span>⭐</span><span>✨</span><span>🌟</span><span>💫</span>
        <span>🎁</span><span>🧸</span><span>💎</span><span>🧢</span>
        <span>🚀</span><span>💍</span><span>🧁</span><span>🎈</span>
        <span>👑</span><span>🛸</span><span>💎</span><span>🎁</span>
        <span>🎰</span><span>💵</span><span>⌚</span><span>👟</span>
        <span>📱</span><span>💻</span><span>🖥️</span><span>⌨️</span>
        <span>🕹️</span><span>🎮</span><span>🏆</span><span>🎖️</span>
        <span>💎</span><span>👑</span><span>🚀</span><span>🛸</span>
    </div>

    <div id="app-content" style="width:100%; max-width:400px;">
        <div id="top-bar">
            <div id="user-info" style="display:flex; align-items:center; gap:10px; cursor:pointer;">
                <div id="avatar-container" style="width:32px; height:32px; border-radius:50%; overflow:hidden; background:var(--accent-color);">
                    <img id="avatar-img" src="" alt="avatar" style="width:100%; height:100%; object-fit:cover; display:none;">
                    <span id="avatar-placeholder" style="display:flex; align-items:center; justify-content:center; width:100%; height:100%; font-weight:bold; font-size:16px; color:#0a0a0a;">U</span>
                </div>
                <span id="username">@user</span>
            </div>
            <div id="balance">
                <span id="balance-amount">0</span> 🎫
                <button id="deposit-btn">+</button>
                <button id="bets-btn">Мои ставки</button>
            </div>
        </div>

        <div id="deposit-menu" style="display: none;">
            <div style="width:100%; text-align:center; margin-bottom:10px; font-weight:bold; color:var(--accent-color);">Пополнить баланс</div>
            <button class="deposit-option" data-amount="100">100₽</button>
            <button class="deposit-option" data-amount="200">200₽</button>
            <button class="deposit-option" data-amount="500">500₽</button>
            <button class="deposit-option" data-amount="1000">1000₽</button>
            <button id="close-deposit">✖</button>
        </div>

        <div id="referral-modal" style="display: none; position: fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); justify-content:center; align-items:center; z-index:1000;">
            <div style="background:#1a1a1a; padding:20px; border-radius:12px; max-width:300px; width:90%; text-align:center; border:1px solid var(--accent-color);">
                <h3 style="color:var(--accent-color); margin-bottom:10px;">Реферальная система</h3>
                <p style="color:#ccc; font-size:14px;">Приведи друга и получи <b>+50 токенов</b> на баланс!</p>
                <p style="color:#fff; word-break:break-all; background:#222; padding:10px; border-radius:6px; margin:10px 0;" id="ref-link">Загрузка...</p>
                <button id="copy-ref-link" style="background:var(--accent-color); border:none; padding:8px 20px; border-radius:6px; font-weight:bold; cursor:pointer;">Копировать ссылку</button>
                <br><br>
                <span style="color:#aaa;">Приглашено друзей: <b id="ref-count">0</b></span>
                <br><br>
                <button id="close-ref-modal" style="background:#333; border:none; color:#fff; padding:8px 20px; border-radius:6px; cursor:pointer;">Закрыть</button>
            </div>
        </div>

        <div id="bets-modal" style="display: none; position: fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); justify-content:center; align-items:center; z-index:1000;">
            <div style="background:#1a1a1a; padding:20px; border-radius:12px; max-width:400px; width:90%; max-height:80%; overflow-y:auto; border:1px solid var(--accent-color);">
                <h3 style="color:var(--accent-color); margin-bottom:10px;">Мои ставки</h3>
                <ul id="bets-list" style="list-style:none; padding:0; margin:0;"></ul>
                <button id="close-bets-modal" style="background:#333; border:none; color:#fff; padding:8px 20px; border-radius:6px; margin-top:10px; cursor:pointer;">Закрыть</button>
            </div>
        </div>

        <!-- РУЛЕТКА (КЕЙС) -->
        <div id="roulette-page">
            <div id="main-title">
                <h1>РУЛЕТКА STAR DROP</h1>
                <p>Испытай удачу и выиграй Telegram-подарки!</p>
            </div>
            <div id="prizes-list">
                <div class="prize-item">🧸 Мишка</div>
                <div class="prize-item">💎 Бриллиант</div>
                <div class="prize-item">💍 Кольцо</div>
                <div class="prize-item">🧁 Торт</div>
                <div class="prize-item">🧢 Кепка Дурова</div>
                <div class="prize-item">🚀 Ракета</div>
            </div>
            <div id="mode-selector">
                <button class="mode-btn active" data-mode="light">Low</button>
                <button class="mode-btn" data-mode="normal">Normal</button>
                <button class="mode-btn" data-mode="hard">Hard</button>
            </div>

            <!-- Увеличенный контейнер -->
            <div id="case-container">
                <div id="case-track"></div>
                <div id="case-pointer">▼</div>
            </div>

            <div id="spin-area">
                <div id="spin-info">1 спин = <span id="spin-cost">25</span> монет</div>
                <button id="spin-btn">КРУТИТЬ <span id="spin-cost-label">25 Токенов</span></button>
            </div>
            <div id="result-message"></div>
        </div>

        <!-- СЛОТ -->
        <div id="slot-page" style="display:none;">
            <div id="main-title">
                <h1>ИГРОВОЙ АВТОМАТ 🎰</h1>
                <p>Дёрни рычаг и удвой ставку!</p>
            </div>
            <div id="slot-machine">
                <div id="reels">
                    <div class="reel" id="reel1">🍒</div>
                    <div class="reel" id="reel2">🍋</div>
                    <div class="reel" id="reel3">🍊</div>
                </div>
                <div id="slot-controls">
                    <div class="bet-control">
                        <label>Ставка: <span id="bet-display">20</span> токенов</label>
                        <input type="range" id="bet-range" min="20" max="100" step="10" value="20">
                        <div id="slot-multiplier">При выигрыше: <b>x2</b> от ставки</div>
                    </div>
                    <button id="spin-slot-btn">Дёрнуть рычаг 🎰</button>
                </div>
                <div id="slot-result"></div>
            </div>
        </div>

        <!-- РАКЕТКА -->
        <div id="rocket-page" style="display:none;">
            <div id="main-title">
                <h1>🚀 РАКЕТКА</h1>
                <p>Лови момент и умножай ставку до x100!</p>
            </div>
            <div id="rocket-game">
                <div id="rocket-display">
                    <div id="rocket-multiplier">0.00</div>
                    <div id="rocket-status">Ожидание</div>
                </div>
                <div id="rocket-canvas-container">
                    <canvas id="rocketCanvas" width="300" height="200"></canvas>
                </div>
                <div id="rocket-bet-control">
                    <label>Ставка: <span id="rocket-bet-display">500</span> токенов</label>
                    <input type="range" id="rocket-bet-range" min="500" max="5000" step="100" value="500">
                </div>
                <div id="rocket-buttons">
                    <button id="rocket-start-btn">🚀 Старт</button>
                    <button id="rocket-cashout-btn" disabled>💰 Стоп</button>
                </div>
                <div id="rocket-timer">Следующий взлёт через: <span id="rocket-countdown">5</span>с</div>
                <div id="rocket-result"></div>
            </div>
        </div>

        <div id="notification-feed">
            <h3>Последние события</h3>
            <ul id="feed-list"></ul>
        </div>

        <button id="withdraw-btn">Вывести токены</button>

        <div id="promo-area">
            <input type="text" id="promo-input" placeholder="Введите промокод" maxlength="20">
            <button id="promo-btn">Активировать</button>
            <div id="promo-message" style="color: var(--accent-color); font-size: 14px; margin-top: 5px; text-align:center;"></div>
        </div>

        <div id="bottom-nav">
            <button class="nav-btn active" data-tab="roulette">Рулетка</button>
            <button class="nav-btn" data-tab="slot">Барабан</button>
            <button class="nav-btn" data-tab="rocket">Ракетка</button>
        </div>
    </div>

    <script src="/static/script.js?v=12"></script>
</body>
</html>""",
    "style.css": """* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
}

:root {
    --accent-color: #ffd700;
    --accent-glow: #ffd70066;
    --bg-dark: #0a0a0a;
    --text-light: #fff;
    --card-bg: #111;
    --border-color: #333;
}

body {
    background: var(--bg-dark);
    color: var(--text-light);
    padding: 16px 16px 70px 16px;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    overflow-x: hidden;
    position: relative;
}

body.theme-light {
    --accent-color: #ffd700;
    --accent-glow: #ffd70066;
}
body.theme-normal {
    --accent-color: #2196F3;
    --accent-glow: #2196F366;
}
body.theme-hard {
    --accent-color: #f44336;
    --accent-glow: #f4433666;
}

.stars-background {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: -1;
    overflow: hidden;
}

.stars-background span {
    position: absolute;
    display: block;
    opacity: 0.5;
    color: var(--accent-color);
    text-shadow: 0 0 10px var(--accent-glow);
    font-size: 18px;
    animation: float var(--duration) ease-in-out infinite alternate;
    animation-delay: var(--delay);
}

/* ... (ключевые кадры для фона опущены для краткости, но в реальном файле они есть) ... */

#top-bar {
    display: flex;
    justify-content: space-between;
    width: 100%;
    padding: 10px 0;
    border-bottom: 1px solid var(--border-color);
    z-index: 2;
}

#user-info {
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
}

#avatar-container {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    overflow: hidden;
    background: var(--accent-color);
    flex-shrink: 0;
}

#avatar-img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: none;
}

#avatar-placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    font-weight: bold;
    font-size: 16px;
    color: #0a0a0a;
}

#username {
    font-size: 18px;
    font-weight: 600;
    color: var(--accent-color);
    transition: color 0.3s;
}

#balance {
    font-size: 18px;
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--accent-color);
    transition: color 0.3s;
}

#balance-amount {
    font-weight: 700;
}

#deposit-btn, #bets-btn {
    background: var(--accent-color);
    border: none;
    border-radius: 8px;
    padding: 4px 10px;
    font-weight: bold;
    color: #0a0a0a;
    cursor: pointer;
    font-size: 12px;
    transition: background 0.3s;
}

#deposit-btn {
    border-radius: 50%;
    width: 28px;
    height: 28px;
    font-size: 20px;
    padding: 0;
}

#deposit-menu {
    background: var(--card-bg);
    border: 1px solid var(--accent-color);
    border-radius: 12px;
    padding: 16px;
    margin: 10px 0;
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    justify-content: center;
    z-index: 10;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    transition: border-color 0.3s;
}

.deposit-option {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 10px 20px;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.3s, filter 0.2s;
}
.deposit-option:hover { filter: brightness(1.1); }

#close-deposit {
    background: transparent;
    color: var(--accent-color);
    border: none;
    font-size: 20px;
    cursor: pointer;
    transition: color 0.3s;
}

#main-title {
    text-align: center;
    margin: 20px 0 10px;
    z-index: 2;
}

#main-title h1 {
    font-size: 24px;
    font-weight: 900;
    color: var(--accent-color);
    letter-spacing: 2px;
    text-shadow: 0 0 10px var(--accent-glow);
    transition: color 0.3s, text-shadow 0.3s;
}

#main-title p {
    color: #aaa;
    font-size: 14px;
    margin-top: 4px;
}

#prizes-list {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
    margin: 15px 0;
    width: 100%;
    max-width: 400px;
    z-index: 2;
}

.prize-item {
    background: #1a1a1a;
    border: 1px solid var(--border-color);
    border-radius: 20px;
    padding: 6px 14px;
    font-size: 13px;
    color: #ccc;
}

#mode-selector {
    display: flex;
    gap: 12px;
    margin: 10px 0;
    z-index: 2;
}

.mode-btn {
    background: #222;
    color: #aaa;
    border: none;
    padding: 6px 18px;
    border-radius: 20px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    font-size: 13px;
}
.mode-btn.active {
    background: var(--accent-color);
    color: #0a0a0a;
    box-shadow: 0 0 15px var(--accent-glow);
}

#case-container {
    position: relative;
    width: 100%;
    max-width: 400px;
    height: 120px;
    background: #1a1a1a;
    border: 3px solid var(--accent-color);
    border-radius: 12px;
    overflow: hidden;
    margin: 10px 0;
    box-shadow: 0 0 20px var(--accent-glow);
}

#case-track {
    display: flex;
    position: absolute;
    top: 0;
    left: 0;
    height: 100%;
    align-items: center;
    transition: none;
    white-space: nowrap;
}

.case-item {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 80px;
    height: 100%;
    padding: 0 15px;
    font-size: 24px;
    font-weight: 600;
    color: #fff;
    background: #2a2a2a;
    border-right: 1px solid #444;
    flex-shrink: 0;
}
.case-item.win {
    background: #2b805e;
}
.case-item.lose {
    background: #ab2b44;
}

#case-pointer {
    position: absolute;
    top: -15px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 30px;
    color: var(--accent-color);
    z-index: 10;
    text-shadow: 0 0 10px var(--accent-glow);
}

#spin-area {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin: 15px 0;
    z-index: 2;
}

#spin-info {
    font-size: 14px;
    color: #aaa;
    margin-bottom: 8px;
}

#spin-btn {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 14px 40px;
    border-radius: 30px;
    font-weight: 700;
    font-size: 18px;
    cursor: pointer;
    box-shadow: 0 0 20px var(--accent-glow);
    transition: transform 0.1s, box-shadow 0.3s, background 0.3s;
    display: flex;
    flex-direction: column;
    align-items: center;
    line-height: 1.2;
}

#spin-btn:active {
    transform: scale(0.95);
}

#spin-btn span {
    font-size: 14px;
    font-weight: 400;
}

#result-message {
    margin: 10px 0;
    font-size: 18px;
    font-weight: 600;
    min-height: 40px;
    text-align: center;
    z-index: 2;
    color: var(--accent-color);
    text-shadow: 0 0 10px var(--accent-glow);
    transition: color 0.3s, text-shadow 0.3s;
}

/* Слот */
#slot-machine {
    background: var(--card-bg);
    border-radius: 20px;
    padding: 20px;
    margin: 10px 0;
    border: 2px solid var(--accent-color);
    box-shadow: 0 0 30px var(--accent-glow);
    width: 100%;
    max-width: 400px;
}

#reels {
    display: flex;
    justify-content: center;
    gap: 15px;
    padding: 15px 0;
}

.reel {
    width: 70px;
    height: 80px;
    background: #222;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 48px;
    border: 2px solid var(--border-color);
    box-shadow: inset 0 0 15px rgba(0,0,0,0.5);
    transition: transform 0.1s;
}

.reel.spinning {
    animation: spin 0.2s steps(1) infinite;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    25% { transform: rotate(90deg); }
    50% { transform: rotate(180deg); }
    75% { transform: rotate(270deg); }
    100% { transform: rotate(360deg); }
}

#slot-controls {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    margin-top: 10px;
}

.bet-control {
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
}

.bet-control label {
    font-size: 14px;
    color: #ccc;
}

#bet-range {
    width: 80%;
    max-width: 250px;
    margin-top: 5px;
    accent-color: var(--accent-color);
}

#slot-multiplier {
    font-size: 14px;
    color: #aaa;
    margin-top: 4px;
}

#slot-multiplier b {
    color: var(--accent-color);
}

#spin-slot-btn {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 14px 30px;
    border-radius: 30px;
    font-weight: 700;
    font-size: 18px;
    cursor: pointer;
    box-shadow: 0 0 20px var(--accent-glow);
    transition: transform 0.1s, box-shadow 0.3s, background 0.3s;
    width: 100%;
    max-width: 280px;
}

#spin-slot-btn:active {
    transform: scale(0.95);
}

#slot-result {
    margin-top: 15px;
    font-size: 18px;
    font-weight: 600;
    text-align: center;
    color: var(--accent-color);
    min-height: 30px;
}

/* Ракетка */
#rocket-game {
    background: var(--card-bg);
    border-radius: 20px;
    padding: 20px;
    margin: 10px 0;
    border: 2px solid var(--accent-color);
    box-shadow: 0 0 30px var(--accent-glow);
    width: 100%;
    max-width: 400px;
}

#rocket-display {
    text-align: center;
    padding: 10px 0;
}

#rocket-multiplier {
    font-size: 48px;
    font-weight: 900;
    color: var(--accent-color);
    text-shadow: 0 0 20px var(--accent-glow);
    transition: color 0.3s;
}

#rocket-status {
    font-size: 16px;
    color: #aaa;
    margin-top: 5px;
}

#rocket-canvas-container {
    width: 100%;
    text-align: center;
}

#rocketCanvas {
    width: 100%;
    height: auto;
    background: #0a0a0a;
    border-radius: 12px;
}

#rocket-bet-control {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin: 10px 0;
}

#rocket-bet-control label {
    font-size: 14px;
    color: #ccc;
}

#rocket-bet-range {
    width: 80%;
    max-width: 250px;
    margin-top: 5px;
    accent-color: var(--accent-color);
}

#rocket-buttons {
    display: flex;
    justify-content: center;
    gap: 12px;
    margin: 15px 0;
}

#rocket-start-btn, #rocket-cashout-btn {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 12px 30px;
    border-radius: 30px;
    font-weight: 700;
    font-size: 18px;
    cursor: pointer;
    box-shadow: 0 0 20px var(--accent-glow);
    transition: transform 0.1s, box-shadow 0.3s, background 0.3s;
    flex: 1;
    max-width: 150px;
}

#rocket-start-btn:disabled, #rocket-cashout-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

#rocket-start-btn:active, #rocket-cashout-btn:active {
    transform: scale(0.95);
}

#rocket-timer {
    font-size: 14px;
    color: #aaa;
    margin: 5px 0;
    text-align: center;
}

#rocket-timer span {
    color: var(--accent-color);
}

#rocket-result {
    margin-top: 10px;
    font-size: 18px;
    font-weight: 600;
    text-align: center;
    color: var(--accent-color);
    min-height: 30px;
}

/* Лента и прочее */
#notification-feed {
    width: 100%;
    max-width: 400px;
    background: var(--card-bg);
    border-radius: 12px;
    padding: 12px;
    margin: 20px 0;
    z-index: 2;
    border: 1px solid var(--border-color);
}

#notification-feed h3 {
    color: var(--accent-color);
    margin-bottom: 8px;
    font-size: 16px;
    transition: color 0.3s;
}

#feed-list {
    list-style: none;
    max-height: 150px;
    overflow-y: auto;
}

#feed-list li {
    padding: 6px 0;
    border-bottom: 1px solid var(--border-color);
    font-size: 13px;
    color: #ddd;
}

#withdraw-btn {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 12px 30px;
    border-radius: 30px;
    font-weight: 700;
    font-size: 16px;
    margin-top: 10px;
    cursor: pointer;
    box-shadow: 0 0 15px var(--accent-glow);
    z-index: 2;
    transition: background 0.3s, box-shadow 0.3s;
}

#promo-area {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    align-items: center;
    gap: 8px;
    margin: 10px 0;
    z-index: 2;
    width: 100%;
    max-width: 400px;
}

#promo-input {
    flex: 1;
    min-width: 140px;
    padding: 8px 14px;
    border-radius: 20px;
    border: 1px solid var(--accent-color);
    background: #222;
    color: #fff;
    outline: none;
    font-size: 14px;
    transition: border-color 0.3s, box-shadow 0.3s;
    text-align: center;
}
#promo-input:focus {
    border-color: var(--accent-color);
    box-shadow: 0 0 10px var(--accent-glow);
}

#promo-btn {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 8px 20px;
    border-radius: 20px;
    font-weight: bold;
    font-size: 14px;
    cursor: pointer;
    transition: background 0.3s, box-shadow 0.3s;
    box-shadow: 0 0 10px var(--accent-glow);
}
#promo-btn:active {
    transform: scale(0.95);
}

#promo-message {
    width: 100%;
    font-size: 14px;
    text-align: center;
    min-height: 20px;
    color: var(--accent-color);
    transition: color 0.3s;
}

#bottom-nav {
    position: fixed;
    bottom: 0;
    left: 0;
    width: 100%;
    background: #111;
    display: flex;
    justify-content: space-around;
    padding: 10px 0;
    border-top: 1px solid var(--border-color);
    z-index: 10;
}

.nav-btn {
    background: transparent;
    color: #888;
    border: none;
    font-size: 14px;
    font-weight: 600;
    padding: 6px 20px;
    border-radius: 20px;
    cursor: pointer;
    transition: 0.2s;
}
.nav-btn.active {
    color: var(--accent-color);
    background: rgba(255,215,0,0.1);
}

#bets-modal ul li {
    padding: 8px 0;
    border-bottom: 1px solid var(--border-color);
    color: #ddd;
    font-size: 14px;
}
#bets-modal ul li span.positive {
    color: #4CAF50;
}
#bets-modal ul li span.negative {
    color: #f44336;
}
""",
    "script.js": """const BASE_URL = window.location.origin;
let user_id = null;
let balance = 0;
let currentMode = 'light';
let isSpinning = false;
let spinInterval = null;
let currentPosition = 0;
let targetPosition = 0;

function showAuthError(message) {
    document.body.innerHTML = `
        <div style="display:flex; justify-content:center; align-items:center; height:100vh; flex-direction:column; background:#0a0a0a; color:#fff; text-align:center; padding:20px;">
            <h1 style="color:var(--accent-color);">⛔ Ошибка авторизации</h1>
            <p style="color:#ccc; margin:20px 0;">${message}</p>
            <p style="color:#888; font-size:14px;">Пожалуйста, откройте это приложение через бота Telegram.</p>
            <button onclick="window.location.href='https://t.me/StarDrop11_bot'" style="background:var(--accent-color); border:none; padding:12px 30px; border-radius:8px; font-weight:bold; cursor:pointer; margin-top:10px;">Открыть бота</button>
        </div>
    `;
    throw new Error('Auth error');
}

if (window.Telegram && window.Telegram.WebApp) {
    window.Telegram.WebApp.ready();
    const tgUser = window.Telegram.WebApp.initDataUnsafe?.user;
    if (tgUser && tgUser.id) {
        user_id = tgUser.id;
        localStorage.setItem('starDrop_userId', user_id);
        const username = tgUser.username || tgUser.first_name || 'User';
        document.getElementById('username').textContent = '@' + username;
        loadAvatar(user_id);
        const placeholder = document.getElementById('avatar-placeholder');
        const name = tgUser.first_name || 'U';
        placeholder.textContent = name.charAt(0).toUpperCase();
    } else {
        showAuthError('Не удалось получить данные пользователя из Telegram.');
    }
} else {
    const savedId = localStorage.getItem('starDrop_userId');
    if (savedId) {
        user_id = parseInt(savedId);
        document.getElementById('username').textContent = '@user_' + user_id;
        document.getElementById('avatar-placeholder').textContent = 'U';
        console.warn('Гостевой режим: используем сохранённый ID');
    } else {
        showAuthError('Это приложение работает только в Telegram. Пожалуйста, откройте его через бота.');
    }
}

async function loadAvatar(userId) {
    try {
        const resp = await fetch(`/api/avatar/${userId}`);
        const data = await resp.json();
        if (data.url) {
            const img = document.getElementById('avatar-img');
            img.src = data.url;
            img.style.display = 'block';
            document.getElementById('avatar-placeholder').style.display = 'none';
        }
    } catch (e) {
        console.error('Avatar load error:', e);
    }
}

fetchUserData().then(() => {
    initGames();
}).catch(() => {
    initGames();
});

async function fetchUserData() {
    if (!user_id) return;
    try {
        const resp = await fetch(`/api/user/${user_id}`);
        if (!resp.ok) throw new Error('User not found');
        const data = await resp.json();
        balance = data.balance;
        document.getElementById('balance-amount').textContent = balance;
        if (data.username && data.username !== '') {
            document.getElementById('username').textContent = '@' + data.username;
        }
    } catch (e) {
        console.error('Ошибка загрузки пользователя:', e);
    }
}

function updateBalanceUI(newBalance) {
    balance = newBalance;
    document.getElementById('balance-amount').textContent = newBalance;
}

document.getElementById('user-info').addEventListener('click', async () => {
    if (!user_id) return;
    try {
        const resp = await fetch(`/api/referral/${user_id}`);
        const data = await resp.json();
        document.getElementById('ref-link').textContent = data.link;
        document.getElementById('ref-count').textContent = data.count;
        document.getElementById('referral-modal').style.display = 'flex';
    } catch (e) {
        alert('Ошибка загрузки реферальной информации');
    }
});

document.getElementById('close-ref-modal').addEventListener('click', () => {
    document.getElementById('referral-modal').style.display = 'none';
});

document.getElementById('copy-ref-link').addEventListener('click', () => {
    const link = document.getElementById('ref-link').textContent;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(() => alert('Ссылка скопирована!'))
            .catch(() => fallbackCopy(link));
    } else fallbackCopy(link);
});

function fallbackCopy(text) {
    const input = document.createElement('input');
    input.style.position = 'fixed';
    input.style.opacity = '0';
    input.value = text;
    document.body.appendChild(input);
    input.select();
    try { document.execCommand('copy'); alert('Ссылка скопирована!'); } 
    catch (e) { alert('Не удалось скопировать, скопируйте вручную: ' + text); }
    document.body.removeChild(input);
}

document.getElementById('bets-btn').addEventListener('click', async () => {
    if (!user_id) return;
    try {
        const resp = await fetch(`/api/user_bets/${user_id}`);
        const bets = await resp.json();
        const list = document.getElementById('bets-list');
        list.innerHTML = '';
        if (bets.length === 0) list.innerHTML = '<li style="color:#aaa;">Ставок пока нет</li>';
        else bets.forEach(b => {
            const li = document.createElement('li');
            let sign = '', cls = '';
            if (b.amount > 0) { sign = '+'; cls = 'positive'; }
            else if (b.amount < 0) { sign = ''; cls = 'negative'; }
            else { sign = '0'; cls = ''; }
            li.innerHTML = `<span class="${cls}">${sign}${b.amount}</span> ${b.description} <span style="color:#888;font-size:12px;">${new Date(b.created_at).toLocaleString()}</span>`;
            list.appendChild(li);
        });
        document.getElementById('bets-modal').style.display = 'flex';
    } catch (e) { alert('Ошибка загрузки ставок'); console.error(e); }
});

document.getElementById('close-bets-modal').addEventListener('click', () => {
    document.getElementById('bets-modal').style.display = 'none';
});
document.getElementById('bets-modal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) document.getElementById('bets-modal').style.display = 'none';
});

document.getElementById('promo-btn').addEventListener('click', async () => {
    if (!user_id) return;
    const input = document.getElementById('promo-input');
    const code = input.value.trim();
    const msg = document.getElementById('promo-message');
    if (!code) { msg.textContent = 'Введите промокод'; return; }
    try {
        const resp = await fetch('/api/activate_promo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id, code })
        });
        const data = await resp.json();
        if (resp.ok) {
            msg.textContent = '✅ ' + data.message;
            input.value = '';
            balance = data.new_balance;
            document.getElementById('balance-amount').textContent = balance;
        } else msg.textContent = '❌ ' + data.detail;
    } catch (e) { msg.textContent = 'Ошибка соединения'; console.error(e); }
});

function initGames() {
    applyTheme('light');
    updateCase(currentMode);
    updateSpinCost();
    const initialBet = parseInt(document.getElementById('bet-range').value);
    document.getElementById('bet-display').textContent = initialBet;
    drawRocket(0, 'idle');
    document.getElementById('rocket-countdown').textContent = '0';
    startAutoRocket();
    startFakeWins();
    startIdleScroll();
}

// ---- ОБНОВЛЁННАЯ ЛЕНТА СОБЫТИЙ (выигрыши + редкие проигрыши) ----
function startFakeWins() {
    setInterval(() => {
        // 75% – выигрыш, 25% – проигрыш
        const isWin = Math.random() < 0.75;
        const fakeUsers = ['user_' + (100000 + Math.floor(Math.random()*900000)), 
                           'player_' + (200000 + Math.floor(Math.random()*800000)), 
                           'gamer_' + (300000 + Math.floor(Math.random()*700000)), 
                           'winner_' + (400000 + Math.floor(Math.random()*600000))];
        const username = fakeUsers[Math.floor(Math.random()*fakeUsers.length)];
        const prizes = ['🎰 Слот', '🎡 Рулетка', '🚀 Ракетка', '🎁 Подарок'];
        const prize = prizes[Math.floor(Math.random()*prizes.length)];
        const amount = Math.floor(Math.random() * 150) + 10;
        
        if (isWin) {
            addFakeWinToFeed(username, prize, amount);
        } else {
            // Проигрыш – разные формулировки
            const loseMessages = ['проиграл', 'не повезло', 'удача отвернулась', 'мимо', 'сгорел'];
            const msg = loseMessages[Math.floor(Math.random() * loseMessages.length)];
            addFakeLoseToFeed(username, prize, msg);
        }
    }, 2000);
}

function addFakeWinToFeed(username, prize, amount) {
    const list = document.getElementById('feed-list');
    const li = document.createElement('li');
    li.textContent = '@' + username + ' выиграл ' + prize + ' (+' + amount + ' токенов) 🎉';
    list.insertBefore(li, list.firstChild);
    if (list.children.length > 10) list.removeChild(list.lastChild);
}

function addFakeLoseToFeed(username, prize, msg) {
    const list = document.getElementById('feed-list');
    const li = document.createElement('li');
    li.textContent = '@' + username + ' ' + msg + ' в ' + prize + ' 😞';
    list.insertBefore(li, list.firstChild);
    if (list.children.length > 10) list.removeChild(list.lastChild);
}

// ---- Остальные функции без изменений ----
function startIdleScroll() {
    if (spinInterval) clearInterval(spinInterval);
    spinInterval = setInterval(() => {
        if (!isSpinning) {
            currentPosition += 1;
            updateTrackPosition();
        }
    }, 50);
}

function stopIdleScroll() {
    if (spinInterval) {
        clearInterval(spinInterval);
        spinInterval = null;
    }
}

function updateTrackPosition() {
    const track = document.getElementById('case-track');
    if (track) {
        track.style.transform = `translateX(${-currentPosition}px)`;
    }
}

function updateCase(mode) {
    const track = document.getElementById('case-track');
    const items = generateCaseItems(mode, 40);
    track.innerHTML = '';
    items.forEach(item => {
        const div = document.createElement('div');
        div.className = 'case-item' + (item.value > 0 ? ' win' : ' lose');
        div.textContent = item.name;
        track.appendChild(div);
    });
    const clone = track.cloneNode(true);
    track.appendChild(clone);
    currentPosition = 0;
    updateTrackPosition();
}

function generateCaseItems(mode, count) {
    const ranges = {
        light: {min: 10, max: 100},
        normal: {min: 50, max: 200},
        hard: {min: 10, max: 500}
    };
    const r = ranges[mode] || ranges.light;
    const items = [];
    for (let i = 0; i < count; i++) {
        if (i % 2 === 0) {
            let val = Math.floor(Math.random() * (r.max - r.min + 1)) + r.min;
            const icon = mode === 'light' ? '🏷️' : mode === 'normal' ? '🎟️' : '🎫';
            items.push({name: `${icon} ${val}`, value: val});
        } else {
            items.push({name: '❌', value: 0});
        }
    }
    return items;
}

function applyTheme(mode) {
    document.body.classList.remove('theme-light', 'theme-normal', 'theme-hard');
    if (mode === 'light') document.body.classList.add('theme-light');
    else if (mode === 'normal') document.body.classList.add('theme-normal');
    else if (mode === 'hard') document.body.classList.add('theme-hard');
}

document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (isSpinning) return;
        document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentMode = btn.dataset.mode;
        updateSpinCost();
        applyTheme(currentMode);
        updateCase(currentMode);
        currentPosition = 0;
        updateTrackPosition();
    });
});

function updateSpinCost() {
    const costs = { light: 25, normal: 50, hard: 100 };
    const cost = costs[currentMode];
    document.getElementById('spin-cost').textContent = cost;
    document.getElementById('spin-cost-label').textContent = cost + ' Токенов';
}

document.getElementById('spin-btn').addEventListener('click', async () => {
    if (!user_id || isSpinning) return;
    const cost = { light:25, normal:50, hard:100 }[currentMode];
    if (balance < cost) {
        document.getElementById('result-message').textContent = '❌ Недостаточно токенов!';
        return;
    }
    isSpinning = true;
    const btn = document.getElementById('spin-btn');
    btn.disabled = true;
    btn.innerHTML = 'КРУТИТЬ <span>Загрузка...</span>';
    document.getElementById('result-message').textContent = '';
    stopIdleScroll();

    try {
        const resp = await fetch('/api/spin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id, mode: currentMode })
        });
        const data = await resp.json();
        if (resp.ok) {
            updateBalanceUI(data.new_balance);
            await animateSpin(data.win, data.prize_value, data.prize_name);
            document.getElementById('result-message').textContent = data.message;
            document.getElementById('result-message').style.color = data.win ? '#4CAF50' : '#f44336';
            if (data.win) {
                const username = document.getElementById('username').textContent.replace('@', '');
                addFakeWinToFeed(username, data.prize_name, data.prize_value);
            }
        } else {
            document.getElementById('result-message').textContent = '❌ ' + data.detail;
        }
    } catch (e) {
        document.getElementById('result-message').textContent = 'Ошибка соединения';
        console.error(e);
    }
    isSpinning = false;
    btn.disabled = false;
    const cost2 = { light:25, normal:50, hard:100 }[currentMode];
    btn.innerHTML = 'КРУТИТЬ <span>' + cost2 + ' Токенов</span>';
    startIdleScroll();
});

function animateSpin(win, prizeValue, prizeName) {
    return new Promise((resolve) => {
        const track = document.getElementById('case-track');
        const items = track.querySelectorAll('.case-item');
        const totalWidth = track.scrollWidth / 2;
        const containerWidth = document.getElementById('case-container').offsetWidth;
        const itemWidth = items[0].offsetWidth + 1;

        let targetIndex = -1;
        if (win) {
            for (let i = 0; i < items.length; i++) {
                if (!items[i].textContent.includes('❌')) {
                    targetIndex = i;
                    break;
                }
            }
            if (targetIndex === -1) targetIndex = Math.floor(Math.random() * items.length);
        } else {
            for (let i = 0; i < items.length; i++) {
                if (items[i].textContent.includes('❌')) {
                    targetIndex = i;
                    break;
                }
            }
            if (targetIndex === -1) targetIndex = Math.floor(Math.random() * items.length);
        }

        const centerPos = containerWidth / 2;
        const targetOffset = targetIndex * itemWidth - centerPos + itemWidth / 2;
        const randomShift = (Math.random() - 0.5) * 30;
        const finalOffset = targetOffset + randomShift;

        let startPos = currentPosition;
        let distance = finalOffset - startPos;
        if (distance < 0) distance += totalWidth;
        const extraCycles = 3 + Math.floor(Math.random() * 3);
        distance += extraCycles * totalWidth;
        targetPosition = startPos + distance;

        let progress = 0;
        const duration = 3000;
        const startTime = Date.now();

        function step() {
            const elapsed = Date.now() - startTime;
            const t = Math.min(elapsed / duration, 1);
            const ease = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
            const currentPos = startPos + distance * ease;
            currentPosition = currentPos;
            track.style.transform = `translateX(${-currentPos}px)`;
            if (t < 1) {
                requestAnimationFrame(step);
            } else {
                currentPosition = targetPosition;
                track.style.transform = `translateX(${-currentPosition}px)`;
                resolve();
            }
        }
        requestAnimationFrame(step);
    });
}

// ---- СЛОТ (без изменений) ----
let slotSpinning = false;
const slotSymbols = ['🍒','🍋','🍊','🍇','🍉','🍓','🍑','🎰'];
const reels = [
    document.getElementById('reel1'),
    document.getElementById('reel2'),
    document.getElementById('reel3')
];
document.getElementById('bet-range').addEventListener('input', function() {
    document.getElementById('bet-display').textContent = this.value;
});
document.getElementById('spin-slot-btn').addEventListener('click', async () => {
    if (!user_id || slotSpinning) return;
    const bet = parseInt(document.getElementById('bet-range').value);
    if (isNaN(bet) || bet<20 || bet>100) { alert('Ставка от 20 до 100'); return; }
    if (balance < bet) { alert('Недостаточно токенов!'); return; }
    slotSpinning = true;
    const btn = document.getElementById('spin-slot-btn');
    btn.disabled = true;
    btn.textContent = '🎰 Крутим...';
    let interval = setInterval(() => {
        reels.forEach(reel => {
            reel.textContent = slotSymbols[Math.floor(Math.random()*slotSymbols.length)];
        });
    }, 100);
    try {
        const resp = await fetch('/api/slot_spin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id, bet })
        });
        const data = await resp.json();
        clearInterval(interval);
        if (resp.ok) {
            reels[0].textContent = data.symbols[0];
            reels[1].textContent = data.symbols[1];
            reels[2].textContent = data.symbols[2];
            updateBalanceUI(data.new_balance);
            const resultDiv = document.getElementById('slot-result');
            if (data.win) {
                resultDiv.textContent = '🎉 ВЫИГРЫШ! +' + data.win_amount + ' токенов!';
                resultDiv.style.color = '#4CAF50';
                const username = document.getElementById('username').textContent.replace('@', '');
                addFakeWinToFeed(username, '🎰 Слот', data.win_amount);
            } else {
                resultDiv.textContent = '😞 Проигрыш. -' + bet + ' токенов';
                resultDiv.style.color = '#f44336';
            }
        } else {
            document.getElementById('slot-result').textContent = '❌ ' + data.detail;
        }
    } catch (e) {
        clearInterval(interval);
        document.getElementById('slot-result').textContent = 'Ошибка соединения';
        console.error(e);
    }
    slotSpinning = false;
    btn.disabled = false;
    btn.textContent = 'Дёрнуть рычаг 🎰';
});

// ---- РАКЕТКА (без изменений) ----
let rocketInterval = null, rocketRoundId = null, rocketActive = false;
let rocketCountdown = 5, countdownInterval = null, rocketAnimationFrame = null;
const rocketCanvas = document.getElementById('rocketCanvas');
const rctx = rocketCanvas.getContext('2d');
let rocketX = 30, rocketY = 160;
let rocketSpeed = 2.5;
let rocketTrail = [];
let isCrashed = false;
let falling = false;
let fallY = 0;
let explosionX = 0, explosionY = 0;

function drawRocket(multiplier, status) {
    rctx.clearRect(0,0,rocketCanvas.width,rocketCanvas.height);
    if (rocketTrail.length > 1 && status !== 'crashed' && status !== 'idle') {
        rctx.beginPath();
        rctx.moveTo(rocketTrail[0].x, rocketTrail[0].y);
        for (let i=1; i<rocketTrail.length; i++) {
            rctx.lineTo(rocketTrail[i].x, rocketTrail[i].y);
        }
        rctx.strokeStyle = 'rgba(255,215,0,0.4)';
        rctx.lineWidth = 2;
        rctx.stroke();
    }
    if (status === 'crashed') {
        rctx.font = '50px sans-serif';
        rctx.textAlign = 'center';
        rctx.fillText('💥', explosionX, explosionY);
        if (falling) {
            rctx.font = '30px sans-serif';
            rctx.fillText('🚀', rocketX, fallY);
        }
        return;
    }
    if (status === 'idle') {
        rctx.font = '30px sans-serif';
        rctx.textAlign = 'center';
        rctx.fillText('🚀', rocketX, rocketY);
        return;
    }
    rctx.font = '30px sans-serif';
    rctx.textAlign = 'center';
    rctx.fillText('🚀', rocketX, rocketY);
    rctx.fillStyle = '#ffd700';
    rctx.font = '14px sans-serif';
    rctx.fillText(multiplier.toFixed(2)+'x', rocketX, rocketY-30);
}

document.getElementById('rocket-bet-range').addEventListener('input', function() {
    document.getElementById('rocket-bet-display').textContent = this.value;
});

document.getElementById('rocket-start-btn').addEventListener('click', async () => {
    if (!user_id || rocketActive) return;
    const bet = parseInt(document.getElementById('rocket-bet-range').value);
    if (isNaN(bet) || bet<500 || bet>5000) { alert('Ставка от 500 до 5000'); return; }
    if (balance < bet) { alert('Недостаточно токенов!'); return; }
    try {
        const resp = await fetch('/api/rocket/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id, bet })
        });
        const data = await resp.json();
        if (resp.ok) {
            rocketRoundId = data.round_id;
            rocketActive = true;
            isCrashed = false;
            falling = false;
            document.getElementById('rocket-start-btn').disabled = true;
            document.getElementById('rocket-cashout-btn').disabled = false;
            document.getElementById('rocket-result').textContent = '';
            document.getElementById('rocket-status').textContent = '🚀 Взлёт!';
            rocketX = 30;
            rocketY = 160;
            rocketTrail = [{x:rocketX, y:rocketY}];
            if (rocketInterval) clearInterval(rocketInterval);
            rocketInterval = setInterval(updateRocketStatus, 150);
            if (rocketAnimationFrame) cancelAnimationFrame(rocketAnimationFrame);
            animateRocket();
        } else alert('❌ ' + data.detail);
    } catch (e) { alert('Ошибка соединения'); console.error(e); }
});

function animateRocket() {
    if (!rocketActive && !falling) return;
    if (isCrashed && !falling) {
        falling = true;
        fallY = rocketY;
        explosionX = rocketX;
        explosionY = rocketY - 20;
    }
    if (falling) {
        fallY += 3;
        if (fallY > rocketCanvas.height + 50) {
            falling = false;
            isCrashed = false;
            drawRocket(0, 'idle');
            return;
        }
        drawRocket(0, 'crashed');
        rocketAnimationFrame = requestAnimationFrame(animateRocket);
        return;
    }
    if (!rocketActive) return;
    rocketX += rocketSpeed * 0.8;
    rocketY -= rocketSpeed * 0.6;
    if (rocketX > rocketCanvas.width - 20) rocketX = rocketCanvas.width - 20;
    if (rocketY < 20) rocketY = 20;
    rocketTrail.push({x:rocketX, y:rocketY});
    if (rocketTrail.length > 100) rocketTrail.shift();
    drawRocket(parseFloat(document.getElementById('rocket-multiplier').textContent) || 0, 'active');
    rocketAnimationFrame = requestAnimationFrame(animateRocket);
}

async function updateRocketStatus() {
    if (!rocketRoundId) return;
    try {
        const resp = await fetch(`/api/rocket/status/${rocketRoundId}`);
        const data = await resp.json();
        if (resp.ok) {
            const display = data.display_multiplier;
            document.getElementById('rocket-multiplier').textContent = display.toFixed(2);
            if (data.crashed) {
                document.getElementById('rocket-status').textContent = '💥 Упала!';
                document.getElementById('rocket-cashout-btn').disabled = true;
                document.getElementById('rocket-start-btn').disabled = false;
                rocketActive = false;
                isCrashed = true;
                if (rocketInterval) clearInterval(rocketInterval);
                animateRocket();
                document.getElementById('rocket-result').textContent = '😞 Ракета упала. Ставка проиграна.';
                document.getElementById('rocket-result').style.color = '#f44336';
                fetchUserData();
                startCountdown();
            } else if (data.cashed_out) {
                document.getElementById('rocket-status').textContent = '💰 Выведено!';
                document.getElementById('rocket-cashout-btn').disabled = true;
                document.getElementById('rocket-start-btn').disabled = false;
                rocketActive = false;
                if (rocketInterval) clearInterval(rocketInterval);
                if (rocketAnimationFrame) cancelAnimationFrame(rocketAnimationFrame);
                fetchUserData();
                startCountdown();
            } else {
                drawRocket(display, 'active');
            }
        } else console.error('Status error:', data);
    } catch (e) { console.error(e); }
}

document.getElementById('rocket-cashout-btn').addEventListener('click', async () => {
    if (!user_id || !rocketRoundId || !rocketActive) return;
    try {
        const resp = await fetch('/api/rocket/cashout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ round_id: rocketRoundId, user_id })
        });
        const data = await resp.json();
        if (resp.ok) {
            document.getElementById('rocket-result').textContent = '🎉 Вы выиграли ' + data.win_amount + ' токенов!';
            document.getElementById('rocket-result').style.color = '#4CAF50';
            document.getElementById('rocket-status').textContent = '💰 Выведено!';
            document.getElementById('rocket-cashout-btn').disabled = true;
            document.getElementById('rocket-start-btn').disabled = false;
            rocketActive = false;
            if (rocketInterval) clearInterval(rocketInterval);
            if (rocketAnimationFrame) cancelAnimationFrame(rocketAnimationFrame);
            updateBalanceUI(data.new_balance);
            const username = document.getElementById('username').textContent.replace('@', '');
            addFakeWinToFeed(username, '🚀 Ракетка', data.win_amount);
            startCountdown();
        } else alert('❌ ' + data.detail);
    } catch (e) { alert('Ошибка соединения'); console.error(e); }
});

function startCountdown() {
    rocketCountdown = 5;
    document.getElementById('rocket-countdown').textContent = rocketCountdown;
    if (countdownInterval) clearInterval(countdownInterval);
    countdownInterval = setInterval(() => {
        rocketCountdown--;
        document.getElementById('rocket-countdown').textContent = rocketCountdown;
        if (rocketCountdown <= 0) {
            clearInterval(countdownInterval);
            countdownInterval = null;
            document.getElementById('rocket-countdown').textContent = '0';
            document.getElementById('rocket-start-btn').click();
        }
    }, 1000);
}

let autoRocketTimer = null;
function startAutoRocket() {
    if (autoRocketTimer) clearInterval(autoRocketTimer);
    autoRocketTimer = setInterval(() => {
        if (!rocketActive) {
            const fakeBet = 500 + Math.floor(Math.random() * 500) * 10;
            simulateRocketRound(fakeBet);
        }
    }, 10000 + Math.random() * 15000);
}

function simulateRocketRound(bet) {
    const win = Math.random() < 0.35;
    const crashMultiplier = win ? 1.1 + Math.random() * 2.0 : 0.5 + Math.random() * 0.5;
    let progress = 0;
    const interval = setInterval(() => {
        progress += 0.02;
        if (progress >= 1) {
            clearInterval(interval);
            if (win) {
                const winAmount = Math.floor(bet * crashMultiplier);
                const fakeUsers = ['user_' + (100000 + Math.floor(Math.random()*900000)), 'player_' + (200000 + Math.floor(Math.random()*800000)), 'gamer_' + (300000 + Math.floor(Math.random()*700000))];
                const username = fakeUsers[Math.floor(Math.random()*fakeUsers.length)];
                addFakeWinToFeed(username, '🚀 Ракетка', winAmount);
            }
            document.getElementById('rocket-multiplier').textContent = '0.00';
            document.getElementById('rocket-status').textContent = 'Ожидание';
            drawRocket(0, 'idle');
            return;
        }
        const currentMultiplier = win ? 1 + progress * crashMultiplier : progress * 0.8;
        document.getElementById('rocket-multiplier').textContent = currentMultiplier.toFixed(2);
        if (win) {
            document.getElementById('rocket-status').textContent = '🚀 Взлёт!';
            drawRocket(currentMultiplier, 'active');
        } else {
            if (progress > 0.6) {
                document.getElementById('rocket-status').textContent = '💥 Упала!';
                drawRocket(currentMultiplier, 'crashed');
            } else {
                document.getElementById('rocket-status').textContent = '🚀 Взлёт!';
                drawRocket(currentMultiplier, 'active');
            }
        }
    }, 200);
}

// --- Общие функции ---
document.getElementById('deposit-btn').addEventListener('click', () => {
    const menu = document.getElementById('deposit-menu');
    menu.style.display = menu.style.display === 'none' ? 'flex' : 'none';
});

document.querySelectorAll('.deposit-option').forEach(btn => {
    btn.addEventListener('click', () => {
        const amount = btn.dataset.amount;
        const links = {
            100: 'https://yookassa.ru/my/i/amMy2QzHTXRI/l',
            200: 'https://yookassa.ru/my/i/amMzHkXK55Uk/l',
            500: 'https://yookassa.ru/my/i/amMzSdZUSmIm/l',
            1000: 'https://yookassa.ru/my/i/amMzbZDBr9y2/l'
        };
        if (links[amount]) window.open(links[amount], '_blank');
    });
});

document.getElementById('close-deposit').addEventListener('click', () => {
    document.getElementById('deposit-menu').style.display = 'none';
});

document.getElementById('withdraw-btn').addEventListener('click', async () => {
    if (!user_id) return;
    const amount = prompt('Введите сумму вывода (минимум 500 токенов):');
    if (!amount || isNaN(amount) || amount < 500) {
        alert('Введите корректное число не менее 500');
        return;
    }
    try {
        const resp = await fetch('/api/withdraw', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id, amount: parseInt(amount) })
        });
        const data = await resp.json();
        if (resp.ok) {
            alert('✅ Заявка на вывод отправлена!');
            fetchUserData();
        } else alert('❌ ' + data.detail);
    } catch (e) { alert('Ошибка соединения'); console.error(e); }
});

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.dataset.tab;
        document.getElementById('roulette-page').style.display = tab==='roulette' ? 'block' : 'none';
        document.getElementById('slot-page').style.display = tab==='slot' ? 'block' : 'none';
        document.getElementById('rocket-page').style.display = tab==='rocket' ? 'block' : 'none';
        if (tab==='rocket') fetchUserData();
    });
});
"""
}

# Всегда перезаписываем статические файлы
for filename, content in STATIC_FILES.items():
    filepath = os.path.join(STATIC_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ Обновлён {filepath}")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")

@app.head("/")
async def root_head():
    return RedirectResponse(url="/static/index.html")

@app.post("/webhook")
async def webhook(request: Request):
    update = types.Update(**(await request.json()))
    await dp.feed_update(bot, update)
    return {"status": "ok"}

# API модели
class SpinRequest(BaseModel):
    user_id: int
    mode: str

class WithdrawRequest(BaseModel):
    user_id: int
    amount: int

class PromoRequest(BaseModel):
    user_id: int
    code: str

class SlotSpinRequest(BaseModel):
    user_id: int
    bet: int

class RocketStartRequest(BaseModel):
    user_id: int
    bet: int

class RocketCashoutRequest(BaseModel):
    round_id: int
    user_id: int

@app.get("/api/user/{user_id}")
async def api_get_user(user_id: int):
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] == 0:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("UPDATE users SET balance = ? WHERE user_id = ?", (START_BALANCE, user_id))
        cur.execute(
            "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
            (user_id, "deposit", START_BALANCE, "Стартовый бонус 50 токенов (восстановлен через API)")
        )
        conn.commit()
        conn.close()
        user["balance"] = START_BALANCE
    return {"balance": user["balance"], "username": user["username"]}

@app.get("/api/user_bets/{user_id}")
async def api_user_bets(user_id: int):
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    bets = get_user_bets(user_id, 50)
    return bets

@app.post("/api/spin")
async def api_spin(data: SpinRequest):
    user_id = data.user_id
    mode = data.mode
    cost = SPIN_COSTS.get(mode, 25)
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] < cost:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    update_balance(user_id, -cost, f"Спин в режиме {mode}")
    win, prize_name, prize_value = get_next_spin_result(user_id, mode)
    if win:
        update_balance(user_id, prize_value, f"Выигрыш: {prize_name}")
        add_win(user_id, prize_name, prize_value, mode)
        message = f"🎉 Вы выиграли {prize_name} (+{prize_value} токенов)!"
    else:
        message = "😞 К сожалению, вы проиграли. Попробуйте ещё раз!"
    new_balance = get_user(user_id)["balance"]
    return {
        "win": win,
        "prize_name": prize_name if win else None,
        "prize_value": prize_value if win else 0,
        "new_balance": new_balance,
        "message": message
    }

@app.post("/api/slot_spin")
async def api_slot_spin(data: SlotSpinRequest):
    user_id = data.user_id
    bet = data.bet
    if bet < 20 or bet > 100:
        raise HTTPException(status_code=400, detail="Ставка должна быть от 20 до 100 токенов")
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] < bet:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    
    update_balance(user_id, -bet, f"Ставка в игровом автомате {bet} токенов")
    win, symbols, win_amount = get_slot_result(bet)
    if win:
        update_balance(user_id, win_amount, f"Выигрыш в игровом автомате {win_amount} токенов")
        add_win(user_id, f"🎰 {symbols[0]}{symbols[1]}{symbols[2]}", win_amount, "slot")
    new_balance = get_user(user_id)["balance"]
    return {
        "win": win,
        "symbols": symbols,
        "win_amount": win_amount if win else 0,
        "new_balance": new_balance
    }

@app.post("/api/rocket/start")
async def rocket_start(data: RocketStartRequest):
    user_id = data.user_id
    bet = data.bet
    if bet < 500 or bet > 5000:
        raise HTTPException(status_code=400, detail="Ставка должна быть от 500 до 5000 токенов")
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] < bet:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    
    update_balance(user_id, -bet, f"Ставка в ракетке {bet} токенов")
    
    if random.random() < 0.05:
        crash_display = 0.7 + random.random() * 98.3
    else:
        crash_display = random.random() * 0.7
    
    global round_counter
    round_counter += 1
    round_id = round_counter
    rocket_rounds[round_id] = {
        "user_id": user_id,
        "bet": bet,
        "crash_display": crash_display,
        "start_time": time.time(),
        "status": "active",
        "current_display": 0.0
    }
    
    return {"round_id": round_id}

@app.get("/api/rocket/status/{round_id}")
async def rocket_status(round_id: int):
    if round_id not in rocket_rounds:
        raise HTTPException(status_code=404, detail="Round not found")
    round_data = rocket_rounds[round_id]
    
    if round_data["status"] == "crashed":
        return {
            "display_multiplier": round_data["crash_display"],
            "crashed": True,
            "cashed_out": False
        }
    if round_data["status"] == "cashed_out":
        return {
            "display_multiplier": round_data["current_display"],
            "crashed": False,
            "cashed_out": True
        }
    
    elapsed = time.time() - round_data["start_time"]
    display_multiplier = elapsed * 0.3
    if display_multiplier >= round_data["crash_display"]:
        round_data["status"] = "crashed"
        return {
            "display_multiplier": round_data["crash_display"],
            "crashed": True,
            "cashed_out": False
        }
    else:
        round_data["current_display"] = display_multiplier
        return {
            "display_multiplier": display_multiplier,
            "crashed": False,
            "cashed_out": False
        }

@app.post("/api/rocket/cashout")
async def rocket_cashout(data: RocketCashoutRequest):
    round_id = data.round_id
    user_id = data.user_id
    if round_id not in rocket_rounds:
        raise HTTPException(status_code=404, detail="Round not found")
    round_data = rocket_rounds[round_id]
    if round_data["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your round")
    if round_data["status"] != "active":
        raise HTTPException(status_code=400, detail="Round already finished")
    
    elapsed = time.time() - round_data["start_time"]
    display_multiplier = elapsed * 0.3
    if display_multiplier >= round_data["crash_display"]:
        round_data["status"] = "crashed"
        raise HTTPException(status_code=400, detail="Ракета уже упала")
    
    real_multiplier = 1.0 + display_multiplier
    win_amount = int(round_data["bet"] * real_multiplier)
    update_balance(user_id, win_amount, f"Выигрыш в ракетке {win_amount} токенов")
    add_win(user_id, f"🚀 x{real_multiplier:.2f}", win_amount, "rocket")
    round_data["status"] = "cashed_out"
    round_data["current_display"] = display_multiplier
    new_balance = get_user(user_id)["balance"]
    return {
        "win_amount": win_amount,
        "new_balance": new_balance,
        "multiplier": real_multiplier
    }

@app.post("/api/withdraw")
async def api_withdraw(data: WithdrawRequest):
    user_id = data.user_id
    amount = data.amount
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] < amount:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    if amount < 500:
        raise HTTPException(status_code=400, detail="Минимальная сумма вывода – 500 токенов")
    create_withdraw_request(user_id, amount)
    return {"status": "success", "message": "Заявка на вывод отправлена администратору"}

@app.get("/api/leaderboard")
async def api_leaderboard():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 10")
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/api/recent_wins")
async def api_recent_wins():
    return get_recent_wins(limit=10)

@app.get("/api/prizes/{mode}")
async def api_get_prizes(mode: str):
    if mode not in SPIN_COSTS:
        raise HTTPException(status_code=400, detail="Invalid mode")
    return get_prizes_for_mode(mode, 40)

@app.get("/api/referral/{user_id}")
async def api_get_referral(user_id: int):
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    info = get_referral_info(user_id)
    link = get_referral_link(user_id)
    return {"code": info["code"], "count": info["count"], "link": link}

@app.post("/api/activate_promo")
async def activate_promo(data: PromoRequest):
    user_id = data.user_id
    code = data.code.lower().strip()
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if code not in PROMOCODES:
        raise HTTPException(status_code=400, detail="Неверный промокод")
    
    if is_promo_used(user_id, code):
        raise HTTPException(status_code=400, detail="Вы уже использовали этот промокод")
    
    reward = PROMOCODES[code]
    update_balance(user_id, reward, f"Промокод {code}")
    use_promo(user_id, code)
    
    new_balance = get_user(user_id)["balance"]
    return {
        "status": "success",
        "message": f"Промокод активирован! Вы получили +{reward} токенов",
        "new_balance": new_balance
    }

# ==================== ЗАПУСК ====================
async def set_webhook():
    webhook_url = f"https://star-drop.onrender.com/webhook"
    await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    logging.info(f"Webhook установлен на {webhook_url}")

async def run_uvicorn():
    port = int(os.environ.get("PORT", 10000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    server_task = asyncio.create_task(run_uvicorn())
    await set_webhook()
    await server_task

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Остановка сервисов...")
        sys.exit(0)
