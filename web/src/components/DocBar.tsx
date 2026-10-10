import { useRef, useState, type ReactNode } from "react";
import { Account } from "./AuthGate";
import { Download, Share, Star } from "./icons";
import { Monogram } from "./Wordmark";
import Menu from "./Menu";
import RenameInput from "./RenameInput";

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
  onDownload: () => void;
  onHome: () => void;
  onRename: (name: string) => void;
  onShare: () => void;
  presence?: ReactNode; // avatars of who else has it open
};

const mod = navigator.platform.includes("Mac") ? "⌘" : "Ctrl+";

/** Document header: mark, title, status and the menu bar. */
export default function DocBar(p: Props) {
  const [starred, setStarred] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const [renaming, setRenaming] = useState(false);
  const name = p.filename.replace(/\.(xlsx|xlsm|xls)$/i, "");

  return (
    <header className="docbar">
      <button className="docbar-brand" onClick={p.onHome} aria-label="Since: all models">
        <Monogram />
      </button>

      <div className="docbar-main">
        <div className="docbar-title">
          {renaming ? (
            <RenameInput
              className="docbar-rename"
              value={name}
              onDone={(next) => {
                setRenaming(false);
                if (next) p.onRename(next);
              }}
            />
          ) : (
            <h1>
              <button className="docbar-name" onClick={() => setRenaming(true)} title="Rename">
                {name}
              </button>
            </h1>
          )}
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
                { label: "Rename", onSelect: () => setRenaming(true) },
                { label: "Download .xlsx", hint: `${mod}S`, onSelect: p.onDownload },
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
                { label: "Magenta corner: stale assumption", onSelect: () => {}, disabled: true },
              ]}
            />
          </nav>
        </div>
      </div>

      <div className="docbar-end">
        {p.presence}
        <button className="download" onClick={p.onDownload} aria-label="Download .xlsx" title={`Download .xlsx (${mod}S)`}>
          <Download />
        </button>
        <button className="share" onClick={p.onShare}>
          <Share />
          Share
        </button>
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
