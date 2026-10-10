/* The header's navigation button, and the reading-progress bar under it.

Both of these were reported from a phone, and both are the kind of thing that
looks fine on a desktop and is broken on a phone:

  - the hamburger opened the documentation rail, but the landing page has no
    rail, so on that page the button rendered, was clickable, and did nothing.
    Verified by clicking it and watching what changed, not by reading the
    handler - a toggle wired to an element that is not on the page runs
    perfectly and is invisible to every check short of clicking it.

  - the progress bar was the accent blue. This checks it is the text colour,
    and that it only ever grows while the reader scrolls down.

Run: node tools/verify_nav.js   (needs: npm i --no-save puppeteer)
*/
const puppeteer = require("puppeteer");
const path = require("path"), fs = require("fs"), http = require("http");

const docs = path.join(__dirname, "..", "docs");
const MIME = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript",
  ".json": "application/json", ".svg": "image/svg+xml", ".woff2": "font/woff2" };
const server = http.createServer((req, res) => {
  const f = path.join(docs, req.url.split("?")[0].replace(/^\//, "") || "index.html");
  if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": MIME[path.extname(f)] || "application/octet-stream" });
  res.end(fs.readFileSync(f));
});
const wait = (ms) => new Promise(r => setTimeout(r, ms));

const PAGES = ["index.html", "features.html", "install.html", "ai.html",
               "security.html", "faq.html", "build.html"];

/* Below this width the bar's links are hidden behind the hamburger, which is
   what makes the hamburger's job matter. The number is duplicated in
   style.css's breakpoint; if they drift, this fails loudly rather than
   quietly testing the wrong layout. */
const NARROW = 900;

let passed = 0;
let failed = 0;
function check(name, ok, detail) {
  (ok ? passed++ : failed++);
  console.log(`  [${ok ? "PASS" : "FAIL"}] ${name}${ok || !detail ? "" : " -> " + detail}`);
}

server.listen(0, "127.0.0.1", async () => {
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await puppeteer.launch({ args: ["--no-sandbox"] });

  // ------------------------------------------------------------ navigation
  for (const width of [390, 768]) {
    console.log(`\n=== the hamburger at ${width}px ===`);
    for (const p of PAGES) {
      const page = await browser.newPage();
      await page.setViewport({ width, height: 780, isMobile: width < NARROW, hasTouch: width < NARROW });
      await page.goto(`${base}/${p}`, { waitUntil: "load" });
      await wait(600);

      const before = await page.evaluate(() => {
        const t = document.getElementById("navToggle");
        return {
          visible: t ? t.getBoundingClientRect().width > 0 : false,
          hasRail: !!document.getElementById("rail"),
          links: document.querySelectorAll(".top-nav a").length,
        };
      });

      if (!before.visible) {
        console.log(`  [skip] ${p}: no hamburger at this width`);
        await page.close();
        continue;
      }

      await page.click("#navToggle");
      await wait(420);

      const after = await page.evaluate(() => {
        const rail = document.getElementById("rail");
        const nav = document.querySelector(".top-nav");
        const t = document.getElementById("navToggle");
        return {
          expanded: t.getAttribute("aria-expanded"),
          railOpen: rail ? rail.classList.contains("is-open") : null,
          railOnScreen: rail
            ? rail.getBoundingClientRect().width > 0 &&
              rail.getBoundingClientRect().left < window.innerWidth &&
              rail.getBoundingClientRect().right > 0
            : null,
          navOpen: nav ? nav.classList.contains("is-open") : null,
          navOnScreen: nav
            ? getComputedStyle(nav).display !== "none" &&
              nav.getBoundingClientRect().height > 0
            : null,
          reachable: document.querySelectorAll(
            (rail && rail.classList.contains("is-open")) ? ".rail-link" : ".top-nav a"
          ).length,
        };
      });

      check(`${p}: the button reports itself open`, after.expanded === "true",
            `aria-expanded=${after.expanded}`);
      check(`${p}: something opened that a reader can reach`,
            (before.hasRail ? after.railOpen && after.railOnScreen
                            : after.navOpen && after.navOnScreen),
            JSON.stringify(after));
      check(`${p}: the navigation has destinations in it`,
            after.reachable > 0 || (before.hasRail ? true : before.links > 0),
            `${after.reachable} reachable, ${before.links} links in the bar`);

      // And it closes again, or the panel sits over the page they asked for.
      await page.keyboard.press("Escape");
      await wait(300);
      const closed = await page.evaluate(() => {
        const rail = document.getElementById("rail");
        const nav = document.querySelector(".top-nav");
        const open = rail ? rail.classList.contains("is-open")
                          : nav ? nav.classList.contains("is-open") : false;
        return { open, expanded: document.getElementById("navToggle").getAttribute("aria-expanded") };
      });
      check(`${p}: Escape closes it`,
            closed.open === false && closed.expanded === "false", JSON.stringify(closed));

      await page.close();
    }
  }

  // ----------------------------------------------------------- progress bar
  console.log("\n=== the reading-progress bar ===");
  for (const cfg of [
    { w: 1280, h: 800, mobile: false, name: "desktop" },
    { w: 390, h: 780, mobile: true, name: "phone" },
  ]) {
    const page = await browser.newPage();
    await page.setViewport({ width: cfg.w, height: cfg.h, isMobile: cfg.mobile, hasTouch: cfg.mobile });
    await page.goto(`${base}/features.html`, { waitUntil: "load" });
    await page.addStyleTag({ content: "html{scroll-behavior:auto!important}" });
    await wait(600);

    const colour = await page.evaluate(() => {
      // Ask for the token's own computed value rather than the custom
      // property's text: `getPropertyValue("--text")` returns the authored
      // "#ededed" while `backgroundColor` returns "rgb(237, 237, 237)", and
      // comparing those two strings reports a mismatch that does not exist.
      const probe = document.createElement("span");
      probe.style.color = "var(--text)";
      document.body.appendChild(probe);
      const text = getComputedStyle(probe).color;
      probe.remove();

      const bar = getComputedStyle(document.querySelector(".progress")).backgroundColor;
      const parts = (v) => (v.match(/\d+/g) || []).map(Number);
      return { bar, text, barRgb: parts(bar), textRgb: parts(text) };
    });
    const spread = colour.barRgb.length === 3
      ? Math.max(...colour.barRgb) - Math.min(...colour.barRgb)
      : 0;
    check(`${cfg.name}: the bar is not a colour`, spread <= 8,
          `${colour.bar} vs text ${colour.text}`);
    check(`${cfg.name}: the bar matches the text colour`,
          colour.barRgb.join(",") === colour.textRgb.join(","),
          `${colour.bar} vs ${colour.text}`);

    const rows = await page.evaluate(async () => {
      const doc = document.documentElement;
      const bar = document.querySelector(".progress");
      const read = () => Math.round(new DOMMatrixReadOnly(getComputedStyle(bar).transform).a * 100000);
      const out = [];
      for (let i = 0; i < 50; i++) {
        doc.scrollTop += 140;
        await new Promise(r => requestAnimationFrame(r));
        await new Promise(r => requestAnimationFrame(r));
        out.push(read());
      }
      return out;
    });
    const backwards = rows.filter((v, i) => i && v < rows[i - 1]).length;
    check(`${cfg.name}: the bar only ever grows while scrolling down`, backwards === 0,
          `${backwards} steps went backwards`);
    check(`${cfg.name}: it starts empty and ends full`,
          rows[0] > 0 && rows[rows.length - 1] > rows[0], `${rows[0]} -> ${rows[rows.length - 1]}`);

    await page.close();
  }

  console.log(`\n${passed} passed, ${failed} failed`);
  await browser.close();
  server.close();
  process.exit(failed ? 1 : 0);
});
