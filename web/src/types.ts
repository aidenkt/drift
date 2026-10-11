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
  // image: the page's preview image (og:image), when it has one
  evidence: { quote: string; url: string; publisher?: string; date?: string; image?: string }[];
  // news behind the move, and the checker's reading of it
  events?: { summary: string; direction: "raises" | "lowers" | "unclear"; quote: string; url: string; publisher?: string; date?: string; image?: string }[];
  effects?: { output: string; direction: "up" | "down" | "unclear" }[]; // output is a label here, not a cell
  assumption?: string | null;
  prediction?: string | null;
  next_steps?: string[];
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
  // embedded only: a number in a formula copied across a row is one constant. `cell` is then
  // a range ("P&L!C35:G35"), `cells` every formula cell, `literal_index` which number (0-based)
  cells?: string[];
  literal_index?: number;
  role?: "market" | "lever" | "internal" | "unit"; // only market constants are checked
  sensitivity?: unknown;
};

export type Report = {
  model_id: string;
  filename: string;
  built_on: string;
  checked_on: string;
  outputs: { cell: string; label: string; value: number }[];
  constants: Constant[];
  combined?: { output: string; delta: number }[]; // every live value applied at once
  status?: "checking" | "done" | "failed"; // missing (the fixture) means done
  progress?: { checked: number; total: number };
};

export type ModelSummary = {
  model_id: string;
  filename: string;
  built_on: string;
  stale: number;
  constants: number;
  status?: Report["status"];
};
