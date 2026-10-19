import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft, Plus, Trash2, CopyPlus, ChevronDown, ChevronUp,
  Search, Check, Loader2, CloudUpload, X, GripVertical, ArrowRight,
} from "lucide-react";
import { toast } from "sonner";
import { PulsingBorder } from "@paper-design/shaders-react";
import { useUser } from "@/context/UserContext";
import { getTemplate, updateTemplate, getExercises, createExercise } from "@/api";
import { haptic } from "@/lib/platform";
import { useBackButton } from "@/hooks/useTelegramUI";
import "./ProgramBuilder.css";

const LEVELS = [
  { key: "beginner", label: "Новичок" },
  { key: "intermediate", label: "Средний" },
  { key: "advanced", label: "Продвинутый" },
];
const GOALS = [
  { key: "strength", label: "Сила" },
  { key: "hypertrophy", label: "Масса" },
  { key: "powerlifting", label: "ПЛ" },
  { key: "general", label: "Общее" },
];
const MUSCLES = [
  { key: "legs", label: "Ноги" }, { key: "chest", label: "Грудь" },
  { key: "back", label: "Спина" }, { key: "shoulders", label: "Плечи" },
  { key: "biceps", label: "Бицепс" }, { key: "triceps", label: "Трицепс" },
  { key: "core", label: "Кор" },
];
const LIFTS = [
  { key: "", label: "Нет" }, { key: "squat", label: "Присед" },
  { key: "bench", label: "Жим" }, { key: "deadlift", label: "Тяга" },
];

const clone = (v) => JSON.parse(JSON.stringify(v));

const inferLift = (ex) => {
  const s = `${ex.slug || ""} ${ex.name || ""}`.toLowerCase();
  if (s.includes("squat") || s.includes("присед")) return "squat";
  if (s.includes("bench") || s.includes("жим лёжа") || s.includes("жим лежа")) return "bench";
  if (s.includes("deadlift") || s.includes("станов")) return "deadlift";
  return null;
};

const schemeSummary = (ex) => {
  if (ex.is_accessory) return "подсобное · отметка целиком";
  const sc = ex.sets_scheme || [];
  if (!sc.length) return "схема не задана";
  return sc
    .map((s) => `${s.sets}×${s.reps}${s.weight ? ` · ${s.weight}кг` : ""}`)
    .join(", ");
};

// ---------- Модалка выбора упражнения из каталога ----------
function ExercisePicker({ tg, onPick, onClose }) {
  const [list, setList] = useState([]);
  const [q, setQ] = useState("");
  const [customName, setCustomName] = useState("");
  const [customMuscle, setCustomMuscle] = useState("chest");
  const [creating, setCreating] = useState(false);
  const [customOpen, setCustomOpen] = useState(false);

  useEffect(() => {
    getExercises({ owner: tg }).then(setList).catch(() => setList([]));
  }, [tg]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return list;
    return list.filter((e) => (e.name || "").toLowerCase().includes(s));
  }, [list, q]);

  const createCustom = async () => {
    const name = customName.trim();
    if (name.length < 2 || creating) return;
    setCreating(true);
    try {
      const ex = await createExercise({
        name, muscle_groups: [customMuscle], owner_telegram_id: tg,
      });
      onPick(ex);
    } catch (e) {
      toast.error("Не удалось создать упражнение");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="pb-overlay" onClick={onClose} data-testid="exercise-picker">
      <div className="pb-modal" onClick={(e) => e.stopPropagation()}>
        <div className="pb-modal-head">
          <h3>Добавить упражнение</h3>
          <button className="pb-x" onClick={onClose} aria-label="Закрыть"><X size={18} /></button>
        </div>
        <div className="pb-search">
          <Search size={16} />
          <input value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Поиск по каталогу…" data-testid="picker-search" autoFocus />
        </div>
        <div className="pb-picker-list">
          {filtered.map((ex) => (
            <button key={ex.id} className="pb-picker-row" onClick={() => onPick(ex)}
              data-testid={`pick-${ex.slug || ex.id}`}>
              <span className="pb-picker-name">{ex.name}</span>
              <span className="pb-picker-mg">
                {MUSCLES.find((m) => m.key === (ex.muscle_groups || [])[0])?.label || ""}
              </span>
            </button>
          ))}
          {!filtered.length ? <p className="pb-empty">Ничего не найдено</p> : null}
        </div>
        <div className="pb-custom">
          <button className="pb-custom-toggle" onClick={() => setCustomOpen((v) => !v)}
            data-testid="picker-custom-toggle">
            <Plus size={15} /> Своё упражнение
          </button>
          {customOpen ? (
            <div className="pb-custom-form">
              <input value={customName} onChange={(e) => setCustomName(e.target.value)}
                placeholder="Название" data-testid="custom-ex-name" />
              <div className="pb-chips">
                {MUSCLES.map((m) => (
                  <button key={m.key}
                    className={`pb-chip ${customMuscle === m.key ? "active" : ""}`}
                    onClick={() => setCustomMuscle(m.key)}>
                    {m.label}
                  </button>
                ))}
              </div>
              <button className="pb-btn-primary" onClick={createCustom}
                disabled={creating || customName.trim().length < 2} data-testid="custom-ex-create">
                {creating ? "Создаём…" : "Создать и добавить"}
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

// ---------- Модалка редактирования упражнения ----------
function ExerciseEditor({ ex, onSave, onDelete, onClose }) {
  const [draft, setDraft] = useState(() => clone(ex));

  const setScheme = (i, field, val) => {
    setDraft((d) => {
      const next = clone(d);
      next.sets_scheme[i][field] = val;
      return next;
    });
  };
  const addRow = () => setDraft((d) => ({
    ...d, sets_scheme: [...(d.sets_scheme || []), { weight: null, sets: 3, reps: 10 }],
  }));
  const delRow = (i) => setDraft((d) => ({
    ...d, sets_scheme: d.sets_scheme.filter((_, idx) => idx !== i),
  }));

  const save = () => {
    const out = clone(draft);
    out.exercise_name = (out.exercise_name || "").trim() || "Упражнение";
    out.sets_scheme = (out.sets_scheme || [])
      .map((s) => ({
        weight: s.weight === "" || s.weight === null ? null : Number(s.weight),
        sets: Math.max(1, parseInt(s.sets, 10) || 1),
        reps: Math.max(0, parseInt(s.reps, 10) || 0),
      }));
    if (out.is_accessory) out.sets_scheme = [];
    out.target_sets = out.sets_scheme.reduce((a, s) => a + s.sets, 0) || 4;
    out.target_reps = out.sets_scheme.length ? String(out.sets_scheme[0].reps) : "10";
    out.rest_seconds = out.rest_seconds ? parseInt(out.rest_seconds, 10) : null;
    out.lift_group = out.lift_group || null;
    onSave(out);
  };

  return (
    <div className="pb-overlay" onClick={onClose} data-testid="exercise-editor">
      <div className="pb-modal" onClick={(e) => e.stopPropagation()}>
        <div className="pb-modal-head">
          <h3>Упражнение</h3>
          <button className="pb-x" onClick={onClose} aria-label="Закрыть"><X size={18} /></button>
        </div>
        <input className="pb-input" value={draft.exercise_name || ""}
          onChange={(e) => setDraft({ ...draft, exercise_name: e.target.value })}
          placeholder="Название" data-testid="editor-name" />

        <label className="pb-toggle">
          <input type="checkbox" checked={!!draft.is_accessory}
            onChange={(e) => setDraft({ ...draft, is_accessory: e.target.checked })}
            data-testid="editor-accessory" />
          <span>Подсобное (без учёта подходов)</span>
        </label>

        {!draft.is_accessory ? (
          <>
            <div className="pb-scheme-head">
              <span>Вес, кг</span><span>Подходы</span><span>Повторы</span><span />
            </div>
            {(draft.sets_scheme || []).map((s, i) => (
              <div className="pb-scheme-row" key={i}>
                <input type="number" inputMode="decimal" value={s.weight ?? ""}
                  onChange={(e) => setScheme(i, "weight", e.target.value)} placeholder="—" />
                <input type="number" inputMode="numeric" value={s.sets}
                  onChange={(e) => setScheme(i, "sets", e.target.value)} />
                <input type="number" inputMode="numeric" value={s.reps}
                  onChange={(e) => setScheme(i, "reps", e.target.value)} />
                <button className="pb-x" onClick={() => delRow(i)} aria-label="Удалить строку">
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
            <button className="pb-add-row" onClick={addRow} data-testid="editor-add-row">
              <Plus size={14} /> Добавить группу подходов
            </button>

            <div className="pb-field-row">
              <label className="pb-field">
                <span>Отдых, сек</span>
                <input type="number" inputMode="numeric" value={draft.rest_seconds ?? ""}
                  onChange={(e) => setDraft({ ...draft, rest_seconds: e.target.value })}
                  placeholder="120" />
              </label>
              <div className="pb-field">
                <span>Базовое движение</span>
                <div className="pb-chips">
                  {LIFTS.map((l) => (
                    <button key={l.key}
                      className={`pb-chip ${(draft.lift_group || "") === l.key ? "active" : ""}`}
                      onClick={() => setDraft({ ...draft, lift_group: l.key || null })}>
                      {l.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </>
        ) : null}

        <div className="pb-editor-actions">
          <button className="pb-btn-danger" onClick={onDelete} data-testid="editor-delete">
            <Trash2 size={15} /> Удалить
          </button>
          <button className="pb-btn-primary" onClick={save} data-testid="editor-save">
            <Check size={15} /> Готово
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------- Страница конструктора ----------
export default function ProgramBuilder() {
  const { templateId } = useParams();
  const { user } = useUser();
  const navigate = useNavigate();
  useBackButton(true, () => navigate("/programs"));

  const [tpl, setTpl] = useState(null);
  const [saveState, setSaveState] = useState("saved"); // saved | saving | error
  const [openWeek, setOpenWeek] = useState(0);
  const [picker, setPicker] = useState(null); // {wi, di}
  const [editor, setEditor] = useState(null); // {wi, di, ei}
  const timerRef = useRef(null);
  const tplRef = useRef(null);

  useEffect(() => {
    getTemplate(templateId)
      .then((t) => { setTpl(t); tplRef.current = t; })
      .catch(() => {
        toast.error("Программа не найдена");
        navigate("/programs");
      });
  }, [templateId, navigate]);

  const persist = async () => {
    const t = tplRef.current;
    if (!t) return;
    setSaveState("saving");
    try {
      await updateTemplate(templateId, {
        name: t.name, description: t.description,
        level: t.level, goal: t.goal, weeks: t.weeks,
      });
      setSaveState("saved");
    } catch (e) {
      setSaveState("error");
    }
  };

  const mutate = (fn) => {
    setTpl((prev) => {
      const next = clone(prev);
      fn(next);
      tplRef.current = next;
      return next;
    });
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(persist, 900);
    setSaveState("saving");
  };

  useEffect(() => () => clearTimeout(timerRef.current), []);

  if (!tpl) {
    return (
      <div className="pb-page" data-testid="builder-loading">
        <div className="pb-load"><Loader2 size={26} className="pb-spin" /></div>
      </div>
    );
  }

  const weeks = tpl.weeks || [];
  const totalEx = weeks.reduce(
    (a, w) => a + (w.days || []).reduce((b, d) => b + (d.exercises || []).length, 0), 0);

  // --- операции с неделями ---
  const addWeek = (copyLast) => {
    haptic("light");
    mutate((t) => {
      const src = copyLast && t.weeks.length ? clone(t.weeks[t.weeks.length - 1]) : null;
      t.weeks.push({
        week_index: t.weeks.length + 1,
        published: true,
        days: src ? src.days : [],
      });
    });
    setOpenWeek(weeks.length);
  };
  const duplicateWeek = (wi) => mutate((t) => {
    const cp = clone(t.weeks[wi]);
    t.weeks.splice(wi + 1, 0, cp);
    t.weeks.forEach((w, i) => { w.week_index = i + 1; });
  });
  const deleteWeek = (wi) => mutate((t) => {
    t.weeks.splice(wi, 1);
    t.weeks.forEach((w, i) => { w.week_index = i + 1; });
  });

  // --- операции с днями ---
  const addDay = (wi) => mutate((t) => {
    const days = t.weeks[wi].days || (t.weeks[wi].days = []);
    const used = new Set(days.map((d) => d.day_index));
    let idx = 1;
    while (used.has(idx) && idx < 7) idx += 1;
    days.push({ day_index: idx, title: `День ${days.length + 1}`, is_rest: false, exercises: [] });
    days.sort((a, b) => a.day_index - b.day_index);
  });
  const duplicateDay = (wi, di) => mutate((t) => {
    const days = t.weeks[wi].days;
    const cp = clone(days[di]);
    const used = new Set(days.map((d) => d.day_index));
    let idx = 1;
    while (used.has(idx) && idx < 7) idx += 1;
    cp.day_index = idx;
    cp.title = `${cp.title} (копия)`;
    days.push(cp);
    days.sort((a, b) => a.day_index - b.day_index);
  });
  const deleteDay = (wi, di) => mutate((t) => {
    t.weeks[wi].days.splice(di, 1);
  });

  // --- операции с упражнениями ---
  const addExercise = (wi, di, ex) => {
    mutate((t) => {
      const exs = t.weeks[wi].days[di].exercises;
      exs.push({
        exercise_id: ex.id || null,
        exercise_slug: ex.slug || null,
        exercise_name: ex.name,
        muscle_group: (ex.muscle_groups || [])[0] || null,
        order: exs.length,
        target_sets: 3,
        target_reps: "10",
        weight_type: "kg",
        rest_seconds: null,
        sets_scheme: [{ weight: null, sets: 3, reps: 10 }],
        lift_group: inferLift(ex),
        is_accessory: false,
      });
    });
    setPicker(null);
  };
  const moveExercise = (wi, di, ei, dir) => mutate((t) => {
    const exs = t.weeks[wi].days[di].exercises;
    const j = ei + dir;
    if (j < 0 || j >= exs.length) return;
    [exs[ei], exs[j]] = [exs[j], exs[ei]];
    exs.forEach((e, i) => { e.order = i; });
  });
  const saveExercise = (wi, di, ei, data) => {
    mutate((t) => { t.weeks[wi].days[di].exercises[ei] = data; });
    setEditor(null);
  };
  const deleteExercise = (wi, di, ei) => {
    mutate((t) => {
      t.weeks[wi].days[di].exercises.splice(ei, 1);
      t.weeks[wi].days[di].exercises.forEach((e, i) => { e.order = i; });
    });
    setEditor(null);
  };

  return (
    <div className="pb-page" data-testid="builder-page">
      <header className="pb-header">
        <button className="pb-back" onClick={() => navigate("/programs")}
          aria-label="Назад" data-testid="builder-back">
          <ArrowLeft size={22} />
        </button>
        <h1 className="pb-title">Конструктор</h1>
        <span className={`pb-save pb-save-${saveState}`} data-testid="builder-save-state">
          {saveState === "saving" ? (<><CloudUpload size={13} /> Сохранение…</>)
            : saveState === "error" ? "Ошибка сохранения"
            : (<><Check size={13} /> Сохранено</>)}
        </span>
      </header>

      {/* AI Promo — плашка с pulsing-border shader */}
      <button
        type="button"
        className="pb-ai-promo"
        onClick={() => navigate("/programs/ai")}
        data-testid="builder-ai-promo"
      >
        <span className="pb-ai-promo-shader" aria-hidden="true">
          <PulsingBorder
            width="100%"
            height="100%"
            colors={["#ff8a24", "#ffda24", "#ff5e00", "#ffce8a"]}
            colorBack="transparent"
            roundness={0.22}
            thickness={0.06}
            softness={0.9}
            intensity={1.0}
            spotsPerColor={3}
            spotSize={0.32}
            pulse={0.35}
            smoke={0.4}
            smokeSize={0.5}
            scale={1.0}
            speed={1.2}
          />
        </span>
        <span className="pb-ai-promo-content">
          <span className="pb-ai-promo-icon">
            <img src="/img/3d/star-dot.png" alt="" className="pb-ai-promo-img" />
          </span>
          <span className="pb-ai-promo-text">
            <b>Создайте программу через ИИ бесплатно</b>
            <span>По вашим предпочтениям и научным исследованиям</span>
          </span>
          <ArrowRight size={18} className="pb-ai-promo-arrow" />
        </span>
      </button>

      <input className="pb-name" value={tpl.name || ""}
        onChange={(e) => mutate((t) => { t.name = e.target.value; })}
        placeholder="Название программы" data-testid="builder-name" />
      <textarea className="pb-desc" value={tpl.description || ""}
        onChange={(e) => mutate((t) => { t.description = e.target.value; })}
        placeholder="Описание (необязательно)" rows={2} data-testid="builder-desc" />

      <div className="pb-meta-row">
        <div className="pb-chips">
          {LEVELS.map((l) => (
            <button key={l.key} className={`pb-chip ${tpl.level === l.key ? "active" : ""}`}
              onClick={() => mutate((t) => { t.level = l.key; })}>{l.label}</button>
          ))}
        </div>
        <div className="pb-chips">
          {GOALS.map((g) => (
            <button key={g.key} className={`pb-chip ${tpl.goal === g.key ? "active" : ""}`}
              onClick={() => mutate((t) => { t.goal = g.key; })}>{g.label}</button>
          ))}
        </div>
      </div>

      <p className="pb-counts" data-testid="builder-counts">
        {weeks.length} нед. · {totalEx} упражнений
      </p>

      {weeks.map((w, wi) => (
        <section className="pb-week" key={wi} data-testid={`builder-week-${wi + 1}`}>
          <button className="pb-week-head" onClick={() => setOpenWeek(openWeek === wi ? -1 : wi)}>
            <span className="pb-week-title">Неделя {w.week_index}</span>
            <span className="pb-week-sub">
              {(w.days || []).length} {["день", "дня", "дней"][
                (w.days || []).length === 1 ? 0 : (w.days || []).length < 5 && (w.days || []).length > 1 ? 1 : 2]}
            </span>
            {openWeek === wi ? <ChevronUp size={17} /> : <ChevronDown size={17} />}
          </button>
          {openWeek === wi ? (
            <div className="pb-week-body">
              {(w.days || []).map((d, di) => (
                <div className="pb-day" key={di}>
                  <div className="pb-day-head">
                    <input className="pb-day-title" value={d.title || ""}
                      onChange={(e) => mutate((t) => { t.weeks[wi].days[di].title = e.target.value; })}
                      placeholder="Название дня" />
                    <button className="pb-ico" onClick={() => duplicateDay(wi, di)}
                      aria-label="Дублировать день"><CopyPlus size={15} /></button>
                    <button className="pb-ico pb-ico-danger" onClick={() => deleteDay(wi, di)}
                      aria-label="Удалить день"><Trash2 size={15} /></button>
                  </div>
                  {(d.exercises || []).map((ex, ei) => (
                    <div className="pb-ex" key={ei}>
                      <GripVertical size={14} className="pb-ex-grip" />
                      <button className="pb-ex-main" onClick={() => setEditor({ wi, di, ei })}
                        data-testid={`builder-ex-${wi}-${di}-${ei}`}>
                        <span className="pb-ex-name">{ex.exercise_name}</span>
                        <span className="pb-ex-scheme">{schemeSummary(ex)}</span>
                      </button>
                      <div className="pb-ex-moves">
                        <button className="pb-ico" onClick={() => moveExercise(wi, di, ei, -1)}
                          disabled={ei === 0} aria-label="Вверх"><ChevronUp size={14} /></button>
                        <button className="pb-ico" onClick={() => moveExercise(wi, di, ei, 1)}
                          disabled={ei === (d.exercises || []).length - 1} aria-label="Вниз">
                          <ChevronDown size={14} /></button>
                      </div>
                    </div>
                  ))}
                  <button className="pb-add" onClick={() => setPicker({ wi, di })}
                    data-testid={`builder-add-ex-${wi}-${di}`}>
                    <Plus size={14} /> Упражнение
                  </button>
                </div>
              ))}
              <button className="pb-add pb-add-day" onClick={() => addDay(wi)}
                data-testid={`builder-add-day-${wi}`}>
                <Plus size={15} /> Добавить день
              </button>
              <div className="pb-week-actions">
                <button className="pb-week-act" onClick={() => duplicateWeek(wi)}
                  data-testid={`builder-dup-week-${wi}`}>
                  <CopyPlus size={14} /> Дублировать неделю
                </button>
                <button className="pb-week-act pb-week-act-danger" onClick={() => deleteWeek(wi)}
                  disabled={weeks.length <= 1} data-testid={`builder-del-week-${wi}`}>
                  <Trash2 size={14} /> Удалить
                </button>
              </div>
            </div>
          ) : null}
        </section>
      ))}

      <div className="pb-add-week-row">
        <button className="pb-add pb-add-week" onClick={() => addWeek(false)} data-testid="builder-add-week">
          <Plus size={15} /> Пустая неделя
        </button>
        <button className="pb-add pb-add-week" onClick={() => addWeek(true)}
          disabled={!weeks.length} data-testid="builder-copy-week">
          <CopyPlus size={15} /> Копия последней
        </button>
      </div>

      <button className="pb-done" onClick={() => { clearTimeout(timerRef.current); persist(); navigate("/programs"); }}
        data-testid="builder-done">
        Готово — к моим программам
      </button>

      {picker ? (
        <ExercisePicker tg={user?.telegram_id}
          onPick={(ex) => addExercise(picker.wi, picker.di, ex)}
          onClose={() => setPicker(null)} />
      ) : null}
      {editor ? (
        <ExerciseEditor
          ex={tpl.weeks[editor.wi].days[editor.di].exercises[editor.ei]}
          onSave={(data) => saveExercise(editor.wi, editor.di, editor.ei, data)}
          onDelete={() => deleteExercise(editor.wi, editor.di, editor.ei)}
          onClose={() => setEditor(null)} />
      ) : null}
    </div>
  );
}
