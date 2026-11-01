// Cache only the public application shell. Private API/audio responses never enter Cache Storage.
const CACHE = "shiftproof-shell-v7";
self.addEventListener("install", (event) =>
  event.waitUntil(
    caches.open(CACHE).then(async (cache) => {
      const response = await fetch("/", { cache: "reload" });
      if (!response.ok) throw new Error("Application shell unavailable");
      const html = await response.clone().text();
      await cache.put("/", response);
      const assets = [
        ...html.matchAll(/(?:src|href)="(\/assets\/[^\"]+)"/g),
      ].map((match) => match[1]);
      await cache.addAll(["/favicon.svg", "/favicon-dark.svg", "/manifest.webmanifest", ...assets]);
    }),
  ),
);
self.addEventListener("activate", (event) =>
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter(
              (key) => key.startsWith("shiftproof-shell-") && key !== CACHE,
            )
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  ),
);
self.addEventListener("fetch", (event) => {
  const request = event.request,
    url = new URL(request.url);
  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin ||
    url.pathname.startsWith("/api") ||
    url.pathname.includes("/audio")
  )
    return;
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match("/").then((response) => response || Response.error()),
      ),
    );
    return;
  }
  if (url.pathname.startsWith("/assets/") || ["/favicon.svg", "/favicon-dark.svg"].includes(url.pathname))
    event.respondWith(
      caches.open(CACHE).then(async (cache) => {
        // Immutable public assets may vary by Origin in the dev/preview server.
        const saved = await cache.match(request, { ignoreVary: true });
        if (saved) return saved;
        const response = await fetch(request);
        if (response.ok) await cache.put(request, response.clone());
        return response;
      }),
    );
});
