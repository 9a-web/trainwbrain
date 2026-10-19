import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useCallback,
} from "react";
import {
  authMe,
  authLoginEmail,
  authRegisterEmail,
  authTelegram,
  authGoogleOAuth,
  getGoogleConfig,
  authLogout,
  getAuthToken,
  setAuthToken,
  switchMode as apiSwitchMode,
} from "@/api";
import { getTelegram, isTelegram } from "@/lib/platform";

const AuthContext = createContext(null);
const TOKEN_KEY = "twb_token";
const USER_CACHE_KEY = "twb_user";
const GOOGLE_STATE_KEY = "twb_google_state";

function saveUser(user) {
  try {
    if (user) window.localStorage.setItem(USER_CACHE_KEY, JSON.stringify(user));
    else window.localStorage.removeItem(USER_CACHE_KEY);
  } catch (e) {
    /* no-op */
  }
}
function loadUser() {
  try {
    const raw = window.localStorage.getItem(USER_CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function saveToken(token) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch (e) {
    /* no-op */
  }
  if (!token) saveUser(null);
  setAuthToken(token || null);
}

export function AuthProvider({ children }) {
  const [authUser, setAuthUser] = useState(null);
  const [loading, setLoading] = useState(true);
  // Инкремент на каждый вход: гарантирует, что «догоняющий» refresh()
  // не перезапишет пользователя/токен, только что полученные при логине.
  const authFlowRef = useRef(0);

  const refresh = useCallback(async () => {
    const startedToken = getAuthToken();
    const flowAtStart = authFlowRef.current;
    try {
      const u = await authMe();
      if (authFlowRef.current === flowAtStart) {
        saveUser(u);
        setAuthUser(u);
      }
      return u;
    } catch (e) {
      // Во время запроса прошёл новый вход — не трогаем свежее состояние.
      if (authFlowRef.current !== flowAtStart) return null;
      const status = e && e.response && e.response.status;
      if (status === 401) {
        // Токен не изменился с начала запроса — можно безопасно очистить сессию.
        if (getAuthToken() === startedToken) saveToken(null);
        setAuthUser(null);
        return null;
      }
      // Сетевой/серверный сбой (5xx/timeout): сохраняем прежнее состояние,
      // чтобы валидная сессия не «выпадала» на экран входа.
      return undefined;
    }
  }, []);

  // Bootstrap: restore an existing session token. The Google callback is
  // handled by the dedicated /auth/google route (see App.js -> GoogleCallback).
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const token = window.localStorage.getItem(TOKEN_KEY);
        if (token) {
          setAuthToken(token);
          // Показываем кэш профиля, чтобы при сетевом сбое не «выпасть» на вход.
          const cached = loadUser();
          if (cached && active) setAuthUser(cached);
          const u = await refresh();
          // Транзиентный сбой — одна повторная попытка, токен при этом сохраняем.
          if (active && u === undefined) {
            await new Promise((r) => setTimeout(r, 1500));
            if (active) await refresh();
          }
        }
      } catch (e) {
        /* no-op */
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [refresh]);

  const loginEmail = useCallback(async (email, password) => {
    const { token, user } = await authLoginEmail(email, password);
    authFlowRef.current += 1;
    saveToken(token);
    saveUser(user);
    setAuthUser(user);
    return user;
  }, []);

  const registerEmail = useCallback(async (email, password, name) => {
    const { token, user } = await authRegisterEmail(email, password, name);
    authFlowRef.current += 1;
    saveToken(token);
    saveUser(user);
    setAuthUser(user);
    return user;
  }, []);

  const loginTelegram = useCallback(async () => {
    const tg = getTelegram();
    const initData = tg && tg.initData;
    if (!initData) throw new Error("Telegram WebApp недоступен");
    const { token, user } = await authTelegram(initData);
    authFlowRef.current += 1;
    saveToken(token);
    saveUser(user);
    setAuthUser(user);
    return user;
  }, []);

  const loginGoogle = useCallback(async () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const { client_id } = await getGoogleConfig();
    const redirectUri = window.location.origin + "/auth/google";
    const params = new URLSearchParams({
      client_id,
      redirect_uri: redirectUri,
      response_type: "code",
      scope: "openid email profile",
      access_type: "offline",
      include_granted_scopes: "true",
      prompt: "select_account",
    });
    // CSRF-защита OAuth: генерим state и проверяем его на callback.
    try {
      const state =
        (window.crypto && window.crypto.randomUUID && window.crypto.randomUUID()) ||
        `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      window.sessionStorage.setItem(GOOGLE_STATE_KEY, state);
      params.set("state", state);
    } catch (e) {
      /* no-op */
    }
    window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
  }, []);

  const consumeGoogleState = useCallback((state) => {
    try {
      const saved = window.sessionStorage.getItem(GOOGLE_STATE_KEY);
      window.sessionStorage.removeItem(GOOGLE_STATE_KEY);
      return !!saved && !!state && saved === state;
    } catch (e) {
      return false;
    }
  }, []);

  const handleGoogleCode = useCallback(async (code) => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUri = window.location.origin + "/auth/google";
    const { token, user } = await authGoogleOAuth(code, redirectUri);
    authFlowRef.current += 1;
    saveToken(token);
    saveUser(user);
    setAuthUser(user);
    return user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authLogout();
    } catch (e) {
      /* ignore */
    }
    authFlowRef.current += 1;
    saveToken(null);
    setAuthUser(null);
  }, []);

  // P3 — переключение активного режима (athlete/coach); обновляет authUser
  const switchMode = useCallback(async (mode) => {
    const tgId = authUser?.telegram_id;
    if (!tgId) return null;
    const updated = await apiSwitchMode(tgId, mode);
    setAuthUser((prev) => {
      const next = { ...(prev || {}), ...updated };
      saveUser(next);
      return next;
    });
    return updated;
  }, [authUser?.telegram_id]);

  const value = useMemo(
    () => ({
      authUser,
      loading,
      isAuthenticated: !!authUser,
      isTelegramAvailable: isTelegram(),
      loginEmail,
      registerEmail,
      loginTelegram,
      loginGoogle,
      handleGoogleCode,
      consumeGoogleState,
      logout,
      refresh,
      switchMode,
    }),
    [
      authUser,
      loading,
      loginEmail,
      registerEmail,
      loginTelegram,
      loginGoogle,
      handleGoogleCode,
      consumeGoogleState,
      logout,
      refresh,
      switchMode,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return (
    useContext(AuthContext) || {
      authUser: null,
      loading: true,
      isAuthenticated: false,
      isTelegramAvailable: false,
    }
  );
}
