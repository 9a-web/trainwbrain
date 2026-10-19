import React, { useEffect, useMemo, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft, Dumbbell, Flame, CalendarDays, Clock,
  ChevronDown, Activity, Trophy, CheckCircle2, XCircle,
  PauseCircle, ShieldCheck, CalendarClock, Zap,
} from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, AreaChart, Area, Line, ComposedChart,
  PieChart, Pie, Cell, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine,
} from "recharts";
import { useUser } from "@/context/UserContext";
import { useBackButton } from "@/hooks/useTelegramUI";
import {
  getActivePlan, getCoachClientPlan, getUserById,
  getDetailedStats, getExerciseProgress,
  getCoachClientStats, getCoachClientExerciseProgress,
  getMuscleMap, getCoachClientMuscleMap,
  getCardioStats,
} from "@/api";
import MuscleGroupsChart from "@/components/MuscleGroupsChart";
import MuscleMapCard from "@/components/MuscleMap";
import "./Stats.css";

const PIE_COLORS = ["#FF8A24", "#FFDA24", "#36C5F0", "#A78BFA", "#34D399", "#FB7185"];

const fmtTon = (kg) => {
  const n = Number(kg) || 0;
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)} т`;
  return `${Math.round(n)} кг`;
};
const fmtDur = (s) => {
  const m = Math.round((Number(s) || 0) / 60);
  if (m < 1) return "—";
  if (m < 60) return `${m} мин`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  return r ? `${h} ч ${r} м` : `${h} ч`;
};
const shortWeek = (w) => (typeof w === "string" ? w.replace(/^\d{4}-W/, "W") : w);
const avatarFallback = (name) =>
  `https://ui-avatars.com/api/?name=${encodeURIComponent(name || "U")}&background=FF6B00&color=fff&size=96&bold=true`;

const SKIP_META = {
  completed: { label: "Выполнено", color: "#34D399", Icon: CheckCircle2 },
  missed: { label: "Пропущено", color: "#FB7185", Icon: XCircle },
  skipped: { label: "Скип", color: "#FFC24B", Icon: PauseCircle },
  excused: { label: "Уважит.", color: "#36C5F0", Icon: ShieldCheck },
  rescheduled: { label: "Перенос", color: "#A78BFA", Icon: CalendarClock },
};

const DYN_TABS = [
  { key: "tonnage", label: "Тоннаж" },
  { key: "frequency", label: "Частота" },
];
const PROG_METRICS = [
  { key: "weight", label: "Вес" },
  { key: "orm", label: "1ПМ" },
  { key: "tonnage", label: "Тоннаж" },
];

function ChartTooltip({ active, payload, label, unit }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="stats-tt">
      <div className="stats-tt-label">{label}</div>
      {payload.map((p) => (
        <div className="stats-tt-row" key={p.dataKey || p.name}>
          <span className="stats-tt-dot" style={{ background: p.color || p.stroke || p.fill }} />
          <span className="stats-tt-name">{p.name}</span>
          <b className="stats-tt-val">
            {typeof p.value === "number" ? p.value.toLocaleString("ru-RU") : p.value}
            {unit ? ` ${unit}` : ""}
          </b>
        </div>
      ))}
    </div>
  );
}

function RingGauge({ value }) {
  const v = Math.max(0, Math.min(100, Math.round(value || 0)));
  const size = 84;
  const stroke = 8;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const gradId = `ring-${React.useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  return (
    <div className="stats-ring-wrap" data-testid="kpi-completion">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="1" x2="1" y2="0">
            <stop offset="0%" stopColor="#FF8A24" />
            <stop offset="100%" stopColor="#FFDA24" />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke="rgba(255,255,255,0.07)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke={`url(#${gradId})`} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={`${(c * v) / 100} ${c}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          className="stats-ring-arc" />
      </svg>
      <div className="stats-ring-center">
        <b>{v}<i>%</i></b>
      </div>
    </div>
  );
}

function TabChips({ tabs, active, onChange, testPrefix }) {
  return (
    <div className="stats-chips-row">
      {tabs.map((t) => (
        <button
          key={t.key}
          className={`stats-tab-chip ${active === t.key ? "active" : ""}`}
          onClick={() => onChange(t.key)}
          data-testid={`${testPrefix}-${t.key}`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

function SectionCard({ title, hint, action, children, testid }) {
  return (
    <section className="stats-card" data-testid={testid}>
      {(title || action) && (
        <div className="stats-card-head">
          <div className="stats-card-titles">
            <h3 className="stats-card-title">{title}</h3>
            {hint ? <span className="stats-card-hint">{hint}</span> : null}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

function Skeleton() {
  return (
    <div className="stats-skel" data-testid="stats-loading">
      <div className="stats-skel-block h150" />
      <div className="stats-skel-row">
        <div className="stats-skel-block h96" />
        <div className="stats-skel-block h96" />
      </div>
      <div className="stats-skel-block h220" />
      <div className="stats-skel-block h220" />
    </div>
  );
}

const CARDIO_TYPE_LABELS = {
  treadmill: "Дорожка", bike: "Велотренажёр", rower: "Гребля",
  walk: "Ходьба", elliptical: "Эллипс", other: "Другое",
};
const CARDIO_TYPE_ICONS = {
  treadmill: "🏃", bike: "🚴", rower: "🚣", walk: "🚶", elliptical: "⛷️", other: "🏋️",
};

/**
 * Фаза 3 — сводка кардио для статистики атлета и подопечного у тренера.
 * Показывает недельную норму и её выполнение (compliance).
 */
function CardioStatsCard({ fetchStats, testPrefix = "cardio" }) {
  const [period, setPeriod] = useState("week");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetchStats({ period })
      .then((d) => { if (alive) setData(d); })
      .catch(() => { if (alive) setData(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [fetchStats, period]);

  if (loading && !data) {
    return <div className="stats-skel-block h150" data-testid={`${testPrefix}-loading`} />;
  }
  if (!data) {
    return <p className="stats-nodata" data-testid={`${testPrefix}-nodata`}>Нет данных по кардио</p>;
  }

  const weeks = [
    { key: "week", label: "7 дней" },
    { key: "month", label: "30 дней" },
  ];
  const pct = data.weekly_target
    ? Math.min(100, Math.round(((data.weekly_minutes || 0) / data.weekly_target) * 100))
    : null;
  const types = Object.entries(data.by_type || {}).sort((a, b) => b[1].minutes - a[1].minutes);

  return (
    <div className="cardio-sum" data-testid={`${testPrefix}-summary`}>
      <div className="cardio-sum-period">
        {weeks.map((w) => (
          <button
            key={w.key} type="button"
            className={period === w.key ? "on" : ""}
            onClick={() => setPeriod(w.key)}
            data-testid={`${testPrefix}-period-${w.key}`}
          >
            {w.label}
          </button>
        ))}
      </div>

      {data.weekly_target ? (
        <div className="cardio-sum-goal" data-testid={`${testPrefix}-goal`}>
          <div className="cardio-sum-goal-top">
            <span>Норма недели</span>
            <b>
              {data.weekly_minutes || 0} / {data.weekly_target} мин
            </b>
          </div>
          <div className="cardio-sum-track">
            <i style={{ width: `${pct}%` }} />
          </div>
          <span className="cardio-sum-goal-note">
            {pct >= 100 ? "Норма выполнена ✓" : `Выполнено ${pct}%`}
          </span>
        </div>
      ) : null}

      <div className="stats-mini-grid">
        <div className="stats-mini" data-testid={`${testPrefix}-minutes`}>
          <Activity size={15} /><b>{data.minutes || 0}</b><span>минут</span>
        </div>
        <div className="stats-mini" data-testid={`${testPrefix}-sessions`}>
          <Dumbbell size={15} /><b>{data.sessions || 0}</b><span>сессий</span>
        </div>
        <div className="stats-mini" data-testid={`${testPrefix}-km`}>
          <Zap size={15} /><b>{data.km || 0}</b><span>км</span>
        </div>
        <div className="stats-mini" data-testid={`${testPrefix}-kcal`}>
          <Flame size={15} /><b>{data.kcal || 0}</b><span>ккал</span>
        </div>
      </div>

      {types.length ? (
        <div className="cardio-sum-types" data-testid={`${testPrefix}-types`}>
          {types.map(([key, v]) => (
            <div className="cardio-sum-type" key={key}>
              <span className="cardio-sum-type-ico">{CARDIO_TYPE_ICONS[key] || "🏋️"}</span>
              <span className="cardio-sum-type-name">{CARDIO_TYPE_LABELS[key] || key}</span>
              <span className="cardio-sum-type-val">{v.minutes} мин</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="stats-nodata" data-testid={`${testPrefix}-empty`}>За период кардио не отмечено</p>
      )}
    </div>
  );
}

function StatsView({ name, avatar, subtitle, onBack, fetchPlanId, fetchDetailed, fetchProgress, fetchMuscleMap, fetchCardio, telegramId, coachId }) {
  const [scope, setScope] = useState("plan"); // 'plan' | 'all'
  const [planId, setPlanId] = useState(undefined); // undefined=loading, null=none
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState(null);
  const [selectedSlug, setSelectedSlug] = useState(null);
  const [dynTab, setDynTab] = useState("tonnage");
  const [progMetric, setProgMetric] = useState("weight");
  // Уникальный префикс SVG-градиентов: id не должны совпадать между инстансами.
  const gid = React.useId().replace(/[^a-zA-Z0-9]/g, "");

  useEffect(() => {
    let alive = true;
    fetchPlanId()
      .then((id) => alive && setPlanId(id || null))
      .catch(() => alive && setPlanId(null));
    return () => { alive = false; };
  }, [fetchPlanId]);

  const planParams = useMemo(
    () => (scope === "plan" && planId ? { plan_id: planId } : {}),
    [scope, planId]
  );

  useEffect(() => {
    if (planId === undefined) return undefined;
    let alive = true;
    setLoading(true);
    fetchDetailed(planParams)
      .then((d) => { if (alive) setData(d); })
      .catch(() => { if (alive) setData(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [planId, planParams, fetchDetailed]);

  useEffect(() => {
    if (planId === undefined) return undefined;
    let alive = true;
    const params = { ...planParams };
    if (selectedSlug) params.slug = selectedSlug;
    fetchProgress(params)
      .then((p) => {
        if (!alive) return;
        setProgress(p);
        if (!selectedSlug && p?.slug) setSelectedSlug(p.slug);
      })
      .catch(() => { if (alive) setProgress(null); });
    return () => { alive = false; };
  }, [planId, planParams, selectedSlug, fetchProgress]);

  const switchScope = (s) => {
    if (s === scope) return;
    setScope(s);
    setSelectedSlug(null);
    setProgress(null);
  };

  const summary = data?.summary || {};
  const empty = !loading && (!data || (summary.total_workouts || 0) === 0);
  const byMicro = scope === "plan" && !!planId; // B10: «микроциклы» только при реальном плане

  const tonnage = data?.tonnage_by_week || [];
  const frequency = data?.frequency_by_week || [];
  const muscles = data?.muscle_distribution || [];
  const orm = data?.one_rep_max_est || [];
  const adherence = data?.adherence || {};
  const skipCounts = data?.skip_counts || {};
  const recent = data?.recent_sessions || [];
  const series = progress?.series || [];
  const exercises = progress?.exercises || [];

  const totalMuscleSets = muscles.reduce((a, m) => a + (m.sets || 0), 0);
  const avgTonnage = tonnage.length
    ? Math.round(tonnage.reduce((a, r) => a + (r.tonnage || 0), 0) / tonnage.length)
    : 0;
  const streakVal = summary.workout_streak ?? summary.streak_days ?? 0;

  const progColor = progMetric === "weight" ? "#FF8A24" : progMetric === "orm" ? "#FFDA24" : "#36C5F0";
  const progKey = progMetric === "weight" ? "top_weight" : progMetric === "orm" ? "one_rm" : "tonnage";
  const progName = progMetric === "weight" ? "Рабочий вес" : progMetric === "orm" ? "1ПМ (оценка)" : "Тоннаж";

  return (
    <div className="stats-page" data-testid="stats-page">
      <div className="stats-ambient" aria-hidden="true" />
      <header className="stats-header">
        <button className="stats-back" onClick={onBack} aria-label="Назад" data-testid="stats-back">
          <ArrowLeft size={22} />
        </button>
        <div className="stats-head-id">
          <span className="stats-head-ava-ring">
            <img className="stats-head-ava" src={avatar || avatarFallback(name)} alt="" />
          </span>
          <div className="stats-head-text">
            <h1 className="stats-title">{name}</h1>
            <span className="stats-subtitle">{subtitle}</span>
          </div>
        </div>
      </header>

      {planId ? (
        <div className="stats-scope" data-testid="stats-scope">
          <button
            className={`stats-scope-btn ${scope === "plan" ? "active" : ""}`}
            onClick={() => switchScope("plan")}
            data-testid="scope-plan"
          >
            По плану
          </button>
          <button
            className={`stats-scope-btn ${scope === "all" ? "active" : ""}`}
            onClick={() => switchScope("all")}
            data-testid="scope-all"
          >
            Всё время
          </button>
        </div>
      ) : null}

      {loading ? (
        <Skeleton />
      ) : empty ? (
        <div className="stats-empty" data-testid="stats-empty">
          <span className="stats-empty-ic"><Activity size={30} /></span>
          <p className="stats-empty-title">Пока нет завершённых тренировок</p>
          <p className="stats-empty-sub">
            Заверши хотя бы одну тренировку — здесь появятся тоннаж, прогресс и графики.
          </p>
        </div>
      ) : (
        <>
          {/* ===== Hero bento ===== */}
          <div className="stats-bento" data-testid="stats-kpis">
            <div className="stats-hero" data-testid="kpi-tonnage">
              <div className="stats-hero-info">
                <span className="stats-metric-label">Общий тоннаж</span>
                <div className="stats-hero-val">
                  {fmtTon(summary.total_tonnage)}
                </div>
                <span className="stats-hero-sub">
                  {data?.plan_name && byMicro ? data.plan_name : "за всё время"}
                </span>
              </div>
              <div className="stats-hero-spark">
                {tonnage.length > 1 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={tonnage} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id={`spark-${gid}`} x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#FF8A24" stopOpacity={0.5} />
                          <stop offset="100%" stopColor="#FF8A24" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <Area type="monotone" dataKey="tonnage" stroke="#FF8A24" strokeWidth={2}
                        fill={`url(#spark-${gid})`} isAnimationActive animationDuration={1200} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : null}
              </div>
            </div>

            <div className="stats-cell stats-cell-ring">
              <RingGauge value={summary.completion_pct} />
              <span className="stats-metric-label">выполнение плана</span>
            </div>

            <div className="stats-cell stats-cell-flame" data-testid="kpi-streak">
              <span className={`stats-flame ${streakVal > 0 ? "lit" : ""}`}>
                <Flame size={26} />
              </span>
              <div className="stats-cell-val">{streakVal}</div>
              <span className="stats-metric-label">серия</span>
            </div>

            <div className="stats-mini" data-testid="kpi-workouts">
              <Dumbbell size={16} />
              <b>{summary.total_workouts || 0}</b>
              <span>тренировок</span>
            </div>
            <div className="stats-mini" data-testid="kpi-freq">
              <CalendarDays size={16} />
              <b>{summary.avg_per_week || 0}</b>
              <span>{byMicro ? "за микроцикл" : "в неделю"}</span>
            </div>
            <div className="stats-mini" data-testid="kpi-duration">
              <Clock size={16} />
              <b>{fmtDur(summary.total_duration_sec)}</b>
              <span>в зале</span>
            </div>
          </div>

          {/* ===== 1ПМ ===== */}
          {orm.length ? (
            <SectionCard title="Одноповторный максимум" hint="факт (Эпли) · план" testid="stats-orm">
              <div className="stats-orm-grid">
                {orm.map((l) => {
                  const main = l.achieved ?? l.planned;
                  const ratio = l.achieved && l.planned
                    ? Math.min(100, Math.round((l.achieved / l.planned) * 100))
                    : null;
                  return (
                    <div className="stats-orm-card" key={l.lift} data-testid={`orm-${l.lift}`}>
                      <Trophy size={15} className="stats-orm-ic" />
                      <div className="stats-orm-name">{l.name}</div>
                      <div className="stats-orm-val">{main != null ? `${main}` : "—"}<span>кг</span></div>
                      <div className="stats-orm-sub">
                        {l.planned != null ? <>план <b>{l.planned}</b></> : "—"}
                        {l.top_weight != null ? <span className="stats-orm-top"> · топ {l.top_weight}</span> : null}
                      </div>
                      {ratio != null ? (
                        <div className="stats-orm-bar">
                          <i style={{ width: `${ratio}%` }} />
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </SectionCard>
          ) : null}

          {/* ===== Динамика: тоннаж / частота ===== */}
          <SectionCard
            title="Динамика"
            hint={byMicro ? "по микроциклам" : "по неделям"}
            testid="stats-dynamics"
            action={<TabChips tabs={DYN_TABS} active={dynTab} onChange={setDynTab} testPrefix="dyn-tab" />}
          >
            {dynTab === "tonnage" ? (
              tonnage.length ? (
                <div className="stats-chart" data-testid="stats-tonnage-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={tonnage} margin={{ top: 14, right: 4, left: -16, bottom: 0 }}>
                      <defs>
                        <linearGradient id={`ton-${gid}`} x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#FFDA24" />
                          <stop offset="100%" stopColor="#FF8A24" />
                        </linearGradient>
                      </defs>
                      <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.05)" />
                      <XAxis dataKey="week" tickFormatter={shortWeek}
                        tick={{ fill: "rgba(255,255,255,0.5)", fontSize: 11 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 11 }} axisLine={false} tickLine={false}
                        width={44} tickFormatter={(v) => (v >= 1000 ? `${Math.round(v / 1000)}т` : v)} />
                      <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} content={<ChartTooltip unit="кг" />} />
                      {avgTonnage > 0 ? (
                        <ReferenceLine y={avgTonnage} stroke="rgba(255,255,255,0.25)" strokeDasharray="4 4"
                          label={{ value: `сред. ${fmtTon(avgTonnage)}`, position: "insideTopRight",
                                   fill: "rgba(255,255,255,0.45)", fontSize: 10 }} />
                      ) : null}
                      <Bar dataKey="tonnage" name="Тоннаж" fill={`url(#ton-${gid})`} radius={[6, 6, 2, 2]}
                        maxBarSize={44} isAnimationActive animationDuration={1200} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="stats-nodata">Недостаточно данных</p>
              )
            ) : frequency.length ? (
              <div className="stats-chart" data-testid="stats-frequency-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={frequency} margin={{ top: 14, right: 4, left: -24, bottom: 0 }}>
                    <defs>
                      <linearGradient id={`freq-${gid}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#7BD8F7" />
                        <stop offset="100%" stopColor="#36C5F0" />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="week" tickFormatter={shortWeek}
                      tick={{ fill: "rgba(255,255,255,0.5)", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 11 }}
                      axisLine={false} tickLine={false} width={28} />
                    <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} content={<ChartTooltip unit="трен." />} />
                    <Bar dataKey="count" name="Тренировок" fill={`url(#freq-${gid})`} radius={[6, 6, 2, 2]}
                      maxBarSize={36} isAnimationActive animationDuration={1200} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="stats-nodata">Недостаточно данных</p>
            )}
          </SectionCard>

          {/* ===== Фаза 2: карта мышц 2D ===== */}
          {fetchMuscleMap ? (
            <SectionCard title="Карта мышц" hint="объём за период" testid="stats-muscle-map">
              <MuscleMapCard fetchMap={fetchMuscleMap} testPrefix="mm" />
            </SectionCard>
          ) : null}

          {/* ===== Фаза 3: кардио ===== */}
          {fetchCardio ? (
            <SectionCard title="Кардио" hint="минуты и норма недели" testid="stats-cardio">
              <CardioStatsCard fetchStats={fetchCardio} testPrefix="cardio" />
            </SectionCard>
          ) : null}

          {/* ===== Прогресс упражнения ===== */}
          <SectionCard
            title="Прогресс упражнения"
            testid="stats-exercise-progress"
            action={
              exercises.length ? (
                <div className="stats-select-wrap">
                  <select
                    className="stats-select"
                    value={selectedSlug || ""}
                    onChange={(e) => setSelectedSlug(e.target.value)}
                    data-testid="exercise-select"
                  >
                    {exercises.map((ex) => (
                      <option key={ex.key} value={ex.key}>{ex.name}</option>
                    ))}
                  </select>
                  <ChevronDown size={16} className="stats-select-ic" />
                </div>
              ) : null
            }
          >
            <TabChips tabs={PROG_METRICS} active={progMetric} onChange={setProgMetric} testPrefix="prog-metric" />
            {series.length ? (
              <div className="stats-chart" style={{ marginTop: 10 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={series} margin={{ top: 10, right: 8, left: -16, bottom: 0 }}>
                    <defs>
                      <linearGradient id={`prog-${gid}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={progColor} stopOpacity={0.45} />
                        <stop offset="100%" stopColor={progColor} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="label" tick={{ fill: "rgba(255,255,255,0.5)", fontSize: 11 }}
                      axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 11 }} axisLine={false}
                      tickLine={false} width={40} domain={["auto", "auto"]} />
                    <Tooltip content={<ChartTooltip unit="кг" />} />
                    {progMetric === "weight" ? (
                      <Line type="monotone" dataKey="plan_weight" name="План"
                        stroke="rgba(255,255,255,0.35)" strokeWidth={2} strokeDasharray="5 5" dot={false} />
                    ) : null}
                    <Area type="monotone" dataKey={progKey} name={progName} stroke={progColor}
                      strokeWidth={3} fill={`url(#prog-${gid})`}
                      dot={{ r: 3, fill: progColor, strokeWidth: 0 }}
                      activeDot={{ r: 5, stroke: "#1C1C1C", strokeWidth: 2 }}
                      isAnimationActive animationDuration={1200} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="stats-nodata">Нет выполненных подходов по упражнению</p>
            )}
          </SectionCard>

          {/* ===== Группы мышц ===== */}
          {muscles.length ? (
            <SectionCard title="Распределение по группам" hint="подходы" testid="stats-muscles">
              <div className="stats-pie-wrap">
                <div className="stats-pie">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={muscles}
                        dataKey="sets"
                        nameKey="label"
                        cx="50%"
                        cy="50%"
                        innerRadius="62%"
                        outerRadius="94%"
                        paddingAngle={2}
                        stroke="#242424"
                        strokeWidth={3}
                        isAnimationActive
                        animationDuration={1000}
                      >
                        {muscles.map((m, i) => (
                          <Cell key={m.group} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip content={<ChartTooltip unit="подх." />} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="stats-pie-center">
                    <b>{totalMuscleSets}</b>
                    <span>подходов</span>
                  </div>
                </div>
                <ul className="stats-legend">
                  {muscles.map((m, i) => {
                    const pct = totalMuscleSets ? Math.round((m.sets / totalMuscleSets) * 100) : 0;
                    return (
                      <li key={m.group} data-testid={`muscle-${m.group}`}>
                        <div className="stats-legend-top">
                          <span className="stats-legend-dot" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                          <span className="stats-legend-name">{m.label}</span>
                          <b className="stats-legend-val">{m.sets}</b>
                          <span className="stats-legend-pct">{pct}%</span>
                        </div>
                        <div className="stats-legend-bar">
                          <i style={{ width: `${pct}%`, background: PIE_COLORS[i % PIE_COLORS.length] }} />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </SectionCard>
          ) : null}

          {/* ===== Карта нагрузки по мышечным группам ===== */}
          <MuscleGroupsChart telegramId={telegramId} coachId={coachId} />

          {/* ===== Соответствие плану ===== */}
          <SectionCard title="Соответствие плану" hint="план ↔ факт" testid="stats-adherence">
            <div className="stats-bars">
              <AdherenceBar label="Объём (подходы)" value={adherence.volume_pct} />
              {adherence.schedule_pct != null ? (
                <AdherenceBar label="Расписание" value={adherence.schedule_pct} />
              ) : null}
              <DeviationRow label="Отклонение по тоннажу" value={adherence.tonnage_dev_pct} />
            </div>
            {Object.keys(skipCounts).length ? (
              <div className="stats-chips" data-testid="stats-skip-chips">
                {Object.entries(SKIP_META).map(([k, meta]) => {
                  const cnt = skipCounts[k] || 0;
                  if (!cnt) return null;
                  const Ic = meta.Icon;
                  return (
                    <span className="stats-chip" key={k}
                      style={{ color: meta.color, borderColor: `${meta.color}55`, background: `${meta.color}18` }}>
                      <Ic size={13} /> {meta.label} <b>{cnt}</b>
                    </span>
                  );
                })}
              </div>
            ) : null}
          </SectionCard>

          {/* ===== Последние тренировки ===== */}
          {recent.length ? (
            <SectionCard title="Последние тренировки" testid="stats-recent">
              <ul className="stats-recent">
                {recent.map((s) => (
                  <li className="stats-recent-row" key={s.id} data-testid={`recent-${s.id}`}>
                    <div className="stats-recent-ring" style={{ "--p": `${s.progress_pct || 0}%` }}>
                      <span>{s.progress_pct || 0}<i>%</i></span>
                    </div>
                    <div className="stats-recent-main">
                      <div className="stats-recent-title">{s.title || "Тренировка"}</div>
                      <div className="stats-recent-meta">
                        {s.group ? <span className="stats-recent-group">{s.group}</span> : null}
                        <span>{fmtTon(s.tonnage)}</span>
                        <span>·</span>
                        <span>{fmtDur(s.duration_sec)}</span>
                        {s.difficulty ? <><span>·</span><span>{s.difficulty}</span></> : null}
                      </div>
                    </div>
                    <div className="stats-recent-date">{formatShortDate(s.date || s.finished_at)}</div>
                  </li>
                ))}
              </ul>
            </SectionCard>
          ) : null}

          <div className="stats-foot-space" />
        </>
      )}
    </div>
  );
}

function AdherenceBar({ label, value }) {
  const v = Math.max(0, Math.min(100, Math.round(value || 0)));
  const color = v >= 85 ? "#34D399" : v >= 60 ? "#FFC24B" : "#FB7185";
  return (
    <div className="stats-bar">
      <div className="stats-bar-top">
        <span>{label}</span>
        <b style={{ color }}>{v}%</b>
      </div>
      <div className="stats-bar-track">
        <div className="stats-bar-fill" style={{ width: `${v}%`, background: color }} />
      </div>
    </div>
  );
}

function DeviationRow({ label, value }) {
  const v = Math.round(value || 0);
  const pos = v >= 0;
  return (
    <div className="stats-dev">
      <span><Zap size={13} style={{ marginRight: 5, verticalAlign: -2 }} />{label}</span>
      <b className={pos ? "up" : "down"}>{pos ? "+" : ""}{v}%</b>
    </div>
  );
}

function formatShortDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
  } catch (e) {
    return "";
  }
}

export function StatsPage() {
  const { user, avatarUrl } = useUser();
  const navigate = useNavigate();
  const tg = user?.telegram_id;
  useBackButton(true, () => navigate(-1));

  const fetchPlanId = useCallback(() => getActivePlan(tg).then((p) => p?.id), [tg]);
  const fetchDetailed = useCallback((params) => getDetailedStats(tg, params), [tg]);
  const fetchProgress = useCallback((params) => getExerciseProgress(tg, params), [tg]);
  const fetchMuscleMap = useCallback(
    (params) => getMuscleMap(tg, params),
    [tg]
  );
  const fetchCardio = useCallback(
    (params) => getCardioStats(tg, params),
    [tg]
  );

  if (!tg) return null;
  return (
    <StatsView
      name={user?.first_name || "Моя статистика"}
      avatar={avatarUrl}
      subtitle="Моя статистика"
      onBack={() => navigate(-1)}
      fetchPlanId={fetchPlanId}
      fetchDetailed={fetchDetailed}
      fetchProgress={fetchProgress}
      fetchMuscleMap={fetchMuscleMap}
      fetchCardio={fetchCardio}
      telegramId={tg}
      coachId={null}
    />
  );
}

export function CoachClientStatsPage() {
  const { athleteId } = useParams();
  const aid = Number(athleteId);
  const { user } = useUser();
  const coachId = user?.telegram_id;
  const navigate = useNavigate();
  const [athlete, setAthlete] = useState(null);
  useBackButton(true, () => navigate(`/coach/${aid}`));

  useEffect(() => {
    let alive = true;
    getUserById(aid).then((u) => alive && setAthlete(u)).catch(() => {});
    return () => { alive = false; };
  }, [aid]);

  const fetchPlanId = useCallback(
    () => getCoachClientPlan(coachId, aid).then((p) => p?.id),
    [coachId, aid]
  );
  const fetchDetailed = useCallback(
    (params) => getCoachClientStats(coachId, aid, params),
    [coachId, aid]
  );
  const fetchProgress = useCallback(
    (params) => getCoachClientExerciseProgress(coachId, aid, params),
    [coachId, aid]
  );
  const fetchMuscleMap = useCallback(
    (params) => getCoachClientMuscleMap(coachId, aid, params),
    [coachId, aid]
  );
  const fetchCardio = useCallback(
    (params) => getCardioStats(aid, params),
    [aid]
  );

  if (!coachId || !aid) return null;
  return (
    <StatsView
      name={athlete?.first_name || "Подопечный"}
      avatar={athlete?.picture}
      subtitle="Статистика подопечного"
      onBack={() => navigate(`/coach/${aid}`)}
      fetchPlanId={fetchPlanId}
      fetchDetailed={fetchDetailed}
      fetchProgress={fetchProgress}
      fetchMuscleMap={fetchMuscleMap}
      fetchCardio={fetchCardio}
      telegramId={aid}
      coachId={coachId}
    />
  );
}

export default StatsPage;
