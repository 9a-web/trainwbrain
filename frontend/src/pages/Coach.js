import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Copy, Link2, Users, ChevronRight, Dumbbell, Activity } from "lucide-react";
import { toast } from "sonner";
import { useUser } from "@/context/UserContext";
import { getCoachClients, coachInvite } from "@/api";
import { haptic } from "@/lib/platform";
import { useBackButton } from "@/hooks/useTelegramUI";
import { useRealtime } from "@/hooks/useRealtime";
import { useCapabilities } from "@/hooks/useCapabilities";
import InviteManager from "@/components/InviteManager";
import api from "@/api";
import "./Coach.css";

const fmtDate = (iso) => {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  } catch (e) {
    return null;
  }
};

const avatarFor = (c) => {
  const a = c.athlete || {};
  if (a.picture) return a.picture;
  const name = encodeURIComponent(a.first_name || "U");
  return `https://ui-avatars.com/api/?name=${name}&background=FF6B00&color=fff&size=80&bold=true`;
};

export default function Coach() {
  const { user } = useUser();
  const navigate = useNavigate();
  const { subscribe } = useRealtime();
  useBackButton(true, () => navigate("/"));
  const coachId = user?.telegram_id;

  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [invite, setInvite] = useState(null);
  const [liveStatuses, setLiveStatuses] = useState({});
  const { capabilities, loading: capsLoading } = useCapabilities();
  const isCoach = capabilities && (capabilities.roles || []).includes("coach");

  const loadLiveStatuses = useCallback(async () => {
    if (!coachId) return;
    try {
      const response = await api.get(`/coach/${coachId}/clients/live-status`);
      const statusMap = {};
      response.data.clients.forEach(client => {
        statusMap[client.athlete_telegram_id] = client.live_status;
      });
      setLiveStatuses(statusMap);
    } catch (e) {
      /* нет данных live-статуса — показываем клиента как idle */
    }
  }, [coachId]);

  const load = useCallback(async () => {
    if (!coachId) return;
    setLoading(true);
    try {
      const [inv, data] = await Promise.all([
        coachInvite(coachId).catch(() => null),
        getCoachClients(coachId),
      ]);
      setInvite(inv);
      setClients(data.clients || []);
      await loadLiveStatuses();
    } catch (e) {
      toast.error("Не удалось загрузить подопечных");
    } finally {
      setLoading(false);
    }
  }, [coachId, loadLiveStatuses]);

  useEffect(() => {
    load();
  }, [load]);

  // Подписка на live-статусы через WebSocket
  useEffect(() => {
    if (!coachId) return;
    
    const unsubscribe = subscribe('client_status_change', (event) => {
      setLiveStatuses(prev => ({
        ...prev,
        [event.athlete_telegram_id]: event.status
      }));
    });
    
    return () => unsubscribe();
  }, [coachId, subscribe]);

  const copy = async (text, label) => {
    if (!text) return;
    haptic("light");
    try {
      await navigator.clipboard.writeText(text);
      toast.success(`${label} скопирован${label === "Ссылка" ? "а" : ""}`);
    } catch (e) {
      toast.info(text);
    }
  };

  return (
    <div className="coach-page" data-testid="coach-page">
      <header className="coach-header">
        <button className="coach-back" onClick={() => navigate("/")} aria-label="Назад" data-testid="coach-back">
          <ArrowLeft size={22} />
        </button>
        <h1 className="coach-title">Кабинет тренера</h1>
      </header>

      {/* Приглашение */}
      <div className="coach-invite-card" data-testid="coach-invite-card">
        <div className="coach-invite-top">
          <Users size={18} />
          <span>Пригласить спортсмена</span>
        </div>
        <p className="coach-invite-hint">
          Дайте этот код спортсмену — он введёт его в своём профиле и привяжется к вам.
        </p>
        <div className="coach-invite-code" data-testid="coach-invite-code">
          {invite?.invite_code || "········"}
        </div>
        <div className="coach-invite-actions">
          <button className="coach-chip-btn" onClick={() => copy(invite?.invite_code, "Код")} data-testid="copy-code-btn">
            <Copy size={15} /> Код
          </button>
          {invite?.deep_link ? (
            <button className="coach-chip-btn" onClick={() => copy(invite?.deep_link, "Ссылка")} data-testid="copy-link-btn">
              <Link2 size={15} /> Ссылка
            </button>
          ) : null}
        </div>
      </div>

      {/* Приглашения (клиентские коды) */}
      {(capsLoading || capabilities === null || isCoach) ? (
        <section className="invite-section" data-testid="coach-invites">
          <h2 className="coach-section-title">Приглашения</h2>
          <InviteManager presetKind="coach_client" />
        </section>
      ) : null}

      <h2 className="coach-section-title">Подопечные{clients.length ? ` · ${clients.length}` : ""}</h2>

      {loading ? (
        <div className="coach-empty">Загрузка…</div>
      ) : clients.length === 0 ? (
        <div className="coach-empty" data-testid="coach-empty">
          Пока нет подопечных. Поделитесь кодом приглашения выше.
        </div>
      ) : (
        <div className="coach-clients">
          {clients.map((c) => {
            const a = c.athlete || {};
            const last = fmtDate(c.last_workout_at);
            const liveStatus = liveStatuses[a.telegram_id] || 'idle';
            
            return (
              <div
                key={a.telegram_id}
                className="client-card"
                role="button"
                tabIndex={0}
                onClick={() => {
                  haptic("light");
                  navigate(`/coach/${a.telegram_id}`);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") navigate(`/coach/${a.telegram_id}`);
                }}
                data-testid={`client-card-${a.telegram_id}`}
              >
                <img className="client-avatar" src={avatarFor(c)} alt="" />
                <div className="client-main">
                  <div className="client-name-row">
                    <span className="client-name">{a.first_name || "Спортсмен"}</span>
                    {liveStatus === 'on_workout' && (
                      <span
                        className="client-live client-live-btn"
                        role="button"
                        tabIndex={0}
                        onClick={(e) => {
                          e.stopPropagation();
                          haptic("medium");
                          navigate(`/coach/${a.telegram_id}/live`);
                        }}
                        data-testid={`client-live-${a.telegram_id}`}
                      >
                        <span className="live-dot" /> смотреть вживую
                      </span>
                    )}
                    {liveStatus === 'completed' && (
                      <span className="status-badge status-completed">
                        ✓ Завершил
                      </span>
                    )}
                    {liveStatus === 'skipped' && (
                      <span className="status-badge status-skipped">
                        ⚠ Пропустил
                      </span>
                    )}
                  </div>
                  <div className="client-sub">
                    {c.plan ? (
                      <>
                        <Dumbbell size={13} />
                        <span className="client-plan-name">{c.plan.name}</span>
                        <span className={`vis-badge vis-${c.plan.visibility}`}>
                          {c.plan.visibility === "draft" ? "черновик" : "опубликован"}
                        </span>
                      </>
                    ) : (
                      <span className="client-noplan">Нет программы</span>
                    )}
                  </div>
                  <div className="client-meta">
                    {last ? `Последняя тренировка: ${last}` : "Тренировок ещё не было"}
                  </div>
                </div>
                <ChevronRight size={20} className="client-chevron" />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
