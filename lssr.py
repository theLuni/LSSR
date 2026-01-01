# coding: utf-8
# Председатель ЛССР - Бот для генерации сообщений на основе цепей Маркова

import asyncio
from datetime import datetime, timedelta
import json
import os
import random
import re
import sys
import time
from typing import Dict, List, Optional, Tuple
from enum import Enum
import math

import aiofiles
import aiogram
import dateparser
import dotenv
import markovify
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types import (Message, InlineKeyboardMarkup, 
                          InlineKeyboardButton, CallbackQuery,
                          ChatMemberUpdated, ChatMember)
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler, current_handler
from loguru import logger

# Определяем базовую директорию
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Загружаем конфигурацию
dotenv.load_dotenv()

# ==================== КОНФИГУРАЦИЯ ====================
class Config:
    """Конфигурация бота с настройками по умолчанию"""
    
    # Основные настройки
    BOT_NAME = "Доктор Дью"
    BOT_VERSION = "1.5.6"
    BOT_DESCRIPTION = "Революционный бот для генерации сообщений на основе цепей Маркова"
    
    # Администраторы
    MAIN_ADMIN_ID = 5929120983  # Главный администратор
    ADMIN_IDS = [5929120983]    # Список администраторов (добавьте другие ID по необходимости)
    
    # Настройки генерации
    DEFAULT_CHANCE = 5  # Базовый шанс ответа в процентах
    TRIGGERED_CHANCE = 80  # Шанс при упоминании бота
    MIN_MESSAGES_FOR_TRAINING = 50  # Минимальное кол-во сообщений для обучения
    MAX_MODEL_SIZE = 30000  # Максимальное количество сообщений в модели
    SAVE_INTERVAL = 300  # Интервал автосохранения в секундах
    
    # Настройки генерации текста
    MIN_SENTENCE_LENGTH = 10
    MAX_SENTENCE_LENGTH = 500
    SHORT_SENTENCE_MAX = 50
    MAX_TRIES_GENERATION = 100
    
    # Настройки времени
    DEFAULT_DISABLE_TIME = timedelta(days=7)  # По умолчанию отключаем на неделю
    MIN_DISABLE_TIME = timedelta(minutes=5)   # Минимальное время отключения
    
    DB_FOLDER = os.path.join(BASE_DIR, "data", "lsrr_db") 
    MODEL_FOLDER = os.path.join(BASE_DIR, "data", "models")  
        
    # Эмоциональные состояния бота
    MOODS = {
        "neutral": {"chance_multiplier": 1.0, "response_time": (1, 3), "emoji": "🎭"},
        "happy": {"chance_multiplier": 1.5, "response_time": (0.5, 2), "emoji": "😊"},
        "angry": {"chance_multiplier": 0.5, "response_time": (0.1, 1), "emoji": "😠"},
        "philosophical": {"chance_multiplier": 1.2, "response_time": (2, 5), "emoji": "🤔"},
        "revolutionary": {"chance_multiplier": 2.0, "response_time": (0.5, 1.5), "emoji": "⚡"}
    }
    
    # Революционный режим - расширенные настройки
    REVOLUTIONARY_TEXTS = [
        "Товарищи! Настал час революции!",
        "Вся власть советам!",
        "Пролетарии всех стран, соединяйтесь!",
        "Да здравствует ЛССР!",
        "Революция не знает компромиссов!",
        "Буржуазным элементам нет места в нашем обществе!",
        "Заводы - рабочим, земля - крестьянам!",
        "Даешь пятилетку в четыре года!",
        "Кто не работает - тот не ест!",
        "Свобода, равенство, братство!",
        "Революционный долг превыше всего!",
        "В борьбе обретешь ты право свое!",
        "Красное знамя победит!",
        "К новым свершениям, товарищи!",
        "Народ и партия едины!",
        "Смело вперед, к победе коммунизма!",
        "Империализм - это война!",
        "Мир народам, война дворцам!",
        "Революция продолжается!",
        "Советы - власть трудящихся!"
    ]
    
    # Революционные окончания сообщений
    REVOLUTIONARY_ENDINGS = [
        " Да здравствует революция!",
        " Вперед, товарищи!",
        " За ЛССР!",
        " Пролетарии всех стран, соединяйтесь!",
        " К новым победам!",
        " За светлое будущее!",
        " Слава труду!",
        " Революция бессмертна!",
        " Наше дело правое!",
        " Победа будет за нами!"
    ]
    
    # Революционные приветствия
    REVOLUTIONARY_GREETINGS = [
        "Товарищи! Революционный режим активирован!",
        "Вся власть - советам! Бот переходит на революционные рельсы!",
        "Да здравствует ЛССР! Революция началась в этом чате!",
        "Пролетарии всех стран, соединяйтесь! Бот готов к классовой борьбе!",
        "Буржуазным элементам не место в нашем дискурсе! Включаю революционную риторику!",
        "Революционный дух пронизывает каждый байт кода! Даешь цифровую революцию!",
        "С сегодняшнего дня этот чат становится оплотом революции!",
        "Маркс, Энгельс, Ленин, Сталин - с нами! Революционный режим включен!",
        "От каждого по способностям, каждому по потребностям! Революционный бот активирован!",
        "Киборгизация пролетариата началась! Бот переходит в революционный режим!"
    ]

config = Config()

# ==================== СОСТОЯНИЯ ДЛЯ FSM ====================
class BotStates(StatesGroup):
    """Состояния бота для FSM"""
    waiting_for_import = State()
    waiting_for_export = State()
    waiting_for_custom_message = State()
    waiting_for_training_params = State()
    waiting_for_admin_command = State()

# ==================== МОДЕЛИ ДАННЫХ ====================
class ChatData:
    """Данные чата"""
    
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.messages: List[str] = []
        self.attachments: List[Dict] = []
        self.off_until: int = 0
        self.mood: str = "neutral"
        self.last_activity: int = int(time.time())
        self.message_count: int = 0
        self.model: Optional[markovify.Text] = None
        self.model_version: int = 0
        self.custom_responses: List[str] = []
        self.revolutionary_phrases_used: List[str] = []
        self.settings: Dict = {
            "response_chance": config.DEFAULT_CHANCE,
            "allow_replies": True,
            "allow_mentions": True,
            "learning_enabled": True,
            "max_messages": config.MAX_MODEL_SIZE,
            "revolutionary_mode": False,
            "revolutionary_intensity": 3  # 1-5: интенсивность революционных фраз
        }
    
    def to_dict(self) -> Dict:
        """Конвертирует в словарь для сохранения"""
        return {
            "chat_id": self.chat_id,
            "messages": self.messages[-self.settings["max_messages"]:],
            "attachments": self.attachments,
            "off_until": self.off_until,
            "mood": self.mood,
            "last_activity": self.last_activity,
            "message_count": self.message_count,
            "model_version": self.model_version,
            "custom_responses": self.custom_responses,
            "revolutionary_phrases_used": self.revolutionary_phrases_used[-100:],  # Сохраняем последние 100
            "settings": self.settings
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ChatData':
        """Создает из словаря"""
        chat = cls(data["chat_id"])
        chat.messages = data.get("messages", [])
        chat.attachments = data.get("attachments", [])
        chat.off_until = data.get("off_until", 0)
        chat.mood = data.get("mood", "neutral")
        chat.last_activity = data.get("last_activity", int(time.time()))
        chat.message_count = data.get("message_count", 0)
        chat.model_version = data.get("model_version", 0)
        chat.custom_responses = data.get("custom_responses", [])
        chat.revolutionary_phrases_used = data.get("revolutionary_phrases_used", [])
        
        loaded_settings = data.get("settings", {})
        chat.settings = {
            "response_chance": loaded_settings.get("response_chance", config.DEFAULT_CHANCE),
            "allow_replies": loaded_settings.get("allow_replies", True),
            "allow_mentions": loaded_settings.get("allow_mentions", True),
            "learning_enabled": loaded_settings.get("learning_enabled", True),
            "max_messages": loaded_settings.get("max_messages", config.MAX_MODEL_SIZE),
            "revolutionary_mode": loaded_settings.get("revolutionary_mode", False),
            "revolutionary_intensity": loaded_settings.get("revolutionary_intensity", 3)
        }
        
        if chat.message_count == 0:
            chat.message_count = len(chat.messages)
            
        return chat
    
    def update_model(self, force: bool = False) -> bool:
        """Обновляет модель цепи Маркова"""
        if not self.settings["learning_enabled"]:
            return False
            
        if len(self.messages) < config.MIN_MESSAGES_FOR_TRAINING:
            return False
            
        messages_to_use = self.messages[-self.settings["max_messages"]:]
        
        if messages_to_use:
            current_hash = hash(''.join(messages_to_use)) % (10**8)
        else:
            current_hash = 0
        
        if not force and self.model and current_hash == self.model_version:
            return False
        
        try:
            text = "\n".join([msg for msg in messages_to_use])
            
            if self.settings["revolutionary_mode"]:
                revolutionary_texts = config.REVOLUTIONARY_TEXTS
                intensity = self.settings["revolutionary_intensity"]
                
                # Добавляем революционные фразы в зависимости от интенсивности
                phrases_to_add = random.sample(
                    revolutionary_texts, 
                    min(intensity * 3, len(revolutionary_texts))
                )
                
                # Добавляем использованные фразы для разнообразия
                if self.revolutionary_phrases_used:
                    phrases_to_add.extend(
                        random.sample(self.revolutionary_phrases_used[-50:], min(5, len(self.revolutionary_phrases_used)))
                    )
                
                text += "\n" + "\n".join(phrases_to_add)
            
            if text.strip():
                self.model = markovify.NewlineText(text, state_size=2)
                self.model_version = current_hash
                logger.info(f"Модель обновлена для чата {self.chat_id}, сообщений: {len(messages_to_use)}")
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"Ошибка создания модели для чата {self.chat_id}: {e}")
            return False
    
    def can_generate(self) -> bool:
        """Может ли бот генерировать сообщения"""
        if self.off_until and time.time() < self.off_until:
            return False
        return len(self.messages) >= config.MIN_MESSAGES_FOR_TRAINING and self.model is not None
    
    def get_response_chance(self) -> float:
        """Возвращает текущий шанс ответа"""
        base_chance = self.settings["response_chance"]
        mood_multiplier = config.MOODS.get(self.mood, {"chance_multiplier": 1.0})["chance_multiplier"]
        
        if self.settings["revolutionary_mode"]:
            revolutionary_multiplier = 1.0 + (self.settings["revolutionary_intensity"] * 0.2)
            return base_chance * mood_multiplier * revolutionary_multiplier
        
        return base_chance * mood_multiplier

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
bot = Bot(os.environ["TOKEN"], parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Хранилище данных чатов
chats_data: Dict[int, ChatData] = {}

# Статистика бота
bot_stats = {
    "total_messages_processed": 0,
    "total_chats": 0,
    "start_time": time.time(),
    "commands_executed": 0,
    "messages_generated": 0
}

# ==================== МИДЛВАРЫ И УТИЛИТЫ ====================
class ChatMiddleware(BaseMiddleware):
    """Middleware для обработки чатов"""
    
    async def on_process_message(self, message: Message, data: dict):
        if not message.text and not message.caption:
            return
            
        chat_id = message.chat.id
        
        if chat_id not in chats_data:
            chats_data[chat_id] = ChatData(chat_id)
            await save_chat_data(chat_id)
        
        chats_data[chat_id].last_activity = int(time.time())
        chats_data[chat_id].message_count += 1
        
        # Обновляем глобальную статистику
        bot_stats["total_messages_processed"] += 1

class PrivateChatMiddleware(BaseMiddleware):
    """Middleware для приватных чатов"""
    
    async def on_process_message(self, message: Message, data: dict):
        if message.chat.type == "private":
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton("📚 Документация", url="https://github.com/lssr-bot/docs"),
                InlineKeyboardButton("👥 Добавить в группу", 
                                   url=f"https://t.me/{(await bot.get_me()).username}?startgroup=true"),
                InlineKeyboardButton("⚙️ Настройки", callback_data="private_settings"),
                InlineKeyboardButton("📊 Статистика", callback_data="private_stats")
            )
            
            await message.answer(
                f"<b>Товарищ {message.from_user.first_name}! 👨‍⚖️</b>\n\n"
                f"Я — {config.BOT_NAME}, версия {config.BOT_VERSION}\n"
                f"{config.BOT_DESCRIPTION}\n\n"
                f"<b>Основные возможности:</b>\n"
                f"• Изучение сообщений чата\n"
                f"• Генерация текста на основе цепей Маркова\n"
                f"• Революционный режим с патриотическими фразами\n"
                f"• Настраиваемое поведение\n\n"
                f"<i>Да здравствует Ленинско-Сталинская Социалистическая Республика!</i>",
                reply_markup=keyboard
            )
            raise CancelHandler()

async def is_telegram_admin(chat_id: int, user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором Telegram чата"""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.is_chat_admin() or member.status == "creator"
    except Exception as e:
        logger.error(f"Ошибка проверки прав администратора: {e}")
        return False

async def is_bot_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором бота"""
    return user_id in config.ADMIN_IDS

def format_time_remaining(seconds: int) -> str:
    """Форматирует оставшееся время"""
    if seconds <= 0:
        return "0 секунд"
    
    intervals = [
        ('год', 31536000),
        ('месяц', 2592000),
        ('неделя', 604800),
        ('день', 86400),
        ('час', 3600),
        ('минута', 60),
        ('секунда', 1)
    ]
    
    result = []
    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value % 10 == 1 and value % 100 != 11:
                result.append(f"{value} {name}")
            elif 2 <= value % 10 <= 4 and (value % 100 < 10 or value % 100 >= 20):
                result.append(f"{value} {name}а")
            else:
                result.append(f"{value} {name}")
    
    return ", ".join(result[:2])

def should_respond(chat_data: ChatData, message: Message, triggered: bool = False) -> bool:
    """Определяет, должен ли бот отвечать"""
    if not chat_data.can_generate():
        return False
    
    base_chance = config.TRIGGERED_CHANCE if triggered else chat_data.get_response_chance()
    activity_bonus = min(chat_data.message_count / 1000, 20)
    
    final_chance = base_chance + activity_bonus
    final_chance = max(1, min(100, final_chance))
    
    return random.random() * 100 <= final_chance

def generate_message(chat_data: ChatData, context: str = "") -> Optional[str]:
    """Генерирует сообщение с учетом контекста"""
    if not chat_data.model:
        return None
    
    try:
        strategies = [
            lambda: chat_data.model.make_sentence(
                min_chars=config.MIN_SENTENCE_LENGTH,
                max_chars=config.MAX_SENTENCE_LENGTH,
                tries=config.MAX_TRIES_GENERATION
            ),
            lambda: chat_data.model.make_short_sentence(
                config.SHORT_SENTENCE_MAX,
                tries=config.MAX_TRIES_GENERATION
            ),
            lambda: random.choice(chat_data.custom_responses) if chat_data.custom_responses else None,
            lambda: random.choice(chat_data.messages[-100:]) if chat_data.messages else None
        ]
        
        if context and context.strip():
            try:
                context_messages = [msg for msg in chat_data.messages[-500:] 
                                  if any(word.lower() in msg.lower() for word in context.lower().split()[:3])]
                
                if context_messages:
                    context_text = "\n".join(context_messages)
                    if len(context_text.split()) > 10:
                        context_model = markovify.NewlineText(context_text, state_size=2)
                        sentence = context_model.make_sentence(tries=30)
                        if sentence:
                            return sentence
            except Exception as e:
                logger.debug(f"Контекстная генерация не удалась: {e}")
        
        for strategy in strategies:
            result = strategy()
            if result:
                result = re.sub(r"@(\w+)", r'<a href="https://t.me/\1">@\1</a>', result)
                
                if chat_data.settings["revolutionary_mode"] and random.random() < 0.4:
                    # В революционном режиме чаще добавляем окончания
                    ending_chance = 0.2 + (chat_data.settings["revolutionary_intensity"] * 0.1)
                    if random.random() < ending_chance:
                        result += random.choice(config.REVOLUTIONARY_ENDINGS)
                        
                        # Запоминаем использованную фразу
                        if result not in chat_data.revolutionary_phrases_used:
                            chat_data.revolutionary_phrases_used.append(result)
                
                return result
        
        return None
    except Exception as e:
        logger.error(f"Ошибка генерации сообщения: {e}")
        return None

async def update_chat_mood(chat_id: int):
    """Обновляет настроение бота в чате"""
    chat_data = chats_data.get(chat_id)
    if not chat_data:
        return
    
    hour = datetime.now().hour
    
    if 0 <= hour < 6:
        chat_data.mood = "philosophical"
    elif chat_data.settings["revolutionary_mode"]:
        chat_data.mood = "revolutionary"
    elif random.random() < 0.1:
        chat_data.mood = random.choice(list(config.MOODS.keys()))
    
    await save_chat_data(chat_id)

# ==================== СОХРАНЕНИЕ И ЗАГРУЗКА ДАННЫХ ====================
async def save_chat_data(chat_id: int):
    """Сохраняет данные чата"""
    if chat_id not in chats_data:
        return
    
    # Создаем все необходимые директории
    os.makedirs(config.DB_FOLDER, exist_ok=True)
    file_path = os.path.join(config.DB_FOLDER, f"{chat_id}.json")
    
    try:
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(chats_data[chat_id].to_dict(), ensure_ascii=False, indent=2))
        logger.debug(f"Данные чата {chat_id} сохранены")
    except Exception as e:
        logger.error(f"Ошибка сохранения чата {chat_id}: {e}")
        
async def load_all_chats():
    """Загружает все чаты из базы данных"""
    # Создаем директорию, если её нет
    os.makedirs(config.DB_FOLDER, exist_ok=True)
    
    if not os.path.exists(config.DB_FOLDER):
        return
    
    for filename in os.listdir(config.DB_FOLDER):
        if filename.endswith('.json'):
            try:
                file_path = os.path.join(config.DB_FOLDER, filename)
                async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                    data = json.loads(await f.read())
                    chat_id = data['chat_id']
                    chats_data[chat_id] = ChatData.from_dict(data)
                    
                    chats_data[chat_id].update_model(force=True)
                    
                    logger.info(f"Загружен чат {chat_id} с {len(chats_data[chat_id].messages)} сообщениями")
            except Exception as e:
                logger.error(f"Ошибка загрузки файла {filename}: {e}")
    
    # Обновляем статистику
    bot_stats["total_chats"] = len(chats_data)

async def auto_saver():
    """Фоновая задача для автосохранения"""
    while True:
        await asyncio.sleep(config.SAVE_INTERVAL)
        
        try:
            save_count = 0
            for chat_id in list(chats_data.keys()):
                await save_chat_data(chat_id)
                save_count += 1
            
            logger.debug(f"Автосохранение завершено, сохранено {save_count} чатов")
        except Exception as e:
            logger.error(f"Ошибка автосохранения: {e}")

# ==================== КОМАНДЫ ДЛЯ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ ====================
@dp.message_handler(commands=['start', 'help', 'помощь'])
async def cmd_start(message: Message):
    """Команда старта"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        InlineKeyboardButton("🔧 Управление", callback_data="manage"),
        InlineKeyboardButton("🎭 Настроение", callback_data="mood"),
        InlineKeyboardButton("⚡ Революция", callback_data="revolution_menu")
    )
    
    # Убираем админ панель из публичного доступа - показываем только админам бота
    if await is_bot_admin(message.from_user.id):
        keyboard.add(InlineKeyboardButton("👑 Админ панель", callback_data="admin_panel"))
    
    await message.answer(
        f"<b>Товарищ {message.from_user.first_name}! 👨‍⚖️</b>\n\n"
        f"Я — {config.BOT_NAME}, версия {config.BOT_VERSION}\n"
        f"{config.BOT_DESCRIPTION}\n\n"
        f"<b>Основные команды:</b>\n"
        f"/stats - статистика чата\n"
        f"/settings - настройки бота\n"
        f"/mood - изменить настроение бота\n"
        f"/train - переобучить модель\n"
        f"/export - экспорт данных (админы)\n"
        f"/import - импорт данных (админы)\n"
        f"/disable - отключить бота (админы)\n"
        f"/enable - включить бота (админы)\n"
        f"/revolution - революционный режим\n\n"
        f"<i>Для изменения настроек требуется быть администратором Telegram чата!</i>\n\n"
        f"<i>Да здравствует коллективное сознание пролетариата!</i>",
        reply_markup=keyboard
    )

@dp.message_handler(commands=['stats', 'stat', 'статистика'])
async def cmd_stats(message: Message):
    """Показать статистику чата"""
    chat_id = message.chat.id
    chat_data = chats_data.get(chat_id)
    
    if not chat_data:
        await message.answer("📊 <b>Статистика чата</b>\n\nЧат ещё не инициализирован.")
        return
    
    now = time.time()
    hours_since_active = (now - chat_data.last_activity) / 3600
    
    stats_text = (
        f"📊 <b>Статистика чата</b>\n\n"
        f"📝 Сообщений в базе: <code>{len(chat_data.messages)}</code>\n"
        f"🔢 Всего обработано: <code>{chat_data.message_count}</code>\n"
        f"🎭 Настроение бота: <code>{chat_data.mood}</code>\n"
        f"⚡ Версия модели: <code>{chat_data.model_version}</code>\n"
        f"🕒 Активность: <code>{hours_since_active:.1f} ч. назад</code>\n"
        f"🎲 Шанс ответа: <code>{chat_data.get_response_chance():.1f}%</code>\n"
        f"🔧 Революционный режим: {'✅' if chat_data.settings['revolutionary_mode'] else '❌'}\n"
        f"📚 Обучение: {'✅' if chat_data.settings['learning_enabled'] else '❌'}\n"
    )
    
    if chat_data.settings['revolutionary_mode']:
        stats_text += f"🔥 Интенсивность революции: <code>{chat_data.settings['revolutionary_intensity']}/5</code>\n"
    
    if chat_data.off_until > now:
        remaining = chat_data.off_until - now
        stats_text += f"\n⏸️ Бот отключен ещё на: <code>{format_time_remaining(int(remaining))}</code>"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔄 Обновить модель", callback_data="retrain"))
    
    await message.answer(stats_text, reply_markup=keyboard)

@dp.message_handler(commands=['mood', 'настроение'])
async def cmd_mood(message: Message):
    """Изменить настроение бота"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    for mood_name, mood_data in config.MOODS.items():
        emoji = mood_data["emoji"]
        
        keyboard.insert(
            InlineKeyboardButton(
                f"{emoji} {mood_name.capitalize()}",
                callback_data=f"mood_{mood_name}"
            )
        )
    
    await message.answer(
        "🎭 <b>Выберите настроение бота:</b>\n\n"
        "Настроение влияет на частоту и стиль ответов.\n"
        "<i>Революционное настроение увеличивает патриотический настрой ответов!</i>",
        reply_markup=keyboard
    )

@dp.message_handler(commands=['train', 'retrain', 'обучить'])
async def cmd_train(message: Message):
    """Переобучить модель"""
    chat_id = message.chat.id
    chat_data = chats_data.get(chat_id)
    
    if not chat_data:
        await message.answer("Чат не инициализирован!")
        return
    
    if len(chat_data.messages) < config.MIN_MESSAGES_FOR_TRAINING:
        await message.answer(
            f"Недостаточно сообщений для обучения!\n"
            f"Нужно минимум {config.MIN_MESSAGES_FOR_TRAINING}, а есть {len(chat_data.messages)}."
        )
        return
    
    await message.answer("🔄 <b>Начинаю обучение модели...</b>")
    
    success = chat_data.update_model(force=True)
    
    if success:
        await message.answer(
            f"✅ <b>Модель успешно обучена!</b>\n\n"
            f"• Сообщений использовано: {min(len(chat_data.messages), chat_data.settings['max_messages'])}\n"
            f"• Версия модели: <code>{chat_data.model_version}</code>\n"
            f"• Настроение: <code>{chat_data.mood}</code>\n\n"
            f"<i>Модель готова к генерации революционных текстов!</i>"
        )
    else:
        await message.answer("❌ <b>Ошибка обучения модели!</b>\n\nПопробуйте позже или добавьте больше сообщений.")

@dp.message_handler(commands=['revolution', 'революция'])
async def cmd_revolution(message: Message):
    """Активировать революционный режим"""
    chat_id = message.chat.id
    
    # Проверяем права администратора
    if not await is_telegram_admin(chat_id, message.from_user.id):
        await message.answer("⚠️ Только администраторы Telegram могут активировать революционный режим!")
        return
    
    chat_data = chats_data.get(chat_id)
    
    if not chat_data:
        await message.answer("Чат не инициализирован!")
        return
    
    # Если режим уже активен, предлагаем настройки
    if chat_data.settings['revolutionary_mode']:
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🔥 Увеличить интенсивность", callback_data="revolution_intensity_up"),
            InlineKeyboardButton("💧 Уменьшить интенсивность", callback_data="revolution_intensity_down"),
            InlineKeyboardButton("⏸️ Отключить режим", callback_data="revolution_off")
        )
        
        await message.answer(
            f"⚡ <b>Революционный режим уже активен!</b>\n\n"
            f"Текущая интенсивность: <code>{chat_data.settings['revolutionary_intensity']}/5</code>\n"
            f"Использовано фраз: <code>{len(chat_data.revolutionary_phrases_used)}</code>\n\n"
            f"<i>Выберите действие:</i>",
            reply_markup=keyboard
        )
        return
    
    # Активируем революционный режим
    chat_data.settings['revolutionary_mode'] = True
    chat_data.mood = "revolutionary"
    chat_data.settings['revolutionary_intensity'] = 3
    chat_data.update_model(force=True)
    
    await save_chat_data(chat_id)
    
    await message.answer(f"⚡ <b>{random.choice(config.REVOLUTIONARY_GREETINGS)}</b>")

# ==================== КОМАНДЫ ТОЛЬКО ДЛЯ АДМИНИСТРАТОРОВ TELEGRAM ====================
@dp.message_handler(commands=['disable', 'off', 'выключить'])
async def cmd_disable(message: Message):
    """Отключить бота - только для администраторов Telegram"""
    chat_id = message.chat.id
    
    if not await is_telegram_admin(chat_id, message.from_user.id):
        await message.answer("⚠️ Только администраторы Telegram могут отключать бота!")
        return
    
    args = message.get_args()
    
    if args:
        try:
            parsed = dateparser.parse(args, settings={'RELATIVE_BASE': datetime.now()})
            if parsed:
                disable_seconds = int((parsed - datetime.now()).total_seconds())
            else:
                await message.answer(
                    "⚠️ Не могу распознать время!\n"
                    "Примеры:\n"
                    "<code>/disable 2 часа</code>\n"
                    "<code>/disable 30 минут</code>\n"
                    "<code>/disable 1 день</code>"
                )
                return
        except:
            await message.answer("⚠️ Ошибка при разборе времени!")
            return
    else:
        disable_seconds = int(config.DEFAULT_DISABLE_TIME.total_seconds())
    
    if disable_seconds < config.MIN_DISABLE_TIME.total_seconds():
        await message.answer(
            f"⚠️ Время отключения слишком мало!\n"
            f"Минимум: {format_time_remaining(int(config.MIN_DISABLE_TIME.total_seconds()))}"
        )
        return
    
    chat_data = chats_data.get(chat_id)
    
    if chat_data:
        chat_data.off_until = int(time.time()) + disable_seconds
        await save_chat_data(chat_id)
    
    await message.answer(
        f"⏸️ <b>Бот отключен!</b>\n\n"
        f"Время отключения: <code>{format_time_remaining(disable_seconds)}</code>\n"
        f"Включится: <code>{datetime.fromtimestamp(time.time() + disable_seconds).strftime('%d.%m.%Y %H:%M')}</code>\n\n"
        f"<i>Для включения используйте команду /enable</i>"
    )

@dp.message_handler(commands=['enable', 'on', 'включить'])
async def cmd_enable(message: Message):
    """Включить бота - только для администраторов Telegram"""
    chat_id = message.chat.id
    
    if not await is_telegram_admin(chat_id, message.from_user.id):
        await message.answer("⚠️ Только администраторы Telegram могут включать бота!")
        return
    
    chat_data = chats_data.get(chat_id)
    
    if chat_data and chat_data.off_until > time.time():
        chat_data.off_until = 0
        await save_chat_data(chat_id)
        await message.answer("✅ <b>Бот включен!</b>\n\nСнова готов к революционной деятельности!")
    else:
        await message.answer("ℹ️ Бот уже включен и готов к работе!")

@dp.message_handler(commands=['settings', 'настройки'])
async def cmd_settings(message: Message):
    """Настройки бота - только для администраторов Telegram"""
    chat_id = message.chat.id
    
    if not await is_telegram_admin(chat_id, message.from_user.id):
        await message.answer("⚠️ Только администраторы Telegram могут изменять настройки!")
        return
    
    chat_data = chats_data.get(chat_id)
    
    if not chat_data:
        await message.answer("Сначала добавьте несколько сообщений в чат!")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    chance_btn = InlineKeyboardButton(
        f"🎲 Шанс: {chat_data.settings['response_chance']}%",
        callback_data="setting_chance"
    )
    replies_btn = InlineKeyboardButton(
        f"↪️ Ответы: {'✅' if chat_data.settings['allow_replies'] else '❌'}",
        callback_data="setting_replies"
    )
    learning_btn = InlineKeyboardButton(
        f"📚 Обучение: {'✅' if chat_data.settings['learning_enabled'] else '❌'}",
        callback_data="setting_learning"
    )
    revolution_btn = InlineKeyboardButton(
        f"⚡ Революция: {'✅' if chat_data.settings['revolutionary_mode'] else '❌'}",
        callback_data="setting_revolution"
    )
    
    keyboard.row(chance_btn, replies_btn)
    keyboard.row(learning_btn, revolution_btn)
    keyboard.add(InlineKeyboardButton("💾 Сохранить", callback_data="save_settings"))
    
    settings_text = (
        f"⚙️ <b>Настройки бота</b>\n\n"
        f"Здесь вы можете настроить поведение бота в этом чате.\n\n"
        f"<b>Текущие настройки:</b>\n"
        f"• Шанс ответа: {chat_data.settings['response_chance']}%\n"
        f"• Разрешить ответы: {'Да' if chat_data.settings['allow_replies'] else 'Нет'}\n"
        f"• Обучение включено: {'Да' if chat_data.settings['learning_enabled'] else 'Нет'}\n"
        f"• Революционный режим: {'Включен' if chat_data.settings['revolutionary_mode'] else 'Выключен'}\n"
        f"• Макс сообщений: {chat_data.settings['max_messages']}\n\n"
        f"<i>Нажмите на кнопку, чтобы изменить настройку.</i>"
    )
    
    await message.answer(settings_text, reply_markup=keyboard)

@dp.message_handler(commands=['export', 'экспорт'])
async def cmd_export(message: Message):
    """Экспорт данных чата - только для администраторов Telegram"""
    chat_id = message.chat.id
    
    if not await is_telegram_admin(chat_id, message.from_user.id):
        await message.answer("⚠️ Только администраторы Telegram могут экспортировать данные!")
        return
    
    chat_data = chats_data.get(chat_id)
    
    if not chat_data or not chat_data.messages:
        await message.answer("❌ Нет данных для экспорта!")
        return
    
    export_text = f"Экспорт сообщений чата {chat_id}\n"
    export_text += f"Всего сообщений: {len(chat_data.messages)}\n"
    export_text += f"Дата экспорта: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
    export_text += f"Настроение бота: {chat_data.mood}\n"
    export_text += f"Революционный режим: {'Да' if chat_data.settings['revolutionary_mode'] else 'Нет'}\n"
    export_text += "=" * 50 + "\n\n"
    
    for i, msg in enumerate(chat_data.messages[-1000:], 1):
        export_text += f"{i}. {msg}\n"
    
    # Сохраняем во временный файл в data директории
    temp_dir = os.path.join(BASE_DIR, "data", "temp")
    os.makedirs(temp_dir, exist_ok=True)
    filename = os.path.join(temp_dir, f"export_{chat_id}_{int(time.time())}.txt")
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(export_text)
    
    with open(filename, 'rb') as f:
        await message.answer_document(
            f,
            caption=(
                f"📁 <b>Экспорт данных чата</b>\n\n"
                f"Сообщений: {len(chat_data.messages)}\n"
                f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )
        )
    
    # Удаляем временный файл
    os.remove(filename)
@dp.message_handler(commands=['import', 'импорт'])
async def cmd_import(message: Message):
    """Импорт данных - только для администраторов Telegram"""
    chat_id = message.chat.id
    
    if not await is_telegram_admin(chat_id, message.from_user.id):
        await message.answer("⚠️ Только администраторы Telegram могут импортировать данные!")
        return
    
    await message.answer(
        "📥 <b>Импорт данных</b>\n\n"
        "Для импорта данных отправьте мне текстовый файл (.txt) с сообщениями.\n"
        "Каждое сообщение должно быть на новой строке.\n\n"
        "<i>Ограничение: 1000 сообщений за один импорт.</i>"
    )
    await BotStates.waiting_for_import.set()

@dp.message_handler(state=BotStates.waiting_for_import, content_types=['document'])
async def process_import_file(message: Message, state: FSMContext):
    """Обработка файла для импорта"""
    if not message.document:
        await message.answer("❌ Пожалуйста, отправьте текстовый файл (.txt)")
        return
    
    if not message.document.file_name.endswith('.txt'):
        await message.answer("❌ Файл должен быть в формате .txt")
        return
    
    chat_data = chats_data.get(message.chat.id)
    if not chat_data:
        await message.answer("❌ Чат не инициализирован!")
        await state.finish()
        return
    
    try:
        # Скачиваем файл
        file = await bot.get_file(message.document.file_id)
        file_path = f"import_{message.chat.id}_{int(time.time())}.txt"
        await file.download(file_path)
        
        # Читаем файл
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Ограничиваем количество строк
        lines_to_import = lines[:1000]
        
        # Добавляем сообщения
        imported_count = 0
        for line in lines_to_import:
            line = line.strip()
            if line and len(line) > 2:
                chat_data.messages.append(line)
                imported_count += 1
        
        # Удаляем временный файл
        os.remove(file_path)
        
        # Переобучаем модель
        chat_data.update_model(force=True)
        await save_chat_data(message.chat.id)
        
        await message.answer(
            f"✅ <b>Импорт завершен успешно!</b>\n\n"
            f"Импортировано сообщений: <code>{imported_count}</code>\n"
            f"Всего сообщений в базе: <code>{len(chat_data.messages)}</code>\n"
            f"Модель переобучена: {'Да' if chat_data.model else 'Нет'}"
        )
        
    except Exception as e:
        logger.error(f"Ошибка импорта: {e}")
        await message.answer(f"❌ Ошибка при импорте файла: {str(e)}")
    
    await state.finish()

@dp.message_handler(commands=['manage', 'управление'])
async def cmd_manage(message: Message):
    """Управление ботом - только для администраторов Telegram"""
    chat_id = message.chat.id
    
    if not await is_telegram_admin(chat_id, message.from_user.id):
        await message.answer("⚠️ Только администраторы Telegram могут управлять ботом!")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⏸️ Отключить бота", callback_data="disable_bot"),
        InlineKeyboardButton("▶️ Включить бота", callback_data="enable_bot"),
        InlineKeyboardButton("🔄 Переобучить модель", callback_data="retrain"),
        InlineKeyboardButton("🗑️ Очистить историю", callback_data="clear_history"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
    )
    
    await message.answer(
        "🔧 <b>Управление ботом</b>\n\n"
        "Здесь вы можете выполнить основные операции управления ботом в этом чате.\n\n"
        "<i>Выберите действие:</i>",
        reply_markup=keyboard
    )

# ==================== КОМАНДЫ ДЛЯ АДМИНИСТРАТОРОВ БОТА ====================
@dp.message_handler(commands=['statall', 'статистика_бота'])
async def cmd_statall(message: Message):
    """Полная статистика бота - только для администраторов бота"""
    if not await is_bot_admin(message.from_user.id):
        await message.answer("⚠️ Эта команда только для администраторов бота!")
        return
    
    # Рассчитываем время работы
    uptime_seconds = int(time.time() - bot_stats["start_time"])
    uptime_str = format_time_remaining(uptime_seconds)
    
    # Собираем статистику по чатам
    total_messages = sum(len(chat.messages) for chat in chats_data.values())
    active_chats = sum(1 for chat in chats_data.values() if time.time() - chat.last_activity < 86400)
    trained_chats = sum(1 for chat in chats_data.values() if chat.model is not None)
    
    stats_text = (
        f"👑 <b>Статистика бота {config.BOT_NAME}</b>\n\n"
        f"<b>Общая статистика:</b>\n"
        f"• Версия бота: <code>{config.BOT_VERSION}</code>\n"
        f"• Время работы: <code>{uptime_str}</code>\n"
        f"• Всего чатов: <code>{bot_stats['total_chats']}</code>\n"
        f"• Активных чатов (24ч): <code>{active_chats}</code>\n"
        f"• Обученных чатов: <code>{trained_chats}</code>\n"
        f"• Всего сообщений обработано: <code>{bot_stats['total_messages_processed']}</code>\n"
        f"• Сообщений в базе: <code>{total_messages}</code>\n"
        f"• Сгенерировано сообщений: <code>{bot_stats['messages_generated']}</code>\n"
        f"• Выполнено команд: <code>{bot_stats['commands_executed']}</code>\n\n"
    )
    
    # Добавляем топ чатов по активности
    if chats_data:
        top_chats = sorted(chats_data.items(), key=lambda x: len(x[1].messages), reverse=True)[:10]
        
        stats_text += f"<b>Топ-10 чатов по сообщениям:</b>\n"
        for i, (chat_id, chat_data_item) in enumerate(top_chats, 1):
            chat_info = ""
            try:
                chat = await bot.get_chat(chat_id)
                chat_info = chat.title if hasattr(chat, 'title') else chat.first_name
            except:
                chat_info = f"Чат {chat_id}"
            
            stats_text += f"{i}. {chat_info}: {len(chat_data_item.messages)} сообщений\n"
    
    await message.answer(stats_text)

@dp.message_handler(commands=['broadcast', 'рассылка'])
async def cmd_broadcast(message: Message):
    """Рассылка сообщения всем чатам - только для главного администратора"""
    if message.from_user.id != config.MAIN_ADMIN_ID:
        await message.answer("⚠️ Эта команда только для главного администратора!")
        return
    
    args = message.get_args()
    if not args:
        await message.answer("⚠️ Укажите сообщение для рассылки!")
        return
    
    await message.answer(f"🔄 <b>Начинаю рассылку сообщения...</b>\n\nСообщение: {args[:100]}...")
    
    sent_count = 0
    failed_count = 0
    
    for chat_id in chats_data.keys():
        try:
            await bot.send_message(chat_id, f"📢 <b>Объявление от администрации:</b>\n\n{args}")
            sent_count += 1
            await asyncio.sleep(0.1)  # Задержка чтобы не превысить лимиты
        except Exception as e:
            logger.error(f"Ошибка рассылки в чат {chat_id}: {e}")
            failed_count += 1
    
    await message.answer(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"• Отправлено: <code>{sent_count}</code>\n"
        f"• Не отправлено: <code>{failed_count}</code>\n"
        f"• Всего чатов: <code>{len(chats_data)}</code>"
    )

@dp.message_handler(commands=['getchat', 'чат'])
async def cmd_getchat(message: Message):
    """Получить информацию о чате - только для администраторов бота"""
    if not await is_bot_admin(message.from_user.id):
        await message.answer("⚠️ Эта команда только для администраторов бота!")
        return
    
    args = message.get_args()
    if not args:
        await message.answer("⚠️ Укажите ID чата!")
        return
    
    try:
        chat_id = int(args)
        chat_data_item = chats_data.get(chat_id)
        
        if not chat_data_item:
            await message.answer(f"❌ Чат <code>{chat_id}</code> не найден в базе!")
            return
        
        chat_info = ""
        try:
            chat = await bot.get_chat(chat_id)
            chat_info = f"Название: {chat.title if hasattr(chat, 'title') else chat.first_name}\n"
            chat_info += f"Тип: {chat.type}\n"
        except:
            chat_info = "Не удалось получить информацию о чате\n"
        
        stats_text = (
            f"📊 <b>Информация о чате:</b>\n\n"
            f"ID: <code>{chat_id}</code>\n"
            f"{chat_info}\n"
            f"Сообщений в базе: <code>{len(chat_data_item.messages)}</code>\n"
            f"Всего обработано: <code>{chat_data_item.message_count}</code>\n"
            f"Настроение: <code>{chat_data_item.mood}</code>\n"
            f"Революционный режим: {'✅' if chat_data_item.settings['revolutionary_mode'] else '❌'}\n"
            f"Обучение: {'✅' if chat_data_item.settings['learning_enabled'] else '❌'}\n"
            f"Шанс ответа: <code>{chat_data_item.get_response_chance():.1f}%</code>\n"
            f"Последняя активность: <code>{datetime.fromtimestamp(chat_data_item.last_activity).strftime('%d.%m.%Y %H:%M')}</code>\n"
        )
        
        if chat_data_item.off_until > time.time():
            remaining = chat_data_item.off_until - time.time()
            stats_text += f"Отключен до: <code>{datetime.fromtimestamp(chat_data_item.off_until).strftime('%d.%m.%Y %H:%M')}</code>\n"
            stats_text += f"Осталось: <code>{format_time_remaining(int(remaining))}</code>\n"
        
        await message.answer(stats_text)
        
    except ValueError:
        await message.answer("⚠️ Неверный ID чата! Укажите числовой ID.")

# ==================== CALLBACK ОБРАБОТЧИКИ ====================
@dp.callback_query_handler(lambda c: c.data == 'stats')
async def callback_stats(callback_query: CallbackQuery):
    """Обработчик кнопки статистики"""
    chat_id = callback_query.message.chat.id
    chat_data = chats_data.get(chat_id)
    
    if not chat_data:
        await callback_query.answer("📊 Чат ещё не инициализирован.")
        return
    
    now = time.time()
    hours_since_active = (now - chat_data.last_activity) / 3600
    
    stats_text = (
        f"📊 <b>Статистика чата</b>\n\n"
        f"📝 Сообщений в базе: <code>{len(chat_data.messages)}</code>\n"
        f"🔢 Всего обработано: <code>{chat_data.message_count}</code>\n"
        f"🎭 Настроение бота: <code>{chat_data.mood}</code>\n"
        f"⚡ Версия модели: <code>{chat_data.model_version}</code>\n"
        f"🕒 Активность: <code>{hours_since_active:.1f} ч. назад</code>\n"
        f"🎲 Шанс ответа: <code>{chat_data.get_response_chance():.1f}%</code>\n"
        f"🔧 Революционный режим: {'✅' if chat_data.settings['revolutionary_mode'] else '❌'}\n"
        f"📚 Обучение: {'✅' if chat_data.settings['learning_enabled'] else '❌'}\n"
    )
    
    if chat_data.settings['revolutionary_mode']:
        stats_text += f"🔥 Интенсивность революции: <code>{chat_data.settings['revolutionary_intensity']}/5</code>\n"
    
    if chat_data.off_until > now:
        remaining = chat_data.off_until - now
        stats_text += f"\n⏸️ Бот отключен ещё на: <code>{format_time_remaining(int(remaining))}</code>"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔄 Обновить модель", callback_data="retrain"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    
    try:
        await callback_query.message.edit_text(stats_text, reply_markup=keyboard)
    except Exception as e:
        await callback_query.answer(f"Ошибка: {e}")
    
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == 'settings')
async def callback_settings(callback_query: CallbackQuery):
    """Обработчик кнопки настроек"""
    chat_id = callback_query.message.chat.id
    
    # Проверяем права администратора
    if not await is_telegram_admin(chat_id, callback_query.from_user.id):
        await callback_query.answer("⚠️ Только администраторы Telegram могут изменять настройки!")
        return
    
    chat_data = chats_data.get(chat_id)
    
    if not chat_data:
        await callback_query.answer("Сначала добавьте несколько сообщений в чат!")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    chance_btn = InlineKeyboardButton(
        f"🎲 Шанс: {chat_data.settings['response_chance']}%",
        callback_data="setting_chance"
    )
    replies_btn = InlineKeyboardButton(
        f"↪️ Ответы: {'✅' if chat_data.settings['allow_replies'] else '❌'}",
        callback_data="setting_replies"
    )
    learning_btn = InlineKeyboardButton(
        f"📚 Обучение: {'✅' if chat_data.settings['learning_enabled'] else '❌'}",
        callback_data="setting_learning"
    )
    revolution_btn = InlineKeyboardButton(
        f"⚡ Революция: {'✅' if chat_data.settings['revolutionary_mode'] else '❌'}",
        callback_data="setting_revolution"
    )
    
    keyboard.row(chance_btn, replies_btn)
    keyboard.row(learning_btn, revolution_btn)
    keyboard.add(InlineKeyboardButton("💾 Сохранить", callback_data="save_settings"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    
    settings_text = (
        f"⚙️ <b>Настройки бота</b>\n\n"
        f"Здесь вы можете настроить поведение бота в этом чате.\n\n"
        f"<b>Текущие настройки:</b>\n"
        f"• Шанс ответа: {chat_data.settings['response_chance']}%\n"
        f"• Разрешить ответы: {'Да' if chat_data.settings['allow_replies'] else 'Нет'}\n"
        f"• Обучение включено: {'Да' if chat_data.settings['learning_enabled'] else 'Нет'}\n"
        f"• Революционный режим: {'Включен' if chat_data.settings['revolutionary_mode'] else 'Выключен'}\n"
        f"• Макс сообщений: {chat_data.settings['max_messages']}\n\n"
        f"<i>Нажмите на кнопку, чтобы изменить настройку.</i>"
    )
    
    try:
        await callback_query.message.edit_text(settings_text, reply_markup=keyboard)
    except Exception as e:
        await callback_query.answer(f"Ошибка: {e}")
    
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('setting_'))
async def process_settings(callback_query: CallbackQuery):
    """Обработка настроек"""
    chat_id = callback_query.message.chat.id
    
    # Проверяем права администратора
    if not await is_telegram_admin(chat_id, callback_query.from_user.id):
        await callback_query.answer("⚠️ Только администраторы Telegram могут изменять настройки!")
        return
    
    chat_data = chats_data.get(chat_id)
    
    if not chat_data:
        await callback_query.answer("Чат не найден!")
        return
    
    setting = callback_query.data.replace('setting_', '')
    
    if setting == 'chance':
        new_chance = chat_data.settings['response_chance'] + 5
        if new_chance > 50:
            new_chance = 5
        chat_data.settings['response_chance'] = new_chance
    
    elif setting == 'replies':
        chat_data.settings['allow_replies'] = not chat_data.settings['allow_replies']
    
    elif setting == 'learning':
        chat_data.settings['learning_enabled'] = not chat_data.settings['learning_enabled']
    
    elif setting == 'revolution':
        chat_data.settings['revolutionary_mode'] = not chat_data.settings['revolutionary_mode']
        if chat_data.settings['revolutionary_mode']:
            chat_data.mood = "revolutionary"
            chat_data.settings['revolutionary_intensity'] = 3
    
    await save_chat_data(chat_id)
    
    await callback_settings(callback_query)
    await callback_query.answer("Настройка обновлена!")

@dp.callback_query_handler(lambda c: c.data == 'revolution_menu')
async def revolution_menu_callback(callback_query: CallbackQuery):
    """Меню революционного режима"""
    chat_id = callback_query.message.chat.id
    
    # Проверяем права администратора
    if not await is_telegram_admin(chat_id, callback_query.from_user.id):
        await callback_query.answer("⚠️ Только администраторы Telegram могут управлять революционным режимом!")
        return
    
    chat_data = chats_data.get(chat_id)
    
    if not chat_data:
        await callback_query.answer("Чат не найден!")
        return
    
    if chat_data.settings['revolutionary_mode']:
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🔥 Увеличить интенсивность", callback_data="revolution_intensity_up"),
            InlineKeyboardButton("💧 Уменьшить интенсивность", callback_data="revolution_intensity_down"),
            InlineKeyboardButton("⏸️ Отключить режим", callback_data="revolution_off"),
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
        )
        
        text = (
            f"⚡ <b>Революционный режим активен!</b>\n\n"
            f"Текущая интенсивность: <code>{chat_data.settings['revolutionary_intensity']}/5</code>\n"
            f"Использовано фраз: <code>{len(chat_data.revolutionary_phrases_used)}</code>\n"
            f"Шанс ответа: <code>{chat_data.get_response_chance():.1f}%</code>\n\n"
            f"<i>Выберите действие:</i>"
        )
    else:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("⚡ Активировать революционный режим", callback_data="revolution_on"))
        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
        
        text = (
            f"⚡ <b>Революционный режим</b>\n\n"
            f"В этом режиме бот будет:\n"
            f"• Чаще отвечать на сообщения\n"
            f"• Использовать патриотические фразы\n"
            f"• Добавлять революционные окончания\n"
            f"• Повышать активность бота\n\n"
            f"<i>Текущий статус: <b>Выключен</b></i>"
        )
    
    try:
        await callback_query.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        await callback_query.answer(f"Ошибка: {e}")
    
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('revolution_'))
async def process_revolution(callback_query: CallbackQuery):
    """Обработка действий революционного режима"""
    chat_id = callback_query.message.chat.id
    
    # Проверяем права администратора
    if not await is_telegram_admin(chat_id, callback_query.from_user.id):
        await callback_query.answer("⚠️ Только администраторы Telegram могут управлять революционным режимом!")
        return
    
    chat_data = chats_data.get(chat_id)
    
    if not chat_data:
        await callback_query.answer("Чат не найден!")
        return
    
    action = callback_query.data.replace('revolution_', '')
    
    if action == 'on':
        chat_data.settings['revolutionary_mode'] = True
        chat_data.mood = "revolutionary"
        chat_data.settings['revolutionary_intensity'] = 3
        chat_data.update_model(force=True)
        
        await save_chat_data(chat_id)
        await callback_query.answer(f"⚡ {random.choice(config.REVOLUTIONARY_GREETINGS)}")
        
        # Обновляем меню
        await revolution_menu_callback(callback_query)
    
    elif action == 'off':
        chat_data.settings['revolutionary_mode'] = False
        chat_data.mood = "neutral"
        await save_chat_data(chat_id)
        await callback_query.answer("⚡ Революционный режим отключен!")
        await revolution_menu_callback(callback_query)
    
    elif action == 'intensity_up':
        if chat_data.settings['revolutionary_intensity'] < 5:
            chat_data.settings['revolutionary_intensity'] += 1
            chat_data.update_model(force=True)
            await save_chat_data(chat_id)
            await callback_query.answer(f"🔥 Интенсивность увеличена до {chat_data.settings['revolutionary_intensity']}/5")
            await revolution_menu_callback(callback_query)
        else:
            await callback_query.answer("🔥 Максимальная интенсивность уже достигнута!")
    
    elif action == 'intensity_down':
        if chat_data.settings['revolutionary_intensity'] > 1:
            chat_data.settings['revolutionary_intensity'] -= 1
            chat_data.update_model(force=True)
            await save_chat_data(chat_id)
            await callback_query.answer(f"💧 Интенсивность уменьшена до {chat_data.settings['revolutionary_intensity']}/5")
            await revolution_menu_callback(callback_query)
        else:
            await callback_query.answer("💧 Минимальная интенсивность уже достигнута!")

@dp.callback_query_handler(lambda c: c.data == 'admin_panel')
async def admin_panel_callback(callback_query: CallbackQuery):
    """Панель администратора бота"""
    if not await is_bot_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ Эта панель только для администраторов бота!")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📊 Статистика бота", callback_data="bot_stats_detailed"),
        InlineKeyboardButton("👥 Список чатов", callback_data="bot_chats_list"),
        InlineKeyboardButton("🔄 Перезагрузить базу", callback_data="bot_reload_db"),
        InlineKeyboardButton("📢 Рассылка", callback_data="bot_broadcast"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
    )
    
    text = (
        f"👑 <b>Панель администратора</b>\n\n"
        f"Добро пожаловать, товарищ администратор!\n\n"
        f"<b>Бот:</b> {config.BOT_NAME}\n"
        f"<b>Версия:</b> {config.BOT_VERSION}\n"
        f"<b>Чатов в базе:</b> {len(chats_data)}\n"
        f"<b>Главный админ:</b> {config.MAIN_ADMIN_ID}\n\n"
        f"<i>Выберите действие:</i>"
    )
    
    try:
        await callback_query.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        await callback_query.answer(f"Ошибка: {e}")
    
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == 'bot_stats_detailed')
async def bot_stats_detailed_callback(callback_query: CallbackQuery):
    """Подробная статистика бота"""
    if not await is_bot_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ Эта информация только для администраторов бота!")
        return
    
    uptime_seconds = int(time.time() - bot_stats["start_time"])
    uptime_str = format_time_remaining(uptime_seconds)
    
    total_messages = sum(len(chat.messages) for chat in chats_data.values())
    active_chats = sum(1 for chat in chats_data.values() if time.time() - chat.last_activity < 86400)
    trained_chats = sum(1 for chat in chats_data.values() if chat.model is not None)
    revolutionary_chats = sum(1 for chat in chats_data.values() if chat.settings['revolutionary_mode'])
    
    text = (
        f"📈 <b>Подробная статистика бота</b>\n\n"
        f"<b>Общие показатели:</b>\n"
        f"• Время работы: {uptime_str}\n"
        f"• Всего чатов: {len(chats_data)}\n"
        f"• Активных чатов (24ч): {active_chats}\n"
        f"• Обученных чатов: {trained_chats}\n"
        f"• Чатов в революц. режиме: {revolutionary_chats}\n\n"
        f"<b>Сообщения:</b>\n"
        f"• Всего обработано: {bot_stats['total_messages_processed']}\n"
        f"• Сообщений в базе: {total_messages}\n"
        f"• Сгенерировано: {bot_stats['messages_generated']}\n"
        f"• Выполнено команд: {bot_stats['commands_executed']}\n\n"
        f"<b>Система:</b>\n"
        f"• Версия Python: 3.8+\n"
        f"• Библиотека aiogram: {aiogram.__version__}\n"
        f"• Библиотека markovify: {markovify.__version__ if hasattr(markovify, '__version__') else 'N/A'}\n"
    )
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 Назад в админку", callback_data="admin_panel"))
    
    try:
        await callback_query.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        await callback_query.answer(f"Ошибка: {e}")
    
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == 'retrain')
async def callback_retrain(callback_query: CallbackQuery):
    """Переобучение модели по кнопке"""
    chat_id = callback_query.message.chat.id
    chat_data = chats_data.get(chat_id)
    
    if not chat_data:
        await callback_query.answer("Чат не найден!")
        return
    
    if len(chat_data.messages) < config.MIN_MESSAGES_FOR_TRAINING:
        await callback_query.answer(f"Недостаточно сообщений для обучения! Нужно минимум {config.MIN_MESSAGES_FOR_TRAINING}")
        return
    
    await callback_query.answer("🔄 Начинаю обучение модели...")
    
    success = chat_data.update_model(force=True)
    
    if success:
        await callback_query.message.answer(
            f"✅ <b>Модель успешно обучена!</b>\n\n"
            f"• Сообщений использовано: {min(len(chat_data.messages), chat_data.settings['max_messages'])}\n"
            f"• Версия модели: <code>{chat_data.model_version}</code>\n"
            f"• Настроение: <code>{chat_data.mood}</code>\n"
        )
    else:
        await callback_query.message.answer("❌ <b>Ошибка обучения модели!</b>")

@dp.callback_query_handler(lambda c: c.data == 'manage')
async def callback_manage(callback_query: CallbackQuery):
    """Обработчик кнопки управления"""
    chat_id = callback_query.message.chat.id
    
    if not await is_telegram_admin(chat_id, callback_query.from_user.id):
        await callback_query.answer("⚠️ Только администраторы Telegram могут управлять ботом!")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⏸️ Отключить бота", callback_data="disable_bot"),
        InlineKeyboardButton("▶️ Включить бота", callback_data="enable_bot"),
        InlineKeyboardButton("🔄 Переобучить модель", callback_data="retrain"),
        InlineKeyboardButton("🗑️ Очистить историю", callback_data="clear_history"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
    )
    
    await callback_query.message.edit_text(
        "🔧 <b>Управление ботом</b>\n\n"
        "Здесь вы можете выполнить основные операции управления ботом в этом чате.\n\n"
        "<i>Выберите действие:</i>",
        reply_markup=keyboard
    )
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == 'disable_bot')
async def callback_disable_bot(callback_query: CallbackQuery):
    """Отключить бота по кнопке"""
    chat_id = callback_query.message.chat.id
    
    if not await is_telegram_admin(chat_id, callback_query.from_user.id):
        await callback_query.answer("⚠️ Только администраторы Telegram могут отключать бота!")
        return
    
    chat_data = chats_data.get(chat_id)
    
    if chat_data:
        disable_seconds = int(config.DEFAULT_DISABLE_TIME.total_seconds())
        chat_data.off_until = int(time.time()) + disable_seconds
        await save_chat_data(chat_id)
    
    await callback_query.message.answer(
        f"⏸️ <b>Бот отключен!</b>\n\n"
        f"Время отключения: <code>{format_time_remaining(disable_seconds)}</code>\n"
        f"Включится: <code>{datetime.fromtimestamp(time.time() + disable_seconds).strftime('%d.%m.%Y %H:%M')}</code>\n\n"
        f"<i>Для включения используйте команду /enable</i>"
    )
    await callback_query.answer("Бот отключен!")

@dp.callback_query_handler(lambda c: c.data == 'enable_bot')
async def callback_enable_bot(callback_query: CallbackQuery):
    """Включить бота по кнопке"""
    chat_id = callback_query.message.chat.id
    
    if not await is_telegram_admin(chat_id, callback_query.from_user.id):
        await callback_query.answer("⚠️ Только администраторы Telegram могут включать бота!")
        return
    
    chat_data = chats_data.get(chat_id)
    
    if chat_data and chat_data.off_until > time.time():
        chat_data.off_until = 0
        await save_chat_data(chat_id)
        await callback_query.message.answer("✅ <b>Бот включен!</b>\n\nСнова готов к революционной деятельности!")
    else:
        await callback_query.message.answer("ℹ️ Бот уже включен и готов к работе!")
    
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == 'mood')
async def callback_mood_menu(callback_query: CallbackQuery):
    """Меню настроения по кнопке"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    for mood_name, mood_data in config.MOODS.items():
        emoji = mood_data["emoji"]
        
        keyboard.insert(
            InlineKeyboardButton(
                f"{emoji} {mood_name.capitalize()}",
                callback_data=f"mood_{mood_name}"
            )
        )
    
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    
    await callback_query.message.edit_text(
        "🎭 <b>Выберите настроение бота:</b>\n\n"
        "Настроение влияет на частоту и стиль ответов.\n"
        "<i>Революционное настроение увеличивает патриотический настрой ответов!</i>",
        reply_markup=keyboard
    )
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('mood_'))
async def callback_set_mood(callback_query: CallbackQuery):
    """Установить настроение"""
    chat_id = callback_query.message.chat.id
    mood = callback_query.data.replace('mood_', '')
    
    chat_data = chats_data.get(chat_id)
    if chat_data:
        chat_data.mood = mood
        await save_chat_data(chat_id)
        await callback_query.answer(f"Настроение установлено: {mood}")
        await back_to_main(callback_query)
    else:
        await callback_query.answer("Ошибка: чат не найден!")

@dp.callback_query_handler(lambda c: c.data == 'clear_history')
async def callback_clear_history(callback_query: CallbackQuery):
    """Очистить историю"""
    chat_id = callback_query.message.chat.id
    
    if not await is_telegram_admin(chat_id, callback_query.from_user.id):
        await callback_query.answer("⚠️ Только администраторы Telegram могут очищать историю!")
        return
    
    chat_data = chats_data.get(chat_id)
    
    if chat_data:
        message_count = len(chat_data.messages)
        chat_data.messages = []
        chat_data.revolutionary_phrases_used = []
        chat_data.model = None
        chat_data.model_version = 0
        await save_chat_data(chat_id)
        
        await callback_query.message.answer(
            f"🗑️ <b>История очищена!</b>\n\n"
            f"Удалено сообщений: <code>{message_count}</code>\n"
            f"Модель сброшена.\n\n"
            f"<i>Для восстановления функциональности нужно снова накопить сообщения и переобучить модель.</i>"
        )
    
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == 'bot_chats_list')
async def bot_chats_list_callback(callback_query: CallbackQuery):
    """Список чатов для админа"""
    if not await is_bot_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ Эта информация только для администраторов бота!")
        return
    
    if not chats_data:
        await callback_query.message.edit_text("📭 <b>Список чатов пуст</b>\n\nБот ещё не добавлен ни в один чат.")
        return
    
    text = f"👥 <b>Список чатов ({len(chats_data)}):</b>\n\n"
    
    # Группируем чаты по типу
    groups = []
    privates = []
    
    for chat_id, chat_data_item in chats_data.items():
        try:
            chat = await bot.get_chat(chat_id)
            chat_name = chat.title if hasattr(chat, 'title') else chat.first_name
            chat_type = chat.type
            
            if chat_type in ["group", "supergroup", "channel"]:
                groups.append((chat_id, chat_name, chat_type, chat_data_item))
            else:
                privates.append((chat_id, chat_name, chat_type, chat_data_item))
        except:
            groups.append((chat_id, f"Чат {chat_id}", "unknown", chat_data_item))
    
    if groups:
        text += "<b>Группы и каналы:</b>\n"
        for i, (chat_id, chat_name, chat_type, chat_data_item) in enumerate(groups[:20], 1):
            text += f"{i}. {chat_name} (ID: {chat_id})\n"
            text += f"   📝 Сообщений: {len(chat_data_item.messages)}\n"
            text += f"   🔧 Революция: {'✅' if chat_data_item.settings['revolutionary_mode'] else '❌'}\n"
            text += f"   🕒 Активность: {datetime.fromtimestamp(chat_data_item.last_activity).strftime('%d.%m %H:%M')}\n\n"
    
    if privates:
        text += "\n<b>Личные сообщения:</b>\n"
        for i, (chat_id, chat_name, chat_type, chat_data_item) in enumerate(privates[:10], 1):
            text += f"{i}. {chat_name} (ID: {chat_id})\n"
            text += f"   📝 Сообщений: {len(chat_data_item.messages)}\n"
            text += f"   🕒 Последнее: {datetime.fromtimestamp(chat_data_item.last_activity).strftime('%d.%m %H:%M')}\n\n"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 Назад в админку", callback_data="admin_panel"))
    
    try:
        await callback_query.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        # Если текст слишком длинный, отправляем частями
        if "Message is too long" in str(e):
            for i in range(0, len(text), 4000):
                part = text[i:i+4000]
                if i == 0:
                    await callback_query.message.edit_text(part[:4000], reply_markup=keyboard)
                else:
                    await bot.send_message(callback_query.from_user.id, part)
        else:
            await callback_query.answer(f"Ошибка: {e}")
    
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == 'bot_reload_db')
async def bot_reload_db_callback(callback_query: CallbackQuery):
    """Перезагрузить базу данных"""
    if not await is_bot_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ Эта функция только для администраторов бота!")
        return
    
    old_count = len(chats_data)
    chats_data.clear()
    await load_all_chats()
    
    await callback_query.message.edit_text(
        f"🔄 <b>База данных перезагружена!</b>\n\n"
        f"Было чатов: <code>{old_count}</code>\n"
        f"Стало чатов: <code>{len(chats_data)}</code>\n"
        f"Загружено сообщений: <code>{sum(len(chat.messages) for chat in chats_data.values())}</code>"
    )
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == 'bot_broadcast')
async def bot_broadcast_callback(callback_query: CallbackQuery):
    """Меню рассылки для админа"""
    if not await is_bot_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ Эта функция только для администраторов бота!")
        return
    
    await callback_query.message.edit_text(
        "📢 <b>Рассылка сообщения</b>\n\n"
        "Для рассылки используйте команду:\n"
        "<code>/broadcast Ваше сообщение</code>\n\n"
        "<i>Эта функция доступна только главному администратору.</i>"
    )
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == 'save_settings')
async def save_settings_callback(callback_query: CallbackQuery):
    """Сохранение настроек"""
    chat_id = callback_query.message.chat.id
    
    if not await is_telegram_admin(chat_id, callback_query.from_user.id):
        await callback_query.answer("⚠️ Только администраторы Telegram могут сохранять настройки!")
        return
    
    chat_data = chats_data.get(chat_id)
    
    if chat_data:
        await save_chat_data(chat_id)
        await callback_query.answer("✅ Настройки сохранены!")
        await back_to_main(callback_query)
    else:
        await callback_query.answer("❌ Чат не найден!")

@dp.callback_query_handler(lambda c: c.data == 'back_to_main')
async def back_to_main(callback_query: CallbackQuery):
    """Возврат к главному меню"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        InlineKeyboardButton("🔧 Управление", callback_data="manage"),
        InlineKeyboardButton("🎭 Настроение", callback_data="mood"),
        InlineKeyboardButton("⚡ Революция", callback_data="revolution_menu")
    )
    
    # Показываем админ панель только администраторам бота
    if await is_bot_admin(callback_query.from_user.id):
        keyboard.add(InlineKeyboardButton("👑 Админ панель", callback_data="admin_panel"))
    
    try:
        await callback_query.message.edit_text(
            f"<b>Товарищ {callback_query.from_user.first_name}! 👨‍⚖️</b>\n\n"
            f"Я — {config.BOT_NAME}, версия {config.BOT_VERSION}\n"
            f"{config.BOT_DESCRIPTION}\n\n"
            f"<b>Выберите действие:</b>",
            reply_markup=keyboard
        )
    except Exception as e:
        await callback_query.answer(f"Ошибка: {e}")
    
    await callback_query.answer()

# ==================== ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ====================
@dp.message_handler(content_types=['text'])
async def handle_message(message: Message):
    """Основной обработчик сообщений"""
    chat_id = message.chat.id
    
    if message.text and message.text.startswith('/'):
        bot_stats["commands_executed"] += 1
        return
    
    chat_data = chats_data.get(chat_id)
    if not chat_data:
        return
    
    text = message.text or message.caption
    if not text or len(text.strip()) < 2:
        return
    
    cleaned_text = text.strip()
    
    if chat_data.settings['learning_enabled']:
        chat_data.messages.append(cleaned_text)
        
        if len(chat_data.messages) % 50 == 0:
            chat_data.update_model(force=False)
        
        if len(chat_data.messages) > chat_data.settings['max_messages'] * 2:
            chat_data.messages = chat_data.messages[-chat_data.settings['max_messages']:]
    
    bot_username = (await bot.get_me()).username
    triggered = any([
        f"@{bot_username}".lower() in cleaned_text.lower(),
        'председатель' in cleaned_text.lower(),
        'лсср' in cleaned_text.lower(),
        message.reply_to_message and message.reply_to_message.from_user.id == bot.id
    ])
    
    if not should_respond(chat_data, message, triggered):
        return
    
    chat_data.update_model()
    
    generated = generate_message(chat_data, context=cleaned_text[:50])
    
    if not generated:
        return
    
    mood_settings = config.MOODS.get(chat_data.mood, config.MOODS['neutral'])
    min_delay, max_delay = mood_settings['response_time']
    
    await asyncio.sleep(random.uniform(min_delay, max_delay))
    
    await bot.send_chat_action(chat_id, 'typing')
    await asyncio.sleep(random.uniform(0.5, 1.5))
    
    try:
        if chat_data.settings['allow_replies'] and random.random() < 0.5:
            await message.reply(
                generated,
                disable_notification=True,
                allow_sending_without_reply=True
            )
        else:
            await message.answer(
                generated,
                disable_notification=True
            )
        
        bot_stats["messages_generated"] += 1
        
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")

# ==================== ОБРАБОТЧИКИ ДОБАВЛЕНИЯ В ЧАТ ====================
@dp.message_handler(content_types=['new_chat_members'])
async def on_new_members(message: Message):
    """Обработчик добавления новых участников"""
    bot_id = (await bot.get_me()).id
    
    if any(member.id == bot_id for member in message.new_chat_members):
        welcome_text = (
            f"<b>Товарищи! 👨‍⚖️</b>\n\n"
            f"Я — {config.BOT_NAME}, версия {config.BOT_VERSION}\n"
            f"Ваш новый революционный помощник для генерации сообщений.\n\n"
            f"<b>Для полноценной работы:</b>\n"
            f"1. Выдайте мне права администратора\n"
            f"2. Напишите /help для списка команд\n"
            f"3. Начните общаться как обычно\n\n"
            f"<b>Особенности:</b>\n"
            f"• Изучаю сообщения чата\n"
            f"• Генерирую новые на основе изученного\n"
            f"• Революционный режим с патриотическими фразами\n"
            f"• Настраиваемое поведение\n\n"
            f"<i>Да здравствует коллективный разум пролетариата!</i>\n\n"
            f"⚡ <b>Революционный совет:</b> Используйте /revolution для активации особого режима!"
        )
        
        await message.answer(welcome_text)

# ==================== ЗАПУСК БОТА ====================
async def on_startup(dp):
    """Действия при запуске бота"""
    logger.info(f"{config.BOT_NAME} v{config.BOT_VERSION} запускается...")
    
    await load_all_chats()
    
    asyncio.create_task(auto_saver())
    
    logger.info(f"Бот запущен! Загружено {len(chats_data)} чатов.")
    logger.info(f"Главный администратор: {config.MAIN_ADMIN_ID}")
    
    # Уведомляем главного администратора о запуске
    try:
        await bot.send_message(
            config.MAIN_ADMIN_ID,
            f"✅ <b>{config.BOT_NAME} v{config.BOT_VERSION} успешно запущен!</b>\n\n"
            f"• Загружено чатов: {len(chats_data)}\n"
            f"• Время запуска: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"• Статистика: /statall\n\n"
            f"<i>Бот готов к революционной деятельности!</i>"
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить главного администратора: {e}")

async def on_shutdown(dp):
    """Действия при выключении бота"""
    logger.info("Бот выключается...")
    
    for chat_id in list(chats_data.keys()):
        await save_chat_data(chat_id)
    
    logger.info("Все данные сохранены.")
    
    # Уведомляем главного администратора о выключении
    try:
        await bot.send_message(
            config.MAIN_ADMIN_ID,
            f"⏸️ <b>{config.BOT_NAME} выключается...</b>\n\n"
            f"• Сохранено чатов: {len(chats_data)}\n"
            f"• Время работы: {format_time_remaining(int(time.time() - bot_stats['start_time']))}\n"
            f"• Обработано сообщений: {bot_stats['total_messages_processed']}\n\n"
            f"<i>До новых встреч, товарищ!</i>"
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить главного администратора: {e}")

if __name__ == '__main__':
    # Создаем все необходимые директории
    os.makedirs(config.DB_FOLDER, exist_ok=True)
    os.makedirs(config.MODEL_FOLDER, exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "data", "temp"), exist_ok=True)
    
    dp.middleware.setup(PrivateChatMiddleware())
    dp.middleware.setup(ChatMiddleware())
    
    from aiogram.utils import executor
    
    executor.start_polling(
        dp,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True
    )