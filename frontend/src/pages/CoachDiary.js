import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft, Plus, X, ChevronLeft, ChevronRight, Search,
  CheckCircle2, Zap, Dumbbell, PenLine, GripVertical, Trash2, Users,
} from "lucide-react";
import { useUser } from "@/context/UserContext";
import {
  getUserById, getExercises,
  coachCreateDiarySession, coachListDiarySessions,
  getCoachClients,
} from "@/api";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useBackButton } from "@/hooks/useTelegramUI";
import ExercisePickerModal from "@/components/ExercisePickerModal";
import "./Coach.css";
import "./CoachDiary.css";

// ---------- helpers ----------

const emptySet = () => ({ weight: "", sets: "1", reps: "10" });

const emptyExercise = () => ({
  name: "",
  slug: null,
  muscle_group: null,
  sets: [emptySet()],
  notes: "",
});

const fmtDate = (d) => {
  const dd = new Date(d);
  return dd.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
};

const toISO = (d) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
};

const avatarFor = (a) => {
  if (a?.picture) return a.picture;
  const name = encodeURIComponent(a?.first_name || "U");
  return `https://ui-avatars.com/api/?name=${name}&background=FF6B00&color=fff&size=80&bold=true`;
};

// ---------- Coach Diary Page ----------

export default function CoachDiary() {
  const { athleteId } = useParams();
  const preselectedAid = athleteId ? Number(athleteId) : null;
  const { user } = useUser();
  const coachId = user?.telegram_id;
  const navigate = useNavigate();
  useBackButton(true, () => navigate(preselectedAid ? `/coach/${preselectedAid}` : "/coach"));
  // Страховка: тренерские экраны доступны только в режиме тренера.
  const { loading: capsLoading, coachMode } = useCapabilities();
  useEffect(() => {
    if (!capsLoading && !coachMode) navigate("/", { replace: true });
  }, [capsLoading, coachMode, navigate]);


  // ---- Step 1: Client selector ----
  const [clients, setClients] = useState([]);
  const [clientsLoading, setClientsLoading] = useState(true);

  // ---- Step 2: Selected client + diary editor ----
  const [selectedClient, setSelectedClient] = useState(null);
  const [athlete, setAthlete] = useState(null);
  const [loadingAthlete, setLoadingAthlete] = useState(false);
  const [exercises, setExercises] = useState([emptyExercise()]);
  const [sessionNotes, setSessionNotes] = useState("");
  const [sessionTitle, setSessionTitle] = useState("");
  const [currentDate, setCurrentDate] = useState(toISO(new Date()));
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerTarget, setPickerTarget] = useState(null);
  const [busy, setBusy] = useState(false);
  const [savedSessionId, setSavedSessionId] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [catalog, setCatalog] = useState([]);
  const [historySessions, setHistorySessions] = useState([]);

  // ---- Load clients list ----
  useEffect(() => {
    if (!coachId) return;
    setClientsLoading(true);
    getCoachClients(coachId)
      .then((data) => {
        const list = data.clients || [];
        setClients(list);
        // Auto-select if athleteId was passed in URL
        if (preselectedAid) {
          const match = list.find((c) => (c.athlete?.telegram_id) === preselectedAid);
          if (match) selectClient(match);
        }
      })
      .catch(() => toast.error("Не удалось загрузить подопечных"))
      .finally(() => setClientsLoading(false));
  }, [coachId, preselectedAid]);

  // ---- When client is selected, load athlete data + diary history ----
  const selectClient = useCallback(async (client) => {
    const a = client.athlete || {};
    setSelectedClient(a);
    setExercises([emptyExercise()]);
    setSessionNotes("");
    setSessionTitle("");
    setSavedSessionId(null);
    setDirty(false);

    setLoadingAthlete(true);
    // Load athlete profile
    getUserById(a.telegram_id)
      .then((ath) => setAthlete(ath))
      .catch(() => setAthlete(a))
      .finally(() => setLoadingAthlete(false));

    // Load exercise catalog
    getExercises()
      .then((list) => setCatalog(list || []))
      .catch(() => {});

    // Load history for progression
    if (coachId && a.telegram_id) {
      coachListDiarySessions(coachId, a.telegram_id, { limit: 20 })
        .then((data) => {
          if (data?.sessions) setHistorySessions(data.sessions);
        })
        .catch(() => {});
    }
  }, [coachId]);

  // ---- Catalog lookup ----
  const catalogByName = useMemo(() => {
    const m = {};
    (catalog || []).forEach((ex) => {
      if (ex.name) m[(ex.name || "").trim().toLowerCase()] = ex;
    });
    return m;
  }, [catalog]);

  // ---- Build history map: exercise slug -> last weight used ----
  const historyBySlug = useMemo(() => {
    const map = {};
    (historySessions || []).forEach((sess) => {
      (sess.exercises || []).forEach((ex) => {
        const slug = ex.exercise_slug || ex.name;
        if (!slug) return;
        const schemes = ex.sets_scheme || [];
        const weights = schemes
          .map((s) => s.weight)
          .filter((w) => w !== null && w !== undefined && w > 0);
        if (weights.length > 0) {
          const maxW = Math.max(...weights);
          if (!map[slug] || map[slug].weight < maxW) {
            map[slug] = { weight: maxW, date: sess.date };
          }
        }
      });
    });
    return map;
  }, [historySessions]);

  // Find the exercise in catalog by name
  const findInCatalog = (name) => {
    const key = (name || "").trim().toLowerCase();
    return catalogByName[key];
  };

  // ---- Reset and go back to client list ----
  const backToClients = () => {
    setSelectedClient(null);
    setAthlete(null);
    setExercises([emptyExercise()]);
    setSessionNotes("");
    setSessionTitle("");
    setSavedSessionId(null);
    setDirty(false);
  };

  // ---- Exercise operations ----
  const addExercise = () => {
    setExercises((prev) => [...prev, emptyExercise()]);
    setDirty(true);
  };

  const removeExercise = (idx) => {
    setExercises((prev) => (prev.length > 1 ? prev.filter((_, i) => i !== idx) : prev));
    setDirty(true);
  };

  const updateExerciseField = (idx, patch) => {
    setExercises((prev) =>
      prev.map((ex, i) => (i === idx ? { ...ex, ...patch } : ex))
    );
    setDirty(true);
  };

  // When an exercise is picked from the modal
  const handleExercisePicked = (pick) => {
    if (pickerTarget !== null) {
      const cat = findInCatalog(pick.name);
      updateExerciseField(pickerTarget, {
        name: pick.name,
        slug: pick.slug || (cat ? cat.slug : null),
        muscle_group: pick.muscle_group || (cat ? (cat.muscle_groups || [])[0] : null),
      });
      setPickerTarget(null);
      setPickerOpen(false);
    }
  };

  // Open picker for a specific exercise slot
  const openPickerFor = (idx) => {
    setPickerTarget(idx);
    setPickerOpen(true);
  };

  // ---- Set operations ----
  const addSet = (exIdx) => {
    setExercises((prev) =>
      prev.map((ex, i) => {
        if (i !== exIdx) return ex;
        const last = ex.sets[ex.sets.length - 1] || emptySet();
        return {
          ...ex,
          sets: [...ex.sets, { weight: last.weight, sets: "1", reps: last.reps }],
        };
      })
    );
    setDirty(true);
  };

  const removeSet = (exIdx, setIdx) => {
    setExercises((prev) =>
      prev.map((ex, i) =>
        i === exIdx && ex.sets.length > 1
          ? { ...ex, sets: ex.sets.filter((_, si) => si !== setIdx) }
          : ex
      )
    );
    setDirty(true);
  };

  const updateSet = (exIdx, setIdx, patch) => {
    setExercises((prev) =>
      prev.map((ex, i) =>
        i === exIdx
          ? { ...ex, sets: ex.sets.map((s, si) => (si === setIdx ? { ...s, ...patch } : s)) }
          : ex
      )
    );
    setDirty(true);
  };

  // ---- Apply weight suggestion from history ----
  const applySuggestion = (exIdx, weight) => {
    setExercises((prev) =>
      prev.map((ex, i) => {
        if (i !== exIdx) return ex;
        return {
          ...ex,
          sets: ex.sets.map((s) => ({ ...s, weight: String(weight) })),
        };
      })
    );
    setDirty(true);
  };

  // ---- Build payload ----
  const buildPayload = () => {
    const exs = exercises
      .filter((ex) => (ex.name || "").trim())
      .map((ex) => {
        const setsScheme = ex.sets
          .map((s) => ({
            weight: s.weight === "" ? null : parseFloat(s.weight),
            sets: parseInt(s.sets, 10) || 1,
            reps: parseInt(s.reps, 10) || 0,
          }))
          .filter((s) => s.reps > 0 || s.weight != null);
        return {
          name: ex.name.trim(),
          exercise_slug: ex.slug || null,
          muscle_group: ex.muscle_group || null,
          is_accessory: false,
          sets_scheme: setsScheme,
          notes: ex.notes?.trim() || null,
        };
      });
    return {
      date: currentDate,
      title: (sessionTitle || "").trim() || null,
      notes: (sessionNotes || "").trim() || null,
      source_input: "coach_diary",
      exercises: exs,
    };
  };

  // ---- Summary ----
  const summary = useMemo(() => {
    let exCount = 0;
    let setCount = 0;
    let tonnage = 0;
    exercises.forEach((ex) => {
      if (!(ex.name || "").trim()) return;
      exCount += 1;
      ex.sets.forEach((s) => {
        const sets = parseInt(s.sets, 10);
        const reps = parseInt(s.reps, 10);
        const w = parseFloat(s.weight);
        if (!Number.isFinite(sets) || sets <= 0) return;
        setCount += sets;
        if (Number.isFinite(w) && w > 0 && Number.isFinite(reps) && reps > 0) {
          tonnage += w * sets * reps;
        }
      });
    });
    return { exercises: exCount, sets: setCount, tonnage };
  }, [exercises]);

  // ---- Save ----
  const handleSave = async () => {
    const payload = buildPayload();
    const athleteId = selectedClient?.telegram_id;
    if (!athleteId) {
      toast.error("Выберите спортсмена");
      return;
    }
    if (payload.exercises.length === 0) {
      toast.error("Добавьте хотя бы одно упражнение");
      return;
    }
    setBusy(true);
    try {
      const session = await coachCreateDiarySession(coachId, athleteId, payload);
      setSavedSessionId(session?.id || "saved");
      setDirty(false);
      toast.success("Тренировка сохранена в дневник");
      window.dispatchEvent(new Event("twb:progress"));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Не удалось сохранить");
    } finally {
      setBusy(false);
    }
  };

  // ---- Navigation ----
  const prevDay = () => {
    const d = new Date(currentDate);
    d.setDate(d.getDate() - 1);
    setCurrentDate(toISO(d));
    setDirty(true);
  };
  const nextDay = () => {
    const d = new Date(currentDate);
    d.setDate(d.getDate() + 1);
    setCurrentDate(toISO(d));
    setDirty(true);
  };
  const today = () => {
    setCurrentDate(toISO(new Date()));
    setDirty(true);
  };

  // =========================================================================
  // RENDER
  // =========================================================================

  const athleteName = selectedClient?.first_name || athlete?.first_name || "Спортсмен";

  return (
    <div className="coach-page coach-diary-page" data-testid="coach-diary-page">
      <header className="cd-header">
        <button
          className="cd-back"
          onClick={selectedClient ? backToClients : () => navigate("/coach")}
          aria-label="Назад"
          data-testid="cd-back"
        >
          <ArrowLeft size={22} />
        </button>
        <h1 className="cd-title">
          {selectedClient ? `Дневник · ${athleteName}` : "Дневник тренера"}
        </h1>
        {selectedClient && (
          <button
            className="cd-back"
            onClick={today}
            aria-label="Сегодня"
            style={{ fontSize: 11, fontWeight: 600, width: "auto", padding: "8px 12px" }}
            data-testid="cd-today-btn"
          >
            Сегодня
          </button>
        )}
      </header>

      {/* ====== Step 1: Client selector (avatar list) ====== */}
      {!selectedClient && (
        <div className="cd-client-select" data-testid="cd-client-select">
          <div className="cd-client-select-label">Выберите подопечного</div>
          {clientsLoading ? (
            <div className="coach-empty">Загрузка…</div>
          ) : clients.length === 0 ? (
            <div className="cd-empty">
              <div className="cd-empty-ico"><Users size={26} /></div>
              <p className="cd-empty-title">Нет подопечных</p>
              <p className="cd-empty-sub">
                Сначала пригласите спортсменов через кабинет тренера.
              </p>
            </div>
          ) : (
            <div className="cd-avatar-scroll" data-testid="cd-avatar-scroll">
              {clients.map((c) => {
                const a = c.athlete || {};
                const name = a.first_name || "Спортсмен";
                const isActive = selectedClient?.telegram_id === a.telegram_id;
                return (
                  <button
                    key={a.telegram_id}
                    className={`cd-avatar-card ${isActive ? "active" : ""}`}
                    onClick={() => selectClient(c)}
                    data-testid={`cd-client-${a.telegram_id}`}
                  >
                    <div className="cd-avatar-ring">
                      <img className="cd-avatar-img" src={avatarFor(a)} alt={name} />
                    </div>
                    <span className="cd-avatar-name">{name}</span>
                    {c.plan && (
                      <span className="cd-avatar-plan">
                        {c.plan.name}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ====== Step 2: Diary editor (after client selected) ====== */}
      {selectedClient && (
        <>
          {/* Athlete banner */}
          <div className="cd-athlete" data-testid="cd-athlete">
            <img className="cd-ava" src={avatarFor(selectedClient)} alt="" />
            <div style={{ minWidth: 0 }}>
              <div className="cd-athlete-name">{athleteName}</div>
              <div className="cd-athlete-sub">Тренировочный дневник</div>
            </div>
            <span className={`cd-save-status ${savedSessionId ? "saved" : "unsaved"}`} data-testid="cd-save-status">
              {savedSessionId ? "Сохранено" : "Новая запись"}
            </span>
          </div>

          {/* Controls: date */}
          <div className="cd-controls">
            <div className="cd-date-nav">
              <button onClick={prevDay} aria-label="Предыдущий день">
                <ChevronLeft size={16} />
              </button>
              <span className="cd-date-label">{fmtDate(currentDate)}</span>
              <button onClick={nextDay} aria-label="Следующий день">
                <ChevronRight size={16} />
              </button>
            </div>
          </div>

          {/* Title input */}
          <div style={{ marginBottom: 12 }}>
            <input
              className="cd-title-input"
              style={{
                width: "100%",
                background: "#2a2a2a",
                border: "1px solid #3a3a3a",
                borderRadius: 12,
                padding: "12px 14px",
                color: "#fff",
                fontSize: 15,
                fontWeight: 600,
                fontFamily: "inherit",
              }}
              placeholder="Название тренировки (необязательно)"
              value={sessionTitle}
              onChange={(e) => { setSessionTitle(e.target.value); setDirty(true); }}
              data-testid="cd-session-title"
            />
          </div>

          {/* Exercise list */}
          <div className="cd-ex-list" data-testid="cd-ex-list">
            {exercises.map((ex, exIdx) => {
              const hasExercise = !!(ex.name || "").trim();
              const slug = ex.slug;
              const history = slug ? historyBySlug[slug] || historyBySlug[ex.name] : historyBySlug[ex.name];
              const hasHistory = history && history.weight > 0;

              return (
                <div
                  className={`cd-ex-card ${hasExercise ? "cd-ex-card-filled" : ""}`}
                  key={exIdx}
                  data-testid={`cd-ex-card-${exIdx}`}
                >
                  {/* Card header */}
                  <div className="cd-ex-head">
                    <span className={`cd-ex-order ${hasExercise ? "filled" : ""}`}>
                      {String(exIdx + 1).padStart(2, "0")}
                    </span>

                    {hasExercise ? (
                      <>
                        <div
                          className="cd-ex-name"
                          onClick={() => openPickerFor(exIdx)}
                          data-testid={`cd-ex-name-${exIdx}`}
                        >
                          {ex.name}
                          {ex.muscle_group ? (
                            <span className="cd-ex-muscle">{ex.muscle_group}</span>
                          ) : null}
                          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", marginLeft: 4 }}>
                            ✎
                          </span>
                        </div>
                        {exercises.length > 1 && (
                          <button
                            className="cd-ex-remove"
                            onClick={() => removeExercise(exIdx)}
                            aria-label="Удалить упражнение"
                            data-testid={`cd-ex-remove-${exIdx}`}
                          >
                            <Trash2 size={17} />
                          </button>
                        )}
                      </>
                    ) : (
                      <button
                        className="cd-ex-picker-btn"
                        onClick={() => openPickerFor(exIdx)}
                        data-testid={`cd-ex-pick-${exIdx}`}
                      >
                        <Plus size={20} strokeWidth={2.5} />
                        Выбрать упражнение
                      </button>
                    )}
                  </div>

                  {/* History suggestion */}
                  {hasHistory && hasExercise && (
                    <div className="cd-progression-hint">
                      Последний раз:{' '}
                      <span
                        className="cd-suggestion"
                        onClick={() => applySuggestion(exIdx, history.weight)}
                        data-testid={`cd-suggest-${exIdx}`}
                        title={`С ${history.date || "прошлой тренировки"}`}
                      >
                        {history.weight} кг
                      </span>
                    </div>
                  )}

                  {/* Sets grid */}
                  {hasExercise && (
                    <div className="cd-sets" data-testid={`cd-sets-${exIdx}`}>
                      <div className="cd-set-head" aria-hidden="true">
                        <span>Вес, кг</span>
                        <span>Подходы</span>
                        <span>Повторы</span>
                        <span />
                      </div>
                      {ex.sets.map((s, setIdx) => (
                        <div className="cd-set-row" key={setIdx}>
                          <div className="cd-set-cell">
                            <input
                              type="number"
                              inputMode="decimal"
                              value={s.weight}
                              onChange={(e) => updateSet(exIdx, setIdx, { weight: e.target.value })}
                              placeholder="—"
                              data-testid={`cd-weight-${exIdx}-${setIdx}`}
                            />
                          </div>
                          <div className="cd-set-cell">
                            <input
                              type="number"
                              inputMode="numeric"
                              value={s.sets}
                              onChange={(e) => updateSet(exIdx, setIdx, { sets: e.target.value })}
                              data-testid={`cd-sets-${exIdx}-${setIdx}`}
                            />
                          </div>
                          <div className="cd-set-cell">
                            <input
                              type="number"
                              inputMode="numeric"
                              value={s.reps}
                              onChange={(e) => updateSet(exIdx, setIdx, { reps: e.target.value })}
                              data-testid={`cd-reps-${exIdx}-${setIdx}`}
                            />
                          </div>
                          <div className="cd-set-del">
                            {ex.sets.length > 1 && (
                              <button
                                onClick={() => removeSet(exIdx, setIdx)}
                                aria-label="Убрать подход"
                                data-testid={`cd-del-set-${exIdx}-${setIdx}`}
                              >
                                <X size={15} />
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                      <button
                        className="cd-add-set"
                        onClick={() => addSet(exIdx)}
                        data-testid={`cd-add-set-${exIdx}`}
                      >
                        <Plus size={13} /> подход с другим весом
                      </button>
                    </div>
                  )}

                  {/* Per-exercise notes */}
                  {hasExercise && (
                    <div className="cd-ex-notes">
                      <textarea
                        rows={1}
                        placeholder="Заметка к упражнению (необязательно)"
                        value={ex.notes}
                        onChange={(e) => updateExerciseField(exIdx, { notes: e.target.value })}
                        data-testid={`cd-ex-notes-${exIdx}`}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Add exercise button */}
          <button
            className="cd-add-ex"
            onClick={addExercise}
            data-testid="cd-add-ex"
          >
            <Plus size={18} /> Добавить упражнение
          </button>

          {/* Session notes */}
          <div className="cd-session-notes">
            <textarea
              placeholder="Заметка про тренировку: самочувствие, техника, кардио…"
              value={sessionNotes}
              onChange={(e) => { setSessionNotes(e.target.value); setDirty(true); }}
              data-testid="cd-session-notes"
            />
          </div>

          {/* Footer with summary + save */}
          <div className="cd-footer" data-testid="cd-footer">
            <div className="cd-summary">
              <div className="cd-sum-stat">
                <b>{summary.exercises}</b>
                <span>упражн.</span>
              </div>
              <div className="cd-sum-stat">
                <b>{summary.sets}</b>
                <span>подходов</span>
              </div>
              <div className="cd-sum-stat cd-sum-tonnage">
                <b>{summary.tonnage > 0 ? summary.tonnage.toLocaleString("ru-RU") : "—"}</b>
                <span>кг объём</span>
              </div>
            </div>
            <button
              className="cd-save-btn"
              onClick={handleSave}
              disabled={busy || summary.exercises === 0}
              data-testid="cd-save-btn"
            >
              {busy ? "Сохраняю…" : dirty ? "Сохранить тренировку" : "Сохранено ✓"}
            </button>
          </div>

          {/* Exercise picker modal */}
          {pickerOpen && (
            <ExercisePickerModal
              onSelect={handleExercisePicked}
              onClose={() => { setPickerOpen(false); setPickerTarget(null); }}
            />
          )}
        </>
      )}
    </div>
  );
}