import { useCallback, useEffect, useRef, useState } from 'react';
import {
  isLiveActivityAvailable,
  startLiveActivity,
  updateLiveActivity,
  endLiveActivity,
} from '@/lib/LiveActivityBridge';

/**
 * useLiveActivity — React Hook для управления Dynamic Island / Live Activity
 * в процессе тренировки.
 *
 * Автоматически запускает Live Activity при старте тренировки,
 * обновляет при смене упражнения/подходов, завершает при окончании.
 *
 * @param {object} opts
 * @param {boolean} opts.enabled — включить Live Activity (обычно === isIOS && тренировка активна)
 * @param {string} opts.sessionId — ID сессии
 * @param {string} opts.exerciseName — текущее упражнение
 * @param {number} opts.setsCompleted — выполнено подходов
 * @param {number} opts.totalSets — всего подходов
 * @param {string} opts.repScheme — схема повторений
 * @param {string} opts.weight — вес
 * @param {string} opts.status — "active" | "rest" | "finished"
 * @param {number} opts.elapsedMinutes — минут прошло
 */
export function useLiveActivity({
  enabled = false,
  sessionId,
  exerciseName = 'Тренировка',
  setsCompleted = 0,
  totalSets = 0,
  repScheme = '',
  weight = '',
  status = 'active',
  elapsedMinutes = 0,
} = {}) {
  const [supported, setSupported] = useState(false);
  const activityStartedRef = useRef(false);
  const prevEnabledRef = useRef(false);
  const prevStatusRef = useRef(status);

  // При монтировании проверяем доступность
  useEffect(() => {
    let cancelled = false;
    isLiveActivityAvailable().then((res) => {
      if (!cancelled) setSupported(res.available);
    });
    return () => { cancelled = true; };
  }, []);

  // Старт/стоп при изменении enabled
  useEffect(() => {
    if (!supported) return;

    // enabled выключился — завершаем активность
    if (prevEnabledRef.current && !enabled && activityStartedRef.current) {
      activityStartedRef.current = false;
      endLiveActivity('immediate');
    }

    prevEnabledRef.current = enabled;
  }, [enabled, supported]);

  // Старт при первом включении
  const doStart = useCallback(async () => {
    if (!supported || !enabled || !sessionId || activityStartedRef.current) return;
    activityStartedRef.current = true;
    try {
      await startLiveActivity({
        sessionId,
        exerciseName,
        setsCompleted,
        totalSets,
        repScheme,
        weight,
        status,
        elapsedMinutes,
      });
    } catch (e) {
      activityStartedRef.current = false;
    }
  }, [supported, enabled, sessionId, exerciseName, setsCompleted, totalSets, repScheme, weight, status, elapsedMinutes]);

  // Запуск Live Activity при старте
  useEffect(() => {
    if (enabled && supported && sessionId && !activityStartedRef.current) {
      doStart();
    }
  }, [enabled, supported, sessionId, doStart]);

  // Обновление при изменении данных
  const prevDataRef = useRef({ exerciseName, setsCompleted, totalSets, repScheme, weight, status });
  useEffect(() => {
    if (!activityStartedRef.current) return;

    const prev = prevDataRef.current;
    const changed =
      prev.exerciseName !== exerciseName ||
      prev.setsCompleted !== setsCompleted ||
      prev.totalSets !== totalSets ||
      prev.repScheme !== repScheme ||
      prev.weight !== weight ||
      prev.status !== status;

    if (changed) {
      prevDataRef.current = { exerciseName, setsCompleted, totalSets, repScheme, weight, status };
      updateLiveActivity({
        exerciseName,
        setsCompleted,
        totalSets,
        repScheme,
        weight,
        status,
        elapsedMinutes,
      });
    }
  }, [exerciseName, setsCompleted, totalSets, repScheme, weight, status, elapsedMinutes]);

  // Завершение при статусе "finished"
  useEffect(() => {
    if (status === 'finished' && activityStartedRef.current) {
      activityStartedRef.current = false;
      endLiveActivity('after');
    }
  }, [status]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (activityStartedRef.current) {
        activityStartedRef.current = false;
        endLiveActivity('immediate');
      }
    };
  }, []);

  return { supported };
}

export default useLiveActivity;