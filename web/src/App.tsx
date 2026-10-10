import { useCallback, useEffect, useState } from "react";
import { getModel } from "./api";
import { readXlsx } from "./lib/workbook";
import ModelList from "./pages/ModelList";
import WorkbookPage, { type OpenModel } from "./pages/WorkbookPage";

const ACCEPT = /\.(xlsx|xlsm|xls)$/i;

export default function App() {
  const [open, setOpen] = useState<OpenModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const importFile = useCallback(async (file: File) => {
    if (!ACCEPT.test(file.name)) return setError(`${file.name} isn't a spreadsheet. Drift opens .xlsx, .xlsm and .xls files.`);
    try {
      setOpen({ id: Date.now(), filename: file.name, builtOn: null, book: readXlsx(await file.arrayBuffer()), report: null });
      setError(null);
    } catch {
      setError(`Couldn't read ${file.name}. Re-save it from Excel as .xlsx and import it again.`);
    }
  }, []);

  const openModel = async (id: string) => {
    // Until the engine returns uploaded workbooks, the case study opens the placeholder sample.
    const [report, buf] = await Promise.all([getModel(id), fetch("/sample.xlsx").then((r) => r.arrayBuffer())]);
    setOpen({ id: Date.now(), filename: report.filename, builtOn: report.built_on, book: readXlsx(buf), report });
    setError(null);
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
        <WorkbookPage model={open} onImport={importFile} onBack={() => setOpen(null)} />
      ) : (
        <ModelList onOpen={openModel} onImport={importFile} />
      )}
      {error && (
        <div className="toast" role="alert">
          {error}
          <button onClick={() => setError(null)} aria-label="Dismiss">×</button>
        </div>
      )}
      {dragging && <div className="drop-veil">Drop to open in Drift</div>}
    </>
  );
}
