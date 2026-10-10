import { useEffect, useState } from "react";
import { listModels } from "../api";
import type { ModelSummary } from "../types";

export default function ModelList({ onOpen }: { onOpen: (id: string) => void }) {
  const [models, setModels] = useState<ModelSummary[]>([]);
  useEffect(() => void listModels().then(setModels), []);

  return (
    <main>
      {models.map((m) => (
        <button key={m.model_id} onClick={() => onOpen(m.model_id)}>
          <span className="mono">{m.filename}</span> · {m.stale}/{m.constants} stale · built {m.built_on}
        </button>
      ))}
    </main>
  );
}
