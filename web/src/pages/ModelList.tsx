import { useEffect, useState } from "react";
import { listModels } from "../api";
import { Account } from "../components/AuthGate";
import ImportButton from "../components/ImportButton";
import type { ModelSummary } from "../types";

type Props = { onOpen: (id: string) => void; onImport: (file: File) => void };

export default function ModelList({ onOpen, onImport }: Props) {
  const [models, setModels] = useState<ModelSummary[]>([]);
  useEffect(() => void listModels().then(setModels), []);

  return (
    <div className="page">
      <header className="bar">
        <span className="wordmark">Since</span>
        <span className="bar-spacer" />
        <ImportButton onImport={onImport} />
        <Account />
      </header>

      <main className="models">
        <table className="model-table">
          <thead>
            <tr>
              <th>Model</th>
              <th className="num">Assumptions set</th>
              <th className="num">Constants</th>
              <th className="num">Stale</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={m.model_id} onClick={() => onOpen(m.model_id)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onOpen(m.model_id)}>
                <td className="mono">{m.filename}</td>
                <td className="num mono">{m.built_on}</td>
                <td className="num mono">{m.constants}</td>
                <td className={`num mono ${m.stale ? "stale-count" : ""}`}>{m.stale || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="hint">Import a model, or drop an .xlsx anywhere on this page.</p>
      </main>
    </div>
  );
}
