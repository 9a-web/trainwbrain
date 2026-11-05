import { useCallback, useEffect, useState } from "react";
import { getCapabilities } from "@/api";

/**
 * Фаза 1 — возможности пользователя (роли / tier / права / онбординг).
 *
 * Полностью backward-compatible: если `GET /me/capabilities` ещё не
 * реализован на бэкенде (404/сеть), capabilities === null, onboarded ===
 * undefined и can() всегда возвращает true, чтобы приложение работало как
 * раньше.
 */
const EMPTY_ROLES = [];

export function useCapabilities() {
  const [capabilities, setCapabilities] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getCapabilities();
      setCapabilities(data || null);
      return data || null;
    } catch (e) {
      setCapabilities(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getCapabilities()
      .then((data) => {
        if (active) setCapabilities(data || null);
      })
      .catch(() => {
        if (active) setCapabilities(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    // Смена режима (спортсмен/тренер/клиент) в профиле должна обновлять
    // capabilities во всех инстансах хука, иначе AppShell останется на старом
    // active_mode и покажет не тот главный экран.
    const onModeChange = () => {
      getCapabilities()
        .then((data) => { if (active) setCapabilities(data || null); })
        .catch(() => {});
    };
    window.addEventListener("twb:capabilities-changed", onModeChange);
    return () => {
      active = false;
      window.removeEventListener("twb:capabilities-changed", onModeChange);
    };
  }, []);

  const can = useCallback(
    (perm) => {
      const perms =
        capabilities && capabilities.permissions ? capabilities.permissions : null;
      if (!perms) return true;
      return !!perms[perm];
    },
    [capabilities]
  );

  // Пока capabilities грузятся, отдаём ПУСТОЙ МАССИВ (а не объект):
  // потребители делают roles.includes(...), и объект ронял рендер
  // (TypeError: roles.includes is not a function → белый экран).
  const roles =
    capabilities && Array.isArray(capabilities.roles)
      ? capabilities.roles
      : EMPTY_ROLES;

  // --- Режим и роли ------------------------------------------------------
  // `roles` — ПОСТОЯННЫЕ права аккаунта (их нельзя «выключить»), поэтому по
  // ним нельзя решать, что показывать: у админа/тренера роль coach есть
  // всегда, и кабинет тренера лез на главный экран в режиме спортсмена.
  // Видимость тренерских/админских функций = роль И активный режим.
  const activeMode = (capabilities && capabilities.active_mode) || "athlete";
  const isCoachRole = roles.includes("coach") || roles.includes("admin");
  const isAdminRole = roles.includes("admin");
  const coachMode = isCoachRole && activeMode === "coach";
  const clientPreview = !!(capabilities && capabilities.client_preview);

  return {
    capabilities,
    can,
    roles,
    onboarded: capabilities ? capabilities.onboarded : undefined,
    accessTier: capabilities ? capabilities.access_tier : undefined,
    activeMode,
    clientPreview,
    // Производные флаги — единый источник правды для всех экранов.
    isCoachRole,
    isAdminRole,
    coachMode,
    loading,
    refresh,
  };
}
