# Развёртывание TrainWithBrain на VPS + DeepSeek Harness

Полная инструкция: от аренды сервера до рабочего `https://trainwbrain.ru`, dev-окружения
и браузерного DeepSeek Harness для разработки прямо на сервере.

> Проверено по коду проекта: React 19 (CRA/CRACO) + FastAPI + MongoDB, WebSocket `/api/ws`,
> Telegram Mini App, ИИ-разбор программ через OpenAI-совместимый API.
> Всё, что ниже, учитывает реальные особенности этого репозитория (см. пометки «почему так»).

---

## Содержание

1. [Какой сервер брать (бюджет и конфигурация)](#1-какой-сервер-брать)
2. [Схема: домены, порты, процессы](#2-схема-домены-порты-процессы)
3. [Домен и DNS](#3-домен-и-dns)
4. [Первичная настройка сервера](#4-первичная-настройка-сервера)
5. [Код проекта на сервере](#5-код-проекта-на-сервере)
6. [Backend (FastAPI)](#6-backend-fastapi)
7. [Frontend (React)](#7-frontend-react)
8. [Nginx + HTTPS](#8-nginx--https)
9. [Telegram Mini App](#9-telegram-mini-app)
10. [Режим разработки на сервере](#10-режим-разработки-на-сервере)
11. [DeepSeek Harness](#11-deepseek-harness)
12. [Эксплуатация: логи, обновления, бэкапы](#12-эксплуатация)
13. [Безопасность](#13-безопасность)
14. [Troubleshooting](#14-troubleshooting)
15. [Бюджет: сколько это стоит](#15-бюджет)
16. [Финальный чек-лист](#16-финальный-чек-лист)

Готовые конфиги лежат в каталоге [`deploy/`](deploy/) — их не нужно набирать руками.

---

## 1. Какой сервер брать

### 1.1 VPS или VDS?

Для вашей задачи это одно и то же: виртуальная машина с KVM. «VDS» обычно маркетинговое
название «выделенных» ресурсов. Важно другое:

- **только KVM** (не OpenVZ/LXC) — MongoDB и сборки Node любят нормальный диск и память;
- **NVMe/SSD**, не HDD;
- **Ubuntu 24.04 LTS** — на ней проверены все команды ниже (см. 1.1.1);
- IPv4 включён в тариф;
- снапшоты/бэкапы доступны в панели.

> ⚠️ **Не путайте VPS с виртуальным хостингом.** Тарифы вида `WEB-25 / WEB-50 / WEB-75 /
> WEB-100` (cPanel, CloudLinux-изоляция, «N сайтов», «8 ядер / 4 ГБ») — это **shared-хостинг**,
> а не VPS. Там нет root, нельзя поставить MongoDB и свои демоны (uvicorn, CRA dev server,
> `dsh web`), обычно недоступны WebSocket и произвольные порты. Для этого проекта нужен
> именно VPS/VDS с root-доступом и KVM — даже если у shared-тарифа «больше ядер».

### 1.1.1 Какую ОС выбрать

| Вариант | Вердикт |
|---|---|
| **Ubuntu 24.04 LTS «Noble Numbat»** | ✅ **рекомендую.** Python 3.12 (как в рабочем окружении проекта), официальный apt-репозиторий MongoDB 8.0 (`noble`), nginx 1.24, поддержка до 2029 |
| Ubuntu 26.04 LTS «Resolute Raccoon» | ⚠️ можно, но с переделками: Python 3.14 и нет пакетов MongoDB под кодовое имя `resolute` — MongoDB придётся ставить в Docker, а часть пинов backend может собираться из исходников |
| Ubuntu 26.10 «Stonking Stingray» | ❌ не-LTS, поддержка 9 месяцев — для сервера не годится |
| Ubuntu 22.04 «Jammy Jellyfish» | 🟡 работает, но Python 3.10 и старый nginx; смысла нет — EOL ближе |

Ключевой аргумент — MongoDB: в инструкции она ставится из официального репозитория по
кодовому имени дистрибутива (`noble`), а под `resolute` пакетов пока нет. Плюс Python 3.12
на 24.04 совпадает с версией, под которую сняты зависимости backend.

В панели выбирайте образ **без панели управления** (не ISPmanager/Plesk/cPanel) и, если есть,
«minimal/cloud image». Архитектура — x86_64.

### 1.2 Рекомендуемая конфигурация

**Берите 4 vCPU / 8 ГБ RAM / 80 ГБ NVMe.** Это «бюджетно, но комфортно» именно для этого
проекта: на сервере одновременно живут MongoDB, FastAPI, CRA dev server (webpack),
сборка фронтенда и DeepSeek Harness.

| Вариант | vCPU | RAM | Диск | Ориентир по цене* | Кому |
|---|---|---|---|---|---|
| Минимум | 2 | 4 ГБ | 60 ГБ | ~600–1000 ₽/мес | сборки медленные, dev server + сборка могут упираться в swap |
| **Комфорт (рекомендую)** | **4** | **8 ГБ** | **80 ГБ** | **~1200–2000 ₽/мес** | всё помещается с запасом, сборка фронта 3–6 мин |
| С запасом | 6–8 | 12–16 ГБ | 120–160 ГБ | ~2200–3500 ₽/мес | если будете держать несколько окружений/команд |

\* Ориентир по российским провайдерам на момент написания. Цены меняются — сверяйтесь
в панели провайдера.

Если денег впритык — можно 2/4/60, но **обязательно добавьте 4 ГБ swap** (это делает
`deploy/scripts/bootstrap.sh`). Тогда сборка не будет падать по OOM, просто станет медленнее.

Если у провайдера нет ровно 8 ГБ, допустимая замена — **4 vCPU / 6 ГБ / 70 ГБ NVMe + 6 ГБ swap**:
сборка и DSH потянут, но на время `yarn build` лучше останавливать dev-сервер
(`sudo systemctl stop twb-frontend-dev`), иначе память уйдёт в swap.

Если сервер всего **2 ГБ RAM / 30 ГБ** (например, тариф «Мидл» 2/2/30) — работать можно,
но с дисциплиной:

- swap **4 ГБ** обязателен (bootstrap его и создаёт);
- MongoDB: ограничить кэш `cacheSizeGB: 0.25` (команда в разделе 6.2.1);
- прод-сборку фронтенда делать **локально** и загружать `build/` (раздел 7.6);
- `twb-frontend-dev` и `dsh-web` не держать включёнными одновременно, на время сборки — стоп.

### 1.3 Почему именно столько (реальный расход)

| Компонент | RAM (примерно) |
|---|---|
| Ubuntu + systemd + journald | 250–400 МБ |
| MongoDB 8 | 300–600 МБ |
| FastAPI (прод) | 250–400 МБ |
| FastAPI dev (`--reload`) | +100 МБ |
| CRA dev server (webpack watch) | 1.2–2.5 ГБ |
| Сборка `yarn build` (пик) | 2–3 ГБ |
| DeepSeek Harness (`dsh web`) | 300–700 МБ |
| nginx | 30–80 МБ |

В спокойном состоянии с включённым dev-сервером и DSH — около 4–5 ГБ. Пик при сборке
фронтенда вместе с dev-сервером — 6–7 ГБ. Поэтому 8 ГБ = комфорт, 4 ГБ = «на грани» (нужен swap).

**Диск.** `node_modules` фронтенда ~1.5–2 ГБ, Python venv ~500 МБ, глобальный npm + DSH
~500 МБ–1 ГБ, кэши ~1 ГБ, MongoDB с данными < 1 ГБ, ОС ~5 ГБ. Итого ~10–12 ГБ;
40 ГБ — минимум, 80 ГБ — с местом под бэкапы, снапшоты и эксперименты.

**CPU.** Сборка CRA хорошо параллелится: 4 vCPU дают заметно более короткую сборку и
отзывчивый dev server. 2 vCPU рабочие, но `yarn build` будет идти 8–12 минут.

**Трафик.** 1 ТБ/мес в тарифе более чем достаточно (Mini App лёгкий, фото уходят в API).

### 1.4 Провайдеры (РФ)

Порядок — примерный, все берут карты РФ и дают KVM + NVMe:

| Провайдер | Плюсы | Замечания |
|---|---|---|
| Timeweb Cloud | дешёвые тарифы, снапшоты, Москва/СПб | самый очевидный «бюджетный» выбор |
| Beget | стабильная панель, бэкапы | цены чуть выше |
| reg.ru | рядом с доменом, если он там же | дороже на том же железе |
| VDSina | дешёвые NVMe-тарифы | проверяйте локацию |
| FirstVDS | предсказуемый RU-хостинг | средние цены |
| Aeza | очень дешёвые тарифы, RU/зарубеж | юрисдикция/поддержка — читайте условия |
| Selectel | надёжность, «взрослый» хостинг | дороже на 30–50% |
| Hostkey / PQ.Hosting / Cloud4Y | альтернативы | сравнивайте по цене за 8 ГБ |

**Локация:** Москва или Санкт-Петербург — минимальная задержка для пользователей в РФ и
нормальный доступ к Telegram Bot API и `api.deepseek.com`. Зарубежные Hetzner/Contabo
дешевле, но оплата из РФ и латентность — отдельная головная боль; для старта не нужны.

### 1.5 Что отметить в панели при заказе

- ОС: **Ubuntu 24.04 LTS** (чистая, без панелей ISPmanager/Plesk — они не нужны и едят RAM);
- IPv4: 1 шт.;
- SSH-ключ: можно сразу добавить свой публичный ключ (тогда пароль root не понадобится);
- снапшоты: включить, если стоят 100–300 ₽/мес — сильно упрощает жизнь;
- защита от DDoS: обычно уже есть на уровне сети.

---

## 2. Схема: домены, порты, процессы

```
Интернет
   │  80/443 (только эти порты открыты наружу)
   ▼
 nginx  ──►  /opt/trainwbrain/frontend/build   (статика React, прод)
   │
   ├──►  127.0.0.1:8000  FastAPI прод        (systemd: twb-backend)
   ├──►  127.0.0.1:8001  FastAPI dev --reload (systemd: twb-backend-dev)
   ├──►  127.0.0.1:3000  CRA dev server       (systemd: twb-frontend-dev)
   └──►  127.0.0.1:3080  DeepSeek Harness     (systemd --user: dsh-web)

 127.0.0.1:27017 MongoDB  (наружу НЕ открыт)
```

| Домен | Куда | Обязателен |
|---|---|---|
| `trainwbrain.ru` | nginx: статика + `/api/` | да |
| `www.trainwbrain.ru` | редирект на без-www | желательно |
| `dev.trainwbrain.ru` | dev-фронтенд (3000) | опционально (можно SSH-туннель) |
| `dsh.trainwbrain.ru` | DeepSeek Harness (3080) | опционально (можно SSH-туннель) |

Все внутренние сервисы слушают только `127.0.0.1`. Наружу смотрит только nginx.
Это главный принцип безопасности этой схемы.

---

## 3. Домен и DNS

Домен `trainwbrain.ru` у вас уже есть. Нужно добавить A-записи у регистратора
(или в DNS-панели, если DNS делегирован, например, на Yandex DNS).

### 3.1 Записи

| Тип | Имя | Значение | TTL |
|---|---|---|---|
| A | `@` | `<IP сервера>` | 300 |
| A | `www` | `<IP сервера>` | 300 |
| A | `dev` | `<IP сервера>` | 300 (если нужен dev-поддомен) |
| A | `dsh` | `<IP сервера>` | 300 (если нужен DSH-поддомен) |

TTL 300 на время настройки, потом можно 3600.

### 3.2 Проверка

С Windows:

```powershell
nslookup trainwbrain.ru 8.8.8.8
nslookup www.trainwbrain.ru 8.8.8.8
```

Должен вернуться IP вашего сервера. Обновление DNS занимает от 1 минуты до пары часов
(зависит от TTL старых записей).

### 3.3 Если используете Cloudflare

На время первичной настройки **выключите оранжевую тучку** (DNS only), иначе:
- HTTP-01 проверка Let's Encrypt может не пройти;
- WebSocket/HMR потребуют отдельной настройки.

После настройки можно включить прокси, но тогда проверьте, что WebSocket работает.

---

## 4. Первичная настройка сервера

### 4.1 Первый вход

```powershell
ssh root@<IP>
```

Если провайдер прислал пароль — введите его. Сразу после входа:

```bash
apt update && apt upgrade -y
timedatectl set-timezone Europe/Moscow
```

### 4.2 Пользователь `deploy` и SSH-ключи

На **Windows** (если ключа ещё нет):

```powershell
ssh-keygen -t ed25519 -C "trainwbrain-vps"
# Enter, Enter, Enter (или задайте passphrase)
```

На **сервере** (root):

```bash
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
```

Скопируйте публичный ключ. На Windows:

```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh root@<IP> "mkdir -p /home/deploy/.ssh && cat >> /home/deploy/.ssh/authorized_keys && chown -R deploy:deploy /home/deploy/.ssh && chmod 700 /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys"
```

Проверьте вход **в новом окне** (старое с root не закрывайте):

```powershell
ssh deploy@<IP>
sudo -v
```

### 4.3 Ужесточение SSH

На сервере:

```bash
sudo tee /etc/ssh/sshd_config.d/99-hardening.conf >/dev/null <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
MaxAuthTries 5
EOF

sudo sshd -t && sudo systemctl reload ssh
```

> Сначала убедитесь, что вход по ключу под `deploy` работает, и только потом
> перезагружайте SSH. Иначе можно остаться без доступа.

### 4.4 Один скрипт: пакеты, swap, firewall, Node, MongoDB, nginx

Сначала скопируйте каталог `deploy/` на сервер (полный репозиторий склонируем в разделе 5):

```powershell
scp -r deploy deploy@<IP>:/tmp/twb-deploy
```

Затем на сервере:

```bash
sudo bash /tmp/twb-deploy/scripts/bootstrap.sh
```

Что делает [`deploy/scripts/bootstrap.sh`](deploy/scripts/bootstrap.sh):

- часовой пояс, обновление пакетов;
- базовые пакеты (`git`, `build-essential`, `nginx`, `certbot`, `ripgrep`, `ufw`, `fail2ban`…);
- swap 4 ГБ (важно для сборок);
- автообновления безопасности;
- Node.js 24 LTS (NodeSource), `yarn@1.22.22`, `@deepseek-ai/dsh`;
- MongoDB 8.0 (официальный репозиторий), включённый `mongod`;
- firewall: открыты только 22/80/443;
- fail2ban.

Если скрипт ещё не на сервере — выполните шаги вручную по содержимому файла,
порядок команд там линейный.

Проверка:

```bash
node -v          # v24.x
yarn -v          # 1.22.22
dsh --version    # 0.2.1-rc.2
mongod --version # 8.0.x
systemctl is-active mongod nginx
sudo ufw status
```

### 4.5 Удобный SSH-конфиг с туннелями (Windows)

Создайте/дополните `C:\Users\<вы>\.ssh\config`:

```
Host twb
    HostName <IP>
    User deploy
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 30
    LocalForward 3000 127.0.0.1:3000
    LocalForward 8001 127.0.0.1:8001
    LocalForward 3080 127.0.0.1:3080
```

Теперь `ssh twb` — это shell на сервере, а пока сессия открыта, у вас локально доступны
`http://localhost:3000` (dev-фронтенд), `http://localhost:8001` (dev-backend) и
`http://127.0.0.1:3080` (DeepSeek Harness). Ничего из этого не торчит в интернет.

### 4.6 Проверка MongoDB

```bash
mongosh --quiet --eval 'db.runCommand({ping:1})'
# { ok: 1 }
```

MongoDB по умолчанию слушает `127.0.0.1:27017` — наружу не открыт, это правильно.

Опционально — включить авторизацию:

```bash
mongosh admin --eval 'db.createUser({user:"twb", pwd:"<сильный-пароль>", roles:[{role:"readWrite", db:"trainwbrain_db"}]})'
sudo sed -i 's/^#security:/security:/' /etc/mongod.conf
sudo tee -a /etc/mongod.conf >/dev/null <<'EOF'
security:
  authorization: enabled
EOF
sudo systemctl restart mongod
```

Тогда в `backend/.env`:

```env
MONGO_URL="mongodb://twb:<сильный-пароль>@127.0.0.1:27017/trainwbrain_db?authSource=admin"
```

---

## 5. Код проекта на сервере

Рекомендуемый вариант — приватный репозиторий на GitHub (или GitVerse/GitFlic).
Это даёт историю, откаты и возможность работать с двух машин.

### 5.1 Починить локальный git и запушить

В этом рабочем каталоге `.git/config` повреждён (файл из пробелов/NUL — `git status`
падает с `fatal: bad config line 1`). История в `.git/objects` при этом цела. Лечится так
(Windows PowerShell, из корня проекта):

```powershell
Remove-Item .git\config
git init
git add -A
git commit -m "TrainWithBrain: initial commit for VPS deploy"
```

Создайте **приватный** репозиторий на GitHub и добавьте remote:

```powershell
git remote add origin git@github.com:<ваш-логин>/trainwbrain.git
git branch -M main
git push -u origin main
```

`.gitignore` уже исключает `node_modules/`, `build/`, `.env`, `.env.*`, `_mongo/` —
секреты и мусор в репозиторий не попадут.

### 5.2 Клонирование на сервер

```bash
sudo mkdir -p /opt/trainwbrain
sudo chown deploy:deploy /opt/trainwbrain

# ключ для доступа к репозиторию (от пользователя deploy)
ssh-keygen -t ed25519 -C "twb-vps" -f ~/.ssh/github_twb -N ""
cat ~/.ssh/github_twb.pub
```

Публичный ключ добавьте в GitHub → репозиторий → **Settings → Deploy keys → Add deploy key**
(поставьте галочку «Allow write access», если хотите пушить изменения с сервера).

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_twb
    IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config

git clone git@github.com:<ваш-логин>/trainwbrain.git /opt/trainwbrain
cd /opt/trainwbrain && git log --oneline -1
```

### 5.3 Вариант без GitHub (rsync)

С Windows (Git Bash или WSL):

```bash
rsync -avz --progress \
  --exclude node_modules --exclude .git --exclude build \
  --exclude _mongo --exclude .mongodb_data --exclude __pycache__ \
  ./ deploy@<IP>:/opt/trainwbrain/
```

Минус: нет истории и удобных откатов. Для «продолжить разработку на сервере» лучше git.

### 5.4 Секреты

Файлы `.env` в репозиторий не попадают. Перенесите их отдельно:

```powershell
scp backend\.env.local deploy@<IP>:/opt/trainwbrain/backend/.env.local
```

или создайте на сервере вручную (раздел 6.2). Сразу выставьте права:

```bash
chmod 600 /opt/trainwbrain/backend/.env /opt/trainwbrain/backend/.env.local 2>/dev/null || true
```

---

## 6. Backend (FastAPI)

### 6.1 Виртуальное окружение и зависимости

```bash
cd /opt/trainwbrain/backend
python3 -m venv .venv
.venv/bin/pip install -U pip wheel
.venv/bin/pip install -r /opt/trainwbrain/deploy/requirements.server.txt
```

> **Почему не `backend/requirements.txt`.** В нём есть пакеты из облака Emergent
> (`litellm` со ссылкой на `customer-assets.emergentagent.com` и `emergentintegrations`),
> которые снаружи недоступны — установка упадёт. При этом ни один файл backend их не
> импортирует. [`deploy/requirements.server.txt`](deploy/requirements.server.txt) содержит
> только реально используемые зависимости с версиями из рабочего окружения проекта.

Проверка синтаксиса (не выполняет код, поэтому можно до создания `.env`):

```bash
.venv/bin/python -m py_compile server.py models.py auth.py seed.py realtime.py scheduler.py notifications.py telegram_bot.py
echo "syntax OK"
```

> Если какая-то версия из `requirements.server.txt` не находится в PyPI —
> уберите пин у этого пакета (`fastapi` вместо `fastapi==...`) и переустановите.
> Версии в файле сняты с рабочего окружения проекта, а не из устаревшего
> `backend/requirements.txt`.

### 6.2 `backend/.env`

```bash
cd /opt/trainwbrain/backend
cp /opt/trainwbrain/deploy/env/backend.env.example .env
nano .env
chmod 600 .env
```

Минимум, что нужно заполнить:

```env
MONGO_URL="mongodb://127.0.0.1:27017"
DB_NAME="trainwbrain_db"
CORS_ORIGINS="https://trainwbrain.ru,https://www.trainwbrain.ru"
TELEGRAM_BOT_TOKEN="<токен из BotFather>"
COOKIE_SECURE=true
TRUST_PROXY_HEADERS=true
AI_BASE_URL="https://api.deepseek.com/v1"
AI_API_KEY="<ключ>"
AI_MODEL="deepseek-chat"
```

Важные нюансы:

- **`CORS_ORIGINS`** — точные origin'ы фронтенда, без слэша в конце. `*` не используйте:
  при `allow_credentials=True` браузер такой ответ отвергнет.
- **`.env.local`** рядом с `.env` загружается с `override=true` и побеждает `.env`.
  Если перенесли `.env.local` — правьте секреты там, либо удалите его и держите всё в `.env`.
- **ИИ**: код делает `POST {AI_BASE_URL}/chat/completions`. Официальный DeepSeek:
  `https://api.deepseek.com/v1` + `deepseek-chat`. Если локально вы используете RouterAI —
  просто перенесите его `AI_BASE_URL`/`AI_MODEL`/`AI_API_KEY`.
- **Vision** (фото программ/кардио) — отдельные `AI_VISION_*`. Без них работает всё,
  кроме распознавания фото (эндпоинт вернёт «ИИ не настроен»).

### 6.2.1 Мало RAM? Урезаем MongoDB

На сервере с 2 ГБ RAM (тариф 2/2/30) MongoDB по умолчанию берёт под кэш до половины памяти —
лучше ограничить. В `/etc/mongod.conf`:

```bash
sudo tee -a /etc/mongod.conf >/dev/null <<'EOF'
storage:
  wiredTiger:
    engineConfig:
      cacheSizeGB: 0.25
EOF
sudo systemctl restart mongod
mongosh --quiet --eval 'db.serverStatus().wiredTiger.cache["maximum bytes configured"]/1024/1024 + " MB cache"'
# ~256 MB cache
```

Важно: `storage:` в YAML уже может быть объявлен — если `mongod` не стартует с
`duplicate key`, добавьте только блок `wiredTiger` внутрь существующей секции `storage`
(проверьте `sudo mongod --config /etc/mongod.conf --test` перед рестартом).

### 6.3 systemd-сервис

```bash
sudo cp /opt/trainwbrain/deploy/systemd/twb-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now twb-backend
systemctl status twb-backend --no-pager
```

Проверка:

```bash
curl -s http://127.0.0.1:8000/api/
# {"message":"Hello World"}
```

Логи:

```bash
journalctl -u twb-backend -f
```

### 6.4 Почему `--workers 1`

В [`backend/realtime.py`](backend/realtime.py) WebSocket-комнаты хранятся **в памяти
процесса**, а в `@app.on_event("startup")` запускается APScheduler. Если поставить
`--workers 2+`, тренер и спортсмен могут попасть в разные процессы — live-синхронизация
сломается, а уведомления начнут дублироваться. Для этого приложения один воркер —
правильная конфигурация; нагрузки Mini App он держит с запасом.

---

## 7. Frontend (React)

### 7.1 Зависимости

```bash
cd /opt/trainwbrain/frontend
yarn install --frozen-lockfile
```

> Пакеты фронтенда ставятся **только yarn** (правило проекта), не npm.
> Первая установка — 3–6 минут, ~1.5–2 ГБ на диске.

### 7.2 Прод-переменные

```bash
cd /opt/trainwbrain/frontend
cp /opt/trainwbrain/deploy/env/frontend.env.production.example .env.production
```

`frontend/.env.production`:

```env
REACT_APP_BACKEND_URL=https://trainwbrain.ru
WDS_SOCKET_PORT=443
ENABLE_HEALTH_CHECK=false
```

CRA **вшивает** `REACT_APP_*` в бандл на этапе сборки. Поэтому:

- меняете URL backend — нужен **ребилд**, не просто рестарт;
- секретов в этих переменных быть не может — они видны каждому посетителю.

`frontend/.env` в репозитории нет (он в `.gitignore`). Для прода используется
`.env.production` (приоритетнее `.env`), для dev на сервере создаётся
`.env.development` — см. раздел 10.3.

### 7.3 Сборка

```bash
yarn build
ls -la build/index.html
```

Сборка на 4 vCPU — 3–6 минут, пик RAM 2–3 ГБ. Если упало с `Killed`/`heap out of memory` —
см. [Troubleshooting](#14-troubleshooting).

> На сервере с 2 ГБ RAM собирать здесь не стоит (уйдёт в swap и будет очень долго).
> Собирайте локально и загружайте готовый `build/` — раздел 7.6.

### 7.4 Перед продом: убрать скрипты Emergent (рекомендую)

В [`frontend/public/index.html`](frontend/public/index.html) остались скрипты визуального
редактора Emergent: `https://assets.emergent.sh/scripts/emergent-main.js` и блок
visual-edits для iframe (он грузит Tailwind CDN и debug-monitor). На проде они не нужны,
тянут сторонний код и могут мешать (в Telegram Web приложение открывается в iframe —
условие `window.self !== window.top` там истинно).

Рекомендуется:

1. удалить `<script src="https://assets.emergent.sh/scripts/emergent-main.js"></script>`;
2. удалить блок `if (window.self !== window.top) { ... }` с debug-monitor и Tailwind CDN;
3. скрипт `telegram.org/js/telegram-web-app.js` — **оставить** (без него нет Telegram WebApp);
4. PostHog-сниппет — на ваше усмотрение (аналитика, шлёт данные в US).

После правок — `yarn build` заново.

### 7.5 Service worker

В проекте регистрируется service worker (`src/index.js` → `serviceWorkerRegistration`).
После нового деплоя пользователь может увидеть старую версию до перезагрузки.
В nginx-конфиге `service-worker.js` отдаётся с `Cache-Control: no-cache`, этого достаточно;
при проверках делайте Hard Reload (Ctrl+Shift+R).

### 7.6 Сборка на слабом сервере: собираем локально (для 2 ГБ RAM)

На тарифе 2/2/30 сборка CRA на сервере будет уходить в swap и займёт очень долго,
а dev-сервер рядом просто не оставит памяти. Рабочая схема:

**На Windows (в проекте):**

```powershell
cd frontend
yarn install --frozen-lockfile
$env:REACT_APP_BACKEND_URL="https://trainwbrain.ru"
yarn build
```

**Загрузить готовый `build/` на сервер:**

```powershell
scp -r frontend\build deploy@<IP>:/opt/trainwbrain/frontend/build
```

Или через rsync (Git Bash):

```bash
rsync -avz --delete frontend/build/ deploy@<IP>:/opt/trainwbrain/frontend/build/
```

На сервере `yarn install` для сборки тогда не нужен вовсе — nginx отдаёт статику
из `frontend/build`. Node на сервере всё равно пригодится для DSH и dev-сервера.

> Обновление фронтенда после правок: снова `yarn build` локально → `scp -r build`.
> `deploy/scripts/deploy.sh` в этом режиме используйте только для backend-части
> (или соберите фронт локально и закомментируйте блок `yarn build` в скрипте).

---

## 8. Nginx + HTTPS

### 8.1 Общая map для WebSocket

```bash
sudo cp /opt/trainwbrain/deploy/nginx/00-upgrade-map.conf /etc/nginx/conf.d/
```

### 8.2 Временный HTTP-конфиг и сертификат

Пока сертификата нет, боевой конфиг не загрузится. Сначала поднимаем временный:

```bash
sudo mkdir -p /var/www/certbot
sudo rm -f /etc/nginx/sites-enabled/default

sudo tee /etc/nginx/sites-available/trainwbrain-temp.conf >/dev/null <<'EOF'
server {
    listen 80;
    server_name trainwbrain.ru www.trainwbrain.ru;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 'ok'; add_header Content-Type text/plain; }
}
EOF

sudo ln -sf /etc/nginx/sites-available/trainwbrain-temp.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

curl -I http://trainwbrain.ru
```

Теперь сертификат:

```bash
sudo certbot certonly --webroot -w /var/www/certbot \
  -d trainwbrain.ru -d www.trainwbrain.ru \
  --agree-tos -m you@example.com --no-eff-email
```

Успех — файлы в `/etc/letsencrypt/live/trainwbrain.ru/`. Certbot сам создаст таймер
автообновления (`systemctl list-timers | grep certbot`).

> Если certbot ругается на DNS/порт 80 — проверьте `nslookup trainwbrain.ru 8.8.8.8`
> и `sudo ufw status`. Домен должен уже указывать на сервер.

### 8.3 Боевой конфиг

```bash
sudo cp /opt/trainwbrain/deploy/nginx/trainwbrain.conf /etc/nginx/sites-available/
sudo rm -f /etc/nginx/sites-enabled/trainwbrain-temp.conf
sudo ln -sf /etc/nginx/sites-available/trainwbrain.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Что учтено в [`deploy/nginx/trainwbrain.conf`](deploy/nginx/trainwbrain.conf):

| Что | Зачем |
|---|---|
| `location = /api/ws` с `Upgrade`/`Connection` | WebSocket живого статуса тренера |
| `proxy_read_timeout 300s` на `/api/` | ИИ-разбор программ/фото думает до 180 с |
| `client_max_body_size 25m` | фото дневника и xlsx-программы |
| `try_files ... /index.html` | SPA-роутинг React Router |
| `frame-ancestors` вместо `X-Frame-Options` | Telegram Web открывает Mini App в iframe |
| `no-cache` для `service-worker.js` | чтобы обновления не «залипали» |
| HSTS, `nosniff`, `Referrer-Policy` | базовая гигиена |

### 8.4 Проверка

```bash
curl -I https://trainwbrain.ru
curl -s https://trainwbrain.ru/api/
# {"message":"Hello World"}
```

Откройте `https://trainwbrain.ru` в браузере — должен загрузиться интерфейс
(вне Telegram он покажет «Гость» — это нормально).

Проверка WebSocket (опционально, на сервере):

```bash
sudo npm i -g wscat
wscat -c "wss://trainwbrain.ru/api/ws?token=bad" 
# ожидаемо: соединение закрывается с кодом 4401 — значит, nginx пропускает upgrade
```

### 8.5 Обновление сертификата

```bash
sudo certbot renew --dry-run
```

Если dry-run проходит — дальше всё автоматически (systemd timer дважды в сутки).

---

## 9. Telegram Mini App

### 9.1 BotFather

1. Откройте [@BotFather](https://t.me/BotFather).
2. Если бота ещё нет — `/newbot`, получите токен → он идёт в `TELEGRAM_BOT_TOKEN`.
3. Настройте кнопку меню:
   - `/setmenubutton` → выберите бота → URL `https://trainwbrain.ru` → название кнопки
     (например, «Открыть TrainWithBrain»).
4. Либо создайте Mini App: `/newapp` → бот → название → фото → URL `https://trainwbrain.ru`.

Требования Telegram: **HTTPS с валидным сертификатом**, без самоподписи, без редиректов
на другой домен. У нас именно так.

### 9.2 Проверка

- Откройте бота → кнопка меню → приложение должно открыться внутри Telegram.
- В приложении подтянется имя пользователя (а не «Гость»).
- В backend-логах (`journalctl -u twb-backend -f`) увидите запросы `/api/users` и т.п.

### 9.3 Если «Гость» и в логах нет пользователя

- приложение открыто не из Telegram (обычный браузер) — это ожидаемо;
- `TELEGRAM_BOT_TOKEN` не тот бот, через которого открываете (initData подписан токеном
  именно этого бота);
- рассинхрон времени на сервере: `timedatectl status` (должен быть синхронизирован);
- домен в BotFather отличается от фактического origin.

---

## 10. Режим разработки на сервере

Задача: править код на сервере и сразу видеть результат, не ломая прод.

### 10.1 SSH-туннели (рекомендуемый способ)

Если настроили `~/.ssh/config` из раздела 4.5 — просто:

```powershell
ssh twb
```

Пока сессия открыта, локально доступны:

- `http://localhost:3000` — dev-фронтенд (hot reload);
- `http://localhost:8001` — dev-backend (`--reload`);
- `http://127.0.0.1:3080` — DeepSeek Harness.

Без shell, только туннели:

```powershell
ssh -N twb
```

### 10.2 Dev-backend

```bash
sudo cp /opt/trainwbrain/deploy/systemd/twb-backend-dev.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now twb-backend-dev
curl -s http://127.0.0.1:8001/api/
```

Uvicorn перезапускается при изменении `.py` в `backend/`.

### 10.3 Dev-frontend

На сервере создайте `frontend/.env.development` (в git не попадает):

```env
REACT_APP_BACKEND_URL=http://localhost:8001
WDS_SOCKET_PORT=3000
ENABLE_HEALTH_CHECK=false
```

```bash
sudo cp /opt/trainwbrain/deploy/systemd/twb-frontend-dev.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now twb-frontend-dev
journalctl -u twb-frontend-dev -f
```

Первый старт CRA компилируется 30–60 с. Откройте `http://localhost:3000` (через туннель).

> Браузер ходит с `http://localhost:3000` на `http://localhost:8001` — это cross-origin.
> Добавьте `http://localhost:3000` в `CORS_ORIGINS` в `backend/.env`:
>
> ```env
> CORS_ORIGINS="https://trainwbrain.ru,https://www.trainwbrain.ru,http://localhost:3000"
> ```
>
> и перезапустите оба backend-сервиса.

> CRA не перечитывает `.env` на лету: после правки `.env.development` —
> `sudo systemctl restart twb-frontend-dev`.

### 10.4 Отдельная БД для экспериментов (опционально)

В `twb-backend-dev.service` раскомментируйте `Environment=DB_NAME=trainwbrain_dev`.
`python-dotenv` не переопределяет уже заданные переменные окружения, поэтому dev-сервис
будет писать в отдельную базу, а прод — в `trainwbrain_db`. Обе базы создаются
автоматически при первом запуске (seed идемпотентный).

### 10.5 Dev-поддомен (опционально)

Нужен, если хотите открывать dev-версию с телефона или из Telegram:

1. A-запись `dev` → IP.
2. `sudo certbot certonly --webroot -w /var/www/certbot -d dev.trainwbrain.ru`
3. Скопируйте [`deploy/nginx/dev-trainwbrain.conf`](deploy/nginx/dev-trainwbrain.conf),
   включите сайт, `nginx -t && systemctl reload nginx`.
4. В `frontend/.env.development` на сервере:

```env
REACT_APP_BACKEND_URL=http://localhost:8001
WDS_SOCKET_PORT=443
WDS_SOCKET_HOST=dev.trainwbrain.ru
```

5. Если webpack-dev-server ругается «Invalid Host header» — добавьте в юнит
   `Environment=DANGEROUSLY_DISABLE_HOST_CHECK=true` (только для dev-поддомена,
   который вы контролируете).
6. Не забудьте добавить `https://dev.trainwbrain.ru` в `CORS_ORIGINS` в
   `backend/.env` и перезапустить backend.

### 10.6 Рабочий цикл

```
правите код (локально в IDE через SSH Remote, или DSH на сервере)
        │
        ├─ dev-сервисы (8001 + 3000) подхватывают изменения автоматически
        │
        └─ когда готово: bash deploy/scripts/deploy.sh
             ├─ git pull
             ├─ pip install (быстро, если ничего не менялось)
             ├─ yarn build
             ├─ systemctl restart twb-backend
             └─ проверка /api/
```

IDE-вариант: VS Code → **Remote - SSH** → `twb` — полноценная разработка на сервере
без отдельного софта.

---

## 11. DeepSeek Harness

`dsh web` — браузерный интерфейс агента, который умеет читать/править код, запускать
команды и тесты прямо на сервере. Это ваш «AI-разработчик» в этой же машине.

### 11.1 Установка

`bootstrap.sh` уже ставит `@deepseek-ai/dsh`. Вручную:

```bash
sudo npm install -g @deepseek-ai/dsh@0.2.1-rc.2
dsh --version
```

### 11.2 Ключ DeepSeek

```bash
mkdir -p ~/.config/dsh
cat > ~/.config/dsh/env <<'EOF'
DEEPSEEK_API_KEY=sk-...
EOF
chmod 600 ~/.config/dsh/env
```

Ключ — в [platform.deepseek.com](https://platform.deepseek.com). Если используете
совместимый шлюз, добавьте `DEEPSEEK_BASE_URL=...`.

### 11.3 Первый запуск (вручную)

```bash
cd /opt/trainwbrain
dsh web --port 3080 --no-open
```

В консоли появится строка вида:

```
dsh web: http://127.0.0.1:3080/?token=<одноразовый-токен>
```

Скопируйте её. **Не закрывайте процесс** — откройте URL на своей машине (через туннель,
раздел 11.5). После обмена токена на cookie приложение работает без токена в URL.

> DSH принципиально не биндится на `0.0.0.0` — это защита от случайного выставления
> shell-доступа в интернет. Поэтому наружу его отдаём только через туннель или nginx
> с паролем.

Перед переходом на systemd остановите ручной процесс (Ctrl+C), иначе порт 3080 будет занят.

### 11.4 systemd (автозапуск)

```bash
mkdir -p ~/.config/systemd/user
cp /opt/trainwbrain/deploy/systemd/dsh-web.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now dsh-web

# чтобы сервис поднимался после ребута без логина deploy
sudo loginctl enable-linger deploy

systemctl --user status dsh-web --no-pager
journalctl --user -u dsh-web -n 30
```

В логах будет та же строка `dsh web: http://127.0.0.1:3080/?token=...`.

> Токен в URL одноразовый и меняется при каждом рестарте сервиса. Если потеряли —
> `journalctl --user -u dsh-web -n 50` и скопируйте заново.

### 11.5 Доступ через SSH-туннель (рекомендую)

На Windows (в отдельном окне, туннель уже настроен в `~/.ssh/config`):

```powershell
ssh -N twb
```

Откройте в браузере `http://127.0.0.1:3080/?token=<токен из логов>`.

Всё: DSH работает как будто локально, наружу не выставлен вообще.

### 11.6 Доступ через `dsh.trainwbrain.ru` (опционально)

Нужен, если хотите заходить с любого устройства без SSH. Обязательно с паролем:

```bash
sudo apt install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd-dsh deploy   # задайте длинный пароль
```

1. A-запись `dsh` → IP.
2. `sudo certbot certonly --webroot -w /var/www/certbot -d dsh.trainwbrain.ru`
3. Скопируйте [`deploy/nginx/dsh-trainwbrain.conf`](deploy/nginx/dsh-trainwbrain.conf),
   включите, `nginx -t && systemctl reload nginx`.
4. Убедитесь, что в юните есть `--trusted-host dsh.trainwbrain.ru`, перезапустите:

```bash
systemctl --user restart dsh-web
journalctl --user -u dsh-web -n 20
```

5. Откройте `https://dsh.trainwbrain.ru/?token=<токен>` — сначала спросит Basic Auth,
   потом пустит в DSH. В строке из логов замените `127.0.0.1:3080` на
   `dsh.trainwbrain.ru`, токен оставьте прежним.

Дополнительно закройте доступ по IP (в конфиге есть закомментированные `allow`/`deny`)
и включите fail2ban для nginx-логинов.

### 11.7 Как им пользоваться для этого проекта

- Workspace = `/opt/trainwbrain` (задан в юните `WorkingDirectory`).
- Агент видит весь репозиторий, `git`, `yarn`, `python`, тесты.
- Dev-сервисы (`8001`, `3000`) подхватывают правки автоматически; прод обновится только
  после `deploy.sh` — то есть «сломал прод» случайно не получится.
- Полезные запросы:
  - «посмотри `backend/server.py`, найди эндпоинты без авторизации»;
  - «прогони `pytest backend/tests -q` и почини падения»;
  - «добавь в дневник экспорт в CSV, покрой тестом, закоммить».

Ограничения и советы:

- DSH — RC-версия (`0.2.x`), фиксируйте версию при установке;
- агент тратит токены DeepSeek: длинные сессии и большие репозитории — дороже;
- не запускайте два экземпляра на одном `DSH_HOME` одновременно;
- состояние сессий — в `~/.dsh` (не в репозитории);
- обновление: `sudo npm i -g @deepseek-ai/dsh@latest && systemctl --user restart dsh-web`;
- одноразовые задачи без GUI: `cd /opt/trainwbrain && dsh headless "прогони pytest -q"`.

### 11.8 Безопасность DSH (важно)

DSH-агент выполняет команды shell от `deploy`. Кто получил доступ к UI — получил сервер.
Поэтому:

- только SSH-туннель или nginx + Basic Auth + (лучше) IP-allowlist;
- пароль длинный, уникальный;
- не ставьте DSH на тот же домен, что и приложение;
- периодически проверяйте `journalctl --user -u dsh-web` на подозрительные команды.

---

## 12. Эксплуатация

### 12.1 Логи

```bash
journalctl -u twb-backend -f          # backend
journalctl -u twb-frontend-dev -f     # dev-фронтенд
journalctl --user -u dsh-web -f       # DSH
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

Ограничьте размер журнала (иначе диск распухнет):

```bash
sudo sed -i 's/^#SystemMaxUse=.*/SystemMaxUse=500M/' /etc/systemd/journald.conf
sudo systemctl restart systemd-journald
```

### 12.2 Обновление приложения

```bash
ssh deploy@<IP>
bash /opt/trainwbrain/deploy/scripts/deploy.sh
```

Скрипт: `git pull` → pip → `yarn build` → рестарт backend → reload nginx → health-check.

> Если на сервере остались незакоммиченные правки (например, после работы DSH),
> `git pull --ff-only` упадёт. Закоммитьте и запушьте изменения либо сделайте
> `git stash`, затем повторите деплой.

Если менялись `.env` или nginx-конфиги:

```bash
sudo systemctl restart twb-backend
sudo nginx -t && sudo systemctl reload nginx
```

> Если хотите, чтобы `deploy.sh` запускался из DeepSeek Harness без ввода пароля sudo,
> разрешите только нужные команды:
>
> ```bash
> echo 'deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart twb-backend, /usr/bin/systemctl reload nginx' \
>   | sudo tee /etc/sudoers.d/twb-deploy
> sudo chmod 440 /etc/sudoers.d/twb-deploy
> ```
>
> Это компромисс: агент сможет рестартовать backend и nginx, но не получит полный root.

### 12.3 Бэкапы MongoDB

```bash
chmod +x /opt/trainwbrain/deploy/scripts/backup-mongo.sh
sudo crontab -e -u deploy
```

Добавьте:

```
30 3 * * * /opt/trainwbrain/deploy/scripts/backup-mongo.sh >> /home/deploy/twb-backup.log 2>&1
```

Бэкапы складываются в `/var/backups/trainwbrain`, хранятся 14 дней
([`deploy/scripts/backup-mongo.sh`](deploy/scripts/backup-mongo.sh)).

**Обязательно** дублируйте их вне сервера: снапшоты провайдера раз в день или
`rclone` в S3/Selectel Object Storage/Yandex Disk. Сервер с бэкапами на том же диске —
это не бэкап.

Проверка восстановления (раз в пару месяцев):

```bash
mongorestore --uri="mongodb://127.0.0.1:27017" --gzip --archive=/var/backups/trainwbrain/twb_....archive
```

### 12.4 Мониторинг

Минимум:

- `uptime`/`htop` руками;
- внешний пинг `https://trainwbrain.ru/api/` (UptimeRobot, Zabbix, Uptime Kuma);
- `df -h` — диск (сборки и логи любят расти);
- `free -h` — память;
- `sudo systemctl status twb-backend twb-frontend-dev nginx mongod`.

Опционально — Netdata (1 команда, ~100 МБ RAM) или Grafana Cloud free tier.

### 12.5 Обновления ОС

```bash
sudo apt update && sudo apt upgrade -y
sudo reboot   # если обновилось ядро
```

Автообновления безопасности уже включены `bootstrap.sh`.

### 12.6 Перенос локальной БД на сервер (если нужны текущие данные)

На Windows (при запущенном локальном mongod):

```powershell
mongodump --uri="mongodb://localhost:27017/trainwbrain_db" --gzip --archive=twb-local.archive
scp twb-local.archive deploy@<IP>:/tmp/
```

На сервере:

```bash
mongorestore --uri="mongodb://127.0.0.1:27017" --gzip --archive=/tmp/twb-local.archive
```

Если локальная БД не нужна — пропустите: при первом старте backend сам создаст индексы
и засеет встроенные упражнения/шаблоны.

---

## 13. Безопасность

Чек-лист (все пункты уже выполнены инструкцией выше, если шли по шагам):

- [x] вход root по паролю запрещён, только ключ;
- [x] ufw: открыты только 22/80/443;
- [x] MongoDB слушает только `127.0.0.1`;
- [x] FastAPI, CRA dev, DSH — только `127.0.0.1`;
- [x] `.env` / `.env.local` — `chmod 600`, не в git;
- [x] секреты (Telegram token, AI keys) не попадают во фронтенд-бандл;
- [x] HTTPS + HSTS + автообновление сертификата;
- [x] fail2ban для SSH;
- [x] автообновления безопасности ОС;
- [x] DSH не выставлен в интернет без пароля;
- [x] бэкапы БД вне сервера.

Дополнительно, если проект публичный:

- добавьте rate limit на AI-эндпоинты в nginx (`limit_req_zone`);
- проверьте, что `/api/docs` (Swagger) не нужен публично — при желании отключите;
- Telegram initData уже валидируется по HMAC в [`backend/auth.py`](backend/auth.py).

---

## 14. Troubleshooting

### `502 Bad Gateway` на `https://trainwbrain.ru`

Backend не запущен или упал:

```bash
systemctl status twb-backend --no-pager
journalctl -u twb-backend -n 100 --no-pager
curl -s http://127.0.0.1:8000/api/
```

Частая причина — ошибка в `.env` (например, MongoDB недоступна). Смотрите traceback.

### CORS-ошибка в браузере

- в `CORS_ORIGINS` должен быть **точный** origin: `https://trainwbrain.ru`, без слэша;
- если фронтенд открыт на `dev.trainwbrain.ru` — добавьте и его;
- после правки `.env` — `sudo systemctl restart twb-backend`.

### WebSocket не подключается (live-статус тренера)

- проверьте блок `location = /api/ws` в nginx (Upgrade/Connection);
- `wscat -c "wss://trainwbrain.ru/api/ws?token=bad"` должен установить соединение
  и закрыть его с кодом 4401 (значит, upgrade проходит);
- в консоли браузера ищите `wss://trainwbrain.ru/api/ws` — схема должна быть `wss`.

### Telegram: `initData` не проходит проверку

- токен бота в `.env` — от **того** бота, через которого открываете;
- время на сервере: `timedatectl status` (синхронизация через systemd-timesyncd);
- домен в BotFather = фактический origin (`https://trainwbrain.ru`).

### `pip install` падает на `customer-assets.emergentagent.com`

Вы ставите полный `backend/requirements.txt`. Используйте
[`deploy/requirements.server.txt`](deploy/requirements.server.txt).

### `yarn build` падает с `Killed` / `JavaScript heap out of memory`

```bash
free -h
sudo swapon --show
```

- убедитесь, что swap включён (bootstrap его создаёт);
- остановите dev-сервисы на время сборки:
  `sudo systemctl stop twb-frontend-dev`;
- добавьте памяти в юните: `Environment=NODE_OPTIONS=--max-old-space-size=4096`.

### `MongoServerError: connect ECONNREFUSED 127.0.0.1:27017`

```bash
systemctl status mongod
sudo tail -n 50 /var/log/mongodb/mongod.log
```

Часто — не хватило диска или mongod не стартовал после смены конфига.

### certbot: `Timeout during connect`

- DNS ещё не обновился (`nslookup`);
- порт 80 закрыт (`sudo ufw status`, провайдерский firewall);
- nginx не отдаёт `/.well-known/acme-challenge/` (проверьте временный конфиг).

### После деплоя фронтенд ходит на `localhost:8000`

Значит, собрали без `.env.production`. Проверьте:

```bash
grep -o 'https://trainwbrain.ru' /opt/trainwbrain/frontend/build/static/js/main.*.js | head
```

Если нет — создайте `.env.production` и пересоберите.

### DSH: `dsh web:` URL не открывается

- DSH слушает только `127.0.0.1` — нужен туннель или nginx;
- токен из URL одноразовый и меняется после рестарта — берите свежий из логов;
- при доступе через домен — флаг `--trusted-host` и Host-заголовок от nginx.

### «Старая версия» после деплоя

Service worker + кэш браузера: Hard Reload (Ctrl+Shift+R), либо в DevTools →
Application → Service Workers → Unregister.

---

## 15. Бюджет

Ориентировочно, в месяц (цены проверяйте у провайдера — они меняются):

| Статья | Стоимость |
|---|---|
| VPS 4 vCPU / 8 ГБ / 80 ГБ NVMe | 1200–2000 ₽ |
| Снапшоты/бэкапы провайдера (опц.) | 100–300 ₽ |
| Домен `.ru` | ~200–900 ₽/год (≈ 20–75 ₽/мес) |
| Let's Encrypt | 0 ₽ |
| Telegram Bot API | 0 ₽ |
| DeepSeek API (разработка + прод) | 300–2000 ₽ (зависит от интенсивности) |
| **Итого** | **≈ 1700–4300 ₽/мес** |

Экономия:

- 2 vCPU / 4 ГБ / 60 ГБ — на 500–900 ₽/мес дешевле, но сборки медленнее и нужен swap;
- не держать dev-сервисы включёнными круглосуточно
  (`systemctl stop twb-frontend-dev twb-backend-dev`), когда не разрабатываете;
- DeepSeek-агент — самая «плавающая» статья: следите за расходом в кабинете.

Что НЕ стоит экономить: NVMe (иначе MongoDB и сборки будут тормозить) и 8 ГБ RAM,
если планируете реально разрабатывать на сервере, а не только хостить прод.

---

## 16. Финальный чек-лист

```
[ ] VPS 4/8/80 Ubuntu 24.04, DNS A-записи указывают на IP
[ ] deploy создан, ключ работает, root/password по SSH отключены
[ ] bootstrap.sh выполнен: node 24, yarn, dsh, mongod, nginx, ufw, swap
[ ] код в /opt/trainwbrain, backend/.env заполнен, chmod 600
[ ] backend venv + requirements.server.txt, twb-backend active
[ ] curl http://127.0.0.1:8000/api/ -> {"message":"Hello World"}
[ ] frontend/.env.production, yarn build -> build/index.html
[ ] nginx: map + боевой конфиг, nginx -t ок
[ ] certbot: сертификат на trainwbrain.ru + www, renew --dry-run ок
[ ] https://trainwbrain.ru открывается, https://trainwbrain.ru/api/ отвечает
[ ] BotFather: menu button / Mini App на https://trainwbrain.ru
[ ] приложение открывается в Telegram, имя пользователя подтягивается
[ ] dev: twb-backend-dev (8001) + twb-frontend-dev (3000), доступ по SSH-туннелю
[ ] DSH: ключ в ~/.config/dsh/env, dsh-web active, доступ по туннелю
[ ] бэкап MongoDB в cron, копия вне сервера
[ ] мониторинг /api/ снаружи, журналы ограничены по размеру
```

---

## Приложение: что лежит в `deploy/`

| Файл | Назначение |
|---|---|
| [`deploy/requirements.server.txt`](deploy/requirements.server.txt) | зависимости backend без пакетов Emergent |
| [`deploy/env/backend.env.example`](deploy/env/backend.env.example) | шаблон `backend/.env` |
| [`deploy/env/frontend.env.production.example`](deploy/env/frontend.env.production.example) | шаблон `frontend/.env.production` |
| [`deploy/nginx/00-upgrade-map.conf`](deploy/nginx/00-upgrade-map.conf) | map для WebSocket |
| [`deploy/nginx/trainwbrain.conf`](deploy/nginx/trainwbrain.conf) | основной сайт + API + WS |
| [`deploy/nginx/dev-trainwbrain.conf`](deploy/nginx/dev-trainwbrain.conf) | dev-поддомен (опц.) |
| [`deploy/nginx/dsh-trainwbrain.conf`](deploy/nginx/dsh-trainwbrain.conf) | DSH-поддомен (опц., с паролем) |
| [`deploy/systemd/twb-backend.service`](deploy/systemd/twb-backend.service) | прод-backend |
| [`deploy/systemd/twb-backend-dev.service`](deploy/systemd/twb-backend-dev.service) | dev-backend с reload |
| [`deploy/systemd/twb-frontend-dev.service`](deploy/systemd/twb-frontend-dev.service) | dev-фронтенд |
| [`deploy/systemd/dsh-web.service`](deploy/systemd/dsh-web.service) | DSH как user-сервис |
| [`deploy/scripts/bootstrap.sh`](deploy/scripts/bootstrap.sh) | первичная настройка сервера |
| [`deploy/scripts/deploy.sh`](deploy/scripts/deploy.sh) | обновление приложения |
| [`deploy/scripts/backup-mongo.sh`](deploy/scripts/backup-mongo.sh) | бэкап MongoDB |
