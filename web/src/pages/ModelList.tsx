import { useCallback, useMemo, useRef, useState, type DragEvent, type MouseEvent, type ReactNode } from "react";
import { Account } from "../components/AuthGate";
import { ContextMenu, type MenuItem } from "../components/Menu";
import RenameInput from "../components/RenameInput";
import ShareDialog from "../components/ShareDialog";
import SheetThumb from "../components/SheetThumb";
import Wordmark from "../components/Wordmark";
import { Folder as FolderIcon, Plus, Table } from "lucide-react";
import { SAMPLE_TIMELINE } from "../data/timeline";
import { deltaMoney, editedAt, shortDate, value } from "../lib/format";
import { eventsFromReport } from "../lib/reportTimeline";
import { xlsxBytes, xlsxName, type Book } from "../lib/workbook";
import { colorFor, createShared, initials, me, type SharedDoc } from "../lib/collab";
import { createFolder, deleteFolder, loadFolders, loadPlacement, moveFolder, pathTo, place, renameFolder, type Folder } from "../lib/folders";
import type { Report } from "../types";

/** A workbook on the home page: a checked model, or a file imported in this browser. */
export type Entry = {
  key: string;
  filename: string;
  builtOn: string | null;
  added: string | null; // ISO time, imported files only
  edited: string | null; // ISO time: an edit made here, else when the file was last saved
  book: Book;
  report: Report | null;
  doc?: SharedDoc; // shared through the engine
  blank?: boolean; // made here with New → Blank spreadsheet, not imported
};

type Props = {
  entries: Entry[] | null;
  onOpen: (e: Entry, startEvent?: string) => void;
  onImport: (file: File) => void;
  onRemove: (e: Entry) => void;
  onRename: (e: Entry, name: string) => void;
  onDownload: (e: Entry) => void;
  onNewBlank: (folder: string | null) => void;
  /** Shared from the home page: uploaded for the first time, or its access changed. */
  onShared: (e: Entry, doc: SharedDoc) => void;
};

const staleCount = (e: Entry) => e.report?.constants.filter((c) => c.check?.status === "stale").length ?? 0;
const sharedLabel = (d: SharedDoc) =>
  d.owner.email === me().email
    ? `shared with ${d.members.length} ${d.members.length === 1 ? "person" : "people"}`
    : `shared with you · can ${d.role === "viewer" ? "view" : "edit"}`;
/** Shared with you by someone else (rather than shared by you). */
const incoming = (e: Entry) => !!e.doc && e.doc.role !== "owner";
const title = (filename: string) => filename.replace(/\.(xlsx|xlsm|xls)$/i, "");

// drag payloads: a model card or a folder tile
const DRAG_KEY = "text/x-since-model";
const DRAG_FOLDER = "text/x-since-folder";

export default function ModelList({ entries, onOpen, onImport, onRemove, onRename, onDownload, onNewBlank, onShared }: Props) {
  const [query, setQuery] = useState("");
  const [layout, setLayout] = useState<"grid" | "list">("grid");
  const file = useRef<HTMLInputElement>(null);
  const [menu, setMenu] = useState<{ x: number; y: number; entry: Entry } | null>(null);
  const closeMenu = useCallback(() => setMenu(null), []);
  const [renaming, setRenaming] = useState<string | null>(null); // entry key
  const [sharingKey, setSharingKey] = useState<string | null>(null);
  // looked up each render so the dialog sees the access list as it changes
  const sharing = entries?.find((e) => e.key === sharingKey) ?? null;

  /* ---------- folders ---------- */
  const [folders, setFolders] = useState<Folder[]>(loadFolders);
  const [placement, setPlacement] = useState<Record<string, string>>(loadPlacement);
  const [current, setCurrent] = useState<string | null>(null);
  const [renamingFolder, setRenamingFolder] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null); // folder id, or "top"
  const [folderMenu, setFolderMenu] = useState<{ x: number; y: number; folder: Folder } | null>(null);
  const [newMenu, setNewMenu] = useState<{ x: number; y: number } | null>(null);
  const refresh = () => {
    setFolders(loadFolders());
    setPlacement(loadPlacement());
  };
  const folderOf = (key: string) => (folders.some((f) => f.id === placement[key]) ? placement[key] : null);
  const path = pathTo(folders, current);
  const fullName = (f: Folder) => pathTo(folders, f.id).map((x) => x.name).join(" / ");
  const countIn = (id: string) =>
    (entries ?? []).filter((e) => folderOf(e.key) === id).length + folders.filter((f) => f.parent === id).length;

  const newFolder = () => {
    const f = createFolder("Untitled folder", current);
    refresh();
    setRenamingFolder(f.id);
  };
  const moveTo = (key: string, folder: string | null) => {
    place(key, folder);
    refresh();
  };
  // a model card or folder tile dropped on a folder (or on "Models", the top level)
  const dropProps = (target: string | null) => ({
    onDragOver: (ev: DragEvent) => {
      if (![DRAG_KEY, DRAG_FOLDER].some((t) => ev.dataTransfer.types.includes(t))) return;
      ev.preventDefault();
      ev.stopPropagation();
      setDropTarget(target ?? "top");
    },
    onDragLeave: () => setDropTarget(null),
    onDrop: (ev: DragEvent) => {
      ev.preventDefault();
      ev.stopPropagation(); // not the page-wide file drop
      setDropTarget(null);
      const key = ev.dataTransfer.getData(DRAG_KEY);
      const folder = ev.dataTransfer.getData(DRAG_FOLDER);
      if (key) place(key, target);
      if (folder && folder !== target) moveFolder(folder, target);
      refresh();
    },
  });
  const folderItems = (f: Folder): MenuItem[] => [
    { label: "Open", onSelect: () => setCurrent(f.id) },
    { label: "Rename", onSelect: () => setRenamingFolder(f.id) },
    "divider",
    {
      label: "Delete folder",
      onSelect: () => {
        deleteFolder(f.id);
        refresh();
      },
    },
  ];
  const moveItems = (e: Entry): MenuItem[] => {
    const here = folderOf(e.key);
    const targets: { label: string; id: string | null }[] = [
      { label: "Models", id: null },
      ...folders.map((f) => ({ label: fullName(f), id: f.id })).sort((a, b) => a.label.localeCompare(b.label)),
    ];
    return targets.filter((t) => t.id !== here).map((t) => ({ label: `Move to ${t.label}`, onSelect: () => moveTo(e.key, t.id) }));
  };

  const openMenu = (ev: MouseEvent, entry: Entry) => {
    ev.preventDefault();
    setMenu({ x: ev.clientX, y: ev.clientY, entry });
  };
  const menuItems = (e: Entry): MenuItem[] => [
    { label: "Open", onSelect: () => onOpen(e) },
    { label: "Rename", onSelect: () => setRenaming(e.key) },
    { label: "Share…", onSelect: () => setSharingKey(e.key) },
    { label: "Download .xlsx", onSelect: () => onDownload(e) },
    ...(folders.length || folderOf(e.key) ? ["divider" as const, ...moveItems(e)] : []),
    ...(e.report ? [] : ["divider" as const, { label: "Remove", onSelect: () => onRemove(e) }]),
  ];
  const nameField = (e: Entry, className: string) => (
    <RenameInput
      className={className}
      value={title(e.filename)}
      onDone={(name) => {
        setRenaming(null);
        if (name) onRename(e, name);
      }}
    />
  );

  // searching looks in every folder; otherwise show what's in the folder you're in
  const q = query.trim().toLowerCase();
  const shown = (entries ?? []).filter((e) =>
    q ? e.filename.toLowerCase().includes(q) : folderOf(e.key) === current && !(current === null && incoming(e) && !placement[e.key]),
  );
  // shared with you and not filed in one of your folders: its own section on the home page
  const sharedWithMe = (entries ?? []).filter((e) => incoming(e) && !folderOf(e.key));
  const shownFolders = folders
    .filter((f) => (q ? f.name.toLowerCase().includes(q) : f.parent === current))
    .sort((a, b) => a.name.localeCompare(b.name));
  const stale = (entries ?? []).reduce((n, e) => n + staleCount(e), 0);

  // the stale assumptions with the biggest dollar effect, across checked models
  const attention = useMemo(() => {
    // the case study keeps the sample timeline; any other report is read as the engine wrote it
    return (entries ?? [])
      .flatMap((entry) =>
        (entry.report?.model_id === "case-study" ? SAMPLE_TIMELINE : entry.report ? eventsFromReport(entry.report) : []).map((ev) => ({ ev, entry })),
      )
      .filter(({ ev }) => ev.status === "stale" && ev.state && ev.impact.length)
      .map(({ ev, entry }) => ({
        ev,
        top: [...ev.impact].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))[0],
        entry,
      }))
      .sort((a, b) => Math.abs(b.top.delta) - Math.abs(a.top.delta))
      .slice(0, 3);
  }, [entries]);

  /** One model as a card: the sheet preview, its name and status. */
  const card = (e: Entry) => (
    <article
      key={e.key}
      className="model-card"
      onContextMenu={(ev) => openMenu(ev, e)}
      draggable={renaming !== e.key}
      onDragStart={(ev) => ev.dataTransfer.setData(DRAG_KEY, e.key)}
    >
      {/* a div while renaming: the name field can't sit inside a button */}
      <CardOpen renaming={renaming === e.key} onClick={() => onOpen(e)} label={`Open ${e.filename}`}>
        <SheetThumb book={e.book} report={e.report} />
      {incoming(e) && (
        <span className="card-owner avatar" style={{ background: colorFor(e.doc!.owner.email) }} title={`Shared by ${e.doc!.owner.name}`}>
          {initials(e.doc!.owner.name)}
        </span>
      )}
        <span className="card-foot">
          <span className="card-icon" aria-hidden>
            <Table size={14} strokeWidth={1.75} absoluteStrokeWidth />
          </span>
          {renaming === e.key ? nameField(e, "card-name card-rename") : <span className="card-name">{title(e.filename)}</span>}
          <span className="card-meta mono">
            {e.report ? (
              <>
                {staleCount(e) > 0 ? <span className="stale-text">{staleCount(e)} stale</span> : "all current"} · set {e.builtOn}
              </>
            ) : e.doc ? (
              <>{e.doc.role === "owner" ? "yours" : `from ${e.doc.owner.name}`} · not checked</>
            ) : (
              <>{e.blank ? "created" : "imported"} {e.added ? shortDate(e.added.slice(0, 10)) : ""} · not checked</>
            )}
          </span>
          {e.doc && <span className="card-shared mono">{sharedLabel(e.doc)}</span>}
        </span>
      </CardOpen>
      {!e.report && !e.doc && renaming !== e.key && (
        <button className="card-remove" onClick={() => onRemove(e)} aria-label={`Remove ${e.filename}`}>
          ×
        </button>
      )}
    </article>
  );

  return (
    <div className="page home">
      <header className="bar home-bar">
        <Wordmark variant="plain" />
        <input
          className="home-search"
          type="search"
          placeholder="Search models"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search models"
        />
        <span className="bar-spacer" />
        <button
          className="btn new-btn"
          aria-haspopup="menu"
          aria-expanded={!!newMenu}
          onClick={(ev) => {
            const r = ev.currentTarget.getBoundingClientRect();
            setNewMenu(newMenu ? null : { x: r.right - 200, y: r.bottom + 6 });
          }}
        >
          <Plus size={15} strokeWidth={2.25} aria-hidden />
          New
        </button>
        <Account />
      </header>

      <main className="home-main">
        {attention.length > 0 && current === null && !q && (
          <section className="attention" aria-labelledby="attention-h">
            <div className="attention-head">
              <h2 id="attention-h">Needs attention</h2>
              <span className="mono muted">
                <span className="stale-text">{stale}</span> stale across {entries?.filter((e) => e.report).length} checked model
                {entries && entries.filter((e) => e.report).length === 1 ? "" : "s"}
              </span>
            </div>
            <div className="attention-row">
              {attention.map(({ ev, top, entry }) => (
                <button key={`${entry.key}:${ev.id}`} className="attn-card" onClick={() => onOpen(entry, ev.id)}>
                  <span className="attn-label">{ev.state!.label}</span>
                  <span className="attn-values mono">
                    <span className="input">{value(ev.state!.model, ev.state!.unit)}</span>
                    <span className="muted">→</span>
                    <span>{ev.state!.live != null ? value(ev.state!.live, ev.state!.unit) : "—"}</span>
                    <span className="stale-text">{ev.state!.change}</span>
                  </span>
                  <span className="attn-effect mono">{deltaMoney(top.delta)}</span>
                  <span className="attn-meta mono muted">
                    {top.label} · {ev.cells[0]} · {title(entry.filename)}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        {current === null && !q && entries !== null && (
          <section aria-labelledby="shared-h">
            <div className="models-head">
              <h2 id="shared-h">Shared with me</h2>
              {sharedWithMe.length > 0 && <span className="mono muted">{sharedWithMe.length}</span>}
            </div>
            {sharedWithMe.length ? (
              <div className="model-grid">{sharedWithMe.map(card)}</div>
            ) : (
              <p className="hint shared-empty">
                Nothing yet. When someone shares a model with <span className="mono">{me().email}</span>, it shows up here.
              </p>
            )}
          </section>
        )}

        <section aria-labelledby="models-h">
          <div className="models-head">
            <nav className="crumbs" aria-label="Folder">
              <h2 id="models-h">
                <button className={`crumb ${dropTarget === "top" ? "drop" : ""}`} onClick={() => setCurrent(null)} {...dropProps(null)}>
                  Models
                </button>
              </h2>
              {path.map((f) => (
                <span key={f.id} className="crumb-step">
                  <span className="muted" aria-hidden>
                    ›
                  </span>
                  <button
                    className={`crumb ${dropTarget === f.id ? "drop" : ""}`}
                    onClick={() => setCurrent(f.id)}
                    aria-current={f.id === current ? "page" : undefined}
                    {...dropProps(f.id)}
                  >
                    {f.name}
                  </button>
                </span>
              ))}
              {q && <span className="muted crumb-note">· results in all folders</span>}
            </nav>
            <span className="bar-spacer" />
            <div className="seg" role="group" aria-label="Layout">
              <button aria-pressed={layout === "grid"} onClick={() => setLayout("grid")}>
                Grid
              </button>
              <button aria-pressed={layout === "list"} onClick={() => setLayout("list")}>
                List
              </button>
            </div>
          </div>

          {entries === null ? (
            <p className="hint">Loading models…</p>
          ) : layout === "grid" ? (
            <>
              {shownFolders.length > 0 && (
                <div className="folder-grid">
                  {shownFolders.map((f) => (
                    <article
                      key={f.id}
                      className={`folder-card ${dropTarget === f.id ? "drop" : ""}`}
                      draggable={renamingFolder !== f.id}
                      onDragStart={(ev) => ev.dataTransfer.setData(DRAG_FOLDER, f.id)}
                      onContextMenu={(ev) => {
                        ev.preventDefault();
                        setFolderMenu({ x: ev.clientX, y: ev.clientY, folder: f });
                      }}
                      {...dropProps(f.id)}
                    >
                      <FolderIcon className="folder-icon" size={22} strokeWidth={1.75} aria-hidden />
                      {renamingFolder === f.id ? (
                        <RenameInput
                          className="folder-name card-rename"
                          value={f.name}
                          onDone={(name) => {
                            setRenamingFolder(null);
                            if (name) renameFolder(f.id, name);
                            refresh();
                          }}
                        />
                      ) : (
                        <button className="folder-open" onClick={() => setCurrent(f.id)} onDoubleClick={() => setRenamingFolder(f.id)}>
                          <span className="folder-name">{f.name}</span>
                          <span className="folder-count mono">{q ? fullName(f) : `${countIn(f.id)} item${countIn(f.id) === 1 ? "" : "s"}`}</span>
                        </button>
                      )}
                    </article>
                  ))}
                </div>
              )}
              <div className="model-grid">
                {!q && (
                  <button className="model-card add-card" onClick={() => onNewBlank(current)}>
                    <span className="add-plus" aria-hidden>
                      +
                    </span>
                    <span>Blank spreadsheet</span>
                    <span className="muted small">or drop an .xlsx anywhere</span>
                  </button>
                )}
                {shown.map(card)}
              </div>
            </>
          ) : (
            <table className="model-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th className="mt-status">Status</th>
                  <th className="mt-num">Constants</th>
                  <th className="mt-date">Last edited</th>
                </tr>
              </thead>
              <tbody>
                {shownFolders.map((f) => (
                  <tr key={f.id} className={`mt-folder ${dropTarget === f.id ? "drop" : ""}`} onClick={() => setCurrent(f.id)} {...dropProps(f.id)}>
                    <td colSpan={4}>
                      <span className="mt-name">
                        <FolderIcon className="folder-icon" size={16} strokeWidth={1.75} aria-hidden />
                        <span className="mt-title">{f.name}</span>
                        <span className="mt-sub mono">{q ? fullName(f) : `${countIn(f.id)} items`}</span>
                      </span>
                    </td>
                  </tr>
                ))}
                {shown.map((e) => {
                  const n = staleCount(e);
                  return (
                    <tr
                      key={e.key}
                      draggable
                      onDragStart={(ev) => ev.dataTransfer.setData(DRAG_KEY, e.key)}
                      onClick={() => renaming !== e.key && onOpen(e)}
                      onContextMenu={(ev) => openMenu(ev, e)}
                      tabIndex={0}
                      onKeyDown={(k) => k.key === "Enter" && k.target === k.currentTarget && onOpen(e)}
                    >
                      <td>
                        <span className="mt-name">
                          <span className="card-icon" aria-hidden>
                            <Table size={14} strokeWidth={1.75} absoluteStrokeWidth />
                          </span>
                          {renaming === e.key ? nameField(e, "mt-title card-rename") : <span className="mt-title">{title(e.filename)}</span>}
                          <span className="mt-sub mono">{e.report ? `assumptions set ${e.builtOn ? shortDate(e.builtOn) : "—"}` : e.filename}</span>
                          {!e.report && (
                            <button
                              className="mt-remove"
                              onClick={(ev) => {
                                ev.stopPropagation();
                                onRemove(e);
                              }}
                              aria-label={`Remove ${e.filename}`}
                            >
                              ×
                            </button>
                          )}
                        </span>
                      </td>
                      <td className="mt-status">
                        {!e.report ? (
                          <span className="mt-pill">Not checked</span>
                        ) : n ? (
                          <span className="mt-pill stale">{n} stale</span>
                        ) : (
                          <span className="mt-pill fresh">All current</span>
                        )}
                      </td>
                      <td className="mt-num mono">{e.report ? e.report.constants.length : <span className="muted">—</span>}</td>
                      <td className="mt-date" title={e.edited ? new Date(e.edited).toLocaleString() : undefined}>
                        {e.edited ? editedAt(e.edited) : <span className="muted">—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          {entries !== null && shown.length === 0 && shownFolders.length === 0 && (
            <p className="hint">{q ? `Nothing matches “${query}”.` : "This folder is empty. Drag models here, or create a blank spreadsheet."}</p>
          )}
        </section>
      </main>

      {menu && <ContextMenu x={menu.x} y={menu.y} items={menuItems(menu.entry)} onClose={closeMenu} />}
      {sharing && (
        <ShareDialog
          filename={sharing.filename}
          doc={sharing.doc ?? null}
          ensureDoc={async () => {
            if (sharing.doc) return sharing.doc;
            const doc = await createShared(xlsxBytes(sharing.book), xlsxName(sharing.filename));
            onShared(sharing, doc);
            return doc;
          }}
          onChange={(doc) => onShared(sharing, doc)}
          onClose={() => setSharingKey(null)}
        />
      )}
      {folderMenu && (
        <ContextMenu x={folderMenu.x} y={folderMenu.y} items={folderItems(folderMenu.folder)} onClose={() => setFolderMenu(null)} />
      )}
      {newMenu && (
        <ContextMenu
          x={newMenu.x}
          y={newMenu.y}
          onClose={() => setNewMenu(null)}
          items={[
            { label: "Blank spreadsheet", onSelect: () => onNewBlank(current) },
            { label: "Folder", onSelect: newFolder },
            "divider",
            { label: "Import .xlsx…", onSelect: () => file.current?.click() },
          ]}
        />
      )}

      <input
        ref={file}
        type="file"
        accept=".xlsx,.xlsm,.xls"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onImport(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}

function CardOpen({ renaming, onClick, label, children }: { renaming: boolean; onClick: () => void; label: string; children: ReactNode }) {
  return renaming ? (
    <div className="card-open">{children}</div>
  ) : (
    <button className="card-open" onClick={onClick} aria-label={label}>
      {children}
    </button>
  );
}

