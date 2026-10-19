import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Ticket,
  Users,
  PieChart,
  Search,
  Loader2,
  RotateCcw,
  Save,
  ShieldAlert,
  ShieldCheck,
  UserCog,
} from "lucide-react";
import { toast } from "sonner";
import {
  getAdminSummary,
  getAdminUsers,
  updateAdminPermissions,
  setAdminAccessTier,
  setAdminRole,
} from "@/api";
import { useAuth } from "@/context/AuthContext";
import { useBackButton } from "@/hooks/useTelegramUI";
import { haptic } from "@/lib/platform";
import InviteManager from "@/components/InviteManager";
import PermissionsMatrix, { DEFAULT_PERMISSIONS } from "@/components/PermissionsMatrix";
import "@/pages/Admin.css";

const TIER_LABEL = {
  coach_managed: "С тренером",
  standalone: "Самостоятельно",
};

const avatarFor = (u) => {
  if (u && u.picture) return u.picture;
  const name = encodeURIComponent((u && u.first_name) || "U");
  return `https://ui-avatars.com/api/?name=${name}&background=FF6B00&color=fff&size=80&bold=true`;
};

const errText = (err, fallback) => {
  const d = err && err.response && err.response.data && err.response.data.detail;
  return typeof d === "string" ? d : fallback;
};

const TABS = [
  { id: "invites", label: "Инвайты", icon: Ticket },
  { id: "athletes", label: "Атлеты", icon: Users },
  { id: "summary", label: "Сводка", icon: PieChart },
];

function AthleteRow({ athlete, onSaved }) {
  const tg = athlete.telegram_id;
  const [perms, setPerms] = useState(() => ({
    ...DEFAULT_PERMISSIONS,
    ...(athlete.permissions || {}),
  }));
  const [tier, setTier] = useState(athlete.access_tier || "coach_managed");
  const [saving, setSaving] = useState(false);

  const roles = athlete.roles || [];
  const isAdmin = roles.includes("admin");
  const isCoach = roles.includes("coach");

  const save = async () => {
    setSaving(true);
    haptic("light");
    try {
      await updateAdminPermissions(tg, perms);
      toast.success("Права обновлены");
      onSaved && onSaved();
    } catch (e) {
      toast.error(errText(e, "Не удалось сохранить права"));
    } finally {
      setSaving(false);
    }
  };

  const changeTier = async (next) => {
    const prev = tier;
    setTier(next);
    try {
      await setAdminAccessTier(tg, next);
      toast.success("Режим изменён");
      onSaved && onSaved();
    } catch (e) {
      setTier(prev);
      toast.error(errText(e, "Не удалось изменить режим"));
    }
  };

  const toggleRole = async (role) => {
    try {
      await setAdminRole(tg, role);
      toast.success(
        role === "coach" ? "Роль тренера обновлена" : "Роль админа обновлена"
      );
      onSaved && onSaved();
    } catch (e) {
      toast.error(errText(e, "Не удалось изменить роль"));
    }
  };

  return (
    <div className="adm-athlete" data-testid={`athlete-card-${tg}`}>
      <div className="adm-athlete-head">
        <img className="adm-athlete-ava" src={avatarFor(athlete)} alt="" />
        <div className="adm-athlete-id">
          <span className="adm-athlete-name">
            {athlete.first_name || "Атлет"}
            {athlete.username ? ` · @${athlete.username}` : ""}
          </span>
          <span className="adm-athlete-tg">ID: {tg}</span>
          {athlete.coach_telegram_id ? (
            <span className="adm-athlete-coach">
              Тренер: {athlete.coach_telegram_id}
            </span>
          ) : null}
        </div>
        <span className={`adm-tier-badge adm-tier-${tier}`}>
          {TIER_LABEL[tier] || tier}
        </span>
      </div>

      <div className="adm-athlete-flags">
        {isAdmin ? (
          <span className="adm-flag adm-flag-admin">
            <ShieldCheck size={13} /> Админ
          </span>
        ) : null}
        {isCoach ? (
          <span className="adm-flag">
            <UserCog size={13} /> Тренер
          </span>
        ) : null}
        {athlete.onboarded ? (
          <span className="adm-flag adm-flag-ok">Онбординг пройден</span>
        ) : (
          <span className="adm-flag adm-flag-warn">Без кода</span>
        )}
      </div>

      <div className="adm-subsection">
        <span className="adm-subsection-title">Режим доступа</span>
        <div className="mode-toggle adm-tier-toggle">
          {["coach_managed", "standalone"].map((t) => (
            <button
              key={t}
              type="button"
              className={`mode-btn ${tier === t ? "active" : ""}`}
              onClick={() => changeTier(t)}
              data-testid={`tier-${t}-${tg}`}
            >
              {TIER_LABEL[t]}
            </button>
          ))}
        </div>
      </div>

      <div className="adm-subsection">
        <span className="adm-subsection-title">Права</span>
        <PermissionsMatrix value={perms} onChange={setPerms} />
        <button
          type="button"
          className="adm-btn adm-btn-primary adm-btn-block adm-save"
          onClick={save}
          disabled={saving}
          data-testid={`save-perms-${tg}`}
        >
          {saving ? <Loader2 size={15} className="spin" /> : <Save size={15} />}
          {saving ? "Сохраняем…" : "Сохранить права"}
        </button>
      </div>

      <div className="adm-subsection">
        <span className="adm-subsection-title">Роли</span>
        <div className="adm-role-btns">
          <button
            type="button"
            className={`adm-btn ${isCoach ? "adm-btn-active" : "adm-btn-ghost"}`}
            onClick={() => toggleRole("coach")}
            data-testid={`role-coach-${tg}`}
          >
            {isCoach ? "Снять тренера" : "Сделать тренером"}
          </button>
          <button
            type="button"
            className={`adm-btn ${isAdmin ? "adm-btn-active" : "adm-btn-ghost"}`}
            onClick={() => toggleRole("admin")}
            data-testid={`role-admin-${tg}`}
          >
            {isAdmin ? "Снять админа" : "Сделать админом"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Admin() {
  const navigate = useNavigate();
  const { authUser } = useAuth();
  useBackButton(true, () => navigate("/"));

  const [tab, setTab] = useState("invites");
  const [users, setUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [usersError, setUsersError] = useState("");
  const [query, setQuery] = useState("");
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(true);

  const roles = (authUser && authUser.roles) || [];
  const isAdmin = roles.includes("admin");

  const loadUsers = useCallback(async () => {
    setUsersLoading(true);
    setUsersError("");
    try {
      const data = await getAdminUsers();
      setUsers((data && data.users) || []);
    } catch (e) {
      setUsers([]);
      setUsersError(
        errText(e, "Атлеты пока недоступны. Функция появится после обновления сервера.")
      );
    } finally {
      setUsersLoading(false);
    }
  }, []);

  const loadSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const data = await getAdminSummary();
      setSummary(data || null);
    } catch (e) {
      setSummary(null);
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "athletes" && users.length === 0) loadUsers();
    if (tab === "summary") loadSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) => {
      const name = (u.first_name || "").toLowerCase();
      const uname = (u.username || "").toLowerCase();
      return name.includes(q) || uname.includes(q) || String(u.telegram_id).includes(q);
    });
  }, [users, query]);

  const summaryCards = useMemo(() => {
    if (!summary) return [];
    const managed =
      summary.athletes_coach_managed ?? summary.coach_managed ?? summary.managed ?? 0;
    const standalone =
      summary.athletes_standalone ?? summary.standalone ?? 0;
    const links = summary.active_links ?? summary.active_coach_links ?? 0;
    const invitesUsed = summary.invites_used ?? 0;
    const invitesFree = summary.invites_free ?? summary.invites_active ?? 0;
    return [
      { label: "С тренером", value: managed, testid: "summary-managed" },
      { label: "Самостоятельно", value: standalone, testid: "summary-standalone" },
      { label: "Активных связей", value: links, testid: "summary-links" },
      { label: "Инвайтов использовано", value: invitesUsed, testid: "summary-invites-used" },
      { label: "Инвайтов свободно", value: invitesFree, testid: "summary-invites-free" },
    ];
  }, [summary]);

  return (
    <div className="admin-page" data-testid="admin-page">
      <header className="adm-header">
        <button
          className="coach-back"
          onClick={() => navigate("/")}
          aria-label="Назад"
          data-testid="admin-back"
        >
          <ArrowLeft size={22} />
        </button>
        <h1 className="adm-title">Админ-панель</h1>
      </header>

      {!isAdmin ? (
        <div className="adm-warning" data-testid="admin-warning">
          <ShieldAlert size={18} />
          <span>
            Вы не администратор. Действия на этой странице сервер может отклонить.
          </span>
        </div>
      ) : null}

      <div className="adm-tabs" role="tablist">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              className={`adm-tab ${tab === t.id ? "active" : ""}`}
              onClick={() => {
                haptic("light");
                setTab(t.id);
              }}
              data-testid={`admin-tab-${t.id}`}
            >
              <Icon size={16} /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === "invites" ? (
        <section className="adm-panel anim-fade-up" data-testid="admin-tab-content-invites">
          <InviteManager admin />
        </section>
      ) : null}

      {tab === "athletes" ? (
        <section className="adm-panel anim-fade-up" data-testid="admin-tab-content-athletes">
          <div className="adm-search">
            <Search size={17} className="adm-search-ic" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Поиск по имени, @username или ID"
              data-testid="admin-users-search"
            />
          </div>

          {usersLoading ? (
            <div className="adm-skeleton" data-testid="admin-users-loading">
              <div className="adm-skel-row" />
              <div className="adm-skel-row" />
              <div className="adm-skel-row" />
            </div>
          ) : usersError ? (
            <div className="adm-error" data-testid="admin-users-error">
              <span>{usersError}</span>
              <button
                type="button"
                className="adm-btn adm-btn-ghost"
                onClick={loadUsers}
                data-testid="admin-users-retry"
              >
                <RotateCcw size={15} /> Повторить
              </button>
            </div>
          ) : filtered.length === 0 ? (
            <div className="adm-empty" data-testid="admin-users-empty">
              <Users size={30} />
              <p>{query ? "Ничего не найдено." : "Пока нет атлетов."}</p>
            </div>
          ) : (
            <div className="adm-athletes">
              {filtered.map((u) => (
                <AthleteRow key={u.telegram_id} athlete={u} onSaved={loadUsers} />
              ))}
            </div>
          )}
        </section>
      ) : null}

      {tab === "summary" ? (
        <section className="adm-panel anim-fade-up" data-testid="admin-tab-content-summary">
          {summaryLoading ? (
            <div className="adm-skeleton" data-testid="admin-summary-loading">
              <div className="adm-skel-row" />
              <div className="adm-skel-row" />
            </div>
          ) : !summary ? (
            <div className="adm-empty" data-testid="admin-summary-error">
              <PieChart size={30} />
              <p>Сводка пока недоступна. Обновите после развёртывания сервера.</p>
              <button
                type="button"
                className="adm-btn adm-btn-ghost"
                onClick={loadSummary}
                data-testid="admin-summary-retry"
              >
                <RotateCcw size={15} /> Повторить
              </button>
            </div>
          ) : (
            <div className="adm-summary-grid">
              {summaryCards.map((c) => (
                <div className="adm-summary-card" key={c.testid} data-testid={c.testid}>
                  <span className="adm-summary-value">{c.value}</span>
                  <span className="adm-summary-label">{c.label}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
