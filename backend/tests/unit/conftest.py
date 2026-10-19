"""Общая настройка unit-тестов: переменные окружения и sys.path.

Интеграционные скрипты (tests/*.py, tests/integration/*) не собираются —
см. testpaths в pytest.ini. Здесь только офлайн-тесты без БД/сети.
"""
import os
import sys

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# server.py читает эти переменные на этапе импорта (fail-fast).
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trainwbrain_test")
os.environ.setdefault("CORS_ORIGINS", "*")
