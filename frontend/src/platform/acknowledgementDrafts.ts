export type AcknowledgementDraft = {
  key: string;
  userId: string;
  base: string;
  shiftId: string;
  version: number;
  audio: Blob;
  savedId: string;
  updatedAt: string;
};
export const acknowledgementKey = (
  userId: string,
  base: string,
  shiftId: string,
) => JSON.stringify([userId, base, shiftId]);

async function operation<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open("shiftproof-private-readbacks", 1);
    request.onupgradeneeded = () =>
      request.result.createObjectStore("readbacks", { keyPath: "key" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(
        new Error(
          "Could not open saved readbacks. Keep this page open until you confirm receipt.",
        ),
      );
  });
  return new Promise<T>((resolve, reject) => {
    const tx = db.transaction("readbacks", mode),
      request = run(tx.objectStore("readbacks"));
    tx.oncomplete = () => {
      db.close();
      resolve(request.result);
    };
    tx.onabort = tx.onerror = () => {
      db.close();
      reject(
        new Error(
          "Could not save your readback on this device. Keep this page open until you confirm receipt.",
        ),
      );
    };
  });
}
export const loadAcknowledgement = (key: string) =>
  operation<AcknowledgementDraft | undefined>("readonly", (store) =>
    store.get(key),
  );
export const saveAcknowledgement = (draft: AcknowledgementDraft) =>
  operation("readwrite", (store) => store.put(draft));
export const deleteAcknowledgement = (key: string) =>
  operation("readwrite", (store) => store.delete(key));
export async function clearAccountAcknowledgements(userId: string) {
  const drafts = await operation<AcknowledgementDraft[]>("readonly", (store) =>
    store.getAll(),
  );
  await Promise.all(
    drafts
      .filter((draft) => draft.userId === userId)
      .map((draft) => deleteAcknowledgement(draft.key)),
  );
}
