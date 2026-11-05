/**
 * BgJobFloater — плавающее уведомление о фоновых ИИ-задачах.
 *
 * Отображается внизу экрана на всех страницах, когда есть активные/завершённые
 * задачи. Показывает краткий статус и кнопку перехода к результату.
 * Исчезает, если задач нет.
 */
import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, X } from "lucide-react";
import useBackgroundJobs from "@/hooks/useBackgroundJobs";
import "@/components/BgJobFloater.css";

export default function BgJobFloater() {
  const navigate = useNavigate();
  const { jobs, runningCount, clearDone, remove } = useBackgroundJobs();
  const [dismissed, setDismissed] = useState(false);

  // Если появляется новая running-задача — сбрасываем dismissed
  const prevRunning = useRef(runningCount);
  useEffect(() => {
    if (runningCount > prevRunning.current) {
      setDismissed(false);
    }
    prevRunning.current = runningCount;
  }, [runningCount]);

  // Показываем флоатер, если есть хотя бы одна задача
  if (jobs.length === 0 || dismissed) return null;

  // Берём первую задачу для превью
  const primary = jobs[0];
  const more = jobs.length - 1;

  // Маршрут для перехода (тот же, что в HomeScreen)
  const routeFor = (job) => {
    const kind = job.kind || "";
    if (kind.startsWith("diary_")) {
      return "/profile";
    }
    if (kind === "cardio_parse") {
      return "/cardio";
    }
    return `/programs/ai?job=${encodeURIComponent(job.id)}`;
  };

  return (
    <div className="bg-floater" data-testid="bg-floater" onClick={() => navigate(routeFor(primary))}>
      <div className="bg-floater-body">
        <span className="bg-floater-icon"><Sparkles size={16} /></span>
        <span className="bg-floater-text">
          {runningCount > 0 ? (
            <span>
              <b>Фоновая задача</b> · {primary.preview || primary.kind}
              {more > 0 ? ` +${more}` : ""}
            </span>
          ) : (
            <span>
              <b>Задача выполнена</b> · {primary.preview || primary.kind}
              {more > 0 ? ` +${more}` : ""}
            </span>
          )}
        </span>
        <span className="bg-floater-status">
          {primary.status === "running" ? (
            <span className="bg-floater-spin" />
          ) : primary.status === "done" ? (
            <span className="bg-floater-done">✓</span>
          ) : (
            <span className="bg-floater-error">✗</span>
          )}
        </span>
        {primary.status === "running" ? (
          <span className="bg-floater-progress">
            {primary.progress || "в процессе…"}
          </span>
        ) : null}
      </div>
      <button
        className="bg-floater-dismiss"
        onClick={(e) => {
          e.stopPropagation();
          setDismissed(true);
        }}
        aria-label="Закрыть уведомление"
      >
        <X size={14} />
      </button>
    </div>
  );
}