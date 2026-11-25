// Network first, so page updates show up straight away; the cache only serves
// the page shell when the server can't be reached.
var staticCacheName = "keyboard-companion-v2";

self.addEventListener("install", function (e) {
  self.skipWaiting();
  e.waitUntil(
    caches.open(staticCacheName).then(function (cache) {
      return cache.addAll(["/"]);
    }),
  );
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys().then(function (names) {
      return Promise.all(
        names.filter((n) => n !== staticCacheName).map((n) => caches.delete(n)),
      );
    }),
  );
});

self.addEventListener("fetch", function (event) {
  event.respondWith(
    fetch(event.request).catch(function () {
      return caches.match(event.request);
    }),
  );
});
