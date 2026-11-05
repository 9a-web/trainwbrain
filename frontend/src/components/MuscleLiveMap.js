import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity } from "lucide-react";
import { getSessionMuscleMap } from "@/api";
import { MUSCLE_CANON, muscleLabel, normalizeMuscleWeights } from "@/lib/muscles";
import MuscleFigure from "@/components/MuscleFigure";
import "./MuscleLiveMap.css";

/**
 * Живая карта мышц внизу тренировки.
 *
 * Подсвечивается по мере заполнения: как только подход/упражнение засчитано,
 * меняются данные сессии (`view`), и карта пересчитывается локально по тем же
 * правилам, что и серверная карта (веса основных/вспомогательных групп), а
 * затем сверяется с `GET /sessions/{id}/muscle-map?live=true`.
 *
 * Для завершённой тренировки карта остаётся итоговой и тоже показывается —
 * ровно под карточками упражнений.
 */

/**
 * Веса мышц упражнения сессии. Основной источник — `muscle_group` в карточке
 * упражнения (канон/legacy, раскладывается как на бэкенде); если в справочнике
 * есть точный список групп (`muscle_groups`/`secondary_groups`) — он главнее.
 */
function weightsFor(ex) {
  if (ex.muscle_groups?.length) {
    return normalizeMuscleWeights(ex.muscle_groups, ex.secondary_groups || []);
  }
  return normalizeMuscleWeights(ex.muscle_group ? [ex.muscle_group] : [], []);
}

/* --- те же правила нагрузки, что в backend/muscle_engine.py --------------- */

// Упражнение без веса (собственный вес) считается как доля массы тела —
// иначе подходы «на массу тела» не давали бы нагрузки вообще.
const BODYWEIGHT_DEFAULT_KG = 75.0;
const BODYWEIGHT_SHARE = 0.65;

/** Интенсивность подхода по %1ПМ (линейно между опорными точками). */
function intensityFromPercent(percent) {
  const p = Number(percent);
  if (!p || p <= 0) return null;
  const points = [[50, 0.3], [60, 0.52], [65, 0.62], [70, 0.72], [75, 0.82],
    [80, 0.9], [85, 0.95], [90, 1.0], [100, 1.0]];
  if (p <= points[0][0]) return points[0][1];
  for (let i = 0; i < points.length - 1; i += 1) {
    const [p0, v0] = points[i];
    const [p1, v1] = points[i + 1];
    if (p <= p1) return v0 + ((v1 - v0) * (p - p0)) / (p1 - p0);
  }
  return 1;
}

/** Интенсивность подхода по числу повторов (когда %1ПМ неизвестен). */
function intensityFromReps(reps) {
  const r = Number(reps) || 0;
  if (r <= 0) return 0;
  if (r <= 3) return 1;
  if (r <= 6) return 0.95;
  if (r <= 9) return 0.88;
  if (r <= 12) return 0.8;
  if (r <= 15) return 0.68;
  if (r <= 20) return 0.55;
  return 0.42;
}

/** Вес подхода: штанга или условный вес тела для собственного веса. */
function effectiveWeight(weight) {
  const w = Number(weight) || 0;
  return w > 0 ? w : BODYWEIGHT_DEFAULT_KG * BODYWEIGHT_SHARE;
}

/** Подходы упражнения: из set_logs, иначе (старые сессии) из схемы. */
function setsOf(ex) {
  const logs = (ex.set_logs || []).filter((l) => l.done && !l.skipped && l.reps);
  if (logs.length) {
    return logs.map((l) => ({ w: Number(l.weight) || 0, reps: Number(l.reps) || 0, pct: l.percent_1rm }));
  }
  if ((ex.set_logs || []).length) return [];
  if (ex.status !== "done") return [];
  const out = [];
  (ex.sets_scheme || []).forEach((sch) => {
    const reps = Number(sch.reps) || 0;
    if (!reps) return;
    for (let i = 0; i < (Number(sch.sets) || 0); i += 1) {
      out.push({ w: Number(sch.weight) || 0, reps, pct: sch.percent_1rm });
    }
  });
  return out;
}

/** Локальный расчёт подсветки — зеркало build_rules + _build_muscle_map. */
function computeRegions(exercises) {
  const stats = {}; // muscle -> { load, sets, volume }
  let totalLoad = 0;
  let totalSets = 0;
  let totalVolume = 0;

  (exercises || []).forEach((ex) => {
    const sets = setsOf(ex);
    if (!sets.length) return;
    const weights = weightsFor(ex);
    if (!Object.keys(weights).length) return;

    sets.forEach((st) => {
      if (!st.reps) return;
      let inten = intensityFromPercent(st.pct);
      if (inten === null) inten = intensityFromReps(st.reps);
      if (!(inten > 0)) return;
      const ew = effectiveWeight(st.w);
      const load = ew * st.reps * inten;
      // Объём (volume_kg) тоже считаем через effectiveWeight: упражнения без
      // веса (собственный вес, тренажёры, которые не заполнили вес) иначе
      // давали бы 0 объём и не подсвечивались.
      const volume = (Number(st.w) || 0) > 0 ? Number(st.w) * st.reps : ew * st.reps;
      totalLoad += load;
      totalVolume += volume;
      Object.entries(weights).forEach(([m, share]) => {
        const r = stats[m] || { load: 0, sets: 0, volume: 0 };
        r.load += load * share;
        r.sets += share;
        r.volume += volume * share;
        stats[m] = r;
      });
      totalSets += 1;
    });
  });

  const maxLoad = Math.max(0, ...Object.values(stats).map((r) => r.load));
  const regions = {};
  Object.entries(stats).forEach(([m, r]) => {
    // Та же кривая, что scale_for_map: мягкий старт, читаемый максимум.
    const intensity = maxLoad > 0 ? Math.sqrt(Math.min(1, r.load / maxLoad)) : 0;
    regions[m] = {
      volume_kg: Math.round(r.volume),
      working_sets: Math.round(r.sets),
      intensity_0_1: Math.round(intensity * 1000) / 1000,
    };
  });

  // Для сравнения с сервером: сервер отдаёт сумму взвешенных подходов.
  const weightedSets = Object.values(regions).reduce((a, r) => a + r.working_sets, 0);
  return { regions, totalVolume: Math.round(totalVolume), totalLoad, totalSets: weightedSets, rawSets: totalSets };
}

/**
 * Отпечаток засчитанной работы — триггер «живого» пересчёта.
 * Учитывает не только число подходов, но и вес/повторы: правка веса в уже
 * засчитанном подходе тоже должна перекрашивать карту.
 */
function doneSignature(exercises) {
  return (exercises || [])
    .map((ex) => {
      const done = (ex.set_logs || []).filter((l) => l.done && !l.skipped);
      const work = done.reduce((a, l) => a + (Number(l.weight) || 0) * (Number(l.reps) || 0), 0);
      return `${ex.order}:${ex.status}:${done.length}:${work}:${ex.tonnage || 0}`;
    })
    .join("|");
}

const fmtKg = (v) => `${(Number(v) || 0).toLocaleString("ru-RU")} кг`;

const MuscleLiveMap = ({ view, sessionId: explicitId = null, testPrefix = "wv-muscles" }) => {
  const sessionId = explicitId || view?.id || view?.session_id || null;
  const status = view?.status;
  const exercises = useMemo(() => view?.exercises || [], [view]);
  const isLive = status === "in_progress" || status === "paused";
  const signature = useMemo(() => doneSignature(exercises), [exercises]);

  // Локальный расчёт — мгновенная подсветка, не дожидаясь ответа сервера.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const local = useMemo(() => computeRegions(exercises), [signature, exercises]);

  // Уточнённые данные с сервера (учитывают резолвер упражнений и ИИ-разбор).
  const [server, setServer] = useState(null);
  const [flash, setFlash] = useState(false);
  const prevSig = useRef(signature);
  const reqRef = useRef(0);

  // Сброс серверного ответа при изменении набора подходов — чтобы
  // не сравнивать с ответом, который пришёл до следующего марка.
  useEffect(() => {
    if (signature === prevSig.current) return;
    prevSig.current = signature;
    setServer((prev) => (prev && prev.__sig === signature ? prev : null));
    setFlash(true);
    const t = setTimeout(() => setFlash(false), 900);
    return () => clearTimeout(t);
  }, [signature]);

  useEffect(() => {
    if (!sessionId) {
      setServer(null);
      return undefined;
    }
    const req = ++reqRef.current;
    let cancelled = false;
    getSessionMuscleMap(sessionId, isLive ? { live: true } : undefined)
      .then((d) => {
        if (!cancelled && req === reqRef.current) {
          if (d && typeof d === "object") d.__sig = signature;
          setServer(d || null);
        }
      })
      .catch(() => {
        if (!cancelled && req === reqRef.current) setServer(null);
      });
    return () => {
      cancelled = true;
    };
    // Пересчитываем на каждое изменение состава выполненных подходов.
  }, [sessionId, signature, isLive]);

  // Сервер главнее (он учитывает справочник упражнений и вес тела), но пустой
  // или отставший ответ не должен гасить уже зажжённые мышцы.
  const regions = useMemo(() => {
    const srv = server?.regions || null;
    if (!srv) return local.regions;
    const srvSets = Number(server?.totals?.sets) || 0;
    const srvLit = Object.values(srv).filter((r) => (r?.intensity_0_1 || 0) > 0).length;
    if (srvSets >= local.totalSets && srvLit > 0) return srv;
    return local.regions;
  }, [server, local]);

  const lit = useMemo(
    () =>
      Object.entries(regions)
        .filter(([, r]) => (r?.intensity_0_1 || 0) > 0)
        .sort((a, b) => (b[1].intensity_0_1 || 0) - (a[1].intensity_0_1 || 0)),
    [regions]
  );

  const [view3d, setView3d] = useState("front");
  const toggleView = useCallback(
    (v) => setView3d((cur) => (cur === v ? cur : v)),
    []
  );
  const [selected, setSelected] = useState(null);
  const onSelect = useCallback((m) => setSelected((cur) => (cur === m ? null : m)), []);
  const selRegion = selected ? regions[selected] : null;

  // Ничего ещё не сделано — карта видна, но не подсвечена (ожидание).
  const empty = lit.length === 0;

  return (
    <div
      className={`wvm-card ${isLive ? "is-live" : ""} ${flash ? "is-flash" : ""}`}
      data-testid={`${testPrefix}-card`}
    >
      <div className="wvm-head">
        <span className="wvm-title">
          <Activity size={15} />
          <span>Мышцы</span>
          {isLive ? <span className="wvm-live">в реальном времени</span> : null}
        </span>
        <span className="wvm-tabs">
          <button
            type="button"
            className={`wvm-tab ${view3d === "front" ? "active" : ""}`}
            onClick={() => toggleView("front")}
            data-testid={`${testPrefix}-view-front`}
          >
            Спереди
          </button>
          <button
            type="button"
            className={`wvm-tab ${view3d === "back" ? "active" : ""}`}
            onClick={() => toggleView("back")}
            data-testid={`${testPrefix}-view-back`}
          >
            Сзади
          </button>
        </span>
      </div>

      {/* 3D-модель анатомии — та же, что в «Статистике» */}
      <div className="wvm-figure">
        <MuscleFigure
          view={view3d}
          regions={regions}
          selected={selected}
          onSelect={onSelect}
          testPrefix={testPrefix}
        />
      </div>

      <div className="wvm-side">
        {empty ? (
          <span className="wvm-hint" data-testid={`${testPrefix}-empty`}>
            {isLive
              ? "Засчитайте первое упражнение — мышцы подсветятся"
              : "Нет выполненных упражнений"}
          </span>
        ) : (
          <ul className="wvm-list" data-testid={`${testPrefix}-list`}>
            {lit.slice(0, 6).map(([muscle, r]) => (
              <li key={muscle} className="wvm-item">
                <i style={{ background: `rgba(255, 138, 36, ${0.25 + 0.75 * (r.intensity_0_1 || 0)})` }} />
                <span className="wvm-item-name">{muscleLabel(muscle)}</span>
                <span className="wvm-item-sets">{r.working_sets || 0}</span>
              </li>
            ))}
          </ul>
        )}
        {selected && selRegion ? (
          <span className="wvm-info" data-testid={`${testPrefix}-info`}>
            {muscleLabel(selected)} · {fmtKg(selRegion.volume_kg)}
          </span>
        ) : null}
      </div>

      <div className="wvm-legend">
        <span className="wvm-legend-bar" />
        <span className="wvm-legend-txt">
          {isLive ? "подсветка растёт по ходу тренировки" : "итоговая нагрузка"}
        </span>
      </div>
    </div>
  );
};

export default MuscleLiveMap;
