import { useEffect, useRef, useState } from "react";
import { sendChat, type ChatUpdate } from "../api";
import { useI18n } from "../I18nProvider";

interface Msg {
  role: "user" | "assistant";
  content: string;
}

function BubbleIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 5h16v11H9l-5 4V5z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * Persistent floating assistant. Always available during a run; holds a real
 * multi-turn conversation and, depending on the message, edits the currently
 * editable artifact (applied via onUpdates) or just answers.
 */
export function FloatingChat({
  runId,
  viewing,
  onUpdates,
}: {
  runId: string;
  viewing: string;
  onUpdates: (updates: ChatUpdate[]) => void;
}) {
  const { lang, t } = useI18n();
  const [open, setOpen] = useState(true);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const threadRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight });
  }, [messages, busy]);

  const send = async () => {
    const message = text.trim();
    if (!message || busy) return;
    setMessages((m) => [...m, { role: "user", content: message }]);
    setText("");
    setBusy(true);
    try {
      const res = await sendChat(runId, message, viewing, lang);
      setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
      if (res.updates.length) onUpdates(res.updates);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", content: `⚠ ${String(e)}` }]);
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        className="chat-fab"
        onClick={() => setOpen(true)}
        aria-label={t("chat.title")}
      >
        <BubbleIcon />
      </button>
    );
  }

  return (
    <div className="chat-panel" role="dialog" aria-label={t("chat.title")}>
      <div className="chat-header">
        <span className="chat-header-title">
          <BubbleIcon /> {t("chat.title")}
        </span>
        <button type="button" className="chat-close" onClick={() => setOpen(false)} aria-label="—">
          –
        </button>
      </div>
      <div className="chat-thread" ref={threadRef}>
        {messages.length === 0 && <div className="chat-hint">{t("chat.hint")}</div>}
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg chat-${m.role}`}>
            {m.content}
          </div>
        ))}
        {busy && (
          <div className="chat-msg chat-assistant chat-typing">
            <span className="chat-dot" />
            <span className="chat-dot" />
            <span className="chat-dot" />
          </div>
        )}
      </div>
      <div className="chat-input-row">
        <textarea
          className="chat-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("chat.placeholder")}
          rows={1}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button
          type="button"
          className="chat-send"
          disabled={busy || !text.trim()}
          onClick={send}
          aria-label={t("chat.send")}
        >
          ↑
        </button>
      </div>
    </div>
  );
}
