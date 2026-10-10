import { useMemo } from "react";
import { Account } from "../components/AuthGate";
import ImportButton from "../components/ImportButton";
import Spreadsheet from "../components/Spreadsheet";
import { normalizeRef, type Book } from "../lib/workbook";
import type { Constant, Report } from "../types";

export type OpenModel = { id: number; filename: string; builtOn: string | null; book: Book; report: Report | null };

type Props = { model: OpenModel; onImport: (file: File) => void; onBack: () => void };

export default function WorkbookPage({ model, onImport, onBack }: Props) {
  const constants = useMemo(
    () => new Map<string, Constant>((model.report?.constants ?? []).map((c) => [normalizeRef(c.cell), c])),
    [model.report],
  );
  const stale = model.report?.constants.filter((c) => c.check?.status === "stale").length ?? 0;

  return (
    <div className="page workbook">
      <header className="bar">
        <button className="btn-quiet wordmark" onClick={onBack}>
          Drift
        </button>
        <span className="filename mono">{model.filename}</span>
        {model.builtOn && <span className="muted mono">assumptions set {model.builtOn}</span>}
        {model.report && (
          <span className={`mono ${stale ? "stale-count" : "muted"}`}>
            {stale} stale of {model.report.constants.length}
          </span>
        )}
        <span className="bar-spacer" />
        <ImportButton onImport={onImport} />
        <Account />
      </header>
      {/* key: a new workbook resets selection and sheet */}
      <Spreadsheet key={model.id} book={model.book} constants={constants} />
    </div>
  );
}
