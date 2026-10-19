import React, { useCallback, useEffect, useState } from "react";
import { Zap, Flame } from "lucide-react";
import "./MuscleMap.css";

/**
 * Фаза 2 — карта мышц 2D: два силуэта (спереди/сзади), зоны заливаются
 * по интенсивности объёма за период. Данные — из GET /stats/{tg}/muscle-map
 * (или тренерской версии), прокидываются через проп fetchMap({period}).
 */

const MUSCLE_LABELS = {
  chest: "Грудные",
  upper_back: "Верх спины",
  lats: "Широчайшие",
  traps: "Трапеции",
  front_delts: "Передние дельты",
  side_delts: "Средние дельты",
  rear_delts: "Задние дельты",
  biceps: "Бицепс",
  triceps: "Трицепс",
  forearms: "Предплечья",
  abs: "Пресс",
  obliques: "Косые",
  lower_back: "Поясница",
  glutes: "Ягодицы",
  quads: "Квадрицепсы",
  hamstrings: "Бицепс бедра",
  adductors: "Приводящие",
  abductors: "Отводящие",
  calves: "Икры",
  neck: "Шея",
};

const PERIODS = [
  { key: "week", label: "Неделя" },
  { key: "month", label: "Месяц" },
  { key: "all", label: "Всё" },
];

const VIEWS = [
  { key: "front", label: "Спереди" },
  { key: "back", label: "Сзади" },
];

const fmtKg = (v) => `${(Number(v) || 0).toLocaleString("ru-RU")} кг`;

function colorFor(t) {
  const k = Math.min(1, Math.max(0, Number(t) || 0));
  if (k <= 0) return "rgba(255,255,255,0.07)";
  const c1 = [255, 107, 0];
  const c2 = [255, 218, 36];
  const mix = c1.map((v, i) => Math.round(v + (c2[i] - v) * k));
  return `rgba(${mix[0]},${mix[1]},${mix[2]},${0.42 + 0.55 * k})`;
}

/* Половина силуэта (левая); правая — зеркальным <g>. Регионы несут data-muscle. */
function HalfShapes({ view, regions, selected }) {
  const r = (muscle) => ({
    "data-muscle": muscle,
    style: { fill: colorFor(regions?.[muscle]?.intensity_0_1) },
    className: `mm-region ${selected === muscle ? "mm-region-sel" : ""}`,
  });
  if (view === "front") {
    return (
      <>
        {/* декор: голова, туловище-база, рука-база, нога-база, кисть, голень */}
        <circle cx="110" cy="36" r="19" className="mm-deco" />
        <circle cx="49" cy="188" r="6" className="mm-deco" />
        <path className="mm-deco" d="M100,280 C98,300 100,322 104,338 L114,338 C117,320 118,300 117,280 Z" />
        <path className="mm-deco" d="M84,76 C86,68 100,64 110,64 C120,64 134,68 136,76 L134,130 C134,158 130,178 126,188 L94,188 C90,178 86,158 86,130 Z" />
        <path className="mm-deco" d="M70,90 C64,102 62,122 60,142 C58,158 56,172 54,184 L66,186 C68,168 70,150 72,134 C74,118 76,104 78,94 Z" />
        <path className="mm-deco" d="M92,190 C90,220 92,252 98,280 L120,280 C124,250 126,218 125,190 Z" />
        {/* регионы */}
        <path {...r("neck")} d="M100,56 L120,56 L118,72 L102,72 Z" />
        <path {...r("traps")} d="M102,62 L110,76 L88,72 Z" />
        <ellipse {...r("front_delts")} cx="77" cy="90" rx="13" ry="12" />
        <ellipse {...r("side_delts")} cx="65" cy="95" rx="7" ry="11" />
        <path {...r("chest")} d="M108,74 C96,72 84,78 82,92 C82,104 94,108 108,102 Z" />
        <path {...r("abs")} d="M97,110 L123,110 L121,166 L99,166 Z" />
        <path {...r("obliques")} d="M93,112 C89,128 91,150 97,164 L97,112 Z" />
        <ellipse {...r("biceps")} cx="57" cy="116" rx="10" ry="19" />
        <ellipse {...r("forearms")} cx="51" cy="158" rx="8" ry="21" />
        <ellipse {...r("abductors")} cx="88" cy="196" rx="9" ry="15" />
        <path {...r("quads")} d="M92,188 C90,216 92,248 98,276 L114,276 C117,244 118,212 117,188 Z" />
        <path {...r("adductors")} d="M110,190 C108,212 108,232 112,252 L116,232 C117,212 116,198 115,190 Z" />
      </>
    );
  }
  return (
    <>
      <circle cx="110" cy="36" r="19" className="mm-deco" />
      <circle cx="49" cy="188" r="6" className="mm-deco" />
      <path className="mm-deco" d="M84,76 C86,68 100,64 110,64 C120,64 134,68 136,76 L134,130 C134,158 130,178 126,188 L94,188 C90,178 86,158 86,130 Z" />
      <path className="mm-deco" d="M70,90 C64,102 62,122 60,142 C58,158 56,172 54,184 L66,186 C68,168 70,150 72,134 C74,118 76,104 78,94 Z" />
      <path {...r("neck")} d="M100,56 L120,56 L118,72 L102,72 Z" />
      <path {...r("traps")} d="M110,58 L84,74 L96,96 L110,84 L124,96 L136,74 Z" />
      <path {...r("upper_back")} d="M94,80 C102,74 118,74 126,80 L122,112 L98,112 Z" />
      <ellipse {...r("rear_delts")} cx="77" cy="90" rx="13" ry="12" />
      <path {...r("lats")} d="M96,114 C88,126 88,146 96,162 L108,150 L108,114 Z" />
      <path {...r("lower_back")} d="M100,150 L120,150 L117,178 L103,178 Z" />
      <ellipse {...r("triceps")} cx="57" cy="116" rx="10" ry="19" />
      <ellipse {...r("forearms")} cx="51" cy="158" rx="8" ry="21" />
      <ellipse {...r("glutes")} cx="97" cy="198" rx="16" ry="15" />
      <path {...r("hamstrings")} d="M92,216 C90,240 92,260 98,276 L114,276 C117,258 118,236 117,216 Z" />
      <ellipse {...r("calves")} cx="104" cy="304" rx="11" ry="24" />
    </>
  );
}

function Silhouette({ view, regions, selected, onSelect }) {
  const handleClick = (e) => {
    const muscle = e.target?.getAttribute?.("data-muscle");
    if (muscle) onSelect(muscle);
  };
  return (
    <svg
      viewBox="0 0 220 350"
      className="mm-svg"
      role="img"
      aria-label={`Силуэт ${view === "front" ? "спереди" : "сзади"}`}
      data-testid={`mm-svg-${view}`}
    >
      <g className="mm-body" onClick={handleClick}>
        <HalfShapes view={view} regions={regions} selected={selected} />
        <g transform="translate(220,0) scale(-1,1)">
          <HalfShapes view={view} regions={regions} selected={selected} />
        </g>
      </g>
    </svg>
  );
}

export function MuscleMapCard({ fetchMap, testPrefix = "mm" }) {
  const [period, setPeriod] = useState("week");
  const [view, setView] = useState("front");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  const load = useCallback(
    async (p) => {
      setLoading(true);
      setError("");
      try {
        const d = await fetchMap({ period: p });
        setData(d || null);
      } catch (e) {
        setData(null);
        setError("Не удалось загрузить карту мышц");
      } finally {
        setLoading(false);
      }
    },
    [fetchMap]
  );

  useEffect(() => {
    load(period);
  }, [period, load]);

  const regions = data?.regions || {};
  const totals = data?.totals || { volume: 0, sets: 0, sessions: 0 };
  const imbalance = data?.imbalance || [];
  const selRegion = selected ? regions[selected] : null;
  const empty = !loading && !error && (totals.sets || 0) === 0;

  return (
    <div className="mm-card" data-testid={`${testPrefix}-card`}>
      <div className="mm-toolbar">
        <div className="mm-chips">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              type="button"
              className={`mm-chip ${period === p.key ? "active" : ""}`}
              onClick={() => { setSelected(null); setPeriod(p.key); }}
              data-testid={`${testPrefix}-period-${p.key}`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="mm-chips">
          {VIEWS.map((v) => (
            <button
              key={v.key}
              type="button"
              className={`mm-chip mm-chip-view ${view === v.key ? "active" : ""}`}
              onClick={() => setView(v.key)}
              data-testid={`${testPrefix}-view-${v.key}`}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="mm-skel" data-testid={`${testPrefix}-loading`}>
          <div className="mm-skel-body" />
        </div>
      ) : error ? (
        <div className="mm-error" data-testid={`${testPrefix}-error`}>
          <Zap size={20} />
          <p>{error}</p>
          <button type="button" className="mm-retry" onClick={() => load(period)}>Повторить</button>
        </div>
      ) : empty ? (
        <div className="mm-empty" data-testid={`${testPrefix}-empty`}>
          <span className="mm-empty-ic"><Flame size={22} /></span>
          <p>Нет данных за период</p>
          <span className="mm-empty-sub">Завершите тренировки — карта оживёт</span>
        </div>
      ) : (
        <>
          <div className="mm-figures">
            <Silhouette
              view={view}
              regions={regions}
              selected={selected}
              onSelect={(m) => setSelected((cur) => (cur === m ? null : m))}
            />
            <div className="mm-legend">
              <span>меньше</span>
              <i className="mm-legend-bar" />
              <span>больше</span>
            </div>
          </div>

          <div className="mm-totals" data-testid={`${testPrefix}-totals`}>
            <div><b>{fmtKg(totals.volume)}</b><span>объём</span></div>
            <div><b>{totals.sets}</b><span>подходов</span></div>
            <div><b>{totals.sessions}</b><span>тренировок</span></div>
          </div>

          {imbalance.length ? (
            <div className="mm-imbalance" data-testid={`${testPrefix}-imbalance`}>
              <Zap size={13} />
              Акцент: {imbalance.map((m) => MUSCLE_LABELS[m] || m).join(", ")}
            </div>
          ) : null}

          {selected && selRegion ? (
            <div className="mm-info" data-testid={`${testPrefix}-info`}>
              <b>{MUSCLE_LABELS[selected] || selected}</b>
              <span>{fmtKg(selRegion.volume_kg)} · {selRegion.working_sets} подходов · {selRegion.sessions} трен.</span>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

export default MuscleMapCard;
