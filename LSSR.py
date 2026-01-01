# coding: utf-8
# Председатель ЛССР - Бот для генерации сообщений на основе цепей Маркова

import asyncio
from datetime import datetime, timedelta
import json
import os
import random
import re
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

# Загружаем конфигурацию
dotenv.load_dotenv()

# ==================== КОНФИГУРАЦИЯ ====================
class Config:
    """Конфигурация бота с настройками по умолчанию"""
    
    # Основные настройки
    BOT_NAME = "Председатель ЛССР"
    DEFAULT_CHANCE = 8  # Базовый шанс ответа в процентах
    TRIGGERED_CHANCE = 80  # Шанс при упоминании бота
    MIN_MESSAGES_FOR_TRAINING = 50  # Минимальное кол-во сообщений для обучения
    MAX_MODEL_SIZE = 20000  # Максимальное количество сообщений в модели
    SAVE_INTERVAL = 300  # Интервал автосохранения в секундах
    
    # Настройки генерации
    MIN_SENTENCE_LENGTH = 10
    MAX_SENTENCE_LENGTH = 500
    SHORT_SENTENCE_MAX = 50
    MAX_TRIES_GENERATION = 100
    
    # Настройки времени
    DEFAULT_DISABLE_TIME = timedelta(days=7)  # По умолчанию отключаем на неделю
    MIN_DISABLE_TIME = timedelta(minutes=5)   # Минимальное время отключения
    
    # Настройки базы данных
    DB_FOLDER = "lsrr_db"
    MODEL_FOLDER = "models"
    
    # Эмоциональные состояния бота
    MOODS = {
        "neutral": {"chance_multiplier": 1.0, "response_time": (1, 3)},
        "happy": {"chance_multiplier": 1.5, "response_time": (0.5, 2)},
        "angry": {"chance_multiplier": 0.5, "response_time": (0.1, 1)},
        "philosophical": {"chance_multiplier": 1.2, "response_time": (2, 5)},
        "revolutionary": {"chance_multiplier": 2.0, "response_time": (0.5, 1.5)}
    }

config = Config()

# ==================== СОСТОЯНИЯ ДЛЯ FSM ====================
class BotStates(StatesGroup):
    """Состояния бота для FSM"""
    waiting_for_import = State()
    waiting_for_export = State()
    waiting_for_custom_message = State()
    waiting_for_training_params = State()

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
        self.settings: Dict = {
            "response_chance": config.DEFAULT_CHANCE,
            "allow_replies": True,
            "allow_mentions": True,
            "learning_enabled": True,
            "max_messages": config.MAX_MODEL_SIZE,
            "revolutionary_mode": False  # Специальный режим для важных обсуждений
        }
    
    def to_dict(self) -> Dict:
        """Конвертирует в словарь для сохранения"""
        return {
            "chat_id": self.chat_id,
            "messages": self.messages[-config.settings["max_messages"]:],
            "attachments": self.attachments,
            "off_until": self.off_until,
            "mood": self.mood,
            "last_activity": self.last_activity,
            "message_count": self.message_count,
            "model_version": self.model_version,
            "custom_responses": self.custom_responses,
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
        chat.message_count = data.get("message_count", len(chat.messages))
        chat.model_version = data.get("model_version", 0)
        chat.custom_responses = data.get("custom_responses", [])
        chat.settings = data.get("settings", {
            "response_chance": config.DEFAULT_CHANCE,
            "allow_replies": True,
            "allow_mentions": True,
            "learning_enabled": True,
            "max_messages": config.MAX_MODEL_SIZE,
            "revolutionary_mode": False
        })
        return chat
    
    def update_model(self, force: bool = False) -> bool:
        """Обновляет модель цепи Маркова"""
        if not self.settings["learning_enabled"]:
            return False
            
        if len(self.messages) < config.MIN_MESSAGES_FOR_TRAINING:
            return False
            
        # Проверяем, нужно ли обновлять модель
        messages_to_use = self.messages[-self.settings["max_messages"]:]
        current_hash = hash(tuple(messages_to_use))
        
        if not force and self.model and current_hash == self.model_version:
            return False
        
        try:
            # Создаем модель с учетом настроек
            text = "\n".join([msg.lower() for msg in messages_to_use])
            
            if self.settings["revolutionary_mode"]:
                # В революционном режиме добавляем специальные фразы
                revolutionary_texts = [
                    "Товарищи! Настал час революции!",
                    "Вся власть советам!",
                    "Пролетарии всех стран, соединяйтесь!",
                    "Да здравствует ЛССР!",
                    "Революция не знает компромиссов!",
                    "Буржуазным элементам нет места в нашем обществе!"
                ]
                text += "\n" + "\n".join(revolutionary_texts)
            
            self.model = markovify.NewlineText(text, state_size=2)
            self.model_version = current_hash
            return True
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
        return base_chance * mood_multiplier

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
bot = Bot(os.environ["TOKEN"], parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Хранилище данных чатов
chats_data: Dict[int, ChatData] = {}

# ==================== МИДЛВАРЫ ====================
class ChatMiddleware(BaseMiddleware):
    """Middleware для обработки чатов"""
    
    async def on_process_message(self, message: Message, data: dict):
        # Игнорируем служебные сообщения
        if not message.text and not message.caption:
            return
            
        # Инициализируем данные чата, если их нет
        chat_id = message.chat.id
        
        if chat_id not in chats_data:
            chats_data[chat_id] = ChatData(chat_id)
            await save_chat_data(chat_id)
        
        # Обновляем активность
        chats_data[chat_id].last_activity = int(time.time())
        chats_data[chat_id].message_count += 1

class PrivateChatMiddleware(BaseMiddleware):
    """Middleware для приватных чатов"""
    
    async def on_process_message(self, message: Message, data: dict):
        if message.chat.type == "private":
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton("📚 Документация", url="https://example.com/docs"),
                InlineKeyboardButton("👥 Добавить в группу", 
                                   url=f"https://t.me/{(await bot.get_me()).username}?startgroup=true")
            )
            
            await message.answer(
                f"<b>Товарищ {message.from_user.first_name}! 👨‍⚖️</b>\n\n"
                f"Я — {config.BOT_NAME}, революционный бот для генерации сообщений.\n"
                f"Для работы добавьте меня в группу и выдайте права администратора.\n\n"
                f"<i>Да здравствует Ленинско-Сталинская Социалистическая Республика!</i>",
                reply_markup=keyboard
            )
            raise CancelHandler()

# ==================== УТИЛИТЫ ====================
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
    
    # Базовый шанс
    base_chance = config.TRIGGERED_CHANCE if triggered else chat_data.get_response_chance()
    
    # Увеличиваем шанс при высокой активности
    activity_bonus = min(chat_data.message_count / 1000, 20)  # До +20%
    
    # Уменьшаем шанс, если бот недавно отвечал
    recency_penalty = 0
    
    final_chance = base_chance + activity_bonus - recency_penalty
    final_chance = max(1, min(100, final_chance))
    
    return random.random() * 100 <= final_chance

def generate_message(chat_data: ChatData, context: str = "") -> Optional[str]:
    """Генерирует сообщение с учетом контекста"""
    if not chat_data.model:
        return None
    
    try:
        # Пробуем разные стратегии генерации
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
        
        # Если есть контекст, пробуем сгенерировать на его основе
        if context:
            try:
                context_model = markovify.NewlineText("\n".join(
                    [msg for msg in chat_data.messages if context.lower() in msg.lower()]
                ))
                if context_model:
                    sentence = context_model.make_sentence(tries=50)
                    if sentence:
                        return sentence
            except:
                pass
        
        # Пробуем стратегии по очереди
        for strategy in strategies:
            result = strategy()
            if result:
                # Обрабатываем упоминания
                result = re.sub(r"@(\w+)", r'<a href="https://t.me/\1">@\1</a>', result)
                
                # Добавляем эмоциональную окраску в зависимости от настроения
                if chat_data.mood == "revolutionary":
                    revolutionary_endings = [
                        " Да здравствует революция!",
                        " Вперед, товарищи!",
                        " За ЛССР!",
                        " Пролетарии всех стран, соединяйтесь!"
                    ]
                    if random.random() < 0.3:
                        result += random.choice(revolutionary_endings)
                
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
    
    # Определяем настроение на основе активности и времени
    hour = datetime.now().hour
    
    if 0 <= hour < 6:
        chat_data.mood = "philosophical"  # Ночью бот философствует
    elif chat_data.settings["revolutionary_mode"]:
        chat_data.mood = "revolutionary"
    elif random.random() < 0.1:
        chat_data.mood = random.choice(list(config.MOODS.keys()))
    
    # Сохраняем изменения
    await save_chat_data(chat_id)

# ==================== СОХРАНЕНИЕ И ЗАГРУЗКА ДАННЫХ ====================
async def save_chat_data(chat_id: int):
    """Сохраняет данные чата"""
    if chat_id not in chats_data:
        return
    
    os.makedirs(config.DB_FOLDER, exist_ok=True)
    file_path = os.path.join(config.DB_FOLDER, f"{chat_id}.json")
    
    try:
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(chats_data[chat_id].to_dict(), ensure_ascii=False, indent=2))
    except Exception as e:
        logger.error(f"Ошибка сохранения чата {chat_id}: {e}")

async def load_all_chats():
    """Загружает все чаты из базы данных"""
    if not os.path.exists(config.DB_FOLDER):
        os.makedirs(config.DB_FOLDER, exist_ok=True)
        return
    
    for filename in os.listdir(config.DB_FOLDER):
        if filename.endswith('.json'):
            try:
                file_path = os.path.join(config.DB_FOLDER, filename)
                async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                    data = json.loads(await f.read())
                    chat_id = data['chat_id']
                    chats_data[chat_id] = ChatData.from_dict(data)
                    
                    # Обновляем модель
                    chats_data[chat_id].update_model(force=True)
                    
                    logger.info(f"Загружен чат {chat_id} с {len(chats_data[chat_id].messages)} сообщениями")
            except Exception as e:
                logger.error(f"Ошибка загрузки файла {filename}: {e}")

async def auto_saver():
    """Фоновая задача для автосохранения"""
    while True:
        await asyncio.sleep(config.SAVE_INTERVAL)
        
        try:
            for chat_id in list(chats_data.keys()):
                await save_chat_data(chat_id)
            
            logger.debug(f"Автосохранение завершено, сохранено {len(chats_data)} чатов")
        except Exception as e:
            logger.error(f"Ошибка автосохранения: {e}")

# ==================== КОМАНДЫ ====================
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(message: Message):
    """Команда старта"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        InlineKeyboardButton("🔧 Управление", callback_data="manage"),
        InlineKeyboardButton("🎭 Настроение", callback_data="mood")
    )
    
    await message.answer(
        f"<b>Товарищ {message.from_user.first_name}! 👨‍⚖️</b>\n\n"
        f"Я — {config.BOT_NAME}, ваш революционный помощник.\n"
        f"Я изучаю сообщения чата и генерирую новые на основе изученного.\n\n"
        f"<b>Основные команды:</b>\n"
        f"/stats - статистика чата\n"
        f"/settings - настройки бота\n"
        f"/mood - изменить настроение бота\n"
        f="/train - переобучить модель\n"
        f="/export - экспорт данных\n"
        f="/import - импорт данных\n"
        f"/disable - отключить бота\n"
        f="/enable - включить бота\n\n"
        f"<i>Да здравствует коллективное сознание пролетариата!</i>",
        reply_markup=keyboard
    )

@dp.message_handler(commands=['stats', 'stat', 'статистика'])
async def cmd_stats(message: Message):
    """Показать статистику"""
    chat_id = message.chat.id
    chat_data = chats_data.get(chat_id)
    
    if not chat_data:
        await message.answer("📊 <b>Статистика чата</b>\n\nЧат ещё не инициализирован.")
        return
    
    # Рассчитываем активность
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
    )
    
    if chat_data.off_until > now:
        remaining = chat_data.off_until - now
        stats_text += f"\n⏸️ Бот отключен ещё на: <code>{format_time_remaining(int(remaining))}</code>"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔄 Обновить модель", callback_data="retrain"))
    
    await message.answer(stats_text, reply_markup=keyboard)

@dp.message_handler(commands=['settings', 'настройки'])
async def cmd_settings(message: Message):
    """Настройки бота"""
    chat_id = message.chat.id
    chat_data = chats_data.get(chat_id)
    
    if not chat_data:
        await message.answer("Сначала добавьте несколько сообщений в чат!")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    # Кнопки настроек
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

@dp.callback_query_handler(lambda c: c.data.startswith('setting_'))
async def process_settings(callback_query: CallbackQuery):
    """Обработка настроек"""
    chat_id = callback_query.message.chat.id
    chat_data = chats_data.get(chat_id)
    
    if not chat_data:
        await callback_query.answer("Чат не найден!")
        return
    
    setting = callback_query.data.replace('setting_', '')
    
    if setting == 'chance':
        # Изменение шанса ответа
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
    
    await save_chat_data(chat_id)
    await cmd_settings(callback_query.message)
    await callback_query.answer("Настройка обновлена!")

@dp.message_handler(commands=['mood', 'настроение'])
async def cmd_mood(message: Message):
    """Изменить настроение бота"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    for mood_name, mood_data in config.MOODS.items():
        emoji = "🎭"
        if mood_name == "happy": emoji = "😊"
        elif mood_name == "angry": emoji = "😠"
        elif mood_name == "philosophical": emoji = "🤔"
        elif mood_name == "revolutionary": emoji = "⚡"
        
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

@dp.callback_query_handler(lambda c: c.data.startswith('mood_'))
async def process_mood(callback_query: CallbackQuery):
    """Обработка выбора настроения"""
    chat_id = callback_query.message.chat.id
    chat_data = chats_data.get(chat_id)
    
    if not chat_data:
        await callback_query.answer("Чат не найден!")
        return
    
    mood = callback_query.data.replace('mood_', '')
    chat_data.mood = mood
    
    # Обновляем модель при смене настроения
    chat_data.update_model(force=True)
    
    await save_chat_data(chat_id)
    await callback_query.message.edit_text(
        f"🎭 <b>Настроение обновлено!</b>\n\n"
        f"Теперь бот в настроении: <code>{mood.capitalize()}</code>\n"
        f"Множитель шанса: <code>{config.MOODS[mood]['chance_multiplier']}x</code>"
    )
    await callback_query.answer()

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

@dp.message_handler(commands=['disable', 'off', 'выключить'])
async def cmd_disable(message: Message, state: FSMContext):
    """Отключить бота"""
    # Проверяем права администратора
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if not member.is_chat_admin():
            await message.answer("⚠️ Только администраторы могут отключать бота!")
            return
    except:
        await message.answer("⚠️ Не удалось проверить права администратора!")
        return
    
    args = message.get_args()
    
    if args:
        # Парсим время из аргументов
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
        # Используем время по умолчанию
        disable_seconds = int(config.DEFAULT_DISABLE_TIME.total_seconds())
    
    # Проверяем минимальное время
    if disable_seconds < config.MIN_DISABLE_TIME.total_seconds():
        await message.answer(
            f"⚠️ Время отключения слишком мало!\n"
            f"Минимум: {format_time_remaining(int(config.MIN_DISABLE_TIME.total_seconds()))}"
        )
        return
    
    chat_id = message.chat.id
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
    """Включить бота"""
    # Проверяем права администратора
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if not member.is_chat_admin():
            await message.answer("⚠️ Только администраторы могут включать бота!")
            return
    except:
        await message.answer("⚠️ Не удалось проверить права администратора!")
        return
    
    chat_id = message.chat.id
    chat_data = chats_data.get(chat_id)
    
    if chat_data and chat_data.off_until > time.time():
        chat_data.off_until = 0
        await save_chat_data(chat_id)
        await message.answer("✅ <b>Бот включен!</b>\n\nСнова готов к революционной деятельности!")
    else:
        await message.answer("ℹ️ Бот уже включен и готов к работе!")

@dp.message_handler(commands=['export', 'экспорт'])
async def cmd_export(message: Message):
    """Экспорт данных чата"""
    chat_id = message.chat.id
    chat_data = chats_data.get(chat_id)
    
    if not chat_data or not chat_data.messages:
        await message.answer("❌ Нет данных для экспорта!")
        return
    
    # Создаем текстовый файл с сообщениями
    export_text = f"Экспорт сообщений чата {chat_id}\n"
    export_text += f"Всего сообщений: {len(chat_data.messages)}\n"
    export_text += f"Дата экспорта: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
    export_text += "=" * 50 + "\n\n"
    
    for i, msg in enumerate(chat_data.messages[-1000:], 1):  # Экспортируем последние 1000 сообщений
        export_text += f"{i}. {msg}\n"
    
    # Сохраняем во временный файл
    filename = f"export_{chat_id}_{int(time.time())}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(export_text)
    
    # Отправляем файл
    with open(filename, 'rb') as f:
        await message.answer_document(
            f,
            caption=f"📁 <b>Экспорт данных чата</b>\n\n"
                   f"Сообщений: {len(chat_data.messages)}\n"
                   f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
    
    # Удаляем временный файл
    os.remove(filename)

@dp.message_handler(commands=['revolution', 'революция'])
async def cmd_revolution(message: Message):
    """Активировать революционный режим"""
    chat_id = message.chat.id
    chat_data = chats_data.get(chat_id)
    
    if not chat_data:
        await message.answer("Чат не инициализирован!")
        return
    
    chat_data.settings['revolutionary_mode'] = True
    chat_data.mood = "revolutionary"
    chat_data.update_model(force=True)
    
    await save_chat_data(chat_id)
    
    revolutionary_messages = [
        "Товарищи! Революционный режим активирован!",
        "Вся власть - советам! Бот переходит на революционные рельсы!",
        "Да здравствует ЛССР! Революция началась в этом чате!",
        "Пролетарии всех стран, соединяйтесь! Бот готов к классовой борьбе!",
        "Буржуазным элементам не место в нашем дискурсе! Включаю революционную риторику!"
    ]
    
    await message.answer(f"⚡ <b>{random.choice(revolutionary_messages)}</b>")

# ==================== ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ====================
@dp.message_handler(content_types=['text'])
async def handle_message(message: Message):
    """Основной обработчик сообщений"""
    chat_id = message.chat.id
    
    # Игнорируем команды
    if message.text.startswith('/'):
        return
    
    # Получаем данные чата
    chat_data = chats_data.get(chat_id)
    if not chat_data:
        return
    
    # Получаем текст сообщения
    text = message.text or message.caption
    if not text or len(text.strip()) < 2:
        return
    
    # Очищаем текст
    cleaned_text = text.strip()
    
    # Сохраняем сообщение
    if chat_data.settings['learning_enabled']:
        chat_data.messages.append(cleaned_text)
        # Обрезаем если слишком много сообщений
        if len(chat_data.messages) > chat_data.settings['max_messages'] * 2:
            chat_data.messages = chat_data.messages[-chat_data.settings['max_messages']:]
    
    # Проверяем, упомянут ли бот
    bot_username = (await bot.get_me()).username
    triggered = any([
        bot_username.lower() in cleaned_text.lower(),
        'председатель' in cleaned_text.lower(),
        'лсср' in cleaned_text.lower(),
        message.reply_to_message and message.reply_to_message.from_user.id == bot.id
    ])
    
    # Определяем, нужно ли отвечать
    if not should_respond(chat_data, message, triggered):
        return
    
    # Обновляем модель при необходимости
    chat_data.update_model()
    
    # Генерируем сообщение
    generated = generate_message(chat_data, context=cleaned_text[:50])
    
    if not generated:
        return
    
    # Добавляем задержку для реалистичности
    mood_settings = config.MOODS.get(chat_data.mood, config.MOODS['neutral'])
    min_delay, max_delay = mood_settings['response_time']
    
    await asyncio.sleep(random.uniform(min_delay, max_delay))
    
    # Показываем "печатает"
    await bot.send_chat_action(chat_id, 'typing')
    await asyncio.sleep(random.uniform(0.5, 1.5))
    
    # Отправляем сообщение
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
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")

# ==================== ОБРАБОТЧИКИ ДОБАВЛЕНИЯ В ЧАТ ====================
@dp.message_handler(content_types=['new_chat_members'])
async def on_new_members(message: Message):
    """Обработчик добавления новых участников"""
    bot_id = (await bot.get_me()).id
    
    # Проверяем, добавили ли бота
    if any(member.id == bot_id for member in message.new_chat_members):
        welcome_text = (
            f"<b>Товарищи! 👨‍⚖️</b>\n\n"
            f"Я — {config.BOT_NAME}, ваш новый революционный помощник.\n"
            f"Я буду изучать ваши сообщения и генерировать новые на их основе.\n\n"
            f"<b>Для полноценной работы:</b>\n"
            f"1. Выдайте мне права администратора\n"
            f"2. Напишите /help для списка команд\n"
            f"3. Начните общаться как обычно\n\n"
            f"<i>Да здравствует коллективный разум пролетариата!</i>\n\n"
            f"⚡ <b>Революционный совет:</b> Используйте /revolution для активации особого режима!"
        )
        
        await message.answer(welcome_text)

# ==================== ЗАПУСК БОТА ====================
async def on_startup(dp):
    """Действия при запуске бота"""
    logger.info(f"{config.BOT_NAME} запускается...")
    
    # Загружаем данные
    await load_all_chats()
    
    # Запускаем фоновые задачи
    asyncio.create_task(auto_saver())
    
    logger.info(f"Бот запущен! Загружено {len(chats_data)} чатов.")

async def on_shutdown(dp):
    """Действия при выключении бота"""
    logger.info("Бот выключается...")
    
    # Сохраняем все данные
    for chat_id in list(chats_data.keys()):
        await save_chat_data(chat_id)
    
    logger.info("Все данные сохранены.")

if __name__ == '__main__':
    # Создаем необходимые папки
    os.makedirs(config.DB_FOLDER, exist_ok=True)
    os.makedirs(config.MODEL_FOLDER, exist_ok=True)
    
    # Регистрируем middleware
    dp.middleware.setup(PrivateChatMiddleware())
    dp.middleware.setup(ChatMiddleware())
    
    # Запускаем бота
    from aiogram.utils import executor
    
    executor.start_polling(
        dp,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True
    )