import os
import sys
import asyncio
import logging
import sqlite3
import random
import signal
import time
from datetime import datetime
from typing import Optional, List, Dict
import json
import hashlib

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8988678866:AAHIWxUB8zKBCoF21g7OVYEEWnwEF_MpLmI"

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

# Призы для бекенда (используются при вычислении выигрыша)
PRIZES = {
    "light": [
        {"name": "🧸 Мишка", "value": 15},
        {"name": "🍬 Конфета", "value": 20},
        {"name": "⭐ Звезда", "value": 25},
        {"name": "🌹 Роза", "value": 40},
        {"name": "💨 Пусто", "value": 0},
        {"name": "🧸 Мишка", "value": 10},
        {"name": "💨 Пусто", "value": 0},
        {"name": "⭐ Звезда", "value": 20},
    ],
    "normal": [
        {"name": "💍 Кольцо", "value": 120},
        {"name": "💎 Бриллиант", "value": 200},
        {"name": "🧁 Торт", "value": 150},
        {"name": "🏆 Кубок", "value": 250},
        {"name": "💨 Пусто", "value": 0},
        {"name": "💍 Кольцо", "value": 100},
        {"name": "💨 Пусто", "value": 0},
        {"name": "💎 Бриллиант", "value": 180},
    ],
    "hard": [
        {"name": "👑 Корона", "value": 600},
        {"name": "🧢 Кепка Дурова", "value": 800},
        {"name": "🚀 Ракета", "value": 700},
        {"name": "🛸 НЛО", "value": 1000},
        {"name": "💨 Пусто", "value": 0},
        {"name": "👑 Корона", "value": 500},
        {"name": "💨 Пусто", "value": 0},
        {"name": "🚀 Ракета", "value": 650},
    ]
}

DB_NAME = "star_drop.db"
WEBAPP_URL = "https://star-drop.onrender.com"  # ваш домен
REFERRAL_BONUS = 50

# Символы для игрового автомата
SLOT_SYMBOLS = ['🍒', '🍋', '🍊', '🍇', '🍉', '🍓', '🍑', '🎰']
SLOT_WIN_MULTIPLIER = 2  # выигрыш = ставка * 2

# Список доступных промокодов с наградами
PROMOCODES = {
    "rifleman": 50,
}

# Глобальный словарь для активных раундов ракетки
rocket_rounds = {}
round_counter = 0

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
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

def create_user(user_id: int, username: str = None, referrer_code: str = None):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    code = hashlib.md5(str(user_id).encode()).hexdigest()[:8]
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, username, referral_code) VALUES (?, ?, ?)",
        (user_id, username, code)
    )
    if referrer_code:
        cur.execute("SELECT user_id FROM users WHERE referral_code = ?", (referrer_code,))
        row = cur.fetchone()
        if row:
            referrer_id = row[0]
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

# ==================== УТИЛИТЫ ====================
def get_spin_result(mode: str):
    # Определяем шанс выигрыша в зависимости от режима
    if mode == "light":
        win_chance = 30  # фиксированный 30%
    elif mode == "normal":
        win_chance = random.randint(20, 50)  # от 20% до 50%
    elif mode == "hard":
        win_chance = random.randint(30, 45)  # от 30% до 45%
    else:
        win_chance = 35  # по умолчанию

    win = random.randint(1, 100) <= win_chance
    if win:
        available_prizes = [p for p in PRIZES[mode] if p["value"] > 0]
        if available_prizes:
            prize = random.choice(available_prizes)
            return True, prize["name"], prize["value"]
    return False, "❌ Проигрыш", 0

def get_prizes_for_mode(mode: str):
    return PRIZES[mode]

def get_slot_result(bet: int):
    """Возвращает (выигрыш_да, символы, выигрыш_сумма)"""
    # Определяем шанс выигрыша в зависимости от ставки
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

# ==================== ТЕЛЕГРАМ БОТ (только webhook) ====================
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

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
    create_user(user_id, username, referrer_code)
    await message.answer(
        f"🎉 Приветствую тебя, {username}!\n"
        "Добро пожаловать в **Star Drop** – розыгрыш подарков Telegram!\n\n"
        "Нажми кнопку ниже, чтобы открыть наше мини-приложение и испытать удачу! 🍀",
        reply_markup=get_start_keyboard()
    )

# ==================== ВЕБ-СЕРВЕР (FASTAPI) ====================
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Создаём папку static и файлы
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)

# ==================== СТАТИЧЕСКИЕ ФАЙЛЫ ====================
STATIC_FILES = {
    "index.html": """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Star Drop</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body class="theme-light">
    <!-- Фоновые летящие элементы -->
    <div class="stars-background">
        <span>⭐</span><span>✨</span><span>🌟</span><span>💫</span>
        <span>🎁</span><span>🧸</span><span>💎</span><span>🧢</span>
        <span>🚀</span><span>💍</span><span>🧁</span><span>🎈</span>
        <span>👑</span><span>🛸</span><span>💎</span><span>🎁</span>
    </div>

    <div id="top-bar">
        <div id="username" style="cursor:pointer;">@user</div>
        <div id="balance">
            <span id="balance-amount">0</span> 🌟
            <button id="deposit-btn">+</button>
            <button id="gifts-btn">Мои подарки</button>
        </div>
    </div>

    <!-- Меню пополнения -->
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

    <!-- РУЛЕТКА -->
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
        <div id="wheel-container">
            <div id="wheel-pointer">▼</div>
            <canvas id="wheelCanvas" width="300" height="300"></canvas>
        </div>
        <div id="spin-area">
            <div id="spin-info">1 спин = <span id="spin-cost">25</span> монет</div>
            <button id="spin-btn">КРУТИТЬ <span id="spin-cost-label">25 Токенов</span></button>
        </div>
        <div id="result-message"></div>
    </div>

    <!-- ИГРОВОЙ АВТОМАТ (СЛОТ) -->
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

    <!-- РАКЕТКА (Aviator) -->
    <div id="rocket-page" style="display:none;">
        <div id="main-title">
            <h1>🚀 РАКЕТКА</h1>
            <p>Лови момент и умножай ставку до x100!</p>
        </div>
        <div id="rocket-game">
            <div id="rocket-display">
                <div id="rocket-multiplier">1.00</div>
                <div id="rocket-status">Ожидание</div>
            </div>
            <div id="rocket-bet-control">
                <label>Ставка: <span id="rocket-bet-display">500</span> токенов</label>
                <input type="range" id="rocket-bet-range" min="500" max="5000" step="100" value="500">
            </div>
            <div id="rocket-buttons">
                <button id="rocket-start-btn">🚀 Старт</button>
                <button id="rocket-cashout-btn" disabled>💰 Стоп</button>
            </div>
            <div id="rocket-result"></div>
        </div>
    </div>

    <!-- Общие элементы -->
    <div id="notification-feed">
        <h3>Последние выигрыши</h3>
        <ul id="feed-list"></ul>
    </div>

    <button id="withdraw-btn">Вывести токены</button>

    <!-- Промокоды -->
    <div id="promo-area">
        <input type="text" id="promo-input" placeholder="Введите промокод" maxlength="20">
        <button id="promo-btn">Активировать</button>
        <div id="promo-message" style="color: var(--accent-color); font-size: 14px; margin-top: 5px; text-align:center;"></div>
    </div>

    <!-- Нижняя навигация -->
    <div id="bottom-nav">
        <button class="nav-btn active" data-tab="roulette">Рулетка</button>
        <button class="nav-btn" data-tab="slot">Барабан</button>
        <button class="nav-btn" data-tab="rocket">Ракетка</button>
    </div>

    <script src="/static/script.js"></script>
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

/* Цветовые темы для режимов */
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

/* Анимированный фон */
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
    animation: fall linear infinite;
    opacity: 0.4;
    color: var(--accent-color);
    text-shadow: 0 0 8px var(--accent-glow);
    font-size: 18px;
}

.stars-background span:nth-child(1) { left: 5%; animation-duration: 8s; font-size: 16px; }
.stars-background span:nth-child(2) { left: 15%; animation-duration: 12s; font-size: 22px; animation-delay: 1s; }
.stars-background span:nth-child(3) { left: 25%; animation-duration: 7s; font-size: 14px; animation-delay: 2s; }
.stars-background span:nth-child(4) { left: 35%; animation-duration: 10s; font-size: 20px; animation-delay: 0.5s; }
.stars-background span:nth-child(5) { left: 45%; animation-duration: 9s; font-size: 24px; animation-delay: 3s; }
.stars-background span:nth-child(6) { left: 55%; animation-duration: 6s; font-size: 18px; animation-delay: 1.5s; }
.stars-background span:nth-child(7) { left: 65%; animation-duration: 11s; font-size: 28px; animation-delay: 2.5s; }
.stars-background span:nth-child(8) { left: 75%; animation-duration: 8s; font-size: 16px; animation-delay: 4s; }
.stars-background span:nth-child(9) { left: 85%; animation-duration: 10s; font-size: 20px; animation-delay: 0.8s; }
.stars-background span:nth-child(10) { left: 92%; animation-duration: 7s; font-size: 14px; animation-delay: 3.5s; }
.stars-background span:nth-child(11) { left: 10%; animation-duration: 13s; font-size: 26px; animation-delay: 5s; }
.stars-background span:nth-child(12) { left: 40%; animation-duration: 9s; font-size: 30px; animation-delay: 1.2s; }
.stars-background span:nth-child(13) { left: 70%; animation-duration: 11s; font-size: 22px; animation-delay: 2.8s; }
.stars-background span:nth-child(14) { left: 20%; animation-duration: 8s; font-size: 18px; animation-delay: 4.5s; }
.stars-background span:nth-child(15) { left: 60%; animation-duration: 12s; font-size: 28px; animation-delay: 0.2s; }
.stars-background span:nth-child(16) { left: 80%; animation-duration: 7s; font-size: 20px; animation-delay: 3.8s; }

@keyframes fall {
    0% { transform: translateY(-30px) rotate(0deg); opacity: 0; }
    20% { opacity: 0.7; }
    80% { opacity: 0.7; }
    100% { transform: translateY(105vh) rotate(720deg); opacity: 0; }
}

#top-bar {
    display: flex;
    justify-content: space-between;
    width: 100%;
    padding: 10px 0;
    border-bottom: 1px solid var(--border-color);
    z-index: 2;
}

#username {
    font-size: 18px;
    font-weight: 600;
    color: var(--accent-color);
    cursor: pointer;
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

#deposit-btn {
    background: var(--accent-color);
    border: none;
    border-radius: 50%;
    width: 28px;
    height: 28px;
    font-size: 20px;
    font-weight: bold;
    color: #0a0a0a;
    cursor: pointer;
    transition: background 0.3s, transform 0.2s;
}
#deposit-btn:hover { transform: scale(1.1); }

#gifts-btn {
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

#wheel-container {
    position: relative;
    width: 280px;
    height: 280px;
    margin: 15px auto;
    z-index: 2;
}

#wheel-pointer {
    position: absolute;
    top: -12px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 24px;
    color: var(--accent-color);
    z-index: 5;
    text-shadow: 0 0 8px var(--accent-glow);
    transition: color 0.3s, text-shadow 0.3s;
}

#wheelCanvas {
    width: 100%;
    height: 100%;
    border-radius: 50%;
    box-shadow: 0 0 30px var(--accent-glow);
    border: 4px solid var(--accent-color);
    transition: transform 3s cubic-bezier(0.15, 0.7, 0.1, 1),
                box-shadow 0.3s,
                border-color 0.3s;
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

/* Стили для игрового автомата */
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

/* Стили для ракетки */
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
    padding: 15px 0;
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

#rocket-result {
    margin-top: 10px;
    font-size: 18px;
    font-weight: 600;
    text-align: center;
    color: var(--accent-color);
    min-height: 30px;
}

/* Общие элементы */
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
""",
    "script.js": """const BASE_URL = window.location.origin;
let user_id = null;
let balance = 0;
let currentMode = 'light';
let isSpinning = false;
let currentRotation = 0;

if (window.Telegram && window.Telegram.WebApp) {
    window.Telegram.WebApp.ready();
    const tgUser = window.Telegram.WebApp.initDataUnsafe?.user;
    if (tgUser && tgUser.id) {
        user_id = tgUser.id;
        document.getElementById('username').textContent = '@' + (tgUser.username || tgUser.first_name);
        fetchUserData();
    }
}
if (!user_id) {
    user_id = prompt('Введите ваш Telegram ID (для теста):') || 123456789;
    document.getElementById('username').textContent = '@user_' + user_id;
    fetchUserData();
}

async function fetchUserData() {
    try {
        const resp = await fetch(`/api/user/${user_id}`);
        if (!resp.ok) throw new Error('User not found');
        const data = await resp.json();
        balance = data.balance;
        document.getElementById('balance-amount').textContent = balance;
    } catch (e) {
        console.error(e);
    }
}

function updateBalanceUI(newBalance) {
    balance = newBalance;
    document.getElementById('balance-amount').textContent = newBalance;
}

// === Реферальное окно ===
document.getElementById('username').addEventListener('click', async () => {
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
        navigator.clipboard.writeText(link).then(() => {
            alert('Ссылка скопирована!');
        }).catch(() => {
            fallbackCopy(link);
        });
    } else {
        fallbackCopy(link);
    }
});

function fallbackCopy(text) {
    const input = document.createElement('input');
    input.style.position = 'fixed';
    input.style.opacity = '0';
    input.value = text;
    document.body.appendChild(input);
    input.select();
    try {
        document.execCommand('copy');
        alert('Ссылка скопирована!');
    } catch (e) {
        alert('Не удалось скопировать, скопируйте вручную: ' + text);
    }
    document.body.removeChild(input);
}

document.getElementById('gifts-btn').addEventListener('click', () => {
    alert('Здесь будут ваши выигранные Telegram-подарки!');
});

// === Промокоды ===
document.getElementById('promo-btn').addEventListener('click', async () => {
    const input = document.getElementById('promo-input');
    const code = input.value.trim();
    const msg = document.getElementById('promo-message');
    if (!code) {
        msg.textContent = 'Введите промокод';
        return;
    }
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
        } else {
            msg.textContent = '❌ ' + data.detail;
        }
    } catch (e) {
        msg.textContent = 'Ошибка соединения';
        console.error(e);
    }
});

// === Тема и колесо ===
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
        drawWheel();
    });
});

function updateSpinCost() {
    const costs = { light: 25, normal: 50, hard: 100 };
    const cost = costs[currentMode];
    document.getElementById('spin-cost').textContent = cost;
    document.getElementById('spin-cost-label').textContent = cost + ' Токенов';
}

const canvas = document.getElementById('wheelCanvas');
const ctx = canvas.getContext('2d');

function getPrizesForMode(mode) {
    const allPrizes = {
        light: [
            { name: '🧸', value: 15 },
            { name: '🍬', value: 20 },
            { name: '⭐', value: 25 },
            { name: '🌹', value: 40 },
            { name: '💨', value: 0 },
            { name: '🧸', value: 10 },
            { name: '💨', value: 0 },
            { name: '⭐', value: 20 }
        ],
        normal: [
            { name: '💍', value: 120 },
            { name: '💎', value: 200 },
            { name: '🧁', value: 150 },
            { name: '🏆', value: 250 },
            { name: '💨', value: 0 },
            { name: '💍', value: 100 },
            { name: '💨', value: 0 },
            { name: '💎', value: 180 }
        ],
        hard: [
            { name: '👑', value: 600 },
            { name: '🧢', value: 800 },
            { name: '🚀', value: 700 },
            { name: '🛸', value: 1000 },
            { name: '💨', value: 0 },
            { name: '👑', value: 500 },
            { name: '💨', value: 0 },
            { name: '🚀', value: 650 }
        ]
    };
    return allPrizes[mode] || allPrizes.light;
}

function drawWheel() {
    const width = canvas.width;
    const height = canvas.height;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) / 2 - 4;
    
    ctx.clearRect(0, 0, width, height);
    const modePrizes = getPrizesForMode(currentMode);
    const count = modePrizes.length;
    const angleStep = (2 * Math.PI) / count;

    for (let i = 0; i < count; i++) {
        const startAngle = i * angleStep;
        const endAngle = startAngle + angleStep;
        
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, startAngle, endAngle);
        ctx.closePath();
        
        if (currentMode === 'light') {
            ctx.fillStyle = i % 2 === 0 ? '#ffea75' : '#e6c229';
        } else if (currentMode === 'normal') {
            ctx.fillStyle = i % 2 === 0 ? '#64b5f6' : '#1976d2';
        } else {
            ctx.fillStyle = i % 2 === 0 ? '#e57373' : '#d32f2f';
        }
        
        ctx.fill();
        ctx.strokeStyle = '#0a0a0a';
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.rotate(startAngle + angleStep / 2);
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.font = 'bold 24px sans-serif';
        ctx.fillText(modePrizes[i].name, radius * 0.65, 0);
        ctx.restore();
    }

    ctx.beginPath();
    ctx.arc(centerX, centerY, 22, 0, 2 * Math.PI);
    ctx.fillStyle = '#111';
    ctx.fill();
    ctx.strokeStyle = currentMode === 'light' ? '#ffd700' : (currentMode === 'normal' ? '#2196F3' : '#f44336');
    ctx.lineWidth = 3;
    ctx.stroke();
}

applyTheme('light');
drawWheel();
updateSpinCost();

// === Вращение рулетки ===
document.getElementById('spin-btn').addEventListener('click', async () => {
    if (isSpinning) return;
    isSpinning = true;
    document.getElementById('spin-btn').disabled = true;
    document.getElementById('spin-btn').innerHTML = 'КРУТИТЬ <span>Загрузка...</span>';
    document.getElementById('result-message').textContent = '';

    try {
        const resp = await fetch('/api/spin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id, mode: currentMode })
        });
        const data = await resp.json();
        
        if (resp.ok) {
            updateBalanceUI(data.new_balance);
            const extraSpins = 5;
            const randomAngle = Math.random() * 360;
            currentRotation += (extraSpins * 360) + randomAngle;
            canvas.style.transform = `rotate(${currentRotation}deg)`;

            setTimeout(() => {
                document.getElementById('result-message').textContent = data.message;
                if (data.win) fetchFeed();
            }, 3000);
        } else {
            document.getElementById('result-message').textContent = '❌ ' + data.detail;
        }
    } catch (e) {
        document.getElementById('result-message').textContent = 'Ошибка соединения';
        console.error(e);
    }

    setTimeout(() => {
        isSpinning = false;
        document.getElementById('spin-btn').disabled = false;
        const cost = { light: 25, normal: 50, hard: 100 }[currentMode];
        document.getElementById('spin-btn').innerHTML = 'КРУТИТЬ <span>' + cost + ' Токенов</span>';
    }, 3200);
});

// === Игровой автомат (слот) ===
let slotSpinning = false;
const slotSymbols = ['🍒', '🍋', '🍊', '🍇', '🍉', '🍓', '🍑', '🎰'];
const reels = [
    document.getElementById('reel1'),
    document.getElementById('reel2'),
    document.getElementById('reel3')
];

document.getElementById('bet-range').addEventListener('input', function() {
    const bet = parseInt(this.value);
    document.getElementById('bet-display').textContent = bet;
});

document.addEventListener('DOMContentLoaded', function() {
    const initialBet = parseInt(document.getElementById('bet-range').value);
    document.getElementById('bet-display').textContent = initialBet;
});

document.getElementById('spin-slot-btn').addEventListener('click', async () => {
    if (slotSpinning) return;
    const bet = parseInt(document.getElementById('bet-range').value);
    if (isNaN(bet) || bet < 20 || bet > 100) {
        alert('Ставка должна быть от 20 до 100 токенов');
        return;
    }
    if (balance < bet) {
        alert('Недостаточно токенов!');
        return;
    }

    slotSpinning = true;
    const btn = document.getElementById('spin-slot-btn');
    btn.disabled = true;
    btn.textContent = '🎰 Крутим...';

    let interval = setInterval(() => {
        reels.forEach(reel => {
            reel.textContent = slotSymbols[Math.floor(Math.random() * slotSymbols.length)];
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
            } else {
                resultDiv.textContent = '😞 Проигрыш. -' + bet + ' токенов';
                resultDiv.style.color = '#f44336';
            }
            if (data.win) fetchFeed();
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

// === Ракетка (Aviator) ===
let rocketInterval = null;
let rocketRoundId = null;
let rocketActive = false;

document.getElementById('rocket-bet-range').addEventListener('input', function() {
    document.getElementById('rocket-bet-display').textContent = this.value;
});

document.getElementById('rocket-start-btn').addEventListener('click', async () => {
    if (rocketActive) return;
    const bet = parseInt(document.getElementById('rocket-bet-range').value);
    if (isNaN(bet) || bet < 500 || bet > 5000) {
        alert('Ставка должна быть от 500 до 5000 токенов');
        return;
    }
    if (balance < bet) {
        alert('Недостаточно токенов!');
        return;
    }

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
            document.getElementById('rocket-start-btn').disabled = true;
            document.getElementById('rocket-cashout-btn').disabled = false;
            document.getElementById('rocket-result').textContent = '';
            document.getElementById('rocket-status').textContent = '🚀 Взлёт!';

            // Запускаем опрос статуса
            if (rocketInterval) clearInterval(rocketInterval);
            rocketInterval = setInterval(updateRocketStatus, 500);
            // Сразу обновить
            updateRocketStatus();
        } else {
            alert('❌ ' + data.detail);
        }
    } catch (e) {
        alert('Ошибка соединения');
        console.error(e);
    }
});

async function updateRocketStatus() {
    if (!rocketRoundId) return;
    try {
        const resp = await fetch(`/api/rocket/status/${rocketRoundId}`);
        const data = await resp.json();
        if (resp.ok) {
            document.getElementById('rocket-multiplier').textContent = data.current_multiplier.toFixed(2);
            if (data.crashed) {
                // Ракета упала
                document.getElementById('rocket-status').textContent = '💥 Упала!';
                document.getElementById('rocket-cashout-btn').disabled = true;
                document.getElementById('rocket-start-btn').disabled = false;
                rocketActive = false;
                if (rocketInterval) {
                    clearInterval(rocketInterval);
                    rocketInterval = null;
                }
                // Показываем результат проигрыша (уже списано)
                document.getElementById('rocket-result').textContent = '😞 Ракета упала. Ставка проиграна.';
                document.getElementById('rocket-result').style.color = '#f44336';
                // Обновляем баланс
                fetchUserData();
            } else if (data.cashed_out) {
                // Игрок уже вывел
                document.getElementById('rocket-status').textContent = '💰 Выведено!';
                document.getElementById('rocket-cashout-btn').disabled = true;
                document.getElementById('rocket-start-btn').disabled = false;
                rocketActive = false;
                if (rocketInterval) {
                    clearInterval(rocketInterval);
                    rocketInterval = null;
                }
                // Баланс обновим при каш-ауте, но на всякий случай
                fetchUserData();
            }
        } else {
            console.error('Status error:', data);
        }
    } catch (e) {
        console.error(e);
    }
}

document.getElementById('rocket-cashout-btn').addEventListener('click', async () => {
    if (!rocketRoundId || !rocketActive) return;
    try {
        const resp = await fetch('/api/rocket/cashout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ round_id: rocketRoundId, user_id })
        });
        const data = await resp.json();
        if (resp.ok) {
            // Успешный вывод
            document.getElementById('rocket-result').textContent = '🎉 Вы выиграли ' + data.win_amount + ' токенов!';
            document.getElementById('rocket-result').style.color = '#4CAF50';
            document.getElementById('rocket-status').textContent = '💰 Выведено!';
            document.getElementById('rocket-cashout-btn').disabled = true;
            document.getElementById('rocket-start-btn').disabled = false;
            rocketActive = false;
            if (rocketInterval) {
                clearInterval(rocketInterval);
                rocketInterval = null;
            }
            updateBalanceUI(data.new_balance);
            // Показать в ленте? Можно добавить, но не обязательно
            fetchFeed();
        } else {
            alert('❌ ' + data.detail);
        }
    } catch (e) {
        alert('Ошибка соединения');
        console.error(e);
    }
});

// === Пополнение ===
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
        if (links[amount]) {
            window.open(links[amount], '_blank');
        }
    });
});

document.getElementById('close-deposit').addEventListener('click', () => {
    document.getElementById('deposit-menu').style.display = 'none';
});

// === Лента выигрышей ===
async function fetchFeed() {
    try {
        const resp = await fetch('/api/recent_wins');
        const wins = await resp.json();
        const list = document.getElementById('feed-list');
        list.innerHTML = '';
        wins.forEach(w => {
            const li = document.createElement('li');
            li.textContent = '@' + w.username + ' выиграл ' + w.prize_name + ' (+' + w.prize_value + ' токенов)';
            list.appendChild(li);
        });
    } catch (e) {
        console.error(e);
    }
}

fetchFeed();
setInterval(fetchFeed, 5000);

// === Вывод (минимальная сумма 500) ===
document.getElementById('withdraw-btn').addEventListener('click', async () => {
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
        } else {
            alert('❌ ' + data.detail);
        }
    } catch (e) {
        alert('Ошибка соединения');
        console.error(e);
    }
});

// === Навигация по вкладкам ===
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.dataset.tab;
        if (tab === 'roulette') {
            document.getElementById('roulette-page').style.display = 'block';
            document.getElementById('slot-page').style.display = 'none';
            document.getElementById('rocket-page').style.display = 'none';
        } else if (tab === 'slot') {
            document.getElementById('roulette-page').style.display = 'none';
            document.getElementById('slot-page').style.display = 'block';
            document.getElementById('rocket-page').style.display = 'none';
        } else if (tab === 'rocket') {
            document.getElementById('roulette-page').style.display = 'none';
            document.getElementById('slot-page').style.display = 'none';
            document.getElementById('rocket-page').style.display = 'block';
            // При переключении обновить баланс
            fetchUserData();
        }
    });
});
"""
}

# Записываем файлы (перезаписываем)
for filename, content in STATIC_FILES.items():
    filepath = os.path.join(STATIC_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ Обновлён {filepath}")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Корневой путь – редирект на index.html
@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")

@app.head("/")
async def root_head():
    return RedirectResponse(url="/static/index.html")

# Webhook endpoint для Telegram
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
    return {"balance": user["balance"], "username": user["username"]}

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
    win, prize_name, prize_value = get_spin_result(mode)
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
    
    # Списываем ставку
    update_balance(user_id, -bet, f"Ставка в ракетке {bet} токенов")
    
    # Генерируем crash point
    # 95%: от 1.0 до 1.7, 5%: от 1.7 до 100.0
    if random.random() < 0.05:
        crash_point = 1.7 + random.random() * 98.3
    else:
        crash_point = 1.0 + random.random() * 0.7
    
    # Создаём раунд
    global round_counter
    round_counter += 1
    round_id = round_counter
    rocket_rounds[round_id] = {
        "user_id": user_id,
        "bet": bet,
        "crash_point": crash_point,
        "start_time": time.time(),
        "status": "active",  # active, crashed, cashed_out
        "current_multiplier": 1.0
    }
    
    return {"round_id": round_id, "crash_point": crash_point}

@app.get("/api/rocket/status/{round_id}")
async def rocket_status(round_id: int):
    if round_id not in rocket_rounds:
        raise HTTPException(status_code=404, detail="Round not found")
    round_data = rocket_rounds[round_id]
    
    if round_data["status"] == "crashed":
        return {
            "current_multiplier": round_data["crash_point"],
            "crashed": True,
            "cashed_out": False
        }
    if round_data["status"] == "cashed_out":
        return {
            "current_multiplier": round_data["current_multiplier"],
            "crashed": False,
            "cashed_out": True
        }
    
    # Активный раунд: вычисляем текущий множитель (линейно растёт)
    elapsed = time.time() - round_data["start_time"]
    # Множитель растёт со скоростью 0.5 за секунду
    current_multiplier = 1.0 + elapsed * 0.5
    if current_multiplier >= round_data["crash_point"]:
        # Ракета упала
        round_data["status"] = "crashed"
        current_multiplier = round_data["crash_point"]
        return {
            "current_multiplier": current_multiplier,
            "crashed": True,
            "cashed_out": False
        }
    else:
        round_data["current_multiplier"] = current_multiplier
        return {
            "current_multiplier": current_multiplier,
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
    
    # Получаем текущий множитель
    elapsed = time.time() - round_data["start_time"]
    current_multiplier = 1.0 + elapsed * 0.5
    if current_multiplier >= round_data["crash_point"]:
        # Ракета уже упала (должна была, но на всякий случай)
        round_data["status"] = "crashed"
        raise HTTPException(status_code=400, detail="Ракета уже упала")
    
    # Начисляем выигрыш
    win_amount = int(round_data["bet"] * current_multiplier)
    update_balance(user_id, win_amount, f"Выигрыш в ракетке {win_amount} токенов")
    # Добавляем в ленту выигрышей
    add_win(user_id, f"🚀 x{current_multiplier:.2f}", win_amount, "rocket")
    round_data["status"] = "cashed_out"
    round_data["current_multiplier"] = current_multiplier
    new_balance = get_user(user_id)["balance"]
    return {
        "win_amount": win_amount,
        "new_balance": new_balance,
        "multiplier": current_multiplier
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
    return get_prizes_for_mode(mode)

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
    port = int(os.environ.get("PORT", 10000))
    webhook_url = f"https://star-drop.onrender.com/webhook"
    await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    logging.info(f"Webhook установлен на {webhook_url}")

async def run_uvicorn():
    port = int(os.environ.get("PORT", 10000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def shutdown(sig, loop):
    logging.info(f"Received signal {sig}, shutting down...")
    await bot.delete_webhook()
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

async def main():
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(sig, loop)))
    await set_webhook()
    await run_uvicorn()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Остановка сервисов...")
        sys.exit(0)
