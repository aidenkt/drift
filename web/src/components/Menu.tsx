import { useEffect, useRef, useState, type ReactNode } from "react";

export type MenuItem =
  | { label: string; onSelect: () => void; hint?: string; disabled?: boolean }
  | "divider";

/** Text menu (File, Edit, ...) or a toolbar dropdown when `trigger` is given. */
export default function Menu({ label, items, trigger, className }: { label: string; items: MenuItem[]; trigger?: ReactNode; className?: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <div className={`menu ${className ?? ""}`} ref={root}>
      <button
        className={trigger ? "tb-btn tb-drop" : "menu-trigger"}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={trigger ? label : undefined}
        onClick={() => setOpen((o) => !o)}
      >
        {trigger ?? label}
      </button>
      {open && (
        <div className="menu-pop" role="menu">
          {items.map((item, i) =>
            item === "divider" ? (
              <hr key={i} />
            ) : (
              <button
                key={item.label}
                role="menuitem"
                disabled={item.disabled}
                onClick={() => {
                  setOpen(false);
                  item.onSelect();
                }}
              >
                <span>{item.label}</span>
                {item.hint && <span className="menu-hint mono">{item.hint}</span>}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  );
}
