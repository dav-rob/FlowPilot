import test from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const server = await createServer({
  server: { middlewareMode: true, hmr: false },
  optimizeDeps: { noDiscovery: true, include: [] },
  appType: "custom",
});
const { default: UserProfile } = await server.ssrLoadModule(
  "/src/UserProfile.tsx",
);
test.after(() => server.close());

test("UserProfile SSR renders accessible menu trigger and collapsed menu items", () => {
  const html = renderToStaticMarkup(createElement(UserProfile));

  assert.match(html, /<button[^>]*type="button"[^>]*class="up-trigger"/);
  assert.match(html, /aria-label="Alex Morgan, Operations reviewer"/);
  assert.match(html, /aria-haspopup="menu"/);
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /aria-controls="[^"]+"/);
  assert.match(html, />AM</);
  assert.match(html, />Alex Morgan</);
  assert.match(html, />Operations reviewer</);

  assert.match(html, /class="up-menu-panel"[^>]*hidden=""/);
  assert.match(html, /role="menu"/);
  assert.match(html, /role="menuitem"[^>]*>.*Profile/s);
  assert.match(
    html,
    /role="menuitem"[^>]*>.*Responsibilities &amp; permissions/s,
  );
  assert.match(html, /Demo profile/);
  assert.match(html, /Name, team and role/);
  assert.match(html, /Approval requirements and restrictions/);
});
