// Mirrors schema/constant.schema.json. Change both together.

export type Check = {
  kind: "series" | "news";
  status: "stale" | "current" | "unknown";
  live: number | null;
  drift_pct: number | null;
  p_stale: number | null;
  as_of: string | null;
  source_name: string | null;
  source_url: string | null;
  evidence: { quote: string; url: string; publisher?: string; date?: string }[];
};

export type Constant = {
  cell: string;
  value: number;
  embedded: boolean;
  formula: string | null;
  label: string;
  driver: string | null;
  label_source: "header" | "llm" | "user";
  confirmed: boolean;
  feeds: number;
  outputs: string[];
  check: Check | null;
  impact: { output: string; delta: number }[];
};

export type Report = {
  model_id: string;
  filename: string;
  built_on: string;
  checked_on: string;
  outputs: { cell: string; label: string; value: number }[];
  constants: Constant[];
};

export type ModelSummary = {
  model_id: string;
  filename: string;
  built_on: string;
  stale: number;
  constants: number;
};
