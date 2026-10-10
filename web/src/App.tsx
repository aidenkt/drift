import { useCallback, useEffect, useState } from "react";
import { getModel, listModels } from "./api";
import { listFiles, removeFile, saveFile } from "./lib/library";
import { readXlsx } from "./lib/workbook";
import caseStudyUrl from "../../data/case_study_aug2026.xlsx?url";
import ModelList, { type Entry } from "./pages/ModelList";
import WorkbookPage, { type OpenModel } from "./pages/WorkbookPage";

const ACCEPT = /\.(xlsx|xlsm|xls)$/i;

export default function App() {
  const [open, setOpen] = useState<(OpenModel & { key: string }) | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  // checked models plus every workbook imported in this browser; null while loading
  const [library, setLibrary] = useState<Entry[] | null>(null);

  useEffect(() => {
    let live = true;
    (async () => {
      // Until the engine returns uploaded workbooks, each report opens the case-study workbook.
      const [summaries, stored, buf] = await Promise.all([
        listModels(),
        listFiles().catch(() => []),
        fetch(caseStudyUrl).then((r) => r.arrayBuffer()),
      ]);
      const reports = await Promise.all(summaries.map((m) => getModel(m.model_id)));
      const checked: Entry[] = reports.map((r) => ({
        key: `model:${r.model_id}`,
        filename: r.filename,
        builtOn: r.built_on,
        added: null,
        edited: null,
        book: readXlsx(buf),
        report: r,
      }));
      const imported = stored
        .sort((a, b) => b.added.localeCompare(a.added))
        .flatMap((f): Entry[] => {
          try {
            return [{ key: f.key, filename: f.filename, builtOn: null, added: f.added, edited: null, book: readXlsx(f.buf), report: null }];
          } catch {
            return [];
          }
        });
      // last edited starts as when the file itself was saved (or imported, if it doesn't say)
      const entries = [...checked, ...imported].map((e) => ({ ...e, edited: e.book.modified ?? e.added }));
      if (live) setLibrary(entries);
    })();
    return () => {
      live = false;
    };
  }, []);

  const openEntry = (e: Entry, startEvent?: string) => {
    setOpen({ id: Date.now(), key: e.key, filename: e.filename, builtOn: e.builtOn, book: e.book, report: e.report, startEvent });
    setError(null);
  };

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
    } catch {
      setError(`Couldn't read ${file.name}. Re-save it from Excel as .xlsx and import it again.`);
    }
  }, []);

  const removeEntry = (e: Entry) => {
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
          onEdited={() => {
            const now = new Date().toISOString();
            setLibrary((prev) => prev?.map((x) => (x.key === open.key ? { ...x, edited: now } : x)) ?? null);
          }}
        />
      ) : (
        <ModelList entries={library} onOpen={openEntry} onImport={importFile} onRemove={removeEntry} />
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
