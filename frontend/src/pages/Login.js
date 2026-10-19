import React, { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { haptic, hapticNotify } from "@/lib/platform";
import "@/pages/Login.css";

export default function Login() {
  const {
    loginEmail,
    registerEmail,
    loginTelegram,
    loginGoogle,
    isTelegramAvailable,
  } = useAuth();
  const [mode, setMode] = useState("login"); // login | register
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Ошибку Google OAuth (отказ/сбой проверки) показываем на экране входа.
  useEffect(() => {
    try {
      const ge = window.sessionStorage.getItem("twb_google_error");
      if (ge) {
        window.sessionStorage.removeItem("twb_google_error");
        setError(ge);
      }
    } catch (e) {
      /* no-op */
    }
  }, []);

  const errText = (err, fallback) => {
    const d = err && err.response && err.response.data && err.response.data.detail;
    return typeof d === "string" ? d : fallback;
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    haptic("light");
    try {
      if (mode === "register") {
        await registerEmail(email.trim(), password, name.trim());
      } else {
        await loginEmail(email.trim(), password);
      }
      hapticNotify("success");
    } catch (err) {
      setError(errText(err, "Не удалось войти. Проверьте данные."));
      hapticNotify("error");
    } finally {
      setBusy(false);
    }
  };

  const onTelegram = async () => {
    setError("");
    setBusy(true);
    haptic("medium");
    try {
      await loginTelegram();
      hapticNotify("success");
    } catch (err) {
      setError("Не удалось войти через Telegram");
      hapticNotify("error");
    } finally {
      setBusy(false);
    }
  };

  const onGoogle = async () => {
    setError("");
    setBusy(true);
    haptic("light");
    try {
      await loginGoogle();
    } catch (err) {
      setError(errText(err, "Не удалось войти через Google"));
      hapticNotify("error");
      setBusy(false);
    }
  };

  return (
    <div className="login-page" data-testid="login-page">
      <div className="login-gradient" aria-hidden="true">
        <img src="/gradientcenter.png" alt="" />
      </div>

      <div className="login-card">
        <img src="/TWBlogo.png" alt="TrainWithBrain" className="login-logo" />
        <h1 className="login-title">
          {mode === "register" ? "Регистрация" : "Вход"}
        </h1>
        <p className="login-subtitle">Войдите, чтобы продолжить тренировки</p>

        {isTelegramAvailable && (
          <button
            type="button"
            className="login-btn login-btn-tg"
            onClick={onTelegram}
            disabled={busy}
            data-testid="login-telegram"
          >
            Войти через Telegram
          </button>
        )}

        <button
          type="button"
          className="login-btn login-btn-google"
          onClick={onGoogle}
          disabled={busy}
          data-testid="login-google"
        >
          <span className="login-g">G</span>
          Войти через Google
        </button>

        <div className="login-divider">
          <span>или по email</span>
        </div>

        <form className="login-form" onSubmit={submit}>
          {mode === "register" && (
            <input
              className="login-input"
              type="text"
              placeholder="Имя"
              value={name}
              onChange={(e) => setName(e.target.value)}
              data-testid="login-name"
            />
          )}
          <input
            className="login-input"
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            data-testid="login-email"
          />
          <input
            className="login-input"
            type="password"
            placeholder="Пароль (минимум 6 символов)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            data-testid="login-password"
          />
          {error ? (
            <div className="login-error" data-testid="login-error">
              {error}
            </div>
          ) : null}
          <button
            type="submit"
            className="login-btn login-btn-primary"
            disabled={busy}
            data-testid="login-submit"
          >
            {busy
              ? "Подождите…"
              : mode === "register"
              ? "Зарегистрироваться"
              : "Войти"}
          </button>
        </form>

        <button
          type="button"
          className="login-switch"
          onClick={() => {
            setError("");
            setMode(mode === "login" ? "register" : "login");
          }}
          data-testid="login-switch"
        >
          {mode === "login"
            ? "Нет аккаунта? Зарегистрироваться"
            : "Уже есть аккаунт? Войти"}
        </button>
      </div>
    </div>
  );
}
