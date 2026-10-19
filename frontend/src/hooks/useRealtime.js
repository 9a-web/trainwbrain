import { useCallback, useEffect, useRef, useState } from "react";
import { WS_BASE, getAuthToken } from "@/api";

/**
 * useRealtime — единое WebSocket-соединение к /api/ws.
 *
 * Возможности:
 *  - аутентификация по session-token (?token=) из localStorage;
 *  - подписка на комнату плана (plan:{planId});
 *  - автопереподключение с экспоненциальным backoff;
 *  - keepalive ping каждые ~25с;
 *  - presence (кто онлайн в комнате) обновляется автоматически;
 *  - события доставляются в колбэк onEvent({ type, room, payload, ts }).
 *
 * Источник истины — БД: на (ре)коннекте потребитель должен сделать REST-«догон».
 *
 * @param {object} opts
 * @param {string|null} opts.planId — комната плана для подписки
 * @param {boolean} opts.enabled — включить соединение
 * @param {(event:object)=>void} opts.onEvent — обработчик событий
 * @returns {{connected:boolean, online:Array, subscribe:Function}}
 */
export function useRealtime({ planId = null, enabled = true, onEvent } = {}) {
  const [connected, setConnected] = useState(false);
  const [online, setOnline] = useState([]);

  const wsRef = useRef(null);
  const retryRef = useRef(0);
  const pingRef = useRef(null);
  const stoppedRef = useRef(false);
  const onEventRef = useRef(onEvent);
  const planRef = useRef(planId);
  // Локальные подписчики по типу события: Map<type, Set<handler>>
  const listenersRef = useRef(new Map());

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);
  useEffect(() => {
    planRef.current = planId;
  }, [planId]);

  /**
   * Двойное назначение:
   *   subscribe(planId)                 — подписка на комнату плана (WS);
   *   subscribe(eventType, handler)     — локальный колбэк на событие, возвращает unsubscribe().
   * Второй вариант нужен странице тренера (client_status_change).
   */
  const subscribe = useCallback((arg1, arg2) => {
    if (typeof arg2 === "function") {
      const type = arg1;
      const map = listenersRef.current;
      if (!map.has(type)) map.set(type, new Set());
      map.get(type).add(arg2);
      return () => {
        const set = map.get(type);
        if (set) {
          set.delete(arg2);
          if (!set.size) map.delete(type);
        }
      };
    }
    const pid = arg1;
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN && pid) {
      ws.send(JSON.stringify({ type: "subscribe", plan_id: pid }));
    }
    return undefined;
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;
    stoppedRef.current = false;

    let reconnectTimer = null;

    const scheduleReconnect = () => {
      if (stoppedRef.current) return;
      const attempt = retryRef.current;
      retryRef.current += 1;
      const delay = Math.min(30000, 1000 * 2 ** Math.min(attempt, 5)); // 1s..32s
      reconnectTimer = setTimeout(connect, delay);
    };

    const connect = () => {
      if (stoppedRef.current) return;
      // Без базового URL WebSocket создать нельзя — не зацикливаем реконнекты.
      // Данные всё равно приходят по REST, realtime просто отключён.
      if (!WS_BASE) {
        setConnected(false);
        return;
      }
      const token = getAuthToken();
      if (!token) {
        scheduleReconnect();
        return;
      }
      let ws;
      try {
        ws = new WebSocket(`${WS_BASE}?token=${encodeURIComponent(token)}`);
      } catch (e) {
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        retryRef.current = 0;
        setConnected(true);
        if (planRef.current) {
          ws.send(JSON.stringify({ type: "subscribe", plan_id: planRef.current }));
        }
        if (pingRef.current) clearInterval(pingRef.current);
        pingRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, 25000);
      };

      ws.onmessage = (e) => {
        let msg;
        try {
          msg = JSON.parse(e.data);
        } catch (err) {
          return;
        }
        if (msg.type === "pong" || msg.type === "connected") return;
        if (msg.type === "presence") {
          setOnline(msg.payload?.online || []);
          return;
        }
        const localSet = listenersRef.current.get(msg.type);
        if (localSet) {
          localSet.forEach((cb) => {
            try {
              cb(msg.payload || msg);
            } catch (err) {
              /* изолируем сбой одного подписчика */
            }
          });
        }
        if (onEventRef.current) onEventRef.current(msg);
      };

      ws.onclose = () => {
        setConnected(false);
        if (pingRef.current) {
          clearInterval(pingRef.current);
          pingRef.current = null;
        }
        if (!stoppedRef.current) scheduleReconnect();
      };

      ws.onerror = () => {
        try {
          ws.close();
        } catch (err) {
          /* no-op */
        }
      };
    };

    connect();

    return () => {
      stoppedRef.current = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (pingRef.current) {
        clearInterval(pingRef.current);
        pingRef.current = null;
      }
      const ws = wsRef.current;
      if (ws) {
        try {
          ws.close();
        } catch (err) {
          /* no-op */
        }
      }
      wsRef.current = null;
      setConnected(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  // (Пере)подписка при смене planId; при смене/размонтировании — отписка от старой комнаты (I5)
  useEffect(() => {
    if (!connected) return undefined;
    if (planId) subscribe(planId);
    return () => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN && planId) {
        try {
          ws.send(JSON.stringify({ type: "unsubscribe", plan_id: planId }));
        } catch (e) {
          /* no-op */
        }
      }
    };
  }, [planId, connected, subscribe]);

  return { connected, online, subscribe };
}

export default useRealtime;
