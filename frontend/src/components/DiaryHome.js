import React, { useState, useEffect, useCallback, useMemo } from "react";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { useUser } from "@/context/UserContext";
import {
  listDiarySessions,
  getDiaryProfile,
  putDiaryProfile,
  diaryAnalyze,
  diaryWeekly,
  diaryNext,
  pollDiaryJob,
  deleteDiarySession,
} from "@/api";
import DiaryComposer from "@/components/DiaryComposer";
import DiaryChat from "@/components/DiaryChat";
import WorkoutView from "@/components/WorkoutView";
import { DayCard } from "@/components/DateSelector";
import "@/components/DateSelector.css";
import "@/components/Diary.css";

const DOW = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const MONTHS_GEN = [
  "Января", "Февраля", "Марта", "Апреля", "Мая", "Июня",
  "Июля", "Августа", "Сентября", "Октября", "Ноября", "Декабря",
];
const WEEK_OFFSETS = [-1, 0, 1];
const toISO = (d) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
};
const isSameISO = (d, iso) => toISO(d) === iso;

const diffCat = (score) =>
  score == null ? null : score < 36 ? "Легко" : score < 61 ? "Средне" : score < 81 ? "Тяжело" : "Очень тяжело";

const GOALS = [["hypertrophy", "Масса"], ["strength", "Сила"], ["powerlifting", "Пауэрлифтинг"], ["general", "ОФП"]];
const EXP = [["beginner", "Новичок"], ["intermediate", "Средний"], ["advanced", "Продвинутый"]];
const EQUIP = [["gym", "Зал"], ["barbell_home", "Штанга дома"], ["dumbbells", "Гантели"], ["bodyweight", "Свой вес"]];

const AiFeedback = ({ fb }) => {
  if (!fb) return null;
  return (
    <div className="ai-feedback" data-testid="diary-ai-feedback">
      {fb.summary && <div className="fb-summary">{fb.summary}</div>}
      {fb.difficulty_comment && (
        <div className="fb-section">
          <h5>Про нагрузку</h5>
          <div style={{ fontSize: 13, color: "rgba(255,255,255,0.8)" }}>{fb.difficulty_comment}</div>
        </div>
      )}
      {fb.good && fb.good.length > 0 && (
        <div className="fb-section">
          <h5>Хорошо</h5>
          <ul>{fb.good.map((g, i) => <li key={i}>{g}</li>)}</ul>
        </div>
      )}
      {fb.improve && fb.improve.length > 0 && (
        <div className="fb-section">
          <h5>Улучшить</h5>
          <ul>{fb.improve.map((g, i) => <li key={i}>{g}</li>)}</ul>
        </div>
      )}
      {fb.progression && <div className="fb-prog">➜ {fb.progression}</div>}
    </div>
  );
};

const DiaryHome = () => {
  const { user } = useUser();
  const tg = user?.telegram_id;
  const [weekOffset, setWeekOffset] = useState(0);
  const [selected, setSelected] = useState(toISO(new Date()));
  const [sessions, setSessions] = useState([]);
  const [profile, setProfile] = useState(null);
  const [composerOpen, setComposerOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [prefill, setPrefill] = useState(null);
  const [analyzing, setAnalyzing] = useState(null);
  const [obOpen, setObOpen] = useState(false);
  const [weekly, setWeekly] = useState(null);
  const [weeklyOpen, setWeeklyOpen] = useState(false);
  const [busyAgent, setBusyAgent] = useState("");

  const days = useMemo(() => {
    const base = new Date();
    const monday = new Date(base);
    monday.setDate(base.getDate() - ((base.getDay() + 6) % 7) + weekOffset * 7);
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(monday);
      d.setDate(monday.getDate() + i);
      return d;
    });
  }, [weekOffset]);

  const load = useCallback(async () => {
    if (!tg) return;
    try {
      const list = await listDiarySessions({ limit: 200 });
      setSessions(list || []);
    } catch (e) {
      /* no-op */
    }
  }, [tg]);

  useEffect(() => {
    load();
    getDiaryProfile().then(setProfile).catch(() => {});
    const onProg = () => load();
    window.addEventListener("twb:progress", onProg);
    return () => window.removeEventListener("twb:progress", onProg);
  }, [load]);

  const datesWithEntry = useMemo(
    () => new Set(sessions.map((s) => (s.date || "").slice(0, 10))),
    [sessions]
  );
  const dayEntries = sessions.filter((s) => (s.date || "").slice(0, 10) === selected);

  const selDate = new Date(`${selected}T00:00:00`);
  const formattedDate = `${selDate.getDate()} ${MONTHS_GEN[selDate.getMonth()]}`;

  // Собираем view для WorkoutView (тот же элемент, что в режиме «План»).
  const makeView = (s) => {
    const score = s.difficulty_score != null ? s.difficulty_score : s.difficulty?.score;
    const cat = diffCat(score);
    return {
      ...s,
      stats: { ...(s.stats || {}), difficulty: cat || (s.stats && s.stats.difficulty) || "—" },
    };
  };

  const handleAnalyze = async (session) => {
    setAnalyzing(session.id);
    try {
      const { job_id } = await diaryAnalyze(session.id);
      const job = await pollDiaryJob(job_id);
      if (job.status === "done" && job.template) {
        setSessions((ss) => ss.map((s) => (s.id === session.id ? { ...s, ai_feedback: job.template } : s)));
        toast.success("Разбор готов");
      } else {
        toast.error(job.error || "Не удалось разобрать");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Ошибка разбора");
    } finally {
      setAnalyzing(null);
    }
  };

  const handleDelete = async (id) => {
    try {
      await deleteDiarySession(id);
      setSessions((ss) => ss.filter((s) => s.id !== id));
      window.dispatchEvent(new Event("twb:progress"));
      toast.success("Запись удалена");
    } catch (e) {
      toast.error("Не удалось удалить");
    }
  };

  const handleWeekly = async () => {
    setBusyAgent("weekly");
    try {
      const res = await diaryWeekly();
      setWeekly(res);
      setWeeklyOpen(true);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Не удалось получить разбор недели");
    } finally {
      setBusyAgent("");
    }
  };

  const handleNext = async () => {
    setBusyAgent("next");
    try {
      const { job_id } = await diaryNext("");
      const job = await pollDiaryJob(job_id);
      if (job.status === "done" && job.template) {
        setPrefill(job.template.exercises || []);
        setComposerOpen(true);
        toast.success(`Тренировка «${job.template.title}» готова — проверь и запиши`);
      } else {
        toast.error(job.error || "Не удалось собрать тренировку");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Ошибка генерации");
    } finally {
      setBusyAgent("");
    }
  };

  const openRecord = () => {
    setPrefill(null);
    setComposerOpen(true);
  };

  return (
    <div className="date-selector" data-testid="diary-home">
      {/* Та же строка выбора недели/дней, что и в режиме «План» */}
      <div className="date-selector-row">
        <div className="week-dots" role="tablist" aria-label="Выбор недели" data-testid="diary-week-dots">
          {WEEK_OFFSETS.map((offset) => (
            <button
              key={offset}
              type="button"
              className={`week-dot ${weekOffset === offset ? "week-dot-active" : ""}`}
              onClick={() => setWeekOffset(offset)}
              role="tab"
              aria-selected={weekOffset === offset}
              aria-label={offset === 0 ? "Текущая неделя" : offset > 0 ? "Следующая неделя" : "Прошлая неделя"}
            />
          ))}
        </div>
        <div className="date-selector-scroll" data-testid="diary-week">
          {days.map((d, i) => {
            const iso = toISO(d);
            const has = datesWithEntry.has(iso);
            return (
              <DayCard
                key={iso}
                date={d}
                dayName={DOW[(d.getDay() + 6) % 7]}
                dayNumber={d.getDate()}
                progress={has ? 100 : 0}
                isWorkout={has}
                isSelected={isSameISO(d, selected)}
                onClick={() => setSelected(iso)}
                index={i}
              />
            );
          })}
        </div>
      </div>

      {/* Заголовок даты + действие — тот же блок, что в «Плане» */}
      <div className="date-title-row">
        <h2 className="selected-date-title">{formattedDate}</h2>
        <div className="date-actions" data-testid="date-actions">
          <button
            className="launch-button"
            type="button"
            onClick={openRecord}
            data-testid="diary-record-btn"
          >
            <Plus className="launch-button-icon" size={16} strokeWidth={2.5} />
            <span>Записать</span>
          </button>
        </div>
      </div>

      {profile && !profile.onboarded && (
        <button
          className="diary-btn diary-btn-ghost"
          style={{ width: "100%", marginBottom: 14 }}
          onClick={() => setObOpen(true)}
          data-testid="diary-onboard-btn"
        >
          ⚙️ Настрой ИИ-тренера под себя →
        </button>
      )}

      {/* Содержимое дня — тот же WorkoutView, что и в плане */}
      {dayEntries.length === 0 ? (
        <div className="no-plan-card" data-testid="diary-empty">
          <p className="no-plan-text">
            На этот день записей нет. Запиши, что сделал — ИИ разберёт и подскажет.
          </p>
          <button className="no-plan-button" onClick={openRecord} data-testid="diary-empty-record">
            Записать тренировку
          </button>
        </div>
      ) : (
        dayEntries.map((s) => (
          <div className="diary-entry-block" key={s.id} data-testid={`diary-entry-${s.id}`}>
            <div className="diary-entry-preview-label">
              <span className="diary-entry-preview-dot" aria-hidden="true" />
              Запись дневника
            </div>
            <WorkoutView view={makeView(s)} isPreview />
            {s.ai_feedback ? (
              <AiFeedback fb={s.ai_feedback} />
            ) : (
              <div className="diary-btn-row">
                <button
                  className="diary-btn-sm"
                  onClick={() => handleAnalyze(s)}
                  disabled={analyzing === s.id}
                  data-testid={`diary-analyze-${s.id}`}
                >
                  {analyzing === s.id ? <span className="diary-spinner" /> : "🧠 Разбор ИИ"}
                </button>
              </div>
            )}
            <div className="diary-btn-row">
              <button
                className="diary-btn-sm diary-btn-danger"
                onClick={() => handleDelete(s.id)}
                data-testid={`diary-delete-${s.id}`}
              >
                Удалить запись
              </button>
            </div>
          </div>
        ))
      )}

      {/* Панель ИИ-агента (дополнительно к общим элементам) */}
      <div className="diary-agent" data-testid="diary-agent">
        <h3>🤖 Личный ИИ-тренер</h3>
        <p className="hint">Спроси совет, разбери неделю или собери следующую тренировку.</p>
        <div className="agent-actions">
          <button onClick={() => setChatOpen(true)} data-testid="diary-agent-chat">💬 Спросить тренера</button>
          <button onClick={handleWeekly} disabled={busyAgent === "weekly"} data-testid="diary-agent-weekly">
            {busyAgent === "weekly" ? <span className="diary-spinner" /> : "📊 Разбор недели"}
          </button>
          <button onClick={handleNext} disabled={busyAgent === "next"} data-testid="diary-agent-next">
            {busyAgent === "next" ? <span className="diary-spinner" /> : "✨ Собрать тренировку"}
          </button>
          <button onClick={() => setObOpen(true)} data-testid="diary-agent-profile">⚙️ Мой профиль</button>
        </div>
      </div>

      <DiaryComposer
        open={composerOpen}
        onClose={() => setComposerOpen(false)}
        date={selected}
        prefill={prefill}
        onSaved={(session) => {
          load();
          if (session) handleAnalyze(session);
        }}
      />
      <DiaryChat open={chatOpen} onClose={() => setChatOpen(false)} />
      {obOpen && (
        <OnboardingModal
          profile={profile}
          onClose={() => setObOpen(false)}
          onSaved={(p) => {
            setProfile(p);
            setObOpen(false);
          }}
        />
      )}
      {weeklyOpen && weekly && <WeeklyModal data={weekly} onClose={() => setWeeklyOpen(false)} />}
    </div>
  );
};

const OnboardingModal = ({ profile, onClose, onSaved }) => {
  const [goal, setGoal] = useState(profile?.goal || "hypertrophy");
  const [experience, setExperience] = useState(profile?.experience || "intermediate");
  const [equipment, setEquipment] = useState(profile?.equipment || "gym");
  const [days, setDays] = useState(profile?.weekly_target_days || 3);
  const [maxes, setMaxes] = useState(profile?.maxes || {});
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const clean = {};
      ["squat", "bench", "deadlift"].forEach((k) => {
        if (maxes[k]) clean[k] = parseFloat(maxes[k]);
      });
      const p = await putDiaryProfile({ goal, experience, equipment, weekly_target_days: days, maxes: clean });
      toast.success("Профиль сохранён");
      onSaved(p);
    } catch (e) {
      toast.error("Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="diary-modal-backdrop" onClick={onClose} data-testid="diary-onboarding">
      <div className="diary-modal" onClick={(e) => e.stopPropagation()}>
        <div className="diary-modal-head">
          <h3>Профиль для ИИ-тренера</h3>
          <button className="diary-modal-close" onClick={onClose}>×</button>
        </div>
        <div className="ob-label">Цель</div>
        <div className="chip-row">
          {GOALS.map(([v, l]) => (
            <button key={v} className={`chip ${goal === v ? "sel" : ""}`} onClick={() => setGoal(v)}>{l}</button>
          ))}
        </div>
        <div className="ob-label">Опыт</div>
        <div className="chip-row">
          {EXP.map(([v, l]) => (
            <button key={v} className={`chip ${experience === v ? "sel" : ""}`} onClick={() => setExperience(v)}>{l}</button>
          ))}
        </div>
        <div className="ob-label">Оборудование</div>
        <div className="chip-row">
          {EQUIP.map(([v, l]) => (
            <button key={v} className={`chip ${equipment === v ? "sel" : ""}`} onClick={() => setEquipment(v)}>{l}</button>
          ))}
        </div>
        <div className="ob-label">Тренировок в неделю</div>
        <div className="chip-row">
          {[2, 3, 4, 5, 6].map((n) => (
            <button key={n} className={`chip ${days === n ? "sel" : ""}`} onClick={() => setDays(n)}>{n}</button>
          ))}
        </div>
        <div className="ob-label">Максимумы (кг, необязательно) — для точной оценки сложности</div>
        <div className="qx-nums" style={{ marginBottom: 16 }}>
          {[["squat", "Присед"], ["bench", "Жим"], ["deadlift", "Тяга"]].map(([k, l]) => (
            <div className="qx-num" key={k}>
              <label>{l}</label>
              <input
                type="number"
                value={maxes[k] || ""}
                onChange={(e) => setMaxes({ ...maxes, [k]: e.target.value })}
                placeholder="—"
              />
            </div>
          ))}
        </div>
        <button className="diary-btn diary-btn-primary" onClick={save} disabled={saving} data-testid="diary-onboard-save">
          {saving ? <span className="diary-spinner" /> : "Сохранить"}
        </button>
      </div>
    </div>
  );
};

const WeeklyModal = ({ data, onClose }) => (
  <div className="diary-modal-backdrop" onClick={onClose} data-testid="diary-weekly">
    <div className="diary-modal" onClick={(e) => e.stopPropagation()}>
      <div className="diary-modal-head">
        <h3>📊 Разбор недели</h3>
        <button className="diary-modal-close" onClick={onClose}>×</button>
      </div>
      <div style={{ color: "rgba(255,255,255,0.55)", fontSize: 13, marginBottom: 10 }}>
        {data.volume?.workouts || 0} тренировок за 7 дней
      </div>
      {data.assessment && <div className="fb-summary" style={{ marginBottom: 12 }}>{data.assessment}</div>}
      {data.balance && data.balance.length > 0 && (
        <div className="fb-section">
          <h5>Баланс групп</h5>
          {data.balance.map((b, i) => (
            <div className="balance-row" key={i}>
              <span className={`balance-dot bd-${b.status || "ok"}`} />
              <b>{b.group}</b>
              <span style={{ color: "rgba(255,255,255,0.6)" }}>{b.note}</span>
            </div>
          ))}
        </div>
      )}
      {data.recommend_exercises && data.recommend_exercises.length > 0 && (
        <div className="fb-section">
          <h5>Добавь упражнения</h5>
          <ul className="rec-list">
            {data.recommend_exercises.map((r, i) => (
              <li key={i}>
                <span className="rec-name">{r.name}</span>
                {r.reason ? <div className="rec-reason">{r.reason}</div> : null}
              </li>
            ))}
          </ul>
        </div>
      )}
      {data.advice && <div className="fb-prog" style={{ marginTop: 12 }}>{data.advice}</div>}
    </div>
  </div>
);

export default DiaryHome;
