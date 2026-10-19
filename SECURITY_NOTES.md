# Замечания по безопасности

## Критические действия

### 1. Telegram Bot Token
**Статус:** 🔴 КРИТИЧНО

Файл `backend/.env` содержит хардкод токена бота:
```
TELEGRAM_BOT_TOKEN=8483056076:AAHGZHKKx4cYgbzK3oPB435dcJ4hEiDUBBU
```

**Необходимые действия:**
1. Немедленно отозвать токен через [@BotFather](https://t.me/BotFather):
   - Отправьте `/mybots`
   - Выберите бота
   - Bot Settings → Revoke token
2. Создать новый токен
3. Обновить `backend/.env` локально (не коммитить!)
4. Использовать переменные окружения на сервере

### 2. .env в .gitignore
**Статус:** ✅ ИСПРАВЛЕНО

Добавлены правила в `.gitignore`:
```gitignore
.env
.env.*
!.env.example
backend/.env
frontend/.env
```

### 3. CORS Origins
**Статус:** ⚠️ ТРЕБУЕТ ВНИМАНИЯ

Текущая конфигурация в `backend/.env`:
```
CORS_ORIGINS="*"
```

**Рекомендация:** Ограничить список доменов в production:
```
CORS_ORIGINS="http://localhost:3000,https://yourdomain.com,https://preview.yourdomain.com"
```

Создан `backend/.env.example` с безопасными значениями по умолчанию.

## Рекомендации

### Rate Limiting
Отсутствует защита от DDoS и брутфорса. Рекомендуется добавить:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@api_router.post("/auth/login")
@limiter.limit("5/minute")
async def login(request: Request, ...):
    ...
```

### Логирование
Добавлено логирование критических ошибок:
- AI service failures (server.py:3618, 3624)
- Telegram Bot API failures (server.py:267, 681)

### База данных
Добавлены недостающие индексы для производительности и безопасности:
- `user_sessions.token` (unique) — аутентификация
- `user_sessions.expires_at` (TTL) — автоудаление сессий
- `users.email` (unique, sparse) — OAuth
- `coach_links.coach_telegram_id` — запросы тренера
- `diary_chats.user_telegram_id` — дневник

## Проверка перед деплоем

- [ ] Отозван старый Telegram Bot Token
- [ ] Создан новый токен и добавлен в переменные окружения сервера
- [ ] CORS ограничен конкретными доменами
- [ ] `.env` файлы не коммитятся в репозиторий
- [ ] Проверены права доступа к MongoDB (не используется публичный доступ)
- [ ] Включён HTTPS на production
- [ ] Настроен rate limiting для критических эндпоинтов
