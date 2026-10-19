import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Check, Trophy, Dumbbell, Target, Flame, CalendarDays, ChevronDown } from "lucide-react";
import { useUser } from "@/context/UserContext";
import { useBackButton } from "@/hooks/useTelegramUI";
import { getStreakData } from "@/api";
import "./Streak.css";

const WD = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

const pluralize = (n, forms) => {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return forms[2];
  if (b > 1 && b < 5) return forms[1];
  if (b === 1) return forms[0];
  return forms[2];
};

const fmtDayMonth = (iso) => {
  const d = new Date(`${iso}T00:00:00`);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
};

const fmtRange = (startIso, endIso) => {
  const s = new Date(`${startIso}T00:00:00`);
  const e = new Date(`${endIso}T00:00:00`);
  const year = e.getFullYear() !== new Date().getFullYear() ? ` ${e.getFullYear()}` : "";
  if (s.getMonth() === e.getMonth()) {
    return `${s.getDate()}–${e.getDate()} ${MONTHS[e.getMonth()]}${year}`;
  }
  return `${s.getDate()} ${MONTHS[s.getMonth()]} – ${e.getDate()} ${MONTHS[e.getMonth()]}${year}`;
};

const GiftIcon = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    {/* Крышка */}
    <rect x="2.5" y="6.5" width="19" height="4.5" rx="1.2" fill="currentColor" opacity="0.92" />
    {/* Коробка */}
    <path d="M4 11h16v9.2a1.3 1.3 0 0 1-1.3 1.3H5.3A1.3 1.3 0 0 1 4 20.2V11Z" fill="currentColor" opacity="0.72" />
    {/* Лента вертикальная */}
    <rect x="10.6" y="6.5" width="2.8" height="15" fill="#1c1c1c" opacity="0.85" />
    {/* Бант */}
    <path d="M12 6.5c-.6-2-2.2-3.4-4-2.9-1.6.4-2.4 2-1.6 3.4.6 1 2 1.5 3.6 1.5H12Z" fill="currentColor" />
    <path d="M12 6.5c.6-2 2.2-3.4 4-2.9 1.6.4 2.4 2 1.6 3.4-.6 1-2 1.5-3.6 1.5H12Z" fill="currentColor" />
    <circle cx="12" cy="6.2" r="1.2" fill="#1c1c1c" opacity="0.85" />
  </svg>
);

function DayCircle({ d }) {
  let cls = "sk-circle";
  if (d.trained) cls += " is-done";
  else if (d.is_today) cls += " is-today";
  else if (d.is_future) cls += " is-future";
  else cls += " is-miss";
  return (
    <div className="sk-day" data-testid={`sk-day-${d.weekday}`}>
      <span className="sk-day-label">{WD[d.weekday - 1]}</span>
      <span className={cls}>
        {d.trained ? <Check size={20} strokeWidth={3} /> : null}
        {!d.trained && d.is_today ? <i className="sk-today-dot" /> : null}
      </span>
    </div>
  );
}

export default function StreakPage() {
  const { user } = useUser();
  const navigate = useNavigate();
  const tg = user?.telegram_id;
  useBackButton(true, () => navigate(-1));

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [weeksN, setWeeksN] = useState(13);
  const [showAllStreaks, setShowAllStreaks] = useState(false);
  const hmRef = useRef(null);

  useEffect(() => {
    if (!tg) return undefined;
    let alive = true;
    setLoading(true);
    getStreakData(tg, { weeks: weeksN })
      .then((d) => { if (alive) setData(d); })
      .catch(() => { if (alive) setData(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [tg, weeksN]);

  const cur = data?.current_streak || 0;
  const best = data?.best_streak || 0;
  const total = data?.total_workouts || 0;
  const activeDays = data?.active_days ?? total;
  const goal = data?.weekly_goal || 0;
  const thisWeek = data?.trained_this_week || 0;
  const weekDays = data?.week?.days || [];
  const calendar = useMemo(() => data?.calendar || [], [data]);
  const streaks = useMemo(() => data?.streaks || [], [data]);
  const thisMonth = data?.this_month || 0;
  const avgPerWeek = data?.avg_per_week || 0;
  const rewardActive = goal > 0 && thisWeek >= goal;

  // Ярлыки серий над колонками календаря: колонка -> серия, начинающаяся в ней
  const colBadges = useMemo(() => {
    const dateToCol = {};
    calendar.forEach((wk, i) => (wk.days || []).forEach((d) => { dateToCol[d.date] = i; }));
    const badges = {};
    streaks.forEach((s) => {
      let col = dateToCol[s.start];
      if (col === undefined && dateToCol[s.end] !== undefined) col = 0; // серия началась до видимого периода
      if (col === undefined) return;
      if (!badges[col] || badges[col].length < s.length) badges[col] = s;
    });
    return badges;
  }, [calendar, streaks]);

  // Автопрокрутка календаря к последним (свежим) неделям
  useEffect(() => {
    const el = hmRef.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [calendar]);

  // Метки месяцев над колонками хитмапа
  const monthLabels = calendar.map((wk, i) => {
    const m = new Date(wk.week_start).getMonth();
    const prev = i > 0 ? new Date(calendar[i - 1].week_start).getMonth() : null;
    return m !== prev ? MONTHS[m] : "";
  });

  return (
    <div className="sk-page" data-testid="streak-page">
      <div className="sk-ambient" aria-hidden="true" />
      <header className="sk-header">
        <button className="sk-back" onClick={() => navigate(-1)} aria-label="Назад" data-testid="streak-back">
          <ArrowLeft size={22} />
        </button>
        <h1 className="sk-title">Тренировочная серия</h1>
      </header>

      {loading && !data ? (
        <div className="sk-skel" data-testid="streak-loading">
          <div className="sk-skel-block h230" />
          <div className="sk-skel-block h140" />
          <div className="sk-skel-block h170" />
        </div>
      ) : (
        <>
          {/* Hero */}
          <div className="sk-hero" data-testid="streak-hero">
            <div className="sk-hero-glow" />
            <div className={`sk-flame ${cur > 0 ? "lit" : ""}`}>
              <img src="/img/3d/fire.png" alt="" className="sk-flame-img" />
            </div>
            <div className="sk-num" data-testid="streak-current">{cur}</div>
            <div className="sk-num-label">
              {pluralize(cur, ["день", "дня", "дней"])} подряд
            </div>
            <div className="sk-substats">
              <div className="sk-sub" data-testid="streak-best">
                <Trophy size={15} />
                <b>{best}</b>
                <span>рекорд</span>
              </div>
              <div className="sk-sub" data-testid="streak-total">
                <Dumbbell size={15} />
                <b>{total}</b>
                <span>{pluralize(total, ["тренировка", "тренировки", "тренировок"])}</span>
              </div>
              <div className="sk-sub" data-testid="streak-week-goal">
                <Target size={15} />
                <b>{goal ? `${thisWeek}/${goal}` : thisWeek}</b>
                <span>за неделю</span>
              </div>
            </div>
          </div>

          {/* Мини-статистика */}
          <div className="sk-mini" data-testid="streak-mini-stats">
            <div className="sk-mini-tile" data-testid="streak-mini-month">
              <CalendarDays size={16} />
              <b>{thisMonth}</b>
              <span>в этом месяце</span>
            </div>
            <div className="sk-mini-tile" data-testid="streak-mini-avg">
              <Flame size={16} />
              <b>{avgPerWeek}</b>
              <span>в среднем / нед</span>
            </div>
            <div className="sk-mini-tile" data-testid="streak-mini-days">
              <Check size={16} />
              <b>{activeDays}</b>
              <span>{pluralize(activeDays, ["активный день", "активных дня", "активных дней"])}</span>
            </div>
          </div>

          {/* Эта неделя */}
          <section className="sk-card" data-testid="streak-week">
            <div className="sk-card-head">
              <h3 className="sk-card-title">Эта неделя</h3>
              {goal ? (
                <span className="sk-card-hint">цель {goal} в неделю</span>
              ) : null}
            </div>
            <div className="sk-week">
              {weekDays.map((d) => (
                <DayCircle key={d.date} d={d} />
              ))}
              <div className="sk-day sk-reward" data-testid="streak-reward">
                <span className="sk-day-label">Приз</span>
                <span className={`sk-gift ${rewardActive ? "active" : ""}`}>
                  <GiftIcon size={22} />
                </span>
              </div>
            </div>
            {goal ? (
              <>
                <div className="sk-goal-track" data-testid="streak-goal-bar">
                  <i style={{ width: `${Math.min(100, Math.round((thisWeek / goal) * 100))}%` }} />
                </div>
                <p className="sk-reward-note">
                  {rewardActive
                    ? "Цель недели выполнена — так держать! 🎉"
                    : `Ещё ${goal - thisWeek} ${pluralize(goal - thisWeek, ["тренировка", "тренировки", "тренировок"])} до награды за неделю`}
                </p>
              </>
            ) : null}
          </section>

          {/* Календарь (как в GitHub) */}
          <section className="sk-card" data-testid="streak-history">
            <div className="sk-card-head">
              <h3 className="sk-card-title">Календарь</h3>
              <div className="sk-period" data-testid="streak-period-toggle">
                <button
                  type="button"
                  className={weeksN === 13 ? "on" : ""}
                  onClick={() => setWeeksN(13)}
                  data-testid="streak-period-3m"
                >
                  3 мес
                </button>
                <button
                  type="button"
                  className={weeksN === 26 ? "on" : ""}
                  onClick={() => setWeeksN(26)}
                  data-testid="streak-period-6m"
                >
                  6 мес
                </button>
              </div>
            </div>
            <div className={`sk-heatmap-wrap ${loading ? "is-refetch" : ""}`} ref={hmRef}>
              <div className="sk-hm-labels">
                <span className="sk-hm-label sk-hm-badge-spacer" />
                <span className="sk-hm-label sk-hm-month-spacer" />
                {WD.map((w) => (
                  <span key={w} className="sk-hm-label">{w}</span>
                ))}
              </div>
              <div className="sk-hm-body">
                {/* Ярлыки серий над колонками */}
                <div className="sk-hm-streakrow" data-testid="streak-badges-row">
                  {calendar.map((wk, i) => (
                    <span className="sk-hm-slot" key={wk.week_start}>
                      {colBadges[i] ? (
                        <span
                          className={`sk-hm-badge${colBadges[i].is_best ? " best" : ""}${colBadges[i].is_current ? " cur" : ""}`}
                          title={`Серия ${colBadges[i].length} ${pluralize(colBadges[i].length, ["день", "дня", "дней"])}: ${fmtRange(colBadges[i].start, colBadges[i].end)}`}
                          data-testid="streak-badge"
                        >
                          <Flame size={9} strokeWidth={2.5} />
                          {colBadges[i].length}
                        </span>
                      ) : null}
                    </span>
                  ))}
                </div>
                <div className="sk-hm-months">
                  {monthLabels.map((m, i) => (
                    <span key={`${m}-${i}`} className="sk-hm-month">{m}</span>
                  ))}
                </div>
                <div className="sk-heatmap" data-testid="streak-heatmap">
                  {calendar.map((wk) => (
                    <div className="sk-hm-week" key={wk.week_start}>
                      {wk.days.map((d) => {
                        const inRun = d.trained && (d.streak_len || 0) >= 2;
                        let cls = "sk-hm-cell";
                        if (d.trained) cls += (d.count || 0) >= 2 ? " done hot" : " done";
                        else if (d.is_future) cls += " future";
                        if (inRun) {
                          cls += " streak";
                          if (d.streak_start || d.weekday === 1) cls += " run-start";
                          if (d.streak_end || d.weekday === 7) cls += " run-end";
                          if (!d.streak_end && d.weekday < 7) cls += " conn";
                        }
                        if (d.is_today) cls += " today";
                        const tip = `${fmtDayMonth(d.date)}${d.count ? ` · ${d.count} трен.` : ""}${inRun ? ` · серия ${d.streak_len} дн.` : ""}`;
                        return (
                          <span key={d.date} className={cls} title={tip} aria-label={tip} />
                        );
                      })}
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="sk-hm-legend">
              <span className="sk-hm-legend-left">
                {activeDays} {pluralize(activeDays, ["активный день", "активных дня", "активных дней"])} · {calendar.length} нед.
              </span>
              <span className="sk-legend-scale">
                <span>меньше</span>
                <i className="sk-hm-cell" />
                <i className="sk-hm-cell done dim" />
                <i className="sk-hm-cell done" />
                <i className="sk-hm-cell done hot" />
                <span>больше</span>
              </span>
            </div>
          </section>

          {/* Мои серии */}
          <section className="sk-card" data-testid="streak-series">
            <div className="sk-card-head">
              <h3 className="sk-card-title">Мои серии</h3>
              {streaks.length ? (
                <span className="sk-card-hint">
                  {streaks.length} {pluralize(streaks.length, ["серия", "серии", "серий"])}
                </span>
              ) : null}
            </div>
            {streaks.length === 0 ? (
              <p className="sk-series-empty" data-testid="streak-series-empty">
                Позанимайся 2 дня подряд — появится первая серия 🔥
              </p>
            ) : (
              <>
                <div className="sk-series-list">
                  {(showAllStreaks ? streaks : streaks.slice(0, 5)).map((s) => (
                    <div
                      className={`sk-series-row${s.is_current ? " cur" : ""}`}
                      key={s.start}
                      data-testid="streak-series-row"
                    >
                      <span className={`sk-series-flame${s.is_best ? " best" : ""}${s.is_current ? " on" : ""}`}>
                        <Flame size={15} />
                        <b>{s.length}</b>
                      </span>
                      <div className="sk-series-info">
                        <div className="sk-series-range">{fmtRange(s.start, s.end)}</div>
                        <div className="sk-series-sub">
                          {s.length} {pluralize(s.length, ["день", "дня", "дней"])} подряд
                        </div>
                      </div>
                      {s.is_current ? (
                        <span className="sk-series-tag cur" data-testid="streak-tag-current">сейчас</span>
                      ) : null}
                      {s.is_best ? (
                        <span className="sk-series-tag best" data-testid="streak-tag-best">
                          <Trophy size={11} /> рекорд
                        </span>
                      ) : null}
                    </div>
                  ))}
                </div>
                {streaks.length > 5 ? (
                  <button
                    type="button"
                    className="sk-series-more"
                    onClick={() => setShowAllStreaks((v) => !v)}
                    data-testid="streak-series-more"
                  >
                    {showAllStreaks ? "Свернуть" : `Показать все (${streaks.length})`}
                    <ChevronDown size={14} className={showAllStreaks ? "flip" : ""} />
                  </button>
                ) : null}
              </>
            )}
          </section>

          {total === 0 ? (
            <p className="sk-empty-note" data-testid="streak-empty">
              Заверши первую тренировку — и серия начнётся 🔥
            </p>
          ) : null}

          <div className="sk-foot" />
        </>
      )}
    </div>
  );
}
