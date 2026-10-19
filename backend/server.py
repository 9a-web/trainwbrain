from fastapi import FastAPI, APIRouter, HTTPException, Body, Depends, Header, Cookie, Response, Request, WebSocket, WebSocketDisconnect, Query, UploadFile, File
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import asyncio
import time
import logging
import re
import copy
import json
import secrets
import difflib
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, date, timedelta
import httpx
import json_repair
import math
from pymongo.errors import DuplicateKeyError
from pymongo.errors import DuplicateKeyError

from models import (
    Exercise, ExerciseCreate,
    ProgramTemplate, ProgramTemplateCreate, ProgramTemplateUpdate,
    Plan, PlanCreate,
    WorkoutSession, SessionStartReq,
    CoachLink,
    PlanDayMark, DaySkipReq, DayRescheduleReq, DayMarkReq, UserSettingsReq,
    DiaryExerciseIn, DiarySessionCreate, DiarySessionUpdate, DiaryProfileUpdate,
    DiaryParseReq, DiaryChatReq, DiaryNextReq,
    InviteCreateReq, InviteRedeemReq, InviteCode,
    PermissionsUpdateReq, AccessTierReq, RoleReq,
    CardioSession, CardioCreateReq, CardioPhotoReq,
    CARDIO_TYPES, CARDIO_INTENSITIES, CARDIO_SOURCES,
)
from seed import (
    seed_builtins, ensure_indexes, ensure_phase1_backfill,
    group_letters, muscle_letter, percent_of, scheme_tonnage,
    MUSCLE_CANON, MUSCLE_VIEWS, normalize_muscle_weights,
)
from auth import (
    RegisterReq, LoginReq, TelegramAuthReq, GoogleSessionReq, GoogleOAuthReq,
    hash_password, verify_password, new_session_token, session_expiry,
    synthetic_telegram_id, validate_telegram_init_data, parse_telegram_user,
    ensure_auth_indexes,
)
from realtime import ConnectionManager

# Система уведомлений
from scheduler import init_scheduler, start_scheduler, stop_scheduler, get_scheduler_status
from notifications import (
    get_notification_settings,
    notify_coach_on_workout_complete,
    notify_coach_on_new_client
)
from telegram_bot import send_test_message, get_bot_info
from realtime import manager, now_iso as rt_now


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')
# Локальные секреты (не коммитятся) переопределяют шаблонные значения из .env,
# чтобы прод-креды не лежали в отслеживаемом файле.
load_dotenv(ROOT_DIR / '.env.local', override=True)

# MongoDB connection
mongo_url = os.environ['MONGO_URL']

# Проверка TLS-сертификата включена по умолчанию (Atlas отдаёт валидные
# сертификаты). Небезопасный режим — только по явному MONGO_TLS_INSECURE=true|1.
_mongo_tls_insecure = os.environ.get("MONGO_TLS_INSECURE", "false").lower() in ("1", "true", "yes")
try:
    _mongo_kwargs = {"serverSelectionTimeoutMS": 30000}
    if _mongo_tls_insecure:
        _mongo_kwargs.update(
            tls=True,
            tlsAllowInvalidCertificates=True,
            tlsAllowInvalidHostnames=True,
        )
    client = AsyncIOMotorClient(mongo_url, **_mongo_kwargs)
except Exception as e:
    print(f"Mongo client setup failed, using default: {e}")
    client = AsyncIOMotorClient(mongo_url)

db = client[os.environ['DB_NAME']]

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')

# Google OAuth (own credentials — shows the app's own consent-screen branding)
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')

# Create the main app without a prefix
app = FastAPI()

# CORS middleware - MUST be added before routers.
# NB: allow_origins=["*"] is INVALID together with allow_credentials=True
# (browsers reject it). Parse an explicit list from CORS_ORIGINS; fall back to
# "*" without credentials for local development.
_cors_origins = [o.strip() for o in os.environ.get('CORS_ORIGINS', '*').split(',') if o.strip()]
_cors_wildcard = _cors_origins == ['*'] or '*' in _cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_credentials=not _cors_wildcard,
    allow_origins=["*"] if _cors_wildcard else _cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
# User Models
class UserCreate(BaseModel):
    """Данные пользователя из Telegram WebApp"""
    telegram_id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = None


class User(BaseModel):
    """Модель пользователя в БД"""
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    telegram_id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Hello World"}


async def get_current_user(authorization: Optional[str] = Header(default=None)):
    # Аутентификация ТОЛЬКО по Bearer-заголовку. Cookie намеренно игнорируется,
    # чтобы не оставалось CSRF-вектора (фронтенд шлёт только Authorization).
    # Определена здесь — до первого Depends(get_current_user): default-аргумент
    # вычисляется в момент декорирования роута, а не при вызове.
    token = _token_from(authorization, None)
    if not token:
        raise HTTPException(status_code=401, detail="Не авторизован")
    sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=401, detail="Недействительная сессия")
    exp = sess.get("expires_at")
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Сессия истекла")
    user = await db.users.find_one(
        {"telegram_id": sess["telegram_id"]},
        {"_id": 0, "password_hash": 0},
    )
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return user


# User endpoints
@api_router.post("/users", response_model=User)
async def create_or_update_user(user_data: UserCreate, current: dict = Depends(get_current_user)):
    """
    Создать или обновить пользователя (upsert).
    IDOR-защита: обновлять можно только собственный профиль.
    """
    if user_data.telegram_id != current["telegram_id"]:
        raise HTTPException(status_code=403, detail="Not your account")
    existing_user = await db.users.find_one(
        {"telegram_id": user_data.telegram_id},
        {"_id": 0}
    )
    
    if existing_user:
        # Обновляем существующего пользователя
        update_data = {
            "first_name": user_data.first_name,
            "last_name": user_data.last_name,
            "username": user_data.username,
            "language_code": user_data.language_code,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.update_one(
            {"telegram_id": user_data.telegram_id},
            {"$set": update_data}
        )
        # Получаем обновлённого пользователя
        updated_user = await db.users.find_one(
            {"telegram_id": user_data.telegram_id},
            {"_id": 0}
        )
        # Конвертируем даты
        for field in ['created_at', 'updated_at']:
            if isinstance(updated_user.get(field), str):
                updated_user[field] = datetime.fromisoformat(updated_user[field])
        logger.info(f"User updated: telegram_id={user_data.telegram_id}")
        return updated_user
    else:
        # Создаём нового пользователя
        new_user = User(
            telegram_id=user_data.telegram_id,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            username=user_data.username,
            language_code=user_data.language_code
        )
        doc = new_user.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        doc['updated_at'] = doc['updated_at'].isoformat()
        
        await db.users.insert_one(doc)
        logger.info(f"New user created: telegram_id={user_data.telegram_id}, id={new_user.id}")
        return new_user


@api_router.get("/users/{telegram_id}")
async def get_user(telegram_id: int, current: dict = Depends(get_current_user)):
    """Получить пользователя по Telegram ID.

    IDOR-защита: доступен себе либо тренеру, привязанному к этому спортсмену."""
    if current["telegram_id"] != telegram_id and not await _is_coach_of(current["telegram_id"], telegram_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    user = await db.users.find_one(
        {"telegram_id": telegram_id},
        {"_id": 0, "password_hash": 0}
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ===========================================================================
# P3 — Режим пользователя (athlete/coach), приглашения, подопечные, видимость плана
# ===========================================================================
import secrets as _secrets

_BOT_USERNAME_CACHE = {"value": None}


class ModeReq(BaseModel):
    mode: str  # athlete | coach


class CoachInviteReq(BaseModel):
    coach_telegram_id: int


class CoachLinkReq(BaseModel):
    code: str
    athlete_telegram_id: int


class CoachUnlinkReq(BaseModel):
    athlete_telegram_id: int


class VisibilityReq(BaseModel):
    visibility: str  # draft | published


class WeekPublishReq(BaseModel):
    published: bool = True


class TrainingDaysReq(BaseModel):
    training_days: List[int] = Field(default_factory=list)


def _gen_invite_code(n: int = 8) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # без неоднозначных символов
    return "".join(_secrets.choice(alphabet) for _ in range(n))


async def _unique_invite_code() -> str:
    code = _gen_invite_code()
    while await db.users.find_one({"invite_code": code}, {"_id": 0}):
        code = _gen_invite_code()
    return code


async def _get_bot_username() -> Optional[str]:
    """Best-effort: получить username бота через getMe (кэшируется)."""
    if _BOT_USERNAME_CACHE["value"] is not None:
        return _BOT_USERNAME_CACHE["value"] or None
    if not TELEGRAM_BOT_TOKEN:
        _BOT_USERNAME_CACHE["value"] = ""
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as cx:
            r = await cx.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe")
            if r.status_code == 200:
                uname = (r.json().get("result") or {}).get("username")
                _BOT_USERNAME_CACHE["value"] = uname or ""
                return uname
    except Exception as e:
        logger.warning(f"Failed to fetch bot username: {e}")
    _BOT_USERNAME_CACHE["value"] = ""
    return None


def _user_brief(u: Optional[dict]) -> Optional[dict]:
    if not u:
        return None
    return {
        "telegram_id": u.get("telegram_id"),
        "first_name": u.get("first_name"),
        "last_name": u.get("last_name"),
        "username": u.get("username"),
        "picture": u.get("picture"),
        "roles": u.get("roles") or ["athlete"],
        "active_mode": u.get("active_mode") or "athlete",
    }


@api_router.patch("/users/{telegram_id}/mode")
async def switch_user_mode(telegram_id: int, payload: ModeReq, current: dict = Depends(get_current_user)):
    """Переключить активный режим UI (athlete/coach). При первом переходе в coach —
    добавляет роль coach и генерирует invite_code."""
    # IDOR-защита: менять режим можно только себе.
    if telegram_id != current["telegram_id"]:
        raise HTTPException(status_code=403, detail="Not your account")
    mode = (payload.mode or "").strip().lower()
    if mode not in ("athlete", "coach"):
        raise HTTPException(status_code=400, detail="mode должен быть athlete или coach")
    user = await db.users.find_one({"telegram_id": telegram_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    roles = set(user.get("roles") or ["athlete"])
    roles.add("athlete")
    set_fields = {"active_mode": mode, "updated_at": datetime.now(timezone.utc).isoformat()}
    if mode == "coach":
        roles.add("coach")
        if not user.get("invite_code"):
            set_fields["invite_code"] = await _unique_invite_code()
    set_fields["roles"] = sorted(roles)
    await db.users.update_one({"telegram_id": telegram_id}, {"$set": set_fields})
    updated = await db.users.find_one({"telegram_id": telegram_id}, {"_id": 0, "password_hash": 0})
    return updated


# ===========================================================================
# Аутентификация: Telegram (один тап) + Email/пароль + Google (Emergent Auth)
# Единая модель сессий (коллекция user_sessions). Каждый аккаунт имеет
# telegram_id (реальный или синтетический) — ключ всех данных приложения.
# ===========================================================================

def _token_from(authorization, session_token):
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return session_token


# Прагматичная проверка email + dummy-hash для выравнивания времени ответа
# (защита от перечисления аккаунтов по таймингу). Хеш считаем лениво — вызов
# bcrypt на импорте не нужен и замедляет старт.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DUMMY_PASSWORD_HASH: Optional[str] = None


def _dummy_password_hash() -> str:
    global _DUMMY_PASSWORD_HASH
    if _DUMMY_PASSWORD_HASH is None:
        _DUMMY_PASSWORD_HASH = hash_password("timing-equalizer-dummy-password")
    return _DUMMY_PASSWORD_HASH


# --- Простой in-memory rate limiter для /auth/* (защита от bruteforce/спама) ---
_AUTH_BUCKETS: dict = {}
_AUTH_MAX_BUCKETS = 10000


def _client_ip(request: Request) -> str:
    # X-Forwarded-For доверяем ТОЛЬКО при TRUST_PROXY_HEADERS=true и берём
    # ПОСЛЕДНИЙ адрес (его дописал доверенный прокси) — первый легко подделать.
    trust_proxy = os.environ.get("TRUST_PROXY_HEADERS", "false").lower() in ("1", "true", "yes")
    if trust_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            parts = [p.strip() for p in fwd.split(",") if p.strip()]
            if parts:
                return parts[-1]
    return request.client.host if request.client else "unknown"


def _rate_limit(bucket_key: str, limit: int, window: float, detail: str) -> None:
    """Бросает 429, если попыток за `window` секунд стало >= limit."""
    now = time.monotonic()
    if len(_AUTH_BUCKETS) > _AUTH_MAX_BUCKETS:
        # Аварийная уборка, чтобы словарь не рос безгранично.
        for k in [k for k, v in _AUTH_BUCKETS.items() if not v or now - v[-1] > window]:
            _AUTH_BUCKETS.pop(k, None)
    bucket = _AUTH_BUCKETS.setdefault(bucket_key, [])
    bucket[:] = [t for t in bucket if now - t < window]
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail=detail)
    bucket.append(now)


async def _create_session(telegram_id: int, method: str) -> str:
    token = new_session_token()
    await db.user_sessions.insert_one({
        "session_token": token,
        "telegram_id": telegram_id,
        "auth_method": method,
        "created_at": datetime.now(timezone.utc).isoformat(),
        # Store a real BSON Date so the TTL index on expires_at actually works.
        "expires_at": session_expiry(),
    })
    return token


async def _user_public(telegram_id: int) -> dict:
    return await db.users.find_one(
        {"telegram_id": telegram_id},
        {"_id": 0, "password_hash": 0},
    )


def _set_session_cookie(response: Response, token: str):
    # Cookie оставлен для обратной совместимости, но аутентификация идёт ТОЛЬКО
    # по Bearer-заголовку. SameSite=lax исключает CSRF-использование cookie.
    secure_cookie = os.environ.get("COOKIE_SECURE", "true").lower() not in ("0", "false", "no")
    response.set_cookie(
        key="session_token", value=token,
        max_age=7 * 24 * 3600, httponly=True,
        secure=secure_cookie, samesite="lax", path="/",
    )


async def _unique_synth_id() -> int:
    tgid = synthetic_telegram_id()
    while await db.users.find_one({"telegram_id": tgid}, {"_id": 0}):
        tgid = synthetic_telegram_id()
    return tgid


@api_router.post("/auth/register")
async def auth_register(payload: RegisterReq, response: Response, request: Request):
    from pymongo.errors import DuplicateKeyError
    _rate_limit(f"register:{_client_ip(request)}", 10, 3600,
                "Слишком много попыток регистрации. Попробуйте позже.")
    email = (payload.email or "").strip().lower()
    if not email or len(email) > 254 or not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Некорректный email")
    if not payload.password or len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Пароль должен быть не короче 6 символов")
    if len(payload.password) > 128:
        raise HTTPException(status_code=400, detail="Пароль слишком длинный (до 128 символов)")
    if await db.users.find_one({"email": email}, {"_id": 0}):
        raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")
    tgid = await _unique_synth_id()
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()), "telegram_id": tgid,
        "first_name": (payload.name or email.split("@")[0]).strip(),
        "last_name": None, "username": None, "language_code": "ru",
        "email": email, "password_hash": hash_password(payload.password),
        "auth_provider": ["email"], "picture": None,
        "phase1_migrated": True,
        "created_at": now, "updated_at": now,
    }
    try:
        await db.users.insert_one(doc)
    except DuplicateKeyError:
        # Гонка между find_one и insert_one: тот же 400, без 500.
        raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")
    token = await _create_session(tgid, "email")
    _set_session_cookie(response, token)
    logger.info(f"Auth register: email={email}, telegram_id={tgid}")
    return {"token": token, "user": await _user_public(tgid)}


@api_router.post("/auth/login")
async def auth_login(payload: LoginReq, response: Response, request: Request):
    email = (payload.email or "").strip().lower()
    if not email or len(email) > 254 or not _EMAIL_RE.match(email):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if len(payload.password or "") > 128:
        raise HTTPException(status_code=400, detail="Пароль слишком длинный (до 128 символов)")
    # Lockout против подбора пароля: лимит на пару (IP, email).
    _rate_limit(f"login:{_client_ip(request)}:{email}", 8, 900,
                "Слишком много неудачных попыток входа. Повторите через 15 минут.")
    user = await db.users.find_one({"email": email})
    # bcrypt считаем ВСЕГДА (в т.ч. для несуществующего email по dummy-hash),
    # иначе разница во времени выдаёт наличие аккаунта.
    password_hash = (user or {}).get("password_hash") or _dummy_password_hash()
    ok = verify_password(payload.password or "", password_hash)
    if not user or not user.get("password_hash") or not ok:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    token = await _create_session(user["telegram_id"], "email")
    _set_session_cookie(response, token)
    return {"token": token, "user": await _user_public(user["telegram_id"])}


@api_router.post("/auth/telegram")
async def auth_telegram(payload: TelegramAuthReq, response: Response, request: Request):
    _rate_limit(f"telegram:{_client_ip(request)}", 30, 900,
                "Слишком много попыток входа. Повторите позже.")
    parsed = validate_telegram_init_data(payload.init_data, TELEGRAM_BOT_TOKEN)
    if not parsed:
        raise HTTPException(status_code=401, detail="Не удалось проверить подпись Telegram")
    tg_user = parse_telegram_user(parsed)
    if not tg_user or "id" not in tg_user:
        raise HTTPException(status_code=401, detail="Нет данных пользователя Telegram")
    tgid = int(tg_user["id"])
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.users.find_one({"telegram_id": tgid}, {"_id": 0})
    if existing:
        await db.users.update_one({"telegram_id": tgid}, {
            "$set": {
                "first_name": tg_user.get("first_name") or existing.get("first_name") or "User",
                "last_name": tg_user.get("last_name"),
                "username": tg_user.get("username"),
                "language_code": tg_user.get("language_code") or existing.get("language_code") or "ru",
                "updated_at": now,
            },
            "$addToSet": {"auth_provider": "telegram"},
        })
    else:
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "telegram_id": tgid,
            "first_name": tg_user.get("first_name") or "User",
            "last_name": tg_user.get("last_name"),
            "username": tg_user.get("username"),
            "language_code": tg_user.get("language_code") or "ru",
            "email": None, "password_hash": None,
            "auth_provider": ["telegram"], "picture": tg_user.get("photo_url"),
            "phase1_migrated": True,
            "created_at": now, "updated_at": now,
        })
    token = await _create_session(tgid, "telegram")
    _set_session_cookie(response, token)
    logger.info(f"Auth telegram: telegram_id={tgid}")
    return {"token": token, "user": await _user_public(tgid)}


@api_router.post("/auth/google/session")
async def auth_google_session(payload: GoogleSessionReq, response: Response, request: Request):
    _rate_limit(f"google:{_client_ip(request)}", 30, 900,
                "Слишком много попыток входа. Повторите позже.")
    data = await exchange_emergent_session(payload.session_id)
    if not data or not data.get("email"):
        raise HTTPException(status_code=401, detail="Не удалось авторизоваться через Google")
    email = data["email"].strip().lower()
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        tgid = existing["telegram_id"]
        await db.users.update_one({"telegram_id": tgid}, {
            "$set": {
                "first_name": existing.get("first_name") or data.get("name") or email.split("@")[0],
                "picture": data.get("picture") or existing.get("picture"),
                "updated_at": now,
            },
            "$addToSet": {"auth_provider": "google"},
        })
    else:
        tgid = await _unique_synth_id()
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "telegram_id": tgid,
            "first_name": data.get("name") or email.split("@")[0],
            "last_name": None, "username": None, "language_code": "ru",
            "email": email, "password_hash": None,
            "auth_provider": ["google"], "google_sub": data.get("id"),
            "picture": data.get("picture"),
            "phase1_migrated": True,
            "created_at": now, "updated_at": now,
        })
    # Сторонний Emergent session_token не сохраняем как нашу сессию — всегда
    # чеканим собственный токен (единый формат/срок жизни/отзыв).
    token = await _create_session(tgid, "google")
    _set_session_cookie(response, token)
    logger.info(f"Auth google: email={email}, telegram_id={tgid}")
    return {"token": token, "user": await _user_public(tgid)}


@api_router.get("/auth/google/config")
async def auth_google_config():
    """Public Google OAuth config for the frontend (client_id is not secret)."""
    return {"client_id": GOOGLE_CLIENT_ID}


@api_router.post("/auth/google/oauth")
async def auth_google_oauth(payload: GoogleOAuthReq, response: Response, request: Request):
    """Direct Google OAuth (own credentials): exchange the authorization code
    for the user's profile, then create/load the account and issue our session."""
    _rate_limit(f"google-oauth:{_client_ip(request)}", 30, 900,
                "Слишком много попыток входа. Повторите позже.")
    # CSRF-state необязателен (старый фронтенд его не шлёт) — если передан,
    # проверяем формат, чтобы не принимать мусор/инъекции.
    if payload.state is not None:
        st = payload.state.strip()
        if not st or len(st) > 512 or any(ord(c) < 0x20 for c in st):
            raise HTTPException(status_code=400, detail="Некорректный параметр state")
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth не настроен на сервере")
    data = await exchange_google_code(
        payload.code, payload.redirect_uri, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
    )
    if not data or not data.get("email"):
        raise HTTPException(status_code=401, detail="Не удалось авторизоваться через Google")
    email = data["email"].strip().lower()
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        tgid = existing["telegram_id"]
        await db.users.update_one({"telegram_id": tgid}, {
            "$set": {
                "first_name": existing.get("first_name") or data.get("name") or email.split("@")[0],
                "picture": data.get("picture") or existing.get("picture"),
                "updated_at": now,
            },
            "$addToSet": {"auth_provider": "google"},
        })
    else:
        tgid = await _unique_synth_id()
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "telegram_id": tgid,
            "first_name": data.get("name") or email.split("@")[0],
            "last_name": None, "username": None, "language_code": "ru",
            "email": email, "password_hash": None,
            "auth_provider": ["google"], "google_sub": data.get("sub"),
            "picture": data.get("picture"),
            "phase1_migrated": True,
            "created_at": now, "updated_at": now,
        })
    token = await _create_session(tgid, "google")
    _set_session_cookie(response, token)
    logger.info(f"Auth google-oauth: email={email}, telegram_id={tgid}")
    return {"token": token, "user": await _user_public(tgid)}


@api_router.get("/auth/me")
async def auth_me(current=Depends(get_current_user)):
    return current


@api_router.post("/auth/logout")
async def auth_logout(
    response: Response,
    authorization: Optional[str] = Header(default=None),
):
    # Только Bearer — cookie не участвует в аутентификации (анти-CSRF logout).
    token = _token_from(authorization, None)
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


# Кэш file_path аватаров: user_id -> (file_path, expires_monotonic)
_TG_AVATAR_CACHE: dict = {}
_TG_AVATAR_TTL = 3600.0


async def _resolve_telegram_avatar_file(user_id: int) -> Optional[str]:
    """Возвращает file_path аватара пользователя через Bot API (с кэшем).

    Секрет (bot-токен) остаётся внутри backend и наружу не отдаётся."""
    if not TELEGRAM_BOT_TOKEN:
        return None
    now = asyncio.get_event_loop().time()
    cached = _TG_AVATAR_CACHE.get(user_id)
    if cached and cached[1] > now:
        return cached[0]
    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            photos_response = await http_client.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUserProfilePhotos",
                params={"user_id": user_id, "limit": 1},
            )
            photos_data = photos_response.json()
            if not photos_data.get("ok"):
                logger.warning(f"Telegram API error: {photos_data.get('description', 'Unknown error')}")
                return None
            photos = photos_data.get("result", {}).get("photos", [])
            if not photos:
                return None
            # Последний размер = самый большой
            file_id = photos[0][-1]["file_id"]
            file_response = await http_client.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile",
                params={"file_id": file_id},
            )
            file_data = file_response.json()
            if not file_data.get("ok"):
                logger.warning(f"Failed to get file path: {file_data.get('description')}")
                return None
            file_path = file_data["result"]["file_path"]
            _TG_AVATAR_CACHE[user_id] = (file_path, now + _TG_AVATAR_TTL)
            return file_path
    except Exception as e:
        logger.warning(f"Telegram avatar resolve failed for user {user_id}: {e}")
        return None


@api_router.get("/telegram/avatar/{user_id}")
async def get_telegram_avatar(user_id: int, current: dict = Depends(get_current_user)):
    """Метаданные аватара. Возвращает ВНУТРЕННИЙ относительный URL прокси —
    bot-токен больше не попадает в ответ (была утечка секрета)."""
    if current["telegram_id"] != user_id and not await _is_coach_of(current["telegram_id"], user_id):
        raise HTTPException(status_code=403, detail="Нет доступа к аватару этого пользователя")
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not configured")
        return {"avatar_url": None, "error": "Bot token not configured"}
    file_path = await _resolve_telegram_avatar_file(user_id)
    if not file_path:
        return {"avatar_url": None, "message": "User has no profile photo"}
    return {"avatar_url": f"/api/telegram/avatar/{user_id}/file"}


@api_router.get("/telegram/avatar/{user_id}/file")
async def get_telegram_avatar_file(user_id: int, current: dict = Depends(get_current_user)):
    """Проксирует бинарный файл аватара из Telegram, скрывая bot-токен."""
    if current["telegram_id"] != user_id and not await _is_coach_of(current["telegram_id"], user_id):
        raise HTTPException(status_code=403, detail="Нет доступа к аватару этого пользователя")
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=404, detail="Avatar unavailable")
    file_path = await _resolve_telegram_avatar_file(user_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Avatar not found")
    try:
        async with httpx.AsyncClient(timeout=15.0) as http_client:
            r = await http_client.get(
                f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            )
            if r.status_code != 200:
                raise HTTPException(status_code=404, detail="Avatar unavailable")
            return Response(
                content=r.content,
                media_type=r.headers.get("content-type", "image/jpeg"),
                headers={"Cache-Control": "public, max-age=3600"},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Telegram avatar proxy failed for user {user_id}: {e}")
        raise HTTPException(status_code=404, detail="Avatar unavailable")

# ===========================================================================
# PHASE 1 — Программы и Планы
# ===========================================================================

# ---- Справочник упражнений ----
@api_router.get("/exercises", response_model=List[Exercise])
async def list_exercises(query: Optional[str] = None, muscle: Optional[str] = None,
                         owner: Optional[int] = None,
                         current: dict = Depends(get_current_user)):
    filt = {}
    if query:
        # re.escape — иначе пользовательский ввод трактуется как regex (ReDoS/инъекция).
        filt["name"] = {"$regex": re.escape(query[:100]), "$options": "i"}
    if muscle:
        filt["muscle_groups"] = muscle
    if owner is not None:
        # Чужие кастомные упражнения — только тренер этого спортсмена.
        if owner != current["telegram_id"] and not await _is_coach_of(current["telegram_id"], owner):
            raise HTTPException(status_code=403, detail="Нет доступа к упражнениям этого спортсмена")
        filt["$or"] = [{"is_builtin": True}, {"owner_telegram_id": owner}]
    else:
        # по умолчанию отдаём встроенные + свои кастомные
        filt["$or"] = [{"is_builtin": True}, {"owner_telegram_id": current["telegram_id"]}]
    docs = await db.exercises.find(filt, {"_id": 0}).to_list(1000)
    return docs


@api_router.post("/exercises", response_model=Exercise)
async def create_exercise(payload: ExerciseCreate, current: dict = Depends(get_current_user)):
    payload.owner_telegram_id = current["telegram_id"]
    ex = Exercise(**payload.model_dump(), is_builtin=False)
    doc = ex.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.exercises.insert_one(doc)
    logger.info(f"Custom exercise created: {ex.name} (owner={ex.owner_telegram_id})")
    return ex


# ---- Шаблоны программ (библиотека / конструктор / импорт / шаринг) ----
_SHARE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _new_share_code():
    return "TWB-" + "".join(secrets.choice(_SHARE_ALPHABET) for _ in range(6))


_bot_username_cache = {"value": None, "checked": False}


async def _get_bot_username():
    """Username бота (для deep-link t.me/<bot>?startapp=...). Ленивый кэш getMe."""
    if _bot_username_cache["checked"]:
        return _bot_username_cache["value"]
    _bot_username_cache["checked"] = True
    if not TELEGRAM_BOT_TOKEN:
        return None
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe")
            d = r.json()
            if d.get("ok"):
                _bot_username_cache["value"] = (d.get("result") or {}).get("username")
    except Exception as e:
        logger.warning(f"Failed to get bot username from cache: {e}")
    return _bot_username_cache["value"]


def _template_recount(doc):
    """Пересчёт производных полей шаблона (weeks_count / days_per_week)."""
    weeks = doc.get("weeks") or []
    doc["weeks_count"] = len(weeks)
    dpw = 0
    for w in weeks:
        n = len([d for d in (w.get("days") or []) if not d.get("is_rest")])
        dpw = max(dpw, n)
    if dpw:
        doc["days_per_week"] = dpw
    return doc


def _template_exercise_count(doc):
    total = 0
    for w in (doc.get("weeks") or []):
        for d in (w.get("days") or []):
            total += len(d.get("exercises") or [])
    return total


def _template_first_week_preview(doc):
    """Компактное превью 1-й недели: карточки дней со списком упражнений."""
    weeks = doc.get("weeks") or []
    if not weeks:
        return []
    days = weeks[0].get("days") or []
    out = []
    for d in days:
        if d.get("is_rest"):
            continue
        exs = []
        for e in (d.get("exercises") or [])[:12]:
            scheme = [
                {"weight": s.get("weight"), "sets": s.get("sets"), "reps": s.get("reps")}
                for s in (e.get("sets_scheme") or [])
            ]
            exs.append({
                "name": e.get("exercise_name") or "",
                "muscle_group": e.get("muscle_group"),
                "lift_group": e.get("lift_group"),
                "is_accessory": bool(e.get("is_accessory")),
                "target_sets": e.get("target_sets"),
                "target_reps": e.get("target_reps"),
                "sets_scheme": scheme,
            })
        out.append({
            "day_index": d.get("day_index"),
            "title": d.get("title") or "",
            "exercises": exs,
        })
    return out


def _template_forecast(doc):
    """Прогноз прогресса. Для программ в кг — тоннаж по неделям + рост %.
    Для программ на %1ПМ (requires_maxes=True) — интенсивность (доля от base_max
    основного движения) по неделям.
    """
    weeks = doc.get("weeks") or []
    is_percent = bool(doc.get("requires_maxes"))
    base = doc.get("base_maxes") or {}
    weekly_tonnage = []
    weekly_intensity = []
    for idx, w in enumerate(weeks):
        wi = int(w.get("week_index") or (idx + 1))
        tonnage = 0.0
        pct_top = 0.0
        pct_sum = 0.0
        pct_n = 0
        for d in (w.get("days") or []):
            if d.get("is_rest"):
                continue
            for e in (d.get("exercises") or []):
                lg = e.get("lift_group")
                base_max = base.get(lg) if lg else None
                for s in (e.get("sets_scheme") or []):
                    try:
                        w_val = float(s.get("weight") or 0)
                        n_sets = int(s.get("sets") or 0)
                        reps = int(s.get("reps") or 0)
                    except (TypeError, ValueError):
                        continue
                    if w_val and n_sets and reps:
                        tonnage += w_val * n_sets * reps
                    if is_percent and lg and w_val:
                        bm = float(base_max) if base_max else 100.0
                        pct = (w_val / bm) * 100.0 if bm else 0.0
                        if pct > 0:
                            pct_top = max(pct_top, pct)
                            pct_sum += pct
                            pct_n += 1
        weekly_tonnage.append({"week": wi, "tonnage": round(tonnage, 1)})
        if is_percent:
            weekly_intensity.append({
                "week": wi,
                "top_percent": round(pct_top, 1),
                "avg_percent": round(pct_sum / pct_n, 1) if pct_n else 0.0,
            })

    if is_percent:
        non_empty = [x for x in weekly_intensity if x["top_percent"] > 0]
        first_p = non_empty[0]["top_percent"] if non_empty else None
        last_p = non_empty[-1]["top_percent"] if non_empty else None
        growth = round(last_p - first_p, 1) if (first_p is not None and last_p is not None) else None
        return {
            "is_percent_based": True,
            "weekly_intensity": weekly_intensity,
            "first_percent": first_p,
            "last_percent": last_p,
            "growth_points": growth,
        }

    non_empty = [x for x in weekly_tonnage if x["tonnage"] > 0]
    first_t = non_empty[0]["tonnage"] if non_empty else None
    last_t = non_empty[-1]["tonnage"] if non_empty else None
    growth = None
    if first_t and last_t is not None:
        growth = round((last_t - first_t) / first_t * 100, 1)
    return {
        "is_percent_based": False,
        "weekly_tonnage": weekly_tonnage,
        "first_tonnage": first_t,
        "last_tonnage": last_t,
        "growth_pct": growth,
    }


async def _get_own_template_or_403(template_id: str, current: dict):
    doc = await db.programs.find_one({"id": template_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Программа не найдена")
    if doc.get("is_builtin") or doc.get("owner_telegram_id") != current.get("telegram_id"):
        raise HTTPException(status_code=403, detail="Можно изменять только свои программы")
    return doc


@api_router.get("/programs/templates", response_model=List[ProgramTemplate])
async def list_templates(level: Optional[str] = None, goal: Optional[str] = None,
                         current: dict = Depends(get_current_user)):
    filt = {"$or": [{"is_builtin": True}, {"owner_telegram_id": current.get("telegram_id")}]}
    if level:
        filt["level"] = level
    if goal:
        filt["goal"] = goal
    docs = await db.programs.find(filt, {"_id": 0}).to_list(1000)
    docs.sort(key=lambda t: (not t.get("is_builtin"), t.get("created_at") or ""))
    return docs


@api_router.get("/programs/templates/{template_id}", response_model=ProgramTemplate)
async def get_template(template_id: str, current: dict = Depends(get_current_user)):
    doc = await db.programs.find_one({"id": template_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    if not doc.get("is_builtin") and doc.get("owner_telegram_id") != current.get("telegram_id"):
        raise HTTPException(status_code=403, detail="Нет доступа к этой программе")
    return doc


@api_router.post("/programs/templates", response_model=ProgramTemplate)
async def create_template(payload: ProgramTemplateCreate,
                          current: dict = Depends(get_current_user)):
    tpl = ProgramTemplate(
        **{**payload.model_dump(), "owner_telegram_id": current.get("telegram_id")},
        is_builtin=False,
    )
    doc = tpl.model_dump()
    if not doc.get("source"):
        doc["source"] = "constructor"
    _template_recount(doc)
    doc["created_at"] = doc["created_at"].isoformat()
    doc["updated_at"] = doc["updated_at"].isoformat()
    await db.programs.insert_one(dict(doc))
    logger.info(f"Custom template created: {tpl.name} (owner={current.get('telegram_id')})")
    return doc


@api_router.patch("/programs/templates/{template_id}", response_model=ProgramTemplate)
async def update_template(template_id: str, payload: ProgramTemplateUpdate,
                          current: dict = Depends(get_current_user)):
    doc = await _get_own_template_or_403(template_id, current)
    upd = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    doc.update(upd)
    _template_recount(doc)
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.programs.update_one({"id": template_id}, {"$set": {k: doc[k] for k in
        list(upd.keys()) + ["weeks_count", "days_per_week", "updated_at"] if k in doc}})
    return doc


@api_router.delete("/programs/templates/{template_id}")
async def delete_template(template_id: str, current: dict = Depends(get_current_user)):
    await _get_own_template_or_403(template_id, current)
    res = await db.programs.delete_one({"id": template_id})
    # Деактивируем активные планы этого пользователя, ссылающиеся на удалённый шаблон
    tgid = current.get("telegram_id")
    now_iso = datetime.now(timezone.utc).isoformat()
    upd = await db.plans.update_many(
        {"source_template_id": template_id, "athlete_telegram_id": tgid,
         "status": {"$in": ["active", "draft"]}},
        {"$set": {"status": "completed", "updated_at": now_iso}},
    )
    return {"deleted": res.deleted_count, "plans_cancelled": upd.modified_count}


@api_router.post("/programs/templates/{template_id}/share")
async def share_template(template_id: str, current: dict = Depends(get_current_user)):
    """Владелец получает короткий код и ссылки для шаринга программы."""
    doc = await _get_own_template_or_403(template_id, current)
    code = doc.get("share_code")
    if not code:
        for _ in range(10):
            code = _new_share_code()
            if not await db.programs.find_one({"share_code": code}, {"_id": 0, "id": 1}):
                break
        await db.programs.update_one({"id": template_id}, {"$set": {
            "share_code": code, "updated_at": datetime.now(timezone.utc).isoformat()}})
    bot = await _get_bot_username()
    return {
        "code": code,
        "web_path": f"/import/{code}",
        "tg_link": f"https://t.me/{bot}?startapp=import_{code.replace('-', '_')}" if bot else None,
    }


@api_router.get("/programs/shared/{code}")
async def get_shared_program(code: str):
    """ПУБЛИЧНОЕ превью программы по коду (для landing-страницы ссылки)."""
    norm = code.strip().upper().replace("_", "-")
    if not norm.startswith("TWB-"):
        norm = f"TWB-{norm}"
    doc = await db.programs.find_one({"share_code": norm}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Программа по этому коду не найдена")
    owner = await db.users.find_one(
        {"telegram_id": doc.get("owner_telegram_id")}, {"_id": 0, "first_name": 1})
    bot = await _get_bot_username()
    return {
        "code": norm,
        "name": doc.get("name"),
        "description": doc.get("description") or "",
        "level": doc.get("level"),
        "goal": doc.get("goal"),
        "weeks_count": doc.get("weeks_count") or len(doc.get("weeks") or []),
        "days_per_week": doc.get("days_per_week"),
        "exercises_count": _template_exercise_count(doc),
        "requires_maxes": bool(doc.get("requires_maxes")),
        "author_name": (owner or {}).get("first_name") or doc.get("author") or "Пользователь TWB",
        "week1_days": _template_first_week_preview(doc),
        "forecast": _template_forecast(doc),
        "tg_link": f"https://t.me/{bot}?startapp=import_{norm.replace('-', '_')}" if bot else None,
    }


@api_router.post("/programs/import/{code}")
async def import_shared_program(code: str, current: dict = Depends(get_current_user)):
    """Импорт программы по коду — копия появляется в «Моих программах»."""
    norm = code.strip().upper().replace("_", "-")
    if not norm.startswith("TWB-"):
        norm = f"TWB-{norm}"
    src = await db.programs.find_one({"share_code": norm}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Программа по этому коду не найдена")
    tgid = current.get("telegram_id")
    if src.get("owner_telegram_id") == tgid:
        return {"template": src, "already_imported": True, "own": True}
    existing = await db.programs.find_one(
        {"owner_telegram_id": tgid, "shared_from": src["id"]}, {"_id": 0})
    if existing:
        return {"template": existing, "already_imported": True, "own": False}
    owner = await db.users.find_one(
        {"telegram_id": src.get("owner_telegram_id")}, {"_id": 0, "first_name": 1})
    now = datetime.now(timezone.utc).isoformat()
    new_doc = {
        **src,
        "id": str(uuid.uuid4()),
        "slug": None,
        "is_builtin": False,
        "owner_telegram_id": tgid,
        "source": "import",
        "shared_from": src["id"],
        "share_code": None,
        "author": src.get("author") or (owner or {}).get("first_name") or "",
        "created_at": now,
        "updated_at": now,
    }
    await db.programs.insert_one(dict(new_doc))
    new_doc.pop("_id", None)
    logger.info(f"Program imported by {tgid} via code {norm}")
    return {"template": new_doc, "already_imported": False, "own": False}


# ---- Планы (назначенный экземпляр программы = снимок шаблона) ----
def _round_2_5(x):
    """Округление веса до ближайших 2.5 кг."""
    return round(round(float(x) / 2.5) * 2.5, 2)


def _remap_week_days(weeks, training_days):
    """Ремаппит тренировочные (не-rest) дни снимка плана на выбранные дни недели.

    day_index = 1..7 (Пн..Вс). Берёт непустые дни каждой недели по их текущему
    порядку и расставляет на выбранные дни. Гарантирует уникальность day_index в
    неделе (без коллизий): если тренировок больше, чем выбрано дней, лишние
    занимают ближайшие свободные дни недели. Дни отдыха не хранятся
    (отсутствующий день недели = отдых)."""
    td = sorted({int(x) for x in (training_days or []) if 1 <= int(x) <= 7})
    if not td:
        return weeks
    out = copy.deepcopy(weeks)
    # Слоты: сначала выбранные дни, затем остальные дни недели (для overflow без коллизий)
    slots = td + [x for x in range(1, 8) if x not in td]
    for w in out:
        workout_days = sorted(
            [d for d in (w.get("days") or []) if not d.get("is_rest")],
            key=lambda d: d.get("day_index", 0),
        )
        for i, d in enumerate(workout_days):
            d["day_index"] = slots[i] if i < len(slots) else (i + 1)
        workout_days.sort(key=lambda d: d.get("day_index", 0))
        w["days"] = workout_days
    return out


def _scale_and_map_weeks(weeks, tpl, maxes, training_days):
    """Масштабирует веса под максимумы спортсмена и ремаппит дни недели.
    Возвращает (weeks_copy, scaled_one_rep_max)."""
    weeks = copy.deepcopy(weeks)
    base = tpl.get("base_maxes") or {}
    default_orm = dict(tpl.get("default_one_rep_max") or {})
    scaled_orm = dict(default_orm)

    # Коэффициенты масштабирования по группам (squat/bench/deadlift)
    factors = {}
    if maxes and base:
        for g in ("squat", "bench", "deadlift"):
            try:
                if base.get(g) and maxes.get(g):
                    factors[g] = float(maxes[g]) / float(base[g])
            except (TypeError, ValueError):
                pass

    # slug -> lift_group (для масштабирования референсных 1ПМ)
    slug_lift = {}
    if factors:
        for w in weeks:
            for d in w.get("days", []):
                for e in d.get("exercises", []):
                    slug = e.get("exercise_slug")
                    lg = e.get("lift_group")
                    if slug and lg:
                        slug_lift[slug] = lg
                    f = factors.get(lg)
                    if not f:
                        continue
                    for s in e.get("sets_scheme", []) or []:
                        if s.get("weight") is not None:
                            s["weight"] = _round_2_5(float(s["weight"]) * f)
        for slug, ref in default_orm.items():
            f = factors.get(slug_lift.get(slug))
            scaled_orm[slug] = round(float(ref) * f, 1) if f else ref

    # Ремаппинг дней недели: тренировочные дни шаблона -> выбранные пользователем
    if training_days:
        weeks = _remap_week_days(weeks, training_days)

    return weeks, scaled_orm


@api_router.post("/plans", response_model=Plan)
async def create_plan(payload: PlanCreate, current: dict = Depends(get_current_user)):
    # Авторизация: план можно создавать себе (self-coached) или своему подопечному
    caller = current.get("telegram_id")
    if caller != payload.athlete_telegram_id and not await _is_coach_of(caller, payload.athlete_telegram_id):
        raise HTTPException(status_code=403, detail="Создавать план можно только себе или своему подопечному")

    weeks = payload.weeks
    name = payload.name
    source_template_id = payload.template_id
    one_rep_max = payload.one_rep_max or {}
    maxes = payload.maxes or {}
    training_days = payload.training_days or []

    if payload.template_id:
        tpl = await db.programs.find_one({"id": payload.template_id}, {"_id": 0})
        if not tpl:
            raise HTTPException(status_code=404, detail="Template not found")
        weeks = tpl["weeks"]  # снимок структуры
        if not name:
            name = tpl["name"]
        if not one_rep_max:
            one_rep_max = tpl.get("default_one_rep_max") or {}
        # Масштабирование весов под максимумы спортсмена + ремаппинг дней недели
        if maxes or training_days:
            weeks, scaled_orm = _scale_and_map_weeks(weeks, tpl, maxes, training_days)
            if maxes:
                one_rep_max = scaled_orm

    if weeks is None:
        raise HTTPException(status_code=400, detail="Either template_id or weeks must be provided")

    # Один активный план: прежние активные планы спортсмена помечаем завершёнными
    # (перенесено ниже — зависит от вычисленного статуса: черновик не замещает план)

    # Видимость: тренер, готовящий план другому спортсмену → по умолчанию черновик
    coach_id = payload.coach_telegram_id
    is_coach_prepared = bool(coach_id and coach_id != payload.athlete_telegram_id)
    if payload.visibility in ("draft", "published"):
        visibility = payload.visibility
    else:
        visibility = "draft" if is_coach_prepared else "published"
    prepared_by_coach = payload.prepared_by_coach or is_coach_prepared
    now_iso = datetime.now(timezone.utc).isoformat()

    # Статус: опубликованный план становится единственным «живым» планом спортсмена;
    # черновик тренера НЕ замещает и НЕ гасит текущий рабочий план спортсмена (B2).
    status = "active" if visibility == "published" else "draft"
    if status == "active":
        await db.plans.update_many(
            {"athlete_telegram_id": payload.athlete_telegram_id,
             "status": {"$in": ["active", "draft"]}},
            {"$set": {"status": "completed", "updated_at": now_iso}},
        )

    plan = Plan(
        athlete_telegram_id=payload.athlete_telegram_id,
        coach_telegram_id=payload.coach_telegram_id,
        source_template_id=source_template_id,
        name=name or "Мой план",
        status=status,
        start_date=payload.start_date,
        weeks=weeks,
        one_rep_max=one_rep_max,
        maxes=maxes,
        training_days=sorted(set(int(d) for d in training_days)) if training_days else [],
        visibility=visibility,
        published_at=now_iso if visibility == "published" else None,
        prepared_by_coach=prepared_by_coach,
    )
    doc = plan.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    doc["updated_at"] = doc["updated_at"].isoformat()
    await db.plans.insert_one(doc)
    logger.info(f"Plan created: {plan.id} for athlete={plan.athlete_telegram_id} (visibility={visibility})")
    return plan


@api_router.get("/plans/active/{telegram_id}", response_model=Optional[Plan])
async def get_active_plan(telegram_id: int, current: dict = Depends(get_current_user)):
    # IDOR-защита: активный план отдаём самому спортсмену или его тренеру.
    if current["telegram_id"] != telegram_id and not await _is_coach_of(current["telegram_id"], telegram_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    doc = await db.plans.find_one(
        {"athlete_telegram_id": telegram_id, "status": "active"},
        {"_id": 0},
    )
    if not doc:
        # Активного плана нет, но тренер мог готовить черновик «заранее» —
        # показываем спортсмену «план готовится» без содержимого (B2).
        draft = await db.plans.find_one(
            {"athlete_telegram_id": telegram_id, "status": "draft"},
            {"_id": 0}, sort=[("updated_at", -1)],
        )
        if draft:
            draft["weeks"] = []
            return draft
        return None
    # Черновик тренера: спортсмену не показываем содержимое («план готовится»)
    if doc.get("visibility") == "draft":
        doc["weeks"] = []
        return doc
    # Опубликованный план: скрываем содержимое ещё не открытых недель (B3),
    # сохраняя сами недели (с флагом published) для корректной навигации.
    for w in doc.get("weeks", []) or []:
        if w.get("published") is False:
            w["days"] = []
    return doc  # может быть None → вернётся null


@api_router.get("/plans/{plan_id}", response_model=Plan)
async def get_plan(plan_id: str, current: dict = Depends(get_current_user)):
    doc = await db.plans.find_one({"id": plan_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Plan not found")
    # IDOR-защита: владелец, назначенный тренер или активный тренер спортсмена.
    tgid = current["telegram_id"]
    if (doc.get("athlete_telegram_id") != tgid
            and doc.get("coach_telegram_id") != tgid
            and not await _is_coach_of(tgid, doc.get("athlete_telegram_id"))):
        raise HTTPException(status_code=403, detail="Forbidden")
    return doc


@api_router.post("/plans/{plan_id}/cancel")
async def cancel_plan(plan_id: str, current: dict = Depends(get_current_user)):
    """Спортсмен отменяет выбор программы. Сессии/прогресс сохраняются, план — «completed»."""
    doc = await db.plans.find_one({"id": plan_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Plan not found")
    tgid = current.get("telegram_id")
    if doc.get("athlete_telegram_id") != tgid:
        raise HTTPException(status_code=403, detail="Not your plan")
    if doc.get("status") not in ("active", "draft"):
        return {"status": doc.get("status") or "completed", "cancelled": False}
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.plans.update_one(
        {"id": plan_id},
        {"$set": {"status": "completed", "updated_at": now_iso}},
    )
    return {"status": "completed", "cancelled": True}


# ===========================================================================
# P6 — Шаринг плана (read-only) и экспорт
# ===========================================================================
def _plan_public_snapshot(plan: dict) -> dict:
    """Снимок плана для публичной ссылки: без персональных id/максимумов."""
    return {
        "id": plan.get("id"),
        "name": plan.get("name"),
        "current_week": plan.get("current_week", 1),
        "training_days": plan.get("training_days", []),
        "weeks": plan.get("weeks", []),
    }


@api_router.post("/plans/{plan_id}/share")
async def share_plan(plan_id: str, current: dict = Depends(get_current_user)):
    """Включить публичную read-only ссылку на план (владелец/тренер)."""
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    token = plan.get("share_token") or secrets.token_urlsafe(16)
    await db.plans.update_one(
        {"id": plan_id},
        {"$set": {"share_token": token, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"share_token": token}


@api_router.delete("/plans/{plan_id}/share")
async def unshare_plan(plan_id: str, current: dict = Depends(get_current_user)):
    """Выключить публичную ссылку на план."""
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    await db.plans.update_one(
        {"id": plan_id},
        {"$set": {"share_token": None, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True}


@api_router.get("/shared/plan/{token}")
async def get_shared_plan(token: str):
    """Публичный read-only снимок плана по токену (без авторизации)."""
    if not token:
        raise HTTPException(status_code=404, detail="Not found")
    plan = await db.plans.find_one({"share_token": token}, {"_id": 0})
    if not plan:
        raise HTTPException(status_code=404, detail="Ссылка не найдена или отключена")
    return _plan_public_snapshot(plan)


@api_router.get("/plans/{plan_id}/export")
async def export_plan(plan_id: str, current: dict = Depends(get_current_user)):
    """Экспорт плана в Excel (владелец/тренер)."""
    from openpyxl import Workbook
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)

    wb = Workbook()
    ws = wb.active
    ws.title = "План"
    ws.append(["Неделя", "День", "Упражнение", "Подходы", "Повторы", "Вес", "Отдых, с", "Заметки"])
    for week in plan.get("weeks", []) or []:
        for day in week.get("days", []) or []:
            if day.get("is_rest"):
                continue
            for i, ex in enumerate(sorted(day.get("exercises", []) or [], key=lambda x: x.get("order", 0))):
                scheme = ex.get("sets_scheme") or []
                if scheme:
                    sets = "+".join(str(s.get("sets", 1)) for s in scheme)
                    reps = "+".join(str(s.get("reps", "")) for s in scheme)
                    weight = "+".join(str(s.get("weight", "")) if s.get("weight") is not None else "—" for s in scheme)
                else:
                    sets = str(ex.get("target_sets", ""))
                    reps = str(ex.get("target_reps", ""))
                    weight = str(ex.get("target_weight", "")) if ex.get("target_weight") is not None else "—"
                ws.append([
                    week.get("week_index"), day.get("day_index"),
                    ex.get("exercise_name") or ex.get("name") or "",
                    sets, reps, weight,
                    ex.get("rest_seconds", "") or "",
                    ex.get("notes", "") or "",
                ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    safe_name = "".join(c for c in (plan.get("name") or "plan") if c.isalnum() or c in " -_")[:40].strip() or "plan"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.xlsx"'},
    )


# ===========================================================================
# P3 — Приглашения тренера, связь тренер↔спортсмен, подопечные
# ===========================================================================
@api_router.post("/coach/invite")
async def coach_invite(payload: CoachInviteReq, current: dict = Depends(get_current_user)):
    """Тренер получает (или генерирует) invite-код + deep link для приглашения спортсмена."""
    # IDOR-защита: генерировать invite-код можно только для самого себя.
    if payload.coach_telegram_id != current["telegram_id"]:
        raise HTTPException(status_code=403, detail="Not your account")
    user = await db.users.find_one({"telegram_id": payload.coach_telegram_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    roles = set(user.get("roles") or ["athlete"])
    roles.update(["athlete", "coach"])
    set_fields = {"roles": sorted(roles), "updated_at": datetime.now(timezone.utc).isoformat()}
    code = user.get("invite_code")
    if not code:
        code = await _unique_invite_code()
        set_fields["invite_code"] = code
    await db.users.update_one({"telegram_id": payload.coach_telegram_id}, {"$set": set_fields})

    bot = await _get_bot_username()
    deep_link = f"https://t.me/{bot}?startapp=coach_{code}" if bot else None
    return {"invite_code": code, "deep_link": deep_link, "bot_username": bot}


@api_router.post("/coach/link")
async def coach_link(payload: CoachLinkReq, current: dict = Depends(get_current_user)):
    """Спортсмен привязывается к тренеру по коду (инициатива спортсмена = согласие → active)."""
    # IDOR-защита: привязать можно только собственный аккаунт.
    if payload.athlete_telegram_id != current["telegram_id"]:
        raise HTTPException(status_code=403, detail="Not your account")
    code = (payload.code or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Код не указан")
    coach = await db.users.find_one({"invite_code": code}, {"_id": 0})
    if not coach:
        raise HTTPException(status_code=404, detail="Тренер с таким кодом не найден")
    coach_tgid = coach["telegram_id"]
    if coach_tgid == payload.athlete_telegram_id:
        raise HTTPException(status_code=400, detail="Нельзя привязать самого себя")

    athlete = await db.users.find_one({"telegram_id": payload.athlete_telegram_id}, {"_id": 0})
    if not athlete:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")

    now = datetime.now(timezone.utc).isoformat()
    existing = await db.coach_links.find_one(
        {"coach_telegram_id": coach_tgid, "athlete_telegram_id": payload.athlete_telegram_id},
        {"_id": 0},
    )
    if existing:
        await db.coach_links.update_one(
            {"coach_telegram_id": coach_tgid, "athlete_telegram_id": payload.athlete_telegram_id},
            {"$set": {"status": "active", "updated_at": now}},
        )
    else:
        link = CoachLink(coach_telegram_id=coach_tgid, athlete_telegram_id=payload.athlete_telegram_id)
        doc = link.model_dump()
        doc["created_at"] = doc["created_at"].isoformat()
        doc["updated_at"] = doc["updated_at"].isoformat()
        await db.coach_links.insert_one(doc)

    # У спортсмена один активный тренер: ревокируем прочие активные связи (B1)
    await db.coach_links.update_many(
        {"athlete_telegram_id": payload.athlete_telegram_id,
         "coach_telegram_id": {"$ne": coach_tgid}, "status": "active"},
        {"$set": {"status": "revoked", "updated_at": now}},
    )
    await db.users.update_one(
        {"telegram_id": payload.athlete_telegram_id},
        {"$set": {
            "coach_telegram_id": coach_tgid,
            "access_tier": athlete.get("access_tier") or "coach_managed",
            "permissions": athlete.get("permissions") or _default_permissions("coach_managed"),
            "onboarded_at": athlete.get("onboarded_at") or now,
            "updated_at": now,
        }},
    )
    logger.info(f"Coach link: coach={coach_tgid} <- athlete={payload.athlete_telegram_id}")
    return {"status": "active", "coach": _user_brief(coach)}


@api_router.post("/coach/unlink")
async def coach_unlink(payload: CoachUnlinkReq, current: dict = Depends(get_current_user)):
    """Спортсмен отвязывается от текущего тренера."""
    # IDOR-защита: отвязать можно только собственный аккаунт.
    if payload.athlete_telegram_id != current["telegram_id"]:
        raise HTTPException(status_code=403, detail="Not your account")
    athlete = await db.users.find_one({"telegram_id": payload.athlete_telegram_id}, {"_id": 0})
    if not athlete:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")
    coach_tgid = athlete.get("coach_telegram_id")
    now = datetime.now(timezone.utc).isoformat()
    if coach_tgid:
        await db.coach_links.update_one(
            {"coach_telegram_id": coach_tgid, "athlete_telegram_id": payload.athlete_telegram_id},
            {"$set": {"status": "revoked", "updated_at": now}},
        )
    await db.users.update_one(
        {"telegram_id": payload.athlete_telegram_id},
        {"$set": {"coach_telegram_id": None, "updated_at": now}},
    )
    return {"ok": True}


@api_router.get("/athlete/{telegram_id}/coach")
async def athlete_coach(telegram_id: int, current: dict = Depends(get_current_user)):
    """Текущий тренер спортсмена (или null)."""
    athlete = await db.users.find_one({"telegram_id": telegram_id}, {"_id": 0})
    if not athlete:
        raise HTTPException(status_code=404, detail="User not found")
    # Доступ: сам спортсмен или его тренер.
    if current["telegram_id"] != telegram_id and not await _is_coach_of(current["telegram_id"], telegram_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    coach_tgid = athlete.get("coach_telegram_id")
    if not coach_tgid:
        return {"coach": None}
    coach = await db.users.find_one({"telegram_id": coach_tgid}, {"_id": 0})
    return {"coach": _user_brief(coach)}


@api_router.get("/coach/{telegram_id}/clients")
async def coach_clients(telegram_id: int, current: dict = Depends(get_current_user)):
    """Список подопечных тренера + краткая активность (активный план, последняя/текущая сессия)."""
    # IDOR-защита: список подопечных отдаём только самому тренеру.
    if current["telegram_id"] != telegram_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    links = await db.coach_links.find(
        {"coach_telegram_id": telegram_id, "status": "active"}, {"_id": 0}
    ).to_list(500)
    if not links:
        return {"coach_telegram_id": telegram_id, "clients": []}

    # Батч-выборки вместо N+1 (было 4 запроса на каждого подопечного).
    athlete_ids = [link["athlete_telegram_id"] for link in links]

    users = await db.users.find(
        {"telegram_id": {"$in": athlete_ids}}, {"_id": 0}
    ).to_list(len(athlete_ids))
    users_by_id = {u["telegram_id"]: u for u in users}

    # План: приоритет черновику (готовится тренером), иначе активному (B2).
    actives = await db.plans.find(
        {"athlete_telegram_id": {"$in": athlete_ids}, "status": "active"}, {"_id": 0}
    ).to_list(1000)
    drafts = await db.plans.find(
        {"athlete_telegram_id": {"$in": athlete_ids}, "status": "draft"}, {"_id": 0}
    ).sort("updated_at", -1).to_list(1000)
    plan_by_athlete = {}
    for p in actives:
        plan_by_athlete.setdefault(p["athlete_telegram_id"], p)
    # Первый черновик в отсортированном по updated_at убыв. списке — самый свежий.
    for p in drafts:
        plan_by_athlete[p["athlete_telegram_id"]] = p

    active_sessions = await db.workout_sessions.find(
        {"athlete_telegram_id": {"$in": athlete_ids}, "status": "in_progress"},
        {"_id": 0, "id": 1, "athlete_telegram_id": 1},
    ).to_list(1000)
    active_by_athlete = {}
    for s in active_sessions:
        active_by_athlete.setdefault(s["athlete_telegram_id"], s)

    # Последняя завершённая тренировка каждого подопечного — одной агрегацией.
    last_by_athlete = {}
    async for row in db.workout_sessions.aggregate([
        {"$match": {"athlete_telegram_id": {"$in": athlete_ids}, "status": "finished"}},
        {"$sort": {"finished_at": -1}},
        {"$group": {"_id": "$athlete_telegram_id", "finished_at": {"$first": "$finished_at"}}},
    ]):
        last_by_athlete[row["_id"]] = row.get("finished_at")

    clients = []
    for link in links:
        a_id = link["athlete_telegram_id"]
        plan = plan_by_athlete.get(a_id)
        active_session = active_by_athlete.get(a_id)
        clients.append({
            "athlete": _user_brief(users_by_id.get(a_id)),
            "plan": ({
                "id": plan["id"], "name": plan.get("name"),
                "visibility": plan.get("visibility", "published"),
                "current_week": plan.get("current_week", 1),
                "weeks_count": len(plan.get("weeks", [])),
                "prepared_by_coach": plan.get("prepared_by_coach", False),
            } if plan else None),
            "is_training_now": bool(active_session),
            "active_session_id": active_session["id"] if active_session else None,
            "last_workout_at": last_by_athlete.get(a_id),
            "linked_at": link.get("created_at"),
        })
    return {"coach_telegram_id": telegram_id, "clients": clients}


async def _assert_coach_of(coach_tgid: int, athlete_tgid: int):
    link = await db.coach_links.find_one(
        {"coach_telegram_id": coach_tgid, "athlete_telegram_id": athlete_tgid, "status": "active"},
        {"_id": 0},
    )
    if not link:
        raise HTTPException(status_code=403, detail="Вы не тренер этого спортсмена")


async def _is_coach_of(coach_tgid: int, athlete_tgid: int) -> bool:
    link = await db.coach_links.find_one(
        {"coach_telegram_id": coach_tgid, "athlete_telegram_id": athlete_tgid, "status": "active"},
        {"_id": 0},
    )
    return bool(link)


async def _assert_can_read_stats(current: dict, athlete_tgid: int):
    """Статистику видит только сам спортсмен или его активный тренер."""
    tgid = current.get("telegram_id")
    if tgid == athlete_tgid:
        return
    if await _is_coach_of(tgid, athlete_tgid):
        return
    raise HTTPException(status_code=403, detail="Нет доступа к этой статистике")


async def _assert_can_edit_plan(current: dict, plan: dict):
    """Право на изменение плана: владелец-спортсмен ИЛИ активный тренер спортсмена
    (привязанный или указанный в plan.coach_telegram_id). Иначе 403."""
    tgid = current.get("telegram_id")
    athlete = plan.get("athlete_telegram_id")
    if tgid == athlete:
        return
    if plan.get("coach_telegram_id") == tgid and await _is_coach_of(tgid, athlete):
        return
    if await _is_coach_of(tgid, athlete):
        return
    raise HTTPException(status_code=403, detail="Недостаточно прав для изменения этого плана")


async def _assert_session_read(current: dict, session: dict):
    """Просмотр тренировки: владелец-спортсмен ИЛИ активный тренер спортсмена."""
    tgid = current.get("telegram_id")
    athlete = session.get("athlete_telegram_id")
    if tgid == athlete:
        return
    if await _is_coach_of(tgid, athlete):
        return
    raise HTTPException(status_code=403, detail="Нет доступа к этой тренировке")


async def _assert_session_actor(current: dict, session: dict, actor: str, by: Optional[int]):
    """Изменение тренировки: владелец-спортсмен ИЛИ активный тренер спортсмена.
    Для actor=='coach' дополнительно проверяем, что вызывающий и есть этот тренер."""
    tgid = current.get("telegram_id")
    athlete = session.get("athlete_telegram_id")
    if actor == "coach":
        coach_id = by if by is not None else tgid
        if tgid != coach_id:
            raise HTTPException(status_code=403, detail="Действие от имени другого тренера запрещено")
        await _assert_coach_of(coach_id, athlete)
        return
    if tgid == athlete:
        return
    if await _is_coach_of(tgid, athlete):
        return
    raise HTTPException(status_code=403, detail="Нет доступа к этой тренировке")


async def _resolve_athlete_coach(athlete_tgid: int) -> Optional[int]:
    """Текущий активный тренер спортсмена (по coach_links). None, если нет."""
    link = await db.coach_links.find_one(
        {"athlete_telegram_id": athlete_tgid, "status": "active"},
        {"_id": 0, "coach_telegram_id": 1},
        sort=[("updated_at", -1)],
    )
    return link.get("coach_telegram_id") if link else None


@api_router.get("/coach/{telegram_id}/clients/{athlete_id}/plan", response_model=Optional[Plan])
async def coach_client_plan(telegram_id: int, athlete_id: int,
                            current: dict = Depends(get_current_user)):
    """План подопечного, которым управляет тренер (полный, в т.ч. черновик).
    Приоритет — черновик (готовится тренером), иначе активный план (B2)."""
    # IDOR-защита: смотреть можно только от собственного имени.
    if current["telegram_id"] != telegram_id:
        raise HTTPException(status_code=403, detail="Доступ от имени другого тренера запрещён")
    await _assert_coach_of(telegram_id, athlete_id)
    doc = await db.plans.find_one(
        {"athlete_telegram_id": athlete_id, "status": "draft"}, {"_id": 0},
        sort=[("updated_at", -1)],
    ) or await db.plans.find_one(
        {"athlete_telegram_id": athlete_id, "status": "active"}, {"_id": 0},
    )
    return doc


@api_router.get("/coach/{telegram_id}/clients/{athlete_id}/session")
async def coach_client_session(telegram_id: int, athlete_id: int,
                               current: dict = Depends(get_current_user)):
    """Живая (или последняя) тренировка подопочного для экрана наблюдения тренера.

    Возвращает текущую активную (in_progress) сессию, либо последнюю сессию за
    сегодня. Если активной/сегодняшней сессии нет — `null` (тренировка не идёт).
    Coach-gated: 403, если тренер не привязан к спортсмену.
    """
    if current["telegram_id"] != telegram_id:
        raise HTTPException(status_code=403, detail="Доступ от имени другого тренера запрещён")
    await _assert_coach_of(telegram_id, athlete_id)
    s = await db.workout_sessions.find_one(
        {"athlete_telegram_id": athlete_id, "status": "in_progress"},
        {"_id": 0}, sort=[("created_at", -1)],
    )
    if not s:
        today = datetime.now(timezone.utc).date().isoformat()
        s = await db.workout_sessions.find_one(
            {"athlete_telegram_id": athlete_id, "date": today},
            {"_id": 0}, sort=[("created_at", -1)],
        )
    if not s:
        return None
    return _serialize_session(s)


# ===========================================================================
# Фаза 1 — доступ по инвайту: коды, redeem, права атлета, админ-панель
# Вход в приложение только по инвайт-коду (onboarding gate): /auth/me и
# /me/capabilities отдают onboarded, фронт редиректит на /welcome до redeem.
# ===========================================================================

# Канонический набор прав (см. planTrainWBrain.md §2.3). Расширять — только
# добавлением ключа сюда, иначе админ-оверрайды не применятся.
PERMISSION_KEYS = (
    "log_strength", "log_cardio", "log_nutrition",
    "view_strength", "view_muscle_map", "view_cardio",
    "view_nutrition", "view_forecast", "view_goals",
    "manage_plan", "ai_programs",
)

ACCESS_TIERS = ("coach_managed", "standalone")
ROLES_ALL = ("athlete", "coach", "admin")
INVITE_KINDS = ("coach_client", "standalone", "coach")
INVITE_PRESETS = ("traincee", "standalone", "custom")


def _default_permissions(access_tier: str) -> dict:
    """Профиль прав по умолчанию для access_tier.

    traincee (coach_managed) — «физический подопечный»: силовые заполняет
    тренер (только просмотр), кардио/питание атлет ведёт сам.
    standalone — полное self-service.
    """
    if access_tier == "standalone":
        return {k: True for k in PERMISSION_KEYS}
    return {
        "log_strength": False,
        "log_cardio": True,
        "log_nutrition": True,
        "view_strength": True,
        "view_muscle_map": True,
        "view_cardio": True,
        "view_nutrition": True,
        "view_forecast": True,
        "view_goals": True,
        "manage_plan": False,
        "ai_programs": False,
    }


def _merge_permission_overrides(base: dict, overrides: Optional[dict]) -> dict:
    """Слить базовый профиль с админ-оверрайдами (неизвестные ключи отбрасываются)."""
    clean = {
        k: bool(v)
        for k, v in (overrides or {}).items()
        if k in PERMISSION_KEYS
    }
    merged = dict(base or {})
    merged.update(clean)
    return merged


def _resolve_access_tier(user: Optional[dict]) -> str:
    """Итоговый access_tier. Явное поле > legacy-эвристика (обратная совместимость:
    тренерам/админам — standalone, привязанным к тренеру — coach_managed)."""
    u = user or {}
    tier = u.get("access_tier")
    if tier in ACCESS_TIERS:
        return tier
    roles = u.get("roles") or []
    if any(r in ("coach", "admin") for r in roles):
        return "standalone"
    if u.get("coach_telegram_id"):
        return "coach_managed"
    return "standalone"


def _get_capabilities(user: Optional[dict]) -> dict:
    """Итоговые права: дефолт по access_tier + админ-оверрайды + онбординг."""
    u = user or {}
    roles = sorted({*(u.get("roles") or []), "athlete"})
    tier = _resolve_access_tier(u)
    perms = _merge_permission_overrides(_default_permissions(tier), u.get("permissions"))
    onboarded = bool(u.get("onboarded_at")) or any(r in ("coach", "admin") for r in roles)
    return {
        "roles": roles,
        "access_tier": tier,
        "permissions": perms,
        "onboarded": onboarded,
        "coach_telegram_id": u.get("coach_telegram_id"),
    }


def _assert_admin(user: Optional[dict]) -> None:
    if "admin" not in ((user or {}).get("roles") or []):
        raise HTTPException(status_code=403, detail="Требуются права администратора")


def _validate_invite_for_redeem(invite: Optional[dict], now: Optional[datetime] = None) -> dict:
    """Чистая валидация инвайта для redeem: 404/400 с понятными текстами."""
    if not invite:
        raise HTTPException(status_code=404, detail="Код не найден. Проверьте написание.")
    status = invite.get("status")
    if status == "revoked":
        raise HTTPException(status_code=400, detail="Код отозван администратором.")
    now = now or datetime.now(timezone.utc)
    exp = invite.get("expires_at")
    if exp:
        try:
            exp_dt = datetime.fromisoformat(str(exp))
        except ValueError:
            exp_dt = None
        if exp_dt is not None:
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < now:
                raise HTTPException(status_code=400, detail="Код просрочен.")
    max_uses = int(invite.get("max_uses") or 1)
    if int(invite.get("uses") or 0) >= max_uses:
        raise HTTPException(status_code=400, detail="Код уже использован.")
    return invite


def _invite_preset_permissions(preset: Optional[str], custom: Optional[dict],
                               kind: str) -> dict:
    """Права, выдаваемые атлету при redeem: по пресету или custom-набору."""
    if preset == "standalone":
        return _default_permissions("standalone")
    if preset == "custom":
        return _merge_permission_overrides(_default_permissions("coach_managed"), custom)
    # traincee / по умолчанию
    base = _default_permissions("standalone" if kind == "standalone" else "coach_managed")
    return _merge_permission_overrides(base, custom)


async def _unique_invite_code_db() -> str:
    """Человекочитаемый уникальный код в invite_codes (TWB-XXXXXX)."""
    while True:
        code = f"TWB-{_gen_invite_code(6)}"
        if not await db.invite_codes.find_one({"code": code}, {"_id": 0}):
            return code


def _invite_public(inv: dict) -> dict:
    inv = dict(inv)
    inv.pop("_id", None)
    return inv


async def _get_user_or_404(telegram_id: int) -> dict:
    user = await db.users.find_one({"telegram_id": telegram_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


def _has_role(user: Optional[dict], role: str) -> bool:
    return role in ((user or {}).get("roles") or [])


def _assert_can_selffill_strength(user: Optional[dict], athlete_tgid: int) -> None:
    """Managed-атлет без права log_strength не заполняет силовую сам —
    заполняет тренер (co-scribe / coach-led). Тренер и админ проходят всегда."""
    if (user or {}).get("telegram_id") != athlete_tgid:
        return
    caps = _get_capabilities(user)
    if caps["onboarded"] and not caps["permissions"]["log_strength"]:
        raise HTTPException(status_code=403, detail="Силовую заполняет ваш тренер")


# --- Инвайты ---------------------------------------------------------------

@api_router.post("/invites")
async def create_invite(payload: InviteCreateReq, current: dict = Depends(get_current_user)):
    """Создать инвайт. Тренер — только клиентские коды на себя; админ — любые."""
    is_admin = _has_role(current, "admin")
    is_coach = is_admin or _has_role(current, "coach")
    if not is_coach:
        raise HTTPException(status_code=403, detail="Только тренер или администратор может создавать приглашения")

    kind = (payload.kind or "coach_client").strip()
    if kind not in INVITE_KINDS:
        raise HTTPException(status_code=400, detail="kind должен быть coach_client, standalone или coach")

    if is_admin:
        assigned = payload.assigned_coach_telegram_id
        preset = (payload.preset or ("traincee" if kind == "coach_client" else "standalone"))
    else:
        if kind != "coach_client":
            raise HTTPException(status_code=403, detail="Тренер может создавать только клиентские приглашения")
        assigned = current["telegram_id"]
        preset = payload.preset or "traincee"

    if kind == "coach_client":
        if not assigned:
            raise HTTPException(status_code=400, detail="Не указан тренер для клиентского приглашения")
        coach = await db.users.find_one({"telegram_id": assigned}, {"_id": 0})
        if not coach:
            raise HTTPException(status_code=404, detail="Назначенный тренер не найден")
        if not (_has_role(coach, "coach") or _has_role(coach, "admin")):
            raise HTTPException(status_code=400, detail="Назначенный пользователь не тренер")
    elif kind == "standalone":
        assigned = None

    if preset not in INVITE_PRESETS:
        raise HTTPException(status_code=400, detail="preset должен быть traincee, standalone или custom")
    if payload.max_uses < 1 or payload.max_uses > 100:
        raise HTTPException(status_code=400, detail="max_uses должен быть от 1 до 100")

    expires_at = payload.expires_at
    if expires_at:
        try:
            datetime.fromisoformat(expires_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="expires_at должен быть в формате ISO")

    now = datetime.now(timezone.utc)
    invite = InviteCode(
        code=await _unique_invite_code_db(),
        kind=kind,
        preset=preset,
        created_by=current["telegram_id"],
        assigned_coach_telegram_id=assigned,
        permissions=_invite_preset_permissions(preset, payload.permissions, kind),
        max_uses=payload.max_uses,
        status="active",
        expires_at=expires_at,
        note=(payload.note or None),
        created_at=now,
        updated_at=now,
    )
    doc = invite.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    doc["updated_at"] = doc["updated_at"].isoformat()
    await db.invite_codes.insert_one(doc)
    logger.info(f"Invite created: code={invite.code} kind={kind} by={current['telegram_id']}")
    return _invite_public(doc)


@api_router.get("/invites")
async def list_invites(current: dict = Depends(get_current_user)):
    """Список инвайтов: тренер — свои клиентские, админ — все."""
    is_admin = _has_role(current, "admin")
    is_coach = is_admin or _has_role(current, "coach")
    if not is_coach:
        raise HTTPException(status_code=403, detail="Нет доступа к приглашениям")
    query = {} if is_admin else {
        "created_by": current["telegram_id"],
        "kind": "coach_client",
    }
    docs = await db.invite_codes.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"invites": docs}


@api_router.post("/invites/{invite_id}/revoke")
async def revoke_invite(invite_id: str, current: dict = Depends(get_current_user)):
    """Отозвать инвайт: создатель-тренер или админ."""
    invite = await db.invite_codes.find_one({"id": invite_id}, {"_id": 0})
    if not invite:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")
    is_admin = _has_role(current, "admin")
    if not is_admin and invite.get("created_by") != current["telegram_id"]:
        raise HTTPException(status_code=403, detail="Можно отозвать только своё приглашение")
    await db.invite_codes.update_one(
        {"id": invite_id},
        {"$set": {"status": "revoked", "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "status": "revoked"}


@api_router.post("/invites/redeem")
async def redeem_invite(payload: InviteRedeemReq, current: dict = Depends(get_current_user)):
    """Применить инвайт-код: выдаёт доступ (onboarded), tier и права из инвайта."""
    code = (payload.code or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Код не указан")
    if len(code) > 32:
        raise HTTPException(status_code=400, detail="Код неверный. Проверьте написание.")

    invite = await db.invite_codes.find_one({"code": code}, {"_id": 0})
    if not invite and not code.startswith("TWB-"):
        # Терпим ввод без префикса: «7K2M9Q» → «TWB-7K2M9Q».
        invite = await db.invite_codes.find_one({"code": f"TWB-{code}"}, {"_id": 0})
    _validate_invite_for_redeem(invite)
    invite = _invite_public(invite)

    user = await _get_user_or_404(current["telegram_id"])
    # Идемпотентный повтор того же кода — просто возвращаем capabilities.
    if user.get("redeemed_invite_id") == invite["id"]:
        return _get_capabilities(user)
    if user.get("onboarded_at"):
        raise HTTPException(status_code=400, detail="Доступ уже выдан. Обратитесь к администратору для смены режима.")

    # Атомарный захват использования (гонка двух redeem одного кода).
    from pymongo import ReturnDocument
    claimed = await db.invite_codes.find_one_and_update(
        {"id": invite["id"], "status": "active", "uses": {"$lt": int(invite.get("max_uses") or 1)}},
        {"$inc": {"uses": 1}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        raise HTTPException(status_code=400, detail="Код уже использован.")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    tgid = current["telegram_id"]
    kind = invite.get("kind")
    set_fields = {
        "access_tier": "standalone" if kind == "standalone" else "coach_managed",
        "permissions": invite.get("permissions") or _default_permissions("coach_managed"),
        "permissions_updated_at": now_iso,
        "onboarded_at": now_iso,
        "redeemed_invite_id": invite["id"],
        "updated_at": now_iso,
    }
    roles = set(user.get("roles") or [])
    if kind == "coach":
        roles.update({"coach", "athlete"})
        set_fields["access_tier"] = user.get("access_tier") or "standalone"
    else:
        roles.add("athlete")
    set_fields["roles"] = sorted(roles)

    if kind == "coach_client":
        coach_tgid = invite.get("assigned_coach_telegram_id")
        if not coach_tgid:
            # Инвайт повреждён — откатываем использование.
            await db.invite_codes.update_one({"id": invite["id"]}, {"$inc": {"uses": -1}})
            raise HTTPException(status_code=500, detail="Приглашение без тренера. Обратитесь к администратору.")
        if coach_tgid == tgid:
            await db.invite_codes.update_one({"id": invite["id"]}, {"$inc": {"uses": -1}})
            raise HTTPException(status_code=400, detail="Нельзя применить собственный код.")
        link = await db.coach_links.find_one(
            {"coach_telegram_id": coach_tgid, "athlete_telegram_id": tgid}, {"_id": 0}
        )
        if link:
            await db.coach_links.update_one(
                {"coach_telegram_id": coach_tgid, "athlete_telegram_id": tgid},
                {"$set": {"status": "active", "updated_at": now_iso}},
            )
        else:
            new_link = CoachLink(coach_telegram_id=coach_tgid, athlete_telegram_id=tgid)
            link_doc = new_link.model_dump()
            link_doc["created_at"] = link_doc["created_at"].isoformat()
            link_doc["updated_at"] = link_doc["updated_at"].isoformat()
            await db.coach_links.insert_one(link_doc)
        # Один активный тренер на атлета: остальные связи — revoked.
        await db.coach_links.update_many(
            {"athlete_telegram_id": tgid, "coach_telegram_id": {"$ne": coach_tgid}, "status": "active"},
            {"$set": {"status": "revoked", "updated_at": now_iso}},
        )
        set_fields["coach_telegram_id"] = coach_tgid

    await db.users.update_one({"telegram_id": tgid}, {"$set": set_fields})
    fresh = await _get_user_or_404(tgid)
    logger.info(f"Invite redeemed: code={invite['code']} kind={kind} user={tgid}")
    return _get_capabilities(fresh)


@api_router.get("/me/capabilities")
async def me_capabilities(current: dict = Depends(get_current_user)):
    """Итоговые права текущего пользователя (дефолт по tier + оверрайды)."""
    return _get_capabilities(current)


# --- Админ-панель ----------------------------------------------------------

@api_router.get("/admin/summary")
async def admin_summary(current: dict = Depends(get_current_user)):
    """Счётчики для админ-панели: атлеты по tier, связи, инвайты, онбординг."""
    _assert_admin(current)
    tier_counts = {"coach_managed": 0, "standalone": 0, "unset": 0}
    roles_counts = {"athlete": 0, "coach": 0, "admin": 0}
    onboarded = 0
    users_total = 0
    async for u in db.users.find({}, {"access_tier": 1, "roles": 1, "onboarded_at": 1}):
        users_total += 1
        tier = u.get("access_tier")
        tier_counts[tier if tier in ACCESS_TIERS else "unset"] += 1
        for r in (u.get("roles") or []):
            if r in roles_counts:
                roles_counts[r] += 1
        if u.get("onboarded_at"):
            onboarded += 1
    active_links = await db.coach_links.count_documents({"status": "active"})
    invites_active = await db.invite_codes.count_documents({"status": "active"})
    invites_used = await db.invite_codes.count_documents({"uses": {"$gt": 0}})
    invites_total = await db.invite_codes.count_documents({})
    return {
        "users_total": users_total,
        "athletes_by_tier": tier_counts,
        "roles": roles_counts,
        "onboarded": onboarded,
        "not_onboarded": users_total - onboarded,
        "active_coach_links": active_links,
        "invites": {
            "total": invites_total,
            "active": invites_active,
            "used": invites_used,
            "free": max(invites_active - invites_used, 0),
        },
    }


@api_router.get("/admin/users")
async def admin_users(
    search: Optional[str] = None,
    tier: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    current: dict = Depends(get_current_user),
):
    """Список пользователей с правами (фильтры: поиск, tier, роль)."""
    _assert_admin(current)
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    query: dict = {}
    if tier:
        if tier not in ACCESS_TIERS and tier != "unset":
            raise HTTPException(status_code=400, detail="tier должен быть coach_managed, standalone или unset")
        query["access_tier"] = {"$in": [tier] + ([] if tier == "unset" else [])} if tier != "unset" \
            else {"$nin": list(ACCESS_TIERS)}
    if role:
        if role not in ROLES_ALL:
            raise HTTPException(status_code=400, detail="role должен быть athlete, coach или admin")
        query["roles"] = role
    if search:
        s = search.strip()
        if s:
            rx = {"$regex": re.escape(s), "$options": "i"}
            or_clause = [{"first_name": rx}, {"username": rx}, {"email": rx}]
            if s.isdigit():
                or_clause.append({"telegram_id": int(s)})
            query["$or"] = or_clause
    total = await db.users.count_documents(query)
    docs = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort(
        "created_at", -1
    ).skip(offset).limit(limit).to_list(limit)
    for u in docs:
        u["onboarded"] = bool(u.get("onboarded_at")) or any(
            r in ("coach", "admin") for r in (u.get("roles") or [])
        )
    return {"users": docs, "total": total, "limit": limit, "offset": offset}


@api_router.patch("/admin/users/{telegram_id}/permissions")
async def admin_update_permissions(
    telegram_id: int,
    payload: PermissionsUpdateReq,
    current: dict = Depends(get_current_user),
):
    """Выдать/снять права атлету (мердж в users.permissions)."""
    _assert_admin(current)
    user = await _get_user_or_404(telegram_id)
    unknown = [k for k in (payload.permissions or {}) if k not in PERMISSION_KEYS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Неизвестные права: {', '.join(sorted(unknown))}")
    now_iso = datetime.now(timezone.utc).isoformat()
    merged = _merge_permission_overrides(
        _default_permissions(_resolve_access_tier(user)), payload.permissions
    )
    await db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {
            "permissions": merged,
            "permissions_updated_by": current["telegram_id"],
            "permissions_updated_at": now_iso,
            "updated_at": now_iso,
        }},
    )
    fresh = await _get_user_or_404(telegram_id)
    return _get_capabilities(fresh)


@api_router.post("/admin/users/{telegram_id}/access-tier")
async def admin_set_access_tier(
    telegram_id: int,
    payload: AccessTierReq,
    current: dict = Depends(get_current_user),
):
    """Сменить режим атлета: coach_managed | standalone."""
    _assert_admin(current)
    tier = (payload.access_tier or "").strip()
    if tier not in ACCESS_TIERS:
        raise HTTPException(status_code=400, detail="access_tier должен быть coach_managed или standalone")
    await _get_user_or_404(telegram_id)
    await db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"access_tier": tier, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    fresh = await _get_user_or_404(telegram_id)
    return _get_capabilities(fresh)


@api_router.post("/admin/users/{telegram_id}/role")
async def admin_toggle_role(
    telegram_id: int,
    payload: RoleReq,
    current: dict = Depends(get_current_user),
):
    """Переключить роль (coach/admin): есть — снять, нет — выдать. athlete — всегда."""
    _assert_admin(current)
    role = (payload.role or "").strip()
    if role not in ("coach", "admin"):
        raise HTTPException(status_code=400, detail="Переключать можно только роли coach или admin")
    user = await _get_user_or_404(telegram_id)
    if telegram_id == current["telegram_id"]:
        raise HTTPException(status_code=400, detail="Нельзя менять собственную роль администратора")
    roles = set(user.get("roles") or [])
    roles.add("athlete")
    if role in roles:
        roles.discard(role)
    else:
        roles.add(role)
    await db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"roles": sorted(roles), "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    fresh = await _get_user_or_404(telegram_id)
    return _get_capabilities(fresh)


@api_router.get("/admin/invites")
async def admin_list_invites(
    kind: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 500,
    current: dict = Depends(get_current_user),
):
    """Все инвайты (админ) с фильтрами kind/status."""
    _assert_admin(current)
    limit = max(1, min(limit, 1000))
    query: dict = {}
    if kind:
        if kind not in INVITE_KINDS:
            raise HTTPException(status_code=400, detail="Недопустимый kind")
        query["kind"] = kind
    if status:
        if status not in ("active", "revoked", "expired"):
            raise HTTPException(status_code=400, detail="Недопустимый статус")
        query["status"] = status
    docs = await db.invite_codes.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"invites": docs}


@api_router.post("/admin/invites/{invite_id}/revoke")
async def admin_revoke_invite(invite_id: str, current: dict = Depends(get_current_user)):
    """Отозвать любой инвайт (админ)."""
    _assert_admin(current)
    res = await db.invite_codes.update_one(
        {"id": invite_id},
        {"$set": {"status": "revoked", "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")
    return {"ok": True, "status": "revoked"}


# ===========================================================================
# P3 — Видимость плана, публикация недель, тренировочные дни
# ===========================================================================
async def _get_plan_or_404(plan_id: str) -> dict:
    doc = await db.plans.find_one({"id": plan_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Plan not found")
    return doc


@api_router.patch("/plans/{plan_id}/visibility", response_model=Plan)
async def set_plan_visibility(plan_id: str, payload: VisibilityReq,
                             current: dict = Depends(get_current_user)):
    vis = (payload.visibility or "").strip().lower()
    if vis not in ("draft", "published"):
        raise HTTPException(status_code=400, detail="visibility должен быть draft или published")
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    now = datetime.now(timezone.utc).isoformat()
    set_fields = {"visibility": vis, "updated_at": now}
    if vis == "published":
        # Публикация делает план единственным «живым»: промоутим в active и
        # завершаем прочие планы спортсмена (старый рабочий план уступает место).
        set_fields["status"] = "active"
        if not plan.get("published_at"):
            set_fields["published_at"] = now
        await db.plans.update_many(
            {"athlete_telegram_id": plan.get("athlete_telegram_id"),
             "status": {"$in": ["active", "draft"]}, "id": {"$ne": plan_id}},
            {"$set": {"status": "completed", "updated_at": now}},
        )
    await db.plans.update_one({"id": plan_id}, {"$set": set_fields})
    updated = await _get_plan_or_404(plan_id)
    await _rt_plan(plan_id, "plan.published", {"visibility": vis})
    await _notify_user(updated.get("athlete_telegram_id"), "plan.published",
                       {"plan_id": plan_id, "visibility": vis})
    return updated


@api_router.patch("/plans/{plan_id}/weeks/{week}/publish", response_model=Plan)
async def publish_plan_week(plan_id: str, week: int, payload: WeekPublishReq,
                            current: dict = Depends(get_current_user)):
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    weeks = plan.get("weeks", [])
    found = False
    for w in weeks:
        if w.get("week_index") == week:
            w["published"] = bool(payload.published)
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Week not found")
    await db.plans.update_one(
        {"id": plan_id},
        {"$set": {"weeks": weeks, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    updated = await _get_plan_or_404(plan_id)
    await _rt_plan(plan_id, "week.published", {"week_index": week, "published": bool(payload.published)})
    await _notify_user(updated.get("athlete_telegram_id"), "week.published",
                       {"plan_id": plan_id, "week_index": week, "published": bool(payload.published)})
    return updated


@api_router.patch("/plans/{plan_id}/training-days", response_model=Plan)
async def set_plan_training_days(plan_id: str, payload: TrainingDaysReq,
                                 current: dict = Depends(get_current_user)):
    days = payload.training_days or []
    if any((not isinstance(d, int)) or d < 1 or d > 7 for d in days):
        raise HTTPException(status_code=400, detail="training_days: числа 1..7")
    norm = sorted(set(int(d) for d in days))
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    set_fields = {"training_days": norm, "updated_at": datetime.now(timezone.utc).isoformat()}
    # Ремаппим дни снимка плана, чтобы спортсмен реально увидел изменение в календаре.
    # Без этого недельный селектор/прогресс берут дни из week.days и не реагируют на training_days.
    if norm:
        set_fields["weeks"] = _remap_week_days(plan.get("weeks") or [], norm)
    await db.plans.update_one({"id": plan_id}, {"$set": set_fields})
    updated = await _get_plan_or_404(plan_id)
    await _rt_plan(plan_id, "training_days.updated", {"training_days": norm})
    await _notify_user(updated.get("athlete_telegram_id"), "training_days.updated",
                       {"plan_id": plan_id, "training_days": norm})
    return updated


# ===========================================================================
# P4 (pre) — Редактор плана подопечного: недели / дни / упражнения
# Тренер (или владелец) правит снимок плана. %1ПМ/тоннаж считаются при чтении.
# ===========================================================================
class PlanMetaReq(BaseModel):
    name: Optional[str] = None
    current_week: Optional[int] = None
    start_date: Optional[str] = None


class PlanDayUpsertReq(BaseModel):
    week: int
    day: int
    title: Optional[str] = None
    is_rest: Optional[bool] = None


class PlanExerciseReq(BaseModel):
    week: int
    day: int
    order: Optional[int] = None           # задан → редактируем; иначе добавляем
    exercise_name: str
    exercise_slug: Optional[str] = None
    exercise_id: Optional[str] = None
    muscle_group: Optional[str] = None
    difficulty: Optional[str] = None
    lift_group: Optional[str] = None
    is_accessory: bool = False
    weight_type: str = "kg"
    target_reps: Optional[str] = None
    target_rpe: Optional[float] = None
    rest_seconds: Optional[int] = None
    notes: Optional[str] = None
    sets_scheme: Optional[List[dict]] = None
    # Суперсеты
    superset_id: Optional[str] = None
    superset_order: Optional[int] = None
    rest_after_superset: Optional[int] = None


def _norm_sets_scheme(scheme):
    out = []
    for s in scheme or []:
        try:
            w = s.get("weight")
            w = float(w) if w not in (None, "") else None
        except Exception:
            w = None
        try:
            sets = int(s.get("sets") or 1)
        except Exception:
            sets = 1
        try:
            reps = int(s.get("reps") or 0)
        except Exception:
            reps = 0
        out.append({"weight": w, "sets": max(1, sets), "reps": max(0, reps)})
    return out


def _normalize_plan_exercise(payload: "PlanExerciseReq", order: int) -> dict:
    scheme = _norm_sets_scheme(payload.sets_scheme)
    if scheme:
        target_sets = sum(s["sets"] for s in scheme)
        target_reps = payload.target_reps or str(scheme[0]["reps"])
        target_weight = scheme[0]["weight"]
    else:
        target_sets = 4 if payload.is_accessory else 3
        target_reps = payload.target_reps or "10"
        target_weight = None
    return {
        "exercise_id": payload.exercise_id,
        "exercise_slug": payload.exercise_slug,
        "exercise_name": (payload.exercise_name or "").strip() or "Упражнение",
        "muscle_group": payload.muscle_group,
        "difficulty": payload.difficulty,
        "order": order,
        "target_sets": target_sets,
        "target_reps": str(target_reps),
        "target_weight": target_weight,
        "weight_type": payload.weight_type or "kg",
        "target_rpe": payload.target_rpe,
        "rest_seconds": payload.rest_seconds,
        "notes": (payload.notes or None),
        "sets_scheme": scheme,
        "lift_group": payload.lift_group,
        "is_accessory": bool(payload.is_accessory),
        # Суперсеты
        "superset_id": payload.superset_id,
        "superset_order": payload.superset_order,
        "rest_after_superset": payload.rest_after_superset,
    }


def _find_week(plan: dict, week: int):
    return next((w for w in plan.get("weeks", []) if w.get("week_index") == week), None)


def _find_day(week_obj: dict, day: int):
    return next((d for d in (week_obj.get("days") or []) if d.get("day_index") == day), None)


async def _save_plan_weeks(plan_id: str, weeks: list):
    await db.plans.update_one(
        {"id": plan_id},
        {"$set": {"weeks": weeks, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    updated = await _get_plan_or_404(plan_id)
    # Real-time: правки структуры плана доходят до спортсмена «вживую» (B5)
    await _rt_plan(plan_id, "plan.updated", {})
    await _notify_user(updated.get("athlete_telegram_id"), "plan.updated", {"plan_id": plan_id})
    return updated


@api_router.patch("/plans/{plan_id}", response_model=Plan)
async def update_plan_meta(plan_id: str, payload: PlanMetaReq,
                           current: dict = Depends(get_current_user)):
    """Переименовать план / задать текущую неделю / дату старта."""
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    set_fields = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if payload.name is not None and payload.name.strip():
        set_fields["name"] = payload.name.strip()
    if payload.current_week is not None:
        set_fields["current_week"] = max(1, int(payload.current_week))
    if payload.start_date is not None:
        set_fields["start_date"] = payload.start_date
    await db.plans.update_one({"id": plan_id}, {"$set": set_fields})
    updated = await _get_plan_or_404(plan_id)
    await _rt_plan(plan_id, "plan.updated", {})
    await _notify_user(updated.get("athlete_telegram_id"), "plan.updated", {"plan_id": plan_id})
    return updated


@api_router.put("/plans/{plan_id}/day", response_model=Plan)
async def upsert_plan_day(plan_id: str, payload: PlanDayUpsertReq,
                          current: dict = Depends(get_current_user)):
    """Создать/изменить день недели (день = слот дня недели 1..7)."""
    if payload.day < 1 or payload.day > 7:
        raise HTTPException(status_code=400, detail="day: 1..7")
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    week_obj = _find_week(plan, payload.week)
    if not week_obj:
        raise HTTPException(status_code=404, detail="Week not found")
    day_obj = _find_day(week_obj, payload.day)
    if day_obj:
        if payload.title is not None:
            day_obj["title"] = payload.title
        if payload.is_rest is not None:
            day_obj["is_rest"] = bool(payload.is_rest)
    else:
        week_obj.setdefault("days", []).append({
            "day_index": payload.day,
            "title": payload.title or f"День {payload.day}",
            "is_rest": bool(payload.is_rest) if payload.is_rest is not None else False,
            "exercises": [],
        })
        week_obj["days"].sort(key=lambda d: d.get("day_index", 0))
    return await _save_plan_weeks(plan_id, plan["weeks"])


@api_router.delete("/plans/{plan_id}/day", response_model=Plan)
async def delete_plan_day(plan_id: str, week: int, day: int,
                          current: dict = Depends(get_current_user)):
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    week_obj = _find_week(plan, week)
    if not week_obj:
        raise HTTPException(status_code=404, detail="Week not found")
    days = week_obj.get("days") or []
    new_days = [d for d in days if d.get("day_index") != day]
    if len(new_days) == len(days):
        raise HTTPException(status_code=404, detail="Day not found")
    week_obj["days"] = new_days
    return await _save_plan_weeks(plan_id, plan["weeks"])


@api_router.put("/plans/{plan_id}/exercise", response_model=Plan)
async def upsert_plan_exercise(plan_id: str, payload: PlanExerciseReq,
                               current: dict = Depends(get_current_user)):
    """Добавить (order=None) или изменить (order задан) упражнение в дне."""
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    week_obj = _find_week(plan, payload.week)
    if not week_obj:
        raise HTTPException(status_code=404, detail="Week not found")
    day_obj = _find_day(week_obj, payload.day)
    if not day_obj:
        raise HTTPException(status_code=404, detail="Day not found (создайте день сначала)")
    exs = sorted(day_obj.get("exercises") or [], key=lambda x: x.get("order", 0))
    if payload.order is not None and 0 <= int(payload.order) < len(exs):
        exs[int(payload.order)] = _normalize_plan_exercise(payload, int(payload.order))
    else:
        exs.append(_normalize_plan_exercise(payload, len(exs)))
    for i, e in enumerate(exs):
        e["order"] = i
    day_obj["exercises"] = exs
    return await _save_plan_weeks(plan_id, plan["weeks"])


@api_router.delete("/plans/{plan_id}/exercise", response_model=Plan)
async def delete_plan_exercise(plan_id: str, week: int, day: int, order: int,
                               current: dict = Depends(get_current_user)):
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    week_obj = _find_week(plan, week)
    if not week_obj:
        raise HTTPException(status_code=404, detail="Week not found")
    day_obj = _find_day(week_obj, day)
    if not day_obj:
        raise HTTPException(status_code=404, detail="Day not found")
    exs = sorted(day_obj.get("exercises") or [], key=lambda x: x.get("order", 0))
    if order < 0 or order >= len(exs):
        raise HTTPException(status_code=404, detail="Exercise not found")
    del exs[order]
    for i, e in enumerate(exs):
        e["order"] = i
    day_obj["exercises"] = exs
    return await _save_plan_weeks(plan_id, plan["weeks"])


@api_router.post("/plans/{plan_id}/week", response_model=Plan)
async def add_plan_week(plan_id: str, current: dict = Depends(get_current_user)):
    """Добавить пустую неделю в конец плана."""
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    weeks = plan.get("weeks") or []
    next_index = (max((w.get("week_index", 0) for w in weeks), default=0)) + 1
    weeks.append({"week_index": next_index, "published": True, "days": []})
    return await _save_plan_weeks(plan_id, weeks)


@api_router.delete("/plans/{plan_id}/week", response_model=Plan)
async def delete_plan_week(plan_id: str, week: int,
                           current: dict = Depends(get_current_user)):
    """Удалить неделю и пере-нумеровать оставшиеся (1..N)."""
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    weeks = sorted(plan.get("weeks") or [], key=lambda w: w.get("week_index", 0))
    new_weeks = [w for w in weeks if w.get("week_index") != week]
    if len(new_weeks) == len(weeks):
        raise HTTPException(status_code=404, detail="Week not found")
    for i, w in enumerate(new_weeks):
        w["week_index"] = i + 1
    now = datetime.now(timezone.utc).isoformat()
    cur = plan.get("current_week", 1)
    new_cur = min(max(1, cur), len(new_weeks)) if new_weeks else 1
    await db.plans.update_one(
        {"id": plan_id},
        {"$set": {"weeks": new_weeks, "current_week": new_cur, "updated_at": now}},
    )
    updated = await _get_plan_or_404(plan_id)
    await _rt_plan(plan_id, "plan.updated", {})
    await _notify_user(updated.get("athlete_telegram_id"), "plan.updated", {"plan_id": plan_id})
    return updated




# ===========================================================================
# Хелперы Фазы 2 (расчёт %1ПМ, схемы подходов, статистика сессии)
# ===========================================================================
_DIFF_RANK = {"Легко": 1, "Средне": 2, "Тяжело": 3}


def _int_or_zero(v):
    if isinstance(v, int):
        return v
    if v is None:
        return 0
    m = re.match(r"\s*(\d+)", str(v))
    return int(m.group(1)) if m else 0


def _resolve_sets(pe, orm):
    """Список рабочих подходов с рассчитанным %1ПМ. pe — ProgramExercise dict."""
    slug = pe.get("exercise_slug")
    scheme = pe.get("sets_scheme") or []
    if not scheme:
        scheme = [{
            "weight": pe.get("target_weight"),
            "sets": pe.get("target_sets") or 1,
            "reps": _int_or_zero(pe.get("target_reps")),
        }]
    out = []
    for s in scheme:
        w = s.get("weight")
        out.append({
            "weight": w,
            "sets": s.get("sets") or 1,
            "reps": s.get("reps") or 0,
            "percent_1rm": percent_of(w, slug, orm),
        })
    return out


def _expand_set_logs(sets_scheme):
    """Разворачивает групповую схему (weight×sets×reps) в плоский чек-лист
    индивидуальных подходов для по-подходного логирования."""
    logs = []
    for grp in (sets_scheme or []):
        n = max(1, int(grp.get("sets") or 1))
        for _ in range(n):
            logs.append({
                "weight": grp.get("weight"),
                "reps": int(grp.get("reps") or 0),
                "percent_1rm": grp.get("percent_1rm"),
                "done": False,
                "skipped": False,
            })
    return logs


def _scheme_from_logs(set_logs, only_done=True):
    """Собирает групповую схему (weight×sets×reps) из плоского списка подходов.
    Подряд идущие одинаковые (вес, повторы, %) сворачиваются в одну группу.
    only_done=True — учитывать только выполненные подходы (факт)."""
    groups = []
    for lg in (set_logs or []):
        if only_done and not lg.get("done"):
            continue
        w = lg.get("weight")
        r = int(lg.get("reps") or 0)
        p = lg.get("percent_1rm")
        if groups and groups[-1]["weight"] == w and groups[-1]["reps"] == r and groups[-1].get("percent_1rm") == p:
            groups[-1]["sets"] += 1
        else:
            groups.append({"weight": w, "sets": 1, "reps": r, "percent_1rm": p})
    return groups


def _view_exercise(pe, orm, order, status="pending"):
    """Унифицированная карточка упражнения для экрана дня/сессии."""
    is_acc = bool(pe.get("is_accessory"))
    sets = [] if is_acc else _resolve_sets(pe, orm)
    return {
        "order": order,
        "exercise_id": pe.get("exercise_id"),
        "exercise_slug": pe.get("exercise_slug"),
        "exercise_name": pe.get("exercise_name"),
        "muscle_group": pe.get("muscle_group"),
        "muscle_letter": muscle_letter(pe.get("muscle_group")),
        "difficulty": pe.get("difficulty"),
        "sets_scheme": sets,
        "plan_sets_scheme": [dict(s) for s in sets],
        "set_logs": [],
        "rest_seconds": pe.get("rest_seconds"),
        "tonnage": scheme_tonnage(sets),
        "status": status,
        "comment": pe.get("comment"),
        "edited": pe.get("edited", False),
        "lift_group": pe.get("lift_group"),
        "is_accessory": is_acc,
        "filled_by": None,
        "coach_confirmed": False,
        "confirmed_by": None,
        "confirmed_at": None,
    }


def _day_group_difficulty(exercises):
    group = group_letters([e.get("muscle_group") for e in exercises])
    diffs = [e.get("difficulty") for e in exercises if e.get("difficulty")]
    difficulty = max(diffs, key=lambda d: _DIFF_RANK.get(d, 0)) if diffs else None
    return group, difficulty


def _build_session_exercises(day_obj, orm):
    ordered = sorted(day_obj.get("exercises", []), key=lambda x: x.get("order", 0))
    exs = [_view_exercise(pe, orm, i) for i, pe in enumerate(ordered)]
    for ex in exs:
        # По-подходный чек-лист строим только для основных упражнений (у подсобных
        # нет схемы подходов — они отмечаются целиком).
        if not ex.get("is_accessory"):
            ex["set_logs"] = _expand_set_logs(ex.get("sets_scheme"))
    if exs:
        exs[0]["status"] = "in_progress"
    return exs


def _est_1rm(weight, percent_1rm, reps):
    """Оценка 1ПМ по фактическому исполнению (формула Эпли): вес × (1 + повт/30).
    Если повторы неизвестны — fallback: вес ÷ (плановый % / 100)."""
    if not weight:
        return None
    try:
        r = int(reps or 0)
        if r == 1:
            return round(float(weight), 1)
        if r > 1:
            return round(float(weight) * (1 + r / 30.0), 1)
        if percent_1rm:
            return round(float(weight) / (float(percent_1rm) / 100.0), 1)
        return round(float(weight), 1)
    except Exception:
        return None


def _sets_count(scheme):
    """Суммарное число рабочих подходов в схеме (Σ sets)."""
    return sum(int(s.get("sets") or 0) for s in (scheme or []))


def _top_set(scheme):
    """Подход с максимальным весом в схеме (или None)."""
    best = None
    for s in (scheme or []):
        w = s.get("weight")
        if w is None:
            continue
        if best is None or w > best.get("weight", -1):
            best = s
    return best


def _lift_summary(exs):
    """Сводка по основным движениям (squat/bench/deadlift) из выполненных
    упражнений: топовый рабочий вес и оценка 1ПМ «по плану» (вес ÷ план%)."""
    lifts = {}
    for e in exs:
        lg = e.get("lift_group")
        if lg not in ("squat", "bench", "deadlift"):
            continue
        if e.get("status") != "done":
            continue
        fact_top = _top_set(e.get("sets_scheme"))
        if not fact_top:
            continue
        plan_top = _top_set(e.get("plan_sets_scheme")) or fact_top
        w = fact_top.get("weight")
        # 1ПМ «как в таблице»: фактический вес ÷ плановый % (фикс. интенсивность плана)
        pct = (plan_top or {}).get("percent_1rm") or fact_top.get("percent_1rm")
        one_rm = _est_1rm(w, pct, fact_top.get("reps"))
        cur = lifts.get(lg)
        if not cur or (w or 0) > (cur.get("top_weight") or 0):
            lifts[lg] = {
                "top_weight": w,
                "reps": fact_top.get("reps"),
                "percent_1rm": pct,
                "one_rm": one_rm,
            }
    return lifts


def _muscle_sets(exs):
    """Распределение выполненных подходов по буквам мышечных групп: {letter: sets}."""
    dist = {}
    for e in exs:
        if e.get("status") != "done":
            continue
        ltr = e.get("muscle_letter") or muscle_letter(e.get("muscle_group"))
        if not ltr:
            continue
        n = _sets_count(e.get("sets_scheme")) or 1
        dist[ltr] = dist.get(ltr, 0) + n
    return dist


def _session_stats(session):
    exs = session.get("exercises", [])
    total = len(exs)
    done = [e for e in exs if e.get("status") == "done"]
    skipped = [e for e in exs if e.get("status") == "skipped"]
    tonnage = round(sum(e.get("tonnage", 0) or 0 for e in done))
    group = group_letters([e.get("muscle_group") for e in exs])
    diffs = [e.get("difficulty") for e in exs if e.get("difficulty")]
    difficulty = max(diffs, key=lambda d: _DIFF_RANK.get(d, 0)) if diffs else None

    started = session.get("started_at")
    finished = session.get("finished_at")
    duration_sec = 0
    if started:
        try:
            start_dt = datetime.fromisoformat(started) if isinstance(started, str) else started
            if finished:
                end_dt = datetime.fromisoformat(finished) if isinstance(finished, str) else finished
            else:
                end_dt = datetime.now(timezone.utc)
            duration_sec = max(0, int((end_dt - start_dt).total_seconds()))
        except Exception:
            duration_sec = 0

    progress_pct = round(len(done) / total * 100) if total else 0

    # --- P7: объём (подходы) план vs факт, тоннаж план vs факт ---
    sets_done = sum(_sets_count(e.get("sets_scheme")) for e in done)
    sets_planned = sum(_sets_count(e.get("plan_sets_scheme") or e.get("sets_scheme")) for e in exs)
    tonnage_planned = round(sum(scheme_tonnage(e.get("plan_sets_scheme") or e.get("sets_scheme")) for e in exs))
    volume_pct = round(sets_done / sets_planned * 100) if sets_planned else 0
    tonnage_dev_pct = round((tonnage - tonnage_planned) / tonnage_planned * 100) if tonnage_planned else 0

    return {
        "tonnage": tonnage,
        "tonnage_planned": tonnage_planned,
        "tonnage_dev_pct": tonnage_dev_pct,
        "group": group,
        "difficulty": difficulty,
        "duration_sec": duration_sec,
        "done_count": len(done),
        "skipped_count": len(skipped),
        "total_count": total,
        "progress_pct": progress_pct,
        "sets_done": sets_done,
        "sets_planned": sets_planned,
        "volume_pct": volume_pct,
        "muscle_sets": _muscle_sets(exs),
        "lifts": _lift_summary(exs),
    }


def _deviation_flags(plan_scheme, fact_scheme, status):
    """Флаги отклонения упражнения: список строк."""
    flags = []
    if status == "skipped":
        return ["skipped"]
    p_sets = _sets_count(plan_scheme)
    f_sets = _sets_count(fact_scheme)
    if f_sets > p_sets:
        flags.append("more_volume")
    elif f_sets < p_sets and p_sets:
        flags.append("less_volume")
    p_top = _top_set(plan_scheme)
    f_top = _top_set(fact_scheme)
    pw = p_top.get("weight") if p_top else None
    fw = f_top.get("weight") if f_top else None
    if pw is not None and fw is not None:
        if fw > pw:
            flags.append("weight_up")
        elif fw < pw:
            flags.append("weight_down")
    return flags


def _session_deviation(session):
    """План vs факт по упражнениям одной сессии (для отчёта об отклонениях)."""
    items = []
    for e in session.get("exercises", []):
        plan_scheme = e.get("plan_sets_scheme") or []
        fact_scheme = e.get("sets_scheme") or []
        items.append({
            "order": e.get("order"),
            "exercise_name": e.get("exercise_name"),
            "lift_group": e.get("lift_group"),
            "muscle_group": e.get("muscle_group"),
            "status": e.get("status"),
            "edited": bool(e.get("edited")),
            "planned": {
                "sets": _sets_count(plan_scheme),
                "tonnage": scheme_tonnage(plan_scheme),
                "scheme": plan_scheme,
            },
            "actual": {
                "sets": _sets_count(fact_scheme) if e.get("status") == "done" else 0,
                "tonnage": e.get("tonnage", 0) if e.get("status") == "done" else 0,
                "scheme": fact_scheme,
            },
            "flags": _deviation_flags(plan_scheme, fact_scheme, e.get("status")),
        })
    return items


def _serialize_session(session):
    out = dict(session)
    out.pop("_id", None)
    out["stats"] = _session_stats(session)
    return out


def _assert_session_mutable(s):
    """Завершённую тренировку нельзя менять (кроме /resume)."""
    if s.get("status") == "finished":
        raise HTTPException(status_code=409, detail="Тренировка завершена")


async def _apply_session_mutation(session_id: str, mutator):
    """Пишет мутацию сессии с оптимистичной блокировкой (version).

    mutator(session) -> dict полей для $set (сама мутация применяется к dict).
    Если прямой write проиграл гонку (version не сошлась) — перечитываем один раз
    и повторяем; при повторном конфликте — 409. Возвращает актуальный dict сессии.
    """
    s = await db.workout_sessions.find_one({"id": session_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    for attempt in (0, 1):
        fields = dict(await mutator(s))
        now = datetime.now(timezone.utc).isoformat()
        fields.setdefault("updated_at", now)
        fields.setdefault("last_event_at", now)
        fields["version"] = (s.get("version") or 0) + 1
        res = await db.workout_sessions.update_one(
            {"id": session_id, "version": s.get("version") or 0},
            {"$set": fields},
        )
        if res.matched_count > 0:
            s["version"] = fields["version"]
            return s
        if attempt == 1:
            raise HTTPException(
                status_code=409,
                detail="Конфликт: сессия изменена. Обновите и повторите",
            )
        s = await db.workout_sessions.find_one({"id": session_id}, {"_id": 0})
        if not s:
            raise HTTPException(status_code=404, detail="Session not found")
    raise HTTPException(status_code=409,
                        detail="Конфликт: сессия изменена. Обновите и повторите")


# ===========================================================================
# P4 — Real-time helpers (persist-then-broadcast)
# ===========================================================================
async def _can_access_plan(tgid: int, plan_id: str) -> bool:
    """Имеет ли пользователь доступ к комнате плана: владелец-спортсмен,
    привязанный тренер или указанный coach_telegram_id плана."""
    plan = await db.plans.find_one(
        {"id": plan_id},
        {"_id": 0, "athlete_telegram_id": 1, "coach_telegram_id": 1},
    )
    if not plan:
        return False
    athlete = plan.get("athlete_telegram_id")
    if athlete == tgid or plan.get("coach_telegram_id") == tgid:
        return True
    link = await db.coach_links.find_one(
        {"coach_telegram_id": tgid, "athlete_telegram_id": athlete, "status": "active"},
        {"_id": 0},
    )
    return bool(link)


async def _rt_session(plan_id: Optional[str], event_type: str, session: dict):
    """Broadcast события сессии в комнату плана. Payload содержит готовый
    снимок сессии — клиент применяет его без дополнительного REST-запроса."""
    if not plan_id:
        return
    try:
        await manager.broadcast(
            f"plan:{plan_id}",
            event_type,
            {"session_id": session.get("id"), "plan_id": plan_id, "session": _serialize_session(session)},
        )
    except Exception as e:
        logger.warning(f"rt_session broadcast failed: {e}")


async def _rt_plan(plan_id: Optional[str], event_type: str, extra: Optional[dict] = None):
    """Broadcast события плана (видимость/недели/дни) в комнату плана."""
    if not plan_id:
        return
    try:
        payload = {"plan_id": plan_id}
        if extra:
            payload.update(extra)
        await manager.broadcast(f"plan:{plan_id}", event_type, payload)
    except Exception as e:
        logger.warning(f"rt_plan broadcast failed: {e}")


async def _notify_user(telegram_id: Optional[int], event_type: str, payload: dict):
    """Личное уведомление пользователю (комната user:{telegram_id})."""
    if telegram_id is None:
        return
    try:
        await manager.broadcast(f"user:{telegram_id}", event_type, payload)
    except Exception as e:
        logger.warning(f"notify_user broadcast failed: {e}")


async def _touch_session_event(session_id: str) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    await db.workout_sessions.update_one(
        {"id": session_id}, {"$set": {"last_event_at": ts}}
    )
    return ts


# ---- День плана (превью перед стартом) ----
@api_router.get("/plans/{plan_id}/day")
async def get_plan_day(plan_id: str, week: int = 1, day: int = 1,
                       viewer: Optional[int] = None,
                       current: dict = Depends(get_current_user)):
    """День плана: упражнения + мета. day = 1..7 (Пн..Вс).

    Неделя, ещё не опубликованная тренером, скрыта от спортсмена (locked).
    Владелец определяется из СЕССИИ, а не из клиентского `viewer` — иначе,
    не передав viewer, можно было прочитать скрытую неделю."""
    doc = await db.plans.find_one({"id": plan_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Plan not found")
    athlete = doc.get("athlete_telegram_id")
    tgid = current["telegram_id"]
    if tgid != athlete and not await _is_coach_of(tgid, athlete):
        raise HTTPException(status_code=403, detail="Forbidden")

    orm = doc.get("one_rep_max") or {}
    rest_response = {
        "plan_id": plan_id, "week_index": week, "day_index": day,
        "is_rest": True, "title": "День отдыха", "exercises": [],
        "group": "", "difficulty": None,
    }
    week_obj = next((w for w in (doc.get("weeks") or []) if w.get("week_index") == week), None)
    if not week_obj:
        return rest_response
    # Неделя скрыта от самого спортсмена — отдаём «заблокировано»
    is_owner = tgid == athlete
    if is_owner and week_obj.get("published") is False:
        return {**rest_response, "is_rest": True, "locked": True,
                "title": "Неделя ещё не открыта тренером"}
    day_obj = next((d for d in (week_obj.get("days") or []) if d.get("day_index") == day), None)
    if not day_obj or day_obj.get("is_rest"):
        return rest_response

    ordered = sorted(day_obj.get("exercises", []), key=lambda x: x.get("order", 0))
    exercises = [_view_exercise(pe, orm, i) for i, pe in enumerate(ordered)]
    group, difficulty = _day_group_difficulty(exercises)
    return {
        "plan_id": plan_id, "week_index": week, "day_index": day_obj["day_index"],
        "title": day_obj.get("title", ""), "is_rest": False,
        "group": group, "difficulty": difficulty,
        "exercises": exercises,
    }


@api_router.get("/plans/{plan_id}/week-progress")
async def get_week_progress(plan_id: str, week: int = 1, viewer: Optional[int] = None,
                            dates: Optional[str] = None,
                            current: dict = Depends(get_current_user)):
    """Прогресс/расписание по дням недели (для колец в селекторе).

    Владелец определяется из СЕССИИ (не из `viewer`): для спортсмена скрытая
    неделя возвращается как заблокированная (7 дней отдыха + locked) — выдача
    недель «по одной» (B3).

    dates — опц. список из 7 ISO-дат (через запятую) для day_index 1..7 текущей
    КАЛЕНДАРНОЙ недели. Если задан, прогресс дня берётся из сессии, реально
    выполненной В ЭТУ дату (session.date), а не просто по (week,day). Это
    исключает «протекание» прогресса на одинаковые дни недели соседних недель."""
    doc = await db.plans.find_one({"id": plan_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Plan not found")
    athlete = doc.get("athlete_telegram_id")
    tgid = current["telegram_id"]
    if tgid != athlete and not await _is_coach_of(tgid, athlete):
        raise HTTPException(status_code=403, detail="Forbidden")

    week_obj = next((w for w in (doc.get("weeks") or []) if w.get("week_index") == week), None)
    is_owner = tgid == athlete
    locked = bool(week_obj and is_owner and week_obj.get("published") is False)
    days_map = {}
    if week_obj and not locked:
        for d in (week_obj.get("days") or []):
            if d.get("is_rest"):
                continue
            planned_sets = sum(int(e.get("target_sets", 0) or 0) for e in d.get("exercises", []))
            days_map[d.get("day_index")] = {
                "title": d.get("title", ""),
                "exercise_count": len(d.get("exercises", [])),
                "planned_sets": planned_sets,
            }

    # Календарные даты дней недели (day_index 1..7), если переданы
    date_by_day = {}
    if dates:
        parts = [p.strip() for p in dates.split(",")]
        for i, iso in enumerate(parts[:7]):
            if iso:
                date_by_day[i + 1] = iso

    # Сессии этой недели — для реального прогресса колец
    sessions = await db.workout_sessions.find(
        {"plan_id": plan_id, "week_index": week}, {"_id": 0}
    ).sort("created_at", 1).to_list(200)
    sess_by_day = {}
    for s in sessions:
        di = s.get("day_index")
        if date_by_day:
            # привязка к реальной дате выполнения
            if s.get("date") and s.get("date") == date_by_day.get(di):
                sess_by_day[di] = s
        else:
            sess_by_day[di] = s

    days = []
    for di in range(1, 8):
        info = days_map.get(di)
        s = sess_by_day.get(di)
        if info:
            progress_pct = 0
            is_done = False
            if s:
                st = _session_stats(s)
                progress_pct = st["progress_pct"]
                is_done = s.get("status") == "finished"
            days.append({
                "day_index": di, "is_workout": True, "title": info["title"],
                "exercise_count": info["exercise_count"], "planned_sets": info["planned_sets"],
                "progress_pct": progress_pct, "is_done": is_done, "has_session": bool(s),
            })
        else:
            days.append({
                "day_index": di, "is_workout": False, "title": "Отдых",
                "exercise_count": 0, "planned_sets": 0,
                "progress_pct": 0, "is_done": False, "has_session": False,
            })
    return {"plan_id": plan_id, "week_index": week, "days": days, "locked": locked}


# ===========================================================================
# Тренировочные сессии (Phase 2)
# ===========================================================================
@api_router.post("/sessions/start")
async def start_session(req: SessionStartReq, current_user: dict = Depends(get_current_user)):
    plan = await db.plans.find_one({"id": req.plan_id}, {"_id": 0})
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # IDOR: план можно начать только для того спортсмена, которому он принадлежит.
    if plan.get("athlete_telegram_id") is not None and plan.get("athlete_telegram_id") != req.athlete_telegram_id:
        raise HTTPException(status_code=403, detail="План принадлежит другому спортсмену")

    # Старт «под диктовку тренера»: проверяем, что вызывающий — тренер этого спортсмена
    coach_led = req.coach_telegram_id is not None
    uid = current_user["telegram_id"]
    if coach_led:
        if uid != req.coach_telegram_id:
            raise HTTPException(status_code=403, detail="Старт от имени другого тренера запрещён")
        await _assert_coach_of(req.coach_telegram_id, req.athlete_telegram_id)
    else:
        # Обычный старт: только сам спортсмен или его активный тренер
        if uid != req.athlete_telegram_id and not await _is_coach_of(uid, req.athlete_telegram_id):
            raise HTTPException(status_code=403, detail="Нельзя начать тренировку за другого спортсмена")
        # Фаза 1: managed-атлет без права log_strength сам силовую не начинает.
        _assert_can_selffill_strength(current_user, req.athlete_telegram_id)

    existing = await db.workout_sessions.find_one(
        {"plan_id": req.plan_id, "athlete_telegram_id": req.athlete_telegram_id,
         "week_index": req.week, "day_index": req.day, "status": {"$ne": "finished"},
         **({"date": req.date} if req.date else {})},
        {"_id": 0},
    )
    if existing:
        return _serialize_session(existing)

    # Запрет нескольких одновременных тренировок: незавершённая НЕ на паузе сессия в другой день
    active_other = await db.workout_sessions.find_one(
        {"athlete_telegram_id": req.athlete_telegram_id,
         "status": "in_progress", "paused": {"$ne": True}},
        {"_id": 0},
    )
    if active_other:
        raise HTTPException(status_code=409, detail={
            "error": "active_session_exists",
            "message": ("У спортсмена уже есть активная тренировка. Завершите её, чтобы начать новую."
                        if coach_led else
                        "У вас уже есть активная тренировка. Завершите её, чтобы начать новую."),
            "session_id": active_other["id"],
            "plan_id": active_other.get("plan_id"),
            "week_index": active_other.get("week_index"),
            "day_index": active_other.get("day_index"),
        })

    week_obj = next((w for w in (plan.get("weeks") or []) if w.get("week_index") == req.week), None)
    # Нельзя начать тренировку в скрытой (неопубликованной) тренером неделе —
    # но тренер, ведущий тренировку «под диктовку», может стартовать любую неделю.
    if (week_obj and week_obj.get("published") is False
            and not coach_led
            and uid == req.athlete_telegram_id):
        raise HTTPException(status_code=400, detail="Эта неделя ещё не открыта тренером")
    day_obj = next((d for d in (week_obj.get("days") or []) if d.get("day_index") == req.day), None) if week_obj else None
    if not day_obj or day_obj.get("is_rest"):
        raise HTTPException(status_code=400, detail="No workout scheduled for this day")

    # Тренер сессии: из плана, иначе инициатор старта, иначе из активной связи спортсмена
    coach_for_session = (plan.get("coach_telegram_id")
                         or req.coach_telegram_id
                         or await _resolve_athlete_coach(req.athlete_telegram_id))

    orm = plan.get("one_rep_max") or {}
    now = datetime.now(timezone.utc).isoformat()
    session = {
        "id": str(uuid.uuid4()),
        "plan_id": req.plan_id,
        "athlete_telegram_id": req.athlete_telegram_id,
        "coach_telegram_id": coach_for_session,
        "week_index": req.week, "day_index": req.day,
        "date": req.date or datetime.now(timezone.utc).date().isoformat(),
        "title": day_obj.get("title", ""),
        "status": "in_progress", "paused": False,
        "started_by": "coach" if coach_led else "athlete",
        "started_at": now, "finished_at": None,
        "exercises": _build_session_exercises(day_obj, orm),
        "version": 0,
        "coach_confirmed": False, "confirmed_by": None, "confirmed_at": None,
        "last_event_at": now,
        "live_status": "on_workout",
        "status_updated_at": datetime.now(timezone.utc),
        "created_at": now, "updated_at": now,
    }
    try:
        await db.workout_sessions.insert_one(dict(session))
    except DuplicateKeyError:
        # Гонка двух стартов: одна активная сессия на спортсмена (см. индекс в seed).
        dup = await db.workout_sessions.find_one(
            {"athlete_telegram_id": req.athlete_telegram_id, "status": "in_progress"},
            {"_id": 0},
        )
        if dup:
            return _serialize_session(dup)
        raise HTTPException(status_code=409, detail="У вас уже есть активная тренировка")
    logger.info(f"Session started ({session['started_by']}): {session['id']} plan={req.plan_id} day={req.day}")
    
    # Real-time: оповестить комнату плана и лично тренера
    await _rt_session(req.plan_id, "session.started", session)
    
    # WebSocket broadcast live-статуса тренеру (личная комната user:{tgid};
    # у ConnectionManager нет метода broadcast_to_room — вызов падал с 500).
    if coach_for_session:
        await manager.broadcast(f"user:{coach_for_session}", "client_status_change", {
            "athlete_telegram_id": req.athlete_telegram_id,
            "status": "on_workout",
            "session_id": session["id"]
        })
    await _notify_user(coach_for_session, "session.started", {
        "session_id": session["id"], "plan_id": req.plan_id,
        "athlete_telegram_id": req.athlete_telegram_id,
        "week_index": req.week, "day_index": req.day, "title": session["title"],
    })
    return _serialize_session(session)


@api_router.get("/sessions/active")
async def get_active_session(plan_id: str, week: int, day: int, athlete: int,
                             date: Optional[str] = None,
                             current_user: dict = Depends(get_current_user)):
    """Сессия для дня плана. Если передан date (ISO YYYY-MM-DD) — возвращаем
    сессию, реально выполненную В ЭТУ календарную дату (иначе последнюю по
    (plan,week,day)). Это исключает показ одной тренировки на одинаковых днях
    недели разных календарных недель."""
    # Доступ: только сам спортсмен или его активный тренер
    if current_user["telegram_id"] != athlete and not await _is_coach_of(current_user["telegram_id"], athlete):
        raise HTTPException(status_code=403, detail="Нет доступа к тренировкам этого спортсмена")
    q = {"plan_id": plan_id, "athlete_telegram_id": athlete,
         "week_index": week, "day_index": day}
    if date:
        q["date"] = date
    s = await db.workout_sessions.find_one(
        q, {"_id": 0}, sort=[("created_at", -1)],
    )
    if not s:
        return None
    return _serialize_session(s)


@api_router.get("/sessions/{session_id}")
async def get_session(session_id: str, current_user: dict = Depends(get_current_user)):
    s = await db.workout_sessions.find_one({"id": session_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    await _assert_session_read(current_user, s)
    return _serialize_session(s)


@api_router.patch("/sessions/{session_id}/exercise/{order}")
async def update_session_exercise(
    session_id: str,
    order: int,
    action: str,
    actor: str = "athlete",
    by: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    """Отметка упражнения (done/skip/reset).

    actor: "athlete" (по умолчанию) или "coach" — кто отмечает. Если actor=="coach",
    проверяем, что `by` (telegram_id тренера) действительно тренер этого спортсмена.
    Заполняется поле `filled_by` для real-time co-scribe.
    """
    s = await db.workout_sessions.find_one({"id": session_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    if actor == "coach" and by is None:
        raise HTTPException(status_code=400, detail="Не указан тренер (by)")
    await _assert_session_actor(current_user, s, actor, by)
    _assert_session_mutable(s)
    if actor != "coach":
        _assert_can_selffill_strength(current_user, s.get("athlete_telegram_id"))

    exs = s["exercises"]
    target = next((e for e in exs if e["order"] == order), None)
    if not target:
        raise HTTPException(status_code=404, detail="Exercise not found")

    if action == "done":
        # «Выполнить всё» = все подходы сделаны как в плане (с учётом ранее
        # внесённого факта по отдельным подходам).
        for lg in target.get("set_logs") or []:
            lg["done"] = True
            lg["skipped"] = False
        if target.get("set_logs"):
            target["sets_scheme"] = _scheme_from_logs(target["set_logs"], only_done=True)
            target["tonnage"] = scheme_tonnage(target["sets_scheme"])
        target["status"] = "done"
        target["filled_by"] = actor
    elif action == "skip":
        # «Пропустить всё» = все подходы помечаются пропущенными
        for lg in target.get("set_logs") or []:
            lg["skipped"] = True
            lg["done"] = False
        if target.get("set_logs"):
            target["sets_scheme"] = _scheme_from_logs(target["set_logs"], only_done=True)
            target["tonnage"] = scheme_tonnage(target["sets_scheme"])
        target["status"] = "skipped"
        target["filled_by"] = actor
    elif action == "reset":
        for lg in target.get("set_logs") or []:
            lg["done"] = False
            lg["skipped"] = False
        if target.get("set_logs"):
            # Возвращаем плановую схему как ориентир (упражнение снова pending)
            target["sets_scheme"] = [dict(s) for s in (target.get("plan_sets_scheme") or [])]
            target["tonnage"] = scheme_tonnage(target["sets_scheme"])
        target["status"] = "pending"
        target["filled_by"] = None
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    # Следующее ожидающее упражнение делаем активным, если активного не осталось
    if not any(e["status"] == "in_progress" for e in exs):
        nxt = next((e for e in exs if e["status"] == "pending"), None)
        if nxt:
            nxt["status"] = "in_progress"

    now = datetime.now(timezone.utc).isoformat()
    status = s.get("status", "in_progress")
    finished_at = s.get("finished_at")
    just_finished = False
    if exs and all(e["status"] in ("done", "skipped") for e in exs):
        if status != "finished":
            just_finished = True
        status = "finished"
        finished_at = finished_at or now

    set_fields = {"exercises": exs, "status": status, "finished_at": finished_at,
                  "updated_at": now, "last_event_at": now,
                  "version": (s.get("version") or 0) + 1}
    # P7: при завершении замораживаем снимок статистики тренировки
    if status == "finished":
        s["exercises"] = exs
        s["finished_at"] = finished_at
        set_fields["stats"] = _session_stats(s)
    res = await db.workout_sessions.update_one(
        {"id": session_id, "version": s.get("version") or 0},
        {"$set": set_fields},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=409, detail="Конфликт: сессия изменена. Обновите и повторите")
    s["exercises"] = exs
    s["status"] = status
    s["finished_at"] = finished_at
    s["last_event_at"] = now
    # Real-time broadcast: либо обновление, либо завершение
    await _rt_session(s.get("plan_id"), "session.finished" if just_finished else "session.updated", s)
    if just_finished:
        await _notify_user(s.get("coach_telegram_id"), "session.finished", {
            "session_id": s["id"], "plan_id": s.get("plan_id"),
            "athlete_telegram_id": s["athlete_telegram_id"],
        })
    return _serialize_session(s)


class SetLogReq(BaseModel):
    done: Optional[bool] = None
    skipped: Optional[bool] = None
    weight: Optional[float] = None
    reps: Optional[int] = None

    def validated(self):
        """Валидация входа: вес/повторы должны быть конечны и в разумных рамках."""
        if self.weight is not None:
            w = float(self.weight)
            if not math.isfinite(w) or w < 0 or w > 2000:
                raise HTTPException(status_code=400, detail="Вес должен быть от 0 до 2000 кг")
            self.weight = w
        if self.reps is not None:
            r = int(self.reps)
            if r < 0 or r > 1000:
                raise HTTPException(status_code=400, detail="Повторы должны быть от 0 до 1000")
            self.reps = r
        return self


@api_router.patch("/sessions/{session_id}/exercise/{order}/set/{set_index}")
async def log_session_set(
    session_id: str,
    order: int,
    set_index: int,
    payload: SetLogReq = Body(default=None),
    actor: str = "athlete",
    by: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    """По-подходное логирование факта: отметка подхода выполненным/пропущенным
    и/или запись фактических веса/повторов конкретного подхода.

    actor: "athlete" (по умолчанию) | "coach". Тренер (actor=="coach", by=telegram_id)
    может заполнять подходы подопечного в реальном времени (co-scribe).
    """
    s = await db.workout_sessions.find_one({"id": session_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if actor == "coach" and by is None:
        raise HTTPException(status_code=400, detail="Не указан тренер (by)")
    await _assert_session_actor(current_user, s, actor, by)
    _assert_session_mutable(s)
    if actor != "coach":
        _assert_can_selffill_strength(current_user, s.get("athlete_telegram_id"))

    exs = s["exercises"]
    target = next((e for e in exs if e["order"] == order), None)
    if not target:
        raise HTTPException(status_code=404, detail="Exercise not found")
    logs = target.get("set_logs") or []
    if set_index < 0 or set_index >= len(logs):
        raise HTTPException(status_code=404, detail="Set not found")

    payload = (payload or SetLogReq()).validated()
    lg = logs[set_index]
    changed = False
    if payload.weight is not None and payload.weight != lg.get("weight"):
        lg["weight"] = payload.weight
        changed = True
    if payload.reps is not None and int(payload.reps) != int(lg.get("reps") or 0):
        lg["reps"] = max(0, int(payload.reps))
        changed = True
    # Пропуск и выполнение — взаимоисключающие состояния подхода
    if payload.skipped is not None:
        lg["skipped"] = bool(payload.skipped)
        if lg["skipped"]:
            lg["done"] = False
    if payload.done is not None:
        lg["done"] = bool(payload.done)
        if lg["done"]:
            lg["skipped"] = False
    target["set_logs"] = logs
    if changed:
        target["edited"] = True

    # Факт. схема и тоннаж — из выполненных подходов
    target["sets_scheme"] = _scheme_from_logs(logs, only_done=True)
    target["tonnage"] = scheme_tonnage(target["sets_scheme"])

    # Статус упражнения по чек-листу: подход «улажен», если выполнен или пропущен
    settled = [bool(x.get("done") or x.get("skipped")) for x in logs]
    all_settled = len(logs) > 0 and all(settled)
    any_settled = any(settled)
    any_done = any(x.get("done") for x in logs)
    if all_settled:
        if target.get("status") not in ("done", "skipped"):
            target["filled_by"] = actor
        target["status"] = "done" if any_done else "skipped"
    else:
        target["status"] = "in_progress" if any_settled else (target.get("status") or "pending")

    # Активное упражнение: следующий pending → in_progress, если активного нет
    if not any(e["status"] == "in_progress" for e in exs):
        nxt = next((e for e in exs if e["status"] == "pending"), None)
        if nxt:
            nxt["status"] = "in_progress"

    now = datetime.now(timezone.utc).isoformat()
    status = s.get("status", "in_progress")
    finished_at = s.get("finished_at")
    just_finished = False
    all_closed = bool(exs) and all(e["status"] in ("done", "skipped") for e in exs)
    if all_closed:
        if status != "finished":
            just_finished = True
        status = "finished"
        finished_at = finished_at or now

    set_fields = {"exercises": exs, "status": status, "finished_at": finished_at,
                  "updated_at": now, "last_event_at": now,
                  "version": (s.get("version") or 0) + 1}
    if status == "finished":
        s["exercises"] = exs
        s["finished_at"] = finished_at
        set_fields["stats"] = _session_stats(s)
    res = await db.workout_sessions.update_one(
        {"id": session_id, "version": s.get("version") or 0}, {"$set": set_fields})
    if res.matched_count == 0:
        raise HTTPException(status_code=409, detail="Конфликт: сессия изменена. Обновите и повторите")
    s["exercises"] = exs
    s["status"] = status
    s["finished_at"] = finished_at
    s["last_event_at"] = now
    await _rt_session(s.get("plan_id"), "session.finished" if just_finished else "session.updated", s)
    if just_finished:
        await _notify_user(s.get("coach_telegram_id"), "session.finished", {
            "session_id": s["id"], "plan_id": s.get("plan_id"),
            "athlete_telegram_id": s["athlete_telegram_id"],
        })
    return _serialize_session(s)


class EditSessionExerciseReq(BaseModel):
    exercise_name: Optional[str] = None
    comment: Optional[str] = None
    sets_scheme: Optional[List[dict]] = None


@api_router.patch("/sessions/{session_id}/exercise/{order}/edit")
async def edit_session_exercise(
    session_id: str,
    order: int,
    payload: EditSessionExerciseReq = Body(...),
    actor: str = "athlete",
    by: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    """Редактирование упражнения сессии (кнопка ✨): имя и/или схема подходов.

    actor: "athlete" | "coach". Тренер (actor=="coach", by=telegram_id тренера)
    может править упражнение подопечного в реальном времени (co-scribe).
    Разрешено и для завершённой тренировки: кнопка-карандаш в истории."""
    s = await db.workout_sessions.find_one({"id": session_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if actor == "coach" and by is None:
        raise HTTPException(status_code=400, detail="Не указан тренер (by)")
    await _assert_session_actor(current_user, s, actor, by)
    # Редактирование разрешено и после завершения тренировки (кнопка-карандаш в
    # истории): спортсмен/тренер может исправить упражнение. Остальные мутации
    # завершённой сессии (подходы, действия) по-прежнему блокируются
    # _assert_session_mutable в своих эндпоинтах.
    if actor != "coach":
        _assert_can_selffill_strength(current_user, s.get("athlete_telegram_id"))
    plan = await db.plans.find_one({"id": s["plan_id"]}, {"_id": 0})
    orm = (plan or {}).get("one_rep_max") or {}

    exs = s["exercises"]
    target = next((e for e in exs if e["order"] == order), None)
    if not target:
        raise HTTPException(status_code=404, detail="Exercise not found")

    changed = False
    if payload.exercise_name:
        if payload.exercise_name != target.get("exercise_name"):
            changed = True
        target["exercise_name"] = payload.exercise_name[:200]
    if payload.sets_scheme is not None:
        slug = target.get("exercise_slug")
        old_norm = [
            (float(s.get("weight")) if s.get("weight") is not None else None,
             int(s.get("sets") or 0), int(s.get("reps") or 0))
            for s in (target.get("sets_scheme") or [])
        ]
        new_sets = []
        for st in payload.sets_scheme:
            if not isinstance(st, dict):
                raise HTTPException(status_code=400, detail="sets_scheme должен быть списком объектов")
            w = st.get("weight")
            if w is not None:
                try:
                    w = float(w)
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail="Некорректный вес в sets_scheme")
                if not math.isfinite(w) or w < 0 or w > 2000:
                    raise HTTPException(status_code=400, detail="Вес должен быть от 0 до 2000 кг")
            try:
                sets = max(1, int(st.get("sets") or 1))
                reps = max(0, int(st.get("reps") or 0))
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Некорректные подходы/повторы в sets_scheme")
            if sets > 100 or reps > 1000:
                raise HTTPException(status_code=400, detail="Слишком большие подходы/повторы")
            new_sets.append({
                "weight": w,
                "sets": sets,
                "reps": reps,
                "percent_1rm": percent_of(w, slug, orm),
            })
        new_norm = [
            (float(s["weight"]) if s["weight"] is not None else None, s["sets"], s["reps"])
            for s in new_sets
        ]
        if new_norm != old_norm:
            changed = True
        target["sets_scheme"] = new_sets
        target["tonnage"] = scheme_tonnage(new_sets)
        old_logs = target.get("set_logs") or []
        if old_logs:
            new_logs = _expand_set_logs(new_sets)
            for i, nl in enumerate(new_logs):
                if i < len(old_logs):
                    if old_logs[i].get("done"):
                        nl["done"] = True
                    if old_logs[i].get("skipped"):
                        nl["skipped"] = True
            target["set_logs"] = new_logs
            if target.get("status") == "done":
                target["sets_scheme"] = _scheme_from_logs(new_logs, only_done=True)
                target["tonnage"] = scheme_tonnage(target["sets_scheme"])
    if payload.comment is not None:
        c = payload.comment.strip()
        target["comment"] = c[:500] if c else None
    if changed:
        target["edited"] = True

    now = datetime.now(timezone.utc).isoformat()
    set_fields = {"exercises": exs, "updated_at": now, "last_event_at": now,
                  "version": (s.get("version") or 0) + 1}
    if s.get("status") == "finished":
        # История: пересчитываем «замороженную» статистику, чтобы тоннаж/объём
        # завершённой тренировки совпадали с исправленными упражнениями.
        set_fields["stats"] = _session_stats(dict(s, exercises=exs))
    res = await db.workout_sessions.update_one(
        {"id": session_id, "version": s.get("version") or 0},
        {"$set": set_fields},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=409, detail="Конфликт: сессия изменена. Обновите и повторите")
    s["exercises"] = exs
    s["last_event_at"] = now
    await _rt_session(s.get("plan_id"), "session.updated", s)
    return _serialize_session(s)


@api_router.post("/sessions/{session_id}/finish")
async def finish_session(session_id: str, current_user: dict = Depends(get_current_user)):
    s = await db.workout_sessions.find_one({"id": session_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    await _assert_session_actor(current_user, s, "athlete", None)
    if s.get("status") == "finished":
        # Идемпотентность: повторный finish не шлёт повторных уведомлений.
        return _serialize_session(s)
    now = datetime.now(timezone.utc).isoformat()
    finished_at = s.get("finished_at") or now
    s["status"] = "finished"
    s["finished_at"] = finished_at
    frozen = _session_stats(s)
    
    # Обновить статус с live_status
    await db.workout_sessions.update_one(
        {"id": session_id},
        {"$set": {
            "status": "finished",
            "finished_at": finished_at,
            "updated_at": now,
            "last_event_at": now,
            "stats": frozen,
            "paused": False,
            "live_status": "completed",
            "status_updated_at": datetime.now(timezone.utc)
        }},
    )
    
    s["last_event_at"] = now
    s["live_status"] = "completed"
    
    # WebSocket broadcast
    await _rt_session(s.get("plan_id"), "session.finished", s)
    
    # WebSocket broadcast live-статуса тренеру (личная комната user:{tgid})
    if s.get("coach_telegram_id"):
        await manager.broadcast(f"user:{s['coach_telegram_id']}", "client_status_change", {
            "athlete_telegram_id": s["athlete_telegram_id"],
            "status": "completed",
            "session_id": session_id
        })
    
    await _notify_user(s.get("coach_telegram_id"), "session.finished", {
        "session_id": s["id"], "plan_id": s.get("plan_id"),
        "athlete_telegram_id": s["athlete_telegram_id"],
    })
    
    # Отправить Telegram уведомление тренеру
    try:
        await notify_coach_on_workout_complete(db, session_id, s["athlete_telegram_id"])
    except Exception as e:
        logger.warning(f"Failed to send notification to coach: {e}")
    
    return _serialize_session(s)


@api_router.post("/sessions/{session_id}/resume")
async def resume_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """Продолжить ранее завершённую тренировку, СОХРАНИВ отметки о выполненных
    упражнениях. Сессия снова становится активной (in_progress); следующее
    невыполненное упражнение делается текущим. Запрещаем, если у спортсмена уже
    есть ДРУГАЯ активная тренировка (409)."""
    s = await db.workout_sessions.find_one({"id": session_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    await _assert_session_actor(current_user, s, "athlete", None)
    if s.get("status") != "finished":
        # Уже активна — ничего не делаем (идемпотентно).
        return _serialize_session(s)

    active_other = await db.workout_sessions.find_one(
        {"athlete_telegram_id": s["athlete_telegram_id"], "status": "in_progress",
         "paused": {"$ne": True},
         "id": {"$ne": session_id}},
        {"_id": 0},
    )
    if active_other:
        raise HTTPException(status_code=409, detail={
            "error": "active_session_exists",
            "message": "У вас уже есть активная тренировка. Завершите её, чтобы продолжить эту.",
            "session_id": active_other["id"],
            "plan_id": active_other.get("plan_id"),
            "week_index": active_other.get("week_index"),
            "day_index": active_other.get("day_index"),
        })

    now = datetime.now(timezone.utc).isoformat()
    exs = s.get("exercises") or []
    # Сохраняем все отметки (done/skipped/filled_by). Просто
    # реактивируем следующее невыполненное упражнение, если активного нет.
    if not any(e.get("status") == "in_progress" for e in exs):
        nxt = next((e for e in exs if e.get("status") == "pending"), None)
        if nxt:
            nxt["status"] = "in_progress"

    set_fields = {
        "exercises": exs,
        "status": "in_progress",
        "paused": False,
        "finished_at": None,
        "stats": None,  # сброс замороженного снимка: после возобновления он неактуален
        "last_event_at": now,
        "updated_at": now,
        "live_status": "on_workout",
        "status_updated_at": datetime.now(timezone.utc),
        "version": (s.get("version") or 0) + 1,
    }
    res = await db.workout_sessions.update_one(
        {"id": session_id, "version": s.get("version") or 0}, {"$set": set_fields})
    if res.matched_count == 0:
        raise HTTPException(status_code=409, detail="Конфликт: сессия изменена. Обновите и повторите")
    s2 = await db.workout_sessions.find_one({"id": session_id}, {"_id": 0})
    logger.info(f"Session resumed: {session_id}")
    await _rt_session(s2.get("plan_id"), "session.updated", s2)
    await _notify_user(s2.get("coach_telegram_id"), "session.updated", {
        "session_id": s2["id"], "plan_id": s2.get("plan_id"),
        "athlete_telegram_id": s2["athlete_telegram_id"],
    })
    return _serialize_session(s2)


@api_router.post("/sessions/{session_id}/pause")
async def pause_session(session_id: str, resume: bool = False, current_user: dict = Depends(get_current_user)):
    s = await db.workout_sessions.find_one({"id": session_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    await _assert_session_actor(current_user, s, "athlete", None)
    if s.get("status") != "in_progress":
        raise HTTPException(status_code=409, detail="Тренировка не активна")
    now = datetime.now(timezone.utc).isoformat()
    new_paused = not resume
    res = await db.workout_sessions.update_one(
        {"id": session_id, "version": s.get("version") or 0},
        {"$set": {"paused": new_paused, "updated_at": now, "last_event_at": now,
                  "live_status": "on_workout" if not new_paused else s.get("live_status", "on_workout"),
                  "status_updated_at": datetime.now(timezone.utc),
                  "version": (s.get("version") or 0) + 1}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=409, detail="Конфликт: сессия изменена. Обновите и повторите")
    s["paused"] = new_paused
    s["last_event_at"] = now
    await _rt_session(s.get("plan_id"), "session.updated", s)
    return _serialize_session(s)


class ConfirmReq(BaseModel):
    coach_telegram_id: Optional[int] = None


@api_router.post("/sessions/{session_id}/confirm")
async def confirm_session(session_id: str, payload: ConfirmReq = Body(default=None),
                          current_user: dict = Depends(get_current_user)):
    """Тренер подтверждает всю тренировку подопечного."""
    s = await db.workout_sessions.find_one({"id": session_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    payload = payload or ConfirmReq()
    if payload.coach_telegram_id is None:
        raise HTTPException(status_code=400, detail="Не указан тренер (coach_telegram_id)")
    await _assert_session_actor(current_user, s, "coach", payload.coach_telegram_id)
    now = datetime.now(timezone.utc).isoformat()
    res = await db.workout_sessions.update_one(
        {"id": session_id, "version": s.get("version") or 0},
        {"$set": {"coach_confirmed": True, "confirmed_by": payload.coach_telegram_id,
                  "confirmed_at": now, "session_confirmed_at": now,
                  "updated_at": now, "last_event_at": now,
                  "version": (s.get("version") or 0) + 1}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=409, detail="Конфликт: сессия изменена. Обновите и повторите")
    s.update({"coach_confirmed": True, "confirmed_by": payload.coach_telegram_id,
              "confirmed_at": now, "session_confirmed_at": now,
              "last_event_at": now, "version": (s.get("version") or 0) + 1})
    await _rt_session(s.get("plan_id"), "session.confirmed", s)
    return _serialize_session(s)


@api_router.patch("/sessions/{session_id}/exercise/{order}/confirm")
async def confirm_session_exercise(session_id: str, order: int,
                                   payload: ConfirmReq = Body(default=None),
                                   current_user: dict = Depends(get_current_user)):
    """Тренер подтверждает/снимает подтверждение упражнения (toggle)."""
    s = await db.workout_sessions.find_one({"id": session_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    payload = payload or ConfirmReq()
    if payload.coach_telegram_id is None:
        raise HTTPException(status_code=400, detail="Не указан тренер (coach_telegram_id)")
    await _assert_session_actor(current_user, s, "coach", payload.coach_telegram_id)
    exs = s.get("exercises") or []
    target = next((e for e in exs if e["order"] == order), None)
    if not target:
        raise HTTPException(status_code=404, detail="Exercise not found")
    now = datetime.now(timezone.utc).isoformat()
    if target.get("coach_confirmed"):
        target["coach_confirmed"] = False
        target["confirmed_by"] = None
        target["confirmed_at"] = None
    else:
        target["coach_confirmed"] = True
        target["confirmed_by"] = payload.coach_telegram_id
        target["confirmed_at"] = now
    res = await db.workout_sessions.update_one(
        {"id": session_id, "version": s.get("version") or 0},
        {"$set": {"exercises": exs, "updated_at": now, "last_event_at": now,
                  "version": (s.get("version") or 0) + 1}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=409, detail="Конфликт: сессия изменена. Обновите и повторите")
    s["exercises"] = exs
    s["last_event_at"] = now
    await _rt_session(s.get("plan_id"), "exercise.confirmed", s)
    return _serialize_session(s)


# ---- Сводная статистика спортсмена (серия/streak) ----
@api_router.get("/stats/{telegram_id}")
async def get_athlete_stats(telegram_id: int, current: dict = Depends(get_current_user)):
    await _assert_can_read_stats(current, telegram_id)
    sessions = await db.workout_sessions.find(
        {"athlete_telegram_id": telegram_id, "status": "finished"},
        {"_id": 0, "finished_at": 1, "date": 1, "exercises": 1},
    ).to_list(2000)
    # Засчитываем тренировку только если реально выполнено хотя бы одно упражнение
    valid = [s for s in sessions
             if any(e.get("status") == "done" for e in (s.get("exercises") or []))]
    streak, active_days = _calendar_streak(valid)
    return {"telegram_id": telegram_id, "streak_days": streak,
            "total_workouts": len(valid), "active_days": active_days}


# ===========================================================================
# P7 — Хелперы агрегированной статистики и пропусков
# ===========================================================================
from seed import LETTER_ORDER as _LETTER_ORDER  # порядок букв групп мышц

_LETTER_NAMES = {
    "Н": "Ноги", "Г": "Грудь", "С": "Спина", "П": "Плечи", "Р": "Руки", "К": "Кор",
}
_LIFT_NAMES = {"squat": "Присед", "bench": "Жим", "deadlift": "Становая"}


def _parse_date(s):
    if not s:
        return None
    try:
        if "T" in s:
            return datetime.fromisoformat(s).date()
        return date.fromisoformat(s[:10])
    except Exception:
        try:
            return date.fromisoformat(str(s)[:10])
        except Exception:
            return None


def _session_day(s):
    """Единый календарный день сессии: date (день по плану) → finished_at."""
    return _parse_date(s.get("date")) or _parse_date(s.get("finished_at"))


def _iso_week_key(d):
    if not d:
        return None
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _get_session_stats(s):
    """Берём замороженный снимок статистики, иначе считаем на лету."""
    st = s.get("stats")
    if st and isinstance(st, dict) and "tonnage" in st:
        return st
    return _session_stats(s)


def _plan_planned_days(plan):
    """Список запланированных (не-rest) тренировочных дней плана с числом подходов."""
    days = []
    for w in (plan.get("weeks") or []):
        wi = w.get("week_index")
        for d in (w.get("days") or []):
            if d.get("is_rest"):
                continue
            exs = d.get("exercises") or []
            if not exs:
                continue
            sets_planned = 0
            for e in exs:
                sc = e.get("sets_scheme") or []
                sets_planned += _sets_count(sc) if sc else int(e.get("target_sets") or 0)
            days.append({
                "week_index": wi,
                "day_index": d.get("day_index"),
                "title": d.get("title", ""),
                "exercise_count": len(exs),
                "sets_planned": sets_planned,
            })
    days.sort(key=lambda x: (x["week_index"] or 0, x["day_index"] or 0))
    return days


async def _collect_day_marks(plan_id):
    docs = await db.plan_day_marks.find({"plan_id": plan_id}, {"_id": 0}).to_list(2000)
    return {(d.get("week_index"), d.get("day_index")): d for d in docs}


async def _streak_mode(tg):
    u = await db.users.find_one({"telegram_id": tg}, {"_id": 0, "settings": 1})
    return ((u or {}).get("settings") or {}).get("streak_mode") or "strict"


async def _schedule_and_streak(plan, streak_mode):
    """Adherence по расписанию + тренировочный streak (с учётом пропусков/переносов).

    Дни без привязки к календарю: «достигнутые» дни — все запланированные дни
    до самого дальнего (week, day), на котором уже была сессия (фронтир)."""
    plan_id = plan["id"]
    planned = _plan_planned_days(plan)
    sess = await db.workout_sessions.find(
        {"plan_id": plan_id},
        {"_id": 0, "week_index": 1, "day_index": 1, "status": 1, "exercises": 1},
    ).to_list(3000)
    completed = set()
    frontier = None
    for s in sess:
        t = (s.get("week_index") or 1, s.get("day_index") or 1)
        if frontier is None or t > frontier:
            frontier = t
        if s.get("status") == "finished" and any(
            e.get("status") == "done" for e in (s.get("exercises") or [])
        ):
            completed.add(t)
    marks = await _collect_day_marks(plan_id)
    reached = [p for p in planned
               if frontier and (p["week_index"], p["day_index"]) <= frontier]

    counts = {"completed": 0, "missed": 0, "skipped": 0, "excused": 0, "rescheduled": 0}
    rows = []
    num = denom = 0
    for p in reached:
        k = (p["week_index"], p["day_index"])
        if k in completed:
            status = "completed"
            num += 1
            denom += 1
        elif k in marks:
            status = marks[k].get("status") or "skipped"
            if status not in ("excused", "rescheduled"):
                denom += 1
        else:
            status = "missed"
            denom += 1
        counts[status] = counts.get(status, 0) + 1
        rows.append({**p, "status": status, "mark": marks.get(k)})

    schedule_pct = round(num / denom * 100) if denom else 0

    streak = 0
    for p in reversed(reached):
        k = (p["week_index"], p["day_index"])
        if k in completed:
            streak += 1
            continue
        if k in marks:
            ms = marks[k].get("status")
            if ms in ("excused", "rescheduled"):
                continue
            if ms == "skipped" and streak_mode == "lenient" and marks[k].get("reason"):
                continue
        break

    return {
        "rows": rows, "counts": counts, "schedule_pct": schedule_pct,
        "workout_streak": streak, "planned_total": len(planned),
        "reached_total": len(reached), "marks": marks, "frontier": frontier,
    }


def _calendar_streak(sessions):
    dates = set()
    for s in sessions:
        if not any(e.get("status") == "done" for e in (s.get("exercises") or [])):
            continue
        d = _session_day(s)
        if d:
            dates.add(d)
    streak = 0
    if dates:
        today = datetime.now(timezone.utc).date()
        cur = today if today in dates else (today - timedelta(days=1))
        while cur in dates:
            streak += 1
            cur = cur - timedelta(days=1)
    return streak, len(dates)


async def _finished_sessions(tg, plan_id=None, frm=None, to=None):
    q = {"athlete_telegram_id": tg, "status": "finished"}
    if plan_id:
        q["plan_id"] = plan_id
    docs = await db.workout_sessions.find(q, {"_id": 0}).sort("finished_at", 1).to_list(3000)
    fr = _parse_date(frm) if frm else None
    tt = _parse_date(to) if to else None
    out = []
    for s in docs:
        if not any(e.get("status") == "done" for e in (s.get("exercises") or [])):
            continue
        d = _session_day(s)
        if (fr or tt) and not d:
            continue
        if fr and d < fr:
            continue
        if tt and d > tt:
            continue
        out.append(s)
    return out


async def _resolve_stats_plan(tg, plan_id):
    if plan_id:
        p = await db.plans.find_one({"id": plan_id}, {"_id": 0})
        if p:
            return p
    return await db.plans.find_one(
        {"athlete_telegram_id": tg, "status": "active"}, {"_id": 0}
    )


async def _athlete_detailed_stats(tg, frm=None, to=None, plan_id=None):
    plan = await _resolve_stats_plan(tg, plan_id)
    use_plan_week = bool(plan_id and plan)   # по микроциклам только при явном выборе плана
    sessions = await _finished_sessions(tg, plan_id if plan_id else None, frm, to)

    # Если фильтр по плану ничего не дал, но план есть — оставляем пусто (честно)
    total_tonnage = total_tonnage_planned = 0
    total_sets_done = total_sets_planned = 0
    total_duration = 0
    progress_acc = 0
    week_agg = {}
    muscle_agg = {}
    lift_best = {}  # lift_group -> {top_weight, one_rm}

    for s in sessions:
        st = _get_session_stats(s)
        total_tonnage += st.get("tonnage", 0) or 0
        total_tonnage_planned += st.get("tonnage_planned", 0) or 0
        total_sets_done += st.get("sets_done", 0) or 0
        total_sets_planned += st.get("sets_planned", 0) or 0
        total_duration += st.get("duration_sec", 0) or 0
        progress_acc += st.get("progress_pct", 0) or 0

        if use_plan_week:
            wi = s.get("week_index") or 1
            key, label, srt = wi, f"Нед {wi}", (wi,)
        else:
            d = _session_day(s)
            key = _iso_week_key(d) or "—"
            label, srt = key, (key,)
        a = week_agg.setdefault(key, {"tonnage": 0, "count": 0, "label": label, "sort": srt})
        a["tonnage"] += st.get("tonnage", 0) or 0
        a["count"] += 1

        # Считаем свежо из упражнений (а не из замороженного снимка), чтобы
        # исправленные формулы применялись и к историческим данным.
        for ltr, cnt in _muscle_sets(s.get("exercises") or []).items():
            muscle_agg[ltr] = muscle_agg.get(ltr, 0) + cnt
        for lg, info in _lift_summary(s.get("exercises") or []).items():
            cur = lift_best.get(lg)
            if not cur or (info.get("one_rm") or info.get("top_weight") or 0) > (
                cur.get("one_rm") or cur.get("top_weight") or 0
            ):
                lift_best[lg] = info

    n = len(sessions)
    week_rows = sorted(week_agg.values(), key=lambda x: x["sort"])
    tonnage_by_week = [{"week": r["label"], "tonnage": round(r["tonnage"])} for r in week_rows]
    frequency_by_week = [{"week": r["label"], "count": r["count"]} for r in week_rows]
    muscle_distribution = [
        {"group": ltr, "label": _LETTER_NAMES.get(ltr, ltr), "sets": muscle_agg[ltr]}
        for ltr in _LETTER_ORDER if ltr in muscle_agg
    ]
    for ltr in muscle_agg:  # буквы вне стандартного порядка
        if ltr not in _LETTER_ORDER:
            muscle_distribution.append(
                {"group": ltr, "label": _LETTER_NAMES.get(ltr, ltr), "sets": muscle_agg[ltr]}
            )

    # Оценка 1ПМ: план (по программе) + достигнутое (как в таблице)
    plan_maxes = (plan.get("maxes") if plan else {}) or {}
    one_rep_max_est = []
    for lift, name in _LIFT_NAMES.items():
        planned_v = plan_maxes.get(lift)
        ach = lift_best.get(lift) or {}
        achieved_v = ach.get("one_rm")
        top_v = ach.get("top_weight")
        if planned_v or achieved_v:
            one_rep_max_est.append({
                "lift": lift, "name": name,
                "planned": planned_v, "achieved": achieved_v, "top_weight": top_v,
            })

    cal_streak, _ = _calendar_streak(sessions)
    sched = None
    workout_streak = cal_streak
    if plan:
        sched = await _schedule_and_streak(plan, await _streak_mode(tg))
        workout_streak = sched["workout_streak"]

    completion_pct = min(100, round(total_sets_done / total_sets_planned * 100)) if total_sets_planned else (
        min(100, round(progress_acc / n)) if n else 0
    )
    tonnage_dev_pct = round(
        (total_tonnage - total_tonnage_planned) / total_tonnage_planned * 100
    ) if total_tonnage_planned else 0
    volume_pct = min(100, round(total_sets_done / total_sets_planned * 100)) if total_sets_planned else 0

    # Частота: по микроциклам выбранного плана или по календарным неделям
    if use_plan_week:
        avg_per_week = round(n / len(week_agg), 1) if week_agg else 0
    else:
        cal_weeks = {}
        for s in sessions:
            d = _session_day(s)
            wk = _iso_week_key(d)
            if wk:
                cal_weeks[wk] = cal_weeks.get(wk, 0) + 1
        avg_per_week = round(sum(cal_weeks.values()) / len(cal_weeks), 1) if cal_weeks else 0

    recent = []
    for s in sorted(sessions, key=lambda x: x.get("finished_at") or "", reverse=True)[:10]:
        st = _get_session_stats(s)
        recent.append({
            "id": s.get("id"), "date": s.get("date"),
            "finished_at": s.get("finished_at"),
            "title": s.get("title") or "Тренировка",
            "week_index": s.get("week_index"), "day_index": s.get("day_index"),
            "tonnage": st.get("tonnage", 0), "duration_sec": st.get("duration_sec", 0),
            "progress_pct": st.get("progress_pct", 0), "group": st.get("group", ""),
            "difficulty": st.get("difficulty"), "done_count": st.get("done_count", 0),
            "total_count": st.get("total_count", 0),
        })

    summary = {
        "total_workouts": n,
        "streak_days": cal_streak,
        "workout_streak": workout_streak,
        "avg_per_week": avg_per_week,
        "completion_pct": completion_pct,
        "total_tonnage": round(total_tonnage),
        "total_duration_sec": total_duration,
        "total_sets": total_sets_done,
    }
    adherence = {
        "volume_pct": volume_pct,
        "schedule_pct": sched["schedule_pct"] if sched else None,
        "tonnage_dev_pct": tonnage_dev_pct,
    }
    skip_counts = sched["counts"] if sched else {}

    return {
        "telegram_id": tg,
        "plan_id": plan.get("id") if plan else None,
        "plan_name": plan.get("name") if plan else None,
        "range": {"from": frm, "to": to},
        "summary": summary,
        "tonnage_by_week": tonnage_by_week,
        "frequency_by_week": frequency_by_week,
        "muscle_distribution": muscle_distribution,
        "one_rep_max_est": one_rep_max_est,
        "adherence": adherence,
        "skip_counts": skip_counts,
        "recent_sessions": recent,
    }


async def _athlete_exercise_progress(tg, slug=None, plan_id=None):
    # B4: без явного plan_id считаем «за всё время» (по всем планам, группировка по датам)
    plan = (await _resolve_stats_plan(tg, plan_id)) if plan_id else None
    by_plan = bool(plan)
    sessions = await _finished_sessions(tg, plan["id"] if plan else None)

    avail = {}
    weighted = set()
    for s in sessions:
        for e in (s.get("exercises") or []):
            sg = e.get("exercise_slug") or e.get("exercise_name")
            if not sg:
                continue
            if sg not in avail:
                avail[sg] = {
                    "slug": e.get("exercise_slug"),
                    "key": sg,
                    "name": e.get("exercise_name"),
                    "lift_group": e.get("lift_group"),
                }
            if e.get("status") == "done" and _top_set(e.get("sets_scheme")):
                weighted.add(sg)
    # B5: в выпадающем списке — только упражнения с рабочим весом
    avail = {k: v for k, v in avail.items() if k in weighted}

    target = slug
    if not target:
        for sg, info in avail.items():
            if info.get("lift_group"):
                target = sg
                break
        if not target and avail:
            target = next(iter(avail))

    series_map = {}
    for s in sessions:
        if by_plan:
            key = s.get("week_index") or 1
            label = f"Нед {key}"
            sort_key = (key,)
        else:
            d = _session_day(s)
            if not d:
                continue
            key = d.isoformat()
            label = d.strftime("%d.%m")
            sort_key = (key,)
        for e in (s.get("exercises") or []):
            if e.get("status") != "done":
                continue
            sg = e.get("exercise_slug") or e.get("exercise_name")
            if sg != target:
                continue
            fact_top = _top_set(e.get("sets_scheme"))
            if not fact_top:
                continue
            plan_top = _top_set(e.get("plan_sets_scheme")) or fact_top
            fw = fact_top.get("weight")
            pct = (plan_top or {}).get("percent_1rm") or fact_top.get("percent_1rm")
            one_rm = _est_1rm(fw, pct, fact_top.get("reps"))
            cand = {
                "label": label, "sort": sort_key,
                "week_index": s.get("week_index") if by_plan else None,
                "date": None if by_plan else key,
                "top_weight": fw, "plan_weight": (plan_top or {}).get("weight"),
                "reps": fact_top.get("reps"), "one_rm": one_rm,
                "tonnage": e.get("tonnage", 0),
            }
            row = series_map.get(key)
            if not row or (fw or 0) > (row.get("top_weight") or 0):
                series_map[key] = cand
    series = sorted(series_map.values(), key=lambda x: x["sort"])
    for r in series:
        r.pop("sort", None)
    return {
        "telegram_id": tg, "slug": target,
        "scope": "plan" if by_plan else "all",
        "name": (avail.get(target) or {}).get("name") if target else None,
        "exercises": list(avail.values()),
        "series": series,
    }


# ---- P2.1: пропуски/переносы тренировочных дней ----
async def _upsert_day_mark(plan, week, day, status, reason=None,
                           rescheduled_to=None, marked_by=None):
    plan_id = plan["id"]
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.plan_day_marks.find_one(
        {"plan_id": plan_id, "week_index": week, "day_index": day}, {"_id": 0}
    )
    if existing:
        set_fields = {"status": status, "updated_at": now}
        if reason is not None:
            set_fields["reason"] = reason
        if rescheduled_to is not None:
            set_fields["rescheduled_to"] = rescheduled_to
        if marked_by is not None:
            set_fields["marked_by"] = marked_by
        await db.plan_day_marks.update_one(
            {"plan_id": plan_id, "week_index": week, "day_index": day},
            {"$set": set_fields},
        )
        existing.update(set_fields)
        return existing
    mark = PlanDayMark(
        plan_id=plan_id, athlete_telegram_id=plan["athlete_telegram_id"],
        week_index=week, day_index=day, status=status, reason=reason,
        rescheduled_to=rescheduled_to, marked_by=marked_by,
    )
    doc = mark.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    doc["updated_at"] = doc["updated_at"].isoformat()
    try:
        await db.plan_day_marks.insert_one(dict(doc))
    except DuplicateKeyError:
        # Гонка: параллельная пометка того же дня — обновляем существующую.
        await db.plan_day_marks.update_one(
            {"plan_id": plan_id, "week_index": week, "day_index": day},
            {"$set": {"status": status, "reason": reason,
                      "rescheduled_to": rescheduled_to, "marked_by": marked_by,
                      "updated_at": now}},
        )
        doc = await db.plan_day_marks.find_one(
            {"plan_id": plan_id, "week_index": week, "day_index": day}, {"_id": 0}
        )
    return doc


@api_router.post("/plans/{plan_id}/day/skip")
async def skip_plan_day(plan_id: str, payload: DaySkipReq,
                        current: dict = Depends(get_current_user)):
    """Спортсмен/тренер помечает день плана пропущенным (с причиной)."""
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    by = current.get("telegram_id")
    mark = await _upsert_day_mark(plan, payload.week, payload.day, "skipped",
                                  reason=payload.reason, marked_by=by)
    await _rt_plan(plan_id, "day.skipped", {
        "week_index": payload.week, "day_index": payload.day,
        "status": "skipped", "reason": payload.reason,
    })
    return mark


@api_router.post("/plans/{plan_id}/day/reschedule")
async def reschedule_plan_day(plan_id: str, payload: DayRescheduleReq,
                              current: dict = Depends(get_current_user)):
    """Перенос тренировочного дня на другую дату (не считается пропуском)."""
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    by = current.get("telegram_id")
    try:
        datetime.strptime(payload.rescheduled_to, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="rescheduled_to должен быть датой YYYY-MM-DD")
    mark = await _upsert_day_mark(plan, payload.week, payload.day, "rescheduled",
                                  reason=payload.reason,
                                  rescheduled_to=payload.rescheduled_to, marked_by=by)
    await _rt_plan(plan_id, "day.rescheduled", {
        "week_index": payload.week, "day_index": payload.day,
        "rescheduled_to": payload.rescheduled_to,
    })
    return mark


@api_router.patch("/plans/{plan_id}/day/{week}/{day}/mark")
async def mark_plan_day(plan_id: str, week: int, day: int, payload: DayMarkReq,
                        current: dict = Depends(get_current_user)):
    """Тренер/владелец помечает день: excused (уважительный) / missed / skipped."""
    if payload.status not in ("excused", "missed", "skipped"):
        raise HTTPException(status_code=400, detail="status: excused | missed | skipped")
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    by = current.get("telegram_id")
    mark = await _upsert_day_mark(plan, week, day, payload.status,
                                  reason=payload.reason, marked_by=by)
    await _rt_plan(plan_id, "day.marked", {
        "week_index": week, "day_index": day, "status": payload.status,
    })
    return mark


@api_router.delete("/plans/{plan_id}/day/{week}/{day}/mark")
async def unmark_plan_day(plan_id: str, week: int, day: int,
                          current: dict = Depends(get_current_user)):
    """Снять пометку с дня (вернуть в обычное состояние)."""
    plan = await _get_plan_or_404(plan_id)
    await _assert_can_edit_plan(current, plan)
    res = await db.plan_day_marks.delete_one(
        {"plan_id": plan_id, "week_index": week, "day_index": day}
    )
    await _rt_plan(plan_id, "day.unmarked", {"week_index": week, "day_index": day})
    return {"deleted": res.deleted_count}


@api_router.get("/plans/{plan_id}/missed")
async def get_plan_missed(plan_id: str, current: dict = Depends(get_current_user)):
    """Список пропущенных/перенесённых дней + авто-определённые missed-дни."""
    plan = await _get_plan_or_404(plan_id)
    # IDOR-защита: владелец или его тренер.
    tgid = current["telegram_id"]
    if plan.get("athlete_telegram_id") != tgid and not await _is_coach_of(tgid, plan.get("athlete_telegram_id")):
        raise HTTPException(status_code=403, detail="Forbidden")
    sched = await _schedule_and_streak(plan, await _streak_mode(plan["athlete_telegram_id"]))
    days = [r for r in sched["rows"] if r["status"] != "completed"]
    # Явные пометки за пределами «достигнутых» дней — тоже показываем
    reached_keys = {(r["week_index"], r["day_index"]) for r in sched["rows"]}
    for (w, d), m in (sched["marks"] or {}).items():
        if (w, d) not in reached_keys:
            days.append({
                "week_index": w, "day_index": d, "title": "",
                "status": m.get("status"), "mark": m,
            })
    days.sort(key=lambda x: (x["week_index"] or 0, x["day_index"] or 0))
    return {
        "plan_id": plan_id, "days": days, "counts": sched["counts"],
        "schedule_pct": sched["schedule_pct"], "workout_streak": sched["workout_streak"],
        "planned_total": sched["planned_total"], "reached_total": sched["reached_total"],
    }


# ---- P7: отклонения сессии и подробная статистика ----
@api_router.get("/sessions/{session_id}/deviation")
async def get_session_deviation(session_id: str, current_user: dict = Depends(get_current_user)):
    """План vs факт по упражнениям одной тренировки."""
    s = await db.workout_sessions.find_one({"id": session_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    await _assert_session_read(current_user, s)
    return {
        "session_id": session_id,
        "stats": _get_session_stats(s),
        "exercises": _session_deviation(s),
    }


@api_router.get("/stats/{telegram_id}/detailed")
async def stats_detailed(telegram_id: int, from_: Optional[str] = Query(default=None, alias="from"),
                         to: Optional[str] = None, plan_id: Optional[str] = None,
                         current: dict = Depends(get_current_user)):
    await _assert_can_read_stats(current, telegram_id)
    return await _athlete_detailed_stats(telegram_id, from_, to, plan_id)


@api_router.get("/stats/{telegram_id}/exercise-progress")
async def stats_exercise_progress(telegram_id: int, slug: Optional[str] = None,
                                  plan_id: Optional[str] = None,
                                  current: dict = Depends(get_current_user)):
    await _assert_can_read_stats(current, telegram_id)
    return await _athlete_exercise_progress(telegram_id, slug, plan_id)


@api_router.get("/stats/{telegram_id}/muscle-groups")
async def stats_muscle_groups(telegram_id: int, period: str = "week",
                               current: dict = Depends(get_current_user)):
    """Статистика по мышечным группам: объём (вес × повторы × подходы) за период."""
    await _assert_can_read_stats(current, telegram_id)
    
    # Определяем временной диапазон
    today = datetime.now(timezone.utc).date()
    if period == "week":
        start_date = today - timedelta(days=7)
    elif period == "month":
        start_date = today - timedelta(days=30)
    else:  # all
        start_date = None
    
    end_date = today
    
    # Получаем завершённые сессии за период
    query = {"athlete_telegram_id": telegram_id, "status": "finished"}
    if start_date:
        query["date"] = {"$gte": start_date.isoformat()}
    
    sessions = await db.workout_sessions.find(query, {"_id": 0}).to_list(3000)
    
    # Получаем справочник упражнений для маппинга muscle_groups
    exercises_catalog = await db.exercises.find(
        {"$or": [{"is_builtin": True}, {"owner_telegram_id": telegram_id}]},
        {"_id": 0, "id": 1, "slug": 1, "muscle_groups": 1, "secondary_groups": 1}
    ).to_list(1000)
    
    # Создаём индексы для быстрого поиска
    ex_by_id = {ex["id"]: ex for ex in exercises_catalog if ex.get("id")}
    ex_by_slug = {ex["slug"]: ex for ex in exercises_catalog if ex.get("slug")}
    
    # Собираем статистику по мышечным группам
    muscle_stats = {}
    
    for session in sessions:
        for exercise in session.get("exercises", []):
            if exercise.get("status") != "done":
                continue
            
            # Находим определение упражнения
            ex_def = None
            if exercise.get("exercise_id"):
                ex_def = ex_by_id.get(exercise["exercise_id"])
            elif exercise.get("exercise_slug"):
                ex_def = ex_by_slug.get(exercise["exercise_slug"])
            
            if not ex_def:
                continue
            
            # Получаем primary и secondary группы мышц
            primary_groups = ex_def.get("muscle_groups", [])
            secondary_groups = ex_def.get("secondary_groups", [])
            
            # Считаем объём (volume = weight × reps × sets)
            volume = 0
            sessions_count = 1
            
            for set_log in exercise.get("set_logs", []):
                if set_log.get("done"):
                    weight = set_log.get("weight", 0) or 0
                    reps = set_log.get("reps", 0) or 0
                    volume += weight * reps
            
            # Распределяем объём: primary получают 100%, secondary получают 50%
            for mg in primary_groups:
                if mg not in muscle_stats:
                    muscle_stats[mg] = {"volume": 0, "sessions": set()}
                muscle_stats[mg]["volume"] += volume
                muscle_stats[mg]["sessions"].add(session.get("id"))
            
            for mg in secondary_groups:
                if mg not in muscle_stats:
                    muscle_stats[mg] = {"volume": 0, "sessions": set()}
                muscle_stats[mg]["volume"] += volume * 0.5  # Secondary = 50% volume
                muscle_stats[mg]["sessions"].add(session.get("id"))
    
    # Форматируем результат
    muscle_groups = {}
    for mg, stats in muscle_stats.items():
        muscle_groups[mg] = {
            "volume": round(stats["volume"]),
            "sessions": len(stats["sessions"])
        }
    
    return {
        "period": period,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat(),
        "muscle_groups": muscle_groups
    }


# --- Фаза 2: карта мышц 2D ---

def _build_muscle_map(sessions, ex_by_id, ex_by_slug) -> dict:
    """Чистый агрегатор карты мышц: объём/рабочие подходы/сессии по канону.

    Объём = Σ(weight × reps) по выполненным подходам, распределённый по
    мышечным весам (primary=1.0, secondary=0.5). Возвращает регионы + totals +
    imbalance (зона > 1.75× медианы ненулевых).
    """
    regions = {m: {"volume_kg": 0.0, "working_sets": 0, "sessions": set()} for m in MUSCLE_CANON}
    for session in sessions:
        sid = session.get("id")
        for exercise in session.get("exercises") or []:
            if exercise.get("status") != "done":
                continue
            ex_def = None
            if exercise.get("exercise_id"):
                ex_def = ex_by_id.get(exercise["exercise_id"])
            if not ex_def and exercise.get("exercise_slug"):
                ex_def = ex_by_slug.get(exercise["exercise_slug"])
            if not ex_def:
                continue
            weights = normalize_muscle_weights(
                ex_def.get("muscle_groups") or [],
                ex_def.get("secondary_groups") or [],
            )
            if not weights:
                continue
            volume = 0.0
            working_sets = 0
            for lg in exercise.get("set_logs") or []:
                if not lg.get("done"):
                    continue
                volume += (lg.get("weight") or 0) * (lg.get("reps") or 0)
                working_sets += 1
            # legacy-сессии без set_logs: берём тоннаж упражнения как объём
            if working_sets == 0:
                volume = float(exercise.get("tonnage") or 0)
                working_sets = len(exercise.get("sets_scheme") or [])
            if volume <= 0 and working_sets <= 0:
                continue
            for canon, w in weights.items():
                r = regions.setdefault(canon, {"volume_kg": 0.0, "working_sets": 0, "sessions": set()})
                r["volume_kg"] += volume * w
                r["working_sets"] += int(round(working_sets * w))
                if sid:
                    r["sessions"].add(sid)

    max_volume = max((r["volume_kg"] for r in regions.values()), default=0.0)
    out_regions = {}
    for m in MUSCLE_CANON:
        r = regions.get(m) or {"volume_kg": 0.0, "working_sets": 0, "sessions": set()}
        vol = round(r["volume_kg"])
        out_regions[m] = {
            "volume_kg": vol,
            "working_sets": r["working_sets"],
            "sessions": len(r["sessions"]),
            "intensity_0_1": round(r["volume_kg"] / max_volume, 3) if max_volume > 0 else 0.0,
        }

    nonzero = sorted(v["volume_kg"] for v in out_regions.values() if v["volume_kg"] > 0)
    imbalance = []
    if nonzero:
        median = nonzero[len(nonzero) // 2]
        if median > 0:
            imbalance = [m for m, v in out_regions.items() if v["volume_kg"] > 1.75 * median]

    return {
        "regions": out_regions,
        "totals": {
            "volume": round(sum(v["volume_kg"] for v in out_regions.values())),
            "sets": sum(v["working_sets"] for v in out_regions.values()),
            "sessions": len({sid for r in regions.values() for sid in r["sessions"]}),
        },
        "imbalance": imbalance,
    }


def _muscle_map_range(period: str, start: Optional[str], end: Optional[str]):
    today = datetime.now(timezone.utc).date()
    if period == "custom" and (start or end):
        return _parse_date(start) if start else None, (_parse_date(end) if end else today)
    if period == "month":
        return today - timedelta(days=30), today
    if period == "all":
        return None, today
    return today - timedelta(days=7), today  # week (по умолчанию)


async def _athlete_muscle_map(tg: int, period: str, start: Optional[str], end: Optional[str]) -> dict:
    frm, to = _muscle_map_range(period, start, end)
    sessions = await _finished_sessions(tg, None, frm.isoformat() if frm else None,
                                        to.isoformat() if to else None)
    catalog = await db.exercises.find(
        {"$or": [{"is_builtin": True}, {"owner_telegram_id": tg}]},
        {"_id": 0, "id": 1, "slug": 1, "muscle_groups": 1, "secondary_groups": 1},
    ).to_list(2000)
    ex_by_id = {ex["id"]: ex for ex in catalog if ex.get("id")}
    ex_by_slug = {ex["slug"]: ex for ex in catalog if ex.get("slug")}
    agg = _build_muscle_map(sessions, ex_by_id, ex_by_slug)
    return {
        "period": period,
        "start": frm.isoformat() if frm else None,
        "end": to.isoformat() if to else None,
        "views": MUSCLE_VIEWS,
        **agg,
    }


@api_router.get("/stats/{telegram_id}/muscle-map")
async def stats_muscle_map(telegram_id: int, period: str = "week",
                           start: Optional[str] = None, end: Optional[str] = None,
                           current: dict = Depends(get_current_user)):
    """Карта мышц 2D: объём и рабочие подходы по каноническим зонам за период."""
    await _assert_can_read_stats(current, telegram_id)
    if period not in ("week", "month", "all", "custom"):
        raise HTTPException(status_code=400, detail="period должен быть week, month, all или custom")
    return await _athlete_muscle_map(telegram_id, period, start, end)


@api_router.get("/coach/{coach_id}/clients/{athlete_id}/muscle-map")
async def coach_client_muscle_map(coach_id: int, athlete_id: int, period: str = "week",
                                  start: Optional[str] = None, end: Optional[str] = None,
                                  current: dict = Depends(get_current_user)):
    """Карта мышц подопечного для тренера (guard _assert_coach_of)."""
    if current["telegram_id"] != coach_id:
        raise HTTPException(status_code=403, detail="Доступ от имени другого тренера запрещён")
    await _assert_coach_of(coach_id, athlete_id)
    if period not in ("week", "month", "all", "custom"):
        raise HTTPException(status_code=400, detail="period должен быть week, month, all или custom")
    return await _athlete_muscle_map(athlete_id, period, start, end)


# ===========================================================================
# Фаза 3 — Кардио-модуль (planTrainWBrain.md §6.3)
# ===========================================================================

# MET (метаболический эквивалент) по типу активности и интенсивности.
# Источник — Compendium of Physical Activities (округлённые значения).
CARDIO_MET = {
    "walk":       {"low": 2.8, "moderate": 3.8, "high": 5.0},
    "treadmill":  {"low": 5.0, "moderate": 8.0, "high": 11.0},
    "bike":       {"low": 4.0, "moderate": 7.0, "high": 10.0},
    "rower":      {"low": 4.8, "moderate": 7.0, "high": 10.0},
    "elliptical": {"low": 4.6, "moderate": 7.0, "high": 9.0},
    "other":      {"low": 4.0, "moderate": 6.0, "high": 8.0},
}
CARDIO_TYPE_LABELS = {
    "walk": "Ходьба", "treadmill": "Дорожка", "bike": "Велотренажёр",
    "rower": "Гребля", "elliptical": "Эллипс", "other": "Другое",
}
DEFAULT_ATHLETE_WEIGHT_KG = 75.0

# Поля кардио, которые можно явно очистить, передав null (PATCH).
CARDIO_NULLABLE = (
    "distance_km", "avg_hr", "max_hr", "calories", "rpe",
    "incline_percent", "avg_speed_kmh", "avg_pace", "notes", "photo_ref",
)


def cardio_met(ctype: str, intensity: Optional[str]) -> float:
    """MET для типа кардио и интенсивности (fallback — moderate)."""
    table = CARDIO_MET.get((ctype or "other").lower()) or CARDIO_MET["other"]
    key = (intensity or "moderate").lower()
    return float(table.get(key, table["moderate"]))


def cardio_kcal(ctype: str, intensity: Optional[str], weight_kg: Optional[float],
                duration_sec: Optional[int], met: Optional[float] = None) -> int:
    """Калории по MET-формуле: kcal = MET × 3.5 × kg / 200 × min.

    Чистая функция (без БД) — покрыта offline unit-тестами.
    """
    try:
        minutes = max(0.0, float(duration_sec or 0) / 60.0)
    except (TypeError, ValueError):
        minutes = 0.0
    if minutes <= 0:
        return 0
    kg = float(weight_kg) if weight_kg else DEFAULT_ATHLETE_WEIGHT_KG
    if kg <= 0:
        kg = DEFAULT_ATHLETE_WEIGHT_KG
    m = float(met) if met else cardio_met(ctype, intensity)
    return int(round(m * 3.5 * kg / 200.0 * minutes))


def _parse_hhmmss_pace(distance_km: Optional[float], duration_sec: Optional[int]) -> Optional[str]:
    """Темп мин/км в формате MM:SS (для дорожки/ходьбы)."""
    try:
        d = float(distance_km or 0)
        s = float(duration_sec or 0)
    except (TypeError, ValueError):
        return None
    if d <= 0 or s <= 0:
        return None
    pace_sec = s / d
    return f"{int(pace_sec // 60):02d}:{int(round(pace_sec % 60)):02d}"


def _avg_speed_kmh(distance_km: Optional[float],
                   duration_sec: Optional[int]) -> Optional[float]:
    """Средняя скорость км/ч из дистанции и времени. None — если данных нет."""
    try:
        d = float(distance_km or 0)
        s = float(duration_sec or 0)
    except (TypeError, ValueError):
        return None
    if d <= 0 or s <= 0:
        return None
    return round(d / (s / 3600.0), 2)


def _clean_cardio_payload(payload: dict, *, partial: bool = False) -> dict:
    """Валидация и нормализация полей кардио. Чистая функция.

    partial=True — PATCH: проверяем только переданные поля.
    Бросает HTTPException(400) при некорректных значениях.
    """
    out = {}
    p = payload or {}

    if "type" in p and p.get("type") is not None:
        t = str(p["type"]).strip().lower()
        if t not in CARDIO_TYPES:
            raise HTTPException(status_code=400,
                                detail="type должен быть " + ", ".join(CARDIO_TYPES))
        out["type"] = t

    if "date" in p and p.get("date") is not None:
        d = _parse_date(p["date"])
        if not d:
            raise HTTPException(status_code=400, detail="Некорректная дата (ожидается YYYY-MM-DD)")
        out["date"] = d.isoformat()

    # Длительность: duration_sec или duration_min
    dur = p.get("duration_sec")
    if dur is None and p.get("duration_min") is not None:
        try:
            dur = int(round(float(p["duration_min"]) * 60))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Некорректная длительность")
    if dur is not None:
        try:
            dur = int(dur)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Некорректная длительность")
        if dur <= 0:
            raise HTTPException(status_code=400, detail="Длительность должна быть больше 0")
        if dur > 12 * 3600:
            raise HTTPException(status_code=400, detail="Длительность слишком большая (макс 12 ч)")
        out["duration_sec"] = dur

    if "distance_km" in p and p.get("distance_km") is not None:
        try:
            dist = float(p["distance_km"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Некорректная дистанция")
        if not math.isfinite(dist) or dist < 0 or dist > 500:
            raise HTTPException(status_code=400, detail="Дистанция должна быть от 0 до 500 км")
        out["distance_km"] = round(dist, 3)

    for key, lo, hi, label in (("avg_hr", 30, 230, "Средний пульс"),
                               ("max_hr", 30, 230, "Максимальный пульс")):
        if key in p and p.get(key) is not None:
            try:
                v = int(p[key])
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"Некорректный {label.lower()}")
            if v < lo or v > hi:
                raise HTTPException(status_code=400,
                                    detail=f"{label} должен быть от {lo} до {hi}")
            out[key] = v

    if "calories" in p and p.get("calories") is not None:
        try:
            cal = int(p["calories"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Некорректные калории")
        if cal < 0 or cal > 20000:
            raise HTTPException(status_code=400, detail="Калории должны быть от 0 до 20000")
        out["calories"] = cal

    if "intensity" in p and p.get("intensity") is not None:
        it = str(p["intensity"]).strip().lower()
        if it not in CARDIO_INTENSITIES:
            raise HTTPException(status_code=400, detail="intensity должен быть low, moderate или high")
        out["intensity"] = it

    if "rpe" in p and p.get("rpe") is not None:
        try:
            rpe = float(p["rpe"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Некорректный RPE")
        if not math.isfinite(rpe) or rpe < 1 or rpe > 10:
            raise HTTPException(status_code=400, detail="RPE должен быть от 1 до 10")
        out["rpe"] = round(rpe, 1)

    if "incline_percent" in p and p.get("incline_percent") is not None:
        try:
            inc = float(p["incline_percent"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Некорректный наклон")
        if not math.isfinite(inc) or inc < 0 or inc > 40:
            raise HTTPException(status_code=400, detail="Наклон должен быть от 0 до 40%")
        out["incline_percent"] = round(inc, 1)

    if "avg_speed_kmh" in p and p.get("avg_speed_kmh") is not None:
        try:
            sp = float(p["avg_speed_kmh"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Некорректная скорость")
        if not math.isfinite(sp) or sp < 0 or sp > 60:
            raise HTTPException(status_code=400, detail="Скорость должна быть от 0 до 60 км/ч")
        out["avg_speed_kmh"] = round(sp, 2)

    if "source" in p and p.get("source") is not None:
        s = str(p["source"]).strip().lower()
        if s not in CARDIO_SOURCES:
            raise HTTPException(status_code=400, detail="source должен быть manual или photo")
        out["source"] = s

    if "notes" in p:
        n = p.get("notes")
        out["notes"] = (str(n).strip()[:1000] or None) if n is not None else None

    if "photo_ref" in p:
        out["photo_ref"] = p.get("photo_ref") or None

    if "avg_pace" in p:
        out["avg_pace"] = (str(p["avg_pace"]).strip()[:10] or None) if p.get("avg_pace") else None

    # Явный null очищает необязательное поле (например, смена дорожки на вело
    # убирает наклон). Для POST такие ключи просто отсутствуют.
    for key in CARDIO_NULLABLE:
        if key in p and p.get(key) is None:
            out[key] = None

    if partial and not out:
        raise HTTPException(status_code=400, detail="Нет полей для обновления")
    return out


def _assert_can_log_permission(user: Optional[dict], athlete_tgid: int,
                               perm_key: str, detail: str) -> None:
    """Self-fill: сам атлет должен иметь право perm_key; тренер/админ проходят.

    Зеркалит _assert_can_selffill_strength для кардио/питания.
    """
    if (user or {}).get("telegram_id") != athlete_tgid:
        return
    caps = _get_capabilities(user)
    if caps["onboarded"] and not caps["permissions"].get(perm_key, False):
        raise HTTPException(status_code=403, detail=detail)


async def _athlete_weight_kg(tg: int) -> Optional[float]:
    """Последний известный вес атлета (для MET-расчёта). None — если неизвестен."""
    doc = await db.body_metrics.find_one(
        {"athlete_telegram_id": tg, "weight_kg": {"$ne": None}},
        {"_id": 0, "weight_kg": 1}, sort=[("date", -1)],
    )
    if doc and doc.get("weight_kg"):
        try:
            return float(doc["weight_kg"])
        except (TypeError, ValueError):
            return None
    return None


def _cardio_range(period: str, start: Optional[str], end: Optional[str]):
    """Диапазон дат для агрегата кардио. Возвращает (from_date|None, to_date)."""
    today = datetime.now(timezone.utc).date()
    if period == "custom" and (start or end):
        return _parse_date(start) if start else None, (_parse_date(end) or today)
    if period == "month":
        return today - timedelta(days=30), today
    if period == "all":
        return None, today
    return today - timedelta(days=7), today  # week (по умолчанию)


async def _cardio_weekly_target(tg: int) -> Optional[int]:
    """Недельная норма кардио (минуты) из целей. None — если не задана.

    Фаза 4 наполнит коллекцию `goals`; читаем защитно, чтобы модуль работал и без неё.
    """
    try:
        goal = await db.goals.find_one(
            {"athlete_telegram_id": tg, "type": "cardio_minutes",
             "period": "weekly", "status": "active"},
            {"_id": 0, "target": 1},
        )
    except Exception:
        return None
    if not goal or goal.get("target") is None:
        return None
    try:
        return int(round(float(goal["target"])))
    except (TypeError, ValueError):
        return None


async def _athlete_cardio_stats(tg: int, period: str, start: Optional[str],
                                end: Optional[str]) -> dict:
    """Агрегат кардио за период: минуты, сессии, км, ккал, разбивка по типам."""
    frm, to = _cardio_range(period, start, end)
    q = {"athlete_telegram_id": tg}
    if frm or to:
        rng = {}
        if frm:
            rng["$gte"] = frm.isoformat()
        if to:
            rng["$lte"] = to.isoformat()
        q["date"] = rng
    rows = await db.cardio_sessions.find(q, {"_id": 0}).sort("date", -1).to_list(2000)

    minutes = 0
    km = 0.0
    kcal = 0
    by_type = {}
    hr_sum = 0
    hr_n = 0
    for r in rows:
        mins = round((r.get("duration_sec") or 0) / 60)
        minutes += mins
        km += float(r.get("distance_km") or 0)
        kcal += int(r.get("calories") or 0)
        t = r.get("type") or "other"
        bt = by_type.setdefault(t, {"minutes": 0, "sessions": 0, "km": 0.0, "kcal": 0})
        bt["minutes"] += mins
        bt["sessions"] += 1
        bt["km"] = round(bt["km"] + float(r.get("distance_km") or 0), 3)
        bt["kcal"] += int(r.get("calories") or 0)
        if r.get("avg_hr"):
            hr_sum += int(r["avg_hr"])
            hr_n += 1

    # Недельная норма и выполнение считаются по ТЕКУЩЕЙ календарной неделе
    # (пн–вс), независимо от выбранного периода отображения.
    today = datetime.now(timezone.utc).date()
    week_from = today - timedelta(days=today.weekday())
    week_rows = await db.cardio_sessions.find(
        {"athlete_telegram_id": tg, "date": {"$gte": week_from.isoformat(),
                                             "$lte": today.isoformat()}},
        {"_id": 0, "duration_sec": 1},
    ).to_list(500)
    week_minutes = sum(round((r.get("duration_sec") or 0) / 60) for r in week_rows)
    target = await _cardio_weekly_target(tg)

    return {
        "period": period,
        "start": frm.isoformat() if frm else None,
        "end": to.isoformat() if to else None,
        "minutes": minutes,
        "sessions": len(rows),
        "km": round(km, 2),
        "kcal": kcal,
        "avg_hr": round(hr_sum / hr_n) if hr_n else None,
        "by_type": by_type,
        "weekly_minutes": week_minutes,
        "weekly_target": target,
        "compliance": (round(week_minutes / target, 3) if target else None),
        "type_labels": CARDIO_TYPE_LABELS,
    }


def _serialize_cardio(doc: dict) -> dict:
    out = dict(doc)
    out.pop("_id", None)
    if isinstance(out.get("created_at"), datetime):
        out["created_at"] = out["created_at"].isoformat()
    if isinstance(out.get("updated_at"), datetime):
        out["updated_at"] = out["updated_at"].isoformat()
    return out


@api_router.post("/cardio")
async def create_cardio(payload: CardioCreateReq, current: dict = Depends(get_current_user)):
    """Создать кардио-сессию. Атлет — себе (нужно permissions.log_cardio),
    тренер — подопечному (guard _assert_coach_of)."""
    athlete = payload.athlete_telegram_id or current["telegram_id"]
    coach_id = None
    if athlete != current["telegram_id"]:
        await _assert_coach_of(current["telegram_id"], athlete)
        coach_id = current["telegram_id"]
    else:
        _assert_can_log_permission(current, athlete, "log_cardio",
                                   "Заполнение кардио недоступно: обратитесь к администратору")

    fields = _clean_cardio_payload(payload.model_dump(exclude_none=True))
    fields.setdefault("date", datetime.now(timezone.utc).date().isoformat())
    fields.setdefault("type", "treadmill")
    fields.setdefault("intensity", "moderate")
    fields.setdefault("source", "manual")

    # Калории: если не переданы — считаем по MET (вес из профиля/запроса).
    if not fields.get("calories"):
        weight = payload.weight_kg or await _athlete_weight_kg(athlete)
        fields["calories"] = cardio_kcal(fields.get("type"), fields.get("intensity"),
                                         weight, fields.get("duration_sec"))
    if not fields.get("avg_pace"):
        fields["avg_pace"] = _parse_hhmmss_pace(fields.get("distance_km"),
                                                fields.get("duration_sec"))
    if not fields.get("avg_speed_kmh"):
        fields["avg_speed_kmh"] = _avg_speed_kmh(fields.get("distance_km"),
                                                 fields.get("duration_sec"))

    now_iso = datetime.now(timezone.utc).isoformat()
    doc = CardioSession(
        athlete_telegram_id=athlete,
        coach_telegram_id=coach_id,
        date=fields.get("date"),
        type=fields.get("type", "treadmill"),
        duration_sec=fields.get("duration_sec") or 0,
        distance_km=fields.get("distance_km"),
        avg_hr=fields.get("avg_hr"),
        max_hr=fields.get("max_hr"),
        calories=fields.get("calories"),
        intensity=fields.get("intensity"),
        rpe=fields.get("rpe"),
        incline_percent=fields.get("incline_percent"),
        avg_speed_kmh=fields.get("avg_speed_kmh"),
        avg_pace=fields.get("avg_pace"),
        notes=fields.get("notes"),
        photo_ref=fields.get("photo_ref"),
        source=fields.get("source", "manual"),
    )
    row = doc.model_dump()
    row["created_at"] = now_iso
    row["updated_at"] = now_iso
    await db.cardio_sessions.insert_one(row)
    return _serialize_cardio(row)


@api_router.get("/cardio")
async def list_cardio(athlete: Optional[int] = None,
                      frm: Optional[str] = Query(default=None, alias="from"),
                      to: Optional[str] = None,
                      limit: int = 100,
                      current: dict = Depends(get_current_user)):
    """Список кардио-сессий (владелец или его тренер)."""
    tg = athlete or current["telegram_id"]
    await _assert_can_read_stats(current, tg)
    limit = max(1, min(int(limit or 100), 500))
    q = {"athlete_telegram_id": tg}
    rng = {}
    d_from = _parse_date(frm)
    d_to = _parse_date(to)
    if d_from:
        rng["$gte"] = d_from.isoformat()
    if d_to:
        rng["$lte"] = d_to.isoformat()
    if rng:
        q["date"] = rng
    rows = await db.cardio_sessions.find(q, {"_id": 0}).sort([("date", -1), ("created_at", -1)]).to_list(limit)
    return {"items": [_serialize_cardio(r) for r in rows], "count": len(rows)}


async def _get_cardio_or_403(cardio_id: str, current: dict) -> dict:
    doc = await db.cardio_sessions.find_one({"id": cardio_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Кардио-сессия не найдена")
    await _assert_can_read_stats(current, doc.get("athlete_telegram_id"))
    return doc


@api_router.patch("/cardio/{cardio_id}")
async def update_cardio(cardio_id: str, payload: CardioCreateReq,
                        current: dict = Depends(get_current_user)):
    """Изменить кардио-сессию (владелец или тренер)."""
    doc = await _get_cardio_or_403(cardio_id, current)
    tg = doc.get("athlete_telegram_id")
    is_owner = current["telegram_id"] == tg
    if is_owner:
        _assert_can_log_permission(current, tg, "log_cardio",
                                   "Заполнение кардио недоступно: обратитесь к администратору")
    # exclude_unset: PATCH меняет ТОЛЬКО явно переданные поля — иначе дефолт
    # Pydantic (type="treadmill") молча перетирал бы данные при пустом запросе.
    # Без exclude_none: явный null очищает необязательное поле.
    fields = _clean_cardio_payload(
        payload.model_dump(exclude_unset=True), partial=True
    )
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Пересчёт производных полей, если поменяли дистанцию/время/тип и не задали
    # их явно. Берём итоговое состояние = сохранённый документ + патч.
    merged = dict(doc)
    merged.update(fields)
    if "avg_pace" not in fields:
        fields["avg_pace"] = _parse_hhmmss_pace(merged.get("distance_km"),
                                                merged.get("duration_sec"))
    if "avg_speed_kmh" not in fields:
        fields["avg_speed_kmh"] = _avg_speed_kmh(merged.get("distance_km"),
                                                 merged.get("duration_sec"))
    if "calories" not in fields and ("duration_sec" in fields or "intensity" in fields
                                     or "type" in fields):
        weight = await _athlete_weight_kg(tg)
        fields["calories"] = cardio_kcal(merged.get("type"), merged.get("intensity"),
                                         weight, merged.get("duration_sec"))

    if not is_owner:
        # тренерская правка помечается авторством
        fields["coach_telegram_id"] = current["telegram_id"]
    await db.cardio_sessions.update_one({"id": cardio_id}, {"$set": fields})
    updated = await db.cardio_sessions.find_one({"id": cardio_id}, {"_id": 0})
    return _serialize_cardio(updated)


@api_router.delete("/cardio/{cardio_id}")
async def delete_cardio(cardio_id: str, current: dict = Depends(get_current_user)):
    """Удалить кардио-сессию (владелец или тренер)."""
    doc = await _get_cardio_or_403(cardio_id, current)
    if current["telegram_id"] == doc.get("athlete_telegram_id"):
        _assert_can_log_permission(current, doc.get("athlete_telegram_id"), "log_cardio",
                                   "Заполнение кардио недоступно: обратитесь к администратору")
    await db.cardio_sessions.delete_one({"id": cardio_id})
    return {"ok": True, "id": cardio_id}


_CARDIO_VISION_PROMPT = """Ты разбираешь фотографию консоли кардиотренажёра (дорожка, велотренажёр, эллипс, гребной).
Верни ТОЛЬКО JSON без пояснений по схеме:
{"type": "treadmill|bike|rower|walk|elliptical|other",
 "duration_sec": число секунд или null,
 "distance_km": число км или null,
 "avg_hr": средний пульс целым числом или null,
 "max_hr": максимальный пульс целым числом или null,
 "calories": калории целым числом или null,
 "incline_percent": наклон в % или null,
 "avg_speed_kmh": средняя скорость км/ч или null}
Правила: время переводи в секунды (30:00 → 1800). Если поле не видно — null. Не выдумывай значения."""


@api_router.post("/cardio/parse-photo")
async def cardio_parse_photo(file: UploadFile = File(...),
                             current: dict = Depends(get_current_user)):
    """Фото консоли → черновик кардио (vision). Черновик не сохраняется —
    пользователь подтверждает и правит, затем POST /cardio."""
    _rate_limit(f"cardio-photo:{current['telegram_id']}", 20, 600,
                "Слишком много разборов фото. Попробуйте позже.")
    _assert_can_log_permission(current, current["telegram_id"], "log_cardio",
                               "Заполнение кардио недоступно: обратитесь к администратору")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Фото слишком большое (макс 8 МБ)")
    mime = (file.content_type or "").lower()
    if not mime.startswith("image/"):
        fn = (file.filename or "").lower()
        if fn.endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        elif fn.endswith(".png"):
            mime = "image/png"
        elif fn.endswith(".webp"):
            mime = "image/webp"
        elif fn.endswith(".heic"):
            mime = "image/heic"
        else:
            raise HTTPException(status_code=400, detail="Поддерживаются только изображения (jpg/png/webp/heic)")

    import base64
    images = [{"mime": mime, "data_b64": base64.b64encode(raw).decode("ascii")}]
    text = await _ai_chat_vision(_CARDIO_VISION_PROMPT, images)
    data = _extract_json(text)

    draft = {}
    for key in ("type", "duration_sec", "distance_km", "avg_hr", "max_hr",
                "calories", "incline_percent", "avg_speed_kmh"):
        if data.get(key) is not None:
            draft[key] = data[key]
    # Нормализуем через общий валидатор; некорректные поля ИИ отбрасываем,
    # а не роняем запрос целиком.
    clean = {}
    for key, val in draft.items():
        try:
            clean.update(_clean_cardio_payload({key: val}))
        except HTTPException:
            continue
    if clean.get("duration_sec") and not clean.get("calories"):
        weight = await _athlete_weight_kg(current["telegram_id"])
        clean["calories"] = cardio_kcal(clean.get("type"), clean.get("intensity"),
                                        weight, clean.get("duration_sec"))
    if not clean.get("avg_pace"):
        clean["avg_pace"] = _parse_hhmmss_pace(clean.get("distance_km"),
                                               clean.get("duration_sec"))
    clean["source"] = "photo"
    return {"draft": clean, "confidence": "vision" if clean else "low"}


@api_router.get("/stats/{telegram_id}/cardio")
async def stats_cardio(telegram_id: int, period: str = "week",
                       start: Optional[str] = None, end: Optional[str] = None,
                       current: dict = Depends(get_current_user)):
    """Агрегат кардио за период: минуты, сессии, км, ккал, разбивка по типам,
    недельная норма и её выполнение."""
    await _assert_can_read_stats(current, telegram_id)
    if period not in ("week", "month", "all", "custom"):
        raise HTTPException(status_code=400, detail="period должен быть week, month, all или custom")
    return await _athlete_cardio_stats(telegram_id, period, start, end)


# ---- P7: данные для экрана тренировочной серии (streak) ----
async def _athlete_streak_data(tg, weeks=12):
    sessions = await db.workout_sessions.find(
        {"athlete_telegram_id": tg, "status": "finished"},
        {"_id": 0, "finished_at": 1, "date": 1, "exercises": 1},
    ).to_list(3000)
    day_counts = {}
    total_sessions = 0
    for s in sessions:
        if not any(e.get("status") == "done" for e in (s.get("exercises") or [])):
            continue
        total_sessions += 1
        d = _session_day(s)
        if d:
            day_counts[d] = day_counts.get(d, 0) + 1
    dates = set(day_counts)

    today = datetime.now(timezone.utc).date()
    # текущая серия (подряд идущие дни до сегодня/вчера)
    cur = 0
    c = today if today in dates else (today - timedelta(days=1))
    while c in dates:
        cur += 1
        c -= timedelta(days=1)
    # все серии (подряд идущие дни) + рекорд
    runs = []
    for d in sorted(dates):
        if (d - timedelta(days=1)) not in dates:
            end = d
            while (end + timedelta(days=1)) in dates:
                end += timedelta(days=1)
            runs.append({"start": d, "end": end, "length": (end - d).days + 1})
    best = max((r["length"] for r in runs), default=0)

    # карта: день -> его серия (для аннотации календарной сетки)
    run_by_day = {}
    for r in runs:
        d = r["start"]
        while d <= r["end"]:
            run_by_day[d] = r
            d += timedelta(days=1)

    # список серий (>= 2 дней) для UI: свежие первыми, рекорд помечен
    streaks = []
    for r in sorted(runs, key=lambda x: x["start"], reverse=True):
        if r["length"] < 2:
            continue
        streaks.append({
            "start": r["start"].isoformat(),
            "end": r["end"].isoformat(),
            "length": r["length"],
            "is_current": cur > 0 and r["end"] >= today - timedelta(days=1),
            "is_best": False,
        })
    streaks = streaks[:50]
    if streaks:
        longest = max(streaks, key=lambda x: x["length"])
        longest["is_best"] = True

    # доп. метрики: тренировок в этом месяце, среднее в неделю, первая тренировка
    this_month = sum(n for d, n in day_counts.items()
                     if d.year == today.year and d.month == today.month)
    first_day = min(dates) if dates else None
    avg_per_week = 0.0
    if first_day:
        weeks_elapsed = max(1, (today - first_day).days // 7 + 1)
        avg_per_week = round(total_sessions / weeks_elapsed, 1)

    plan = await db.plans.find_one(
        {"athlete_telegram_id": tg, "status": "active"}, {"_id": 0, "training_days": 1}
    )
    weekly_goal = len((plan or {}).get("training_days") or [])

    monday = today - timedelta(days=today.weekday())
    trained_this_week = sum(1 for i in range(7) if (monday + timedelta(days=i)) in dates)

    weeks = max(1, min(int(weeks or 12), 26))
    grid = []
    cur_m = monday - timedelta(weeks=weeks - 1)
    while cur_m <= monday:
        days = []
        for i in range(7):
            dd = cur_m + timedelta(days=i)
            r = run_by_day.get(dd)
            days.append({
                "date": dd.isoformat(),
                "weekday": i + 1,            # 1=Пн .. 7=Вс
                "trained": dd in dates,
                "count": day_counts.get(dd, 0),
                "is_today": dd == today,
                "is_future": dd > today,
                "streak_len": (r or {}).get("length", 0),
                "streak_start": bool(r and dd == r["start"]),
                "streak_end": bool(r and dd == r["end"]),
            })
        grid.append({"week_start": cur_m.isoformat(), "days": days})
        cur_m += timedelta(weeks=1)

    return {
        "telegram_id": tg,
        "current_streak": cur,
        "best_streak": best,
        "total_workouts": total_sessions,
        "active_days": len(dates),
        "weekly_goal": weekly_goal,
        "trained_this_week": trained_this_week,
        "week": grid[-1] if grid else {"days": []},
        "calendar": grid,
        "streaks": streaks,
        "this_month": this_month,
        "avg_per_week": avg_per_week,
        "first_workout_date": first_day.isoformat() if first_day else None,
    }


@api_router.get("/stats/{telegram_id}/streak")
async def stats_streak(telegram_id: int, weeks: int = 12,
                       current: dict = Depends(get_current_user)):
    await _assert_can_read_stats(current, telegram_id)
    return await _athlete_streak_data(telegram_id, weeks)


@api_router.get("/coach/{coach_id}/clients/{athlete_id}/stats")
async def coach_client_stats(coach_id: int, athlete_id: int,
                             from_: Optional[str] = Query(default=None, alias="from"),
                             to: Optional[str] = None, plan_id: Optional[str] = None,
                             current: dict = Depends(get_current_user)):
    if current.get("telegram_id") != coach_id:
        raise HTTPException(status_code=403, detail="Доступ от имени другого тренера запрещён")
    await _assert_coach_of(coach_id, athlete_id)
    return await _athlete_detailed_stats(athlete_id, from_, to, plan_id)


@api_router.get("/coach/{coach_id}/clients/{athlete_id}/exercise-progress")
async def coach_client_exercise_progress(coach_id: int, athlete_id: int,
                                         slug: Optional[str] = None,
                                         plan_id: Optional[str] = None,
                                         current: dict = Depends(get_current_user)):
    if current.get("telegram_id") != coach_id:
        raise HTTPException(status_code=403, detail="Доступ от имени другого тренера запрещён")
    await _assert_coach_of(coach_id, athlete_id)
    return await _athlete_exercise_progress(athlete_id, slug, plan_id)


@api_router.get("/coach/{coach_id}/clients/{athlete_id}/muscle-groups")
async def coach_client_muscle_groups(coach_id: int, athlete_id: int, period: str = "week",
                                     current: dict = Depends(get_current_user)):
    """Статистика по мышечным группам подопечного."""
    if current.get("telegram_id") != coach_id:
        raise HTTPException(status_code=403, detail="Доступ от имени другого тренера запрещён")
    await _assert_coach_of(coach_id, athlete_id)
    
    # Используем ту же логику, что и для спортсмена
    today = datetime.now(timezone.utc).date()
    if period == "week":
        start_date = today - timedelta(days=7)
    elif period == "month":
        start_date = today - timedelta(days=30)
    else:
        start_date = None
    
    end_date = today
    
    query = {"athlete_telegram_id": athlete_id, "status": "finished"}
    if start_date:
        query["date"] = {"$gte": start_date.isoformat()}
    
    sessions = await db.workout_sessions.find(query, {"_id": 0}).to_list(3000)
    
    exercises_catalog = await db.exercises.find(
        {"$or": [{"is_builtin": True}, {"owner_telegram_id": athlete_id}]},
        {"_id": 0, "id": 1, "slug": 1, "muscle_groups": 1, "secondary_groups": 1}
    ).to_list(1000)
    
    ex_by_id = {ex["id"]: ex for ex in exercises_catalog if ex.get("id")}
    ex_by_slug = {ex["slug"]: ex for ex in exercises_catalog if ex.get("slug")}
    
    muscle_stats = {}
    
    for session in sessions:
        for exercise in session.get("exercises", []):
            if exercise.get("status") != "done":
                continue
            
            ex_def = None
            if exercise.get("exercise_id"):
                ex_def = ex_by_id.get(exercise["exercise_id"])
            elif exercise.get("exercise_slug"):
                ex_def = ex_by_slug.get(exercise["exercise_slug"])
            
            if not ex_def:
                continue
            
            primary_groups = ex_def.get("muscle_groups", [])
            secondary_groups = ex_def.get("secondary_groups", [])
            
            volume = 0
            for set_log in exercise.get("set_logs", []):
                if set_log.get("done"):
                    weight = set_log.get("weight", 0) or 0
                    reps = set_log.get("reps", 0) or 0
                    volume += weight * reps
            
            for mg in primary_groups:
                if mg not in muscle_stats:
                    muscle_stats[mg] = {"volume": 0, "sessions": set()}
                muscle_stats[mg]["volume"] += volume
                muscle_stats[mg]["sessions"].add(session.get("id"))
            
            for mg in secondary_groups:
                if mg not in muscle_stats:
                    muscle_stats[mg] = {"volume": 0, "sessions": set()}
                muscle_stats[mg]["volume"] += volume * 0.5
                muscle_stats[mg]["sessions"].add(session.get("id"))
    
    muscle_groups = {}
    for mg, stats in muscle_stats.items():
        muscle_groups[mg] = {
            "volume": round(stats["volume"]),
            "sessions": len(stats["sessions"])
        }
    
    return {
        "period": period,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat(),
        "muscle_groups": muscle_groups
    }


# ===========================================================================
# P6 — ИИ-анализ программ (двухмодельная архитектура)
# - Текст/reasoning: DeepSeek V4 Flash через RouterAI (AI_BASE_URL/API_KEY/MODEL)
# - Vision (фото): Google Gemini через OpenAI-совместимый эндпоинт
#   (AI_VISION_BASE_URL/API_KEY/MODEL)
# ===========================================================================
def _ai_config():
    """Текстовый провайдер (DeepSeek / RouterAI) — генерация, refine, parse."""
    return {
        "base_url": (os.environ.get("AI_BASE_URL") or "").rstrip("/"),
        "api_key": os.environ.get("AI_API_KEY") or "",
        "model": os.environ.get("AI_MODEL") or "deepseek/deepseek-v4-flash",
    }


def _ai_vision_config():
    """Vision-провайдер (Google Gemini) — разбор фото в текст."""
    return {
        "base_url": (os.environ.get("AI_VISION_BASE_URL") or "").rstrip("/"),
        "api_key": os.environ.get("AI_VISION_API_KEY") or "",
        "model": os.environ.get("AI_VISION_MODEL") or "gemini-flash-latest",
    }


@api_router.get("/ai/status")
async def ai_status(current: dict = Depends(get_current_user)):
    cfg = _ai_config()
    vcfg = _ai_vision_config()
    return {
        "enabled": bool(cfg["base_url"] and cfg["api_key"]),
        "model": cfg["model"],
        "vision_enabled": bool(vcfg["base_url"] and vcfg["api_key"]),
        "vision_model": vcfg["model"],
    }


async def _ai_chat(messages, temperature=0.3, json_mode=True):
    cfg = _ai_config()
    if not (cfg["base_url"] and cfg["api_key"]):
        raise HTTPException(status_code=503,
                            detail="ИИ-анализ пока не настроен: не задан API-ключ сервиса")
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    body = {
        "model": cfg["model"], "messages": messages, "temperature": temperature,
        "max_tokens": 32000, "stream": False,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    url = f"{cfg['base_url']}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(url, json=body, headers=headers)
            if r.status_code == 400:
                # часть провайдеров не поддерживает response_format — повтор без него
                body.pop("response_format", None)
                r = await c.post(url, json=body, headers=headers)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"ИИ-сервис недоступен: {e.__class__.__name__}")
    if r.status_code >= 400:
        try:
            msg = (r.json().get("error") or {}).get("message") or r.text
        except Exception:
            msg = r.text
        raise HTTPException(status_code=502, detail=f"Ошибка ИИ-сервиса ({r.status_code}): {str(msg)[:200]}")
    try:
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Failed to parse AI response: {e}")
        raise HTTPException(status_code=502, detail="Некорректный ответ ИИ-сервиса")


async def _ai_chat_vision(prompt_text, images):
    """Отправляет промпт + список изображений в Gemini (OpenAI-совместимый vision).
    images: list[{"mime": "image/jpeg", "data_b64": "..."}].
    Возвращает текст-описание программы (для последующей передачи в _ai_chat)."""
    cfg = _ai_vision_config()
    if not (cfg["base_url"] and cfg["api_key"]):
        raise HTTPException(status_code=503,
                            detail="Разбор по фото недоступен: не задан ключ Gemini")
    content = [{"type": "text", "text": prompt_text}]
    for img in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{img['mime']};base64,{img['data_b64']}"},
        })
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    body = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
        "max_tokens": 8000,
        "stream": False,
    }
    url = f"{cfg['base_url']}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(url, json=body, headers=headers)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Vision-сервис недоступен: {e.__class__.__name__}")
    if r.status_code >= 400:
        try:
            msg = (r.json().get("error") or {}).get("message") or r.text
        except Exception:
            msg = r.text
        raise HTTPException(status_code=502, detail=f"Ошибка Vision-сервиса ({r.status_code}): {str(msg)[:200]}")
    try:
        return r.json()["choices"][0]["message"]["content"] or ""
    except Exception:
        raise HTTPException(status_code=502, detail="Некорректный ответ Vision-сервиса")


def _extract_json(text):
    s = (text or "").strip()
    s = re.sub(r"```(?:json)?", "", s).strip()
    start = s.find("{")
    if start == -1:
        raise HTTPException(status_code=422, detail="ИИ вернул некорректный формат — попробуйте ещё раз")
    end = s.rfind("}")
    candidate = s[start:end + 1] if end > start else s[start:]
    try:
        return json.loads(candidate)
    except Exception:
        pass
    try:
        # json_repair чинит обрезанный JSON, висячие запятые, одинарные кавычки и т.п.
        data = json_repair.loads(candidate)
        if isinstance(data, dict) and data:
            return data
    except Exception:
        pass
    logger.warning(f"AI JSON parse failed, raw head: {s[:500]!r}")
    raise HTTPException(status_code=422, detail="ИИ вернул некорректный JSON — попробуйте ещё раз")


_AI_SCHEMA = """{
 "name": "название программы (строка)",
 "description": "краткое описание (строка)",
 "level": "beginner|intermediate|advanced",
 "goal": "strength|hypertrophy|powerlifting|general",
 "weeks": [{
   "week_index": 1,
   "days": [{
     "day_index": 1,
     "title": "название дня, например 'День 1 · Присед'",
     "exercises": [{
       "name": "название упражнения (строка, по-русски)",
       "muscle_group": "legs|chest|back|shoulders|biceps|triceps|core",
       "lift_group": "squat|bench|deadlift или null",
       "is_accessory": false,
       "rest_seconds": 120,
       "sets": [{"weight": 100.0, "percent_1rm": null, "sets": 3, "reps": 5}]
     }]
   }]
 }]
}"""

_AI_SYSTEM = (
    "Ты — опытный тренер по силовым видам спорта и парсер тренировочных программ. "
    "Отвечай ТОЛЬКО валидным JSON без пояснений и markdown, строго по схеме:\n"
    + _AI_SCHEMA +
    "\nПравила:\n"
    "- week_index и day_index начинаются с 1; day_index — день недели 1..7.\n"
    "- Дни отдыха НЕ включай в структуру.\n"
    "- В 'sets' каждая запись — группа подходов: sets (кол-во подходов) × reps (повторы).\n"
    "- Если вес задан процентом от 1ПМ — заполни percent_1rm числом (например 75), а weight оставь null. "
    "percent_1rm используй только для базовых движений с lift_group (squat/bench/deadlift).\n"
    "- Если вес известен в кг — заполни weight, percent_1rm оставь null.\n"
    "- Если вес неизвестен (собственный вес, разминка) — weight и percent_1rm null.\n"
    "- is_accessory=true только для подсобки без веса (планка, гиперэкстензия без веса и т.п.).\n"
    "- lift_group: 'squat' для приседов, 'bench' для жимов лёжа, 'deadlift' для становых тяг; иначе null.\n"
    "- Название программы, её описание, названия упражнений и дней — на русском языке.\n"
    "- Выводи максимально КОМПАКТНЫЙ JSON: без лишних пробелов и переносов строк."
)

_AI_SYSTEM_GEN = _AI_SYSTEM + (
    "\n\nТы составляешь программу С НУЛЯ как элитный тренер с 15-летним опытом "
    "(пауэрлифтинг, гипертрофия, ОФП). Строй программу СТРОГО на научно доказанных принципах "
    "(мета-анализы Schoenfeld и др., методики Wendler 5/3/1, RIR-автогуляция):\n"
    "НАУЧНЫЕ ПРИНЦИПЫ (обязательны):\n"
    "- Недельный объём: 10–20 рабочих подходов на каждую целевую мышечную группу "
    "(оптимум 12–16; новичкам 8–12; продвинутым допустимо до 25, но только при 3+ тренировках этой мышцы в неделю).\n"
    "- За одну тренировку — не более 6–8 тяжёлых подходов на одну мышечную группу "
    "(дальше отдача резко падает); лишний объём переноси на другой день.\n"
    "- Частота: каждую целевую мышечную группу тренируй 2 раза в неделю или чаще — "
    "это эффективнее, чем весь объём за один день («бро-сплит» неэффективен).\n"
    "- Близость к отказу: для гипертрофии изоляцию и подсобку доводи почти до отказа (0–2 повтора в запасе); "
    "тяжёлые базовые (присед, становая, жим) НИКОГДА не до отказа — оставляй 2–4 повтора в запасе.\n"
    "- Прогрессивная перегрузка ОБЯЗАТЕЛЬНА: недели не должны быть копиями друг друга — "
    "меняй И проценты, И количество подходов/повторов от недели к неделе.\n"
    "- Разгрузочная неделя (deload): в программах от 4 недель каждая 4-я неделя — разгрузка "
    "(40–60% от 1ПМ, объём вдвое меньше) для суперкомпенсации и профилактики перетренированности.\n"
    "- Диапазоны повторов по цели: сила 3–6 (75–90% 1ПМ), гипертрофия 6–15 (60–80% 1ПМ), "
    "выносливость/ОФП 12–20. Смешанные цели — тяжёлая база 3–6 + подсобка 8–15.\n"
    "- Отдых: базовые многосуставные 150–240 сек (полное восстановление важно для качества подходов), "
    "изоляция и подсобка 60–120 сек.\n"
    "ОБЪЁМ ДНЯ (самое важное):\n"
    "- Каждый тренировочный день содержит 5–8 упражнений. День из 2–4 упражнений — ГРУБАЯ ОШИБКА "
    "(допустимо только если пользователь ЯВНО попросил короткие/минимальные тренировки).\n"
    "- Порядок в дне: сначала 1–2 базовых многосуставных движения (самые тяжёлые — первыми, пока нет утомления), "
    "затем 3–6 подсобных/изолирующих.\n"
    "ПОДБОР УПРАЖНЕНИЙ:\n"
    "- Покрывай все мышечные группы согласно цели и сплиту: ноги, грудь, спина, плечи, руки, кор.\n"
    "- Используй общепринятые русские названия: «Приседания со штангой», «Жим лёжа», «Становая тяга», "
    "«Тяга штанги в наклоне», «Подтягивания», «Жим гантелей сидя», «Румынская тяга», «Выпады с гантелями», "
    "«Тяга верхнего блока», «Французский жим», «Сгибания рук со штангой», «Разводка гантелей», "
    "«Гиперэкстензия», «Планка» и т.п.\n"
    "- Не повторяй одно упражнение дважды в один день; между днями вариативность приветствуется.\n"
    "НАГРУЗКА И ВАРИАЦИЯ ПОДХОДОВ/ПОВТОРОВ (критично):\n"
    "- **Меняй `sets` и `reps` между неделями, а не только `percent_1rm`!** Это принципиальное правило — "
    "иначе программа выглядит однообразной и не даёт стимула. \n"
    "- Базовые движения (lift_group) задавай через percent_1rm: сила 70–95%, гипертрофия 60–80%, разгрузка 40–60%. "
    "Используй МНОЖЕСТВО подходов: 3×5, 4×3, 5×5, 3×8 и т.д. — не по одному подходу.\n"
    "- Подсобка/изоляция: weight и percent_1rm null, но **`sets` и `reps` тоже прогрессируй**: "
    "нед.1: 3×12 → нед.2: 3×10 → нед.3: 4×8 → нед.4 (deload): 2×15.\n"
    "- is_accessory=true ставь ТОЛЬКО для строго bodyweight-упражнений без внешнего веса: планка, «Подъём ног в висе», "
    "«Отжимания на брусьях» без пояса, «Подтягивания» без пояса, «Гиперэкстензия» без веса. Для гантельных/штанговых "
    "упражнений (Жим гантелей, Румынская тяга, Тяга блока, Разводка, Выпады, Жим ногами и т.д.) is_accessory=false — "
    "это НЕ bodyweight, у них подразумевается внешний вес.\n"
    "СПЛИТ (если пользователь не указал число дней — 3–4 дня в неделю):\n"
    "- 2–3 дня → full-body или верх/низ; 4 дня → верх/низ ×2; 5–6 дней → push/pull/legs. "
    "Сплит подбирай так, чтобы каждая мышца работала минимум 2 раза в неделю.\n"
    "- Учитывай уровень: новичкам проще движения, линейная прогрессия и меньше интенсивность; "
    "опытным — волновая периодизация, сложнее и тяжелее.\n\n"
    "РЕФЕРЕНСНЫЕ ПРОГРАММЫ (используй их структуру как основу, воспроизводи ключевые механики):\n\n"
    "1) **Wendler 5/3/1** (сила, продвинутые):\n"
    "   • Волна из 3 недель + deload:\n"
    "     - Нед.1 (5s): 3×5 @ 65/75/85% от 90% ТМ. Последний подход AMRAP-стиль.\n"
    "     - Нед.2 (3s): 3×3 @ 70/80/90%.\n"
    "     - Нед.3 (5/3/1): 3 подхода — 1×5 @ 75%, 1×3 @ 85%, 1×1+ @ 95%.\n"
    "     - Нед.4 (deload): 3×5 @ 40/50/60%.\n"
    "   • База — 1 базовое движение за тренировку + BBB-подсобка (5×10 @ 50% ТМ) + 2–3 изоляции.\n\n"
    "2) **Sheiko** (пауэрлифтинг, средний+):\n"
    "   • Высокий объём (12–16 подходов/тренировка), 3–4 дня в неделю.\n"
    "   • Присед/жим/тяга — по 4–8 подходов за день @ 55–80% с широкой волной "
    "(нед.1 5×5 @ 70%, нед.2 6×3 @ 75%, нед.3 5×2 @ 80%, нед.4 разгрузка 4×5 @ 60%).\n"
    "   • Проценты «зигзагом» внутри дня: 55/60/70/75/70/65% × 5-6-4-3-4-5. Ротация лёгкий/средний/тяжёлый.\n\n"
    "3) **StrongLifts 5×5 / Starting Strength** (новички, сила):\n"
    "   • Full-body 3 дня в неделю (A: присед/жим/тяга, B: присед/жим стоя/подтягивания или трэп-стик).\n"
    "   • Все базовые: 5×5, кроме становой 1×5. Прогресс: +2.5кг/тренировку в верх, +5кг/тренировку в низ.\n"
    "   • Проценты: старт с 50% от 1ПМ, к концу 4-х недель — 65–75%.\n\n"
    "4) **Smolov Jr** (жим/присед, узкоспециализированная, 3 недели):\n"
    "   • Пн 6×6 @ 70%, Ср 7×5 @ 75%, Пт 8×4 @ 80%, Сб 10×3 @ 85%.\n"
    "   • Каждую неделю +2.5кг к рабочим весам. Только одно упражнение + минимум подсобки.\n\n"
    "5) **Push/Pull/Legs (PPL)** (гипертрофия, 6 дней/нед):\n"
    "   • Push (грудь/плечи/трицепс): жим лёжа 4×6-8, жим гантелей на наклонной 3×8-10, "
    "жим стоя 3×8, разводки 3×12, разгибания на блоке 3×12, узкий жим 3×10.\n"
    "   • Pull (спина/бицепс): становая 3×5, подтягивания 4×макс, тяга штанги 4×8, "
    "тяга блока 3×12, шраги 3×15, сгибания со штангой 3×10, молотки 3×12.\n"
    "   • Legs: присед 4×6-8, румынская тяга 3×8, жим ногами 3×12, выпады 3×10, "
    "разгибания 3×15, сгибания 3×15, икры 4×15.\n"
    "   • Прогрессия: неделя 1 → +1 повтор к каждому подходу; неделя 2 → +1 подход; "
    "неделя 3 → +5% веса, повторы обратно; неделя 4 → deload.\n\n"
    "6) **PHUL** (Power Hypertrophy Upper/Lower, 4 дня, гибрид силы+массы):\n"
    "   • Пн Power Upper: жим лёжа 4×3-5, тяга штанги 4×3-5, жим стоя 3×6-8, "
    "тяга блока 3×6-10, сгибания 3×6-10, разгибания 3×6-10.\n"
    "   • Вт Power Lower: присед 4×3-5, становая 4×3-5, жим ногами 3×10-15, сгибания 3×6-10, икры 4×6-10.\n"
    "   • Чт Hypertrophy Upper: жим гантелей на наклонной 4×8-12, тяга гантели 4×8-12, "
    "разводки 3×8-12, тяга блока 3×8-12, разгибания на блоке 3×12-15, сгибания 3×12-15.\n"
    "   • Пт Hypertrophy Lower: фронтальный присед 4×8-12, румынская тяга 3×8-12, "
    "выпады 3×8-12, разгибания 3×12-15, сгибания 3×12-15, икры 4×12-15.\n\n"
    "7) **PHAT** (Power Hypertrophy Adaptive Training, Layne Norton, 5 дней):\n"
    "   • Пн Power Upper (спина/плечи/грудь/бицепс: 3-5 повторов на базе, 6-10 на подсобке).\n"
    "   • Вт Power Lower.\n"
    "   • Чт Hypertrophy Back/Shoulders (8-12 повторов).\n"
    "   • Пт Hypertrophy Lower.\n"
    "   • Сб Hypertrophy Chest/Arms (12-15 повторов).\n\n"
    "8) **German Volume Training (GVT / 10×10)** (гипертрофия, 3–6 недель):\n"
    "   • Один базовый: 10 подходов × 10 повторов @ 60% 1ПМ, отдых 60–90 сек между подходами.\n"
    "   • Дополнение: 3×10 антагонист. Прогрессия: держать 10×10, к 4-й неделе поднять до 65%.\n\n"
    "9) **DUP (Daily Undulating Periodization)** (гипертрофия+сила, 4 дня):\n"
    "   • Пн тяжёлый: 5×3 @ 85%. Ср объёмный: 4×8 @ 70%. Пт скоростной: 6×5 @ 65%.\n"
    "   • Меняй sets/reps/веса каждую тренировку (в отличие от блочной периодизации).\n\n"
    "10) **Bodybuilder Bro-Split** (гипертрофия, 5–6 дней, для среднего/продвинутого):\n"
    "    • Пн грудь: жим лёжа 4×8, жим на наклонной 3×10, жим гантелей 3×10, разводки 3×12, кроссовер 3×15.\n"
    "    • Вт спина: подтягивания 4×макс, тяга штанги 4×8, тяга блока 3×10, тяга гантели 3×10, шраги 3×15.\n"
    "    • Ср плечи: жим гантелей сидя 4×10, тяга к подбородку 3×10, разводки в стороны 4×12, разводки в наклоне 3×15.\n"
    "    • Чт руки: сгибания со штангой 4×10, молотки 3×12, французский жим 4×10, разгибания на блоке 3×15.\n"
    "    • Пт ноги: присед 4×8, жим ногами 4×12, выпады 3×10, разгибания 3×15, сгибания 3×15, икры 5×15.\n"
    "    • Сб опционально: слабые группы дополнительно.\n"
    "    • Прогрессия: чередование недель — тяжёлая (нижняя граница повторов), объёмная (верхняя), метаболическая (дроп-сеты).\n\n"
    "**Как использовать референсы**: определи наиболее подходящую программу под запрос пользователя (цель + опыт + дни) "
    "и построй по её структуре — с реальным разнообразием подходов/повторов между неделями."
)


_AI_QUESTIONS_SYSTEM = (
    "Ты — опытный тренер по силовым видам спорта. Пользователь просит составить тренировочную программу. "
    "Перед составлением задай уточняющие вопросы, чтобы программа получилась максимально точной. "
    "Отвечай ТОЛЬКО валидным JSON без пояснений, по схеме:\n"
    '{"questions":[{"question":"текст вопроса","tier":"basic|advanced","options":["вариант 1","вариант 2"]}]}\n'
    "Правила:\n"
    "- Ровно 8–10 вопросов. Спрашивай ТОЛЬКО о том, чего нет в запросе пользователя (не переспрашивай известное).\n"
    "- Поле tier: \"basic\" — базовые обязательные (5–6 шт., ключевые для структуры программы), "
    "\"advanced\" — тонкая настройка (3–4 шт., помогают отточить нагрузку).\n"
    "- **НИКОГДА не спрашивай про 1ПМ (одноповторные максимумы, рабочие веса, сколько кг присед/жим/тяга).** "
    "Максимумы пользователь укажет при выборе программы (после генерации). Программы на %1ПМ автоматически "
    "масштабируются под введённые максимумы. Не задавай вопросов про конкретные веса.\n"
    "- Обязательно покрой темы (распределяй по tier сам исходя из запроса):\n"
    "  • basic: главная цель (сила / масса / выносливость / комбо), уровень опыта, дней в неделю, "
    "доступное оборудование (зал / штанга дома / только гантели / свой вес), длительность программы (недель), "
    "среднее время на тренировку.\n"
    "  • advanced: травмы или ограничения, предпочитаемый сплит (full-body / верх-низ / PPL — или «на усмотрение ИИ»), "
    "любимые / нелюбимые упражнения, нужна ли кардио/условка внутри тренировок, режим питания "
    "(масса / поддержка / дефицит), качество восстановления (сон 7–9ч / меньше / хроническая усталость), "
    "стиль прогрессии (плавный / волновой Wendler / линейный).\n"
    "- К каждому вопросу 3–5 коротких вариантов ответа (до 40 символов), без «другое» — есть поле «свой ответ» на фронте.\n"
    "- Формулировки коротко и по-человечески, без канцелярита. Вопросы и варианты — на русском. "
    "Выводи компактный JSON."
)


async def _ai_build_template(data, current, source, replace=None):
    """Конвертация JSON-ответа ИИ во внутренний шаблон + сохранение (replace — обновить на месте)."""
    if not isinstance(data, dict) or not (data.get("weeks") or []):
        raise HTTPException(status_code=422, detail="ИИ не смог построить структуру программы")
    tgid = current.get("telegram_id")
    catalog = await db.exercises.find(
        {"$or": [{"is_builtin": True}, {"owner_telegram_id": tgid}]}, {"_id": 0}
    ).to_list(1000)
    by_name = {(ex.get("name") or "").strip().lower(): ex for ex in catalog if ex.get("name")}
    names = list(by_name.keys())

    uses_percent = False
    orm_map = {}
    weeks_out = []
    for wi, w in enumerate((data.get("weeks") or [])[:16], start=1):
        days_out = []
        used_idx = set()
        for di, d in enumerate((w.get("days") or [])[:7], start=1):
            exs_out = []
            for order, e in enumerate((d.get("exercises") or [])[:15]):
                nm = str(e.get("name") or "").strip()
                if not nm:
                    continue
                match = by_name.get(nm.lower())
                if not match:
                    close = difflib.get_close_matches(nm.lower(), names, n=1, cutoff=0.85)
                    if close:
                        match = by_name[close[0]]
                lg = e.get("lift_group")
                if lg not in ("squat", "bench", "deadlift"):
                    lg = None
                mg = e.get("muscle_group")
                if match and (match.get("muscle_groups") or []):
                    mg = match["muscle_groups"][0]

                ex_percent = False
                scheme = []
                for s in (e.get("sets") or [])[:12]:
                    try:
                        n_sets = max(1, min(20, int(s.get("sets") or 1)))
                        reps = max(0, min(100, int(s.get("reps") or 0)))
                    except (TypeError, ValueError):
                        continue
                    w_val = s.get("weight")
                    pct = s.get("percent_1rm")
                    if w_val is None and pct is not None and lg:
                        try:
                            w_val = _round_2_5(float(pct))  # base_max = 100 кг → вес ≡ проценту
                            ex_percent = True
                        except (TypeError, ValueError):
                            w_val = None
                    elif w_val is not None:
                        try:
                            w_val = round(float(w_val), 2)
                        except (TypeError, ValueError):
                            w_val = None
                    scheme.append({"weight": w_val, "sets": n_sets, "reps": reps})
                has_weight = any(s.get("weight") for s in scheme)
                is_acc = bool(e.get("is_accessory")) and not has_weight
                if ex_percent:
                    uses_percent = True
                    if match and match.get("slug"):
                        orm_map[match["slug"]] = 100.0
                try:
                    rest = int(e.get("rest_seconds")) if e.get("rest_seconds") else None
                except (TypeError, ValueError):
                    rest = None
                exs_out.append({
                    "exercise_id": (match or {}).get("id"),
                    "exercise_slug": (match or {}).get("slug"),
                    "exercise_name": (match or {}).get("name") or nm,
                    "muscle_group": mg,
                    "order": order,
                    "target_sets": sum(s["sets"] for s in scheme) or (4 if is_acc else 3),
                    "target_reps": str(scheme[0]["reps"]) if scheme else "10",
                    "weight_type": (match or {}).get("weight_type") or "kg",
                    "rest_seconds": rest,
                    "sets_scheme": [] if is_acc else scheme,
                    "lift_group": lg,
                    "is_accessory": is_acc,
                })
            if not exs_out:
                continue
            try:
                idx = int(d.get("day_index") or di)
            except (TypeError, ValueError):
                idx = di
            idx = min(7, max(1, idx))
            while idx in used_idx and idx < 7:
                idx += 1
            used_idx.add(idx)
            days_out.append({
                "day_index": idx,
                "title": str(d.get("title") or f"День {len(days_out) + 1}")[:60],
                "is_rest": False,
                "exercises": exs_out,
            })
        if days_out:
            days_out.sort(key=lambda x: x["day_index"])
            weeks_out.append({"week_index": wi, "published": True, "days": days_out})

    if not weeks_out:
        raise HTTPException(status_code=422, detail="ИИ не смог распознать ни одного тренировочного дня")

    level = data.get("level") if data.get("level") in ("beginner", "intermediate", "advanced") else "intermediate"
    goal = data.get("goal") if data.get("goal") in ("strength", "hypertrophy", "powerlifting", "general") else "general"
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "slug": None,
        "name": str(data.get("name") or (replace or {}).get("name") or "Моя программа")[:80],
        "description": str(data.get("description") or (replace or {}).get("description") or "")[:600],
        "author": "ИИ-анализ",
        "level": level,
        "goal": goal,
        "weeks": weeks_out,
        "is_builtin": False,
        "owner_telegram_id": tgid,
        "source": source,
        "share_code": None,
        "shared_from": None,
        "tags": [],
        "default_one_rep_max": orm_map,
        "requires_maxes": uses_percent,
        "base_maxes": {"squat": 100, "bench": 100, "deadlift": 100} if uses_percent else {},
        "created_at": now,
        "updated_at": now,
    }
    if replace:
        doc["id"] = replace["id"]
        doc["created_at"] = replace.get("created_at") or now
        doc["slug"] = replace.get("slug")
        doc["share_code"] = replace.get("share_code")
        doc["shared_from"] = replace.get("shared_from")
        doc["tags"] = replace.get("tags") or []
    _template_recount(doc)
    if replace:
        await db.programs.update_one({"id": doc["id"]}, {"$set": dict(doc)})
    else:
        await db.programs.insert_one(dict(doc))
    doc.pop("_id", None)
    logger.info(f"AI template {'refined' if replace else 'created'}: {doc['name']} (owner={tgid}, source={source})")
    return doc


class AiAnswer(BaseModel):
    question: str
    answer: str


class AiGenerateReq(BaseModel):
    prompt: str
    answers: list[AiAnswer] = []


class AiQuestionsReq(BaseModel):
    prompt: str


class AiParseReq(BaseModel):
    text: str


class AiRefineReq(BaseModel):
    template_id: str
    feedback: str


def _template_to_ai_json(doc):
    """Обратная конвертация шаблона в JSON-схему ИИ (для правок)."""
    pct_slugs = set((doc.get("default_one_rep_max") or {}).keys())
    req = bool(doc.get("requires_maxes"))
    weeks = []
    for w in doc.get("weeks") or []:
        days = []
        for d in w.get("days") or []:
            if d.get("is_rest"):
                continue
            exs = []
            for e in sorted(d.get("exercises") or [], key=lambda x: x.get("order") or 0):
                as_pct = req and e.get("lift_group") and e.get("exercise_slug") in pct_slugs
                sets = [{
                    "weight": None if as_pct else s.get("weight"),
                    "percent_1rm": s.get("weight") if as_pct else None,
                    "sets": s.get("sets"), "reps": s.get("reps"),
                } for s in (e.get("sets_scheme") or [])]
                if not sets:
                    m = re.search(r"\d+", str(e.get("target_reps") or ""))
                    sets = [{"weight": None, "percent_1rm": None,
                             "sets": int(e.get("target_sets") or 3),
                             "reps": int(m.group()) if m else 10}]
                exs.append({
                    "name": e.get("exercise_name"),
                    "muscle_group": e.get("muscle_group"),
                    "lift_group": e.get("lift_group"),
                    "is_accessory": bool(e.get("is_accessory")),
                    "rest_seconds": e.get("rest_seconds"),
                    "sets": sets,
                })
            days.append({"day_index": d.get("day_index"), "title": d.get("title"), "exercises": exs})
        weeks.append({"week_index": w.get("week_index"), "days": days})
    return {"name": doc.get("name"), "description": doc.get("description"),
            "level": doc.get("level"), "goal": doc.get("goal"), "weeks": weeks}


def _ai_require_enabled():
    cfg = _ai_config()
    if not (cfg["base_url"] and cfg["api_key"]):
        raise HTTPException(status_code=503,
                            detail="ИИ-анализ пока не настроен: не задан API-ключ сервиса")


async def _ai_start_job(current, kind, coro_factory):
    """Долгие ИИ-запросы (>60 c) убивает ingress — выполняем в фоне, клиент опрашивает job."""
    job_id = str(uuid.uuid4())
    await db.ai_jobs.insert_one({
        "id": job_id, "telegram_id": current.get("telegram_id"), "kind": kind,
        "status": "pending", "template": None, "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    async def _run():
        try:
            tpl = await coro_factory()
            await db.ai_jobs.update_one({"id": job_id}, {"$set": {"status": "done", "template": tpl}})
        except HTTPException as e:
            await db.ai_jobs.update_one({"id": job_id}, {"$set": {"status": "error", "error": str(e.detail)}})
        except Exception:
            logger.exception(f"AI job {job_id} failed")
            await db.ai_jobs.update_one(
                {"id": job_id},
                {"$set": {"status": "error", "error": "Непредвиденная ошибка ИИ — попробуйте ещё раз"}})

    asyncio.create_task(_run())
    return {"job_id": job_id, "status": "pending"}


@api_router.get("/ai/program/jobs/{job_id}")
async def ai_job_status(job_id: str, current: dict = Depends(get_current_user)):
    job = await db.ai_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if job.get("telegram_id") != current.get("telegram_id"):
        raise HTTPException(status_code=403, detail="Доступ к чужой задаче запрещён")
    return job


@api_router.post("/ai/program/questions")
async def ai_program_questions(payload: AiQuestionsReq, current: dict = Depends(get_current_user)):
    """Уточняющие вопросы по первому запросу пользователя (шаг 1 генерации)."""
    _rate_limit(f"ai:{current['telegram_id']}", 30, 600,
                "Слишком много запросов к ИИ. Попробуйте позже.")
    prompt = (payload.prompt or "").strip()
    if len(prompt) < 10:
        raise HTTPException(status_code=400, detail="Опишите пожелания подробнее (минимум 10 символов)")
    content = await _ai_chat([
        {"role": "system", "content": _AI_QUESTIONS_SYSTEM},
        {"role": "user", "content": f"Запрос пользователя:\n{prompt[:4000]}"},
    ], temperature=0.4)
    data = _extract_json(content)
    out = []
    for q in (data.get("questions") or [])[:10]:
        qt = str(q.get("question") or "").strip()
        if not qt:
            continue
        tier = str(q.get("tier") or "").strip().lower()
        if tier not in ("basic", "advanced"):
            tier = "basic"
        opts = [str(o).strip()[:60] for o in (q.get("options") or [])[:6] if str(o).strip()]
        out.append({"question": qt[:200], "tier": tier, "options": opts})
    if not out:
        raise HTTPException(status_code=422, detail="ИИ не смог составить вопросы — попробуйте ещё раз")
    return {"questions": out}


@api_router.post("/ai/program/generate")
async def ai_generate_program(payload: AiGenerateReq, current: dict = Depends(get_current_user)):
    """Генерация программы (фоновая задача): промпт + ответы на уточняющие вопросы."""
    _rate_limit(f"ai:{current['telegram_id']}", 30, 600,
                "Слишком много запросов к ИИ. Попробуйте позже.")
    prompt = (payload.prompt or "").strip()
    if len(prompt) < 10:
        raise HTTPException(status_code=400, detail="Опишите пожелания подробнее (минимум 10 символов)")
    _ai_require_enabled()
    extra = ""
    qa_lines = [f"- {a.question.strip()[:200]} → {a.answer.strip()[:200]}"
                for a in (payload.answers or [])[:10] if (a.answer or "").strip()]
    if qa_lines:
        extra = "\n\nОтветы пользователя на уточняющие вопросы (обязательно учти):\n" + "\n".join(qa_lines)

    async def _factory():
        content = await _ai_chat([
            {"role": "system", "content": _AI_SYSTEM_GEN},
            {"role": "user", "content":
                "Составь ПОЛНОЦЕННУЮ объёмную тренировочную программу по пожеланиям пользователя: "
                "5–8 упражнений в каждый тренировочный день, с прогрессией по неделям. "
                "Если пользователь не указал длительность — сделай 4 недели; не более 12 недель. "
                f"Пожелания:\n{prompt[:4000]}{extra}"},
        ], temperature=0.5)
        data = _extract_json(content)
        return await _ai_build_template(data, current, "ai")

    return await _ai_start_job(current, "generate", _factory)


@api_router.post("/ai/program/refine")
async def ai_refine_program(payload: AiRefineReq, current: dict = Depends(get_current_user)):
    """Правки готовой ИИ-программы по замечаниям пользователя (фоновая задача, тот же id)."""
    _rate_limit(f"ai:{current['telegram_id']}", 30, 600,
                "Слишком много запросов к ИИ. Попробуйте позже.")
    feedback = (payload.feedback or "").strip()
    if len(feedback) < 5:
        raise HTTPException(status_code=400, detail="Опишите, что исправить (минимум 5 символов)")
    _ai_require_enabled()
    tgid = current.get("telegram_id")
    doc = await db.programs.find_one({"id": payload.template_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Программа не найдена")
    if doc.get("is_builtin") or doc.get("owner_telegram_id") != tgid:
        raise HTTPException(status_code=403, detail="Можно править только свои программы")
    current_json = json.dumps(_template_to_ai_json(doc), ensure_ascii=False, separators=(",", ":"))

    async def _factory():
        content = await _ai_chat([
            {"role": "system", "content": _AI_SYSTEM_GEN},
            {"role": "user", "content":
                "Вот ТЕКУЩАЯ тренировочная программа пользователя (JSON по схеме):\n"
                f"{current_json[:60000]}\n\n"
                f"Пользователь просит внести правки/уточнения:\n{feedback[:2000]}\n\n"
                "Верни ПОЛНУЮ обновлённую программу по той же схеме. Измени ТОЛЬКО то, о чём просит "
                "пользователь; всё остальное (название, недели, дни, упражнения, веса, подходы) сохрани "
                "без изменений. Название и описание меняй только если пользователь явно попросил."},
        ], temperature=0.3)
        data = _extract_json(content)
        return await _ai_build_template(data, current, doc.get("source") or "ai", replace=doc)

    return await _ai_start_job(current, "refine", _factory)


async def _ai_parse_text(text, current):
    content = await _ai_chat([
        {"role": "system", "content": _AI_SYSTEM},
        {"role": "user", "content":
            "Разбери готовый план тренировок в структуру. Сохрани ВСЕ недели, дни, упражнения, "
            "веса, проценты, подходы и повторы максимально близко к источнику. "
            f"Источник:\n{text[:60000]}"},
    ], temperature=0.1)
    data = _extract_json(content)
    return await _ai_build_template(data, current, "ai")


@api_router.post("/ai/program/parse")
async def ai_parse_program(payload: AiParseReq, current: dict = Depends(get_current_user)):
    """Разбор готового плана (вставленный текст/таблица) — фоновая задача."""
    _rate_limit(f"ai:{current['telegram_id']}", 30, 600,
                "Слишком много запросов к ИИ. Попробуйте позже.")
    text = (payload.text or "").strip()
    if len(text) < 20:
        raise HTTPException(status_code=400, detail="Вставьте текст плана (минимум 20 символов)")
    _ai_require_enabled()
    return await _ai_start_job(current, "parse", lambda: _ai_parse_text(text, current))


@api_router.post("/ai/program/parse-file")
async def ai_parse_program_file(file: UploadFile = File(...),
                                current: dict = Depends(get_current_user)):
    """Разбор готового плана из файла (.xlsx / .csv / .txt)."""
    _rate_limit(f"ai:{current['telegram_id']}", 30, 600,
                "Слишком много запросов к ИИ. Попробуйте позже.")
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл слишком большой (до 5 МБ)")
    fname = (file.filename or "").lower()
    if fname.endswith(".xlsx"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
        except Exception:
            raise HTTPException(status_code=400, detail="Не удалось прочитать Excel-файл")
        lines = []
        for ws in wb.worksheets[:5]:
            lines.append(f"### Лист: {ws.title}")
            for row in ws.iter_rows(values_only=True):
                cells = ["" if v is None else str(v) for v in row]
                if any(c.strip() for c in cells):
                    lines.append("\t".join(cells))
        text = "\n".join(lines)
    elif fname.endswith((".csv", ".txt", ".tsv", ".md")):
        text = raw.decode("utf-8", errors="replace")
    else:
        raise HTTPException(status_code=400, detail="Поддерживаются файлы .xlsx, .csv, .txt")
    text = text.strip()
    if len(text) < 20:
        raise HTTPException(status_code=400, detail="Файл пуст или не содержит плана")
    return await _ai_parse_text(text, current)


_VISION_EXTRACT_PROMPT = (
    "На изображениях — фрагменты тренировочной программы (таблица, скриншот из чата, "
    "фото тетради, экран Excel и т.п.). Твоя задача — ТОЧНО извлечь всё содержимое "
    "программы в виде структурированного текста:\n"
    "- сохрани разбиение по неделям и дням;\n"
    "- для каждого упражнения выпиши: название (по-русски, как в оригинале), "
    "количество подходов × повторов, вес (кг) или процент от 1ПМ (%), отдых если указан;\n"
    "- если изображений несколько — предполагай, что это ПРОДОЛЖЕНИЕ одной программы "
    "(разные недели/дни), объединяй их по порядку;\n"
    "- если что-то нечитаемо — пропусти, ничего НЕ выдумывай;\n"
    "- никаких пояснений, комментариев или markdown-разметки — только структурированный "
    "текст программы, как из Excel/заметок.\n"
    "Пример формата:\n"
    "Неделя 1\n"
    "Пн: Присед 5×5 80%, Жим лёжа 5×5 75%, Тяга штанги 3×8 60кг\n"
    "Ср: ..."
)


@api_router.post("/ai/program/parse-photo")
async def ai_parse_program_photo(files: list[UploadFile] = File(...),
                                 current: dict = Depends(get_current_user)):
    """Разбор программы по 1–8 фото: Gemini достаёт текст → DeepSeek структурирует.
    Фоновая задача (job_id). Клиент опрашивает GET /ai/program/jobs/{job_id}."""
    _rate_limit(f"ai:{current['telegram_id']}", 30, 600,
                "Слишком много запросов к ИИ. Попробуйте позже.")
    if not files:
        raise HTTPException(status_code=400, detail="Загрузите хотя бы одно фото")
    if len(files) > 8:
        raise HTTPException(status_code=400, detail="Можно загрузить не более 8 фото")

    _ai_require_enabled()
    vcfg = _ai_vision_config()
    if not (vcfg["base_url"] and vcfg["api_key"]):
        raise HTTPException(status_code=503,
                            detail="Разбор по фото недоступен: не задан ключ Gemini")

    import base64
    images = []
    for f in files:
        raw = await f.read()
        if not raw:
            continue
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400,
                                detail=f"Фото '{f.filename or ''}' слишком большое (макс 8 МБ)")
        mime = (f.content_type or "").lower()
        if not mime.startswith("image/"):
            # попробуем по расширению
            fn = (f.filename or "").lower()
            if fn.endswith(".jpg") or fn.endswith(".jpeg"):
                mime = "image/jpeg"
            elif fn.endswith(".png"):
                mime = "image/png"
            elif fn.endswith(".webp"):
                mime = "image/webp"
            elif fn.endswith(".heic"):
                mime = "image/heic"
            else:
                raise HTTPException(status_code=400,
                                    detail="Поддерживаются только изображения (jpg/png/webp/heic)")
        images.append({"mime": mime, "data_b64": base64.b64encode(raw).decode("ascii")})

    if not images:
        raise HTTPException(status_code=400, detail="Не удалось прочитать ни одно изображение")

    async def _factory():
        # Шаг 1: Gemini достаёт текст программы из изображений
        extracted = await _ai_chat_vision(_VISION_EXTRACT_PROMPT, images)
        extracted = (extracted or "").strip()
        if len(extracted) < 20:
            raise HTTPException(status_code=422,
                                detail="Не удалось распознать программу на фото — проверьте качество снимков")
        # Шаг 2: DeepSeek структурирует извлечённый текст в шаблон
        return await _ai_parse_text(extracted, current)

    return await _ai_start_job(current, "parse-photo", _factory)


# ---- Настройки пользователя (streak_mode / единицы) ----
@api_router.patch("/users/{telegram_id}/settings")
async def update_user_settings(telegram_id: int, payload: UserSettingsReq,
                               current: dict = Depends(get_current_user)):
    # IDOR-защита: настройки можно менять только себе.
    if telegram_id != current["telegram_id"]:
        raise HTTPException(status_code=403, detail="Not your account")
    user = await db.users.find_one({"telegram_id": telegram_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    settings = dict(user.get("settings") or {})
    if payload.streak_mode in ("strict", "lenient"):
        settings["streak_mode"] = payload.streak_mode
    if payload.units in ("kg", "lb"):
        settings["units"] = payload.units
    if payload.default_rest_sec is not None:
        settings["default_rest_sec"] = int(payload.default_rest_sec)
    await db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"settings": settings, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    updated = await db.users.find_one(
        {"telegram_id": telegram_id}, {"_id": 0, "password_hash": 0}
    )
    return updated


# ===========================================================================
# ДНЕВНИК (Diary) — свободная запись тренировок + персональный ИИ-агент
# Дневниковые тренировки = WorkoutSession(mode="diary", plan_id=None) в той же
# коллекции workout_sessions → streak/статистика учитывают их автоматически.
# ===========================================================================

# --- Каталог упражнений и резолвинг названий -------------------------------
async def _diary_catalog(tgid):
    catalog = await db.exercises.find(
        {"$or": [{"is_builtin": True}, {"owner_telegram_id": tgid}]}, {"_id": 0}
    ).to_list(1000)
    by_name = {(ex.get("name") or "").strip().lower(): ex for ex in catalog if ex.get("name")}
    by_slug = {ex.get("slug"): ex for ex in catalog if ex.get("slug")}
    return (by_name, by_slug, list(by_name.keys()))


def _resolve_catalog_ex(name, slug, cat):
    by_name, by_slug, names = cat
    if slug and slug in by_slug:
        return by_slug[slug]
    nm = (name or "").strip().lower()
    if not nm:
        return None
    if nm in by_name:
        return by_name[nm]
    close = difflib.get_close_matches(nm, names, n=1, cutoff=0.82)
    return by_name[close[0]] if close else None


def _norm_scheme(sets_in):
    scheme = []
    for s in (sets_in or [])[:20]:
        try:
            n = max(1, min(30, int(s.get("sets") or 1)))
            r = max(0, min(100, int(s.get("reps") or 0)))
        except (TypeError, ValueError):
            continue
        w = s.get("weight")
        try:
            w = round(float(w), 2) if w is not None else None
        except (TypeError, ValueError):
            w = None
        scheme.append({"weight": w, "sets": n, "reps": r})
    return scheme


def _diary_exercise_card(item, order, cat):
    """Строит карточку выполненного упражнения (status=done) для дневника."""
    name = (item.get("name") or "").strip()
    slug = item.get("exercise_slug")
    match = _resolve_catalog_ex(name, slug, cat)
    scheme = _norm_scheme(item.get("sets_scheme"))
    lg = item.get("lift_group")
    if lg not in ("squat", "bench", "deadlift"):
        lg = None
    mg = item.get("muscle_group")
    if match and (match.get("muscle_groups") or []):
        mg = match["muscle_groups"][0]
    has_weight = any(s.get("weight") for s in scheme)
    is_acc = bool(item.get("is_accessory")) and not has_weight
    pe = {
        "exercise_id": (match or {}).get("id"),
        "exercise_slug": (match or {}).get("slug") or slug,
        "exercise_name": (match or {}).get("name") or name or "Упражнение",
        "muscle_group": mg,
        "lift_group": lg,
        "is_accessory": is_acc,
        "rest_seconds": item.get("rest_seconds"),
        "sets_scheme": [] if is_acc else scheme,
        "target_sets": (sum(s["sets"] for s in scheme) or (4 if is_acc else 3)),
        "target_reps": str(scheme[0]["reps"]) if scheme else "10",
    }
    card = _view_exercise(pe, {}, order, status="done")
    if not is_acc:
        logs = _expand_set_logs(card.get("sets_scheme"))
        for lgm in logs:
            lgm["done"] = True
        card["set_logs"] = logs
    card["filled_by"] = "athlete"
    return card


# --- Оценка сложности (детерминированная) ----------------------------------
def _reps_to_intensity(reps):
    """Прокси интенсивности (% от 1ПМ) по числу повторов (когда 1ПМ неизвестен)."""
    if not reps or reps <= 0:
        return 0.6
    if reps >= 20:
        return 0.5
    table = [(1, 1.0), (2, 0.96), (3, 0.93), (4, 0.90), (5, 0.87), (6, 0.85),
             (8, 0.80), (10, 0.75), (12, 0.70), (15, 0.65), (20, 0.55)]
    for i, (r, v) in enumerate(table):
        if reps == r:
            return v
        if reps < r:
            pr, pv = table[i - 1]
            return round(pv + (v - pv) * (reps - pr) / (r - pr), 3)
    return 0.5


def _exercise_intensity(ex, maxes):
    scheme = ex.get("sets_scheme") or []
    if not scheme:
        return 0.5
    lg = ex.get("lift_group")
    top = _top_set(scheme)
    if lg in ("squat", "bench", "deadlift") and (maxes or {}).get(lg) and top and top.get("weight"):
        try:
            return min(1.05, float(top["weight"]) / float(maxes[lg]))
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    pcts = [s.get("percent_1rm") for s in scheme if s.get("percent_1rm")]
    if pcts:
        try:
            return min(1.05, max(pcts) / 100.0)
        except (TypeError, ValueError):
            pass
    reps_vals = [(s.get("reps") or 0) for s in scheme if (s.get("reps") or 0) > 0]
    return _reps_to_intensity(min(reps_vals)) if reps_vals else 0.6


def _diary_difficulty(session, profile):
    """Объективный балл сложности 0..100 + категория (+ подмешивание субъективного RPE)."""
    exs = [e for e in session.get("exercises", []) if e.get("status") == "done"]
    maxes = (profile or {}).get("maxes") or {}
    load = 0.0
    total_sets = 0
    total_reps = 0
    wint = 0.0
    for e in exs:
        i = _exercise_intensity(e, maxes)
        scheme = e.get("sets_scheme") or []
        if not scheme:
            # подсобка/bodyweight без схемы: оценим как 3×12, невысокая интенсивность
            load += 3 * 12 * (0.4 + 0.6 * 0.5)
            total_sets += 3
            total_reps += 36
            wint += 3 * 0.5
            continue
        for s in scheme:
            n = int(s.get("sets") or 0)
            r = int(s.get("reps") or 0)
            load += n * (r * (0.4 + 0.6 * i))
            total_sets += n
            total_reps += n * r
            wint += n * i
    score = max(0, min(100, round(load * 0.7)))
    rpe = session.get("rpe")
    if rpe:
        try:
            score = int(round(0.6 * score + 0.4 * min(100.0, float(rpe) * 10)))
        except (TypeError, ValueError):
            pass
    if score < 36:
        cat = "Легко"
    elif score < 61:
        cat = "Средне"
    elif score < 81:
        cat = "Тяжело"
    else:
        cat = "Очень тяжело"
    avg28 = (profile or {}).get("avg_difficulty_28d")
    delta = round(score - avg28) if isinstance(avg28, (int, float)) else None
    avg_int = round(wint / total_sets, 3) if total_sets else 0
    return {"score": score, "category": cat, "sets": total_sets, "reps": total_reps,
            "avg_intensity": avg_int, "vs_avg_28d": delta}


# --- Профиль агента и вспомогательные сводки --------------------------------
async def _diary_profile_get(tgid):
    doc = await db.diary_profile.find_one({"telegram_id": tgid}, {"_id": 0})
    if not doc:
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "telegram_id": tgid, "goal": "general", "experience": "intermediate",
            "equipment": "gym", "injuries": [],
            "preferences": {"likes": [], "dislikes": []},
            "weekly_target_days": 3, "maxes": {}, "agent_notes": "",
            "avg_difficulty_28d": None, "onboarded": False,
            "created_at": now, "updated_at": now,
        }
        await db.diary_profile.insert_one(dict(doc))
        doc.pop("_id", None)
    return doc


async def _update_avg_difficulty(tgid):
    since = (datetime.now(timezone.utc).date() - timedelta(days=28)).isoformat()
    docs = await db.workout_sessions.find(
        {"athlete_telegram_id": tgid, "status": "finished", "difficulty_score": {"$ne": None}},
        {"_id": 0, "difficulty_score": 1, "date": 1, "finished_at": 1},
    ).to_list(500)
    scores = []
    for s in docs:
        d = _session_day(s)
        if d and d.isoformat() >= since:
            scores.append(s.get("difficulty_score"))
    avg = round(sum(scores) / len(scores), 1) if scores else None
    await db.diary_profile.update_one(
        {"telegram_id": tgid}, {"$set": {"avg_difficulty_28d": avg}}, upsert=True)
    return avg


async def _recent_sessions_summary(tgid, n=7):
    docs = await db.workout_sessions.find(
        {"athlete_telegram_id": tgid, "status": "finished"}, {"_id": 0}
    ).sort("created_at", -1).to_list(n)
    lines = []
    for s in docs:
        st = _get_session_stats(s)
        d = _session_day(s)
        lines.append(f"- {d.isoformat() if d else '—'}: {s.get('title') or 'Тренировка'}; "
                     f"группы {st.get('group') or '—'}; тоннаж {st.get('tonnage')}кг; "
                     f"подходов {st.get('sets_done')}; сложность {s.get('difficulty_score') or '—'}")
    return "\n".join(lines) if lines else "(история пуста)"


async def _weekly_muscle_volume(tgid, days=7):
    since = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
    docs = await db.workout_sessions.find(
        {"athlete_telegram_id": tgid, "status": "finished"}, {"_id": 0}
    ).to_list(500)
    agg = {}
    count = 0
    for s in docs:
        d = _session_day(s)
        if not d or d < since:
            continue
        count += 1
        for ltr, c in _muscle_sets(s.get("exercises") or []).items():
            agg[ltr] = agg.get(ltr, 0) + c
    groups = [{"group": ltr, "label": _LETTER_NAMES.get(ltr, ltr), "sets": agg[ltr]}
              for ltr in _LETTER_ORDER if ltr in agg]
    return {"days": days, "workouts": count, "groups": groups}


def _profile_context(profile):
    p = profile or {}
    prefs = p.get("preferences") or {}
    return ("Профиль пользователя: "
            f"цель={p.get('goal')}, опыт={p.get('experience')}, оборудование={p.get('equipment')}, "
            f"дней/нед={p.get('weekly_target_days')}, "
            f"травмы/ограничения={', '.join(p.get('injuries') or []) or 'нет'}, "
            f"любит={', '.join(prefs.get('likes') or []) or '—'}, "
            f"не любит={', '.join(prefs.get('dislikes') or []) or '—'}, "
            f"средняя сложность за 28д={p.get('avg_difficulty_28d') if p.get('avg_difficulty_28d') is not None else '—'}. "
            f"Заметки агента: {p.get('agent_notes') or 'нет'}.")


# --- CRUD дневниковых записей -----------------------------------------------
@api_router.get("/diary/profile")
async def diary_get_profile(current: dict = Depends(get_current_user)):
    return await _diary_profile_get(current["telegram_id"])


@api_router.put("/diary/profile")
async def diary_put_profile(payload: DiaryProfileUpdate, current: dict = Depends(get_current_user)):
    tgid = current["telegram_id"]
    await _diary_profile_get(tgid)
    upd = {"updated_at": datetime.now(timezone.utc).isoformat(), "onboarded": True}
    if payload.goal in ("strength", "hypertrophy", "powerlifting", "general"):
        upd["goal"] = payload.goal
    if payload.experience in ("beginner", "intermediate", "advanced"):
        upd["experience"] = payload.experience
    if payload.equipment in ("gym", "barbell_home", "dumbbells", "bodyweight"):
        upd["equipment"] = payload.equipment
    if payload.injuries is not None:
        upd["injuries"] = [str(x)[:60] for x in payload.injuries][:10]
    if payload.weekly_target_days is not None:
        upd["weekly_target_days"] = max(1, min(7, int(payload.weekly_target_days)))
    if payload.maxes is not None:
        upd["maxes"] = {k: float(v) for k, v in payload.maxes.items()
                        if k in ("squat", "bench", "deadlift") and v}
    prefs = {}
    if payload.likes is not None:
        prefs["likes"] = [str(x)[:40] for x in payload.likes][:15]
    if payload.dislikes is not None:
        prefs["dislikes"] = [str(x)[:40] for x in payload.dislikes][:15]
    if prefs:
        cur_prefs = ((await db.diary_profile.find_one({"telegram_id": tgid}, {"_id": 0, "preferences": 1}))
                     or {}).get("preferences") or {}
        cur_prefs.update(prefs)
        upd["preferences"] = cur_prefs
    await db.diary_profile.update_one({"telegram_id": tgid}, {"$set": upd})
    return await _diary_profile_get(tgid)


@api_router.post("/diary/sessions")
async def diary_create_session(payload: DiarySessionCreate, current: dict = Depends(get_current_user)):
    tgid = current["telegram_id"]
    profile = await _diary_profile_get(tgid)
    cat = await _diary_catalog(tgid)
    items = [i.model_dump() for i in (payload.exercises or [])]
    exs = [_diary_exercise_card(it, idx, cat) for idx, it in enumerate(items)]
    exs = [e for e in exs if e.get("exercise_name")]
    if not exs:
        raise HTTPException(status_code=400, detail="Добавьте хотя бы одно упражнение")
    now = datetime.now(timezone.utc).isoformat()
    the_date = payload.date or datetime.now(timezone.utc).date().isoformat()
    group, _diff_lbl = _day_group_difficulty(exs)
    default_title = f"Тренировка · {group}" if group else "Тренировка"
    session = {
        "id": str(uuid.uuid4()),
        "plan_id": None, "athlete_telegram_id": tgid, "coach_telegram_id": None,
        "mode": "diary", "week_index": None, "day_index": None,
        "date": the_date, "title": (payload.title or default_title)[:80],
        "status": "finished", "paused": False,
        "started_by": "athlete", "started_at": now, "finished_at": now,
        "rpe": payload.rpe, "notes": payload.notes,
        "raw_input": payload.raw_input, "source_input": payload.source_input or "quick",
        "exercises": exs, "ai_feedback": None,
        "version": 0,
        "last_event_at": now, "created_at": now, "updated_at": now,
    }
    diff = _diary_difficulty(session, profile)
    session["difficulty_score"] = diff["score"]
    session["stats"] = _session_stats(session)
    await db.workout_sessions.insert_one(dict(session))
    await _update_avg_difficulty(tgid)
    logger.info(f"Diary session created: {session['id']} (tg={tgid}) score={diff['score']}")
    out = _serialize_session(session)
    out["difficulty"] = diff
    return out


@api_router.get("/diary/sessions")
async def diary_list_sessions(from_: Optional[str] = Query(default=None, alias="from"),
                              to: Optional[str] = None, limit: int = 50,
                              current: dict = Depends(get_current_user)):
    tgid = current["telegram_id"]
    docs = await db.workout_sessions.find(
        {"athlete_telegram_id": tgid, "mode": "diary"}, {"_id": 0}
    ).sort("date", -1).to_list(min(200, max(1, limit)))
    fr = _parse_date(from_) if from_ else None
    tt = _parse_date(to) if to else None
    out = []
    for s in docs:
        d = _session_day(s)
        if fr and d and d < fr:
            continue
        if tt and d and d > tt:
            continue
        item = _serialize_session(s)
        if s.get("difficulty_score") is not None:
            item["difficulty"] = {"score": s.get("difficulty_score")}
        out.append(item)
    return out


@api_router.get("/diary/sessions/{session_id}")
async def diary_get_session(session_id: str, current: dict = Depends(get_current_user)):
    s = await db.workout_sessions.find_one({"id": session_id, "mode": "diary"}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    if s.get("athlete_telegram_id") != current["telegram_id"]:
        raise HTTPException(status_code=403, detail="Нет доступа к этой записи")
    return _serialize_session(s)


@api_router.patch("/diary/sessions/{session_id}")
async def diary_update_session(session_id: str, payload: DiarySessionUpdate,
                               current: dict = Depends(get_current_user)):
    s = await db.workout_sessions.find_one({"id": session_id, "mode": "diary"}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    tgid = current["telegram_id"]
    if s.get("athlete_telegram_id") != tgid:
        raise HTTPException(status_code=403, detail="Нет доступа к этой записи")
    profile = await _diary_profile_get(tgid)
    upd = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if payload.date is not None:
        upd["date"] = payload.date
    if payload.title is not None:
        upd["title"] = payload.title[:80]
    if payload.rpe is not None:
        upd["rpe"] = payload.rpe
    if payload.notes is not None:
        upd["notes"] = payload.notes
    if payload.exercises is not None:
        cat = await _diary_catalog(tgid)
        items = [i.model_dump() for i in payload.exercises]
        exs = [_diary_exercise_card(it, idx, cat) for idx, it in enumerate(items)]
        upd["exercises"] = [e for e in exs if e.get("exercise_name")]
    merged = dict(s)
    merged.update(upd)
    diff = _diary_difficulty(merged, profile)
    upd["difficulty_score"] = diff["score"]
    upd["stats"] = _session_stats(merged)
    await db.workout_sessions.update_one({"id": session_id}, {"$set": upd})
    await _update_avg_difficulty(tgid)
    s2 = await db.workout_sessions.find_one({"id": session_id}, {"_id": 0})
    out = _serialize_session(s2)
    out["difficulty"] = diff
    return out


@api_router.delete("/diary/sessions/{session_id}")
async def diary_delete_session(session_id: str, current: dict = Depends(get_current_user)):
    s = await db.workout_sessions.find_one({"id": session_id, "mode": "diary"}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    if s.get("athlete_telegram_id") != current["telegram_id"]:
        raise HTTPException(status_code=403, detail="Нет доступа к этой записи")
    await db.workout_sessions.delete_one({"id": session_id})
    await _update_avg_difficulty(current["telegram_id"])
    return {"ok": True}


# --- ИИ-агент: разбор записи, анализ, недельные советы, чат, генерация -------
_DIARY_PARSE_SCHEMA = ('{"title":"краткое название тренировки","exercises":[{"name":"название по-русски",'
                       '"muscle_group":"legs|chest|back|shoulders|biceps|triceps|core",'
                       '"lift_group":"squat|bench|deadlift или null","is_accessory":false,'
                       '"sets":[{"weight":100.0,"reps":5,"sets":3}]}]}')

_DIARY_PARSE_SYSTEM = (
    "Ты — парсер дневника силовых тренировок. Пользователь описывает, ЧТО он уже сделал "
    "(свободный текст, сокращения, сленг). Извлеки выполненные упражнения и подходы. "
    "Отвечай ТОЛЬКО валидным JSON без markdown, по схеме:\n" + _DIARY_PARSE_SCHEMA +
    "\nПравила:\n"
    "- Понимай форматы гибко: '100х5х3' и '100 5 3' обычно = вес 100кг, 5 повторов, 3 подхода; "
    "'3х8' без веса = 3 подхода по 8 повторов; '80кг 8 8 8' = 3 подхода по 8 с весом 80.\n"
    "- Каждый элемент 'sets' — группа: sets (кол-во подходов) × reps (повторы), weight в кг или null.\n"
    "- lift_group: 'squat' присед, 'bench' жим лёжа, 'deadlift' становая; иначе null.\n"
    "- is_accessory=true только для явно bodyweight-упражнений без внешнего веса.\n"
    "- Не выдумывай упражнения, которых нет в тексте. Названия — общепринятые русские. Компактный JSON.")

_DIARY_COACH_SYSTEM = (
    "Ты — персональный тренер по силовым. Разбери ОДНУ проведённую тренировку кратко и по делу, "
    "как живой тренер (на 'ты', по-русски, без канцелярита). Отвечай ТОЛЬКО валидным JSON по схеме:\n"
    '{"summary":"1-2 предложения общий вердикт","difficulty_comment":"комментарий про нагрузку/сложность",'
    '"good":["что было хорошо (1-3)"],"improve":["что улучшить (1-3)"],'
    '"progression":"конкретный совет по прогрессии на следующий раз для ключевого упражнения",'
    '"next_focus":"на чём сфокусироваться в ближайшие тренировки"}\n'
    "Опирайся на метрики и профиль. Не выдумывай упражнения, которых не было. Компактный JSON.")

_DIARY_WEEKLY_SYSTEM = (
    "Ты — персональный тренер. По недельному объёму нагрузки и профилю дай рекомендации. "
    "Отвечай ТОЛЬКО валидным JSON:\n"
    '{"assessment":"оценка недели 1-2 предложения",'
    '"balance":[{"group":"Ноги|Грудь|Спина|Плечи|Руки|Кор","status":"low|ok|high","note":"кратко"}],'
    '"recommend_exercises":[{"name":"упражнение по-русски",'
    '"muscle_group":"legs|chest|back|shoulders|biceps|triceps|core","reason":"зачем"}],'
    '"advice":"общий совет (отдых/прогрессия/баланс)"}\n'
    "Наука: 10-20 рабочих подходов на группу в неделю, частота 2×/нед. "
    "Рекомендуй 2-4 упражнения под пробелы и цель. Компактный JSON.")

_DIARY_CHAT_SYSTEM = (
    "Ты — персональный тренер по силовым тренировкам в приложении TrainWithBrain. Общайся на 'ты', "
    "по-русски, кратко, дружелюбно и по делу, как опытный тренер. Даёшь практичные советы по тренировкам, "
    "технике, прогрессии, восстановлению. Не ставишь медицинских диагнозов. Учитывай профиль и историю. "
    "Отвечай обычным текстом (не JSON), максимум 1-4 коротких абзаца.")

_DIARY_NEXT_SYSTEM = (
    "Ты — персональный тренер. На основе истории, недельного баланса и целей составь СЛЕДУЮЩУЮ тренировку "
    "(ОДИН день, 5-8 упражнений). Отвечай ТОЛЬКО валидным JSON по схеме:\n"
    '{"title":"название дня","focus":"на что нацелена",'
    '"exercises":[{"name":"по-русски","muscle_group":"legs|chest|back|shoulders|biceps|triceps|core",'
    '"lift_group":"squat|bench|deadlift или null","is_accessory":false,"rest_seconds":120,'
    '"sets":[{"weight":null,"reps":8,"sets":3}]}]}\n'
    "Правила: закрывай пробелы недельного объёма, база в начале, изоляция после; учитывай оборудование "
    "и травмы; вес предлагай в кг или null (пользователь подставит). Компактный JSON.")


def _diary_map_exercises(data_exercises, cat):
    """Маппит массив упражнений из ответа ИИ в формат DiaryExerciseIn (+ каталог)."""
    out = []
    for e in (data_exercises or [])[:30]:
        nm = str(e.get("name") or "").strip()
        if not nm:
            continue
        match = _resolve_catalog_ex(nm, None, cat)
        scheme = _norm_scheme([{"weight": s.get("weight"), "sets": s.get("sets"), "reps": s.get("reps")}
                               for s in (e.get("sets") or [])])
        lg = e.get("lift_group")
        if lg not in ("squat", "bench", "deadlift"):
            lg = None
        has_w = any(s.get("weight") for s in scheme)
        mg = e.get("muscle_group")
        if match and (match.get("muscle_groups") or []):
            mg = match["muscle_groups"][0]
        out.append({
            "name": (match or {}).get("name") or nm,
            "exercise_slug": (match or {}).get("slug"),
            "muscle_group": mg,
            "lift_group": lg,
            "is_accessory": bool(e.get("is_accessory")) and not has_w,
            "rest_seconds": e.get("rest_seconds"),
            "sets_scheme": scheme,
        })
    return out


@api_router.post("/diary/parse")
async def diary_parse(payload: DiaryParseReq, current: dict = Depends(get_current_user)):
    _rate_limit(f"ai:{current['telegram_id']}", 30, 600,
                "Слишком много запросов к ИИ. Попробуйте позже.")
    text = (payload.text or "").strip()
    if len(text) < 3:
        raise HTTPException(status_code=400, detail="Опишите тренировку подробнее")
    _ai_require_enabled()

    async def _factory():
        content = await _ai_chat([
            {"role": "system", "content": _DIARY_PARSE_SYSTEM},
            {"role": "user", "content": f"Запись пользователя (что он сделал на тренировке):\n{text[:4000]}"},
        ], temperature=0.2)
        data = _extract_json(content)
        cat = await _diary_catalog(current["telegram_id"])
        exs = _diary_map_exercises(data.get("exercises"), cat)
        if not exs:
            raise HTTPException(status_code=422, detail="Не удалось распознать упражнения — опишите иначе")
        return {"title": str(data.get("title") or "Тренировка")[:80], "exercises": exs}

    return await _ai_start_job(current, "diary_parse", _factory)


@api_router.post("/diary/analyze")
async def diary_analyze(payload: dict = Body(...), current: dict = Depends(get_current_user)):
    _rate_limit(f"ai:{current['telegram_id']}", 30, 600,
                "Слишком много запросов к ИИ. Попробуйте позже.")
    sid = payload.get("session_id")
    s = await db.workout_sessions.find_one({"id": sid}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    if s.get("athlete_telegram_id") != current["telegram_id"]:
        raise HTTPException(status_code=403, detail="Нет доступа")
    _ai_require_enabled()
    profile = await _diary_profile_get(current["telegram_id"])

    async def _factory():
        st = _get_session_stats(s)
        diff = _diary_difficulty(s, profile)
        exlines = []
        for e in s.get("exercises", []):
            sc = e.get("sets_scheme") or []
            sets_txt = ", ".join(
                f"{x.get('sets')}×{x.get('reps')}" + (f"@{x.get('weight')}кг" if x.get('weight') else "")
                for x in sc) or "—"
            exlines.append(f"- {e.get('exercise_name')} ({e.get('muscle_group') or '—'}): {sets_txt}")
        rel = ""
        if diff.get("vs_avg_28d") is not None:
            sign = "+" if diff["vs_avg_28d"] >= 0 else ""
            rel = f" Относительно среднего за 28д: {sign}{diff['vs_avg_28d']}."
        metrics = (f"Сложность {diff['score']}/100 ({diff['category']}); подходов {st.get('sets_done')}; "
                   f"тоннаж {st.get('tonnage')}кг; группы {st.get('group') or '—'}; RPE {s.get('rpe') or '—'}.{rel}")
        hist = await _recent_sessions_summary(s.get("athlete_telegram_id"), 5)
        content = await _ai_chat([
            {"role": "system", "content": _DIARY_COACH_SYSTEM},
            {"role": "user", "content": f"{_profile_context(profile)}\n\nСЕГОДНЯШНЯЯ ТРЕНИРОВКА:\n"
                                        + "\n".join(exlines)
                                        + f"\n\nМЕТРИКИ: {metrics}\n\nПОСЛЕДНИЕ ТРЕНИРОВКИ:\n{hist}"},
        ], temperature=0.5)
        data = _extract_json(content)
        fb = {
            "summary": str(data.get("summary") or "")[:500],
            "difficulty_comment": str(data.get("difficulty_comment") or "")[:400],
            "good": [str(x)[:200] for x in (data.get("good") or [])[:4]],
            "improve": [str(x)[:200] for x in (data.get("improve") or [])[:4]],
            "progression": str(data.get("progression") or "")[:400],
            "next_focus": str(data.get("next_focus") or "")[:300],
            "difficulty": diff,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.workout_sessions.update_one({"id": s["id"]}, {"$set": {"ai_feedback": fb}})
        return fb

    return await _ai_start_job(current, "diary_analyze", _factory)


@api_router.get("/diary/agent/weekly")
async def diary_agent_weekly(current: dict = Depends(get_current_user)):
    tgid = current["telegram_id"]
    _ai_require_enabled()
    profile = await _diary_profile_get(tgid)
    vol = await _weekly_muscle_volume(tgid, 7)
    vol_txt = ", ".join(f"{g['label']}: {g['sets']} подходов" for g in vol["groups"]) or "нет данных за неделю"
    content = await _ai_chat([
        {"role": "system", "content": _DIARY_WEEKLY_SYSTEM},
        {"role": "user", "content": f"{_profile_context(profile)}\n\n"
                                    f"ОБЪЁМ ЗА 7 ДНЕЙ ({vol['workouts']} тренировок): {vol_txt}."},
    ], temperature=0.5)
    data = _extract_json(content)
    cat = await _diary_catalog(tgid)
    recs = []
    for r in (data.get("recommend_exercises") or [])[:6]:
        nm = str(r.get("name") or "").strip()
        if not nm:
            continue
        match = _resolve_catalog_ex(nm, None, cat)
        recs.append({"name": (match or {}).get("name") or nm, "exercise_slug": (match or {}).get("slug"),
                     "muscle_group": r.get("muscle_group"), "reason": str(r.get("reason") or "")[:200]})
    return {
        "volume": vol,
        "assessment": str(data.get("assessment") or "")[:500],
        "balance": [{"group": str(b.get("group") or ""), "status": b.get("status"),
                     "note": str(b.get("note") or "")[:200]} for b in (data.get("balance") or [])[:8]],
        "recommend_exercises": recs,
        "advice": str(data.get("advice") or "")[:400],
    }


@api_router.get("/diary/agent/chat/{thread_id}")
async def diary_get_chat(thread_id: str, current: dict = Depends(get_current_user)):
    chat = await db.diary_chats.find_one(
        {"thread_id": thread_id, "telegram_id": current["telegram_id"]}, {"_id": 0})
    if not chat:
        return {"thread_id": thread_id, "messages": []}
    return {"thread_id": thread_id, "messages": chat.get("messages") or []}


@api_router.post("/diary/agent/chat")
async def diary_agent_chat(payload: DiaryChatReq, current: dict = Depends(get_current_user)):
    _rate_limit(f"ai:{current['telegram_id']}", 30, 600,
                "Слишком много запросов к ИИ. Попробуйте позже.")
    tgid = current["telegram_id"]
    msg = (payload.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Пустое сообщение")
    _ai_require_enabled()
    profile = await _diary_profile_get(tgid)
    thread_id = payload.thread_id or str(uuid.uuid4())
    chat = await db.diary_chats.find_one({"thread_id": thread_id, "telegram_id": tgid}, {"_id": 0})
    history = (chat or {}).get("messages") or []
    hist_summary = await _recent_sessions_summary(tgid, 5)
    llm_msgs = [{"role": "system", "content": _DIARY_CHAT_SYSTEM + "\n\n" + _profile_context(profile)
                 + f"\n\nПоследние тренировки:\n{hist_summary}"}]
    for m in history[-10:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            llm_msgs.append({"role": m["role"], "content": m["content"]})
    llm_msgs.append({"role": "user", "content": msg[:2000]})
    reply = await _ai_chat(llm_msgs, temperature=0.6, json_mode=False)
    reply = (reply or "").strip() or "Не смог сформулировать ответ, попробуй переформулировать вопрос."
    now = datetime.now(timezone.utc).isoformat()
    new_msgs = history + [
        {"role": "user", "content": msg[:2000], "at": now},
        {"role": "assistant", "content": reply[:4000], "at": now},
    ]
    await db.diary_chats.update_one(
        {"thread_id": thread_id, "telegram_id": tgid},
        {"$set": {"messages": new_msgs[-40:], "updated_at": now},
         "$setOnInsert": {"id": str(uuid.uuid4()), "thread_id": thread_id,
                          "telegram_id": tgid, "created_at": now}},
        upsert=True)
    return {"thread_id": thread_id, "reply": reply}


@api_router.post("/diary/agent/next")
async def diary_agent_next(payload: DiaryNextReq, current: dict = Depends(get_current_user)):
    _rate_limit(f"ai:{current['telegram_id']}", 30, 600,
                "Слишком много запросов к ИИ. Попробуйте позже.")
    _ai_require_enabled()
    tgid = current["telegram_id"]

    async def _factory():
        profile = await _diary_profile_get(tgid)
        vol = await _weekly_muscle_volume(tgid, 7)
        vol_txt = ", ".join(f"{g['label']}: {g['sets']}" for g in vol["groups"]) or "нет данных"
        hist = await _recent_sessions_summary(tgid, 5)
        content = await _ai_chat([
            {"role": "system", "content": _DIARY_NEXT_SYSTEM},
            {"role": "user", "content": f"{_profile_context(profile)}\n\n"
                                        f"Объём за неделю (подходы по группам): {vol_txt}.\n"
                                        f"Последние тренировки:\n{hist}\n\n"
                                        f"Пожелание на сегодня: {(payload.hint or '').strip() or 'на усмотрение тренера'}"},
        ], temperature=0.6)
        data = _extract_json(content)
        cat = await _diary_catalog(tgid)
        exs = _diary_map_exercises(data.get("exercises"), cat)
        if not exs:
            raise HTTPException(status_code=422, detail="Не удалось составить тренировку — попробуйте ещё раз")
        return {"title": str(data.get("title") or "Рекомендованная тренировка")[:80],
                "focus": str(data.get("focus") or "")[:200], "exercises": exs}

    return await _ai_start_job(current, "diary_next", _factory)


# ============================================================================
# NOTIFICATIONS API
# ============================================================================

class NotificationSettings(BaseModel):
    """Настройки уведомлений пользователя"""
    workout_reminders: bool = True
    report_reminders: bool = True
    achievement_notifications: bool = True
    coach_notifications: bool = True
    time_before_workout_minutes: int = 120
    report_reminder_time: str = "20:00"
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "08:00"


@api_router.get("/notifications/settings")
async def get_user_notification_settings(caller: dict = Depends(get_current_user)):
    """Получить настройки уведомлений текущего пользователя"""
    settings = await get_notification_settings(db, caller["telegram_id"])
    return settings


@api_router.patch("/notifications/settings")
async def update_notification_settings(
    updates: NotificationSettings,
    caller: dict = Depends(get_current_user)
):
    """Обновить настройки уведомлений"""
    user_tg = caller["telegram_id"]
    
    update_dict = updates.model_dump()
    update_dict["user_telegram_id"] = user_tg
    update_dict["updated_at"] = datetime.now(timezone.utc)
    
    await db.notification_settings.update_one(
        {"user_telegram_id": user_tg},
        {"$set": update_dict},
        upsert=True
    )
    
    return {"success": True, "settings": update_dict}


@api_router.post("/notifications/test")
async def send_test_notification(caller: dict = Depends(get_current_user)):
    """Отправить тестовое уведомление (проверка работы бота)"""
    user_tg = caller["telegram_id"]
    
    success = await send_test_message(user_tg)
    
    if success:
        return {"success": True, "message": "Тестовое уведомление отправлено"}
    else:
        raise HTTPException(500, "Не удалось отправить уведомление. Проверьте TELEGRAM_BOT_TOKEN")


@api_router.get("/notifications/bot-info")
async def get_telegram_bot_info(caller: dict = Depends(get_current_user)):
    """Получить информацию о боте"""
    info = await get_bot_info()
    
    if info:
        return {
            "bot_username": info.get("username"),
            "bot_name": info.get("first_name"),
            "bot_id": info.get("id")
        }
    else:
        raise HTTPException(500, "Не удалось получить информацию о боте")


@api_router.get("/notifications/scheduler-status")
async def get_notification_scheduler_status(caller: dict = Depends(get_current_user)):
    """Получить статус планировщика"""
    status = get_scheduler_status()
    return status


# ============================================================================
# LIVE STATUS API
# ============================================================================

@api_router.get("/coach/{coach_tg}/clients/live-status")
async def get_clients_live_status(
    coach_tg: int,
    caller: dict = Depends(get_current_user)
):
    """Получить live-статусы всех клиентов тренера"""
    # Проверка прав
    if caller["telegram_id"] != coach_tg:
        raise HTTPException(403, "Access denied")
    
    # Получить всех клиентов (только активные связи)
    links = await db.coach_links.find({"coach_telegram_id": coach_tg, "status": "active"}).to_list(1000)
    athlete_ids = [link["athlete_telegram_id"] for link in links]
    if not athlete_ids:
        return {"clients": []}

    # Последняя сессия за сегодня для каждого — одной агрегацией (было N+1).
    # started_at хранится ISO-строкой, поэтому граница тоже строка.
    today_iso = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    latest_by_athlete = {}
    async for row in db.workout_sessions.aggregate([
        {"$match": {"athlete_telegram_id": {"$in": athlete_ids},
                    "started_at": {"$gte": today_iso}}},
        {"$sort": {"started_at": -1}},
        {"$group": {"_id": "$athlete_telegram_id",
                    "live_status": {"$first": "$live_status"},
                    "status_updated_at": {"$first": "$status_updated_at"}}},
    ]):
        latest_by_athlete[row["_id"]] = row

    users = await db.users.find(
        {"telegram_id": {"$in": athlete_ids}},
        {"_id": 0, "telegram_id": 1, "first_name": 1},
    ).to_list(len(athlete_ids))
    users_by_id = {u["telegram_id"]: u for u in users}

    statuses = []
    for athlete_id in athlete_ids:
        row = latest_by_athlete.get(athlete_id) or {}
        last_updated = row.get("status_updated_at")
        if hasattr(last_updated, "isoformat"):
            last_updated = last_updated.isoformat()
        statuses.append({
            "athlete_telegram_id": athlete_id,
            "first_name": users_by_id.get(athlete_id, {}).get("first_name", "Unknown"),
            "live_status": row.get("live_status") or "idle",
            "last_updated": last_updated,
        })

    return {"clients": statuses}


# ============================================================================
# EXERCISE HISTORY API
# ============================================================================

@api_router.get("/exercises/{slug}/history/{athlete_tg}")
async def get_exercise_history(
    slug: str,
    athlete_tg: int,
    limit: int = 10,
    caller: dict = Depends(get_current_user)
):
    """
    Получить историю выполнения упражнения спортсменом.
    
    Доступно только тренеру этого спортсмена или самому спортсмену.
    """
    # Проверка прав доступа
    is_athlete = caller["telegram_id"] == athlete_tg
    
    if not is_athlete:
        # Проверить что caller - тренер этого спортсмена
        link = await db.coach_links.find_one({
            "coach_telegram_id": caller["telegram_id"],
            "athlete_telegram_id": athlete_tg,
            "status": "active",
        })
        
        if not link:
            raise HTTPException(403, "Access denied: not your client")
    
    # Получить информацию об упражнении
    exercise = await db.exercises.find_one({"slug": slug})
    if not exercise:
        raise HTTPException(404, f"Exercise {slug} not found")
    
    # Найти все завершенные сессии с этим упражнением
    sessions = await db.workout_sessions.find({
        "athlete_telegram_id": athlete_tg,
        "status": "finished",
        "exercises.exercise_slug": slug
    }).sort("finished_at", -1).limit(limit).to_list(limit)
    
    history = []
    max_weight = 0.0
    max_reps = 0
    total_volume = 0.0
    
    for session in sessions:
        for ex in session.get("exercises", []):
            if ex.get("exercise_slug") != slug:
                continue
            
            # Извлечь по-подходный чек-лист факта (set_logs)
            sets = ex.get("set_logs", [])
            
            if not sets:
                continue
            
            # Подсчитать метрики
            session_max_weight = 0.0
            session_max_reps = 0
            session_volume = 0.0
            
            valid_sets = []
            
            for set_data in sets:
                weight = set_data.get("weight")
                reps = set_data.get("reps")
                # Схема SetLog: done=True — выполнен, skipped=True — пропущен.
                if set_data.get("skipped") or not set_data.get("done", False):
                    continue
                
                if weight is not None:
                    session_max_weight = max(session_max_weight, float(weight))
                    max_weight = max(max_weight, float(weight))
                
                if reps is not None:
                    session_max_reps = max(session_max_reps, int(reps))
                    max_reps = max(max_reps, int(reps))
                
                # Объем = вес × повторения
                if weight and reps:
                    volume = float(weight) * int(reps)
                    session_volume += volume
                    total_volume += volume
                
                valid_sets.append({
                    "weight": weight,
                    "reps": reps,
                    "completed": True,
                })
            
            if not valid_sets:
                continue
            
            finished = session.get("finished_at")
            if isinstance(finished, str):
                finished = finished.split("T")[0]
            elif hasattr(finished, "date"):
                finished = finished.date().isoformat()
            history.append({
                "date": finished or session.get("date"),
                "session_id": session["id"],
                "session_title": session.get("title", ""),
                "sets": valid_sets,
                "max_weight": session_max_weight,
                "max_reps": session_max_reps,
                "total_volume": session_volume
            })
    
    # Рассчитать 1RM (одноповторный максимум) по формуле Brzycki
    # 1RM = weight × (36 / (37 - reps))
    one_rm = 0.0
    if history:
        for entry in history:
            for set_data in entry["sets"]:
                weight = set_data.get("weight")
                reps = set_data.get("reps")
                
                if weight and reps and reps > 0 and reps < 37:
                    calculated_1rm = float(weight) * (36 / (37 - int(reps)))
                    one_rm = max(one_rm, calculated_1rm)
    
    return {
        "slug": slug,
        "exercise_name": exercise.get("name"),
        "athlete_telegram_id": athlete_tg,
        "last_performed": history[0]["date"] if history else None,
        "max_weight": max_weight,
        "max_reps": max_reps,
        "estimated_1rm": round(one_rm, 1) if one_rm else None,
        "total_volume": round(total_volume, 1),
        "history": history
    }


# Include the router in the main app
app.include_router(api_router)


# ===========================================================================
# P4 — WebSocket endpoint (/api/ws). Префикс /api обязателен для ingress.
# ===========================================================================
async def _authenticate_ws_token(token: Optional[str]) -> Optional[dict]:
    """Валидация session-token (как Bearer) для WebSocket-хендшейка."""
    if not token:
        return None
    sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not sess:
        return None
    exp = sess.get("expires_at")
    if isinstance(exp, str):
        try:
            exp = datetime.fromisoformat(exp)
        except Exception:
            exp = None
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and exp < datetime.now(timezone.utc):
        return None
    return await db.users.find_one(
        {"telegram_id": sess["telegram_id"]}, {"_id": 0, "password_hash": 0}
    )


@app.websocket("/api/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None),
    init_data: Optional[str] = Query(default=None),
):
    # 1. Аутентификация: session-token (web/PWA/Telegram) или Telegram initData
    user = await _authenticate_ws_token(token)
    if not user and init_data:
        parsed = validate_telegram_init_data(init_data, TELEGRAM_BOT_TOKEN)
        if parsed:
            tu = parse_telegram_user(parsed)
            if tu and tu.get("id"):
                user = await db.users.find_one(
                    {"telegram_id": tu["id"]}, {"_id": 0, "password_hash": 0}
                )
    if not user:
        await websocket.close(code=4401)  # 4401 — неавторизован
        return

    await websocket.accept()
    tgid = user["telegram_id"]
    name = user.get("first_name") or "Пользователь"
    await manager.register(websocket, tgid, name)
    await manager.join(websocket, f"user:{tgid}")
    await manager.send_personal(websocket, {
        "type": "connected", "room": f"user:{tgid}",
        "payload": {"telegram_id": tgid, "name": name}, "ts": rt_now(),
    })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mtype = msg.get("type")
            if mtype == "ping":
                await manager.send_personal(websocket, {"type": "pong", "ts": rt_now()})
            elif mtype == "subscribe":
                plan_id = msg.get("plan_id")
                if plan_id and await _can_access_plan(tgid, plan_id):
                    room = f"plan:{plan_id}"
                    await manager.join(websocket, room)
                    online = manager.presence(room)
                    await manager.send_personal(websocket, {
                        "type": "presence", "room": room,
                        "payload": {"online": online}, "ts": rt_now(),
                    })
                    await manager.broadcast(room, "presence", {"online": online}, exclude=websocket)
            elif mtype == "unsubscribe":
                plan_id = msg.get("plan_id")
                if plan_id:
                    room = f"plan:{plan_id}"
                    await manager.leave(websocket, room)
                    await manager.broadcast(room, "presence", {"online": manager.presence(room)})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"websocket loop error: {e}")
    finally:
        rooms = await manager.disconnect(websocket)
        for room in rooms:
            if room.startswith("plan:"):
                await manager.broadcast(room, "presence", {"online": manager.presence(room)})


# CORS middleware is now added right after app creation (before routes)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_seed():
    """Идемпотентно создаёт индексы и встроенные данные (упражнения + шаблоны программ)."""
    try:
        await ensure_indexes(db)
    except Exception as e:
        logger.warning(f"ensure_indexes failed: {e}")
    try:
        await ensure_auth_indexes(db)
    except Exception as e:
        logger.warning(f"ensure_auth_indexes failed: {e}")
    try:
        res = await seed_builtins(db)
        logger.info(f"Seed builtins complete: {res}")
    except Exception as e:
        logger.warning(f"seed_builtins failed: {e}")
    # Фаза 1 — grandfathering legacy-пользователей (доступ без повторного инвайта).
    try:
        await ensure_phase1_backfill(db)
    except Exception as e:
        logger.warning(f"ensure_phase1_backfill failed: {e}")
    # Миграция: заполнить weight_type для существующих упражнений без него
    try:
        r1 = await db.exercises.update_many(
            {"weight_type": {"$exists": False}, "equipment": "bodyweight"},
            {"$set": {"weight_type": "bodyweight"}},
        )
        r2 = await db.exercises.update_many(
            {"weight_type": {"$exists": False}},
            {"$set": {"weight_type": "kg"}},
        )
        if r1.modified_count or r2.modified_count:
            logger.info(f"weight_type backfill: bw={r1.modified_count}, kg={r2.modified_count}")
    except Exception as e:
        logger.warning(f"weight_type backfill failed: {e}")
    
    # Инициализация планировщика уведомлений
    try:
        init_scheduler(db)
        start_scheduler()
        logger.info("Notification scheduler started successfully")
    except Exception as e:
        logger.error(f"Failed to start notification scheduler: {e}")


@app.on_event("shutdown")
async def shutdown_services():
    """Graceful shutdown всех сервисов"""
    try:
        stop_scheduler()
        logger.info("Notification scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")
    
    client.close()
    logger.info("MongoDB client closed")