import React, { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, LogOut, Users, UserCog, Dumbbell, Link2, X, BarChart3, ChevronRight, Bell, Calculator, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { useUser } from "@/context/UserContext";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useBackButton } from "@/hooks/useTelegramUI";
import { haptic, hapticNotify } from "@/lib/platform";
import {
  getCoachClients,
  coachInvite,
  coachLink,
  coachUnlink,
  getAthleteCoach,
} from "@/api";
import "@/pages/Profile.css";

const PROVIDER_LABEL = { telegram: "Telegram", email: "Email", google: "Google" };

const avatarUrlFor = (u) =>
  (u && u.picture) ||
  `https://ui-avatars.com/api/?name=${encodeURIComponent(
    (u && u.first_name) || "U"
  )}&background=FF6B00&color=fff&size=80&bold=true`;

export default function Profile() {
  const navigate = useNavigate();
  const { authUser, logout, switchMode } = useAuth();
  const { avatarUrl, env, platform } = useUser();
  const { roles } = useCapabilities();

  useBackButton(true, () => navigate(-1));

  const coachId = authUser?.telegram_id;
  const capsRoles = roles;
  const userRoles = (authUser && authUser.roles) || ["athlete"];
  // Приоритет у capabilities; фолбэк — роли из профиля пользователя.
  const effectiveRoles = capsRoles.length ? capsRoles : userRoles;
  const activeMode = (authUser && authUser.active_mode) || "athlete";
  const isCoach = effectiveRoles.includes("coach") || activeMode === "coach";
  const isAdmin = effectiveRoles.includes("admin");
  const providers = (authUser && authUser.auth_provider) || [];

  // Фаза 1: определяем режим пользователя по capabilities / roles
  const modeLabel = useMemo(() => {
    if (isAdmin) return "Админ";
    if (isCoach) return "Тренер";
    if (activeMode === "athlete") return "Самостоятельно";
    return "С подопечным тренером";
  }, [isAdmin, isCoach, activeMode]);

  const [clients, setClients] = useState([]);
  const [invite, setInvite] = useState(null);
  const [myCoach, setMyCoach] = useState(null);
  const [codeInput, setCodeInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [modeBusy, setModeBusy] = useState(false);

  const loadCoachData = useCallback(async () => {
    if (!coachId || !isCoach) {
      setClients([]);
      return;
    }
    try {
      const [inv, data] = await Promise.all([
        coachInvite(coachId).catch(() => null),
        getCoachClients(coachId).catch(() => ({ clients: [] })),
      ]);
      setInvite(inv);
      setClients(data.clients || []);
    } catch (e) {
      /* no-op */
    }
  }, [coachId, isCoach]);

  useEffect(() => {
    loadCoachData();
  }, [loadCoachData]);

  const loadMyCoach = useCallback(async () => {
    if (!coachId) return;
    try {
      const d = await getAthleteCoach(coachId);
      setMyCoach((d && d.coach) || null);
    } catch (e) {
      /* no-op */
    }
  }, [coachId]);

  useEffect(() => {
    loadMyCoach();
  }, [loadMyCoach]);

  const setMode = async (mode) => {
    if (mode === activeMode || modeBusy) return;
    haptic("light");
    setModeBusy(true);
    try {
      await switchMode(mode);
      hapticNotify("success");
      toast.success(mode === "coach" ? "Режим тренера включён" : "Режим спортсмена");
    } catch (e) {
      toast.error("Не удалось переключить режим");
    } finally {
      setModeBusy(false);
    }
  };

  const linkMyCoach = async () => {
    const code = codeInput.trim().toUpperCase();
    if (!code || busy) return;
    setBusy(true);
    try {
      const r = await coachLink(code, coachId);
      setMyCoach(r.coach);
      setCodeInput("");
      hapticNotify("success");
      toast.success("Тренер привязан");
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Не удалось привязать тренера");
    } finally {
      setBusy(false);
    }
  };

  const unlinkMyCoach = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await coachUnlink(coachId);
      setMyCoach(null);
      toast.success("Тренер отвязан");
    } catch (e) {
      toast.error("Не удалось отвязать тренера");
    } finally {
      setBusy(false);
    }
  };

  const onLogout = async () => {
    haptic("medium");
    await logout();
    navigate("/");
  };

  const platformLabel =
    env === "telegram"
      ? `Telegram (${platform})`
      : env === "pwa"
      ? "Установленное приложение (PWA)"
      : "Веб-браузер";

  return (
    <div className="profile-page" data-testid="profile-page">
      <header className="profile-header">
        <button
          className="profile-back"
          onClick={() => navigate(-1)}
          aria-label="Назад"
          data-testid="profile-back"
        >
          <ArrowLeft size={22} />
        </button>
        <h1 className="profile-title">Профиль</h1>
      </header>

      <div className="profile-card">
        <img src={avatarUrl} alt="" className="profile-avatar-lg" />
        <div className="profile-name">{authUser?.first_name || "Пользователь"}</div>
        {authUser?.email ? (
          <div className="profile-email">{authUser.email}</div>
        ) : null}
        {authUser?.username ? (
          <div className="profile-username">@{authUser.username}</div>
        ) : null}
        {providers.length ? (
          <div className="profile-badges">
            {providers.map((p) => (
              <span key={p} className="profile-badge">
                {PROVIDER_LABEL[p] || p}
              </span>
            ))}
          </div>
        ) : null}
        {modeLabel && (
          <span className="profile-mode-badge" data-testid="profile-mode-badge">
            {modeLabel}
          </span>
        )}
      </div>

      {/* Админ-панель (только для admin) */}
      {isAdmin ? (
        <button
          className="profile-nav profile-nav-admin"
          onClick={() => navigate("/admin")}
          data-testid="open-admin-panel"
        >
          <span className="profile-nav-left">
            <span className="profile-nav-ic">
              <ShieldCheck size={18} />
            </span>
            Админ-панель
          </span>
          <ChevronRight size={18} className="profile-nav-chev" />
        </button>
      ) : null}

      {/* Моя статистика */}
      <button
        className="profile-nav"
        onClick={() => navigate("/stats")}
        data-testid="open-my-stats"
      >
        <span className="profile-nav-left">
          <span className="profile-nav-ic"><BarChart3 size={18} /></span>
          Моя статистика
        </span>
        <ChevronRight size={18} className="profile-nav-chev" />
      </button>

      {/* Уведомления */}
      <button
        className="profile-nav"
        onClick={() => navigate("/notifications")}
        data-testid="open-notifications"
      >
        <span className="profile-nav-left">
          <span className="profile-nav-ic"><Bell size={18} /></span>
          Уведомления
        </span>
        <ChevronRight size={18} className="profile-nav-chev" />
      </button>

      {/* Калькулятор 1ПМ */}
      <button
        className="profile-nav"
        onClick={() => navigate("/tools/1rm")}
        data-testid="open-1rm-calculator"
      >
        <span className="profile-nav-left">
          <span className="profile-nav-ic"><Calculator size={18} /></span>
          Калькулятор 1ПМ
        </span>
        <ChevronRight size={18} className="profile-nav-chev" />
      </button>

      {/* Режим: спортсмен / тренер */}
      <div className="profile-section" data-testid="profile-mode">
        <span className="profile-section-title">
          <UserCog size={16} /> Режим
        </span>
        <div className="mode-toggle">
          <button
            className={`mode-btn ${activeMode === "athlete" ? "active" : ""}`}
            onClick={() => setMode("athlete")}
            disabled={modeBusy}
            data-testid="mode-athlete"
          >
            <Dumbbell size={15} /> Спортсмен
          </button>
          <button
            className={`mode-btn ${activeMode === "coach" ? "active" : ""}`}
            onClick={() => setMode("coach")}
            disabled={modeBusy}
            data-testid="mode-coach"
          >
            <Users size={15} /> Тренер
          </button>
        </div>
      </div>

      {/* Подопечные (для тренера) */}
      {isCoach ? (
        <div className="profile-section" data-testid="profile-clients">
          <div className="profile-section-head">
            <span className="profile-section-title">
              <Users size={16} /> Подопечные
              {clients.length ? <em className="profile-count">{clients.length}</em> : null}
            </span>
            <button
              className="profile-section-link"
              onClick={() => navigate("/coach")}
              data-testid="open-coach-cabinet"
            >
              Кабинет тренера
            </button>
          </div>

          {clients.length ? (
            <div className="clients-avatars" data-testid="clients-avatars">
              {clients.map((c) => {
                const a = c.athlete || {};
                return (
                  <button
                    key={a.telegram_id}
                    className="client-ava"
                    onClick={() => navigate(`/coach/${a.telegram_id}`)}
                    data-testid={`client-ava-${a.telegram_id}`}
                    title={a.first_name || ""}
                  >
                    <span className={`client-ava-imgwrap ${c.is_training_now ? "live" : ""}`}>
                      <img src={avatarUrlFor(a)} alt={a.first_name || ""} />
                    </span>
                    <span className="client-ava-name">{a.first_name || "—"}</span>
                  </button>
                );
              })}
            </div>
          ) : (
            <p className="profile-hint" data-testid="clients-empty-hint">
              Пока нет подопечных. Поделитесь кодом приглашения
              {invite?.invite_code ? (
                <>
                  {": "}
                  <b className="invite-inline">{invite.invite_code}</b>
                </>
              ) : (
                "."
              )}
            </p>
          )}
        </div>
      ) : null}

      {/* Мой тренер (для спортсмена) */}
      <div className="profile-section" data-testid="profile-mycoach">
        <span className="profile-section-title">
          <Link2 size={16} /> Мой тренер
        </span>
        {myCoach ? (
          <div className="mycoach-row" data-testid="mycoach-row">
            <img className="mycoach-ava" src={avatarUrlFor(myCoach)} alt="" />
            <span className="mycoach-name">
              {myCoach.first_name}
              {myCoach.username ? ` · @${myCoach.username}` : ""}
            </span>
            <button
              className="mycoach-unlink"
              onClick={unlinkMyCoach}
              disabled={busy}
              aria-label="Отвязать тренера"
              data-testid="unlink-coach"
            >
              <X size={16} />
            </button>
          </div>
        ) : (
          <div className="mycoach-link">
            <input
              className="mycoach-input"
              value={codeInput}
              onChange={(e) => setCodeInput(e.target.value)}
              placeholder="Код тренера"
              maxLength={12}
              data-testid="coach-code-input"
            />
            <button
              className="mycoach-btn"
              onClick={linkMyCoach}
              disabled={busy || !codeInput.trim()}
              data-testid="link-coach-btn"
            >
              Привязать
            </button>
          </div>
        )}
      </div>

      <div className="profile-meta">
        <div className="profile-meta-row">
          <span>Вход выполнен через</span>
          <b>{providers.map((p) => PROVIDER_LABEL[p] || p).join(", ") || "—"}</b>
        </div>
        <div className="profile-meta-row">
          <span>Платформа</span>
          <b>{platformLabel}</b>
        </div>
      </div>

      <button className="profile-logout" onClick={onLogout} data-testid="logout-btn">
        <LogOut size={18} /> Выйти
      </button>
    </div>
  );
}
