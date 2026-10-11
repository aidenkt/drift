import fixture from "../../schema/fixtures/case_study.json";
import type { Constant, ModelSummary, Report } from "./types";

const USE_FIXTURE = import.meta.env.VITE_USE_FIXTURE !== "0";
const ENGINE = import.meta.env.VITE_ENGINE_URL ?? "http://localhost:8000";

const sample = fixture as unknown as Report;

export async function listModels(): Promise<ModelSummary[]> {
  if (USE_FIXTURE) {
    return [
      {
        model_id: sample.model_id,
        filename: sample.filename,
        built_on: sample.built_on,
        stale: sample.constants.filter((c) => c.check?.status === "stale").length,
        constants: sample.constants.length,
      },
    ];
  }
  return (await fetch(`${ENGINE}/models`)).json();
}

/** Null when the engine no longer has the model: it forgets them when it restarts. */
export async function getModel(id: string): Promise<Report | null> {
  if (USE_FIXTURE) return sample;
  const res = await fetch(`${ENGINE}/models/${id}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`No report for model ${id}`);
  return res.json();
}

/** Send a workbook to be checked. The id comes back at once and its report fills in behind
 *  `getModel`. Null in fixture mode or with the engine off, so importing works without it. */
export async function analyze(file: Blob, filename: string, builtOn?: string): Promise<string | null> {
  if (USE_FIXTURE) return null;
  try {
    const form = new FormData();
    form.append("file", file, filename);
    // no built_on: the engine infers when the model was built
    const res = await fetch(`${ENGINE}/models${builtOn ? `?built_on=${builtOn}` : ""}`, { method: "POST", body: form });
    return res.ok ? ((await res.json()).model_id ?? null) : null;
  } catch {
    return null;
  }
}

/** The .xlsx as it was uploaded. */
export async function getModelFile(id: string): Promise<ArrayBuffer> {
  const res = await fetch(`${ENGINE}/models/${id}/file`);
  if (!res.ok) throw new Error(`No workbook for model ${id}`);
  return res.arrayBuffer();
}

/** Correct a constant's label or role; `literal_index` picks one number in a formula. */
export async function editConstant(
  id: string,
  edit: { cell: string; literal_index?: number; label?: string; role?: Constant["role"] },
): Promise<Constant> {
  const res = await fetch(`${ENGINE}/models/${id}/constants`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(edit),
  });
  if (!res.ok) throw new Error(`Couldn't update ${edit.cell}`);
  return res.json();
}
