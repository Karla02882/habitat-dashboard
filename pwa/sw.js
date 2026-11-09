var VERSION = "1";
var CACHE = "habitat-app-" + VERSION;
var SIN_CONEXION = "/sin-conexion.html";
var PUBLICOS = [SIN_CONEXION, "/icono-192.png"];

self.addEventListener("install", function (e) {
  e.waitUntil(
    caches.open(CACHE)
      .then(function (c) { return c.addAll(PUBLICOS); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys()
      .then(function (ks) {
        return Promise.all(ks.filter(function (k) {
          return k.indexOf("habitat-app-") === 0 && k !== CACHE;
        }).map(function (k) { return caches.delete(k); }));
      })
      .then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (e) {
  if (e.request.mode !== "navigate") return;
  e.respondWith(
    fetch(e.request).catch(function () { return caches.match(SIN_CONEXION); })
  );
});
