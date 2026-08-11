const CACHE_NAME = "expense-manager-v9";

const STATIC_ASSETS = [
    "/offline",
    "/static/style.css",
    "/static/logo.png",
    "/static/login-bg.png",
    "/static/manifest.json",
    "/static/js/db.js",
    "/static/js/sync.js",
    "/static/js/offline.js",
    "/static/js/offline-forms.js",
    "/static/js/dashboard-live.js",
    "/static/js/dashboard-pro.js",
    "/static/pro-dashboard.css",
    "/static/budgets.css",
    "/static/goals.css",
    "/static/subscriptions.css",
    "/static/reports.css",
    "/static/search.css"
];


self.addEventListener("install", event => {
    event.waitUntil(
        caches
            .open(CACHE_NAME)
            .then(cache =>
                cache.addAll(STATIC_ASSETS)
            )
            .then(() =>
                self.skipWaiting()
            )
    );
});


self.addEventListener("activate", event => {
    event.waitUntil(
        caches
            .keys()
            .then(keys =>
                Promise.all(
                    keys
                        .filter(
                            key =>
                                key !== CACHE_NAME
                        )
                        .map(
                            key =>
                                caches.delete(key)
                        )
                )
            )
            .then(() =>
                self.clients.claim()
            )
    );
});


self.addEventListener("fetch", event => {
    const request = event.request;

    if (request.method !== "GET") {
        return;
    }

    const url = new URL(request.url);

    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request).catch(() =>
                caches.match("/offline")
            )
        );

        return;
    }

    if (
        url.origin === self.location.origin &&
        url.pathname.startsWith("/static/")
    ) {
        event.respondWith(
            caches.match(request).then(cached => {
                const network =
                    fetch(request)
                        .then(response => {
                            if (response.ok) {
                                const copy =
                                    response.clone();

                                caches
                                    .open(CACHE_NAME)
                                    .then(cache =>
                                        cache.put(
                                            request,
                                            copy
                                        )
                                    );
                            }

                            return response;
                        })
                        .catch(() => cached);

                return cached || network;
            })
        );
    }
});
