import React, { useCallback, useEffect, useRef, useState } from "react";
import { Zap, Flame } from "lucide-react";
import { muscleLabel } from "@/lib/muscles";
import MuscleFigure, { supportsWebGL } from "@/components/MuscleFigure";
import { MuscleSilhouette } from "@/components/MuscleSilhouette";
import "./MuscleMap.css";

// Обратная совместимость: силуэт раньше жил в этом модуле.
export { MuscleSilhouette };

/**
 * Карта мышц. 3D-модель (three.js + react-three-fiber) с подсветкой мышц по
 * объёму за период; если WebGL недоступен или чанк не загрузился — 2D-силуэт.
 * Данные — из GET /stats/{tg}/muscle-map (или тренерской версии),
 * прокидываются через проп fetchMap({period}).
 */

const PERIODS = [
  { key: "week", label: "Неделя" },
  { key: "month", label: "Месяц" },
  { key: "quarter", label: "Квартал" },
  { key: "year", label: "Год" },
  { key: "all", label: "Всё" },
];

const VIEWS = [
  { key: "front", label: "Спереди" },
  { key: "back", label: "Сзади" },
];

const fmtKg = (v) => `${(Number(v) || 0).toLocaleString("ru-RU")} кг`;

export function MuscleMapCard({ fetchMap, testPrefix = "mm", period, onPeriodChange }) {
  const resolvedPeriod = period || "week";
  const [localPeriod, setLocalPeriod] = useState(resolvedPeriod);

  // Sync from parent when provided
  useEffect(() => {
    if (period) setLocalPeriod(period);
  }, [period]);
  const [view, setView] = useState("front");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  // 3D-модель доступна → показываем её (2D-силуэт остаётся запасным вариантом
  // внутри MuscleFigure: WebGL-сбой откатывает на него сам).
  const [webgl] = useState(supportsWebGL);
  const use3d = webgl;
  const cardRef = useRef(null);
  const toggleMuscle = useCallback((m) => setSelected((cur) => (cur === m ? null : m)), []);

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
    load(period || localPeriod);
  }, [period, localPeriod, load]);

  const regions = data?.regions || {};
  const totals = data?.totals || { volume: 0, sets: 0, sessions: 0 };
  const imbalance = data?.imbalance || [];
  const selRegion = selected ? regions[selected] : null;
  const empty = !loading && !error && (totals.sets || 0) === 0;

  return (
    <div className="mm-card" data-testid={`${testPrefix}-card`} ref={cardRef}>
      <div className="mm-toolbar">
        <div className="mm-chips">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              type="button"
              className={`mm-chip ${(period || localPeriod) === p.key ? "active" : ""}`}
              onClick={() => { setSelected(null); if (onPeriodChange) onPeriodChange(p.key); setLocalPeriod(p.key); }}
              data-testid={`${testPrefix}-period-${p.key}`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="mm-chips">
          {use3d ? <span className="mm-view-3d">3D</span> : null}
          {data?.source && data.source !== "auto" ? (
            <span className="mm-engine" data-testid={`${testPrefix}-engine`} title="Источник разбора нагрузки">
              {data.source === "ai" ? "ИИ" : data.source === "rules" ? "правила" : "ИИ + правила"}
            </span>
          ) : null}
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
          <div className={`mm-figures ${use3d ? "mm-figures-3d" : ""}`}>
            <MuscleFigure
              regions={regions}
              selected={selected}
              onSelect={toggleMuscle}
              view={view}
              testPrefix={testPrefix}
            />
            <div className="mm-legend">
              <span>меньше</span>
              <i className="mm-legend-bar" />
              <span>больше</span>
            </div>
            {use3d ? (
              <div className="mm-attribution">
                3D-модель:{" "}
                <a
                  href="https://github.com/Charleeh/ecorche"
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  écorché
                </a>{" "}
                · BodyParts3D · Z-Anatomy · CC BY-SA 4.0
              </div>
            ) : null}
          </div>

          <div className="mm-totals" data-testid={`${testPrefix}-totals`}>
            <div><b>{fmtKg(totals.volume)}</b><span>объём</span></div>
            <div><b>{totals.sets}</b><span>подходов</span></div>
            <div><b>{totals.sessions}</b><span>тренировок</span></div>
          </div>

          {imbalance.length ? (
            <div className="mm-imbalance" data-testid={`${testPrefix}-imbalance`}>
              <Zap size={13} />
              Акцент: {imbalance.map(muscleLabel).join(", ")}
            </div>
          ) : null}

          {selected && selRegion ? (
            <div className="mm-info" data-testid={`${testPrefix}-info`}>
              <b>{muscleLabel(selected)}</b>
              <span>{fmtKg(selRegion.volume_kg)} · {selRegion.working_sets} подходов · {selRegion.sessions} трен.</span>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

export default MuscleMapCard;
