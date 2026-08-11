const ExpenseOfflineDB = (() => {
    const DB_NAME = "ExpenseManagerOffline";
    const DB_VERSION = 2;

    const OPERATIONS = "pending_operations";
    const CACHE = "app_cache";

    function open() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onupgradeneeded = event => {
                const db = event.target.result;

                if (!db.objectStoreNames.contains(OPERATIONS)) {
                    const store = db.createObjectStore(OPERATIONS, {
                        keyPath: "id",
                        autoIncrement: true
                    });

                    store.createIndex("created_at", "created_at");
                    store.createIndex("type", "type");
                    store.createIndex("status", "status");
                }

                if (!db.objectStoreNames.contains(CACHE)) {
                    const cache = db.createObjectStore(CACHE, {
                        keyPath: "key"
                    });

                    cache.createIndex("updated_at", "updated_at");
                }
            };

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async function add(operation) {
        const db = await open();

        return new Promise((resolve, reject) => {
            const tx = db.transaction(OPERATIONS, "readwrite");

            const request = tx.objectStore(OPERATIONS).add({
                ...operation,
                created_at: new Date().toISOString(),
                status: "pending"
            });

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async function all() {
        const db = await open();

        return new Promise((resolve, reject) => {
            const tx = db.transaction(OPERATIONS, "readonly");
            const request = tx.objectStore(OPERATIONS).getAll();

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async function remove(id) {
        const db = await open();

        return new Promise((resolve, reject) => {
            const tx = db.transaction(OPERATIONS, "readwrite");

            tx.objectStore(OPERATIONS).delete(id);

            tx.oncomplete = resolve;
            tx.onerror = () => reject(tx.error);
        });
    }

    async function count() {
        const db = await open();

        return new Promise((resolve, reject) => {
            const tx = db.transaction(OPERATIONS, "readonly");
            const request = tx.objectStore(OPERATIONS).count();

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async function setCache(key, value) {
        const db = await open();

        return new Promise((resolve, reject) => {
            const tx = db.transaction(CACHE, "readwrite");

            tx.objectStore(CACHE).put({
                key,
                value,
                updated_at: new Date().toISOString()
            });

            tx.oncomplete = resolve;
            tx.onerror = () => reject(tx.error);
        });
    }

    async function getCache(key) {
        const db = await open();

        return new Promise((resolve, reject) => {
            const tx = db.transaction(CACHE, "readonly");
            const request = tx.objectStore(CACHE).get(key);

            request.onsuccess = () => {
                resolve(request.result ? request.result.value : null);
            };

            request.onerror = () => reject(request.error);
        });
    }

    async function removeCache(key) {
        const db = await open();

        return new Promise((resolve, reject) => {
            const tx = db.transaction(CACHE, "readwrite");

            tx.objectStore(CACHE).delete(key);

            tx.oncomplete = resolve;
            tx.onerror = () => reject(tx.error);
        });
    }

    async function clearCache() {
        const db = await open();

        return new Promise((resolve, reject) => {
            const tx = db.transaction(CACHE, "readwrite");

            tx.objectStore(CACHE).clear();

            tx.oncomplete = resolve;
            tx.onerror = () => reject(tx.error);
        });
    }

    return {
        open,
        add,
        all,
        remove,
        count,
        setCache,
        getCache,
        removeCache,
        clearCache
    };
})();
