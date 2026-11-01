// Audio never leaves this device until the user explicitly presses Send.
export type CaptureDraft = {
  id: string;
  userId: string;
  organizationId: string;
  itemId: string;
  reportedById?: string;
  shiftId: string;
  recordedAt: string;
  updatedAt: string;
  transcript: string;
  audio: Blob | null;
  noteId?: string;
  task?: { id: string; title: string } | null;
  corrections: string[];
  reply: { id: string; text: string; version: number } | null;
};
const database = () =>
  new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open("shiftproof-private-drafts", 1);
    request.onupgradeneeded = () =>
      request.result.createObjectStore("drafts", { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(
        new Error(
          "This browser could not save a local draft. Keep this page open until the report is sent.",
        ),
      );
  });
async function operation<T>(
  mode: IDBTransactionMode,
  callback: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await database();
  return new Promise<T>((resolve, reject) => {
    const tx = db.transaction("drafts", mode);
    const request = callback(tx.objectStore("drafts"));
    tx.oncomplete = () => {
      db.close();
      resolve(request.result);
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error || new Error("Could not save draft on this device."));
    };
    tx.onabort = () => {
      db.close();
      reject(tx.error || new Error("Draft save was interrupted."));
    };
  });
}
// A delayed autosave/checkpoint must not resurrect a sent or discarded capture.
// Keep only its opaque ID as a tombstone; no audio or account data remains.
export const saveDraft = (draft: CaptureDraft) =>
  operation("readwrite", (store) => {
    const request = store.get(draft.id);
    request.onsuccess = () => { if (!request.result?.retired) store.put(draft); };
    return request;
  });
export const deleteDraft = (id: string) =>
  operation("readwrite", (store) => store.put({ id, retired: true }));
export async function listDrafts(
  userId: string,
  organizationId: string,
): Promise<CaptureDraft[]> {
  const values = await operation<CaptureDraft[]>("readonly", (store) =>
    store.getAll(),
  );
  return values
    .filter((d) => d.userId === userId && d.organizationId === organizationId)
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}
export async function clearAccountDrafts(userId: string) {
  const values = await operation<CaptureDraft[]>("readonly", (store) =>
    store.getAll(),
  );
  await Promise.all(
    values.filter((d) => d.userId === userId).map((d) => deleteDraft(d.id)),
  );
}
