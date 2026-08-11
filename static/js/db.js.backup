const ExpenseOfflineDB = (() => {
  const DB_NAME = "ExpenseManagerOffline";
  const DB_VERSION = 1;
  const STORE = "pending_operations";

  function open() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onupgradeneeded = event => {
        const db = event.target.result;

        if (!db.objectStoreNames.contains(STORE)) {
          const store = db.createObjectStore(STORE, {
            keyPath: "id",
            autoIncrement: true
          });

          store.createIndex("created_at", "created_at");
          store.createIndex("type", "type");
        }
      };

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function add(operation) {
    const db = await open();

    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");

      tx.objectStore(STORE).add({
        ...operation,
        created_at: new Date().toISOString(),
        status: "pending"
      });

      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
  }

  async function all() {
    const db = await open();

    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const request = tx.objectStore(STORE).getAll();

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function remove(id) {
    const db = await open();

    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(id);

      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
  }

  async function count() {
    const db = await open();

    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const request = tx.objectStore(STORE).count();

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  return {
    open,
    add,
    all,
    remove,
    count
  };
})();
