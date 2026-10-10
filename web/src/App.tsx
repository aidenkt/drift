import { useState } from "react";
import ModelList from "./pages/ModelList";
import ModelDetail from "./pages/ModelDetail";

export default function App() {
  const [modelId, setModelId] = useState<string | null>(null);
  return modelId ? (
    <ModelDetail id={modelId} onBack={() => setModelId(null)} />
  ) : (
    <ModelList onOpen={setModelId} />
  );
}
