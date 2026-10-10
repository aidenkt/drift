import fixture from "../../schema/fixtures/case_study.json";
import type { ModelSummary, Report } from "./types";

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

export async function getModel(id: string): Promise<Report> {
  if (USE_FIXTURE) return sample;
  return (await fetch(`${ENGINE}/models/${id}`)).json();
}
