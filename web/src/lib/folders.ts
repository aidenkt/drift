/** Home-page folders, kept in this browser: the folder tree and which folder each model sits in. */

export type Folder = { id: string; name: string; parent: string | null };

const FOLDERS = "since.folders";
const PLACEMENT = "since.placement"; // entry key -> folder id; absent means the top level

const read = <T,>(key: string, fallback: T): T => {
  try {
    return JSON.parse(localStorage.getItem(key) ?? "") as T;
  } catch {
    return fallback;
  }
};
const write = (key: string, value: unknown) => localStorage.setItem(key, JSON.stringify(value));

export const loadFolders = () => read<Folder[]>(FOLDERS, []);
export const loadPlacement = () => read<Record<string, string>>(PLACEMENT, {});

export function createFolder(name: string, parent: string | null): Folder {
  const folder = { id: `f${Date.now().toString(36)}`, name, parent };
  write(FOLDERS, [...loadFolders(), folder]);
  return folder;
}

export function renameFolder(id: string, name: string) {
  write(FOLDERS, loadFolders().map((f) => (f.id === id ? { ...f, name } : f)));
}

/** Deletes a folder; its models and subfolders move up to its parent. Never deletes models. */
export function deleteFolder(id: string) {
  const folders = loadFolders();
  const parent = folders.find((f) => f.id === id)?.parent ?? null;
  write(FOLDERS, folders.filter((f) => f.id !== id).map((f) => (f.parent === id ? { ...f, parent } : f)));
  const placement = loadPlacement();
  for (const [key, folder] of Object.entries(placement)) {
    if (folder !== id) continue;
    if (parent) placement[key] = parent;
    else delete placement[key];
  }
  write(PLACEMENT, placement);
}

/** Moves a model into a folder, or to the top level with null. */
export function place(key: string, folder: string | null) {
  const placement = loadPlacement();
  if (folder) placement[key] = folder;
  else delete placement[key];
  write(PLACEMENT, placement);
}

/** Moves a folder under another one; refuses to put a folder inside itself. */
export function moveFolder(id: string, parent: string | null) {
  const folders = loadFolders();
  for (let p = parent; p; p = folders.find((f) => f.id === p)?.parent ?? null) if (p === id) return;
  write(FOLDERS, folders.map((f) => (f.id === id ? { ...f, parent } : f)));
}

/** The folders from the top level down to `id`, for the breadcrumb. */
export function pathTo(folders: Folder[], id: string | null): Folder[] {
  const out: Folder[] = [];
  for (let f = folders.find((x) => x.id === id); f; f = folders.find((x) => x.id === f!.parent)) out.unshift(f);
  return out;
}
