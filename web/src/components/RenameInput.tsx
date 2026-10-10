import { useRef, useState } from "react";

/** Inline name field: Enter or clicking away saves, Escape cancels (onDone with null). */
export default function RenameInput({ value, className, onDone }: { value: string; className?: string; onDone: (name: string | null) => void }) {
  const [text, setText] = useState(value);
  const done = useRef(false);
  const finish = (name: string | null) => {
    if (done.current) return;
    done.current = true;
    const next = name?.trim().replace(/\.(xlsx|xlsm|xls)$/i, "");
    onDone(next && next !== value ? next : null);
  };
  return (
    <input
      className={className}
      value={text}
      autoFocus
      aria-label="Model name"
      onFocus={(ev) => ev.target.select()}
      onChange={(ev) => setText(ev.target.value)}
      onClick={(ev) => ev.stopPropagation()}
      onKeyDown={(ev) => {
        ev.stopPropagation();
        if (ev.key === "Enter") finish(text);
        if (ev.key === "Escape") finish(null);
      }}
      onBlur={() => finish(text)}
    />
  );
}
