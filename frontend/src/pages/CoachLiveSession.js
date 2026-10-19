import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Wifi, WifiOff, CheckCircle2, Dumbbell, Radio, Square, Play } from "lucide-react";
import { toast } from "sonner";
import { useUser } from "@/context/UserContext";
import {
  getUserById, getCoachClientPlan, getCoachClientSession,
  sessionExerciseAction, editSessionExercise, finishSession, resumeSession, logSessionSet,
  startSession,
} from "@/api";
import WorkoutView from "@/components/WorkoutView";
import { useRealtime } from "@/hooks/useRealtime";
import { useCapabilities } from "@/hooks/useCapabilities";
import { haptic, hapticNotify } from "@/lib/platform";
import { useBackButton } from "@/hooks/useTelegramUI";
import "./Coach.css";
import "./CoachLive.css";

const avatarFor = (a) => {
  if (a?.picture) return a.picture;
  const name = encodeURIComponent(a?.first_name || "U");
  return `https://ui-avatars.com/api/?name=${name}&background=FF6B00&color=fff&size=80&bold=true`;
};

const DOW = { 1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс" };
const todayWeekday = () => {
  const jd = new Date().getDay(); // 0=Вс..6=Сб
  return jd === 0 ? 7 : jd;
};

export default function CoachLiveSession() {
  const { athleteId } = useParams();
  const aid = Number(athleteId);
  const { user } = useUser();
  const { can } = useCapabilities();
  const coachId = user?.telegram_id;
  const navigate = useNavigate();
  useBackButton(true, () => navigate(`/coach/${aid}`));

  const [athlete, setAthlete] = useState(null);
  const [plan, setPlan] = useState(null);
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const sessionRef = useRef(null);
  useEffect(() => { sessionRef.current = session; }, [session]);

  // ---- загрузка / REST-«догон» ----
  const refetchSession = useCallback(async () => {
    if (!coachId || !aid) return;
    try {
      const s = await getCoachClientSession(coachId, aid);
      setSession(s || null);
    } catch (e) {
      /* no-op */
    }
  }, [coachId, aid]);

  const refetchPlan = useCallback(async () => {
    if (!coachId || !aid) return;
    try {
      const p = await getCoachClientPlan(coachId, aid).catch(() => null);
      setPlan(p);
    } catch (e) {
      /* no-op */
    }
  }, [coachId, aid]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!coachId || !aid) return;
      setLoading(true);
      try {
        const a = await getUserById(aid).catch(() => null);
        if (!cancelled) setAthlete(a);
        const p = await getCoachClientPlan(coachId, aid).catch((e) => {
          if (e?.response?.status === 403) toast.error("Нет доступа к этому спортсмену");
          return null;
        });
        if (!cancelled) setPlan(p);
        const s = await getCoachClientSession(coachId, aid).catch(() => null);
        if (!cancelled) setSession(s || null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [coachId, aid]);

  // ---- real-time ----
  const onEvent = useCallback((evt) => {
    const t = evt.type || "";
    if (t.startsWith("session.")) {
      const sess = evt.payload?.session;
      if (sess && sess.athlete_telegram_id === aid) {
        setSession(sess);
        if (t === "session.started") {
          hapticNotify("success");
          toast.message("Спортсмен начал тренировку", { description: sess.title || "" });
        }
      } else {
        refetchSession();
      }
    } else if (t.startsWith("plan") || t.startsWith("week") || t.startsWith("training_days")) {
      refetchPlan();
    }
  }, [aid, refetchSession, refetchPlan]);

  const { connected, online } = useRealtime({ planId: plan?.id || null, enabled: !!plan?.id, onEvent });

  // Polling fallback, когда WebSocket недоступен (ingress/сеть)
  useEffect(() => {
    if (connected) return undefined;
    const t = setInterval(() => { refetchSession(); }, 4000);
    return () => clearInterval(t);
  }, [connected, refetchSession]);

  const athleteOnline = useMemo(
    () => (online || []).some((o) => Number(o.telegram_id) === aid),
    [online, aid]
  );

  // ---- производные данные для карточек (дифф/прогноз) ----
  const planSetsByOrder = useMemo(() => {
    if (!plan?.weeks || !session) return {};
    const wk = plan.weeks.find((w) => w.week_index === session.week_index);
    if (!wk) return {};
    const day = (wk.days || []).find((d) => d.day_index === session.day_index);
    if (!day) return {};
    const sorted = [...(day.exercises || [])].sort((a, b) => (a.order || 0) - (b.order || 0));
    const map = {};
    sorted.forEach((e, i) => { map[i] = e.sets_scheme || []; });
    return map;
  }, [plan, session]);

  const forecastBySlug = useMemo(() => {
    if (!plan?.weeks) return {};
    const topWeight = (ex) => {
      const ws = (ex.sets_scheme || []).map((s) => s.weight).filter((w) => w !== null && w !== undefined);
      return ws.length ? Math.max(...ws) : null;
    };
    const bySlug = {};
    [...plan.weeks].sort((a, b) => (a.week_index || 0) - (b.week_index || 0)).forEach((w) => {
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
      map[slug] = Object.keys(wk).map(Number).sort((a, b) => a - b).map((wki) => ({ week: wki, value: wk[wki] }));
    });
    return map;
  }, [plan]);

  // ---- действия тренера (co-scribe) ----
  const handleAction = async (order, action) => {
    if (!session) return;
    haptic(action === "done" ? "medium" : "light");
    try {
      const s = await sessionExerciseAction(session.id, order, action, "coach", coachId);
      setSession(s);
    } catch (e) {
      hapticNotify("error");
      toast.error(e?.response?.status === 403 ? "Нет доступа" : "Не удалось обновить упражнение");
    }
  };

  const handleEditSave = async (order, body) => {
    if (!session) return;
    try {
      const s = await editSessionExercise(session.id, order, body, "coach", coachId);
      setSession(s);
      toast.success("Упражнение обновлено");
    } catch (e) {
      toast.error("Не удалось сохранить");
    }
  };

  const handleSetLog = async (order, setIndex, body) => {
    if (!session) return;
    if (body && body.done !== undefined) haptic(body.done ? "medium" : "light");
    try {
      const s = await logSessionSet(session.id, order, setIndex, body, "coach", coachId);
      setSession(s);
    } catch (e) {
      hapticNotify("error");
      toast.error(e?.response?.status === 403 ? "Нет доступа" : "Не удалось сохранить подход");
    }
  };

  const handleFinishSession = async () => {
    if (!session) return;
    setBusy(true);
    try {
      const s = await finishSession(session.id);
      setSession(s);
      hapticNotify("success");
      toast.success("Тренировка завершена");
    } catch (e) {
      toast.error("Не удалось завершить тренировку");
    } finally {
      setBusy(false);
    }
  };

  const handleResumeSession = async () => {
    if (!session) return;
    setBusy(true);
    try {
      const s = await resumeSession(session.id);
      setSession(s);
      hapticNotify("success");
      toast.success("Тренировка возобновлена");
    } catch (e) {
      if (e?.response?.status === 409) {
        toast.error(e.response.data?.detail?.message || "У спортсмена уже есть активная тренировка");
      } else {
        toast.error("Не удалось продолжить тренировку");
      }
    } finally {
      setBusy(false);
    }
  };

  // ---- старт тренировки «под диктовку тренера» ----
  const startWeek = plan?.current_week || 1;
  const startDays = useMemo(() => {
    if (!plan?.weeks) return [];
    const wk = plan.weeks.find((w) => w.week_index === startWeek);
    if (!wk) return [];
    return (wk.days || []).filter((d) => !d.is_rest && (d.exercises || []).length > 0);
  }, [plan, startWeek]);
  const [startDay, setStartDay] = useState(null);
  useEffect(() => {
    if (startDays.length && startDay == null) {
      const wd = todayWeekday();
      const found = startDays.find((d) => d.day_index === wd);
      setStartDay(found ? found.day_index : startDays[0].day_index);
    }
  }, [startDays, startDay]);

  const handleStartForAthlete = async () => {
    if (!plan || startDay == null) return;
    setBusy(true);
    try {
      const dateISO = new Date().toISOString().slice(0, 10);
      const s = await startSession({
        plan_id: plan.id,
        athlete_telegram_id: aid,
        week: startWeek,
        day: startDay,
        date: dateISO,
        coach_telegram_id: coachId,
      });
      setSession(s);
      hapticNotify("success");
      toast.success("Тренировка начата");
    } catch (e) {
      if (e?.response?.status === 409) {
        toast.error(e.response.data?.detail?.message || "У спортсмена уже есть активная тренировка");
      } else if (e?.response?.status === 403) {
        toast.error("Нет доступа к этому спортсмену");
      } else {
        toast.error("Не удалось начать тренировку");
      }
    } finally {
      setBusy(false);
    }
  };

  const athleteName = athlete?.first_name || "Спортсмен";
  const status = session?.status;
  const isLive = status === "in_progress";
  const isFinished = status === "finished";

  const statusLabel = !session
    ? "Тренировка не идёт"
    : isLive
    ? (session.paused ? "На паузе" : "Идёт тренировка")
    : isFinished
    ? "Тренировка завершена"
    : "Не начата";

  return (
    <div className="coach-page coach-live-page" data-testid="coach-live-page">
      <header className="coach-header">
        <button className="coach-back" onClick={() => navigate(`/coach/${aid}`)} aria-label="Назад" data-testid="coach-live-back">
          <ArrowLeft size={22} />
        </button>
        <h1 className="coach-title">Тренировка вживую</h1>
        <span
          className={`rt-chip ${connected ? "rt-on" : "rt-off"}`}
          title={connected ? "Real-time соединение активно" : "Нет соединения — обновление опросом"}
          data-testid="rt-status"
        >
          {connected ? <Wifi size={14} /> : <WifiOff size={14} />}
        </span>
      </header>

      {/* Шапка спортсмена */}
      <div className="cl-athlete" data-testid="cl-athlete">
        <div className="cl-ava-wrap">
          <img className="cl-ava" src={avatarFor(athlete)} alt="" />
          <span className={`cl-presence ${athleteOnline ? "is-online" : ""}`} title={athleteOnline ? "Спортсмен в приложении" : "Спортсмен оффлайн"} />
        </div>
        <div className="cl-athlete-main">
          <div className="cl-athlete-name">{athleteName}</div>
          <div className={`cl-status ${isLive ? "live" : ""}`} data-testid="cl-status">
            {isLive ? <span className="live-dot" /> : <Radio size={13} />}
            {statusLabel}
            {session?.title ? <span className="cl-status-sub"> · {session.title}</span> : null}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="coach-empty">Загрузка…</div>
      ) : !plan ? (
        <div className="coach-noplan" data-testid="cl-noplan">
          <Dumbbell size={26} />
          <p>У спортсмена нет активной программы.</p>
          <button className="coach-primary-btn is-secondary" onClick={() => navigate(`/coach/${aid}`)}>
            К карточке подопечного
          </button>
        </div>
      ) : !session ? (
        <div className="cl-empty" data-testid="cl-no-session">
          <div className="cl-empty-ico"><Radio size={30} /></div>
          <p className="cl-empty-title">Сейчас тренировка не идёт</p>
          <p className="cl-empty-sub">
            Дождитесь, пока спортсмен нажмёт «Начать», или запустите тренировку сами — под диктовку
            {connected ? " (соединение активно)." : "."}
          </p>
          {startDays.length ? (
            <div className="cl-start-box" data-testid="cl-start-box">
              <div className="cl-start-label">Неделя {startWeek} · выберите день</div>
              <div className="cl-start-days">
                {startDays.map((d) => (
                  <button
                    key={d.day_index}
                    type="button"
                    className={`cl-day-chip ${startDay === d.day_index ? "active" : ""}`}
                    onClick={() => setStartDay(d.day_index)}
                    data-testid={`cl-start-day-${d.day_index}`}
                  >
                    <span className="cl-day-chip-dow">{DOW[d.day_index]}</span>
                    <span className="cl-day-chip-title">{d.title || "Тренировка"}</span>
                  </button>
                ))}
              </div>
              <button
                className="coach-primary-btn cl-start-btn"
                onClick={handleStartForAthlete}
                disabled={busy || startDay == null}
                data-testid="cl-start-for-athlete-btn"
              >
                <Play size={16} /> Начать тренировку за спортсмена
              </button>
            </div>
          ) : null}
        </div>
      ) : (
        <>
          {/* Завершение / продолжение тренировки */}
          <div className="cl-confirm-bar" data-testid="cl-confirm-bar">
            {isFinished ? (
              <div className="cl-finished-bar">
                <div className="cl-confirmed" data-testid="cl-finished">
                  <CheckCircle2 size={18} /> Тренировка завершена
                </div>
                <button
                  className="coach-primary-btn is-secondary"
                  onClick={handleResumeSession}
                  disabled={busy}
                  data-testid="cl-resume-session-btn"
                >
                  <Play size={16} /> Продолжить тренировку
                </button>
              </div>
            ) : (
              <div className="cl-live-bar">
                <button
                  className="coach-primary-btn"
                  onClick={handleFinishSession}
                  disabled={busy}
                  data-testid="cl-finish-session-btn"
                >
                  <Square size={16} /> Завершить тренировку
                </button>
              </div>
            )}
          </div>

          <WorkoutView
            view={session}
            isPreview={false}
            mode="coach"
            paused={!!session.paused}
            readOnly={!can("log_strength")}
            onAction={handleAction}
            onEditSave={handleEditSave}
            onSetLog={handleSetLog}
            forecastBySlug={forecastBySlug}
            currentWeek={session.week_index}
            planSetsByOrder={planSetsByOrder}
          />
        </>
      )}
    </div>
  );
}
