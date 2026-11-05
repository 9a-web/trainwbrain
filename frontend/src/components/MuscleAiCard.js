import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Brain, Loader2, RefreshCw, Sparkles, TriangleAlert } from "lucide-react";
import { getSessionMuscleLoad, analyzeSessionMuscles } from "@/api";
import { MUSCLE_LABELS } from "@/lib/muscles";
import "./MuscleAiCard.css";

/**
 * ИИ-разбор тренировки: показывает JSON `muscle_load_v1`, по которому
 * подсвечивается карта мышц.
 *
 * Данные приходят с бэкенда: движок правил считает нагрузку всегда, а языковая
 * модель (если настроен ключ) уточняет её и добавляет пояснения по каждой мышце.
 * Поэтому карточка работает и без ИИ — тогда она честно помечена «правила».
 */

const label = (m) => MUSCLE_LABELS[m] || m;

const ENGINE_META = {
  ai: { text: "ИИ", cls: "ai", icon: Sparkles },
  rules: { text: "Правила", cls: "rules", icon: Brain },
};

function LoadBar({ value }) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <span className="mac-bar" aria-hidden>
      <i style={{ width: `${pct}%` }} />
    </span>
  );
}

export default function MuscleAiCard({ sessionId, testPrefix = "mac", compact = false }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [aiAvailable, setAiAvailable] = useState(true);

  const load = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getSessionMuscleLoad(sessionId);
      setData(res);
      if (res && res.ai_available === false) setAiAvailable(false);
    } catch (e) {
      setError("Не удалось получить разбор тренировки");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => { load(); }, [load]);

  const runAi = async () => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      const res = await analyzeSessionMuscles(sessionId);
      setData(res);
      setAiAvailable(res?.ai_available !== false);
    } catch (e) {
      setError("ИИ-разбор сейчас недоступен");
    } finally {
      setBusy(false);
    }
  };

  const rows = useMemo(() => {
    const muscles = data?.muscles || {};
    return Object.entries(muscles)
      .filter(([, v]) => (v?.load_0_1 || 0) > 0.04)
      .sort((a, b) => (b[1].load_0_1 || 0) - (a[1].load_0_1 || 0));
  }, [data]);

  if (loading) {
    return (
      <div className={`mac-card ${compact ? "is-compact" : ""}`} data-testid={`${testPrefix}-loading`}>
        <div className="mac-head">
          <Loader2 size={15} className="mac-spin" />
          <span>Считаем нагрузку по мышцам…</span>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className={`mac-card ${compact ? "is-compact" : ""}`} data-testid={`${testPrefix}-error`}>
        <div className="mac-head"><TriangleAlert size={15} /><span>{error}</span></div>
      </div>
    );
  }

  const engine = ENGINE_META[data?.engine] || ENGINE_META.rules;
  const EngineIcon = engine.icon;
  const warnings = data?.warnings || [];
  const focus = data?.focus || [];

  return (
    <div className={`mac-card ${compact ? "is-compact" : ""}`} data-testid={`${testPrefix}-card`}>
      <div className="mac-head">
        <span className={`mac-badge ${engine.cls}`} data-testid={`${testPrefix}-engine`}>
          <EngineIcon size={12} strokeWidth={2.4} />
          {engine.text}
        </span>
        <span className="mac-title">Нагрузка по мышцам</span>
        <button
          type="button"
          className="mac-refresh"
          onClick={runAi}
          disabled={busy}
          data-testid={`${testPrefix}-analyze`}
          title={aiAvailable ? "Уточнить разбор с помощью ИИ" : "ИИ пока не настроен"}
        >
          {busy ? <Loader2 size={14} className="mac-spin" /> : <RefreshCw size={14} />}
        </button>
      </div>

      {data?.summary ? (
        <p className="mac-summary" data-testid={`${testPrefix}-summary`}>{data.summary}</p>
      ) : null}

      {focus.length ? (
        <div className="mac-focus" data-testid={`${testPrefix}-focus`}>
          {focus.map((m) => (
            <span key={m} className="mac-chip">{label(m)}</span>
          ))}
        </div>
      ) : null}

      {rows.length ? (
        <ul className="mac-list" data-testid={`${testPrefix}-list`}>
          {rows.map(([m, v]) => (
            <li key={m} className="mac-row">
              <span className="mac-name">{label(m)}</span>
              <LoadBar value={v.load_0_1 || 0} />
              <span className="mac-pct">{Math.round((v.load_0_1 || 0) * 100)}</span>
              {!compact && v.why ? <span className="mac-why">{v.why}</span> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mac-empty">Нет выполненных подходов — нечего подсвечивать</p>
      )}

      {warnings.length ? (
        <ul className="mac-warn" data-testid={`${testPrefix}-warnings`}>
          {warnings.map((w) => (
            <li key={w}><TriangleAlert size={12} />{w}</li>
          ))}
        </ul>
      ) : null}

      {!aiAvailable ? (
        <p className="mac-note" data-testid={`${testPrefix}-note`}>
          ИИ-модель не подключена — показан расчёт по правилам.
        </p>
      ) : null}
    </div>
  );
}
