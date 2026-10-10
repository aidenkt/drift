import { useRef } from "react";

export default function ImportButton({ onImport }: { onImport: (file: File) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <button className="btn" onClick={() => input.current?.click()}>
        Import .xlsx
      </button>
      <input
        ref={input}
        type="file"
        accept=".xlsx,.xlsm,.xls"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onImport(file);
          e.target.value = "";
        }}
      />
    </>
  );
}
