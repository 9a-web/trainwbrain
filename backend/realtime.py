"""
TrainWithBrain — Real-time (WebSocket) инфраструктура для Фазы P4.

Цель: тренер видит ход тренировки подопечного «вживую» и сам заполняет/
подтверждает выполненное; правки плана и подтверждения доходят моментально
в обе стороны.

Транспорт: нативный WebSocket FastAPI на endpoint `/api/ws` (префикс `/api`,
чтобы Kubernetes ingress направил апгрейд на backend:8001).

ConnectionManager — in-memory (достаточно для MVP при одном инстансе backend).
Комнаты:
  - `plan:{plan_id}`     — общая для спортсмена и его тренера(ов)
  - `user:{telegram_id}` — личные уведомления пользователю

Принцип: источник истины — БД. WebSocket только транслирует изменения. Каждое
событие сначала персистится REST-обработчиком, затем broadcast. На реконнекте
клиент делает REST-«догон», поэтому потеря сокет-сообщения не ломает синхрон.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger("realtime")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(message: dict) -> str:
    # default=str: datetime и прочие нестандартные типы превращаются в строки
    return json.dumps(message, default=str, ensure_ascii=False)


class ConnectionManager:
    """Управляет WebSocket-соединениями и комнатами (in-memory)."""

    def __init__(self) -> None:
        # room -> набор активных соединений
        self.rooms: Dict[str, Set[WebSocket]] = {}
        # соединение -> метаданные {telegram_id, name, rooms}
        self.meta: Dict[WebSocket, dict] = {}
        self._lock = asyncio.Lock()

    # --- регистрация / отключение ---------------------------------------
    async def register(self, ws: WebSocket, telegram_id: int, name: str) -> None:
        async with self._lock:
            self.meta[ws] = {
                "telegram_id": telegram_id,
                "name": name,
                "rooms": set(),
            }

    async def disconnect(self, ws: WebSocket) -> List[str]:
        """Удаляет соединение из всех комнат. Возвращает список затронутых комнат."""
        async with self._lock:
            info = self.meta.pop(ws, None)
            rooms = list(info["rooms"]) if info else []
            for room in rooms:
                conns = self.rooms.get(room)
                if conns and ws in conns:
                    conns.discard(ws)
                    if not conns:
                        self.rooms.pop(room, None)
            return rooms

    # --- подписка на комнаты --------------------------------------------
    async def join(self, ws: WebSocket, room: str) -> None:
        async with self._lock:
            self.rooms.setdefault(room, set()).add(ws)
            if ws in self.meta:
                self.meta[ws]["rooms"].add(room)

    async def leave(self, ws: WebSocket, room: str) -> None:
        async with self._lock:
            conns = self.rooms.get(room)
            if conns and ws in conns:
                conns.discard(ws)
                if not conns:
                    self.rooms.pop(room, None)
            if ws in self.meta:
                self.meta[ws]["rooms"].discard(room)

    # --- presence --------------------------------------------------------
    def presence(self, room: str) -> List[dict]:
        """Кто онлайн в комнате (уникально по telegram_id)."""
        seen: Dict[int, str] = {}
        for ws in self.rooms.get(room, set()):
            m = self.meta.get(ws)
            if m:
                seen[m["telegram_id"]] = m["name"]
        return [{"telegram_id": tid, "name": name} for tid, name in seen.items()]

    def room_size(self, room: str) -> int:
        return len(self.rooms.get(room, set()))

    # --- отправка --------------------------------------------------------
    async def send_personal(self, ws: WebSocket, message: dict) -> None:
        try:
            await ws.send_text(_dumps(message))
        except Exception:
            # тихо игнорируем — мёртвое соединение уберётся при следующем disconnect
            pass

    async def broadcast(
        self,
        room: str,
        type_: str,
        payload: dict,
        exclude: Optional[WebSocket] = None,
    ) -> int:
        """Рассылает событие всем в комнате. Возвращает число доставленных."""
        message = {"type": type_, "room": room, "payload": payload, "ts": now_iso()}
        data = _dumps(message)
        dead: List[WebSocket] = []
        sent = 0
        for ws in list(self.rooms.get(room, set())):
            if ws is exclude:
                continue
            try:
                await ws.send_text(data)
                sent += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)
        return sent


# Единый менеджер на процесс backend
manager = ConnectionManager()
