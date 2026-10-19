import React, { useEffect, useMemo, useRef, useState } from "react";
import { X, Dumbbell, CalendarDays, Flame, TrendingUp, Coffee, Play } from "lucide-react";
import "./AiProgramPreview.css";

const MUSCLE_LABELS = {
  legs: "Ноги", chest: "Грудь", back: "Спина", shoulders: "Плечи",
  biceps: "Бицепс", triceps: "Трицепс", core: "Кор",
  hamstrings: "Бицепс бедра", quads: "Квадрицепс", glutes: "Ягодицы",
  calves: "Икры", forearms: "Предплечья", abs: "Пресс", traps: "Трапеции",
};
const MUSCLE_COLORS = {
  legs: "#ff6b6b", chest: "#4ecdc4", back: "#45b7d1", shoulders: "#f9ca24",
  biceps: "#a29bfe", triceps: "#fd79a8", core: "#00b894",
  hamstrings: "#ff9f43", quads: "#eb4d4b", glutes: "#e056fd",
  calves: "#22a6b3", forearms: "#95afc0", abs: "#00b894", traps: "#f0932b",
};
const DAY_LABELS = ["", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const LIFT_LABELS = { squat: "присед", bench: "жим", deadlift: "тяга" };

const fmtWeight = (w) => (Number.isInteger(w) ? `${w}` : Number(w).toFixed(1).replace(/\.0$/, ""));

const formatSetsRow = (scheme, isPercentBased, hasLiftGroup) => {
  if (!scheme || !scheme.length) return null;
  const showAsPct = isPercentBased && hasLiftGroup;
  const unit = showAsPct ? "%" : "кг";
  return scheme.map((s, i) => {
    const w = s.weight;
    const sn = s.sets || 1;
    const r = s.reps || 0;
    if (w == null || w === 0) return { key: i, base: `${sn}×${r}`, w: null };
    return { key: i, base: `${sn}×${r}`, w: `${fmtWeight(w)}${unit}` };
  });
};

// day tonnage / avg intensity (для футера дня)
const dayStats = (day, isPct) => {
  let tonnage = 0;
  let sets = 0;
  const intensities = [];
  (day.exercises || []).forEach((e) => {
    (e.sets_scheme || []).forEach((s) => {
      const w = Number(s.weight) || 0;
      const n = Number(s.sets) || 1;
      const r = Number(s.reps) || 0;
      sets += n;
      if (w > 0) {
        if (isPct && e.lift_group) intensities.push(w);
        else tonnage += w * n * r;
      }
    });
  });
  return { tonnage, sets, avgIntensity: intensities.length ? intensities.reduce((a, b) => a + b, 0) / intensities.length : 0 };
};

export function AiProgramPreview({ open, tpl, onClose, onUse }) {
  const [weekIdx, setWeekIdx] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);
  const sheetRef = useRef(null);

  useEffect(() => {
    if (open) {
      setWeekIdx(0);
      setFullscreen(false);
      document.body.style.overflow = "hidden";
      return () => { document.body.style.overflow = ""; };
    }
    return undefined;
  }, [open]);

  const onSheetScroll = (e) => {
    const st = e.currentTarget.scrollTop;
    // разворачиваем в fullscreen после ~48px скролла, сворачиваем обратно у самого верха
    if (!fullscreen && st > 48) setFullscreen(true);
    else if (fullscreen && st < 6) setFullscreen(false);
  };

  const weeks = useMemo(() => (tpl?.weeks || []).filter((w) => (w.days || []).length), [tpl]);
  const isPct = !!tpl?.requires_maxes;

  if (!open || !tpl || !weeks.length) return null;

  const currentWeek = weeks[Math.min(weekIdx, weeks.length - 1)];

  return (
    <div className={`app-modal ${fullscreen ? "fullscreen" : ""}`} data-testid="ai-program-preview" onClick={onClose}>
      <div ref={sheetRef} className={`app-sheet ${fullscreen ? "fullscreen" : ""}`}
        onClick={(e) => e.stopPropagation()} onScroll={onSheetScroll}>
        <header className="app-header">
          <div className="app-header-info">
            <h2 className="app-title">{tpl.name}</h2>
            <span className="app-meta">
              <CalendarDays size={12} /> {tpl.weeks_count} нед.
              <span className="app-dot">·</span>
              <Dumbbell size={12} /> {tpl.days_per_week || "—"} дн./нед.
              {isPct ? (<><span className="app-dot">·</span><span className="app-pct">%1ПМ</span></>) : null}
            </span>
          </div>
          <button className="app-close" onClick={onClose} aria-label="Закрыть" data-testid="ai-preview-close">
            <X size={20} />
          </button>
        </header>

        {tpl.description ? <p className="app-desc">{tpl.description}</p> : null}

        <div className="app-weeks" role="tablist" data-testid="ai-preview-weeks">
          {weeks.map((w, i) => (
            <button
              key={w.week_index || i}
              role="tab"
              aria-selected={i === weekIdx}
              className={`app-week ${i === weekIdx ? "active" : ""}`}
              onClick={() => setWeekIdx(i)}
              data-testid={`ai-preview-week-${i + 1}`}>
              <span className="app-week-num">{i + 1}</span>
              <span className="app-week-label">неделя</span>
            </button>
          ))}
        </div>

        <div className="app-days">
          {(currentWeek.days || []).map((d, di) => {
            const stats = dayStats(d, isPct);
            return (
              <article key={`${d.day_index}-${di}`} className="app-day" data-testid={`ai-preview-day-${di + 1}`}>
                <header className="app-day-h">
                  <div className="app-day-l">
                    <span className="app-day-badge">{DAY_LABELS[d.day_index] || `Д${di + 1}`}</span>
                    <div>
                      <p className="app-day-title">{d.title || `День ${di + 1}`}</p>
                      <span className="app-day-sub">{(d.exercises || []).length} упр. · {stats.sets} подх.</span>
                    </div>
                  </div>
                  {stats.tonnage > 0 ? (
                    <div className="app-day-tonnage" title="Плановый тоннаж дня">
                      <Flame size={12} /> {stats.tonnage >= 1000 ? `${(stats.tonnage / 1000).toFixed(1)}т` : `${Math.round(stats.tonnage)} кг`}
                    </div>
                  ) : stats.avgIntensity > 0 ? (
                    <div className="app-day-tonnage" title="Средняя интенсивность">
                      <TrendingUp size={12} /> {Math.round(stats.avgIntensity)}%
                    </div>
                  ) : null}
                </header>
                <ul className="app-ex-list">
                  {(d.exercises || []).map((ex, ei) => {
                    const rows = formatSetsRow(ex.sets_scheme, isPct, !!ex.lift_group);
                    const mg = ex.muscle_group;
                    const clr = MUSCLE_COLORS[mg] || "#ff8a24";
                    return (
                      <li key={ei} className="app-ex" data-testid={`ai-preview-ex-${di}-${ei}`}>
                        <div className="app-ex-marker" style={{ background: clr }} />
                        <div className="app-ex-body">
                          <div className="app-ex-top">
                            <span className="app-ex-name">{ex.exercise_name || ex.name}</span>
                            {ex.lift_group ? (
                              <span className="app-ex-lg">{LIFT_LABELS[ex.lift_group]}</span>
                            ) : null}
                          </div>
                          <div className="app-ex-tags">
                            {mg ? (
                              <span className="app-ex-mg" style={{ color: clr, borderColor: `${clr}44` }}>
                                {MUSCLE_LABELS[mg] || mg}
                              </span>
                            ) : null}
                            {ex.is_accessory ? <span className="app-ex-acc">подсобка</span> : null}
                            {ex.rest_seconds ? (
                              <span className="app-ex-rest"><Coffee size={10} /> {ex.rest_seconds}с</span>
                            ) : null}
                          </div>
                          {rows?.length ? (
                            <div className="app-ex-sets">
                              {rows.map((s) => (
                                <span key={s.key} className="app-ex-set">
                                  <b>{s.base}</b>{s.w ? <span className="app-ex-set-w"> @ {s.w}</span> : null}
                                </span>
                              ))}
                            </div>
                          ) : ex.is_accessory ? (
                            <div className="app-ex-sets"><span className="app-ex-set">{ex.target_sets}×{ex.target_reps}</span></div>
                          ) : null}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </article>
            );
          })}
        </div>

        <footer className="app-footer">
          {onUse ? (
            <>
              <button className="app-use-btn" onClick={onUse} data-testid="ai-preview-use">
                <Play size={16} />
                <span>Использовать эту программу</span>
              </button>
              <span className="app-footer-note">
                {isPct
                  ? "Дальше — вы укажете свои 1ПМ (присед / жим / тяга) и дни тренировок."
                  : "Программа будет назначена как активная. Дни тренировок — Пн/Ср/Пт по умолчанию, можно поменять в настройках."}
              </span>
            </>
          ) : (
            <span className="app-footer-note">
              Программу можно доработать в конструкторе — веса, подходы и повторы редактируются.
            </span>
          )}
        </footer>
      </div>
    </div>
  );
}
