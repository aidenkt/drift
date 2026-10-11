import { useCallback, useEffect, useRef, useState } from "react";
import { analyze, getModel, getModelFile, listModels } from "./api";
import { fetchSharedFile, listShared, type SharedDoc } from "./lib/collab";
import { listFiles, removeFile, saveFile } from "./lib/library";
import { loadPlacement, place } from "./lib/folders";
import { modelPath, readRoute } from "./lib/route";
import { blankBook, downloadXlsx, readXlsx, xlsxBytes } from "./lib/workbook";
import caseStudyUrl from "../../data/case_study_aug2026.xlsx?url";
import ModelList, { type Entry } from "./pages/ModelList";
import WorkbookPage, { type OpenModel } from "./pages/WorkbookPage";
import type { Report } from "./types";

const ACCEPT = /\.(xlsx|xlsm|xls)$/i;

// renamed models, by entry key, so a new name survives a reload
const NAMES = "since.names";
const names = (): Record<string, string> => {
  try {
    return JSON.parse(localStorage.getItem(NAMES) ?? "{}");
  } catch {
    return {};
  }
};
const saveName = (key: string, filename: string | null) => {
  const all = names();
  if (filename) all[key] = filename;
  else delete all[key];
  localStorage.setItem(NAMES, JSON.stringify(all));
};

// local models that were shared, by entry key -> engine doc id, so they don't show up twice
const LINKS = "since.links";
const links = (): Record<string, string> => {
  try {
    return JSON.parse(localStorage.getItem(LINKS) ?? "{}");
  } catch {
    return {};
  }
};

// imported files the engine has checked, by entry key -> engine model id, so a reload finds the report again
const REPORTS = "since.reports";
const reportLinks = (): Record<string, string> => {
  try {
    return JSON.parse(localStorage.getItem(REPORTS) ?? "{}");
  } catch {
    return {};
  }
};
const saveReport = (key: string, id: string | null) => {
  const all = reportLinks();
  if (id) all[key] = id;
  else delete all[key];
  localStorage.setItem(REPORTS, JSON.stringify(all));
};

/** Workbooks shared with or by you on the engine: matched to local models, or loaded as new cards. */
async function sharedEntries(local: Entry[]): Promise<Entry[]> {
  const docs = await listShared().catch(() => [] as SharedDoc[]);
  const byDoc = Object.fromEntries(Object.entries(links()).map(([key, id]) => [id, key]));
  const extra: Entry[] = [];
  for (const doc of docs) {
    const mine = local.find((e) => e.key === byDoc[doc.doc_id]);
    if (mine) {
      mine.doc = doc;
      continue;
    }
    try {
      const book = readXlsx(await fetchSharedFile(doc.doc_id));
      const edited = new Date(doc.updated * 1000).toISOString();
      extra.push({ key: `doc:${doc.doc_id}`, filename: doc.filename, builtOn: null, added: edited, edited, book, report: null, doc });
    } catch {
      // unreadable or gone: leave it off the home page
    }
  }
  return extra;
}

export default function App() {
  const [open, setOpen] = useState<(OpenModel & { key: string }) | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  // checked models plus every workbook imported in this browser; null while loading
  const [library, setLibrary] = useState<Entry[] | null>(null);
  const reportsRef = useRef<Report[]>([]);

  // leaving the app stops asking the engine for reports
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  /** Put the engine's report on an entry, and on the open model if it's that one, again every 2 s while it's still checking. */
  const follow = async (key: string, id: string) => {
    let shown = "";
    while (mounted.current) {
      const report = await getModel(id).catch(() => undefined);
      if (!mounted.current || report === undefined) return; // engine unreachable: keep what's shown
      if (report === null) return saveReport(key, null); // the engine restarted and forgot the model
      // most polls bring nothing new: only a changed report redraws the page
      const text = JSON.stringify(report);
      if (text !== shown) {
        shown = text;
        setLibrary((prev) => prev?.map((x) => (x.key === key ? { ...x, report, builtOn: report.built_on } : x)) ?? null);
        setOpen((o) => (o && o.key === key ? { ...o, report, builtOn: report.built_on } : o));
      }
      if (report.status !== "checking") return;
      await new Promise((r) => setTimeout(r, 2000));
    }
  };

  useEffect(() => {
    let live = true;
    (async () => {
      // An engine model opens the workbook that was uploaded; the fixture has none, so it opens the case study.
      const [summaries, stored, buf] = await Promise.all([
        listModels().catch(() => []),
        listFiles().catch(() => []),
        fetch(caseStudyUrl).then((r) => r.arrayBuffer()),
      ]);
      // a model checked from a file imported here already has that file's card
      const linked = reportLinks();
      const mine = new Set(Object.values(linked));
      const reports = (await Promise.all(summaries.map((m) => getModel(m.model_id).catch(() => null)))).filter((r): r is Report => r !== null);
      reportsRef.current = reports;
      const saved = new Map(stored.map((f) => [f.key, f]));
      // checked models open from their saved copy once edited, else from the original file
      const checked = (
        await Promise.all(
          reports
            .filter((r) => !mine.has(r.model_id))
            .map(async (r): Promise<Entry[]> => {
              const key = `model:${r.model_id}`;
              try {
                const own = saved.get(key);
                const book = readXlsx(own?.buf ?? (r.model_id === "case-study" ? buf : await getModelFile(r.model_id)));
                return [{ key, filename: r.filename, builtOn: r.built_on, added: null, edited: null, book, report: r }];
              } catch {
                return []; // no workbook to show it on: leave it off the home page
              }
            }),
        )
      ).flat();
      const imported = stored
        .filter((f) => !f.key.startsWith("model:"))
        .sort((a, b) => b.added.localeCompare(a.added))
        .flatMap((f): Entry[] => {
          try {
            const report = reports.find((r) => r.model_id === (f.report ?? linked[f.key])) ?? null;
            return [{ key: f.key, filename: f.filename, builtOn: report?.built_on ?? null, added: f.added, edited: null, book: readXlsx(f.buf), report, blank: f.blank }];
          } catch {
            return [];
          }
        });
      // last edited starts as when the file itself was saved (or imported, if it doesn't say)
      const renamed = names();
      const entries = [...checked, ...imported].map((e) => ({ ...e, filename: renamed[e.key] ?? e.filename, edited: e.book.modified ?? e.added }));
      const shared = (await sharedEntries(entries)).map((e) => ({ ...e, filename: renamed[e.key] ?? e.filename }));
      if (!live) return;
      const all = [...entries, ...shared];
      setLibrary(all);
      // reports for the files imported here, and for anything the engine is still checking
      const known = new Set(summaries.map((m) => m.model_id));
      for (const e of imported) if (known.has(linked[e.key])) void follow(e.key, linked[e.key]);
      for (const e of checked) if (e.report?.status === "checking") void follow(e.key, e.report.model_id);
      // a reload reopens the model and sheet in the path
      const route = readRoute();
      const entry = route && all.find((e) => e.key === route.key);
      if (entry) openEntry(entry, undefined, route.cell);
    })();
    return () => {
      live = false;
    };
  }, []);

  const openEntry = (e: Entry, startEvent?: string, startCell?: string) => {
    setOpen({ id: Date.now(), key: e.key, filename: e.filename, builtOn: e.builtOn, book: e.book, report: e.report, startEvent, startCell, doc: e.doc });
    setError(null);
  };

  // the path follows the open model: opening one adds a history entry, so Back returns home
  // the sheet reports its cell before this effect runs (child effects first), so it waits here
  const openKey = open?.key ?? null;
  const lastCell = useRef<{ key: string; cell: string } | null>(null);
  useEffect(() => {
    if (library === null) return; // still loading; the path may name a model about to open
    const cell = lastCell.current?.key === openKey ? lastCell.current.cell : undefined;
    if ((readRoute()?.key ?? null) !== openKey) history.pushState(null, "", openKey ? modelPath(openKey, cell) : "/");
  }, [openKey, library === null]);
  const followCell = (key: string, cell: string) => {
    lastCell.current = { key, cell };
    if (readRoute()?.key === key) history.replaceState(null, "", modelPath(key, cell));
  };
  const libraryRef = useRef(library);
  libraryRef.current = library;
  useEffect(() => {
    const onPop = () => {
      const route = readRoute();
      const entry = route && libraryRef.current?.find((e) => e.key === route.key);
      if (!entry) return setOpen(null);
      setOpen((o) => (o?.key === entry.key ? o : { id: Date.now(), key: entry.key, filename: entry.filename, builtOn: entry.builtOn, book: entry.book, report: entry.report, startCell: route.cell, doc: entry.doc }));
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const importFile = useCallback(async (file: File) => {
    if (!ACCEPT.test(file.name)) return setError(`${file.name} isn't a spreadsheet. Since opens .xlsx, .xlsm and .xls files.`);
    try {
      const buf = await file.arrayBuffer();
      const entry: Entry = {
        key: `file:${Date.now()}`,
        filename: file.name,
        builtOn: null,
        added: new Date().toISOString(),
        edited: null,
        book: readXlsx(buf.slice(0)),
        report: null,
      };
      entry.edited = entry.book.modified ?? entry.added;
      void saveFile({ key: entry.key, filename: entry.filename, added: entry.added!, buf }).catch(() => {});
      setLibrary((prev) => [entry, ...(prev ?? [])]);
      setOpen({ id: Date.now(), key: entry.key, filename: entry.filename, builtOn: null, book: entry.book, report: null });
      setError(null);
      // the engine checks it in the background; the report lands on this entry as it fills in
      void analyze(file, file.name).then((id) => {
        if (!id) return;
        saveReport(entry.key, id);
        void follow(entry.key, id);
      });
    } catch {
      setError(`Couldn't read ${file.name}. Re-save it from Excel as .xlsx and import it again.`);
    }
  }, []);

  /** New name without the extension; the original extension stays. */
  const renameEntry = (key: string, name: string) => {
    const rename = (filename: string) => name + (filename.match(ACCEPT)?.[0] ?? ".xlsx");
    const entry = library?.find((x) => x.key === key);
    if (entry) saveName(key, rename(entry.filename));
    setLibrary((prev) => prev?.map((x) => (x.key === key ? { ...x, filename: rename(x.filename) } : x)) ?? null);
    setOpen((o) => (o && o.key === key ? { ...o, filename: rename(o.filename) } : o));
  };

  /** A fresh copy of the example model, with its checks, saved in this browser and opened. */
  const createExample = async (folder: string | null) => {
    const report = reportsRef.current.find((r) => r.model_id === "case-study") ?? null;
    const buf = await fetch(caseStudyUrl).then((r) => r.arrayBuffer());
    const added = new Date().toISOString();
    const entry: Entry = { key: `file:${Date.now()}`, filename: "Example model.xlsx", builtOn: report?.built_on ?? null, added, edited: added, book: readXlsx(buf.slice(0)), report };
    void saveFile({ key: entry.key, filename: entry.filename, added, buf, report: report?.model_id }).catch(() => {});
    if (folder) place(entry.key, folder);
    setLibrary((prev) => [entry, ...(prev ?? [])]);
    openEntry(entry);
  };

  /** A new empty spreadsheet, saved in this browser and opened straight away. */
  const createBlank = (folder: string | null) => {
    const added = new Date().toISOString();
    const entry: Entry = { key: `file:${Date.now()}`, filename: "Untitled spreadsheet.xlsx", builtOn: null, added, edited: added, book: blankBook(), report: null, blank: true };
    void saveFile({ key: entry.key, filename: entry.filename, added, buf: xlsxBytes(entry.book), blank: true }).catch(() => {});
    if (folder) place(entry.key, folder);
    setLibrary((prev) => [entry, ...(prev ?? [])]);
    openEntry(entry);
  };

  // every model keeps its edits in this browser: write the workbook back a moment after each change.
  // Shared workbooks save to Base44 from the workbook page instead.
  const pending = useRef<number | undefined>(undefined);
  const persist = (key: string, book: Entry["book"], filename: string, added: string | null, blank?: boolean, report?: string) => {
    if (key.startsWith("doc:")) return;
    clearTimeout(pending.current);
    pending.current = window.setTimeout(() => {
      void saveFile({ key, filename, added: added ?? new Date().toISOString(), buf: xlsxBytes(book), blank, report }).catch(() => {});
    }, 800);
  };

  /** A model was shared (uploaded) or its access changed: remember the link and show it. */
  const sharedEntry = (key: string, doc: SharedDoc) => {
    if (!key.startsWith("doc:")) localStorage.setItem(LINKS, JSON.stringify({ ...links(), [key]: doc.doc_id }));
    setLibrary((prev) => prev?.map((x) => (x.key === key ? { ...x, doc } : x)) ?? null);
    setOpen((o) => (o && o.key === key ? { ...o, doc } : o));
  };

  /** A copy of the workbook as it stands, saved in this browser and opened. Checks stay with the original. */
  const copyEntry = (key: string, book: Entry["book"], filename: string) => {
    const added = new Date().toISOString();
    const buf = xlsxBytes(book);
    const entry: Entry = { key: `file:${Date.now()}`, filename: `Copy of ${filename}`, builtOn: null, added, edited: added, book: readXlsx(buf.slice(0)), report: null };
    void saveFile({ key: entry.key, filename: entry.filename, added, buf }).catch(() => {});
    const folder = loadPlacement()[key];
    if (folder) place(entry.key, folder);
    setLibrary((prev) => [entry, ...(prev ?? [])]);
    openEntry(entry);
  };

  const removeEntry = (e: Entry) => {
    place(e.key, null);
    saveName(e.key, null);
    void removeFile(e.key).catch(() => {});
    setLibrary((prev) => prev?.filter((x) => x.key !== e.key) ?? null);
  };

  useEffect(() => {
    const over = (e: DragEvent) => {
      if (!e.dataTransfer?.types.includes("Files")) return;
      e.preventDefault();
      setDragging(true);
    };
    const leave = (e: DragEvent) => e.relatedTarget === null && setDragging(false);
    const drop = (e: DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer?.files[0];
      if (file) void importFile(file);
    };
    window.addEventListener("dragover", over);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragover", over);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
    };
  }, [importFile]);

  return (
    <>
      {open ? (
        <WorkbookPage
          key={open.id}
          model={open}
          onImport={importFile}
          onBack={() => setOpen(null)}
          onCell={(cell) => followCell(open.key, cell)}
          onRename={(name) => renameEntry(open.key, name)}
          onShared={(doc) => sharedEntry(open.key, doc)}
          onNew={() => createBlank(loadPlacement()[open.key] ?? null)}
          onCopy={() => copyEntry(open.key, open.book, open.filename)}
          onTrash={
            open.key.startsWith("file:")
              ? () => {
                  const entry = library?.find((x) => x.key === open.key);
                  if (!entry || !confirm(`Move "${open.filename}" to trash? It's removed from this browser.`)) return;
                  removeEntry(entry);
                  setOpen(null);
                }
              : undefined
          }
          onEdited={() => {
            const now = new Date().toISOString();
            const entry = library?.find((x) => x.key === open.key);
            persist(open.key, open.book, open.filename, entry?.added ?? null, entry?.blank, open.report?.model_id);
            setLibrary((prev) => prev?.map((x) => (x.key === open.key ? { ...x, edited: now } : x)) ?? null);
          }}
        />
      ) : (
        <ModelList
          entries={library}
          onOpen={openEntry}
          onImport={importFile}
          onRemove={removeEntry}
          onRename={(e, name) => renameEntry(e.key, name)}
          onDownload={(e) => downloadXlsx(e.book, e.filename)}
          onNewBlank={createBlank}
          onNewExample={(folder) => void createExample(folder)}
          onShared={(e, doc) => sharedEntry(e.key, doc)}
        />
      )}
      {error && (
        <div className="toast" role="alert">
          {error}
          <button onClick={() => setError(null)} aria-label="Dismiss">×</button>
        </div>
      )}
      {dragging && <div className="drop-veil">Drop to open in Since</div>}
    </>
  );
}
