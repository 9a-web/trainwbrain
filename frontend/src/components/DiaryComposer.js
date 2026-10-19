import React, { useState, useEffect, useMemo, useRef } from "react";
import { toast } from "sonner";
import { Plus, X, Zap, PenLine, Search, GripVertical, Trash2 } from "lucide-react";
import {
  createDiarySession,
  diaryParse,
  pollDiaryJob,
  getExercises,
} from "@/api";
import "@/components/Diary.css";

const emptyGroup = () => ({ weight: "", sets: "3", reps: "10" });
const emptyRow = () => ({ name: "", slug: null, muscle_group: null, is_accessory: false, groups: [emptyGroup()] });

// sets_scheme (массив групп) -> строки редактора
const schemeToGroups = (scheme) => {
  const g = (scheme || []).map((s) => ({
    weight: s.weight != null ? String(s.weight) : "",
    sets: String(s.sets || 3),
    reps: String(s.reps || 10),
  }));
  return g.length ? g : [emptyGroup()];
};

const exToRow = (e) => ({
  name: e.name || "",
  slug: e.exercise_slug || null,
  muscle_group: e.muscle_group || null,
  is_accessory: !!e.is_accessory,
  groups: schemeToGroups(e.sets_scheme),
});

const RPE_LABEL = {
  1: "очень легко",
  2: "очень легко",
  3: "легко",
  4: "легко",
  5: "средне",
  6: "средне",
  7: "тяжело",
  8: "тяжело",
  9: "очень тяжело",
  10: "максимум",
};

// Композер: запись выполненной тренировки. Способы — Быстро и Текст (ИИ).
const DiaryComposer = ({ open, onClose, date, onSaved, prefill }) => {
  const [tab, setTab] = useState("quick");
  const [rows, setRows] = useState([emptyRow()]);
  const [rpe, setRpe] = useState(null);
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [busyMsg, setBusyMsg] = useState("");
  const [catalog, setCatalog] = useState([]);

  // Быстрый поиск по каталогу для авто-подстановки slug + группы мышц.
  const listRef = useRef(null);

  const catalogByName = useMemo(() => {
    const m = {};
    (catalog || []).forEach((ex) => {
      if (ex.name) m[(ex.name || "").trim().toLowerCase()] = ex;
    });
    return m;
  }, [catalog]);

  useEffect(() => {
    if (!open) return;
    getExercises().then((list) => setCatalog(list || [])).catch(() => {});
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (prefill && prefill.length) {
      setRows(prefill.map(exToRow));
      setTab("quick");
    } else {
      setRows([emptyRow()]);
      setText("");
      setRpe(null);
      setTitle("");
      setNotes("");
      setTab("quick");
    }
  }, [open, prefill]);

  const updateRow = (i, patch) =>
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));

  // При вводе названия — автоподстановка slug и группы мышц из каталога.
  const updateName = (i, name) => {
    const key = (name || "").trim().toLowerCase();
    const match = catalogByName[key];
    setRows((rs) =>
      rs.map((r, idx) =>
        idx === i
          ? {
              ...r,
              name,
              slug: match ? match.slug : r.slug,
              muscle_group: match && (match.muscle_groups || []).length
                ? match.muscle_groups[0]
                : r.muscle_group,
            }
          : r
      )
    );
    if (match) {
      const groups = (match.muscle_groups || []).join(", ");
      toast.success("\u00ab" + match.name + "\u00bb \u2014 группа: " + (groups || "\u2014"), { duration: 1800 });
    }
  };
  const addRow = () => setRows((rs) => [...rs, emptyRow()]);
  const removeRow = (i) => setRows((rs) => (rs.length > 1 ? rs.filter((_, idx) => idx !== i) : rs));

  const updateGroup = (i, gi, patch) =>
    setRows((rs) =>
      rs.map((r, idx) =>
        idx === i
          ? { ...r, groups: r.groups.map((g, gidx) => (gidx === gi ? { ...g, ...patch } : g)) }
          : r
      )
    );
  const addGroup = (i) =>
    setRows((rs) =>
      rs.map((r, idx) => {
        if (idx !== i) return r;
        const last = r.groups[r.groups.length - 1] || emptyGroup();
        return { ...r, groups: [...r.groups, { weight: "", sets: "1", reps: last.reps }] };
      })
    );
  const removeGroup = (i, gi) =>
    setRows((rs) =>
      rs.map((r, idx) =>
        idx === i && r.groups.length > 1
          ? { ...r, groups: r.groups.filter((_, gidx) => gidx !== gi) }
          : r
      )
    );

  const rowsToExercises = () =>
    rows
      .filter((r) => (r.name || "").trim())
      .map((r) => {
        const sets_scheme = r.is_accessory
          ? []
          : r.groups
              .map((g) => ({
                weight: g.weight === "" ? null : parseFloat(g.weight),
                sets: parseInt(g.sets, 10) || 1,
                reps: parseInt(g.reps, 10) || 0,
              }))
              .filter((g) => g.reps > 0 || g.weight != null);
        return {
          name: r.name.trim(),
          exercise_slug: r.slug || null,
          muscle_group: r.muscle_group || null,
          is_accessory: r.is_accessory,
          sets_scheme,
        };
      });

  // Живая сводка: упражнения / подходы / тоннаж.
  const summary = useMemo(() => {
    let exercises = 0;
    let sets = 0;
    let tonnage = 0;
    rows.forEach((r) => {
      if (!(r.name || "").trim()) return;
      exercises += 1;
      if (r.is_accessory) return;
      r.groups.forEach((g) => {
        const s = parseInt(g.sets, 10);
        const reps = parseInt(g.reps, 10);
        const w = parseFloat(g.weight);
        if (!Number.isFinite(s) || s <= 0) return;
        sets += s;
        if (Number.isFinite(w) && w > 0 && Number.isFinite(reps) && reps > 0) {
          tonnage += w * s * reps;
        }
      });
    });
    return { exercises, sets, tonnage };
  }, [rows]);

  const handleSave = async (exercises) => {
    const exs = exercises || rowsToExercises();
    if (!exs.length) {
      toast.error("Добавь хотя бы одно упражнение");
      return;
    }
    setBusy(true);
    setBusyMsg("Сохраняю...");
    try {
      const session = await createDiarySession({
        date,
        title: (title || "").trim() || null,
        notes: (notes || "").trim() || null,
        rpe: rpe || null,
        source_input: tab === "text" ? "text" : "quick",
        exercises: exs,
      });
      toast.success("Тренировка записана");
      window.dispatchEvent(new Event("twb:progress"));
      onSaved && onSaved(session);
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Не удалось сохранить");
    } finally {
      setBusy(false);
      setBusyMsg("");
    }
  };

  const handleParse = async () => {
    if ((text || "").trim().length < 3) {
      toast.error("Опиши тренировку подробнее");
      return;
    }
    setBusy(true);
    setBusyMsg("ИИ распознаёт запись...");
    try {
      const { job_id } = await diaryParse(text.trim());
      const job = await pollDiaryJob(job_id);
      if (job.status !== "done" || !job.template) {
        throw new Error(job.error || "Не удалось распознать");
      }
      setRows((job.template.exercises || []).map(exToRow));
      setTab("quick");
      toast.success("Распознано — проверь и сохрани");
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message || "Ошибка распознавания");
    } finally {
      setBusy(false);
      setBusyMsg("");
    }
  };

  const isQuick = tab === "quick";

  if (!open) return null;

  return (
    <div className="diary-modal-backdrop" onClick={onClose} data-testid="diary-composer">
      <div
        className="diary-modal dc-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Записать тренировку"
      >
        <div className="dc-grabber" aria-hidden="true" />

        <div className="diary-modal-head dc-head">
          <div className="dc-title">
            <h3>Запись тренировки</h3>
            <span className="dc-date">
              {new Date(`${date}T00:00:00`).toLocaleDateString("ru-RU", {
                day: "numeric",
                month: "long",
              })}
            </span>
          </div>
          <button type="button" className="diary-modal-close" onClick={onClose} data-testid="diary-composer-close" aria-label="Закрыть">
            <X size={18} />
          </button>
        </div>

        <div className="dc-title-field">
          <input
            className="dc-title-input"
            placeholder="Название тренировки (необязательно)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            data-testid="diary-title"
          />
        </div>

        <div className="diary-tabs dc-tabs" role="tablist">
          <button
            type="button"
            className={isQuick ? "active" : ""}
            onClick={() => setTab("quick")}
            data-testid="diary-tab-quick"
            role="tab"
            aria-selected={isQuick}
          >
            <Zap size={15} strokeWidth={2.2} />
            Быстро
          </button>
          <button
            type="button"
            className={!isQuick ? "active" : ""}
            onClick={() => setTab("text")}
            data-testid="diary-tab-text"
            role="tab"
            aria-selected={!isQuick}
          >
            <PenLine size={15} strokeWidth={2.2} />
            Текст (ИИ)
          </button>
        </div>

        {!isQuick && (
          <div className="dc-text-wrap">
            <textarea
              className="diary-textarea dc-textarea"
              placeholder={"Опиши, что сделал. Например:\nприсед 100×5×3 потом 110×3, жим лёжа 80×8×8×8, подтягивания 3×10"}
              value={text}
              onChange={(e) => setText(e.target.value)}
              data-testid="diary-composer-text"
            />
            <p className="diary-hint-txt">
              ИИ распознает упражнения и подходы (в т.ч. разные веса). Дальше проверишь и сохранишь.
            </p>
            <button
              className="diary-btn diary-btn-primary"
              onClick={handleParse}
              disabled={busy}
              data-testid="diary-parse-btn"
            >
              {busy ? <span className="diary-spinner" /> : "Распознать"}
            </button>
          </div>
        )}

        {isQuick && (
          <>
            <div className="dc-list" ref={listRef}>
              {rows.map((r, i) => {
                const filled = !!(r.name || "").trim();
                return (
                  <div className="qx-card" key={i}>
                    <div className="qx-card-head">
                      <span className={`qx-index ${filled ? "filled" : ""}`} aria-hidden="true">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <div className="qx-name-wrap">
                        <Search size={15} className="qx-name-icon" aria-hidden="true" />
                        <input
                          className="qx-name"
                          list="diary-ex-catalog"
                          placeholder="Упражнение"
                          value={r.name}
                          onChange={(e) => updateName(i, e.target.value)}
                          data-testid={`diary-ex-name-${i}`}
                        />
                      </div>
                      {rows.length > 1 && (
                        <button
                          className="qx-row-remove"
                          onClick={() => removeRow(i)}
                          aria-label="Удалить упражнение"
                        >
                          <Trash2 size={17} />
                        </button>
                      )}
                    </div>
                    {r.muscle_group && (
                      <div className="dc-muscle-chip" data-testid={`diary-ex-muscle-${i}`}>
                        {r.muscle_group}
                      </div>
                    )}

                    <label className={`qx-acc ${r.is_accessory ? "on" : ""}`}>
                      <input
                        type="checkbox"
                        checked={r.is_accessory}
                        onChange={(e) => updateRow(i, { is_accessory: e.target.checked })}
                      />
                      <span className="qx-acc-pill">Подсобное · без веса</span>
                    </label>

                    {!r.is_accessory && (
                      <div className="dc-sets">
                        <div className="dc-set-head" aria-hidden="true">
                          <span>Вес, кг</span>
                          <span>Подходы</span>
                          <span>Повторы</span>
                          <span />
                        </div>
                        {r.groups.map((g, gi) => (
                          <div className="dc-set-row" key={gi}>
                            <div className="dc-set-cell">
                              <input
                                type="number"
                                inputMode="decimal"
                                value={g.weight}
                                onChange={(e) => updateGroup(i, gi, { weight: e.target.value })}
                                placeholder="—"
                                data-testid={`diary-ex-weight-${i}-${gi}`}
                              />
                            </div>
                            <div className="dc-set-cell">
                              <input
                                type="number"
                                inputMode="numeric"
                                value={g.sets}
                                onChange={(e) => updateGroup(i, gi, { sets: e.target.value })}
                                data-testid={`diary-ex-sets-${i}-${gi}`}
                              />
                            </div>
                            <div className="dc-set-cell">
                              <input
                                type="number"
                                inputMode="numeric"
                                value={g.reps}
                                onChange={(e) => updateGroup(i, gi, { reps: e.target.value })}
                                data-testid={`diary-ex-reps-${i}-${gi}`}
                              />
                            </div>
                            <div className="dc-set-del">
                              {r.groups.length > 1 && (
                                <button
                                  onClick={() => removeGroup(i, gi)}
                                  aria-label="Убрать подход"
                                  data-testid={`diary-remove-group-${i}-${gi}`}
                                >
                                  <X size={15} />
                                </button>
                              )}
                            </div>
                          </div>
                        ))}
                        <button
                          className="qx-add-group"
                          onClick={() => addGroup(i)}
                          data-testid={`diary-add-group-${i}`}
                        >
                          <Plus size={14} /> подход с другим весом
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
              <datalist id="diary-ex-catalog">
                {catalog.map((ex) => (
                  <option key={ex.id} value={ex.name} />
                ))}
              </datalist>
            </div>

            <button
              type="button"
              className="dc-add-ex"
              onClick={() => {
                addRow();
                requestAnimationFrame(() => {
                  if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
                });
              }}
              data-testid="diary-add-ex"
            >
              <Plus size={16} /> Добавить упражнение
            </button>

            <div className="dc-notes">
              <textarea
                className="dc-notes-input"
                placeholder="Заметка про тренировку (самочувствие, техника, бег/кардио...) — необязательно"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                data-testid="diary-notes"
              />
            </div>

            <div className="dc-rpe">
              <div className="dc-rpe-head">
                <span>Насколько тяжело?</span>
                <span className="dc-rpe-opt">необязательно</span>
              </div>
              <div className="rpe-row dc-rpe-scale">
                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                  <button
                    key={n}
                    className={rpe === n ? "sel" : ""}
                    onClick={() => setRpe(rpe === n ? null : n)}
                    data-testid={`diary-rpe-${n}`}
                    title={`${n} — ${RPE_LABEL[n]}`}
                  >
                    {n}
                  </button>
                ))}
              </div>
              <div className="dc-rpe-desc">
                {rpe ? `RPE ${rpe} — ${RPE_LABEL[rpe]}` : "RPE — индекс воспринимаемой нагрузки"}
              </div>
            </div>
          </>
        )}
        {isQuick && (
          <div className="dc-footer">
            <div className="dc-summary">
              <div className="dc-sum-stat">
                <b>{summary.exercises}</b>
                <span>упражн.</span>
              </div>
              <div className="dc-sum-stat">
                <b>{summary.sets}</b>
                <span>подходов</span>
              </div>
              <div className="dc-sum-stat dc-sum-tonnage">
                <b>{summary.tonnage > 0 ? summary.tonnage.toLocaleString("ru-RU") : "—"}</b>
                <span>кг объём</span>
              </div>
            </div>
            <button
              className="dc-save"
              onClick={() => handleSave()}
              disabled={busy || summary.exercises === 0}
              data-testid="diary-save-btn"
            >
              {busy ? <span className="diary-spinner" /> : "Сохранить тренировку"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default DiaryComposer;
