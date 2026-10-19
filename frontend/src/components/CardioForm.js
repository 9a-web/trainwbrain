import React, { useEffect, useMemo, useState } from "react";
import { Activity, X, Zap } from "lucide-react";
import "./CardioForm.css";

const TYPES = [
  { key: "treadmill", label: "Дорожка", icon: "🏃" },
  { key: "bike", label: "Вело", icon: "🚴" },
  { key: "rower", label: "Гребля", icon: "🚣" },
  { key: "walk", label: "Ходьба", icon: "🚶" },
  { key: "elliptical", label: "Эллипс", icon: "⛷️" },
  { key: "other", label: "Другое", icon: "🏋️" },
];

const INTENSITIES = [
  { key: "low", label: "Низкая" },
  { key: "moderate", label: "Средняя" },
  { key: "high", label: "Высокая" },
];

const todayIso = () => new Date().toISOString().slice(0, 10);

/**
 * Форма кардио-сессии. Используется для создания и правки.
 * initial — существующая сессия (или черновик из фото).
 */
export default function CardioForm({ initial, onSave, onCancel, saving = false, title = "Кардио" }) {
  const base = initial || {};
  const [type, setType] = useState(base.type || "treadmill");
  const [date, setDate] = useState(base.date || todayIso());
  const [minutes, setMinutes] = useState(
    base.duration_sec ? String(Math.round(base.duration_sec / 60)) : ""
  );
  const [distance, setDistance] = useState(
    base.distance_km != null ? String(base.distance_km) : ""
  );
  const [avgHr, setAvgHr] = useState(base.avg_hr != null ? String(base.avg_hr) : "");
  const [maxHr, setMaxHr] = useState(base.max_hr != null ? String(base.max_hr) : "");
  const [calories, setCalories] = useState(base.calories != null ? String(base.calories) : "");
  const [intensity, setIntensity] = useState(base.intensity || "moderate");
  const [rpe, setRpe] = useState(base.rpe != null ? String(base.rpe) : "");
  const [incline, setIncline] = useState(
    base.incline_percent != null ? String(base.incline_percent) : ""
  );
  const [notes, setNotes] = useState(base.notes || "");
  const [err, setErr] = useState("");

  // Сброс при смене initial (черновик из фото)
  useEffect(() => {
    if (!initial) return;
    setType(initial.type || "treadmill");
    if (initial.duration_sec) setMinutes(String(Math.round(initial.duration_sec / 60)));
    if (initial.distance_km != null) setDistance(String(initial.distance_km));
    if (initial.avg_hr != null) setAvgHr(String(initial.avg_hr));
    if (initial.max_hr != null) setMaxHr(String(initial.max_hr));
    if (initial.calories != null) setCalories(String(initial.calories));
    if (initial.intensity) setIntensity(initial.intensity);
    if (initial.rpe != null) setRpe(String(initial.rpe));
    if (initial.incline_percent != null) setIncline(String(initial.incline_percent));
    if (initial.notes) setNotes(initial.notes);
  }, [initial]);

  const isTreadmill = type === "treadmill" || type === "walk";
  const pacePreview = useMemo(() => {
    const d = parseFloat(distance);
    const m = parseFloat(minutes);
    if (!(d > 0) || !(m > 0)) return null;
    const paceSec = (m * 60) / d;
    return `${String(Math.floor(paceSec / 60)).padStart(2, "0")}:${String(
      Math.round(paceSec % 60)
    ).padStart(2, "0")}`;
  }, [distance, minutes]);

  const submit = (e) => {
    e.preventDefault();
    setErr("");
    const m = parseFloat(minutes);
    if (!(m > 0)) {
      setErr("Укажите длительность больше 0");
      return;
    }
    const num = (v) => (v === "" || v == null ? null : Number(v));
    const body = {
      type,
      date,
      duration_sec: Math.round(m * 60),
      distance_km: num(distance),
      avg_hr: num(avgHr),
      max_hr: num(maxHr),
      calories: num(calories),
      intensity,
      rpe: num(rpe),
      incline_percent: isTreadmill ? num(incline) : null,
      notes: notes.trim() || null,
    };
    if (body.avg_hr != null && (body.avg_hr < 30 || body.avg_hr > 230)) {
      setErr("Пульс должен быть от 30 до 230");
      return;
    }
    onSave(body);
  };

  return (
    <form className="cf" onSubmit={submit} data-testid="cardio-form">
      <div className="cf-head">
        <h2 className="cf-title">{title}</h2>
        <button type="button" className="cf-close" onClick={onCancel} aria-label="Закрыть" data-testid="cardio-form-close">
          <X size={20} />
        </button>
      </div>

      <div className="cf-types" role="group" aria-label="Тип кардио">
        {TYPES.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`cf-type ${type === t.key ? "on" : ""}`}
            onClick={() => setType(t.key)}
            data-testid={`cardio-type-${t.key}`}
          >
            <span className="cf-type-ico">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      <label className="cf-field">
        <span>Дата</span>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} data-testid="cardio-date" />
      </label>

      <div className="cf-row">
        <label className="cf-field">
          <span>Длительность, мин</span>
          <input
            type="number" min="1" max="720" inputMode="numeric" placeholder="30"
            value={minutes} onChange={(e) => setMinutes(e.target.value)}
            data-testid="cardio-duration"
          />
        </label>
        <label className="cf-field">
          <span>Дистанция, км</span>
          <input
            type="number" min="0" step="0.01" inputMode="decimal" placeholder="4.2"
            value={distance} onChange={(e) => setDistance(e.target.value)}
            data-testid="cardio-distance"
          />
        </label>
      </div>

      {pacePreview ? (
        <p className="cf-pace" data-testid="cardio-pace">
          <Zap size={13} /> Темп ≈ {pacePreview} /км
        </p>
      ) : null}

      <div className="cf-row">
        <label className="cf-field">
          <span>Средний пульс</span>
          <input
            type="number" min="30" max="230" inputMode="numeric" placeholder="142"
            value={avgHr} onChange={(e) => setAvgHr(e.target.value)}
            data-testid="cardio-avg-hr"
          />
        </label>
        <label className="cf-field">
          <span>Макс. пульс</span>
          <input
            type="number" min="30" max="230" inputMode="numeric" placeholder="168"
            value={maxHr} onChange={(e) => setMaxHr(e.target.value)}
            data-testid="cardio-max-hr"
          />
        </label>
      </div>

      <div className="cf-row">
        <label className="cf-field">
          <span>Калории</span>
          <input
            type="number" min="0" inputMode="numeric" placeholder="авто"
            value={calories} onChange={(e) => setCalories(e.target.value)}
            data-testid="cardio-calories"
          />
        </label>
        <label className="cf-field">
          <span>RPE (1–10)</span>
          <input
            type="number" min="1" max="10" step="0.5" inputMode="decimal" placeholder="6.5"
            value={rpe} onChange={(e) => setRpe(e.target.value)}
            data-testid="cardio-rpe"
          />
        </label>
      </div>

      {isTreadmill ? (
        <label className="cf-field">
          <span>Наклон, %</span>
          <input
            type="number" min="0" max="40" step="0.5" inputMode="decimal" placeholder="6"
            value={incline} onChange={(e) => setIncline(e.target.value)}
            data-testid="cardio-incline"
          />
        </label>
      ) : null}

      <div className="cf-field">
        <span>Интенсивность</span>
        <div className="cf-intens" role="group" aria-label="Интенсивность">
          {INTENSITIES.map((it) => (
            <button
              key={it.key}
              type="button"
              className={`cf-int ${intensity === it.key ? "on" : ""}`}
              onClick={() => setIntensity(it.key)}
              data-testid={`cardio-intensity-${it.key}`}
            >
              {it.label}
            </button>
          ))}
        </div>
      </div>

      <label className="cf-field">
        <span>Заметка</span>
        <textarea
          rows={2} placeholder="Как прошло, самочувствие…" maxLength={1000}
          value={notes} onChange={(e) => setNotes(e.target.value)}
          data-testid="cardio-notes"
        />
      </label>

      {err ? <p className="cf-err" data-testid="cardio-form-error">{err}</p> : null}

      <div className="cf-actions">
        <button type="button" className="cf-btn ghost" onClick={onCancel} data-testid="cardio-cancel">
          Отмена
        </button>
        <button type="submit" className="cf-btn primary" disabled={saving} data-testid="cardio-save">
          <Activity size={16} />
          {saving ? "Сохраняем…" : "Сохранить"}
        </button>
      </div>
    </form>
  );
}
