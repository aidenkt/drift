/** Imported workbooks kept in the browser (IndexedDB) so they stay on the home page across reloads. */

/** report: the model_id whose checks travel with the file, for copies of the example model.
 *  updated: for cached copies of Base44 workbooks ("cache:<doc id>"), the version they hold. */
export type StoredFile = { key: string; filename: string; added: string; buf: ArrayBuffer; blank?: boolean; report?: string; updated?: number };

/** Base44 workbooks are cached here by doc id, so the home page only downloads what changed. */
export const cacheKey = (docId: string) => `cache:${docId}`;
export const isCache = (key: string) => key.startsWith("cache:");

const DB = "since";
const STORE = "files";

function db(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "key" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function run<T>(mode: IDBTransactionMode, op: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return db().then(
    (d) =>
      new Promise<T>((resolve, reject) => {
        const req = op(d.transaction(STORE, mode).objectStore(STORE));
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      }),
  );
}

export const listFiles = () => run<StoredFile[]>("readonly", (s) => s.getAll() as IDBRequest<StoredFile[]>);
export const saveFile = (f: StoredFile) => run("readwrite", (s) => s.put(f));
export const removeFile = (key: string) => run("readwrite", (s) => s.delete(key));
