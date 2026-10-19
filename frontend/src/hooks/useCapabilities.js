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
const EMPTY = {};

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
    return () => {
      active = false;
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

  const roles =
    capabilities && Array.isArray(capabilities.roles)
      ? capabilities.roles
      : EMPTY;

  return {
    capabilities,
    can,
    roles,
    onboarded: capabilities ? capabilities.onboarded : undefined,
    accessTier: capabilities ? capabilities.access_tier : undefined,
    loading,
    refresh,
  };
}
