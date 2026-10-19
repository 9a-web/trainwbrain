import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowLeft, Check, Dumbbell, PencilLine, Link2, Sparkles,
  Share2, Trash2, Copy, Send, X,
} from "lucide-react";
import { toast } from "sonner";
import { useUser } from "@/context/UserContext";
import {
  getTemplates, getActivePlan, createPlan, createTemplate,
  deleteTemplate, shareTemplate, importSharedProgram,
  cancelPlan,
} from "@/api";
import { haptic, hapticNotify } from "@/lib/platform";
import { useBackButton } from "@/hooks/useTelegramUI";
import "./Programs.css";

const LEVEL_LABELS = {
  beginner: "Новичок",
  intermediate: "Средний",
  advanced: "Продвинутый",
};
const GOAL_LABELS = {
  strength: "Сила",
  hypertrophy: "Масса",
  powerlifting: "Пауэрлифтинг",
  general: "Общее",
};
const SOURCE_LABELS = {
  constructor: "Конструктор",
  import: "Импорт",
  ai: "ИИ",
};

const WEEKDAYS = [
  { idx: 1, label: "Пн" }, { idx: 2, label: "Вт" }, { idx: 3, label: "Ср" },
  { idx: 4, label: "Чт" }, { idx: 5, label: "Пт" }, { idx: 6, label: "Сб" }, { idx: 7, label: "Вс" },
];

// Модалка настройки программы перед выбором: максимумы (1ПМ) + дни тренировок
const ProgramConfigModal = ({ tpl, onClose, onSubmit, submitting }) => {
  const needMaxes = !!tpl.requires_maxes;
  const daysNeeded = tpl.days_per_week || 3;
  const [squat, setSquat] = useState("");
  const [bench, setBench] = useState("");
  const [deadlift, setDeadlift] = useState("");
  const [days, setDays] = useState([]);

  const toggleDay = (idx) => {
    setDays((prev) =>
      prev.includes(idx)
        ? prev.filter((d) => d !== idx)
        : prev.length >= daysNeeded
          ? prev
          : [...prev, idx]
    );
  };

  const maxesOk = !needMaxes || (Number(squat) > 0 && Number(bench) > 0 && Number(deadlift) > 0);
  const daysOk = days.length === daysNeeded;
  const canSubmit = maxesOk && daysOk && !submitting;

  const submit = () => {
    if (!canSubmit) return;
    const payload = { training_days: [...days].sort((a, b) => a - b) };
    if (needMaxes) {
      payload.maxes = { squat: Number(squat), bench: Number(bench), deadlift: Number(deadlift) };
    }
    onSubmit(payload);
  };

  return (
    <div className="cfg-overlay" onClick={onClose} data-testid="program-config-modal">
      <div className="cfg-modal" onClick={(e) => e.stopPropagation()}>
        <h3 className="cfg-title">{tpl.name}</h3>
        <p className="cfg-sub">Настройте программу под себя</p>

        {needMaxes ? (
          <div className="cfg-section">
            <div className="cfg-section-title">Ваши максимумы (1ПМ), кг</div>
            <div className="cfg-maxes">
              <label className="cfg-max">
                <span>Присед</span>
                <input type="number" inputMode="decimal" value={squat}
                  onChange={(e) => setSquat(e.target.value)} placeholder="0" data-testid="max-squat" />
              </label>
              <label className="cfg-max">
                <span>Жим</span>
                <input type="number" inputMode="decimal" value={bench}
                  onChange={(e) => setBench(e.target.value)} placeholder="0" data-testid="max-bench" />
              </label>
              <label className="cfg-max">
                <span>Тяга</span>
                <input type="number" inputMode="decimal" value={deadlift}
                  onChange={(e) => setDeadlift(e.target.value)} placeholder="0" data-testid="max-deadlift" />
              </label>
            </div>
          </div>
        ) : null}

        <div className="cfg-section">
          <div className="cfg-section-title">
            Когда тренируетесь? <span className="cfg-hint">выберите {daysNeeded}</span>
          </div>
          <div className="cfg-days">
            {WEEKDAYS.map((d) => (
              <button
                key={d.idx}
                type="button"
                className={`cfg-day ${days.includes(d.idx) ? "active" : ""}`}
                onClick={() => toggleDay(d.idx)}
                data-testid={`day-${d.idx}`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>

        <div className="cfg-actions">
          <button className="cfg-btn-cancel" onClick={onClose}>Отмена</button>
          <button className="cfg-btn-save" onClick={submit} disabled={!canSubmit} data-testid="config-submit">
            {submitting ? "Назначаем…" : "Выбрать программу"}
          </button>
        </div>
      </div>
    </div>
  );
};

// Модалка «Поделиться программой»: код + ссылки
const ShareModal = ({ tpl, onClose }) => {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    shareTemplate(tpl.id)
      .then(setData)
      .catch(() => setError("Не удалось получить код"));
  }, [tpl.id]);

  const webLink = data ? `${window.location.origin}${data.web_path}` : "";

  const copy = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(`${label} скопирован${label === "Ссылка" ? "а" : ""}`);
      haptic("light");
    } catch (e) {
      toast.error("Не удалось скопировать");
    }
  };

  return (
    <div className="cfg-overlay" onClick={onClose} data-testid="share-modal">
      <div className="cfg-modal" onClick={(e) => e.stopPropagation()}>
        <h3 className="cfg-title">Поделиться программой</h3>
        <p className="cfg-sub">{tpl.name}</p>
        {error ? <p className="share-error">{error}</p> : null}
        {data ? (
          <>
            <div className="share-code-box" data-testid="share-code">
              <span className="share-code">{data.code}</span>
              <button className="share-copy" onClick={() => copy(data.code, "Код")}
                data-testid="share-copy-code" aria-label="Скопировать код">
                <Copy size={16} />
              </button>
            </div>
            <button className="share-row" onClick={() => copy(webLink, "Ссылка")} data-testid="share-copy-link">
              <Link2 size={16} />
              <span className="share-row-text">{webLink}</span>
              <Copy size={14} />
            </button>
            {data.tg_link ? (
              <button className="share-row" onClick={() => copy(data.tg_link, "Ссылка")}
                data-testid="share-copy-tg">
                <Send size={16} />
                <span className="share-row-text">{data.tg_link}</span>
                <Copy size={14} />
              </button>
            ) : null}
            <p className="share-hint">
              Получатель откроет ссылку или введёт код в разделе «Программы» — и копия появится у него.
            </p>
          </>
        ) : !error ? (
          <p className="share-hint">Получаем код…</p>
        ) : null}
        <div className="cfg-actions">
          <button className="cfg-btn-cancel" onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  );
};

// Модалка «Импорт по коду»
const CodeImportModal = ({ onClose, onImported }) => {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const c = code.trim().toUpperCase();
    if (c.length < 4) return;
    setBusy(true);
    try {
      const res = await importSharedProgram(c);
      hapticNotify("success");
      if (res.own) toast.info("Это ваша собственная программа");
      else if (res.already_imported) toast.info("Эта программа уже импортирована");
      else toast.success(`Программа «${res.template?.name}» импортирована`);
      onImported();
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Не удалось импортировать");
      hapticNotify("error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="cfg-overlay" onClick={onClose} data-testid="code-import-modal">
      <div className="cfg-modal" onClick={(e) => e.stopPropagation()}>
        <h3 className="cfg-title">Импорт по коду</h3>
        <p className="cfg-sub">Введите код программы вида TWB-X7K2P9</p>
        <input
          className="code-input"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="TWB-••••••"
          autoFocus
          data-testid="code-input"
        />
        <div className="cfg-actions">
          <button className="cfg-btn-cancel" onClick={onClose}>Отмена</button>
          <button className="cfg-btn-save" onClick={submit}
            disabled={busy || code.trim().length < 4} data-testid="code-import-submit">
            {busy ? "Импортируем…" : "Импортировать"}
          </button>
        </div>
      </div>
    </div>
  );
};

const Programs = () => {
  const { user } = useUser();
  const navigate = useNavigate();
  const location = useLocation();
  useBackButton(true, () => navigate("/"));
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activePlan, setActivePlan] = useState(null);
  const [assigningId, setAssigningId] = useState(null);
  const [configTpl, setConfigTpl] = useState(null);
  const [shareTpl, setShareTpl] = useState(null);
  const [codeModal, setCodeModal] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [confirmCancelPlan, setConfirmCancelPlan] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [creating, setCreating] = useState(false);

  const loadTemplates = async () => {
    try {
      const d = await getTemplates();
      setTemplates(d);
    } catch (e) {
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTemplates();
  }, []);

  useEffect(() => {
    if (!user?.telegram_id) return undefined;
    let cancelled = false;
    getActivePlan(user.telegram_id)
      .then((p) => { if (!cancelled) setActivePlan(p); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [user?.telegram_id]);

  // Автоопенер конфига после навигации из ИИ-просмотра (state.assignTemplateId)
  useEffect(() => {
    const targetId = location.state?.assignTemplateId;
    if (!targetId || !templates.length || !user?.telegram_id) return;
    const tpl = templates.find((t) => t.id === targetId);
    // очистить state, чтобы не сработало повторно
    navigate(location.pathname, { replace: true, state: {} });
    if (!tpl) return;
    if (tpl.requires_maxes) {
      // нужны 1ПМ — открываем конфиг-модалку
      setConfigTpl(tpl);
    } else {
      // одним кликом: дефолтные дни (Пн/Ср/Пт для 3, Пн/Вт/Чт/Пт для 4 и т.д.)
      const daysNeeded = tpl.days_per_week || 3;
      const defaultDays = daysNeeded === 3 ? [1, 3, 5]
        : daysNeeded === 4 ? [1, 2, 4, 5]
        : daysNeeded === 2 ? [1, 4]
        : daysNeeded === 5 ? [1, 2, 3, 4, 5]
        : daysNeeded === 6 ? [1, 2, 3, 4, 5, 6]
        : [1];
      assign(tpl, { training_days: defaultDays });
    }
  }, [templates, location.state, user?.telegram_id]);

  const myTemplates = templates.filter((t) => !t.is_builtin);
  const builtins = templates.filter((t) => t.is_builtin);

  const assign = async (tpl, extra = {}) => {
    setAssigningId(tpl.id);
    try {
      const plan = await createPlan({
        athlete_telegram_id: user.telegram_id,
        template_id: tpl.id,
        ...extra,
      });
      setActivePlan(plan);
      setConfigTpl(null);
      hapticNotify("success");
      toast.success(`Программа «${tpl.name}» выбрана`);
      setTimeout(() => navigate("/"), 600);
    } catch (e) {
      toast.error("Не удалось выбрать программу");
    } finally {
      setAssigningId(null);
    }
  };

  const handleChoose = (tpl) => {
    haptic("light");
    if (!user?.telegram_id) {
      toast.error("Пользователь не определён");
      return;
    }
    if (tpl.requires_maxes) {
      setConfigTpl(tpl);
      return;
    }
    assign(tpl);
  };

  const openConstructor = async () => {
    if (creating) return;
    setCreating(true);
    haptic("light");
    try {
      const tpl = await createTemplate({
        name: "Новая программа",
        description: "",
        source: "constructor",
        weeks: [{ week_index: 1, published: true, days: [] }],
      });
      navigate(`/programs/builder/${tpl.id}`);
    } catch (e) {
      toast.error("Не удалось создать программу");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (tpl) => {
    if (confirmDeleteId !== tpl.id) {
      setConfirmDeleteId(tpl.id);
      setTimeout(() => setConfirmDeleteId((v) => (v === tpl.id ? null : v)), 3000);
      return;
    }
    try {
      await deleteTemplate(tpl.id);
      setConfirmDeleteId(null);
      // если активный план ссылался на этот шаблон — deletetemplate вернул plans_cancelled>0
      setActivePlan((p) => (p && p.source_template_id === tpl.id ? null : p));
      toast.success("Программа удалена");
      loadTemplates();
    } catch (e) {
      toast.error("Не удалось удалить");
    }
  };

  const handleCancelActive = async () => {
    if (!activePlan?.id) return;
    if (!confirmCancelPlan) {
      setConfirmCancelPlan(true);
      setTimeout(() => setConfirmCancelPlan((v) => (v ? false : v)), 3500);
      return;
    }
    setCancelling(true);
    try {
      await cancelPlan(activePlan.id);
      setActivePlan(null);
      setConfirmCancelPlan(false);
      toast.success("Выбор программы отменён. Прогресс сохранён.");
    } catch (e) {
      toast.error("Не удалось отменить");
    } finally {
      setCancelling(false);
    }
  };

  const renderCard = (tpl, own) => {
    const isActive = activePlan && activePlan.source_template_id === tpl.id;
    return (
      <div
        className={`program-card ${isActive ? "program-card-active" : ""}`}
        key={tpl.id}
        data-testid={`program-card-${tpl.slug || tpl.id}`}
      >
        <div className="program-card-head">
          <div className="program-card-icon">
            {own ? <PencilLine size={20} /> : <Dumbbell size={20} />}
          </div>
          <div className="program-card-titles">
            <h3 className="program-card-name">{tpl.name}</h3>
            <div className="program-card-badges">
              <span className="badge">{LEVEL_LABELS[tpl.level] || tpl.level}</span>
              <span className="badge">{GOAL_LABELS[tpl.goal] || tpl.goal}</span>
              {own && tpl.source ? (
                <span className="badge badge-source">{SOURCE_LABELS[tpl.source] || tpl.source}</span>
              ) : null}
            </div>
          </div>
        </div>
        {tpl.description ? <p className="program-card-desc">{tpl.description}</p> : null}
        <div className="program-card-meta">
          <span>{tpl.weeks_count} нед.</span>
          <span>·</span>
          <span>{tpl.days_per_week || "—"} дн./нед.</span>
        </div>
        <div className="program-card-foot">
          <button
            className="program-card-button"
            type="button"
            onClick={() => handleChoose(tpl)}
            disabled={assigningId === tpl.id || isActive}
            data-testid={`choose-${tpl.slug || tpl.id}`}
          >
            {isActive ? (<><Check size={16} /> Активна</>)
              : assigningId === tpl.id ? "Назначаем…" : "Выбрать"}
          </button>
          {isActive ? (
            <button
              className={`program-cancel-btn ${confirmCancelPlan ? "confirming" : ""}`}
              type="button"
              onClick={handleCancelActive}
              disabled={cancelling}
              data-testid={`cancel-active-${tpl.slug || tpl.id}`}
              title="Отменить выбор программы (прогресс сохраняется)"
            >
              {cancelling ? "Отменяем…" : (confirmCancelPlan ? "Точно отменить?" : "Отменить выбор")}
            </button>
          ) : null}
          {own ? (
            <div className="program-own-actions">
              <button className="own-act" onClick={() => navigate(`/programs/builder/${tpl.id}`)}
                aria-label="Изменить" data-testid={`edit-${tpl.id}`}>
                <PencilLine size={17} />
              </button>
              <button className="own-act" onClick={() => setShareTpl(tpl)}
                aria-label="Поделиться" data-testid={`share-${tpl.id}`}>
                <Share2 size={17} />
              </button>
              <button
                className={`own-act own-act-danger ${confirmDeleteId === tpl.id ? "confirming" : ""}`}
                onClick={() => handleDelete(tpl)}
                aria-label="Удалить"
                data-testid={`delete-${tpl.id}`}
              >
                {confirmDeleteId === tpl.id ? <X size={17} /> : <Trash2 size={17} />}
              </button>
            </div>
          ) : null}
        </div>
        {confirmDeleteId === tpl.id ? (
          <p className="delete-confirm-note">Нажмите ещё раз, чтобы удалить безвозвратно</p>
        ) : null}
      </div>
    );
  };

  return (
    <div className="programs-page" data-testid="programs-page">
      <header className="programs-header">
        <Link to="/" className="programs-back" data-testid="programs-back" aria-label="Назад">
          <ArrowLeft size={22} />
        </Link>
        <h1 className="programs-title">Программы</h1>
      </header>

      <div className="programs-actions programs-actions-3">
        <button className="programs-action" type="button" onClick={openConstructor}
          disabled={creating} data-testid="action-constructor">
          <PencilLine size={18} />
          <span>Конструктор</span>
        </button>
        <button className="programs-action" type="button" onClick={() => setCodeModal(true)}
          data-testid="action-code-import">
          <Link2 size={18} />
          <span>По коду / ссылке</span>
        </button>
        <button className="programs-action programs-action-ai" type="button"
          onClick={() => navigate("/programs/ai")} data-testid="action-ai">
          <Sparkles size={18} />
          <span>ИИ-анализ</span>
          <em>AI</em>
        </button>
      </div>

      {loading ? (
        <div className="programs-empty">Загрузка…</div>
      ) : (
        <>
          {myTemplates.length ? (
            <>
              <h2 className="programs-section-title">Мои программы</h2>
              <div className="programs-list" data-testid="my-programs-list">
                {myTemplates.map((t) => renderCard(t, true))}
              </div>
            </>
          ) : null}

          <h2 className="programs-section-title" style={myTemplates.length ? { marginTop: 24 } : undefined}>
            Готовые программы
          </h2>
          {builtins.length === 0 ? (
            <div className="programs-empty">Программы не найдены</div>
          ) : (
            <div className="programs-list">
              {builtins.map((t) => renderCard(t, false))}
            </div>
          )}
        </>
      )}

      {configTpl ? (
        <ProgramConfigModal
          tpl={configTpl}
          submitting={assigningId === configTpl.id}
          onClose={() => setConfigTpl(null)}
          onSubmit={(payload) => assign(configTpl, payload)}
        />
      ) : null}
      {shareTpl ? <ShareModal tpl={shareTpl} onClose={() => setShareTpl(null)} /> : null}
      {codeModal ? (
        <CodeImportModal
          onClose={() => setCodeModal(false)}
          onImported={() => { setCodeModal(false); loadTemplates(); }}
        />
      ) : null}
    </div>
  );
};

export default Programs;
