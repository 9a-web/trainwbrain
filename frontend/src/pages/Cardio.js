import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft, Activity, Camera, Plus, Pencil, Trash2, Heart, Flame, Route, Clock,
} from "lucide-react";
import { toast } from "sonner";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { useUser } from "@/context/UserContext";
import { useBackButton } from "@/hooks/useTelegramUI";
import { useCapabilities } from "@/hooks/useCapabilities";
import {
  listCardio, getCardioStats, createCardio, patchCardio, deleteCardio, parseCardioPhoto,
} from "@/api";
import CardioForm from "@/components/CardioForm";
import "./Cardio.css";

const TYPE_ICONS = {
  treadmill: "🏃", bike: "🚴", rower: "🚣", walk: "🚶", elliptical: "⛷️", other: "🏋️",
};
const TYPE_LABELS = {
  treadmill: "Дорожка", bike: "Велотренажёр", rower: "Гребля",
  walk: "Ходьба", elliptical: "Эллипс", other: "Другое",
};
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

const fmtMinutes = (min) => {
  const m = Math.round(min || 0);
  if (m < 60) return `${m} мин`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  return r ? `${h} ч ${r} мин` : `${h} ч`;
};

const fmtDate = (iso) => {
  const d = new Date(`${iso}T00:00:00`);
  const today = new Date();
  const yest = new Date(); yest.setDate(today.getDate() - 1);
  const same = (a, b) => a.toDateString() === b.toDateString();
  if (same(d, today)) return "Сегодня";
  if (same(d, yest)) return "Вчера";
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
};

const isoDay = (d) => d.toISOString().slice(0, 10);

export default function CardioPage() {
  const { user } = useUser();
  const navigate = useNavigate();
  const tg = user?.telegram_id;
  const { can, capabilities } = useCapabilities();
  useBackButton(true, () => navigate(-1));

  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState("week");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);   // сессия для правки
  const [draft, setDraft] = useState(null);       // черновик из фото
  const [saving, setSaving] = useState(false);
  const [parsing, setParsing] = useState(false);
  const fileRef = useRef(null);
  const gradId = useId().replace(/:/g, "");

  const canLog = !capabilities ? true : can("log_cardio");

  const load = useCallback(async () => {
    if (!tg) return;
    setLoading(true);
    try {
      const [list, st] = await Promise.all([
        listCardio({ athlete: tg, limit: 200 }),
        getCardioStats(tg, { period }),
      ]);
      setItems(list?.items || []);
      setStats(st || null);
    } catch (e) {
      toast.error("Не удалось загрузить кардио");
      setItems([]);
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, [tg, period]);

  useEffect(() => { load(); }, [load]);

  // Динамика по дням (для графика)
  const chartData = useMemo(() => {
    const days = period === "month" ? 30 : 7;
    const byDay = {};
    (items || []).forEach((it) => {
      byDay[it.date] = (byDay[it.date] || 0) + Math.round((it.duration_sec || 0) / 60);
    });
    const out = [];
    const now = new Date();
    for (let i = days - 1; i >= 0; i -= 1) {
      const d = new Date(now);
      d.setDate(now.getDate() - i);
      const iso = isoDay(d);
      out.push({ date: iso, label: WD[(d.getDay() + 6) % 7], minutes: byDay[iso] || 0 });
    }
    return out;
  }, [items, period]);

  const maxMinutes = useMemo(
    () => Math.max(60, ...chartData.map((d) => d.minutes)),
    [chartData]
  );

  const weekly = stats?.weekly_target
    ? Math.min(100, Math.round(((stats.weekly_minutes || 0) / stats.weekly_target) * 100))
    : null;

  const handleSave = async (body) => {
    setSaving(true);
    try {
      if (editing) {
        await patchCardio(editing.id, body);
        toast.success("Кардио обновлено");
      } else {
        await createCardio({ ...body, athlete_telegram_id: tg });
        toast.success("Кардио добавлено");
      }
      setFormOpen(false);
      setEditing(null);
      setDraft(null);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (it) => {
    if (!window.confirm("Удалить эту кардио-сессию?")) return;
    try {
      await deleteCardio(it.id);
      toast.success("Удалено");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Не удалось удалить");
    }
  };

  const handlePhoto = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setParsing(true);
    try {
      const res = await parseCardioPhoto(file);
      setDraft(res?.draft || {});
      setEditing(null);
      setFormOpen(true);
      toast.success("Фото распознано — проверьте данные");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Не удалось распознать фото");
    } finally {
      setParsing(false);
    }
  };

  return (
    <div className="cd-page" data-testid="cardio-page">
      <div className="cd-ambient" aria-hidden="true" />
      <header className="cd-header">
        <button className="cd-back" onClick={() => navigate(-1)} aria-label="Назад" data-testid="cardio-back">
          <ArrowLeft size={22} />
        </button>
        <h1 className="cd-title">Кардио</h1>
        {canLog ? (
          <button
            className="cd-add"
            onClick={() => { setEditing(null); setDraft(null); setFormOpen(true); }}
            aria-label="Добавить кардио"
            data-testid="cardio-add"
          >
            <Plus size={20} />
          </button>
        ) : <span className="cd-add-spacer" />}
      </header>

      {/* Сводка */}
      <section className="cd-hero" data-testid="cardio-hero">
        <div className="cd-hero-glow" />
        <div className="cd-hero-main">
          <div className="cd-hero-num" data-testid="cardio-week-minutes">
            {stats?.weekly_minutes ?? 0}
          </div>
          <div className="cd-hero-unit">мин за неделю</div>
        </div>
        {stats?.weekly_target ? (
          <div className="cd-goal" data-testid="cardio-goal">
            <div className="cd-goal-track">
              <i style={{ width: `${weekly}%` }} />
            </div>
            <span className="cd-goal-text">
              Норма {stats.weekly_target} мин · {weekly}%
            </span>
          </div>
        ) : null}
        <div className="cd-hero-tiles">
          <div className="cd-tile" data-testid="cardio-stat-sessions">
            <Activity size={15} /><b>{stats?.sessions ?? 0}</b><span>сессий</span>
          </div>
          <div className="cd-tile" data-testid="cardio-stat-km">
            <Route size={15} /><b>{stats?.km ?? 0}</b><span>км</span>
          </div>
          <div className="cd-tile" data-testid="cardio-stat-kcal">
            <Flame size={15} /><b>{stats?.kcal ?? 0}</b><span>ккал</span>
          </div>
          {stats?.avg_hr ? (
            <div className="cd-tile" data-testid="cardio-stat-hr">
              <Heart size={15} /><b>{stats.avg_hr}</b><span>ср. пульс</span>
            </div>
          ) : null}
        </div>
      </section>

      {/* График */}
      <section className="cd-card" data-testid="cardio-chart-card">
        <div className="cd-card-head">
          <h3 className="cd-card-title">Динамика</h3>
          <div className="cd-period" data-testid="cardio-period">
            <button type="button" className={period === "week" ? "on" : ""} onClick={() => setPeriod("week")} data-testid="cardio-period-week">7 дней</button>
            <button type="button" className={period === "month" ? "on" : ""} onClick={() => setPeriod("month")} data-testid="cardio-period-month">30 дней</button>
          </div>
        </div>
        <div className="cd-chart">
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={chartData} margin={{ top: 6, right: 4, left: -22, bottom: 0 }}>
              <defs>
                <linearGradient id={`cdBar-${gradId}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#FF8A24" />
                  <stop offset="100%" stopColor="#FF6B00" stopOpacity={0.5} />
                </linearGradient>
              </defs>
              <XAxis dataKey="label" tick={{ fill: "#8a8a8a", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis domain={[0, maxMinutes]} tick={{ fill: "#6a6a6a", fontSize: 10 }} axisLine={false} tickLine={false} width={34} />
              <Tooltip
                cursor={{ fill: "rgba(255,255,255,0.04)" }}
                contentStyle={{ background: "#1f1f1f", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, fontSize: 12 }}
                labelStyle={{ color: "#cfcfcf" }}
                formatter={(v) => [`${v} мин`, "Кардио"]}
              />
              <Bar dataKey="minutes" radius={[6, 6, 0, 0]} fill={`url(#cdBar-${gradId})`}>
                {chartData.map((d) => (
                  <Cell key={d.date} fill={d.minutes > 0 ? `url(#cdBar-${gradId})` : "rgba(255,255,255,0.05)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Фото консоли */}
      {canLog ? (
        <button
          type="button"
          className="cd-photo"
          onClick={() => fileRef.current?.click()}
          disabled={parsing}
          data-testid="cardio-photo-btn"
        >
          <Camera size={18} />
          {parsing ? "Распознаём фото…" : "Добавить по фото консоли"}
        </button>
      ) : null}
      <input
        ref={fileRef} type="file" accept="image/*" capture="environment"
        style={{ display: "none" }} onChange={handlePhoto} data-testid="cardio-photo-input"
      />

      {/* Список */}
      <section className="cd-card" data-testid="cardio-list-card">
        <div className="cd-card-head">
          <h3 className="cd-card-title">История</h3>
          <span className="cd-card-hint">
            {items.length} {pluralize(items.length, ["запись", "записи", "записей"])}
          </span>
        </div>

        {loading && items.length === 0 ? (
          <div className="cd-skel" data-testid="cardio-loading">
            <div className="cd-skel-row" /><div className="cd-skel-row" /><div className="cd-skel-row" />
          </div>
        ) : items.length === 0 ? (
          <div className="cd-empty" data-testid="cardio-empty">
            <div className="cd-empty-ico">🏃</div>
            <p>Пока нет кардио-записей</p>
            {canLog ? (
              <button type="button" className="cd-empty-cta" onClick={() => { setDraft(null); setEditing(null); setFormOpen(true); }}>
                Добавить первую
              </button>
            ) : null}
          </div>
        ) : (
          <div className="cd-list">
            {items.map((it) => (
              <div className="cd-row" key={it.id} data-testid={`cardio-row-${it.id}`}>
                <span className="cd-row-ico">{TYPE_ICONS[it.type] || "🏋️"}</span>
                <div className="cd-row-main">
                  <div className="cd-row-top">
                    <b>{TYPE_LABELS[it.type] || "Кардио"}</b>
                    <span className="cd-row-date">{fmtDate(it.date)}</span>
                  </div>
                  <div className="cd-row-meta">
                    <span><Clock size={12} /> {fmtMinutes((it.duration_sec || 0) / 60)}</span>
                    {it.distance_km ? <span><Route size={12} /> {it.distance_km} км</span> : null}
                    {it.calories ? <span><Flame size={12} /> {it.calories} ккал</span> : null}
                    {it.avg_hr ? <span><Heart size={12} /> {it.avg_hr}</span> : null}
                    {it.coach_telegram_id ? <span className="cd-row-coach">тренер</span> : null}
                  </div>
                  {it.notes ? <div className="cd-row-note">{it.notes}</div> : null}
                </div>
                {canLog ? (
                  <div className="cd-row-ops">
                    <button
                      type="button" className="cd-op" aria-label="Изменить"
                      onClick={() => { setDraft(null); setEditing(it); setFormOpen(true); }}
                      data-testid={`cardio-edit-${it.id}`}
                    >
                      <Pencil size={15} />
                    </button>
                    <button
                      type="button" className="cd-op danger" aria-label="Удалить"
                      onClick={() => handleDelete(it)}
                      data-testid={`cardio-delete-${it.id}`}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="cd-foot" />

      {formOpen ? (
        <div className="cd-modal" role="dialog" aria-modal="true" data-testid="cardio-modal">
          <div className="cd-modal-backdrop" onClick={() => { setFormOpen(false); setEditing(null); setDraft(null); }} />
          <div className="cd-modal-body">
            <CardioForm
              initial={editing || draft}
              title={editing ? "Изменить кардио" : "Новое кардио"}
              saving={saving}
              onSave={handleSave}
              onCancel={() => { setFormOpen(false); setEditing(null); setDraft(null); }}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
