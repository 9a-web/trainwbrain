import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Globe, Send, Download, Dumbbell, CircleAlert, Check, TrendingUp, CalendarDays } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { getSharedProgram, importSharedProgram } from "@/api";
import { getEnv, hapticNotify } from "@/lib/platform";
import "./ImportLanding.css";

const LEVEL_LABELS = { beginner: "Новичок", intermediate: "Средний", advanced: "Продвинутый" };
const GOAL_LABELS = { strength: "Сила", hypertrophy: "Масса", powerlifting: "Пауэрлифтинг", general: "Общее" };
const MUSCLE_LABELS = {
  legs: "Ноги", chest: "Грудь", back: "Спина", shoulders: "Плечи",
  biceps: "Бицепс", triceps: "Трицепс", core: "Кор",
};
const DAY_LABELS = ["", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

const compactNum = (n) => {
  const v = Number(n) || 0;
  if (v >= 10000) return `${(v / 1000).toFixed(1).replace(/\.0$/, "")}т`;
  if (v >= 1000) return `${(v / 1000).toFixed(1)}т`;
  return `${Math.round(v)} кг`;
};

const formatSetsRow = (scheme, isPercentBased, hasLiftGroup) => {
  if (!scheme || !scheme.length) return "—";
  const showAsPct = isPercentBased && hasLiftGroup;
  const unit = showAsPct ? "%" : "кг";
  const parts = scheme.map((s) => {
    const w = s.weight;
    const sn = s.sets || 1;
    const r = s.reps || 0;
    const base = `${sn}×${r}`;
    if (w == null || w === 0) return base;
    const wf = Number.isInteger(w) ? w : Number(w).toFixed(1).replace(/\.0$/, "");
    return `${base} @ ${wf}${unit}`;
  });
  return parts.join(" · ");
};

// Мини-спарклайн-график тоннажа по неделям (SVG)
function TonnageSparkline({ data }) {
  const W = 300, H = 80, PAD = 8;
  const values = (data || []).map((d) => d.tonnage || 0);
  if (!values.length) return null;
  const maxV = Math.max(...values, 1);
  const minV = Math.min(...values);
  const range = Math.max(maxV - minV, 1);
  const n = values.length;
  const step = n > 1 ? (W - PAD * 2) / (n - 1) : 0;
  const pts = values.map((v, i) => {
    const x = PAD + i * step;
    const y = H - PAD - ((v - minV) / range) * (H - PAD * 2);
    return [x, y];
  });
  const poly = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${PAD},${H - PAD} ${poly} ${(PAD + (n - 1) * step).toFixed(1)},${H - PAD}`;
  return (
    <svg className="il-spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
      data-testid="forecast-sparkline">
      <defs>
        <linearGradient id="il-spark-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ff8a24" stopOpacity="0.42" />
          <stop offset="100%" stopColor="#ff8a24" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={area} fill="url(#il-spark-fill)" />
      <polyline points={poly} fill="none" stroke="#ffb85a" strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round" />
      {pts.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={i === 0 || i === n - 1 ? 3.5 : 2.2}
          fill={i === n - 1 ? "#ffd24a" : "#ff8a24"} />
      ))}
    </svg>
  );
}

export default function ImportLanding() {
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const env = getEnv();

  const code = decodeURIComponent((location.pathname.split("/import/")[1] || "")).trim();
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const [importing, setImporting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!code) {
      setError("Код не указан");
      return;
    }
    getSharedProgram(code)
      .then(setPreview)
      .catch((e) => {
        const d = e?.response?.data?.detail;
        setError(typeof d === "string" ? d : "Программа по этому коду не найдена");
      });
  }, [code]);

  const forecast = preview?.forecast;
  const week1 = preview?.week1_days || [];
  const isPct = !!forecast?.is_percent_based;

  const tonnageWeeks = useMemo(
    () => (forecast?.weekly_tonnage || []).filter((x) => x.tonnage > 0),
    [forecast],
  );

  const doImport = async () => {
    setImporting(true);
    try {
      const res = await importSharedProgram(code);
      hapticNotify("success");
      setDone(true);
      if (res.own) toast.info("Это ваша собственная программа");
      else if (res.already_imported) toast.info("Программа уже была импортирована");
      else toast.success(`«${res.template?.name}» добавлена в «Мои программы»`);
      setTimeout(() => navigate("/programs"), 900);
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Не удалось импортировать");
      hapticNotify("error");
    } finally {
      setImporting(false);
    }
  };

  const continueOnSite = () => {
    try {
      window.localStorage.setItem("twb_pending_import", code);
    } catch (e) {
      /* no-op */
    }
    navigate("/");
  };

  return (
    <div className="il-page" data-testid="import-landing">
      <div className="il-ambient" aria-hidden="true" />
      <img src="/TWBlogo.png" alt="TrainWithBrain" className="il-logo" />

      {error ? (
        <div className="il-card il-card-error" data-testid="import-error">
          <CircleAlert size={26} />
          <h2>Программа не найдена</h2>
          <p>{error}</p>
          <button className="il-btn il-btn-secondary" onClick={() => navigate("/")}>На главную</button>
        </div>
      ) : !preview ? (
        <div className="il-card">
          <div className="il-skel" />
          <div className="il-skel il-skel-sm" />
        </div>
      ) : (
        <>
          <div className="il-card" data-testid="import-preview">
            <span className="il-badge">Вам поделились программой</span>
            <span className="il-ico"><Dumbbell size={24} /></span>
            <h2 className="il-name">{preview.name}</h2>
            <p className="il-author">от {preview.author_name}</p>
            {preview.description ? <p className="il-desc">{preview.description}</p> : null}
            <div className="il-meta">
              <span>{preview.weeks_count} нед.</span>
              <span>·</span>
              <span>{preview.days_per_week || "—"} дн./нед.</span>
              <span>·</span>
              <span>{preview.exercises_count} упражнений</span>
            </div>
            <div className="il-tags">
              <span className="il-tag">{LEVEL_LABELS[preview.level] || preview.level}</span>
              <span className="il-tag">{GOAL_LABELS[preview.goal] || preview.goal}</span>
              {preview.requires_maxes ? <span className="il-tag il-tag-accent">%1ПМ</span> : null}
            </div>

            {isAuthenticated ? (
              <button className="il-btn il-btn-primary" onClick={doImport}
                disabled={importing || done} data-testid="import-btn">
                {done ? (<><Check size={17} /> Импортировано</>)
                  : importing ? "Импортируем…"
                  : (<><Download size={17} /> Импортировать в мои программы</>)}
              </button>
            ) : (
              <>
                <p className="il-choose">Где открыть программу?</p>
                <button className="il-btn il-btn-primary" onClick={continueOnSite}
                  data-testid="import-open-web">
                  <Globe size={17} /> Продолжить на сайте
                </button>
                {preview.tg_link && env !== "telegram" ? (
                  <a className="il-btn il-btn-tg" href={preview.tg_link} data-testid="import-open-tg">
                    <Send size={17} /> Открыть в Telegram
                  </a>
                ) : null}
                <p className="il-note">Потребуется вход — после него импорт продолжится автоматически.</p>
              </>
            )}
          </div>

          {week1.length > 0 ? (
            <section className="il-section" data-testid="import-week1">
              <header className="il-sec-h">
                <CalendarDays size={16} />
                <h3>Первая неделя</h3>
                <span className="il-sec-sub">{week1.length} {week1.length === 1 ? "день" : "дн."}</span>
              </header>
              <div className="il-days">
                {week1.map((d, i) => (
                  <article className="il-day" key={`${d.day_index}-${i}`} data-testid={`import-day-${i + 1}`}>
                    <div className="il-day-h">
                      <span className="il-day-idx">{DAY_LABELS[d.day_index] || `Д${i + 1}`}</span>
                      <span className="il-day-title">{d.title || `День ${i + 1}`}</span>
                    </div>
                    <ul className="il-ex">
                      {d.exercises.map((ex, ei) => (
                        <li key={ei} className="il-ex-row">
                          <div className="il-ex-main">
                            <span className="il-ex-name">{ex.name}</span>
                            <div className="il-ex-tags">
                              {ex.muscle_group ? (
                                <span className="il-ex-tag">{MUSCLE_LABELS[ex.muscle_group] || ex.muscle_group}</span>
                              ) : null}
                              {ex.is_accessory ? (
                                <span className="il-ex-tag il-ex-tag-acc">подсобка</span>
                              ) : null}
                            </div>
                          </div>
                          <div className="il-ex-sets">
                            {formatSetsRow(ex.sets_scheme, isPct, !!ex.lift_group)}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          {forecast && !isPct && tonnageWeeks.length >= 2 ? (
            <section className="il-section" data-testid="import-forecast">
              <header className="il-sec-h">
                <TrendingUp size={16} />
                <h3>Прогноз прогресса</h3>
                <span className="il-sec-sub">по тоннажу</span>
              </header>
              <div className="il-fc">
                <div className="il-fc-top">
                  <div className="il-fc-cell">
                    <span className="il-fc-lbl">Нед. 1</span>
                    <b className="il-fc-val">{compactNum(forecast.first_tonnage)}</b>
                  </div>
                  <span className={`il-fc-delta${(forecast.growth_pct || 0) >= 0 ? " up" : " down"}`}
                    data-testid="forecast-growth">
                    {(forecast.growth_pct || 0) >= 0 ? "+" : ""}{Math.round(forecast.growth_pct || 0)}%
                  </span>
                  <div className="il-fc-cell il-fc-cell-r">
                    <span className="il-fc-lbl">Нед. {forecast.weekly_tonnage?.[forecast.weekly_tonnage.length - 1]?.week}</span>
                    <b className="il-fc-val il-fc-val-accent">{compactNum(forecast.last_tonnage)}</b>
                  </div>
                </div>
                <TonnageSparkline data={forecast.weekly_tonnage} />
                <p className="il-fc-note">
                  Оценка на базе плановых весов × подходы × повторы. Реальный прогресс зависит от восстановления и техники.
                </p>
              </div>
            </section>
          ) : null}

          {forecast && isPct && forecast.first_percent != null && forecast.last_percent != null ? (
            <section className="il-section" data-testid="import-forecast">
              <header className="il-sec-h">
                <TrendingUp size={16} />
                <h3>Прогноз прогресса</h3>
                <span className="il-sec-sub">по %1ПМ</span>
              </header>
              <div className="il-fc">
                <div className="il-fc-top">
                  <div className="il-fc-cell">
                    <span className="il-fc-lbl">Нед. 1</span>
                    <b className="il-fc-val">{forecast.first_percent}%</b>
                  </div>
                  <span className={`il-fc-delta${(forecast.growth_points || 0) >= 0 ? " up" : " down"}`}
                    data-testid="forecast-growth">
                    {(forecast.growth_points || 0) >= 0 ? "+" : ""}{forecast.growth_points} п.п.
                  </span>
                  <div className="il-fc-cell il-fc-cell-r">
                    <span className="il-fc-lbl">Нед. {forecast.weekly_intensity?.[forecast.weekly_intensity.length - 1]?.week}</span>
                    <b className="il-fc-val il-fc-val-accent">{forecast.last_percent}%</b>
                  </div>
                </div>
                <p className="il-fc-note">
                  Программа на %1ПМ — масштабируется под ваши максимумы после импорта. Прогноз тоннажа скрыт.
                </p>
              </div>
            </section>
          ) : null}
        </>
      )}

      <p className="il-code" data-testid="import-code">Код: {code || "—"}</p>
    </div>
  );
}
