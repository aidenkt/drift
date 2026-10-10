import { History } from "lucide-react";

// 16px stroke icons, drawn to match the toolbar's weight.
const base = { width: 16, height: 16, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: 1.4, strokeLinecap: "round", strokeLinejoin: "round" } as const;

export const Undo = () => (
  <svg {...base} aria-hidden><path d="M5.5 4 2.5 7l3 3" /><path d="M2.5 7h7a4 4 0 0 1 0 8H8" /></svg>
);
export const Redo = () => (
  <svg {...base} aria-hidden><path d="M10.5 4l3 3-3 3" /><path d="M13.5 7h-7a4 4 0 0 0 0 8H8" /></svg>
);
export const Chevron = () => (
  <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor" aria-hidden><path d="M2 3.5h6L5 7z" /></svg>
);
export const Star = ({ filled }: { filled: boolean }) => (
  <svg {...base} fill={filled ? "currentColor" : "none"} aria-hidden>
    <path d="m8 1.8 1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.6l-3.8 2 .7-4.3-3.1-3 4.3-.6z" />
  </svg>
);
export const Panel = () => (
  <svg {...base} aria-hidden><rect x="1.5" y="2.5" width="13" height="11" rx="1.5" /><path d="M10 2.5v11" /></svg>
);
export const DecMore = () => (
  <svg width="22" height="16" viewBox="0 0 22 16" aria-hidden fill="currentColor" fontFamily="ui-monospace, monospace" fontSize="9">
    <text x="0" y="11">.00</text><path d="M16 12h5M19 10l2 2-2 2" stroke="currentColor" fill="none" strokeWidth="1.2" />
  </svg>
);
export const DecLess = () => (
  <svg width="22" height="16" viewBox="0 0 22 16" aria-hidden fill="currentColor" fontFamily="ui-monospace, monospace" fontSize="9">
    <text x="0" y="11">.0</text><path d="M21 12h-5M18 10l-2 2 2 2" stroke="currentColor" fill="none" strokeWidth="1.2" />
  </svg>
);

/** Temporary logo: shadcn's sidebar-block pattern, a lucide icon on a dark rounded square. */
export const Mark = () => (
  <span className="logo-mark" aria-hidden>
    <History size={16} strokeWidth={2} />
  </span>
);
