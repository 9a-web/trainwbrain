import React, { useState, useEffect } from 'react';
import { X, TrendingUp, Award, Calendar, Activity } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import api from '../api';
import './ExerciseHistoryModal.css';

function ExerciseHistoryModal({ slug, athleteId, athleteName, onClose, onSelectWeight }) {
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const response = await api.get(`/exercises/${slug}/history/${athleteId}`);
        if (!cancelled) {
          setHistory(response.data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError('Не удалось загрузить историю');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [slug, athleteId]);

  const handleSelectWeight = (weight) => {
    if (onSelectWeight) {
      onSelectWeight(weight);
    }
    onClose();
  };

  if (loading) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-container history-modal" onClick={(e) => e.stopPropagation()}>
          <div className="loading-spinner">
            <div className="spinner"></div>
            <p>Загрузка истории...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error || !history) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-container history-modal" onClick={(e) => e.stopPropagation()}>
          <div className="error-state">
            <p>{error || 'Нет данных'}</p>
            <button className="btn-primary" onClick={onClose}>Закрыть</button>
          </div>
        </div>
      </div>
    );
  }

  const entries = Array.isArray(history.history) ? history.history : [];

  if (entries.length === 0) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-container history-modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2>{history.exercise_name}</h2>
            <button className="close-btn" onClick={onClose} aria-label="Закрыть">
              <X size={24} />
            </button>
          </div>
          <div className="empty-state">
            <Activity size={48} className="empty-icon" />
            <p>Упражнение ещё не выполнялось</p>
            <button className="btn-secondary" onClick={onClose}>Закрыть</button>
          </div>
        </div>
      </div>
    );
  }

  // Подготовить данные для графика
  const chartData = entries.slice().reverse().map(entry => ({
    date: new Date(entry.date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }),
    weight: entry.max_weight,
    volume: entry.total_volume
  }));

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-container history-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <div>
            <h2>{history.exercise_name}</h2>
            {athleteName && <p className="athlete-name">{athleteName}</p>}
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Закрыть">
            <X size={24} />
          </button>
        </div>

        {/* Stats Cards */}
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon weight">
              <Award size={20} />
            </div>
            <div className="stat-content">
              <span className="stat-label">Макс. вес</span>
              <span className="stat-value">{history.max_weight} кг</span>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon reps">
              <TrendingUp size={20} />
            </div>
            <div className="stat-content">
              <span className="stat-label">Макс. повторения</span>
              <span className="stat-value">{history.max_reps}</span>
            </div>
          </div>

          {history.estimated_1rm && (
            <div className="stat-card">
              <div className="stat-icon estimate">
                <Activity size={20} />
              </div>
              <div className="stat-content">
                <span className="stat-label">Расчётный 1RM</span>
                <span className="stat-value">{history.estimated_1rm} кг</span>
              </div>
            </div>
          )}

          <div className="stat-card">
            <div className="stat-icon volume">
              <Calendar size={20} />
            </div>
            <div className="stat-content">
              <span className="stat-label">Объём (всего)</span>
              <span className="stat-value">{(history.total_volume || 0).toLocaleString()} кг</span>
            </div>
          </div>
        </div>

        {/* Chart */}
        <div className="chart-section">
          <h3>Прогрессия веса</h3>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis 
                  dataKey="date" 
                  stroke="#6b7280"
                  style={{ fontSize: '12px' }}
                />
                <YAxis 
                  stroke="#6b7280"
                  style={{ fontSize: '12px' }}
                  label={{ value: 'кг', angle: -90, position: 'insideLeft' }}
                />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#fff',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                    padding: '8px 12px'
                  }}
                  formatter={(value) => [`${value} кг`, 'Вес']}
                />
                <Line 
                  type="monotone" 
                  dataKey="weight" 
                  stroke="#3b82f6" 
                  strokeWidth={3}
                  dot={{ fill: '#3b82f6', r: 4 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* History List */}
        <div className="history-section">
          <h3>История выполнений</h3>
          <div className="history-list">
            {entries.map((entry, idx) => (
              <div key={idx} className="history-entry">
                <div className="entry-header">
                  <div className="entry-date">
                    <Calendar size={16} />
                    <span>{new Date(entry.date).toLocaleDateString('ru-RU', {
                      day: 'numeric',
                      month: 'long',
                      year: 'numeric'
                    })}</span>
                  </div>
                  {onSelectWeight && (
                    <button 
                      className="btn-use-weight" 
                      onClick={() => handleSelectWeight(entry.max_weight)}
                    >
                      Использовать {entry.max_weight} кг
                    </button>
                  )}
                </div>
                
                {entry.session_title && (
                  <p className="session-title">{entry.session_title}</p>
                )}
                
                <div className="entry-sets">
                  {entry.sets.map((set, setIdx) => (
                    <div key={setIdx} className="set-badge">
                      <span className="set-weight">{set.weight} кг</span>
                      <span className="set-separator">×</span>
                      <span className="set-reps">{set.reps}</span>
                    </div>
                  ))}
                </div>
                
                <div className="entry-meta">
                  <span>Макс: {entry.max_weight} кг</span>
                  <span>Объём: {entry.total_volume} кг</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ExerciseHistoryModal;
