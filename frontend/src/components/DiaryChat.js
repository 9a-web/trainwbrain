import React, { useState, useRef, useEffect } from "react";
import { diaryChat } from "@/api";
import "@/components/Diary.css";

// Чат с персональным ИИ-тренером (многоходовой, thread_id сохраняется).
const DiaryChat = ({ open, onClose }) => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState(null);
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    if (endRef.current) endRef.current.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  if (!open) return null;

  const send = async () => {
    const msg = input.trim();
    if (!msg || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: msg }]);
    setBusy(true);
    try {
      const res = await diaryChat(msg, threadId);
      setThreadId(res.thread_id);
      setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: "Не получилось ответить. Попробуй ещё раз." },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="diary-modal-backdrop" onClick={onClose} data-testid="diary-chat">
      <div className="diary-modal" onClick={(e) => e.stopPropagation()}>
        <div className="diary-modal-head">
          <h3>🤖 ИИ-тренер</h3>
          <button className="diary-modal-close" onClick={onClose} data-testid="diary-chat-close">
            ×
          </button>
        </div>

        <div className="chat-msgs">
          {messages.length === 0 && (
            <div className="chat-msg assistant">
              Привет! Я твой тренер. Спроси что угодно: как прогрессировать, что делать при усталости,
              какие упражнения добавить.
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`chat-msg ${m.role}`}>
              {m.content}
            </div>
          ))}
          {busy && (
            <div className="chat-msg assistant">
              <span className="diary-spinner" /> думаю...
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div className="chat-input-row">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Напиши тренеру..."
            disabled={busy}
            data-testid="diary-chat-input"
          />
          <button
            className="diary-btn diary-btn-primary"
            style={{ width: "auto", padding: "12px 18px" }}
            onClick={send}
            disabled={busy}
            data-testid="diary-chat-send"
          >
            →
          </button>
        </div>
      </div>
    </div>
  );
};

export default DiaryChat;
