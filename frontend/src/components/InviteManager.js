import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Copy,
  Ticket,
  Plus,
  RotateCcw,
  Loader2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { toast } from "sonner";
import {
  createInvite,
  listInvites,
  getAdminInvites,
  revokeInvite,
  revokeAdminInvite,
} from "@/api";
import { haptic, hapticNotify } from "@/lib/platform";

const KIND_LABEL = {
  coach_client: "Клиент тренера",
  standalone: "Самостоятельный",
  coach: "Тренер",
};

const PRESET_LABEL = {
  traincee: "Подопечный",
  standalone: "Самостоятельно",
  custom: "Свой набор",
};

const STATUS_LABEL = {
  active: "Активен",
  revoked: "Отозван",
  expired: "Истёк",
};

const fmtDate = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("ru-RU", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch (e) {
    return "—";
  }
};

const errText = (err, fallback) => {
  const d = err && err.response && err.response.data && err.response.data.detail;
  return typeof d === "string" ? d : fallback;
};

/**
 * Переиспользуемый менеджер инвайтов.
 *  - admin:  полный список через GET /admin/invites, создание любого kind
 *  - coach:  только kind=coach_client, список через GET /invites
 *
 * Полностью деградирует, если бэкенд ещё не готов (вкладка просто скрывает
 * список и показывает понятную подсказку).
 */
export default function InviteManager({ admin = false, presetKind = "coach_client" }) {
  const [invites, setInvites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);

  // форма
  const [kind, setKind] = useState(presetKind);
  const [maxUses, setMaxUses] = useState("1");
  const [validDays, setValidDays] = useState("30");
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = admin ? await getAdminInvites() : await listInvites();
      setInvites((data && data.invites) || []);
    } catch (e) {
      setInvites([]);
      setError(
        errText(e, "Инвайты пока недоступны. Функция появится после обновления сервера.")
      );
    } finally {
      setLoading(false);
    }
  }, [admin]);

  useEffect(() => {
    load();
  }, [load]);

  const stats = useMemo(() => {
    const used = invites.reduce((n, i) => n + (i.uses || 0), 0);
    const active = invites.filter((i) => (i.status || "active") === "active").length;
    return { total: invites.length, used, active };
  }, [invites]);

  const submit = async () => {
    if (busy) return;
    setBusy(true);
    haptic("medium");
    try {
      const payload = {
        kind,
        max_uses: Math.max(1, parseInt(maxUses, 10) || 1),
        note: note.trim() || undefined,
      };
      const days = parseInt(validDays, 10);
      if (days > 0) {
        payload.expires_at = new Date(Date.now() + days * 86400000).toISOString();
      }
      const created = await createInvite(payload);
      toast.success(
        created && created.code ? `Код создан: ${created.code}` : "Инвайт создан"
      );
      hapticNotify("success");
      setNote("");
      setShowForm(false);
      await load();
    } catch (e) {
      toast.error(errText(e, "Не удалось создать инвайт"));
      hapticNotify("error");
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (inv) => {
    const id = inv && (inv.id || inv.code);
    if (!id) return;
    // eslint-disable-next-line no-alert
    if (!window.confirm("Отозвать этот инвайт? Код перестанет действовать.")) return;
    try {
      if (admin) await revokeAdminInvite(id);
      else await revokeInvite(id);
      toast.success("Инвайт отозван");
      await load();
    } catch (e) {
      toast.error(errText(e, "Не удалось отозвать инвайт"));
    }
  };

  const copy = async (text) => {
    if (!text) return;
    haptic("light");
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Код скопирован");
    } catch (e) {
      toast.info(text);
    }
  };

  const kindOptions = admin
    ? [
        { value: "coach_client", label: KIND_LABEL.coach_client },
        { value: "standalone", label: KIND_LABEL.standalone },
      ]
    : [{ value: "coach_client", label: KIND_LABEL.coach_client }];

  return (
    <div className="inv-mgr" data-testid="invite-manager">
      <div className="inv-toolbar">
        <div className="inv-toolbar-stats">
          <span data-testid="invite-stat-total">
            Всего: <b>{stats.total}</b>
          </span>
          <span data-testid="invite-stat-active">
            Активных: <b>{stats.active}</b>
          </span>
          <span data-testid="invite-stat-used">
            Использований: <b>{stats.used}</b>
          </span>
        </div>
        <button
          type="button"
          className="adm-btn adm-btn-primary inv-create-toggle"
          onClick={() => setShowForm((v) => !v)}
          data-testid="invite-create-toggle"
        >
          <Plus size={15} /> Создать
          {showForm ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </button>
      </div>

      {showForm ? (
        <div className="inv-form anim-fade-up" data-testid="invite-form">
          {admin ? (
            <label className="adm-field">
              <span>Тип инвайта</span>
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value)}
                data-testid="invite-kind-select"
              >
                {kindOptions.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <div className="inv-form-note">
              Вы создаёте код для клиента тренера. Подопечный получит
              «только просмотр» силовых и самостоятельное заполнение кардио и
              питания.
            </div>
          )}

          <div className="inv-form-row">
            <label className="adm-field">
              <span>Максимум использований</span>
              <input
                type="number"
                min="1"
                value={maxUses}
                onChange={(e) => setMaxUses(e.target.value)}
                data-testid="invite-max-uses"
              />
            </label>
            <label className="adm-field">
              <span>Срок действия, дней</span>
              <input
                type="number"
                min="0"
                value={validDays}
                onChange={(e) => setValidDays(e.target.value)}
                data-testid="invite-valid-days"
              />
            </label>
          </div>

          <label className="adm-field">
            <span>Заметка (для кого)</span>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Напр. «Для Дмитрия, зал на Ленина»"
              maxLength={120}
              data-testid="invite-note"
            />
          </label>

          <button
            type="button"
            className="adm-btn adm-btn-primary adm-btn-block"
            onClick={submit}
            disabled={busy}
            data-testid="invite-submit"
          >
            {busy ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}
            {busy ? "Создаём…" : "Создать инвайт"}
          </button>
        </div>
      ) : null}

      {loading ? (
        <div className="adm-skeleton" data-testid="invite-loading">
          <div className="adm-skel-row" />
          <div className="adm-skel-row" />
          <div className="adm-skel-row" />
        </div>
      ) : error ? (
        <div className="adm-error" data-testid="invite-error">
          <span>{error}</span>
          <button
            type="button"
            className="adm-btn adm-btn-ghost"
            onClick={load}
            data-testid="invite-retry"
          >
            <RotateCcw size={15} /> Повторить
          </button>
        </div>
      ) : invites.length === 0 ? (
        <div className="adm-empty" data-testid="invite-empty">
          <Ticket size={30} />
          <p>Пока нет инвайтов. Создайте первый код.</p>
        </div>
      ) : (
        <div className="inv-list">
          {invites.map((inv) => {
            const status = inv.status || "active";
            const max = inv.max_uses || 1;
            return (
              <div
                className="inv-card"
                key={inv.id || inv.code}
                data-testid={`invite-card-${inv.id || inv.code}`}
              >
                <div className="inv-card-top">
                  <span className="inv-code" data-testid="invite-code">
                    {inv.code || "········"}
                  </span>
                  <span className={`inv-status inv-status-${status}`}>
                    {STATUS_LABEL[status] || status}
                  </span>
                </div>
                <div className="inv-card-meta">
                  <span className="inv-kind">
                    {KIND_LABEL[inv.kind] || inv.kind || "—"}
                    {inv.preset ? ` · ${PRESET_LABEL[inv.preset] || inv.preset}` : ""}
                  </span>
                  <span className="inv-uses">
                    Использовано {inv.uses || 0}/{max}
                  </span>
                  <span className="inv-expires">
                    До {fmtDate(inv.expires_at)}
                  </span>
                </div>
                {inv.note ? <div className="inv-note">{inv.note}</div> : null}
                <div className="inv-card-actions">
                  <button
                    type="button"
                    className="adm-btn adm-btn-ghost"
                    onClick={() => copy(inv.code)}
                    data-testid="invite-copy"
                  >
                    <Copy size={14} /> Копировать
                  </button>
                  {status === "active" ? (
                    <button
                      type="button"
                      className="adm-btn adm-btn-danger"
                      onClick={() => revoke(inv)}
                      data-testid="invite-revoke"
                    >
                      Отозвать
                    </button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
