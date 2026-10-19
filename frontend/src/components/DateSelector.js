import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { Zap, Pause, Play, Square, Lock, Info } from 'lucide-react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { useUser } from '@/context/UserContext';
import { useCapabilities } from '@/hooks/useCapabilities';
import {
  getActivePlan, getWeekProgress, getPlanDay,
  startSession, getActiveSession, sessionExerciseAction,
  editSessionExercise, finishSession, resumeSession, pauseSession, logSessionSet,
} from '@/api';
import WorkoutView from '@/components/WorkoutView';
import Portal from '@/components/Portal';
import { haptic, hapticNotify, hapticSelection } from '@/lib/platform';
import { useMainButton } from '@/hooks/useTelegramUI';
import { useRealtime } from '@/hooks/useRealtime';
import './DateSelector.css';

// Сокращённые названия дней недели (index = JS getDay(): 0=Вс..6=Сб)
const DAY_NAMES = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];

// Преобразование JS getDay() (Вс=0..Сб=6) в day_index плана (Пн=1..Вс=7)
const toDayIndex = (jsDay) => ((jsDay + 6) % 7) + 1;

// Локальная дата -> ISO YYYY-MM-DD (без сдвига часового пояса, как видит пользователь)
const toISODate = (d) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
};

// Компонент кругового прогресс-бара
const ProgressRing = ({ progress, size = 50, strokeWidth = 4, isSelected = false, isWorkout = false, index = 0 }) => {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  // Анимация заполнения при загрузке: стартуем с 0% и плавно заполняем до целевого значения
  const [animatedProgress, setAnimatedProgress] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => setAnimatedProgress(progress), 60);
    return () => clearTimeout(timer);
  }, [progress]);

  const strokeDashoffset = circumference - (animatedProgress / 100) * circumference;

  return (
    <svg 
      className="progress-ring" 
      viewBox={`0 0 ${size} ${size}`}
      preserveAspectRatio="xMidYMid meet"
    >
      {/* Фоновый круг - скрываем при выборе */}
      <circle
        className="progress-ring-bg"
        cx={size / 2}
        cy={size / 2}
        r={radius}
        strokeWidth={strokeWidth}
        fill={isSelected ? "transparent" : "#1C1C1C"}
        style={{ stroke: (progress > 0 || isSelected || isWorkout) ? "rgba(255, 235, 217, 0.6)" : "#1C1C1C" }}
      />
      {/* Прогресс */}
      <circle
        className="progress-ring-progress"
        cx={size / 2}
        cy={size / 2}
        r={radius}
        strokeWidth={strokeWidth}
        fill="transparent"
        strokeDasharray={circumference}
        strokeDashoffset={strokeDashoffset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{
          transition: 'stroke-dashoffset 0.9s cubic-bezier(0.22, 1, 0.36, 1)',
          transitionDelay: `${index * 90}ms`,
        }}
      />
    </svg>
  );
};

// Компонент карточки дня
export const DayCard = ({ date, dayName, dayNumber, progress, isSelected, isWorkout = false, onClick, index = 0, animClass = '' }) => {
  return (
    <button 
      className={`day-card ${isSelected ? 'day-card-selected' : ''} ${isWorkout ? 'day-card-workout' : ''} ${animClass}`}
      onClick={onClick}
      aria-label={`${dayName}, ${dayNumber} число${isWorkout ? ', тренировка' : ''}`}
      aria-pressed={isSelected}
      style={animClass ? { animationDelay: `${index * 55}ms` } : undefined}
    >
      <span className="day-card-name">{dayName}</span>
      <div className="day-card-circle-wrapper">
        <ProgressRing progress={progress} isSelected={isSelected} isWorkout={isWorkout} index={index} />
        <span className="day-card-number">{dayNumber}</span>
      </div>
      {isWorkout ? <span className="day-card-dot" aria-hidden="true" /> : null}
    </button>
  );
};

// Основной компонент выбора даты
// Названия месяцев в родительном падеже
const MONTH_NAMES = [
  'Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
  'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря'
];

// Доступные тренировочные недели (смещения относительно текущей, 0 = текущая)
const WEEK_OFFSETS = [-1, 0, 1];

const DateSelector = () => {
  const { user } = useUser();
  const { can: canPerm } = useCapabilities();
  // Фаза 1: managed-атлет («физический подопечный») не заполняет силовую —
  // только просмотр (заполняет тренер). capabilities==null → true (back-compat).
  const canLogStrength = canPerm('log_strength');
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [weekOffset, setWeekOffset] = useState(0); // Смещение недели (0 = текущая)
  const [slideDir, setSlideDir] = useState(null); // Направление анимации смены недели
  const [weekPickerOpen, setWeekPickerOpen] = useState(false); // Модалка «План» — выбор любой недели
  const [infoOpen, setInfoOpen] = useState(false); // Инфо-модалка завершённой тренировки

  const [plan, setPlan] = useState(null);
  const [planLoading, setPlanLoading] = useState(true);
  const [progressByDay, setProgressByDay] = useState({}); // day_index -> info
  const [dayDetail, setDayDetail] = useState(null);
  const [dayLoading, setDayLoading] = useState(false);

  // Недели плана: текущая и общее количество
  const totalWeeks = (plan?.weeks && plan.weeks.length) || 0;
  const baseWeek = plan?.current_week || 1;

  // Смещение остаётся в границах доступных недель плана, иначе календарные
  // даты одной недели уезжали бы на другую неделю плана (week/date desync).
  const minOffset = totalWeeks ? 1 - baseWeek : -1;
  const maxOffset = totalWeeks ? totalWeeks - baseWeek : 1;
  const clampOffset = useCallback(
    (o) => Math.min(Math.max(o, minOffset), maxOffset),
    [minOffset, maxOffset]
  );

  // Какая неделя плана соответствует отображаемому смещению
  const planWeek = useMemo(() => {
    if (!plan) return 1;
    const total = (plan.weeks && plan.weeks.length) || 1;
    return Math.min(Math.max(1, baseWeek + weekOffset), total);
  }, [plan, baseWeek, weekOffset]);

  // Смещение, реально соответствующее выбранной неделе плана (после клампа)
  const effectiveOffset = totalWeeks ? planWeek - baseWeek : weekOffset;

  // Реальные календарные даты отображаемой недели (day_index 1..7 = Пн..Вс)
  const weekDates = useMemo(() => {
    const today = new Date();
    const monday = new Date(today);
    monday.setDate(today.getDate() - ((today.getDay() + 6) % 7) + effectiveOffset * 7);
    const arr = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(monday);
      d.setDate(monday.getDate() + i);
      arr.push(toISODate(d));
    }
    return arr;
  }, [effectiveOffset]);
  const weekDatesStr = useMemo(() => weekDates.join(','), [weekDates]);

  // Недели, ещё не открытые тренером (published === false) — спортсмен их не видит
  const isWeekLocked = useCallback((wk) => {
    if (!plan?.weeks) return false;
    const w = plan.weeks.find((x) => x.week_index === wk);
    return !!w && w.published === false;
  }, [plan]);

  // Динамика топового веса каждого упражнения по неделям плана (для графика)
  const forecastBySlug = useMemo(() => {
    if (!plan?.weeks) return {};
    const topWeight = (ex) => {
      const ws = (ex.sets_scheme || [])
        .map((s) => s.weight)
        .filter((w) => w !== null && w !== undefined);
      return ws.length ? Math.max(...ws) : null;
    };
    const bySlug = {};
    [...plan.weeks]
      .sort((a, b) => (a.week_index || 0) - (b.week_index || 0))
      .forEach((w) => {
        (w.days || []).forEach((d) => {
          (d.exercises || []).forEach((ex) => {
            const slug = ex.exercise_slug;
            if (!slug) return;
            const tw = topWeight(ex);
            if (tw === null) return;
            bySlug[slug] = bySlug[slug] || {};
            bySlug[slug][w.week_index] = Math.max(bySlug[slug][w.week_index] ?? 0, tw);
          });
        });
      });
    const map = {};
    Object.entries(bySlug).forEach(([slug, wk]) => {
      map[slug] = Object.keys(wk)
        .map(Number)
        .sort((a, b) => a - b)
        .map((wki) => ({ week: wki, value: wk[wki] }));
    });
    return map;
  }, [plan]);

  // Загрузка активного плана спортсмена
  useEffect(() => {
    if (!user?.telegram_id) return undefined;
    let cancelled = false;
    setPlanLoading(true);
    (async () => {
      try {
        const p = await getActivePlan(user.telegram_id);
        if (!cancelled) setPlan(p);
      } catch (e) {
        if (!cancelled) setPlan(null);
      } finally {
        if (!cancelled) setPlanLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [user?.telegram_id]);

  // Загрузка прогресса по дням выбранной недели
  useEffect(() => {
    if (!plan?.id) { setProgressByDay({}); return undefined; }
    let cancelled = false;
    (async () => {
      try {
        const data = await getWeekProgress(plan.id, planWeek, user?.telegram_id, weekDatesStr);
        if (cancelled) return;
        const map = {};
        (data.days || []).forEach((d) => { map[d.day_index] = d; });
        setProgressByDay(map);
      } catch (e) {
        if (!cancelled) setProgressByDay({});
      }
    })();
    return () => { cancelled = true; };
  }, [plan?.id, planWeek, user?.telegram_id, weekDatesStr]);

  // Генерируем дни недели с учётом смещения
  const weekDays = useMemo(() => {
    const today = new Date();
    const currentDay = today.getDay(); // 0 = Воскресенье

    const monday = new Date(today);
    monday.setDate(today.getDate() - ((currentDay + 6) % 7) + (effectiveOffset * 7));

    const days = [];
    for (let i = 0; i < 7; i++) {
      const date = new Date(monday);
      date.setDate(monday.getDate() + i);

      const di = toDayIndex(date.getDay());
      const info = progressByDay[di];
      days.push({
        date: date,
        dayName: DAY_NAMES[date.getDay()],
        dayNumber: date.getDate(),
        progress: info?.progress_pct || 0,
        isWorkout: !!info?.is_workout,
      });
    }

    return days;
  }, [effectiveOffset, progressByDay]);

  // Загрузка деталей выбранного дня
  useEffect(() => {
    if (!plan?.id) { setDayDetail(null); setDayLoading(false); return undefined; }
    const di = toDayIndex(selectedDate.getDay());
    let cancelled = false;
    // Сбрасываем старый день, чтобы не показывать данные предыдущего дня,
    // пока грузится новый.
    setDayDetail(null);
    setDayLoading(true);
    (async () => {
      try {
        const d = await getPlanDay(plan.id, planWeek, di, user?.telegram_id);
        if (!cancelled) setDayDetail(d);
      } catch (e) {
        if (!cancelled) setDayDetail(null);
      } finally {
        if (!cancelled) setDayLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [plan?.id, planWeek, selectedDate, user?.telegram_id]);

  const handleDayClick = (date, event) => {
    hapticSelection();
    setSelectedDate(date);
    // Автоматический скролл к выбранной карточке дня
    if (event?.currentTarget) {
      event.currentTarget.scrollIntoView({
        behavior: 'smooth',
        inline: 'center',
        block: 'nearest',
      });
    }
  };

  // Неделя плана: точки-индикаторы (прошлая/текущая/следующая) + кнопка «План» для перехода к любой неделе
  const goToOffset = (offset) => {
    const target = clampOffset(offset);
    if (target === weekOffset) return;
    hapticSelection();
    setSlideDir(target > weekOffset ? 'next' : 'prev');
    // Сдвигаем выбранную дату на ту же дельту недель, чтобы выбранный день
    // оставался подсвеченным в новой неделе.
    const diff = target - weekOffset;
    setSelectedDate((prev) => {
      const d = new Date(prev);
      d.setDate(d.getDate() + diff * 7);
      return d;
    });
    setWeekOffset(target);
  };

  // Сброс направления анимации после её проигрывания
  useEffect(() => {
    if (!slideDir) return undefined;
    const t = setTimeout(() => setSlideDir(null), 650);
    return () => clearTimeout(t);
  }, [slideDir]);

  const handleWeekDotClick = (offset) => goToOffset(offset);

  const goToWeek = (weekIndex) => {
    if (isWeekLocked(weekIndex)) {
      toast.message('Эта неделя ещё не открыта тренером');
      return;
    }
    const target = Math.min(Math.max(1, weekIndex), totalWeeks || weekIndex);
    goToOffset(target - baseWeek);
    setWeekPickerOpen(false);
  };

  const isSameDay = (date1, date2) => {
    return date1.getDate() === date2.getDate() &&
           date1.getMonth() === date2.getMonth() &&
           date1.getFullYear() === date2.getFullYear();
  };

  // Форматирование выбранной даты
  const formattedDate = `${selectedDate.getDate()} ${MONTH_NAMES[selectedDate.getMonth()]}`;

  // Пока день грузится — не считаем его днём отдыха (иначе мерцает «День отдыха»).
  const isRestSelected = !dayLoading && (!dayDetail || dayDetail.is_rest);
  const selectedDayIndex = toDayIndex(selectedDate.getDay());
  // Тренер ещё не опубликовал план — содержимое скрыто
  const isDraft = !!plan && plan.visibility === "draft";

  // Тренировочная сессия выбранного дня
  const [session, setSession] = useState(null);
  const [starting, setStarting] = useState(false);
  const [confirmStartOpen, setConfirmStartOpen] = useState(false);

  const refreshProgress = useCallback(async () => {
    if (!plan?.id) return;
    try {
      const data = await getWeekProgress(plan.id, planWeek, user?.telegram_id, weekDatesStr);
      const map = {};
      (data.days || []).forEach((d) => { map[d.day_index] = d; });
      setProgressByDay(map);
      window.dispatchEvent(new Event('twb:progress'));
    } catch (e) { /* no-op */ }
  }, [plan?.id, planWeek, user?.telegram_id, weekDatesStr]);

  // Перезагрузка активного плана (когда тренер опубликовал/изменил недели/дни)
  const reloadPlan = useCallback(async () => {
    if (!user?.telegram_id) return;
    try {
      const p = await getActivePlan(user.telegram_id);
      setPlan(p);
    } catch (e) { /* no-op */ }
  }, [user?.telegram_id]);

  // Real-time: ход тренировки и правки тренера приходят вживую
  const onRtEvent = useCallback((evt) => {
    const t = evt.type || '';
    if (t.startsWith('session.')) {
      const sess = evt.payload?.session;
      if (!sess) return;
      // Применяем снимок для открытой сессии; либо принимаем НОВУЮ сессию, если
      // тренер начал тренировку «под диктовку» в выбранный сейчас день.
      setSession((cur) => {
        if (cur && cur.id === sess.id) return sess;
        if (!cur && sess.plan_id === plan?.id
            && sess.week_index === planWeek
            && sess.day_index === selectedDayIndex) {
          return sess;
        }
        return cur;
      });
      refreshProgress();
      if (t === 'session.confirmed') {
        hapticNotify('success');
        toast.success('Тренер подтвердил тренировку 👏');
      } else if (t === 'session.started' && sess.started_by === 'coach'
                 && sess.plan_id === plan?.id
                 && sess.week_index === planWeek
                 && sess.day_index === selectedDayIndex) {
        hapticNotify('success');
        toast.message('Тренер начал тренировку', { description: sess.title || '' });
      }
    } else if (t.startsWith('plan') || t.startsWith('week') || t.startsWith('training_days')) {
      reloadPlan();
      refreshProgress();
      if (t === 'plan.published') toast.message('Тренер открыл вам программу 💪');
    }
  }, [refreshProgress, reloadPlan, plan?.id, planWeek, selectedDayIndex]);

  useRealtime({
    planId: plan?.id || null,
    enabled: !!plan?.id,
    onEvent: onRtEvent,
  });

  // Загрузка активной сессии выбранного дня
  useEffect(() => {
    if (!plan?.id || !dayDetail || isRestSelected || !user?.telegram_id) { setSession(null); return undefined; }
    let cancelled = false;
    (async () => {
      try {
        const s = await getActiveSession({
          plan_id: plan.id, week: planWeek, day: selectedDayIndex,
          athlete: user.telegram_id, date: toISODate(selectedDate),
        });
        if (!cancelled) setSession(s);
      } catch (e) {
        if (!cancelled) setSession(null);
      }
    })();
    return () => { cancelled = true; };
  }, [plan?.id, planWeek, selectedDayIndex, isRestSelected, dayDetail, user?.telegram_id, selectedDate]);

  // Превью дня (до старта тренировки)
  const previewView = useMemo(() => {
    if (!dayDetail || dayDetail.is_rest) return null;
    const exs = (dayDetail.exercises || []).map((e) => ({ ...e, status: 'pending' }));
    const tonnage = exs.reduce((s, e) => s + (Number(e.tonnage) || 0), 0);
    const estSec = exs.reduce((s, e) => {
      const sets = (e.sets_scheme || []).reduce((a, x) => a + (Number(x.sets) || 0), 0);
      return s + sets * 130;
    }, 0);
    return {
      status: 'not_started',
      title: dayDetail.title,
      exercises: exs,
      stats: {
        tonnage: Math.round(tonnage),
        group: dayDetail.group,
        difficulty: dayDetail.difficulty,
        duration_sec: estSec,
        done_count: 0,
        total_count: exs.length,
        progress_pct: 0,
      },
    };
  }, [dayDetail]);

  const view = session || previewView;

  // Оригинальные подходы дня из плана (по позиции упражнения) — для диффа правок
  const planSetsByOrder = useMemo(() => {
    if (!plan?.weeks) return {};
    const wk = plan.weeks.find((w) => w.week_index === planWeek);
    if (!wk) return {};
    const day = (wk.days || []).find((d) => d.day_index === selectedDayIndex);
    if (!day) return {};
    const sorted = [...(day.exercises || [])].sort((a, b) => (a.order || 0) - (b.order || 0));
    const map = {};
    sorted.forEach((e, i) => { map[i] = e.sets_scheme || []; });
    return map;
  }, [plan, planWeek, selectedDayIndex]);

  const doStart = async () => {
    setConfirmStartOpen(false);
    if (!plan) { toast.info('Сначала выберите программу'); return; }
    setStarting(true);
    try {
      const s = await startSession({
        plan_id: plan.id, athlete_telegram_id: user.telegram_id,
        week: planWeek, day: selectedDayIndex, date: toISODate(selectedDate),
      });
      setSession(s);
      hapticNotify('success');
      refreshProgress();
    } catch (e) {
      if (e?.response?.status === 409) {
        const msg = e.response.data?.detail?.message
          || 'У вас уже есть активная тренировка. Завершите её, чтобы начать новую.';
        toast.error(msg);
      } else {
        toast.error('Не удалось начать тренировку');
      }
    } finally {
      setStarting(false);
    }
  };

  const handleStart = () => {
    if (!plan) { toast.info('Сначала выберите программу'); return; }
    if (isRestSelected) { toast.info('Сегодня день отдыха 💤'); return; }
    haptic('light');
    // Если выбранный день — не сегодня, спросить подтверждение
    if (!isSameDay(selectedDate, new Date())) {
      setConfirmStartOpen(true);
      return;
    }
    doStart();
  };

  const handleAction = async (order, action) => {
    if (!session) return;
    haptic(action === 'done' ? 'medium' : 'light');
    try {
      const s = await sessionExerciseAction(session.id, order, action);
      setSession(s);
      refreshProgress();
      if (s.status === 'finished') {
        hapticNotify('success');
        toast.success('Тренировка завершена! 🎉');
      }
    } catch (e) {
      hapticNotify('error');
      toast.error('Не удалось обновить упражнение');
    }
  };

  const handleEditSave = async (order, body) => {
    if (!session) return;
    try {
      const s = await editSessionExercise(session.id, order, body);
      setSession(s);
      toast.success('Упражнение обновлено');
    } catch (e) {
      toast.error('Не удалось сохранить');
      throw e;
    }
  };

  const handleSetLog = async (order, setIndex, body) => {
    if (!session) return;
    if (body && body.done !== undefined) haptic(body.done ? 'medium' : 'light');
    try {
      const s = await logSessionSet(session.id, order, setIndex, body);
      setSession(s);
      refreshProgress();
      if (s.status === 'finished') {
        hapticNotify('success');
        toast.success('Тренировка завершена! 🎉');
      }
    } catch (e) {
      hapticNotify('error');
      toast.error('Не удалось сохранить подход');
    }
  };

  const handlePauseToggle = async () => {
    if (!session) return;
    haptic('light');
    try {
      const s = await pauseSession(session.id, session.paused);
      setSession(s);
    } catch (e) { /* no-op */ }
  };

  const handleStop = async () => {
    if (!session) return;
    haptic('medium');
    try {
      const s = await finishSession(session.id);
      setSession(s);
      hapticNotify('success');
      refreshProgress();
      toast.success('Тренировка завершена');
    } catch (e) { /* no-op */ }
  };

  const handleResume = async () => {
    if (!session) return;
    haptic('medium');
    setStarting(true);
    try {
      const s = await resumeSession(session.id);
      setSession(s);
      hapticNotify('success');
      refreshProgress();
      toast.success('Тренировка возобновлена');
    } catch (e) {
      if (e?.response?.status === 409) {
        const msg = e.response.data?.detail?.message
          || 'У вас уже есть активная тренировка. Завершите её, чтобы продолжить эту.';
        toast.error(msg);
      } else {
        toast.error('Не удалось продолжить тренировку');
      }
    } finally {
      setStarting(false);
    }
  };

  const sessionStatus = session?.status;
  const allExercisesResolved = useMemo(() => {
    if (sessionStatus !== 'finished') return false;
    const exs = session?.exercises || [];
    return exs.length > 0 && exs.every((e) => e.status === 'done' || e.status === 'skipped');
  }, [session, sessionStatus]);

  // Telegram native MainButton mirrors the primary CTA (no-op off-Telegram).
  const tgMainVisible =
    canLogStrength &&
    !!plan &&
    !isRestSelected &&
    (sessionStatus === 'in_progress' || (sessionStatus === 'finished' && !allExercisesResolved) || (!session && !!previewView));
  useMainButton({
    enabled: true,
    visible: tgMainVisible,
    text:
      sessionStatus === 'in_progress'
        ? 'Завершить тренировку'
        : sessionStatus === 'finished'
        ? 'Продолжить тренировку'
        : 'Начать тренировку',
    disabled: starting || !plan,
    progress: starting,
    onClick:
      sessionStatus === 'in_progress'
        ? handleStop
        : sessionStatus === 'finished'
        ? handleResume
        : handleStart,
  });

  return (
    <div className="date-selector" data-testid="date-selector">
      <div className="date-selector-row">
        {/* Индикатор-точки: вертикально, слева от карточек (прошлая/текущая/следующая) */}
        <div
          className="week-dots"
          role="tablist"
          aria-label="Выбор тренировочной недели"
          data-testid="week-dots"
        >
          {WEEK_OFFSETS.map((offset) => {
            const isActive = effectiveOffset === offset;
            const dotWeek = baseWeek + offset;
            const dotDisabled = totalWeeks > 0 && (dotWeek < 1 || dotWeek > totalWeeks);
            const label =
              offset === 0
                ? 'Текущая неделя'
                : offset > 0
                ? `Через ${offset} нед.`
                : `${Math.abs(offset)} нед. назад`;
            return (
              <button
                key={offset}
                type="button"
                className={`week-dot ${isActive ? 'week-dot-active' : ''} ${dotDisabled ? 'week-dot-disabled' : ''}`}
                onClick={() => handleWeekDotClick(offset)}
                disabled={dotDisabled}
                role="tab"
                aria-selected={isActive}
                aria-label={label}
                data-testid={`week-dot-${offset}`}
              />
            );
          })}
        </div>

        {/* Дни недели — горизонтальный скролл (не перекрывает точки) */}
        <div className="date-selector-scroll" data-testid="date-selector-scroll">
          {weekDays.map((day, index) => (
            <DayCard
              key={`${weekOffset}-${index}`}
              date={day.date}
              dayName={day.dayName}
              dayNumber={day.dayNumber}
              progress={day.progress}
              isWorkout={day.isWorkout}
              isSelected={isSameDay(day.date, selectedDate)}
              onClick={(e) => handleDayClick(day.date, e)}
              index={index}
              animClass={
                slideDir === 'next'
                  ? 'card-anim-next'
                  : slideDir === 'prev'
                  ? 'card-anim-prev'
                  : ''
              }
            />
          ))}
        </div>
      </div>

      {/* Кнопка «План» — открыть любую неделю плана */}
      {plan && !isDraft && totalWeeks > 1 ? (
        <div className="plan-week-row">
          <button
            type="button"
            className="plan-week-btn"
            onClick={() => { hapticSelection(); setWeekPickerOpen(true); }}
            data-testid="plan-week-btn"
          >
            План
          </button>
        </div>
      ) : null}

      <div className="date-title-row">
        <h2 className="selected-date-title">{formattedDate}</h2>
        <div className="date-actions" data-testid="date-actions">
          {sessionStatus === 'in_progress' ? (
            <>
              <button className="icon-btn" type="button" onClick={handlePauseToggle}
                aria-label={session.paused ? 'Продолжить' : 'Пауза'} data-testid="btn-pause">
                {session.paused ? <Play size={18} strokeWidth={2.2} color="#CACACA" /> : <Pause size={18} strokeWidth={2.2} color="#CACACA" />}
              </button>
              <button className="icon-btn" type="button" onClick={handleStop}
                aria-label="Завершить" data-testid="btn-stop">
                <Square size={15} strokeWidth={2.6} color="#CACACA" />
              </button>
            </>
          ) : sessionStatus === 'finished' ? (
            allExercisesResolved ? (
              <button
                className="icon-btn info-btn"
                type="button"
                data-testid="session-info-button"
                onClick={() => setInfoOpen(true)}
                aria-label="Информация о тренировке"
                title="Информация о тренировке"
              >
                <Info size={18} strokeWidth={2.2} color="#CACACA" />
              </button>
            ) : (
              <button
                className="launch-button launch-button-restart"
                type="button"
                data-testid="resume-button"
                onClick={handleResume}
                disabled={starting}
              >
                <Play className="launch-button-icon" size={16} strokeWidth={2.5} />
                <span>{starting ? 'Загрузка…' : 'Продолжить'}</span>
              </button>
            )
          ) : !isRestSelected && canLogStrength ? (
            <button
              className="launch-button"
              type="button"
              data-testid="launch-button"
              onClick={handleStart}
              disabled={!plan || starting}
            >
              <Zap className="launch-button-icon" size={16} strokeWidth={2.5} />
              <span>{starting ? 'Запуск…' : 'Начать'}</span>
            </button>
          ) : null}
        </div>
      </div>

      {/* Нет активной программы */}
      {!planLoading && !plan ? (
        <div className="no-plan-card" data-testid="no-plan-card">
          <p className="no-plan-text">У вас пока нет активной программы.</p>
          <Link to="/programs" className="no-plan-button" data-testid="choose-program-button">
            Выбрать программу
          </Link>
        </div>
      ) : null}

      {/* Тренер готовит план (черновик) */}
      {isDraft ? (
        <div className="no-plan-card" data-testid="plan-preparing-card">
          <p className="no-plan-text">
            Ваш тренер готовит для вас программу. Она появится здесь, как только тренер её опубликует. 💪
          </p>
        </div>
      ) : null}

      {/* День отдыха */}
      {plan && !isDraft && isRestSelected ? (
        <div className="rest-day-note" data-testid="rest-day-note">
          День отдыха — восстановление 💤
        </div>
      ) : null}

      {/* Тренировка дня */}
      {plan && !isDraft && !isRestSelected && view ? (
        <WorkoutView
          view={view}
          isPreview={!session}
          paused={!!session?.paused}
          readOnly={!canLogStrength}
          onAction={handleAction}
          onEditSave={handleEditSave}
          onSetLog={handleSetLog}
          forecastBySlug={forecastBySlug}
          currentWeek={planWeek}
          planSetsByOrder={planSetsByOrder}
        />
      ) : null}

      {/* Подтверждение старта тренировки не на сегодня */}
      {confirmStartOpen ? (
        <Portal>
        <div className="confirm-overlay" onClick={() => setConfirmStartOpen(false)} data-testid="confirm-start-modal">
          <div className="confirm-modal" onClick={(e) => e.stopPropagation()}>
            <h3 className="confirm-title">Тренировка не на сегодня</h3>
            <p className="confirm-text">
              Выбранный день — {formattedDate}, а не сегодня. Начать тренировку всё равно?
            </p>
            <div className="confirm-actions">
              <button className="confirm-btn-cancel" onClick={() => setConfirmStartOpen(false)}>
                Отмена
              </button>
              <button className="confirm-btn-ok" onClick={doStart} data-testid="confirm-start-ok" disabled={starting}>
                {starting ? 'Запуск…' : 'Начать'}
              </button>
            </div>
          </div>
        </div>
        </Portal>
      ) : null}
      {/* Модалка «План» — выбор любой недели */}
      {weekPickerOpen ? (
        <Portal>
        <div className="confirm-overlay" onClick={() => setWeekPickerOpen(false)} data-testid="week-picker-modal">
          <div className="confirm-modal week-picker" onClick={(e) => e.stopPropagation()}>
            <h3 className="confirm-title">Выберите неделю</h3>
            <p className="confirm-text">Текущая неделя плана — {baseWeek}.</p>
            <div className="week-picker-grid" data-testid="week-picker-grid">
              {Array.from({ length: totalWeeks }, (_, i) => i + 1).map((wk) => {
                const locked = isWeekLocked(wk);
                return (
                  <button
                    key={wk}
                    type="button"
                    className={`week-pick ${wk === planWeek ? 'active' : ''} ${wk === baseWeek ? 'is-current' : ''} ${locked ? 'is-locked' : ''}`}
                    onClick={() => goToWeek(wk)}
                    disabled={locked}
                    data-testid={`week-pick-${wk}`}
                    aria-current={wk === planWeek}
                    title={locked ? 'Неделя ещё не открыта тренером' : undefined}
                  >
                    {locked ? <Lock size={12} aria-hidden="true" /> : wk}
                    {wk === baseWeek && !locked ? <span className="week-pick-cur" aria-hidden="true" /> : null}
                  </button>
                );
              })}
            </div>
            <div className="confirm-actions">
              <button className="confirm-btn-cancel" onClick={() => setWeekPickerOpen(false)}>
                Закрыть
              </button>
            </div>
          </div>
        </div>
        </Portal>
      ) : null}

      {/* Инфо-модалка о завершённой тренировке */}
      {infoOpen && session ? (
        <Portal>
        <div className="confirm-overlay" onClick={() => setInfoOpen(false)} data-testid="session-info-modal">
          <div className="confirm-modal session-info-modal" onClick={(e) => e.stopPropagation()}>
            <h3 className="confirm-title">
              <Info size={18} style={{ verticalAlign: '-3px', marginRight: '6px', color: '#ff8a24' }} />
              Тренировка завершена
            </h3>
            <p className="session-info-day">{session.title || `День ${session.day_index || ''}`}</p>
            <div className="session-info-rows" data-testid="session-info-rows">
              <div className="session-info-row">
                <span className="session-info-lbl">Дата</span>
                <span className="session-info-val">{formattedDate}</span>
              </div>
              <div className="session-info-row">
                <span className="session-info-lbl">Неделя плана</span>
                <span className="session-info-val">{planWeek} из {(plan?.weeks?.length) || 1}</span>
              </div>
              {(() => {
                const exs = session?.exercises || [];
                const done = exs.filter((e) => e.status === 'done').length;
                const skipped = exs.filter((e) => e.status === 'skipped').length;
                const totalTonnage = exs.reduce((sum, e) => {
                  return sum + ((e.sets || []).reduce((s, x) => {
                    const w = Number(x.weight) || 0;
                    const r = Number(x.reps) || 0;
                    return s + w * r;
                  }, 0));
                }, 0);
                return (
                  <>
                    <div className="session-info-row">
                      <span className="session-info-lbl">Выполнено упражнений</span>
                      <span className="session-info-val session-info-strong">{done} из {exs.length}</span>
                    </div>
                    {skipped > 0 ? (
                      <div className="session-info-row">
                        <span className="session-info-lbl">Пропущено</span>
                        <span className="session-info-val">{skipped}</span>
                      </div>
                    ) : null}
                    {totalTonnage > 0 ? (
                      <div className="session-info-row">
                        <span className="session-info-lbl">Тоннаж</span>
                        <span className="session-info-val session-info-strong">
                          {totalTonnage >= 1000 ? `${(totalTonnage / 1000).toFixed(1)} т` : `${Math.round(totalTonnage)} кг`}
                        </span>
                      </div>
                    ) : null}
                    {session.duration_sec ? (
                      <div className="session-info-row">
                        <span className="session-info-lbl">Время</span>
                        <span className="session-info-val">
                          {Math.floor(session.duration_sec / 60)} мин
                        </span>
                      </div>
                    ) : null}
                  </>
                );
              })()}
            </div>
            <div className="confirm-actions">
              <button className="confirm-btn-cancel" onClick={() => setInfoOpen(false)} data-testid="session-info-close">
                Закрыть
              </button>
            </div>
          </div>
        </div>
        </Portal>
      ) : null}
    </div>
  );
};

export default DateSelector;
