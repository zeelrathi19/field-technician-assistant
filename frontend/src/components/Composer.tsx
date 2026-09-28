import type { KeyboardEvent } from "react";
import type { SessionState } from "../types";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSend: (text: string) => void;
  disabled: boolean;
  maxChars: number;
  context: SessionState | null;
}

export function Composer({ value, onChange, onSend, disabled, maxChars, context }: Props) {
  const text = value.trim();
  const over = value.length > maxChars;
  const submit = () => {
    if (!text || disabled || over) return;
    onSend(text);
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };
  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div className="context-line" aria-live="polite">
        {context?.active_work_order_id ? (
          <>
            Talking about <strong>{context.active_work_order_id}</strong> — “it” refers to this work order.
          </>
        ) : context?.candidates?.length ? (
          <>Several work orders mentioned ({context.candidates.join(", ")}) — name one to act on it.</>
        ) : (
          <>No work order selected — include an ID like WO-003 to act on one.</>
        )}
      </div>
      <label htmlFor="msg" className="sr-only">
        Message
      </label>
      <div className="composer-row">
        <textarea
          id="msg"
          rows={2}
          value={value}
          placeholder="Ask a question or give an instruction… (Enter to send, Shift+Enter for a new line)"
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKey}
          aria-invalid={over}
          aria-describedby="msg-help"
        />
        <button type="submit" className="send" disabled={disabled || !text || over}>
          {disabled ? "Working…" : "Send"}
        </button>
      </div>
      <div id="msg-help" className={`counter ${over ? "over" : ""}`}>
        {over ? `Too long: ${value.length}/${maxChars} characters` : value.length > maxChars * 0.8 ? `${value.length}/${maxChars}` : ""}
      </div>
    </form>
  );
}
