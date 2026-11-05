import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft, Activity, Camera, ImagePlus, Plus, Pencil, Trash2, Heart, Flame, Route, Clock,
  Sparkles, RefreshCw,
} from "lucide-react";
import { toast } from "sonner";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { useUser } from "@/context/UserContext";
import { useBackButton } from "@/hooks/useTelegramUI";
import { useCapabilities } from "@/hooks/useCapabilities";
import {
  listCardio, getCardioStats, createCardio, patchCardio, deleteCardio, parseCardioPhoto,
  parseCardioPhotoBg, getAiJob,
} from "@/api";
import { addBgJob, removeBgJob } from "@/hooks/useBackgroundJobs";
import CardioForm from "@/components/CardioForm";
import Heart3D from "@/components/Heart3D";
import "./Cardio.css";

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
  const [parseProgress, setParseProgress] = useState(0);
  const [parseStage, setParseStage] = useState("");
  const [aiConfidence, setAiConfidence] = useState(null);
  const parseTimerRef = useRef(null);
  const cameraRef = useRef(null);
  const galleryRef = useRef(null);

  useEffect(() => () => {
    if (parseTimerRef.current) window.clearTimeout(parseTimerRef.current);
  }, []);
  const canLog = capabilities ? can("log_cardio") : false;

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
    () => Math.max(60, ...chartData.map((d) => d.minutes), (stats?.weekly_target || 0) / 7),
    [chartData, stats?.weekly_target]
  );

  const chartSummary = useMemo(() => {
    const active = chartData.filter((d) => d.minutes > 0);
    const best = active.reduce((top, day) => (day.minutes > (top?.minutes || 0) ? day : top), null);
    return {
      activeDays: active.length,
      bestDay: best ? `${best.label}, ${best.minutes} мин` : "нет тренировок",
    };
  }, [chartData]);

  const typeBreakdown = useMemo(() => {
    const byType = stats?.by_type || {};
    return Object.entries(byType)
      .map(([type, value]) => ({ type, label: TYPE_LABELS[type] || "Кардио", minutes: Math.round(value?.minutes || 0) }))
      .filter((row) => row.minutes > 0)
      .sort((a, b) => b.minutes - a.minutes);
  }, [stats]);

  const weekly = stats?.weekly_target
    ? Math.min(100, Math.round(((stats.weekly_minutes || 0) / stats.weekly_target) * 100))
    : null;
  const avgHr = Number(stats?.avg_hr) || 0;
  const heartRate = avgHr > 0 ? avgHr : null;

  const openManualForm = () => {
    setEditing(null);
    setDraft(null);
    setAiConfidence(null);
    setFormOpen(true);
  };

  const openEditForm = (it) => {
    setDraft(null);
    setAiConfidence(null);
    setEditing(it);
    setFormOpen(true);
  };

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
    if (!window.confirm(`Удалить «${TYPE_LABELS[it.type] || "кардио"}» от ${fmtDate(it.date)}?`)) return;
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
    const fileName = (file.name || "").toLowerCase();
    const isImage = file.type.startsWith("image/") || /\.(jpe?g|png|webp|heic)$/i.test(fileName);
    if (!isImage) {
      toast.error("Выберите фотографию консоли");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      toast.error("Фото слишком большое — максимум 8 МБ");
      return;
    }
    setParsing(true);
    setParseProgress(10);
    setParseStage("Подготавливаем снимок");
    try {
      // Запускаем фоновую задачу
      const { job_id } = await parseCardioPhotoBg(file);
      setParseProgress(30);
      setParseStage("Задача запущена, распознаём…");

      // Сохраняем в персистентное хранилище
      addBgJob({ id: job_id, kind: "cardio_parse", preview: "Разбор фото кардио" });

      // Опрашиваем задачу
      let done = false;
      const deadline = Date.now() + 120 * 1000; // 2 минуты
      while (!done && Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 1500));
        let job;
        try {
          job = await getAiJob(job_id);
        } catch {
          continue;
        }
        // Обновляем прогресс
        if (job.progress && typeof job.progress === "string" && job.progress.length > 3) {
          setParseStage(job.progress);
          setParseProgress(Math.min(90, 30 + (job.progress.length % 60)));
        }
        if (job.status === "done") {
          removeBgJob(job_id);
          const tpl = job.template;
          setDraft(tpl?.draft || {});
          setAiConfidence(tpl?.confidence || "low");
          setEditing(null);
          setParseProgress(100);
          setParseStage("Готово — проверяем цифры");
          done = true;
          toast.success(tpl?.draft && Object.keys(tpl.draft).length
            ? "AI распознал показатели — проверьте данные"
            : "Фото открыто — заполните показатели вручную");
          setFormOpen(true);
        } else if (job.status === "error") {
          removeBgJob(job_id);
          throw new Error(job.error || "Не удалось распознать фото");
        }
      }
      if (!done) {
        removeBgJob(job_id);
        throw new Error("ИИ отвечает слишком долго — попробуйте ещё раз");
      }
    } catch (err) {
      toast.error(err.message || err?.response?.data?.detail || "Не удалось распознать фото");
    } finally {
      parseTimerRef.current = window.setTimeout(() => {
        setParsing(false);
        setParseProgress(0);
        setParseStage("");
        parseTimerRef.current = null;
      }, 350);
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
            onClick={openManualForm}
            aria-label="Добавить кардио"
            data-testid="cardio-add"
          >
            <Plus size={20} />
          </button>
        ) : <span className="cd-add-spacer" />}
      </header>

      {/* Сводка: editorial training log */}
      <section className="cd-heart-banner" data-testid="cardio-heart-banner">
        <div className="cd-heart-visual" aria-hidden="true">
          <div className="cd-heart-halo" style={{ "--heart-period": `${heartRate ? Math.max(0.42, Math.min(1.4, 60 / heartRate)) : 0.9}s` }} />
          <Heart3D heartRate={heartRate} />
        </div>
        <div className="cd-heart-copy">
          <div className="cd-kicker">СИСТЕМА / CARDIO</div>
          <h2>Ритм, который<br /><em>движет тебя</em></h2>
          <div className="cd-heart-readout"><Heart size={15} /><strong>{heartRate || "—"}</strong><span>{heartRate ? "ср. bpm за период" : "пульс пока не измерен"}</span></div>
        </div>
      </section>

      <section className="cd-hero cd-editorial-hero" data-testid="cardio-hero">
        <div className="cd-editorial-head">
          <div>
            <div className="cd-kicker">КАРДИО / {period === "month" ? "30 ДНЕЙ" : "7 ДНЕЙ"}</div>
            <div className="cd-hero-main">
              <div className="cd-hero-num" data-testid="cardio-week-minutes">{stats?.weekly_minutes ?? 0}</div>
              <div className="cd-hero-unit">минут<br />этой недели</div>
            </div>
          </div>
          {stats?.weekly_target ? (
            <div className="cd-goal-delta" data-testid="cardio-goal">
              <b>{weekly}%</b><span>от цели</span>
            </div>
          ) : null}
        </div>
        {stats?.weekly_target ? (
          <div className="cd-goal cd-editorial-goal">
            <div className="cd-goal-track"><i style={{ width: `${weekly}%` }} /></div>
            <span className="cd-goal-text">{stats.weekly_minutes ?? 0} из {stats.weekly_target} минут</span>
          </div>
        ) : null}
        <div className="cd-metric-rail" aria-label="Сводка кардио">
          <div className="cd-metric" data-testid="cardio-stat-sessions"><b>{stats?.sessions ?? 0}</b><span>сессий</span></div>
          <div className="cd-metric" data-testid="cardio-stat-km"><b>{stats?.km ?? 0}</b><span>км</span></div>
          <div className="cd-metric" data-testid="cardio-stat-kcal"><b>{stats?.kcal ?? 0}</b><span>ккал</span></div>
          <div className="cd-metric" data-testid="cardio-stat-hr"><b>{heartRate ?? "—"}</b><span>ср. пульс</span></div>
        </div>
      </section>

      {/* График */}
      <section className="cd-card cd-trend-card" data-testid="cardio-chart-card">
        <div className="cd-card-head">
          <div><div className="cd-kicker">ОБЪЁМ</div><h3 className="cd-card-title">Минуты по дням</h3></div>
          <div className="cd-period" data-testid="cardio-period">
            <button type="button" className={period === "week" ? "on" : ""} onClick={() => setPeriod("week")} data-testid="cardio-period-week">7 дней</button>
            <button type="button" className={period === "month" ? "on" : ""} onClick={() => setPeriod("month")} data-testid="cardio-period-month">30 дней</button>
          </div>
        </div>
        <div className="cd-chart" role="img" aria-label={`Кардио за период: ${chartSummary.activeDays} активных дней, лучший день — ${chartSummary.bestDay}`}>
          <ResponsiveContainer width="100%" height={190}>
            <LineChart data={chartData} margin={{ top: 12, right: 8, left: -22, bottom: 0 }}>
              <XAxis dataKey="label" tick={{ fill: "#8f948f", fontSize: 10 }} axisLine={false} tickLine={false} interval={period === "month" ? 4 : 0} />
              <YAxis domain={[0, maxMinutes]} tick={{ fill: "#737a74", fontSize: 10 }} axisLine={false} tickLine={false} width={34} tickCount={4} />
              {stats?.weekly_target ? <ReferenceLine y={stats.weekly_target / 7} stroke="#a5aaa3" strokeDasharray="3 5" strokeOpacity={0.55} /> : null}
              <Tooltip
                cursor={{ stroke: "rgba(246,243,232,.24)", strokeWidth: 1 }}
                contentStyle={{ background: "#202420", border: "1px solid rgba(246,243,232,.16)", borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: "#f6f3e8", marginBottom: 3 }}
                formatter={(v) => [`${v} мин`, "Объём"]}
              />
              <Line type="monotone" dataKey="minutes" stroke="#d7ddd4" strokeWidth={2} dot={{ r: 3, fill: "#ff8a24", stroke: "#111312", strokeWidth: 2 }} activeDot={{ r: 5, fill: "#ff8a24", stroke: "#f6f3e8", strokeWidth: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="cd-chart-caption"><span>{chartSummary.activeDays} активных {pluralize(chartSummary.activeDays, ["день", "дня", "дней"])}</span><span>лучший: {chartSummary.bestDay}</span></div>
      </section>

      {typeBreakdown.length ? (
        <section className="cd-card cd-breakdown" data-testid="cardio-breakdown-card">
          <div className="cd-card-head"><div><div className="cd-kicker">РАСПРЕДЕЛЕНИЕ</div><h3 className="cd-card-title">По типу нагрузки</h3></div></div>
          <div className="cd-breakdown-list">
            {typeBreakdown.map((row) => {
              const share = Math.round((row.minutes / Math.max(1, typeBreakdown[0].minutes)) * 100);
              return <div className="cd-breakdown-row" key={row.type}><div className="cd-breakdown-label"><span>{row.label}</span><b>{row.minutes} мин</b></div><div className="cd-breakdown-track"><i style={{ width: `${share}%` }} /></div></div>;
            })}
          </div>
        </section>
      ) : null}

      {/* Фото консоли */}
      {canLog ? (
        <section className={`cd-ai-card ${parsing ? "is-scanning" : ""}`} data-testid="cardio-ai-card">
          <div className="cd-ai-orbit" aria-hidden="true"><span /><span /><span /></div>
          <div className="cd-ai-copy">
            <div className="cd-ai-label"><Sparkles size={14} /> AI-ЗАПОЛНЕНИЕ</div>
            <h2>{parsing ? "Считываем консоль" : "Покажи фото — остальное сделает AI"}</h2>
            <p>{parsing ? (parseStage || "Ищем время, дистанцию и пульс") : "Распознаем показатели тренажёра и подготовим черновик за секунды."}</p>
            {parsing ? <div className="cd-ai-progress"><i style={{ width: `${parseProgress}%` }} /><span>{parseProgress}%</span></div> : null}
          </div>
          <div className="cd-ai-actions">
            <button type="button" className="cd-ai-action" onClick={() => cameraRef.current?.click()} disabled={parsing} data-testid="cardio-photo-btn">
              {parsing ? <RefreshCw className="cd-spin" size={20} /> : <Camera size={20} />}
              <span>{parsing ? "Сканируем" : "Сфотографировать"}</span>
            </button>
            <button type="button" className="cd-ai-action" onClick={() => galleryRef.current?.click()} disabled={parsing} data-testid="cardio-photo-gallery-btn">
              <ImagePlus size={20} />
              <span>Из галереи</span>
            </button>
          </div>
        </section>
      ) : null}
      <input
        ref={cameraRef} type="file" accept="image/*" capture="environment"
        style={{ display: "none" }} onChange={handlePhoto} data-testid="cardio-photo-camera-input"
      />
      <input
        ref={galleryRef} type="file" accept="image/*"
        style={{ display: "none" }} onChange={handlePhoto} data-testid="cardio-photo-gallery-input"
      />

      {/* Список */}
      <section className="cd-card" data-testid="cardio-list-card">
        <div className="cd-card-head">
          <div><div className="cd-kicker">ЖУРНАЛ</div><h3 className="cd-card-title">История тренировок</h3></div>
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
              <button type="button" className="cd-empty-cta" onClick={openManualForm}>
                Добавить первую
              </button>
            ) : null}
          </div>
        ) : (
          <div className="cd-list">
            {items.map((it) => (
              <div className="cd-row" key={it.id} data-testid={`cardio-row-${it.id}`}>
                <span className="cd-row-ico" aria-hidden="true" />
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
                      onClick={() => openEditForm(it)}
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
              aiConfidence={!editing && draft ? aiConfidence : null}
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
