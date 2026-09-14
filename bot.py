# -*- coding: utf-8 -*-
#
#  ─────────────────────────────────────────────────────────────────
#   STRATFORD CHASE · QUIZ BOT
#   aiogram 3.x · FSM-анкета · 3 ветки монетизации · inline-UX
#
#   Особенности UX:
#   • каждый следующий шаг УДАЛЯЕТ предыдущее сообщение — в чате
#     всегда виден ровно один активный экран;
#   • на каждом экране есть кнопка «Назад» к прошлому вопросу/разделу;
#   • ответы пользователя тоже удаляются, чтобы лента не росла.
#
#   Запуск:  pip install -r requirements.txt  &&  python bot.py
#  ─────────────────────────────────────────────────────────────────

import asyncio
import logging
import os
from html import escape

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

load_dotenv(override=False)


# ─────────────────────────────────────────────────────────────────
#  1. НАСТРОЙКИ — ВСЁ, ЧТО НУЖНО ПОМЕНЯТЬ, СОБРАНО ЗДЕСЬ
# ─────────────────────────────────────────────────────────────────

BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_СЮДА_ТОКЕН_ОТ_BOTFATHER")

# Telegram-username менеджера (без символа @)
MANAGER_USERNAME = os.getenv("MANAGER_USERNAME", "hwaam")

# ID чата/администратора, куда приходят анкеты и скриншоты.
# Свой ID можно узнать у @userinfobot. Если не нужно — оставьте 0.
ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) or None

# Числовой ID менеджера — ему сразу после квиза уходит краткая
# карточка нового лида. Узнать ID: менеджер пишет @userinfobot.
# Важно: менеджер должен сам нажать /start у этого бота, иначе
# Telegram не разрешит боту написать ему первым.
MANAGER_ID = int(os.getenv("MANAGER_ID", "0")) or None

MANAGER_URL = f"https://t.me/{MANAGER_USERNAME}"
# Ник менеджера в текстах не показываем — связь только через кнопку
# «Написать менеджеру», которая ведёт в чат по MANAGER_URL.

# ── Партнёрские ссылки офферов ───────────────────────────────────
LINKS = {
    # дебетовые карты
    "alfa_debit": "https://t.fincpanetwork.ru/click/69704/556?erid=2W5zFGy1aGQ",
    "ozon_debit": "https://t.fincpanetwork.ru/click/69704/700?erid=2W5zFGq8Wsa",
    "otp_debit":  "https://t.fincpanetwork.ru/click/69704/434?erid=2W5zFJrVsqB",
    # кредитные карты
    "alfa_credit": "https://t.fincpanetwork.ru/click/69704/339?erid=2W5zFJjJPEG",
    "tbank_credit": "https://t.fincpanetwork.ru/click/69704/27?erid=2W5zFKAWohb",
    "split_credit": "https://trk.ppdu.ru/click/bNKTOrU3?erid=2SDnjdJuo9L",
    # HR-офферы
    "bk_hr": "https://trk.ppdu.ru/click/RrkSA9jU?erid=2SDnjdu6ZqS",
    "yandex_hr": (
        "https://trk.ppdu.ru/click/JzHOiBTS"
        "?erid=CQH36pWzJqVGXC5oLP8WVVNCNqJmbhiUPijGiu4zpwPd7G&sub1=aT&landingId=2489"
    ),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s · %(levelname)-7s · %(name)s · %(message)s",
)
log = logging.getLogger("stratford.chase")

router = Router(name="stratford_chase")


# ─────────────────────────────────────────────────────────────────
#  2. ВИЗУАЛЬНЫЙ СЛОЙ — ВСЕ ТЕКСТЫ БОТА В ОДНОМ МЕСТЕ
#     HTML: <b>жирный</b>, <i>курсив</i>, <blockquote>цитата</blockquote>
# ─────────────────────────────────────────────────────────────────

def bar(step: int, total: int = 7) -> str:
    """Индикатор прогресса квиза: ▰▰▰▱▱▱▱"""
    return "▰" * step + "▱" * (total - step)


class T:  # Texts — копирайтинг интерфейса

    WELCOME = (
        "<b>Stratford Chase</b>\n\n"
        "Привет! Это бот платформы <b>Stratford Chase</b>.\n"
        "Мы помогаем зарабатывать на банковских продуктах, "
        "фрилансе и партнёрских программах.\n\n"
        "<b>Что здесь можно выбрать:</b>\n"
        "— Заработок на фрилансе\n"
        "— Быстрый заработок на картах\n"
        "— Работа с нами\n\n"
        "Сначала пройди короткий квиз из 7 вопросов — "
        "подберём лучший вариант лично под тебя. "
        "Это займёт <b>1–2 минуты</b>."
    )

    # ── Вопросы квиза ─────────────────────────────────────────────
    Q_NAME = (
        "Вопрос 1 из 7 · {bar}\n\n"
        "<b>Как тебя зовут?</b>\n"
        "Напиши своё имя одним сообщением."
    )
    Q_AGE = (
        "Вопрос 2 из 7 · {bar}\n\n"
        "<b>Сколько тебе лет?</b>\n"
        "Выбери подходящий диапазон на клавиатуре ниже.\n\n"
        "<i>Возраст важен: часть офферов доступна только с 18 лет.</i>"
    )
    Q_CITY = (
        "Вопрос 3 из 7 · {bar}\n\n"
        "<b>Твой город проживания?</b>\n"
        "Напиши город, в котором живёшь сейчас."
    )
    Q_SE = (
        "Вопрос 4 из 7 · {bar}\n\n"
        "<b>Есть ли у тебя статус самозанятости?</b>\n"
        "Если нет — ничего страшного, поможем оформить бесплатно."
    )
    Q_TG = (
        "Вопрос 5 из 7 · {bar}\n\n"
        "<b>Ссылка на твой Telegram для быстрой связи</b>\n"
        "Пришли <b>@username</b> или ссылку вида <b>t.me/username</b>.\n\n"
        "<i>По этому контакту менеджер согласует выплату.</i>"
    )
    Q_TIME = (
        "Вопрос 6 из 7 · {bar}\n\n"
        "<b>Сколько времени готов уделять заработку?</b>\n"
        "Честный ответ поможет подобрать реалистичный вариант."
    )
    Q_SOURCE = (
        "Вопрос 7 из 7 · {bar}\n\n"
        "<b>Откуда вы о нас узнали?</b>\n"
        "Выбери вариант — так мы поймём, какие площадки работают лучше."
    )
    Q_SOURCE_OTHER = (
        "Вопрос 7 из 7 · {bar}\n\n"
        "<b>Расскажи, откуда ты о нас узнал</b>\n"
        "Напиши свой вариант одним сообщением — например, название "
        "канала, сайта или площадки."
    )
    SOURCE_ERROR = (
        "<b>Слишком короткий ответ.</b>\n"
        "Напиши хотя бы пару слов — так менеджер поймёт источник."
    )

    NAME_ERROR = "<b>Напиши, пожалуйста, имя чуть подробнее.</b>"
    CITY_ERROR = "<b>Напиши название города одним сообщением.</b>"
    Q_TG_ERROR = (
        "<b>Кажется, это не похоже на ссылку.</b>\n\n"
        "Пришли, пожалуйста, <b>@username</b> или <b>t.me/username</b> — "
        "так менеджер сможет быстро с тобой связаться."
    )

    SUMMARY = (
        "<b>Отлично, {name}! Данные приняты.</b>\n\n"
        "<blockquote>"
        "Имя — {name}\n"
        "Возраст — {age}\n"
        "Город — {city}\n"
        "Самозанятость — {selfemp}\n"
        "Telegram — {tg}\n"
        "Время на заработок — {time}\n"
        "Узнал о нас — {source}"
        "</blockquote>\n"
        "Теперь выбери направление — расскажу условия каждого:"
    )

    # ── Ветка 1 · Фриланс ─────────────────────────────────────────
    FREE_INTRO = (
        "<b>Фриланс — стабильный доход на своих навыках</b>\n\n"
        "Направление для тех, кто хочет зарабатывать на своих навыках "
        "и работать из любой точки мира.\n\n"
        "Мы поможем выйти на платформу <b>Kwork</b>, где заказчики "
        "ищут исполнителей. Для вывода денег с платформы понадобится:\n"
        "— статус самозанятого;\n"
        "— расчётный счёт.\n\n"
        "Оформление <b>бесплатно</b> — поможем на каждом шаге.\n\n"
        "<b>Бонус</b>\n"
        "<blockquote>Через 30 дней после открытия счёта и первой "
        "активности ты получишь <b>от 3 000 до 5 000 ₽</b> на свой "
        "банковский счёт. Плюс — бесплатно приведём первых клиентов "
        "на твоё первое объявление.</blockquote>"
        "Готов начать? Нажми «Инструкция и ссылка»."
    )
    FREE_LINK = (
        "<b>Оформление займёт ~10 минут</b>\n\n"
        "Всё оформление проходит <b>через менеджера</b> — он подберёт "
        "банк, пришлёт персональную ссылку на самозанятость и "
        "расчётный счёт и поможет с регистрацией на Kwork.\n\n"
        "<b>Как действовать:</b>\n"
        "<b>1.</b> Нажми кнопку ниже и напиши менеджеру — он выдаст "
        "ссылку и проведёт по шагам.\n"
        "<b>2.</b> Оформи самозанятость и счёт по его инструкции.\n"
        "<b>3.</b> Пришли <b>скриншот</b> об открытии счёта прямо "
        "в этот чат — так мы зафиксируем твой бонус.\n\n"
        "<i>Жду скриншот — пришли его фото или файлом.</i>"
    )
    FREE_DONE = (
        "<b>Отлично! Твой счёт активирован.</b>\n\n"
        "Через 30 дней после первой операции по счёту ты получишь "
        "бонус <b>3 000–5 000 ₽</b>. Ты также в списке на продвижение "
        "первых клиентов.\n\n"
        "Ожидай сообщение от менеджера — обычно отвечаем "
        "в течение часа."
    )

    # ── Ветка 2 · Быстрый заработок ───────────────────────────────
    CARDS_INTRO = (
        "<b>Быстрый заработок на картах</b>\n\n"
        "Здесь платим за оформление банковских продуктов: выполняешь "
        "простые действия — получаешь деньги сразу после "
        "подтверждения.\n\n"
        "<blockquote><b>Важно.</b> Если выбранный банк у тебя уже был "
        "или используется сейчас — сначала напиши менеджеру для "
        "согласования (кнопка внизу).</blockquote>"
        "<b>Выбери, что хочешь оформить:</b>\n\n"
        "<b>Дебетовая карта</b> — от 500 ₽ до 1 300 ₽\n"
        "<b>Кредитная карта</b> — от 2 000 ₽ до 2 500 ₽\n"
        "<b>Для ИП / самозанятых</b> — от 4 000 ₽ до 10 000 ₽\n"
        "<b>HR-офферы</b> — от 6 000 ₽ до 10 000 ₽"
    )

    DEBIT = (
        "<b>Дебетовая карта · выплата 500–1 300 ₽</b>\n\n"
        "<b>Что нужно сделать:</b>\n"
        "<b>1.</b> Оформи карту по кнопке нужного банка ниже.\n"
        "<b>2.</b> Получи карту от курьера.\n"
        "<b>3.</b> Активируй её в приложении банка.\n"
        "<b>4.</b> Соверши покупку <b>от 150 ₽ в течение 24 часов</b>.\n\n"
        "Начисление происходит после подтверждения.\n\n"
        "<b>Актуальные банки и выплаты</b>\n"
        "<blockquote>"
        "АльфаБанк — <b>500 ₽</b>\n"
        "ОзонБанк — <b>500 ₽</b>\n"
        "ОТПБанк — <b>1 300 ₽</b>"
        "</blockquote>"
        "<b>АКЦИЯ.</b> Успей до конца месяца оформить карту "
        "<b>ОТПБанк</b>, чтобы получить <b>1 000 ₽</b> как новому "
        "пользователю.\n\n"
        "После оформления карты отправь <b>скриншот</b> в этот чат и "
        "обязательно напиши менеджеру для согласования выплаты — "
        "кнопка внизу."
    )

    CREDIT = (
        "<b>Кредитная карта · выплата 2 000–2 500 ₽</b>\n"
        "<i>Все офферы — от 18 лет.</i>\n\n"
        "<b>АльфаБанк — 2 000 ₽</b>\n"
        "<blockquote><b>Целевое действие:</b> активированная карта — "
        "карта, по которой было совершено снятие годового "
        "обслуживания. В случае бесплатного годового обслуживания "
        "карта считается активированной при совершении любой покупки, "
        "кроме переводов и снятия со счёта.</blockquote>"
        "<b>1.</b> 60 дней без % на покупки\n"
        "<b>2.</b> Бесплатное обслуживание в первый год, далее 990 ₽ "
        "при наличии расходных операций по кредитному счёту\n\n"
        "<b>Т-Банк — 2 500 ₽</b>\n"
        "<blockquote><b>Целевое действие:</b> активация карты и "
        "транзакция от 1 000 ₽ по ней после встречи с представителем "
        "в течение 48 часов.</blockquote>"
        "<b>1.</b> Лимит до 700 000 ₽\n"
        "<b>2.</b> Обслуживание от 0 ₽\n\n"
        "<b>СУПЕР СПЛИТ — 2 500 ₽</b>\n"
        "<blockquote><b>Цель:</b> вознаграждение начисляется за "
        "открытие кредитного договора при условии совершения одной или "
        "нескольких транзакций на общую сумму не менее 1 000 ₽ "
        "в течение 48 часов.</blockquote>"
        "После оформления карты отправь <b>скриншот</b> в этот чат и "
        "обязательно напиши менеджеру для согласования выплаты — "
        "кнопка внизу."
    )

    IP = (
        "<b>Для ИП и самозанятых · выплата 4 000–10 000 ₽</b>\n\n"
        "Открытие расчётного счёта (РКО) для бизнеса — "
        "<b>от 6 000 ₽ до 10 000 ₽</b> в зависимости от банка "
        "и условий оффера.\n\n"
        "<blockquote><b>Как оформить.</b> По этому направлению "
        "оформление идёт <b>напрямую через менеджера</b>: он подберёт "
        "банк под твой статус, пришлёт персональную ссылку и "
        "согласует выплату.</blockquote>"
        "Нажми кнопку ниже — ответим в течение часа и проведём "
        "по шагам в личных сообщениях."
    )

    HR = (
        "<b>HR-офферы · трудоустройство от 18 лет</b>\n\n"
        "Вакансии от партнёров: устраиваешься на работу, выполняешь "
        "условия — получаешь бонус.\n\n"
        "<b>Кассир в Бургер Кинг — 6 000 ₽</b>\n"
        "<blockquote><b>Целевое действие:</b> трудоустройство.</blockquote>"
        "<b>Яндекс Еда · Курьер — 10 000 ₽</b>\n"
        "<blockquote><b>Целевое действие:</b> нужно стать курьером, "
        "выполнить <b>100 заказов</b> и отработать <b>15 дней</b> "
        "(обязательно выполнив 100 заказов). Если в течение 15 дней "
        "не удаётся выполнить 100 заказов, время работы может "
        "увеличиться, но бонус <b>10 000 ₽</b> также остаётся."
        "</blockquote>"
        "Сервис может запросить регистрацию самозанятости — "
        "это стандартная процедура.\n\n"
        "После оформления отправь <b>скриншот</b> в этот чат и "
        "обязательно напиши менеджеру для согласования выплаты — "
        "кнопка внизу."
    )

    OFFER_DONE = (
        "<b>Данные переданы.</b>\n\n"
        "Скриншот получен и отправлен менеджеру на проверку. "
        "Выплата поступит после подтверждения — обычно в течение "
        "24 часов.\n\n"
        "По всем вопросам — кнопка «Написать менеджеру» ниже."
    )

    # ── Ветка 3 · Работа с нами ───────────────────────────────────
    WORK = (
        "<b>Работа с нами</b>\n\n"
        "Направление для тех, кто хочет зарабатывать больше и "
        "строить свою команду.\n\n"
        "Напиши менеджеру о вступлении — расскажем условия, "
        "подключим к команде и обучим всем процессам.\n\n"
        "Нажми кнопку ниже, чтобы начать разговор."
    )

    BRANCHES = "<b>Выбери направление:</b>"

    # ── Служебные ─────────────────────────────────────────────────
    NO_PHOTO = (
        "<b>Жду скриншот.</b>\n"
        "Пришли его фотографией или файлом прямо в этот чат — "
        "так мы быстрее зафиксируем твою выплату."
    )
    NO_STATE = (
        "Выбери действие на клавиатуре выше — "
        "или начни заново командой /start."
    )


# ─────────────────────────────────────────────────────────────────
#  3. FSM — СОСТОЯНИЯ ДИАЛОГА
# ─────────────────────────────────────────────────────────────────

class Quiz(StatesGroup):
    name = State()
    age = State()
    city = State()
    selfemp = State()
    tg = State()
    time = State()
    source = State()          # выбор источника кнопкой
    source_other = State()    # свой вариант текстом («Другое»)


class Proof(StatesGroup):
    """Ожидание скриншота после выдачи ссылки оффера."""
    freelance = State()
    offer = State()


# ─────────────────────────────────────────────────────────────────
#  4. КЛАВИАТУРЫ — INLINE-НАВИГАЦИЯ
# ─────────────────────────────────────────────────────────────────

def ikb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    """Короткий конструктор inline-клавиатур по строкам."""
    return InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r])


def btn(text: str, cb: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb)


def url_btn(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


def back(to: str, label: str = "← Назад") -> list[InlineKeyboardButton]:
    """Кнопка возврата: nav:<точка назначения>."""
    return [btn(label, f"nav:{to}")]


# Кнопка связи: без ника — просто переход в чат с менеджером
MANAGER_BTN = [url_btn("Написать менеджеру", MANAGER_URL)]
TO_BRANCHES = back("branches", "← К выбору направления")
TO_CARDS = back("cards", "← К списку офферов")

KB_WELCOME = ikb([btn("Пройти квиз ▸", "quiz:start")])

# ── клавиатуры квиза: только варианты ответа, без «Назад» ────────
KB_Q_NAME = None            # ответ текстом — клавиатура не нужна

KB_Q_AGE = ikb(
    [btn("14–16", "quiz:age:14–16")],
    [btn("16–23", "quiz:age:16–23")],
    [btn("23–60", "quiz:age:23–60")],
)

KB_Q_CITY = None            # ответ текстом

KB_Q_SE = ikb(
    [btn("Да, есть самозанятость", "quiz:se:Да, есть")],
    [btn("Нету", "quiz:se:Нету")],
    [btn("Оформлю — жду помощь менеджера", "quiz:se:Оформлю, жду помощь")],
)

KB_Q_TG = None              # ответ текстом

KB_Q_TIME = ikb(
    [btn("1–2 часа в день", "quiz:t:1–2 часа в день")],
    [btn("3–5 часов", "quiz:t:3–5 часов")],
    [btn("Полный день", "quiz:t:Полный день")],
)

KB_Q_SOURCE = ikb(
    [btn("TikTok", "quiz:src:TikTok")],
    [btn("Вакансии", "quiz:src:Вакансии")],
    [btn("От 3-их лиц", "quiz:src:От 3-их лиц")],
    [btn("Другое", "quiz:src:other")],
)

KB_Q_SOURCE_OTHER = None    # свой вариант пишем текстом

KB_BRANCHES = ikb(
    [btn("Фриланс", "br:free")],
    [btn("Быстрый заработок", "br:cards")],
    [btn("Работа с нами", "br:work")],
)

# ── ветка 1 ──────────────────────────────────────────────────────
KB_FREE_INTRO = ikb(
    [btn("Инструкция и ссылка ▸", "free:go")],
    TO_BRANCHES,
)

KB_FREE_LINK = ikb(
    MANAGER_BTN,
    back("free", "← К описанию фриланса"),
)

KB_FREE_DONE = ikb(MANAGER_BTN, TO_BRANCHES)

# ── ветка 2 ──────────────────────────────────────────────────────
KB_CARDS = ikb(
    [btn("Дебетовая карта · 500–1 300 ₽", "card:debit")],
    [btn("Кредитная карта · 2 000–2 500 ₽", "card:credit")],
    [btn("Для ИП / самозанятых · 4 000–10 000 ₽", "card:ip")],
    [btn("HR-офферы · 6 000–10 000 ₽", "card:hr")],
    TO_BRANCHES,
)

KB_DEBIT = ikb(
    [url_btn("Альфа банк", LINKS["alfa_debit"])],
    [url_btn("ОзонБанк", LINKS["ozon_debit"])],
    [url_btn("ОТПБанк", LINKS["otp_debit"])],
    MANAGER_BTN,
    TO_CARDS,
)

KB_CREDIT = ikb(
    [url_btn("АльфаБанк", LINKS["alfa_credit"])],
    [url_btn("Т-Банк", LINKS["tbank_credit"])],
    [url_btn("СУПЕР СПЛИТ", LINKS["split_credit"])],
    MANAGER_BTN,
    TO_CARDS,
)

KB_IP = ikb(MANAGER_BTN, TO_CARDS)

KB_HR = ikb(
    [url_btn("Бургер Кинг", LINKS["bk_hr"])],
    [url_btn("Яндекс Еда", LINKS["yandex_hr"])],
    MANAGER_BTN,
    TO_CARDS,
)

KB_OFFER_DONE = ikb(MANAGER_BTN, TO_CARDS, TO_BRANCHES)

# ── ветка 3 ──────────────────────────────────────────────────────
KB_WORK = ikb(MANAGER_BTN, TO_BRANCHES)


# ─────────────────────────────────────────────────────────────────
#  5. СЕРВИСНЫЙ СЛОЙ — «УДАЛЯЕМ ПРЕДЫДУЩЕЕ, ШЛЁМ НОВОЕ»
#     В чате всегда остаётся ровно один активный экран бота.
# ─────────────────────────────────────────────────────────────────

async def say(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    text: str,
    kb: InlineKeyboardMarkup | None = None,
) -> Message:
    """
    Удаляет предыдущее сообщение бота и отправляет новое.
    ID активного экрана хранится в FSM (ключ `screen_id`).
    """
    data = await state.get_data()
    prev_id = data.get("screen_id")

    if prev_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=prev_id)
        except TelegramBadRequest:
            pass  # уже удалено вручную или слишком старое — не страшно

    msg = await bot.send_message(
        chat_id, text, reply_markup=kb, disable_web_page_preview=True
    )
    await state.update_data(screen_id=msg.message_id)
    return msg


async def drop(message: Message) -> None:
    """Удаляет сообщение пользователя — лента не растягивается."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


async def notify_admin(bot: Bot, title: str, lines: list[str]) -> None:
    """Карточка лида администратору (если задан ADMIN_ID)."""
    if not ADMIN_ID:
        return
    card = f"<b>{title}</b>\n" + "\n".join(lines)
    try:
        await bot.send_message(ADMIN_ID, card, disable_web_page_preview=True)
    except TelegramBadRequest as e:
        log.warning("Не удалось написать админу: %s", e)


async def notify_manager(bot: Bot, data: dict, user_id: int) -> None:
    """
    Краткая карточка нового лида менеджеру — сразу после квиза.
    Пять строк: кто, откуда, статус, занятость и контакт.
    """
    if not MANAGER_ID:
        log.info("MANAGER_ID не задан — карточка менеджеру не отправлена")
        return

    tg = data.get("tg", "—")
    contact = tg if tg.startswith("@") else f"<code>{tg}</code>"
    card = (
        "<b>Новый лид · квиз пройден</b>\n"
        f"{data.get('name', '—')} · {data.get('age', '—')} · "
        f"{data.get('city', '—')}\n"
        f"Самозанятость: {data.get('selfemp', '—')}\n"
        f"Готов уделять: {data.get('time', '—')}\n"
        f"Узнал о нас: {data.get('source', '—')}\n"
        f"Связь: {contact} · <a href=\"tg://user?id={user_id}\">профиль</a>"
    )
    try:
        await bot.send_message(MANAGER_ID, card, disable_web_page_preview=True)
    except TelegramBadRequest as e:
        log.warning("Не удалось написать менеджеру: %s", e)


# ─────────────────────────────────────────────────────────────────
#  6. ЭКРАНЫ КВИЗА — ОДНА ФУНКЦИЯ НА ШАГ
# ─────────────────────────────────────────────────────────────────

async def screen_welcome(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await state.set_state(None)
    await say(bot, chat_id, state, T.WELCOME, KB_WELCOME)


async def screen_name(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await state.set_state(Quiz.name)
    await say(bot, chat_id, state, T.Q_NAME.format(bar=bar(1)), KB_Q_NAME)


async def screen_age(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await state.set_state(Quiz.age)
    await say(bot, chat_id, state, T.Q_AGE.format(bar=bar(2)), KB_Q_AGE)


async def screen_city(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await state.set_state(Quiz.city)
    await say(bot, chat_id, state, T.Q_CITY.format(bar=bar(3)), KB_Q_CITY)


async def screen_selfemp(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await state.set_state(Quiz.selfemp)
    await say(bot, chat_id, state, T.Q_SE.format(bar=bar(4)), KB_Q_SE)


async def screen_tg(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await state.set_state(Quiz.tg)
    await say(bot, chat_id, state, T.Q_TG.format(bar=bar(5)), KB_Q_TG)


async def screen_time(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await state.set_state(Quiz.time)
    await say(bot, chat_id, state, T.Q_TIME.format(bar=bar(6)), KB_Q_TIME)


async def screen_source(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await state.set_state(Quiz.source)
    await say(bot, chat_id, state, T.Q_SOURCE.format(bar=bar(7)), KB_Q_SOURCE)


async def screen_source_other(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """«Другое» — клиент пишет свой вариант текстом."""
    await state.set_state(Quiz.source_other)
    await say(
        bot, chat_id, state,
        T.Q_SOURCE_OTHER.format(bar=bar(7)), KB_Q_SOURCE_OTHER,
    )


async def screen_branches(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """Сводка анкеты + выбор направления."""
    await state.set_state(None)
    data = await state.get_data()
    required = ("name", "age", "city", "selfemp", "tg", "time", "source")
    if all(k in data for k in required):
        text = T.SUMMARY.format(**data)
    else:
        text = T.BRANCHES
    await say(bot, chat_id, state, text, KB_BRANCHES)


# карта переходов для кнопок «Назад» (callback_data = nav:<key>)
# В самом квизе кнопок «Назад» нет — только в ветках после анкеты.
NAV = {
    "welcome": screen_welcome,
    "branches": screen_branches,
}


# ─────────────────────────────────────────────────────────────────
#  7. ХЭНДЛЕРЫ · СТАРТ И НАВИГАЦИЯ
# ─────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def on_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    # Не удаляем сообщение пользователя /start.
    # Дальше логика экранов остаётся без изменений: say()
    # удаляет предыдущее сообщение бота через screen_id.
    await screen_welcome(message.bot, message.chat.id, state)


@router.callback_query(F.data.startswith("nav:"))
async def on_nav(cb: CallbackQuery, state: FSMContext) -> None:
    """Универсальная кнопка «Назад»."""
    key = cb.data.split(":", 1)[1]

    if key == "free":
        await state.set_state(None)
        await say(cb.bot, cb.message.chat.id, state, T.FREE_INTRO, KB_FREE_INTRO)
    elif key == "cards":
        await state.set_state(None)
        await say(cb.bot, cb.message.chat.id, state, T.CARDS_INTRO, KB_CARDS)
    else:
        handler = NAV.get(key)
        if handler:
            await handler(cb.bot, cb.message.chat.id, state)
    await cb.answer()


@router.callback_query(F.data == "quiz:start")
async def quiz_start(cb: CallbackQuery, state: FSMContext) -> None:
    await screen_name(cb.bot, cb.message.chat.id, state)
    await cb.answer("Поехали — всего 6 вопросов")


# ─────────────────────────────────────────────────────────────────
#  8. КВИЗ · ШАГИ 1…6
# ─────────────────────────────────────────────────────────────────

@router.message(Quiz.name, F.text)
async def q_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    await drop(message)
    if len(name) < 2:
        await say(
            message.bot, message.chat.id, state,
            f"{T.NAME_ERROR}\n\n{T.Q_NAME.format(bar=bar(1))}", KB_Q_NAME,
        )
        return
    # escape защищает HTML-разметку от символов < > &
    await state.update_data(name=escape(name))
    await screen_age(message.bot, message.chat.id, state)


@router.callback_query(Quiz.age, F.data.startswith("quiz:age:"))
async def q_age(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(age=cb.data.split(":", 2)[2])
    await screen_city(cb.bot, cb.message.chat.id, state)
    await cb.answer()


@router.message(Quiz.city, F.text)
async def q_city(message: Message, state: FSMContext) -> None:
    city = message.text.strip()
    await drop(message)
    if len(city) < 2:
        await say(
            message.bot, message.chat.id, state,
            f"{T.CITY_ERROR}\n\n{T.Q_CITY.format(bar=bar(3))}", KB_Q_CITY,
        )
        return
    await state.update_data(city=escape(city))
    await screen_selfemp(message.bot, message.chat.id, state)


@router.callback_query(Quiz.selfemp, F.data.startswith("quiz:se:"))
async def q_selfemp(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(selfemp=cb.data.split(":", 2)[2])
    await screen_tg(cb.bot, cb.message.chat.id, state)
    await cb.answer()


@router.message(Quiz.tg, F.text)
async def q_tg(message: Message, state: FSMContext) -> None:
    contact = message.text.strip()
    await drop(message)
    ok = (
        (contact.startswith("@") and len(contact) > 4)
        or contact.startswith("t.me/")
        or contact.startswith("https://t.me/")
    )
    if not ok:
        await say(
            message.bot, message.chat.id, state,
            f"{T.Q_TG_ERROR}\n\n{T.Q_TG.format(bar=bar(5))}", KB_Q_TG,
        )
        return
    await state.update_data(tg=escape(contact))
    await screen_time(message.bot, message.chat.id, state)


@router.callback_query(Quiz.time, F.data.startswith("quiz:t:"))
async def q_time(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(time=cb.data.split(":", 2)[2])
    await screen_source(cb.bot, cb.message.chat.id, state)
    await cb.answer()


# ── Вопрос 7 · «Откуда вы о нас узнали?» ─────────────────────────

@router.callback_query(Quiz.source, F.data.startswith("quiz:src:"))
async def q_source(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":", 2)[2]

    if value == "other":
        # «Другое» — просим написать свой вариант
        await screen_source_other(cb.bot, cb.message.chat.id, state)
        await cb.answer("Напиши свой вариант")
        return

    await state.update_data(source=value)
    await finish_quiz(cb.bot, cb.message.chat.id, state, cb.from_user.id)
    await cb.answer("Анкета готова")


@router.message(Quiz.source_other, F.text)
async def q_source_other(message: Message, state: FSMContext) -> None:
    answer = message.text.strip()
    await drop(message)
    if len(answer) < 2:
        await say(
            message.bot, message.chat.id, state,
            f"{T.SOURCE_ERROR}\n\n{T.Q_SOURCE_OTHER.format(bar=bar(7))}",
            KB_Q_SOURCE_OTHER,
        )
        return
    # помечаем, что это свободный ответ клиента
    await state.update_data(source=f"Другое — {escape(answer)}")
    await finish_quiz(
        message.bot, message.chat.id, state, message.from_user.id
    )


@router.message(Quiz.source_other)
async def q_source_other_wrong(message: Message, state: FSMContext) -> None:
    """На этом шаге ждём именно текст."""
    await drop(message)
    await say(
        message.bot, message.chat.id, state,
        f"{T.SOURCE_ERROR}\n\n{T.Q_SOURCE_OTHER.format(bar=bar(7))}",
        KB_Q_SOURCE_OTHER,
    )


async def finish_quiz(
    bot: Bot, chat_id: int, state: FSMContext, user_id: int
) -> None:
    """Финал квиза: сводка пользователю + уведомления."""
    await screen_branches(bot, chat_id, state)

    data = await state.get_data()

    # 1. Краткая карточка — сразу менеджеру
    await notify_manager(bot, data, user_id)

    # 2. Полная анкета — администратору (если задан ADMIN_ID)
    await notify_admin(
        bot,
        "Новая анкета · Stratford Chase",
        [
            f"Имя — {data.get('name', '—')}",
            f"Возраст — {data.get('age', '—')}",
            f"Город — {data.get('city', '—')}",
            f"Самозанятость — {data.get('selfemp', '—')}",
            f"Telegram — {data.get('tg', '—')}",
            f"Время — {data.get('time', '—')}",
            f"Узнал о нас — {data.get('source', '—')}",
            f"TG-id — <code>{user_id}</code>",
        ],
    )


# ─────────────────────────────────────────────────────────────────
#  9. ВЕТКА 1 · ФРИЛАНС
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "br:free")
async def branch_free(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await say(cb.bot, cb.message.chat.id, state, T.FREE_INTRO, KB_FREE_INTRO)
    await cb.answer()


@router.callback_query(F.data == "free:go")
async def branch_free_link(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Proof.freelance)
    await say(cb.bot, cb.message.chat.id, state, T.FREE_LINK, KB_FREE_LINK)
    await cb.answer("Ссылка выдана — жду скриншот")


@router.message(Proof.freelance, F.photo | F.document)
async def proof_freelance(message: Message, state: FSMContext) -> None:
    if ADMIN_ID:
        try:
            await message.forward(ADMIN_ID)
            await notify_admin(
                message.bot, "Скриншот · Фриланс (РКО)",
                [f"От — {escape(message.from_user.full_name)}",
                 f"TG-id — <code>{message.from_user.id}</code>"],
            )
        except TelegramBadRequest as e:
            log.warning("Форвард админу не удался: %s", e)

    await state.set_state(None)
    await say(message.bot, message.chat.id, state, T.FREE_DONE, KB_FREE_DONE)


@router.message(Proof.freelance)
async def proof_freelance_wrong(message: Message, state: FSMContext) -> None:
    await drop(message)
    await say(
        message.bot, message.chat.id, state,
        f"{T.NO_PHOTO}\n\n{T.FREE_LINK}", KB_FREE_LINK,
    )


# ─────────────────────────────────────────────────────────────────
#  10. ВЕТКА 2 · БЫСТРЫЙ ЗАРАБОТОК
# ─────────────────────────────────────────────────────────────────

# оффер → (текст, клавиатура, нужен ли скриншот)
OFFERS = {
    "card:debit":  (T.DEBIT,  KB_DEBIT,  True),
    "card:credit": (T.CREDIT, KB_CREDIT, True),
    "card:ip":     (T.IP,     KB_IP,     False),   # только через менеджера
    "card:hr":     (T.HR,     KB_HR,     True),
}


@router.callback_query(F.data == "br:cards")
async def branch_cards(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await say(cb.bot, cb.message.chat.id, state, T.CARDS_INTRO, KB_CARDS)
    await cb.answer()


@router.callback_query(F.data.in_(OFFERS))
async def offer_show(cb: CallbackQuery, state: FSMContext) -> None:
    text, kb, need_proof = OFFERS[cb.data]
    await state.set_state(Proof.offer if need_proof else None)
    await state.update_data(offer=cb.data)
    await say(cb.bot, cb.message.chat.id, state, text, kb)
    await cb.answer("Условия ниже" + (" — жду скриншот" if need_proof else ""))


@router.message(Proof.offer, F.photo | F.document)
async def proof_offer(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if ADMIN_ID:
        try:
            await message.forward(ADMIN_ID)
            await notify_admin(
                message.bot,
                f"Скриншот · Оффер {data.get('offer', '—')}",
                [f"От — {escape(message.from_user.full_name)}",
                 f"TG-id — <code>{message.from_user.id}</code>"],
            )
        except TelegramBadRequest as e:
            log.warning("Форвард админу не удался: %s", e)

    await state.set_state(None)
    await say(message.bot, message.chat.id, state, T.OFFER_DONE, KB_OFFER_DONE)


@router.message(Proof.offer)
async def proof_offer_wrong(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    text, kb, _ = OFFERS.get(data.get("offer", ""), (T.CARDS_INTRO, KB_CARDS, False))
    await drop(message)
    await say(message.bot, message.chat.id, state, f"{T.NO_PHOTO}\n\n{text}", kb)


# ─────────────────────────────────────────────────────────────────
#  11. ВЕТКА 3 · РАБОТА С НАМИ
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "br:work")
async def branch_work(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await say(cb.bot, cb.message.chat.id, state, T.WORK, KB_WORK)
    await cb.answer()


# ─────────────────────────────────────────────────────────────────
#  12. ФОЛЛБЭК — ЛЮБОЕ СООБЩЕНИЕ БЕЗ СОСТОЯНИЯ
# ─────────────────────────────────────────────────────────────────

@router.message()
async def fallback(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await drop(message)
        data = await state.get_data()
        if data.get("screen_id"):
            return  # активный экран уже висит в чате — не дублируем
        await screen_welcome(message.bot, message.chat.id, state)


# ─────────────────────────────────────────────────────────────────
#  13. ТОЧКА ВХОДА
# ─────────────────────────────────────────────────────────────────

async def main() -> None:
    if BOT_TOKEN.startswith("ВСТАВЬ"):
        raise SystemExit(
            "Токен не задан. Укажите BOT_TOKEN в .env или в начале bot.py"
        )

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    log.info("Бот запущен: @%s · менеджер @%s", me.username, MANAGER_USERNAME)
    if not MANAGER_ID:
        log.warning(
            "MANAGER_ID не задан — краткие карточки лидов менеджеру "
            "отправляться не будут. Укажите MANAGER_ID в .env"
        )

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Бот остановлен")