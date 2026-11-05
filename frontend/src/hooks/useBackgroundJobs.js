/**
 * useBackgroundJobs — персистентный менеджер фоновых ИИ-задач.
 *
 * Хранит активные задачи в localStorage, регулярно опрашивает их статус
 * и позволяет вернуться к результату после перезагрузки/навигации.
 *
 * Каждая задача:
 *   { id: string, kind: string, preview: string, status: "running"|"done"|"error",
 *     progress: string, result?: any, error?: string,
 *     createdAt: string, updatedAt: string }
 */
import React, { useEffect, useRef, useState, useCallback } from "react";
import { getAiJob } from "@/api";

const STORAGE_KEY = "twb_bg_jobs";

// ---- localStorage helpers ----
function readAll() {
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function writeAll(jobs) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs));
  } catch {
    /* no-op */
  }
}

// ---- Утилиты ----
export function getBgJobs() {
  return readAll();
}

export function addBgJob({ id, kind, preview }) {
  const jobs = readAll();
  // Не дублируем
  if (jobs.find((j) => j.id === id)) return;
  jobs.unshift({
    id,
    kind,
    preview,
    status: "running",
    progress: "",
    result: null,
    error: null,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  });
  writeAll(jobs);
}

export function updateBgJob(id, updates) {
  const jobs = readAll();
  const idx = jobs.findIndex((j) => j.id === id);
  if (idx === -1) return;
  jobs[idx] = { ...jobs[idx], ...updates, updatedAt: new Date().toISOString() };
  writeAll(jobs);
}

export function removeBgJob(id) {
  writeAll(readAll().filter((j) => j.id !== id));
}

export function clearDoneJobs() {
  writeAll(readAll().filter((j) => j.status === "running"));
}

/**
 * React-хук: подписывается на изменения localStorage и фоново опрашивает
 * running-задачи, обновляя их статус.
 *
 * Возвращает { jobs, runningCount, clearDone, remove }.
 */
export default function useBackgroundJobs() {
  const [jobs, setJobs] = useState([]);
  const pollingRef = useRef(null);

  // Синхронизируем список из localStorage
  const sync = useCallback(() => {
    setJobs(readAll());
  }, []);

  // Первая загрузка
  useEffect(() => {
    sync();
  }, [sync]);

  // Слушаем внешние изменения localStorage (другие вкладки / компоненты)
  useEffect(() => {
    const handler = () => sync();
    window.addEventListener("storage", handler);
    return () => window.removeEventListener("storage", handler);
  }, [sync]);

  // Фоновый опрос running-задач (каждые 5 сек)
  useEffect(() => {
    let stopped = false;

    const poll = async () => {
      const current = readAll();
      const running = current.filter((j) => j.status === "running");
      if (!running.length) return;

      for (const job of running) {
        if (stopped) return;
        try {
          const backend = await getAiJob(job.id);
          if (stopped) return;
          const updates = { updatedAt: new Date().toISOString() };
          let changed = false;
          if (backend.progress && typeof backend.progress === "string" && backend.progress.length > 3) {
            updates.progress = backend.progress;
            changed = true;
          }
          if (backend.status && backend.status !== "running" && backend.status !== "pending") {
            updates.status = backend.status;
            if (backend.template) {
              updates.result = backend.template;
            }
            if (backend.error) {
              updates.error = backend.error;
            }
            changed = true;
          }
          if (changed) {
            updateBgJob(job.id, updates);
            sync();
          }
        } catch {
          // Ошибка сети — просто пропускаем, попробуем в следующий раз
        }
      }
    };

    const loop = async () => {
      while (!stopped) {
        await poll();
        await new Promise((r) => setTimeout(r, 5000));
      }
    };

    pollingRef.current = loop();
    return () => {
      stopped = true;
    };
  }, [sync]);

  const runningCount = jobs.filter((j) => j.status === "running").length;

  return {
    jobs,
    runningCount,
    clearDone() {
      clearDoneJobs();
      sync();
    },
    remove(id) {
      removeBgJob(id);
      sync();
    },
  };
}