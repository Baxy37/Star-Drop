import os
import sys
import asyncio
import logging
import sqlite3
import random
import signal
from datetime import datetime
from typing import Optional, List, Dict
import json

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

PRIZES = {
    "light": [
        {"name": "🎈 Шар", "value": 15},
        {"name": "🍬 Конфета", "value": 20},
        {"name": "⭐ Звезда", "value": 25},
        {"name": "🌸 Цветок", "value": 40},
        {"name": "💨 Пусто", "value": 0},
        {"name": "💨 Пусто", "value": 0},
        {"name": "💨 Пусто", "value": 0},
        {"name": "💨 Пусто", "value": 0},
    ],
    "normal": [
        {"name": "🎮 Приставка", "value": 120},
        {"name": "📱 Смартфон", "value": 200},
        {"name": "🎧 Наушники", "value": 150},
        {"name": "⌚ Умные часы", "value": 250},
        {"name": "💨 Пусто", "value": 0},
        {"name": "💨 Пусто", "value": 0},
        {"name": "💨 Пусто", "value": 0},
        {"name": "💨 Пусто", "value": 0},
    ],
    "hard": [
        {"name": "👑 Корона", "value": 600},
        {"name": "💎 Бриллиант", "value": 800},
        {"name": "🚁 Вертолёт", "value": 700},
        {"name": "🛸 НЛО", "value": 1000},
        {"name": "💨 Пусто", "value": 0},
        {"name": "💨 Пусто", "value": 0},
        {"name": "💨 Пусто", "value": 0},
        {"name": "💨 Пусто", "value": 0},
    ]
}

WIN_CHANCE = 35
DB_NAME = "star_drop.db"
WEBAPP_URL = "https://star-drop.onrender.com"  # ваш домен
REFERRAL_BONUS = 50

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
    import hashlib
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

init_db()

# ==================== УТИЛИТЫ ====================
def get_spin_result(mode: str):
    win = random.randint(1, 100) <= WIN_CHANCE
    if win:
        available_prizes = [p for p in PRIZES[mode] if p["value"] > 0]
        if available_prizes:
            prize = random.choice(available_prizes)
            return True, prize["name"], prize["value"]
    return False, "Проигрыш", 0

def get_prizes_for_mode(mode: str):
    return PRIZES[mode]

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

STATIC_FILES = {
    "index.html": """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Star Drop</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div id="top-bar">
        <div id="username" style="cursor:pointer;">@user</div>
        <div id="balance">
            <span id="balance-amount">0</span> $
            <button id="deposit-btn">+</button>
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
    <div id="mode-selector">
        <button class="mode-btn active" data-mode="light">Light</button>
        <button class="mode-btn" data-mode="normal">Normal</button>
        <button class="mode-btn" data-mode="hard">Hard</button>
    </div>
    <div id="wheel-container">
        <canvas id="wheelCanvas" width="300" height="300"></canvas>
    </div>
    <div id="mode-info">
        <span>Стоимость спина: <span id="spin-cost">25</span> токенов</span>
    </div>
    <button id="spin-btn">Крутить!</button>
    <div id="result-message"></div>
    <div id="notification-feed">
        <h3>Последние выигрыши</h3>
        <ul id="feed-list"></ul>
    </div>
    <button id="withdraw-btn">Вывести токены</button>
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
    padding: 16px;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    transition: background 0.3s;
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
#top-bar {
    display: flex;
    justify-content: space-between;
    width: 100%;
    padding: 10px 0;
    border-bottom: 1px solid var(--border-color);
}
#username {
    font-size: 18px;
    font-weight: 600;
    color: var(--accent-color);
    cursor: pointer;
}
#username:hover {
    text-decoration: underline;
}
#balance {
    font-size: 18px;
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--accent-color);
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
}
.deposit-option {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 10px 20px;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
}
#close-deposit {
    background: transparent;
    color: var(--accent-color);
    border: none;
    font-size: 20px;
    cursor: pointer;
}
#mode-selector {
    display: flex;
    gap: 12px;
    margin: 20px 0;
}
.mode-btn {
    background: #222;
    color: #aaa;
    border: none;
    padding: 10px 24px;
    border-radius: 20px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
}
.mode-btn.active {
    background: var(--accent-color);
    color: #0a0a0a;
    box-shadow: 0 0 15px var(--accent-glow);
}
#wheel-container {
    position: relative;
    width: 300px;
    height: 300px;
    margin: 20px auto;
}
#wheelCanvas {
    width: 100%;
    height: 100%;
    border-radius: 50%;
    box-shadow: 0 0 30px var(--accent-glow);
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
    transition: 0.1s;
    margin: 10px 0;
}
#spin-btn:active {
    transform: scale(0.95);
}
#mode-info {
    margin: 10px 0;
    color: #ccc;
    font-size: 14px;
}
#result-message {
    margin: 10px 0;
    font-size: 18px;
    font-weight: 600;
    min-height: 40px;
    text-align: center;
}
#notification-feed {
    width: 100%;
    max-width: 400px;
    background: var(--card-bg);
    border-radius: 12px;
    padding: 12px;
    margin: 20px 0;
}
#notification-feed h3 {
    color: var(--accent-color);
    margin-bottom: 8px;
    font-size: 16px;
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
#feed-list li:last-child {
    border-bottom: none;
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
}
""",
    "script.js": """const BASE_URL = window.location.origin;
let user_id = null;
let balance = 0;
let currentMode = 'light';
let isSpinning = false;

window.Telegram.WebApp.ready();
const tgUser = window.Telegram.WebApp.initDataUnsafe?.user;
if (tgUser && tgUser.id) {
    user_id = tgUser.id;
    document.getElementById('username').textContent = '@' + (tgUser.username || tgUser.first_name);
    fetchUserData();
} else {
    user_id = prompt('Введите ваш Telegram ID (для теста)') || 123456789;
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
    navigator.clipboard.writeText(link).then(() => {
        alert('Ссылка скопирована!');
    }).catch(() => {
        alert('Не удалось скопировать ссылку, скопируйте вручную: ' + link);
    });
});

document.getElementById('referral-modal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) {
        document.getElementById('referral-modal').style.display = 'none';
    }
});

function applyTheme(mode) {
    document.body.classList.remove('theme-light', 'theme-normal', 'theme-hard');
    if (mode === 'light') document.body.classList.add('theme-light');
    else if (mode === 'normal') document.body.classList.add('theme-normal');
    else if (mode === 'hard') document.body.classList.add('theme-hard');
}

document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
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
    document.getElementById('spin-cost').textContent = costs[currentMode];
}

const canvas = document.getElementById('wheelCanvas');
const ctx = canvas.getContext('2d');

function drawWheel() {
    const width = canvas.width;
    const height = canvas.height;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) / 2 - 5;
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
        ctx.fillStyle = i % 2 === 0 ? '#ffd700' : '#b8860b';
        ctx.fill();
        ctx.strokeStyle = '#0a0a0a';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.rotate(startAngle + angleStep / 2);
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = '#0a0a0a';
        ctx.font = 'bold 14px sans-serif';
        const label = modePrizes[i].name;
        ctx.fillText(label, radius * 0.65, 0);
        ctx.restore();
    }
}

function getPrizesForMode(mode) {
    const allPrizes = {
        light: [
            {name: '🎈 Шар', value: 15},
            {name: '🍬 Конфета', value: 20},
            {name: '⭐ Звезда', value: 25},
            {name: '🌸 Цветок', value: 40},
            {name: '💨 Пусто', value: 0},
            {name: '💨 Пусто', value: 0},
            {name: '💨 Пусто', value: 0},
            {name: '💨 Пусто', value: 0}
        ],
        normal: [
            {name: '🎮 Приставка', value: 120},
            {name: '📱 Смартфон', value: 200},
            {name: '🎧 Наушники', value: 150},
            {name: '⌚ Умные часы', value: 250},
            {name: '💨 Пусто', value: 0},
            {name: '💨 Пусто', value: 0},
            {name: '💨 Пусто', value: 0},
            {name: '💨 Пусто', value: 0}
        ],
        hard: [
            {name: '👑 Корона', value: 600},
            {name: '💎 Бриллиант', value: 800},
            {name: '🚁 Вертолёт', value: 700},
            {name: '🛸 НЛО', value: 1000},
            {name: '💨 Пусто', value: 0},
            {name: '💨 Пусто', value: 0},
            {name: '💨 Пусто', value: 0},
            {name: '💨 Пусто', value: 0}
        ]
    };
    return allPrizes[mode] || allPrizes.light;
}

applyTheme('light');
drawWheel();

document.getElementById('spin-btn').addEventListener('click', async () => {
    if (isSpinning) return;
    isSpinning = true;
    document.getElementById('spin-btn').disabled = true;
    document.getElementById('spin-btn').textContent = 'Крутим...';
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
            document.getElementById('result-message').textContent = data.message;
            animateWheel();
            if (data.win) setTimeout(fetchFeed, 1000);
        } else {
            document.getElementById('result-message').textContent = '❌ ' + data.detail;
        }
    } catch (e) {
        document.getElementById('result-message').textContent = 'Ошибка соединения';
        console.error(e);
    }
    isSpinning = false;
    document.getElementById('spin-btn').disabled = false;
    document.getElementById('spin-btn').textContent = 'Крутить!';
});

function animateWheel() {
    const angle = Math.random() * 2 * Math.PI * 5 + 2 * Math.PI;
    canvas.style.transition = 'transform 2s cubic-bezier(0.17, 0.67, 0.12, 0.99)';
    canvas.style.transform = 'rotate(' + angle + 'rad)';
    setTimeout(() => {
        canvas.style.transition = 'none';
        canvas.style.transform = 'rotate(0rad)';
    }, 2100);
}

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
        window.open(links[amount], '_blank');
        alert('После оплаты, пожалуйста, напишите администратору для зачисления токенов (временно).');
    });
});

document.getElementById('close-deposit').addEventListener('click', () => {
    document.getElementById('deposit-menu').style.display = 'none';
});

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

document.getElementById('withdraw-btn').addEventListener('click', async () => {
    const amount = prompt('Введите сумму вывода (минимум 100 токенов):');
    if (!amount || isNaN(amount) || amount < 100) {
        alert('Введите корректное число не менее 100');
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
"""
}

# Создаём файлы только при отсутствии
for filename, content in STATIC_FILES.items():
    filepath = os.path.join(STATIC_DIR, filename)
    if not os.path.exists(filepath):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Создан {filepath}")

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

@app.post("/api/withdraw")
async def api_withdraw(data: WithdrawRequest):
    user_id = data.user_id
    amount = data.amount
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] < amount:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    if amount < 100:
        raise HTTPException(status_code=400, detail="Минимальная сумма вывода – 100 токенов")
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
