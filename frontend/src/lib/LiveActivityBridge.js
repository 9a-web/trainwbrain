/**
 * LiveActivityBridge — JavaScript API для управления Dynamic Island
 * через нативный Capacitor плагин LiveActivityPlugin.
 *
 * Доступен в Capacitor-сборке (iOS 16.1+).
 * На вебе/PWA все методы — no-op (возвращают fallback-значения).
 *
 * Использование (import):
 *   import { startLiveActivity, updateLiveActivity, endLiveActivity } from '@/lib/LiveActivityBridge';
 *
 *   // В компоненте тренировки:
 *   await startLiveActivity({
 *     sessionId: 'some-uuid',
 *     exerciseName: 'Жим лёжа',
 *     setsCompleted: 2,
 *     totalSets: 5,
 *     repScheme: '5x5',
 *     weight: '80 кг',
 *     status: 'active'
 *   });
 */

// Пытаемся загрузить Capacitor плагин при первом обращении.
// В вебе/PWA Capacitor просто не зарегистрирован — будет no-op.
function getLiveActivityPlugin() {
  try {
    const { registerPlugin } = require('@capacitor/core');
    return registerPlugin('LiveActivityPlugin');
  } catch (e) {
    return null;
  }
}

/**
 * Проверить, поддерживаются ли Live Activities на устройстве.
 * @returns {Promise<{available: boolean, supportsDynamicIsland?: boolean, reason?: string}>}
 */
export async function isLiveActivityAvailable() {
  const plugin = getLiveActivityPlugin();
  if (!plugin) {
    return { available: false, reason: 'capacitor_not_loaded' };
  }
  try {
    return await plugin.isAvailable();
  } catch (e) {
    return { available: false, reason: e.message };
  }
}

/**
 * Запустить Live Activity для тренировки.
 * @param {object} params
 * @param {string} params.sessionId — ID сессии (для связи с WebSocket)
 * @param {string} params.exerciseName — название упражнения
 * @param {number} params.setsCompleted — выполнено подходов
 * @param {number} params.totalSets — всего подходов
 * @param {string} params.repScheme — схема повторений (например "5x5")
 * @param {string} params.weight — вес (например "80 кг")
 * @param {string} params.status — статус: "active" | "rest" | "finished"
 * @returns {Promise<{activityId: string}>}
 */
export async function startLiveActivity(params) {
  const plugin = getLiveActivityPlugin();
  if (!plugin) {
    return { activityId: null };
  }
  try {
    return await plugin.start(params);
  } catch (e) {
    console.warn('[LiveActivityBridge] start failed:', e.message);
    return { activityId: null };
  }
}

/**
 * Обновить текущую Live Activity.
 * @param {object} params — те же поля, что и в start (все optional)
 * @returns {Promise<{updated: boolean}>}
 */
export async function updateLiveActivity(params) {
  const plugin = getLiveActivityPlugin();
  if (!plugin) {
    return { updated: false };
  }
  try {
    return await plugin.update(params);
  } catch (e) {
    console.warn('[LiveActivityBridge] update failed:', e.message);
    return { updated: false };
  }
}

/**
 * Завершить Live Activity.
 * @param {'immediate'|'after'|'default'} [dismissalPolicy='after']
 * @returns {Promise<{ended: boolean}>}
 */
export async function endLiveActivity(dismissalPolicy = 'after') {
  const plugin = getLiveActivityPlugin();
  if (!plugin) {
    return { ended: false };
  }
  try {
    return await plugin.end({ dismissalPolicy });
  } catch (e) {
    console.warn('[LiveActivityBridge] end failed:', e.message);
    return { ended: false };
  }
}

/**
 * Получить ID текущей активной Live Activity (если есть).
 * @returns {Promise<{activityId: string|null}>}
 */
export async function getActiveActivityId() {
  const plugin = getLiveActivityPlugin();
  if (!plugin) {
    return { activityId: null };
  }
  try {
    return await plugin.getActiveActivityId();
  } catch (e) {
    return { activityId: null };
  }
}

export default {
  isLiveActivityAvailable,
  startLiveActivity,
  updateLiveActivity,
  endLiveActivity,
  getActiveActivityId,
};