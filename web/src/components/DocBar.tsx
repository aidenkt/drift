import { useRef, useState } from "react";
import { Account } from "./AuthGate";
import { Mark, Star } from "./icons";
import Menu from "./Menu";

type Props = {
  filename: string;
  builtOn: string | null;
  stale: number | null; // null: not checked
  total: number;
  showChanges: boolean;
  onToggleChanges: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onImport: (file: File) => void;
  onHome: () => void;
};

const mod = navigator.platform.includes("Mac") ? "⌘" : "Ctrl+";

/** Document header: mark, title, status and the menu bar. */
export default function DocBar(p: Props) {
  const [starred, setStarred] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  return (
    <header className="docbar">
      <button className="docbar-brand" onClick={p.onHome} aria-label="Since: all models">
        <Mark />
        <span className="brand-name">Since</span>
      </button>

      <div className="docbar-main">
        <div className="docbar-title">
          <h1>{p.filename.replace(/\.(xlsx|xlsm|xls)$/i, "")}</h1>
          <button
            className={`star ${starred ? "on" : ""}`}
            aria-pressed={starred}
            aria-label={starred ? "Unstar model" : "Star model"}
            onClick={() => setStarred((s) => !s)}
          >
            <Star filled={starred} />
          </button>
        </div>

        <div className="docbar-sub">
          <span className={`doc-status ${p.stale ? "stale" : ""}`}>
            {p.stale == null ? "Not checked" : p.stale ? `${p.stale} stale of ${p.total}` : `${p.total} current`}
          </span>
          {p.builtOn && <span className="doc-built mono">set {p.builtOn}</span>}
          <nav className="menubar" aria-label="Menu">
            <Menu
              label="File"
              items={[
                { label: "Import .xlsx…", onSelect: () => file.current?.click() },
                "divider",
                { label: "All models", onSelect: p.onHome },
              ]}
            />
            <Menu
              label="Edit"
              items={[
                { label: "Undo", hint: `${mod}Z`, onSelect: p.onUndo },
                { label: "Redo", hint: `${mod}⇧Z`, onSelect: p.onRedo },
              ]}
            />
            <Menu
              label="View"
              items={[{ label: p.showChanges ? "Hide changes" : "Show changes", onSelect: p.onToggleChanges }]}
            />
            <Menu
              label="Help"
              items={[
                { label: "Blue numbers are hardcoded inputs", onSelect: () => {}, disabled: true },
                { label: "Orange corner: stale assumption", onSelect: () => {}, disabled: true },
              ]}
            />
          </nav>
        </div>
      </div>

      <div className="docbar-end">
        <Account />
      </div>

      <input
        ref={file}
        type="file"
        accept=".xlsx,.xlsm,.xls"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) p.onImport(f);
          e.target.value = "";
        }}
      />
    </header>
  );
}
