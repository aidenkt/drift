import { useEffect, useState } from "react";
import { getModel } from "../api";
import type { Report } from "../types";
import Stamp from "../components/Stamp";

export default function ModelDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const [report, setReport] = useState<Report | null>(null);
  useEffect(() => void getModel(id).then(setReport), [id]);
  if (!report) return null;

  return (
    <main>
      <button onClick={onBack}>←</button>
      <table>
        <tbody>
          {report.constants.map((c) => (
            <tr key={c.cell}>
              <td>{c.check && <Stamp status={c.check.status} />}</td>
              <td className="mono">{c.cell}</td>
              <td>{c.label}</td>
              <td className="mono">{c.value}</td>
              <td className="mono">{c.check?.live ?? "—"}</td>
              <td className="mono">{c.check?.drift_pct != null ? `${c.check.drift_pct}%` : "—"}</td>
              <td className="mono">{c.feeds}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
