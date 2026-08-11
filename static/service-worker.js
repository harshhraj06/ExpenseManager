const CACHE_NAME = "expense-manager-v1";

const APP_SHELL = [
  "/",
  "/static/style.css",
  "/static/auth.css",
  "/static/password_toggle.css",
  "/static/logo.png",
  "/static/login-bg.png",
  "/static/manifest.json",
  "/static/js/offline.js",
  "/static/js/db.js",
  "/static/js/sync.js"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;

  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => {
            cache.put(event.request, copy);
          });
        }
        return response;
      })
      .catch(() =>
        caches.match(event.request)
          .then(response =>
            response || caches.match("/offline")
          )
      )
  );
});
