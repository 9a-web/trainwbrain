import React, { Suspense, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, BarChart3, CheckCircle2, Clock3, Dumbbell, Flame, Loader2, Sparkles, Target, XCircle } from "lucide-react";
import { useUser } from "@/context/UserContext";
import { getSession, getSessionMuscleMap } from "@/api";
import { useBackButton } from "@/hooks/useTelegramUI";
import { muscleLabel } from "@/lib/muscles";
import "./SessionDetail.css";

const MuscleBody3D = React.lazy(() => import("@/components/MuscleBody3D"));

const fmtDateTime = (value) => {
  if (!value) return "";
  try {
    return new Date(value).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
  } catch (e) { return ""; }
};
const fmtDuration = (seconds) => {
  const m = Math.round((Number(seconds) || 0) / 60);
  if (!m) return "—";
  return m < 60 ? `${m} мин` : `${Math.floor(m / 60)} ч ${m % 60 ? `${m % 60} мин` : ""}`.trim();
};

function MiniMetric({ icon: Icon, value, label }) {
  return <div className="session-metric"><span><Icon size={15} /></span><b>{value}</b><small>{label}</small></div>;
}

function muscleRows(load) {
  return load?.muscle_load?.muscles || load?.muscles || {};
}

function buildRegions(load) {
  const muscles = muscleRows(load);
  const mapped = Object.fromEntries(Object.entries(muscles).map(([key, value]) => [key, {
    intensity_0_1: Number(value?.load_0_1 ?? value?.intensity_0_1 ?? 0),
    working_sets: Number(value?.sets || value?.working_sets || 0),
    volume_kg: Number(value?.mechanical_kg || value?.volume_kg || 0),
    sessions: 1,
    load_sum: Number(value?.load_0_1 || value?.intensity_0_1 || 0),
  }]));
  // The single-session endpoint also returns canonical map regions. Keep their
  // exact intensities when available, since those are the values rendered by 3D.
  return Object.keys(load?.regions || {}).length ? load.regions : mapped;
}

export default function SessionDetail() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [load, setLoad] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [mapError, setMapError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [view, setView] = useState("front");
  useBackButton(true, () => navigate(-1));

  // Отчёт и карта мышц загружаются независимо: сбой 3D-аналитики не должен
  // скрывать саму тренировку (тоннаж, упражнения, подходы).
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    setSession(null);
    setLoad(null);
    setMapError(false);
    (async () => {
      try {
        const s = await getSession(sessionId);
        if (!alive) return;
        setSession(s);
        setLoading(false);
      } catch (e) {
        if (!alive) return;
        const status = e?.response?.status;
        setError(status === 404 ? "notfound" : status === 403 ? "forbidden" : "network");
        setLoading(false);
        return;
      }
      try {
        const m = await getSessionMuscleMap(sessionId);
        if (alive) setLoad(m);
      } catch (e) {
        if (alive) setMapError(true);
      }
    })();
    return () => { alive = false; };
  }, [sessionId, retry]);

  const regions = useMemo(() => buildRegions(load), [load]);
  const trained = useMemo(() => Object.entries(muscleRows(load))
    .filter(([, item]) => Number(item?.sets || item?.working_sets || 0) > 0 || Number(item?.load_0_1 || item?.intensity_0_1 || 0) > 0)
    .sort((a, b) => Number(b[1]?.load_0_1 ?? b[1]?.intensity_0_1 ?? 0) - Number(a[1]?.load_0_1 ?? a[1]?.intensity_0_1 ?? 0)), [load]);
  const stats = session?.stats || {};
  const exercises = session?.exercises || [];

  if (loading) return <div className="session-detail-state"><Loader2 className="twb-spin" size={24} /> Загружаем отчёт…</div>;
  if (error || !session) {
    const text = error === "notfound"
      ? "Тренировка не найдена"
      : error === "forbidden"
      ? "Нет доступа к этой тренировке"
      : "Не удалось открыть тренировку";
    return (
      <div className="session-detail-state" data-testid="session-detail-error">
        <XCircle size={28} /><b>{text}</b>
        <small>{error === "network" ? "Проверьте соединение и попробуйте снова." : "Возможно, запись удалена."}</small>
        <div className="session-detail-state-actions">
          {error === "network" ? <button onClick={() => setRetry((v) => v + 1)}>Повторить</button> : null}
          <button onClick={() => navigate(-1)}>Вернуться назад</button>
        </div>
      </div>
    );
  }

  return (
    <div className="session-detail-page" data-testid="session-detail-page">
      <header className="session-detail-header">
        <button type="button" onClick={() => navigate(-1)} aria-label="Назад"><ArrowLeft size={21} /></button>
        <div><span>ОТЧЁТ ТРЕНИРОВКИ</span><h1>{session.title || "Тренировка"}</h1></div>
        <span className="session-complete-badge"><CheckCircle2 size={14} /> завершена</span>
      </header>
      <main className="session-detail-content">
        <div className="session-date-line"><span>{fmtDateTime(session.finished_at || session.date)}</span>{stats.group ? <b>{stats.group}</b> : null}</div>
        <section className="session-summary-card">
          <div><span className="session-kicker">РЕЗУЛЬТАТ</span><strong>{Math.round(stats.tonnage || session.stats?.tonnage || 0).toLocaleString("ru-RU")}<small> кг</small></strong><p>Объём выполненной работы</p></div>
          <div className="session-summary-orb"><Flame size={27} /><b>{stats.progress_pct || 0}%</b><span>план выполнен</span></div>
        </section>
        <div className="session-metrics-grid">
          <MiniMetric icon={Dumbbell} value={`${stats.done_count || 0}/${stats.total_count || exercises.length}`} label="упражнений" />
          <MiniMetric icon={Target} value={stats.sets_done ?? exercises.reduce((a, e) => a + (e.set_logs || []).filter((l) => l.done).length, 0)} label="подходов" />
          <MiniMetric icon={Clock3} value={fmtDuration(stats.duration_sec)} label="длительность" />
          <MiniMetric icon={BarChart3} value={load?.muscle_load?.totals?.muscles_trained || load?.totals?.muscles_trained || trained.length} label="мышц в работе" />
        </div>
        <section className="session-muscle-card">
          <div className="session-section-head"><div><span className="session-kicker">ТОЧЕЧНАЯ АНАЛИТИКА</span><h2>Какие мышцы работали</h2><p>Подсвечены только мышцы этой тренировки</p></div><Sparkles size={18} /></div>
          <div className="session-view-switch"><button className={view === "front" ? "active" : ""} onClick={() => setView("front")}>Спереди</button><button className={view === "back" ? "active" : ""} onClick={() => setView("back")}>Сзади</button></div>
          <div className="session-body-stage">
            {mapError ? <div className="session-model-empty" data-testid="session-map-error"><Sparkles size={24} /><b>Карта мышц недоступна</b><span>Данные тренировки загружены, но точечная аналитика не отвечает.</span><button type="button" onClick={() => setRetry((v) => v + 1)}>Повторить</button></div> : !load ? <div className="session-model-loading"><Loader2 className="twb-spin" size={22} /> Считаем мышечную нагрузку</div> : trained.length ? <Suspense fallback={<div className="session-model-loading"><Loader2 className="twb-spin" size={22} /> Загружаем 3D-модель</div>}><MuscleBody3D regions={regions} view={view} testPrefix="session-body" /></Suspense> : <div className="session-model-empty"><Dumbbell size={24} /><b>Мышечная нагрузка не определена</b><span>В тренировке нет отмеченных выполненных подходов.</span></div>}
          </div>
          {trained.length ? <div className="session-muscle-list">{trained.slice(0, 6).map(([key, value]) => { const intensity = Math.round(Number(value?.load_0_1 ?? value?.intensity_0_1 ?? 0) * 100); return <div className="session-muscle-row" key={key}><span><i style={{ opacity: Math.max(.35, intensity / 100) }} />{muscleLabel(key)}</span><b>{value?.sets || value?.working_sets || 0} подх.</b><em>{intensity}%</em></div>; })}</div> : null}
        </section>
        <section className="session-exercises-card"><div className="session-section-head"><div><span className="session-kicker">ФАКТ</span><h2>Что сделали</h2></div></div><div className="session-exercise-list">{exercises.map((exercise) => { const done = exercise.status === "done"; const logs = (exercise.set_logs || []).filter((l) => l.done); return <div className="session-exercise-row" key={exercise.order}><span className={done ? "done" : "skipped"}>{done ? <CheckCircle2 size={16} /> : <XCircle size={16} />}</span><div><b>{exercise.exercise_name || "Упражнение"}</b><small>{done ? `${logs.length || exercise.sets_scheme?.length || 0} подходов · ${Math.round(exercise.tonnage || 0)} кг` : "Пропущено"}</small></div></div>; })}</div></section>
        {load?.summary ? <p className="session-ai-note"><Sparkles size={15} /> {load.summary}</p> : null}
      </main>
    </div>
  );
}
