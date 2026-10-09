/* Verify the motion system end to end, against a local build.

   This exists because "the animations are gone" is not a report that can be
   acted on. A stylesheet can be full of transitions and match nothing; a script
   can run without error and reveal nothing; a rule can be live while its element
   sits at opacity 0. Every check below is something a reader would notice,
   measured the way a reader meets it.

   Three things have to hold at once:
     1. a normal visitor sees content fade in, not snap
     2. a reduced-motion visitor gets the same page, just stiller - including the
        copy button and the table-of-contents tracking
     3. no reveal is ever left invisible

   The second was a real bug: motion.js returned early when a visitor asked for
   less motion, which took the copy button and the TOC tracking with it. Those are
   a control and a piece of navigation, not decoration.

   Run: node tools/verify_motion.js   (needs: npm i --no-save puppeteer)
*/
const puppeteer = require("puppeteer");
const path = require("path"), fs = require("fs"), http = require("http"), crypto = require("crypto");
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
const sha = (b) => crypto.createHash("sha1").update(b).digest("hex").slice(0, 10);

const PAGES = ["index.html", "features.html", "install.html", "ai.html",
               "security.html", "faq.html", "build.html"];

server.listen(0, "127.0.0.1", async () => {
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await puppeteer.launch({ args: ["--no-sandbox"] });
  let pass = 0, fail = 0;
  const check = (name, ok, detail) => {
    (ok ? pass++ : fail++);
    console.log(`  [${ok ? "PASS" : "FAIL"}] ${name}${ok || !detail ? "" : " -> " + detail}`);
  };

  for (const mode of ["no-preference", "reduce"]) {
    console.log(`\n=== prefers-reduced-motion: ${mode} ===`);
    for (const p of PAGES) {
      const page = await browser.newPage();
      await page.setViewport({ width: 1280, height: 800 });
      await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: mode }]);
      const errors = [];
      page.on("pageerror", e => errors.push(e.message));
      await page.goto(`${base}/${p}`, { waitUntil: "load" });
      await page.addStyleTag({ content: "html{scroll-behavior:auto!important}" });
      await wait(1100);

      // ---- read the whole page the way a reader does
      const read = await page.evaluate(async () => {
        const step = window.innerHeight * 0.7;
        for (let y = 0; y < document.body.scrollHeight; y += step) {
          window.scrollTo(0, y);
          await new Promise(r => setTimeout(r, 120));
        }
        window.scrollTo(0, document.body.scrollHeight);
        await new Promise(r => setTimeout(r, 1300));
        const dim = Array.from(document.querySelectorAll("[data-reveal]"))
          .filter(n => parseFloat(getComputedStyle(n).opacity) < 0.98);
        return {
          total: document.querySelectorAll("[data-reveal]").length,
          dim: dim.length,
          copy: document.querySelectorAll("pre .copy").length,
          blocks: document.querySelectorAll("pre").length,
          tocLinks: document.querySelectorAll(".toc a").length,
          tocCurrent: document.querySelectorAll(".toc a.is-current").length,
          counters: Array.from(document.querySelectorAll("[data-count]")).map(n => n.textContent),
          motionClass: document.documentElement.classList.contains("motion"),
        };
      });

      check(`${p}: nothing left invisible`, read.dim === 0, `${read.dim} of ${read.total}`);
      // The controls must be there either way. This is the regression the fix
      // was for: the early return used to take them away.
      check(`${p}: copy buttons present`, read.copy === read.blocks,
            `${read.copy} of ${read.blocks}`);
      if (read.tocLinks) {
        check(`${p}: toc marks the current heading`, read.tocCurrent >= 1,
              `${read.tocCurrent} marked of ${read.tocLinks}`);
      }
      // Counters must show the real value in both modes.
      check(`${p}: counters show real values`,
            read.counters.every(t => t && t !== "0 MB"), read.counters.join(", "));
      check(`${p}: no script errors`, errors.length === 0, errors.join("; "));

      if (mode === "no-preference") {
        check(`${p}: html.motion is set`, read.motionClass, "reveals would never hide");
      } else {
        check(`${p}: html.motion not set`, !read.motionClass,
              "the stylesheet would hide content that nothing reveals");
      }
      await page.close();
    }
  }

  // ---- and confirm a normal visitor actually sees motion, in pixels
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });
  await page.goto(`${base}/index.html`, { waitUntil: "load" });
  await wait(1300);
  const a = await page.screenshot({ encoding: "binary" });
  await wait(1800);
  const b = await page.screenshot({ encoding: "binary" });
  check("ambient motion is visible (pixels change)", sha(a) !== sha(b), "identical frames");

  await page.evaluate(() => window.scrollTo({ top: document.body.scrollHeight * 0.5, behavior: "auto" }));
  await wait(140);
  const mid = await page.screenshot({ encoding: "binary" });
  await wait(800);
  const done = await page.screenshot({ encoding: "binary" });
  check("reveals fade in rather than snap", sha(mid) !== sha(done), "identical frames");
  await page.close();

  console.log(`\n${pass} passed, ${fail} failed`);
  await browser.close();
  server.close();
  process.exit(fail ? 1 : 0);
});
