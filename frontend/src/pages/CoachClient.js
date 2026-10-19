import React, { useEffect, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Eye, EyeOff, Dumbbell, Check, RefreshCw, Pencil, Radio, ChevronRight, BarChart3, Share2, Download, Activity, Flame, Route } from "lucide-react";
import { toast } from "sonner";
import { useUser } from "@/context/UserContext";
import {
  getCoachClientPlan, getUserById, getTemplates, createPlan,
  setPlanVisibility, publishPlanWeek, setPlanTrainingDays, getCoachClientSession,
  sharePlan, exportPlanFile, getCardioStats,
} from "@/api";
import { useRealtime } from "@/hooks/useRealtime";
import Portal from "@/components/Portal";
import { haptic, hapticNotify } from "@/lib/platform";
import { useBackButton } from "@/hooks/useTelegramUI";
import "./Coach.css";

const WEEKDAYS = [
  { idx: 1, label: "Пн" }, { idx: 2, label: "Вт" }, { idx: 3, label: "Ср" },
  { idx: 4, label: "Чт" }, { idx: 5, label: "Пт" }, { idx: 6, label: "Сб" }, { idx: 7, label: "Вс" },
];

// Модалка настройки шаблона (максимумы + дни) — для шаблонов с requires_maxes
function AssignModal({ tpl, onClose, onSubmit, submitting }) {
  const needMaxes = !!tpl.requires_maxes;
  const daysNeeded = tpl.days_per_week || 3;
  const [squat, setSquat] = useState("");
  const [bench, setBench] = useState("");
  const [deadlift, setDeadlift] = useState("");
  const [days, setDays] = useState([]);

  const toggleDay = (idx) =>
    setDays((prev) =>
      prev.includes(idx)
        ? prev.filter((d) => d !== idx)
        : prev.length >= daysNeeded ? prev : [...prev, idx]
    );

  const maxesOk = !needMaxes || (Number(squat) > 0 && Number(bench) > 0 && Number(deadlift) > 0);
  const daysOk = days.length === daysNeeded;
  const canSubmit = maxesOk && daysOk && !submitting;

  const submit = () => {
    if (!canSubmit) return;
    const payload = { training_days: [...days].sort((a, b) => a - b) };
    if (needMaxes) payload.maxes = { squat: Number(squat), bench: Number(bench), deadlift: Number(deadlift) };
    onSubmit(payload);
  };

  return (
    <Portal>
    <div className="cfg-overlay" onClick={onClose} data-testid="assign-config-modal">
      <div className="cfg-modal" onClick={(e) => e.stopPropagation()}>
        <h3 className="cfg-title">{tpl.name}</h3>
        <p className="cfg-sub">Настройте программу под спортсмена</p>
        {needMaxes ? (
          <div className="cfg-section">
            <div className="cfg-section-title">Максимумы спортсмена (1ПМ), кг</div>
            <div className="cfg-maxes">
              <label className="cfg-max"><span>Присед</span>
                <input type="number" inputMode="decimal" value={squat} onChange={(e) => setSquat(e.target.value)} placeholder="0" /></label>
              <label className="cfg-max"><span>Жим</span>
                <input type="number" inputMode="decimal" value={bench} onChange={(e) => setBench(e.target.value)} placeholder="0" /></label>
              <label className="cfg-max"><span>Тяга</span>
                <input type="number" inputMode="decimal" value={deadlift} onChange={(e) => setDeadlift(e.target.value)} placeholder="0" /></label>
            </div>
          </div>
        ) : null}
        <div className="cfg-section">
          <div className="cfg-section-title">Дни тренировок <span className="cfg-hint">выберите {daysNeeded}</span></div>
          <div className="cfg-days">
            {WEEKDAYS.map((d) => (
              <button key={d.idx} type="button" className={`cfg-day ${days.includes(d.idx) ? "active" : ""}`} onClick={() => toggleDay(d.idx)}>
                {d.label}
              </button>
            ))}
          </div>
        </div>
        <div className="cfg-actions">
          <button className="cfg-btn-cancel" onClick={onClose}>Отмена</button>
          <button className="cfg-btn-save" onClick={submit} disabled={!canSubmit} data-testid="assign-submit">
            {submitting ? "Назначаем…" : "Назначить"}
          </button>
        </div>
      </div>
    </div>
    </Portal>
  );
}

export default function CoachClient() {
  const { athleteId } = useParams();
  const aid = Number(athleteId);
  const { user } = useUser();
  const coachId = user?.telegram_id;
  const navigate = useNavigate();
  useBackButton(true, () => navigate("/coach"));

  const [athlete, setAthlete] = useState(null);
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState([]);
  const [picking, setPicking] = useState(false);
  const [assignTpl, setAssignTpl] = useState(null);
  const [busy, setBusy] = useState(false);
  const [liveSession, setLiveSession] = useState(null);
  const [sharing, setSharing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [cardio, setCardio] = useState(null);

  const refetchLive = useCallback(async () => {
    if (!coachId || !aid) return;
    try {
      const s = await getCoachClientSession(coachId, aid);
      setLiveSession(s || null);
    } catch (e) {
      /* no-op */
    }
  }, [coachId, aid]);

  // Real-time: обновляем индикатор «идёт тренировка» вживую
  const onRtEvent = useCallback((evt) => {
    const t = evt.type || "";
    if (t.startsWith("session.")) {
      const sess = evt.payload?.session;
      if (sess && Number(sess.athlete_telegram_id) === aid) setLiveSession(sess);
      else refetchLive();
    }
  }, [aid, refetchLive]);
  useRealtime({ planId: plan?.id || null, enabled: !!plan?.id, onEvent: onRtEvent });

  const loadPlan = useCallback(async () => {
    if (!coachId || !aid) return;
    setLoading(true);
    try {
      const a = await getUserById(aid).catch(() => null);
      setAthlete(a);
      const p = await getCoachClientPlan(coachId, aid).catch((e) => {
        if (e?.response?.status === 403) toast.error("Нет доступа к этому спортсмену");
        return null;
      });
      setPlan(p);
    } finally {
      setLoading(false);
    }
  }, [coachId, aid]);

  useEffect(() => {
    loadPlan();
    refetchLive();
  }, [loadPlan, refetchLive]);

  // Фаза 3: кардио-норма подопечного за текущую неделю
  useEffect(() => {
    if (!aid) return undefined;
    let alive = true;
    getCardioStats(aid, { period: "week" })
      .then((d) => { if (alive) setCardio(d || null); })
      .catch(() => { if (alive) setCardio(null); });
    return () => { alive = false; };
  }, [aid]);

  const openPicker = async () => {
    haptic("light");
    setPicking(true);
    if (templates.length === 0) {
      try {
        setTemplates(await getTemplates());
      } catch (e) {
        /* no-op */
      }
    }
  };

  const assign = async (tpl, extra = {}) => {
    setBusy(true);
    try {
      const p = await createPlan({
        athlete_telegram_id: aid,
        template_id: tpl.id,
        coach_telegram_id: coachId,
        ...extra,
      });
      setPlan(p);
      setAssignTpl(null);
      setPicking(false);
      hapticNotify("success");
      toast.success("Программа назначена как черновик");
    } catch (e) {
      toast.error("Не удалось назначить программу");
    } finally {
      setBusy(false);
    }
  };

  const handleChoose = (tpl) => {
    if (tpl.requires_maxes) setAssignTpl(tpl);
    else assign(tpl);
  };

  const toggleVisibility = async () => {
    if (!plan) return;
    haptic("medium");
    const next = plan.visibility === "published" ? "draft" : "published";
    setBusy(true);
    try {
      const p = await setPlanVisibility(plan.id, next);
      setPlan(p);
      hapticNotify("success");
      toast.success(next === "published" ? "План опубликован — спортсмен его видит" : "План скрыт (черновик)");
    } catch (e) {
      toast.error("Не удалось изменить видимость");
    } finally {
      setBusy(false);
    }
  };

  const onShare = async () => {
    if (!plan || sharing) return;
    haptic("medium");
    setSharing(true);
    try {
      const { share_token } = await sharePlan(plan.id);
      const url = `${window.location.origin}/shared/plan/${share_token}`;
      try {
        await navigator.clipboard.writeText(url);
        toast.success("Ссылка на план скопирована");
      } catch (e) {
        toast.info(url);
      }
    } catch (e) {
      toast.error("Не удалось создать ссылку");
    } finally {
      setSharing(false);
    }
  };

  const onExport = async () => {
    if (!plan || exporting) return;
    haptic("light");
    setExporting(true);
    try {
      const res = await exportPlanFile(plan.id);
      const blob = new Blob([res.data], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${plan.name || "plan"}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Файл скачан");
    } catch (e) {
      toast.error("Не удалось экспортировать план");
    } finally {
      setExporting(false);
    }
  };

  const toggleDay = async (idx) => {
    if (!plan) return;
    haptic("light");
    const cur = new Set(plan.training_days || []);
    if (cur.has(idx)) cur.delete(idx);
    else cur.add(idx);
    const arr = [...cur].sort((a, b) => a - b);
    setPlan({ ...plan, training_days: arr });
    try {
      const p = await setPlanTrainingDays(plan.id, arr);
      setPlan(p);
    } catch (e) {
      toast.error("Не удалось сохранить дни");
      loadPlan();
    }
  };

  const toggleWeek = async (wk) => {
    if (!plan) return;
    haptic("light");
    const next = !(wk.published !== false);
    try {
      const p = await publishPlanWeek(plan.id, wk.week_index, next);
      setPlan(p);
    } catch (e) {
      toast.error("Не удалось изменить неделю");
    }
  };

  const editWeek = (weekIndex) => {
    haptic("light");
    navigate(`/coach/${aid}/edit`, { state: { week: weekIndex } });
  };

  const athleteName = athlete?.first_name || "Спортсмен";
  const isPublished = plan?.visibility === "published";

  return (
    <div className="coach-page" data-testid="coach-client-page">
      <header className="coach-header">
        <button className="coach-back" onClick={() => navigate("/coach")} aria-label="Назад" data-testid="coach-client-back">
          <ArrowLeft size={22} />
        </button>
        <h1 className="coach-title">{athleteName}</h1>
      </header>

      {loading ? (
        <div className="coach-empty">Загрузка…</div>
      ) : !plan ? (
        <>
          <div className="coach-noplan" data-testid="client-noplan-block">
            <Dumbbell size={26} />
            <p>У спортсмена нет активной программы.</p>
            {!picking ? (
              <button className="coach-primary-btn" onClick={openPicker} data-testid="assign-program-btn">
                Назначить программу
              </button>
            ) : null}
          </div>
          {picking ? (
            <div className="programs-list" data-testid="assign-template-list">
              {templates.map((tpl) => (
                <div className="program-card" key={tpl.id}>
                  <div className="program-card-head">
                    <div className="program-card-icon"><Dumbbell size={20} /></div>
                    <div className="program-card-titles">
                      <h3 className="program-card-name">{tpl.name}</h3>
                    </div>
                  </div>
                  <p className="program-card-desc">{tpl.description}</p>
                  <div className="program-card-meta">
                    <span>{tpl.weeks_count} нед.</span><span>·</span><span>{tpl.days_per_week} дн./нед.</span>
                  </div>
                  <button className="program-card-button" onClick={() => handleChoose(tpl)} disabled={busy} data-testid={`assign-choose-${tpl.slug || tpl.id}`}>
                    {busy ? "Назначаем…" : "Назначить"}
                  </button>
                </div>
              ))}
            </div>
          ) : null}
        </>
      ) : (
        <>
          {/* Тренировка вживую (real-time наблюдение + co-scribe) */}
          {(() => {
            const live = liveSession && liveSession.status === "in_progress";
            return (
              <button
                className={`cl-live-entry ${live ? "is-live" : ""}`}
                onClick={() => { haptic("medium"); navigate(`/coach/${aid}/live`); }}
                data-testid="open-live-btn"
              >
                <span className="cl-live-entry-left">
                  {live ? <span className="live-dot" /> : <Radio size={18} />}
                  <span className="cl-live-entry-text">
                    <span className="cl-live-entry-title">
                      {live ? "Идёт тренировка — смотреть" : "Тренировка вживую"}
                    </span>
                    <span className="cl-live-entry-sub">
                      {live
                        ? (liveSession.title || "Открыть живой просмотр")
                        : "Наблюдать и заполнять в реальном времени"}
                    </span>
                  </span>
                </span>
                <ChevronRight size={20} className="client-chevron" />
              </button>
            );
          })()}

          {/* Подробная статистика подопечного */}
          <button
            className="cl-live-entry cl-stats-entry"
            onClick={() => { haptic("light"); navigate(`/coach/${aid}/stats`); }}
            data-testid="open-client-stats-btn"
          >
            <span className="cl-live-entry-left">
              <BarChart3 size={18} />
              <span className="cl-live-entry-text">
                <span className="cl-live-entry-title">Статистика</span>
                <span className="cl-live-entry-sub">Тоннаж, прогресс, 1ПМ, соответствие плану</span>
              </span>
            </span>
            <ChevronRight size={20} className="client-chevron" />
          </button>

          {/* Фаза 3: кардио-норма за неделю */}
          <div className="coach-block" data-testid="coach-cardio-block">
            <div className="coach-block-head">
              <div>
                <div className="coach-block-title">Кардио за неделю</div>
                <div className="coach-block-sub">
                  {cardio?.weekly_target
                    ? `Норма ${cardio.weekly_target} мин · ${cardio.weekly_minutes || 0} мин выполнено`
                    : "Норма не задана"}
                </div>
              </div>
              {cardio?.weekly_target ? (
                <span
                  className={`vis-badge ${
                    (cardio.weekly_minutes || 0) >= cardio.weekly_target ? "vis-published" : "vis-draft"
                  }`}
                  data-testid="coach-cardio-badge"
                >
                  {(cardio.weekly_minutes || 0) >= cardio.weekly_target ? "норма выполнена" : "не выполнена"}
                </span>
              ) : null}
            </div>
            {cardio?.weekly_target ? (
              <div className="coach-cardio-track" data-testid="coach-cardio-track">
                <i
                  style={{
                    width: `${Math.min(
                      100,
                      Math.round(((cardio.weekly_minutes || 0) / cardio.weekly_target) * 100)
                    )}%`,
                  }}
                />
              </div>
            ) : null}
            <div className="coach-cardio-stats">
              <span data-testid="coach-cardio-sessions">
                <Activity size={15} /> <b>{cardio?.sessions || 0}</b> сессий
              </span>
              <span data-testid="coach-cardio-km">
                <Route size={15} /> <b>{cardio?.km || 0}</b> км
              </span>
              <span data-testid="coach-cardio-kcal">
                <Flame size={15} /> <b>{cardio?.kcal || 0}</b> ккал
              </span>
            </div>
            <button
              className="coach-primary-btn is-secondary"
              onClick={() => { haptic("light"); navigate(`/coach/${aid}/stats`); }}
              data-testid="coach-cardio-details"
            >
              Подробнее в статистике
            </button>
          </div>

          {/* Видимость плана */}
          <div className="coach-block" data-testid="visibility-block">
            <div className="coach-block-head">
              <div>
                <div className="coach-block-title">{plan.name}</div>
                <div className="coach-block-sub">
                  {plan.weeks?.length || 0} нед. · {isPublished ? "виден спортсмену" : "черновик (скрыт)"}
                </div>
              </div>
              <span className={`vis-badge vis-${plan.visibility}`}>
                {isPublished ? "опубликован" : "черновик"}
              </span>
            </div>
            <button
              className={`coach-primary-btn ${isPublished ? "is-secondary" : ""}`}
              onClick={toggleVisibility}
              disabled={busy}
              data-testid="toggle-visibility-btn"
            >
              {isPublished ? (<><EyeOff size={16} /> Скрыть (вернуть в черновик)</>) : (<><Eye size={16} /> Опубликовать для спортсмена</>)}
            </button>
          </div>

          {/* Поделиться / экспорт */}
          <div className="coach-block" data-testid="share-export-block">
            <div className="coach-block-title">Поделиться планом</div>
            <div className="coach-block-sub">
              Публичная read-only ссылка или файл Excel — для спортсмена и коллег.
            </div>
            <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
              <button
                className="coach-primary-btn is-secondary"
                onClick={onShare}
                disabled={sharing}
                data-testid="share-plan-btn"
              >
                <Share2 size={16} /> {sharing ? "Создаём…" : "Ссылка"}
              </button>
              <button
                className="coach-primary-btn is-secondary"
                onClick={onExport}
                disabled={exporting}
                data-testid="export-plan-btn"
              >
                <Download size={16} /> {exporting ? "Готовим…" : "Excel"}
              </button>
            </div>
          </div>

          {/* Тренировочные дни */}
          <div className="coach-block" data-testid="training-days-block">
            <div className="coach-block-title">Тренировочные дни</div>
            <div className="coach-block-sub">Спортсмен увидит их в недельном календаре</div>
            <div className="cfg-days">
              {WEEKDAYS.map((d) => (
                <button
                  key={d.idx}
                  type="button"
                  className={`cfg-day ${(plan.training_days || []).includes(d.idx) ? "active" : ""}`}
                  onClick={() => toggleDay(d.idx)}
                  data-testid={`coach-day-${d.idx}`}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          {/* Недели плана */}
          <div className="coach-block" data-testid="weeks-block">
            <div className="coach-block-title">Недели плана</div>
            <div className="coach-block-sub">Нажмите на неделю, чтобы изменить тренировки. Глаз — открыть/скрыть неделю спортсмену.</div>
            <div className="weeks-list">
              {[...(plan.weeks || [])]
                .sort((a, b) => (a.week_index || 0) - (b.week_index || 0))
                .map((wk) => {
                  const wkPublished = wk.published !== false;
                  const workoutDays = (wk.days || []).filter((d) => !d.is_rest).length;
                  return (
                    <div
                      className="week-row week-row-click"
                      key={wk.week_index}
                      data-testid={`week-row-${wk.week_index}`}
                      role="button"
                      tabIndex={0}
                      onClick={() => editWeek(wk.week_index)}
                      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") editWeek(wk.week_index); }}
                    >
                      <div className="week-info">
                        <span className="week-name">Неделя {wk.week_index}</span>
                        <span className="week-days">{workoutDays} трен.</span>
                      </div>
                      <div className="week-row-right">
                        <button
                          className={`week-toggle ${wkPublished ? "on" : "off"}`}
                          onClick={(e) => { e.stopPropagation(); toggleWeek(wk); }}
                          data-testid={`week-toggle-${wk.week_index}`}
                          aria-pressed={wkPublished}
                        >
                          {wkPublished ? (<><Eye size={14} /> видна</>) : (<><EyeOff size={14} /> скрыта</>)}
                        </button>
                        <Pencil size={15} className="week-edit-ico" aria-hidden="true" />
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>

          <button
            className="coach-primary-btn is-secondary ed-open-btn"
            onClick={() => navigate(`/coach/${aid}/edit`)}
            data-testid="edit-plan-btn"
          >
            <Pencil size={16} /> Редактировать весь план
          </button>

          <button className="coach-text-btn" onClick={openPicker} data-testid="reassign-btn">
            <RefreshCw size={14} /> Сменить программу
          </button>
          {picking ? (
            <div className="programs-list" data-testid="reassign-template-list">
              {templates.map((tpl) => (
                <div className="program-card" key={tpl.id}>
                  <div className="program-card-head">
                    <div className="program-card-icon"><Dumbbell size={20} /></div>
                    <div className="program-card-titles">
                      <h3 className="program-card-name">{tpl.name}</h3>
                    </div>
                  </div>
                  <div className="program-card-meta">
                    <span>{tpl.weeks_count} нед.</span><span>·</span><span>{tpl.days_per_week} дн./нед.</span>
                  </div>
                  <button className="program-card-button" onClick={() => handleChoose(tpl)} disabled={busy} data-testid={`reassign-choose-${tpl.slug || tpl.id}`}>
                    {busy ? "Назначаем…" : "Назначить"}
                  </button>
                </div>
              ))}
            </div>
          ) : null}
        </>
      )}

      {assignTpl ? (
        <AssignModal
          tpl={assignTpl}
          submitting={busy}
          onClose={() => setAssignTpl(null)}
          onSubmit={(payload) => assign(assignTpl, payload)}
        />
      ) : null}
    </div>
  );
}
