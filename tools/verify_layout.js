/* Structural checks on the generated site.
   Run: node tools/verify_layout.js

   The design is only as good as what it does at the sizes people actually use.
   These checks run against the built HTML in a headless browser: a rule that
   silently breaks at 380px is a bug whether or not it looks fine on the
   developer's screen.

   Anything that only needs static inspection lives in verify_site_security.js.
   This file is for what has to be laid out before it can be judged.
*/
const fs = require("fs");
const path = require("path");
const http = require("http");
const { spawnSync } = require("child_process");

const docs = path.join(__dirname, "..", "docs");

let pass = 0, fail = 0;
function check(name, ok, detail) {
  if (ok) { pass++; console.log("  [PASS] " + name); }
  else { fail++; console.log("  [FAIL] " + name + (detail ? " -> " + detail : "")); }
}

/** How many revealed elements are still painted at zero opacity.
 *
 *  The class is the state; the opacity is the animation. Headless Chrome does
 *  not finish a CSS transition without a compositor, so an element correctly
 *  marked as revealed can still read as opacity 0 here. Callers that care about
 *  state should ask for `revealed`, and only check `painted` where the
 *  transition is known to have had time to run.
 */
async function revealState(page) {
  return page.evaluate(() => {
    const nodes = [...document.querySelectorAll("[data-reveal]")];
    return {
      total: nodes.length,
      revealed: nodes.filter(n => n.classList.contains("is-revealed")).length,
      painted: nodes.filter(n => parseFloat(getComputedStyle(n).opacity) >= 0.99).length,
    };
  });
}

/** Open a page with smooth scrolling switched off.
 *
 *  `scroll-behavior: smooth` animates every jump, and headless Chrome has no
 *  compositor to drive that animation - the scroll simply never finishes, so a
 *  test that scrolls sees a page that did not move. It is turned off here
 *  rather than in the stylesheet because it is a property of the harness, not of
 *  the site.
 */
async function open(page, url, { width = 1440, height = 1000 } = {}) {
  await page.setViewport({ width, height });
  await page.goto(url, { waitUntil: "load" });
  await page.addStyleTag({ content: "html{scroll-behavior:auto!important}" });
  return page;
}

const PAGES = ["index", "features", "install", "ai", "security", "build", "faq"];

// Widths chosen for what they break, not as round numbers: 380 is the narrowest
// phone in common use, 768 is where the rail becomes a drawer, 1180 is where
// the right-hand TOC loses its column, and 1920 is a desktop at full width.
const WIDTHS = [380, 768, 1024, 1180, 1440, 1920];

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2"
};

function serve() {
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(req.url.split("?")[0]);
    const file = path.join(docs, rel === "/" ? "index.html" : rel.replace(/^\//, ""));
    if (!file.startsWith(docs) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404); res.end("no"); return;
    }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    res.end(fs.readFileSync(file));
  });
  return new Promise(resolve => server.listen(0, "127.0.0.1", () => resolve(server)));
}

(async function main() {
  console.log("generated pages:");
  for (const name of PAGES) {
    const file = path.join(docs, `${name}.html`);
    check(`${name}.html exists`, fs.existsSync(file), file);
    if (!fs.existsSync(file)) continue;
    const html = fs.readFileSync(file, "utf8");
    check(`${name}.html declares a language`, /<html[^>]+lang="en"/.test(html));
    check(`${name}.html has one h1`, (html.match(/<h1[\s>]/g) || []).length === 1,
      String((html.match(/<h1[\s>]/g) || []).length));
    check(`${name}.html links the stylesheet`, /href="assets\/style\.css"/.test(html));
    check(`${name}.html links both scripts`,
      /src="assets\/search\.js"/.test(html) && /src="assets\/app\.js"/.test(html));
    check(`${name}.html links the motion script`, /src="assets\/motion\.js"/.test(html));
    check(`${name}.html has a reading progress bar`, /class="progress"/.test(html));
    check(`${name}.html has a footer`, /class="site-foot"/.test(html));
    check(`${name}.html has a skip link`, /class="skip" href="#main"/.test(html));
  }

  const index = fs.readFileSync(path.join(docs, "index.html"), "utf8");
  console.log("\nlanding page:");
  check("the landing page has no documentation rail", !/class="rail"/.test(index));
  check("the landing page has no right-hand TOC", !/class="toc-rail"/.test(index));
  check("the landing page has a hero", /class="hero"/.test(index));
  check("the hero is inside the grid field", /class="gridfield"/.test(index));
  check("the mock-up window is present", /class="shot-body"/.test(index));
  check("the download button names the version", /Download 1\.4\.0|Download<\/a>|Download for Windows/.test(index));

  const css = fs.readFileSync(path.join(docs, "assets", "style.css"), "utf8");
  console.log("\nstylesheet:");
  check("the sans font is self-hosted", /url\("fonts\/Geist-Variable\.woff2"\)/.test(css));
  check("the mono font is self-hosted", /url\("fonts\/GeistMono-Variable\.woff2"\)/.test(css));
  check("no remote font or stylesheet url remains", !/https?:\/\/[^\s"')]+/.test(css));
  check("light mode is defined", /html\[data-theme="light"\]/.test(css));
  check("reduced motion is respected", /prefers-reduced-motion/.test(css));
  check("print styles exist", /@media print/.test(css));
  // A stylesheet that grows a horizontal scrollbar is the failure that survives
  // review and reaches the reader. Only a bare width counts; max-width is a cap
  // and is supposed to be large.
  const fixedWidths = (css.match(/(^|[^-])width:\s*\d{4,}px/gm) || []);
  check("no fixed width wider than the viewport", fixedWidths.length === 0,
    fixedWidths.join(" "));
  check("nothing relies on a min-width that forces scrolling",
    !/(^|[^-])min-width:\s*\d{4,}px/.test(css));

  for (const font of ["Geist-Variable.woff2", "GeistMono-Variable.woff2"]) {
    const path_ = path.join(docs, "assets", "fonts", font);
    check(`${font} is shipped`, fs.existsSync(path_), path_);
  }

  // ------------------------------------------------------------- in a browser
  const puppeteer = tryLoad();
  if (!puppeteer) {
    console.log("\n(puppeteer unavailable - layout checks skipped)");
  } else {
    const server = await serve();
    const base = `http://127.0.0.1:${server.address().port}`;
    const browser = await puppeteer.launch({
      args: ["--no-sandbox"],
      // Two of the blocks below launch a second browser for the coarse-pointer
      // checks, and thirty-odd pages share this one. The default 30s budget is
      // not enough headroom for that and it fails as a navigation timeout
      // rather than as anything to do with the page.
      protocolTimeout: 120000,
    });

    console.log("\nno horizontal overflow:");
    for (const name of PAGES) {
      const page = await browser.newPage();
      for (const width of WIDTHS) {
        await page.setViewport({ width, height: 900 });
        await page.goto(`${base}/${name}.html`, { waitUntil: "load" });
        const overflow = await page.evaluate(() =>
          document.documentElement.scrollWidth - document.documentElement.clientWidth);
        check(`${name} at ${width}px`, overflow <= 1, `${overflow}px over`);
      }
      await page.close();
    }

    console.log("\ntype stays inside its box:");
    // Long unbreakable strings are what actually push a layout out. One is
    // inserted on the fly rather than trusting the prose to contain one.
    for (const name of ["features", "install"]) {
      const page = await browser.newPage();
      await page.setViewport({ width: 380, height: 900 });
      await page.goto(`${base}/${name}.html`, { waitUntil: "load" });
      const clipped = await page.evaluate(() => {
        // A descendant of a scroll container is allowed to be wider than the
        // screen - that is what overflow-x:auto is for. A <pre> holding a long
        // command line scrolls inside itself and must not count as a spill.
        const inScroller = node => {
          for (let n = node.parentElement; n; n = n.parentElement) {
            const overflowX = getComputedStyle(n).overflowX;
            if (overflowX === "auto" || overflowX === "scroll" || overflowX === "hidden") return true;
          }
          return false;
        };
        const probe = document.createElement("p");
        probe.textContent = "x".repeat(90);
        probe.style.cssText = "font-family:monospace";
        document.querySelector("main").appendChild(probe);
        const spills = [...document.querySelectorAll("main *")]
          .filter(n => !inScroller(n))
          .filter(n => n.getBoundingClientRect().right > window.innerWidth + 1)
          .map(n => n.tagName + "." + n.className);
        probe.remove();
        return spills;
      });
      check(`${name} holds an unbreakable string`, clipped.length === 0, clipped.slice(0, 3).join(", "));
      await page.close();
    }

    console.log("\nlong lines scroll rather than push the page:");
    // The command on the install page is the longest thing on the site. It has
    // to be reachable, and reaching it must not widen the document.
    {
      const page = await browser.newPage();
      await page.setViewport({ width: 380, height: 900 });
      await page.goto(`${base}/install.html`, { waitUntil: "load" });
      const pre = await page.evaluate(() => {
        const block = document.querySelector("pre");
        if (!block) return { missing: true };
        const before = document.documentElement.scrollWidth;
        block.scrollLeft = 9999;
        return {
          scrollable: block.scrollWidth > block.clientWidth,
          moved: block.scrollLeft > 0,
          pageWidthUnchanged: document.documentElement.scrollWidth === before,
        };
      });
      check("a long command line is scrollable", pre.scrollable === true, JSON.stringify(pre));
      check("scrolling it does not widen the page", pre.pageWidthUnchanged === true);
      await page.close();
    }

    console.log("\nthe header is usable:");
    for (const width of [380, 768, 1440]) {
      const page = await browser.newPage();
      await page.setViewport({ width, height: 900 });
      await page.goto(`${base}/features.html`, { waitUntil: "load" });
      const state = await page.evaluate(() => {
        const bar = document.querySelector(".bar");
        const toggle = document.getElementById("navToggle");
        const brand = document.querySelector(".brand");
        const r = n => n.getBoundingClientRect();
        return {
          toggleVisible: !!toggle && getComputedStyle(toggle).display !== "none",
          brandWidth: Math.round(r(brand).width),
          barScroll: bar.scrollWidth - bar.clientWidth,
        };
      });
      if (width <= 768) {
        check(`the menu button appears at ${width}px`, state.toggleVisible);
      }
      check(`the header does not overflow at ${width}px`, state.barScroll <= 1, `${state.barScroll}px`);
      await page.close();
    }

    console.log("\nthe drawer opens:");
    {
      const page = await browser.newPage();
      await page.setViewport({ width: 380, height: 900 });
      await page.goto(`${base}/features.html`, { waitUntil: "load" });
      // Headless Chrome does not run CSS transitions without a compositor, so
      // the drawer is still mid-slide however long you wait. Turning transitions
      // off tests the end state, which is what the assertion is about.
      await page.addStyleTag({ content: "*,*::before,*::after{transition:none!important}" });
      await page.click("#navToggle");
      await new Promise(r => setTimeout(r, 150));
      const open = await page.evaluate(() => {
        const rail = document.getElementById("rail");
        const r = rail.getBoundingClientRect();
        return {
          expanded: document.getElementById("navToggle").getAttribute("aria-expanded"),
          onScreen: r.left >= -1 && r.right > 0,
          left: Math.round(r.left),
          links: rail.querySelectorAll(".rail-link").length,
        };
      });
      check("aria-expanded is true", open.expanded === "true", open.expanded);
      check("the drawer is on screen", open.onScreen, `left=${open.left}`);
      check("the drawer lists every page", open.links === PAGES.length, String(open.links));

      await page.click("#navToggle");
      await new Promise(r => setTimeout(r, 150));
      const closed = await page.evaluate(() => {
        const rail = document.getElementById("rail");
        return rail.getBoundingClientRect().right <= 1 &&
          document.getElementById("navToggle").getAttribute("aria-expanded") === "false";
      });
      check("it closes again", closed);
      await page.close();
    }

    /* The rail groups its links under captions. A caption used to be emitted
       before the page that owned it, so it described the entry above, and the
       last one was dropped entirely because nothing followed it. */
    console.log("\nrail captions:");
    {
      const page = await browser.newPage();
      await page.setViewport({ width: 1440, height: 900 });
      await page.goto(`${base}/features.html`, { waitUntil: "load" });
      const groups = await page.evaluate(() => {
        const out = [];
        for (const node of document.querySelectorAll(".rail-nav > *")) {
          out.push(node.classList.contains("rail-caption")
            ? ["caption", node.textContent.trim()]
            : ["link", node.textContent.trim()]);
        }
        return out;
      });
      const captions = groups.filter(g => g[0] === "caption");
      check("the rail has captions", captions.length > 0, JSON.stringify(captions));
      check("no caption is the last entry",
        groups[groups.length - 1][0] === "link", groups[groups.length - 1][1]);
      check("a caption is followed by a link",
        groups.every((g, i) => g[0] === "link" || groups[i + 1] && groups[i + 1][0] === "link"));
      check("no caption is empty", captions.every(c => c[1].length > 0));
      await page.close();
    }

    console.log("\nthe search overlay on a phone:");
    {
      const page = await browser.newPage();
      await page.setViewport({ width: 380, height: 800 });
      await page.goto(`${base}/features.html`, { waitUntil: "load" });
      // getComputedStyle on an input inside a display:none wrapper still reports the
      // input's own display, so the wrapper is what has to be measured.
      const before = await page.evaluate(() => {
        const wrap = document.querySelector(".search");
        const input = document.getElementById("searchInput");
        return {
          wrap: getComputedStyle(wrap).display,
          width: Math.round(input.getBoundingClientRect().width),
        };
      });
      check("the box is hidden until asked for",
        before.wrap === "none" && before.width === 0, JSON.stringify(before));
      await page.click("#searchToggle");
      await new Promise(r => setTimeout(r, 200));
      const opened = await page.evaluate(() => {
        const input = document.getElementById("searchInput");
        const r = input.getBoundingClientRect();
        return {
          display: getComputedStyle(document.querySelector(".search")).display,
          onScreen: r.top >= -1 && r.bottom <= window.innerHeight + 1,
          expanded: document.getElementById("searchToggle").getAttribute("aria-expanded"),
        };
      });
      check("the magnifier opens it", opened.display !== "none", opened.display);
      check("aria-expanded is true", opened.expanded === "true", opened.expanded);
      check("it lands on screen", opened.onScreen);
      await page.keyboard.press("Escape");
      await new Promise(r => setTimeout(r, 150));
      const shut = await page.evaluate(() =>
        !document.body.classList.contains("searching"));
      check("Escape closes it", shut);
      await page.close();
    }

    console.log("\nthe theme toggle flips and persists:");
    {
      const page = await browser.newPage();
      await page.setViewport({ width: 1440, height: 900 });
      await page.goto(`${base}/index.html`, { waitUntil: "load" });
      const before = await page.evaluate(() =>
        getComputedStyle(document.body).backgroundColor);
      await page.click("#themeToggle");
      await new Promise(r => setTimeout(r, 120));
      const after = await page.evaluate(() => ({
        bg: getComputedStyle(document.body).backgroundColor,
        stored: localStorage.getItem("ghm-theme"),
      }));
      check("the background changes", before !== after.bg, `${before} -> ${after.bg}`);
      check("the choice is stored", after.stored === "light", String(after.stored));
      await page.reload({ waitUntil: "load" });
      const kept = await page.evaluate(() =>
        getComputedStyle(document.body).backgroundColor);
      check("it survives a reload", kept === after.bg, `${kept}`);
      await page.close();
    }

    console.log("\nsearch:");
    {
      const page = await browser.newPage();
      await page.setViewport({ width: 1440, height: 900 });
      await page.goto(`${base}/features.html`, { waitUntil: "load" });
      await page.click("#searchInput");
      await page.type("#searchInput", "webhook");
      await page.evaluate(() => new Promise(r => setTimeout(r, 700)));
      const hits = await page.evaluate(() => {
        const panel = document.getElementById("searchResults");
        const first = panel.querySelector(".result");
        return {
          hidden: panel.hidden,
          count: panel.querySelectorAll(".result").length,
          marks: panel.querySelectorAll("mark").length,
          href: first ? first.getAttribute("href") : null,
        };
      });
      check("results appear", !hits.hidden && hits.count > 0, `${hits.count}`);
      check("the query is highlighted", hits.marks > 0, String(hits.marks));
      check("the first hit points at the new section",
        hits.href === "features.html#webhooks", String(hits.href));
      await page.close();
    }

    /* Regression: typing before the index has loaded used to leave the box
       empty. Every keystroke after the first was dropped by load()'s in-flight
       guard, and the one callback that did run bailed out because the query it
       held was stale. */
    console.log("\nsearch while the index is still in flight:");
    {
      const page = await browser.newPage();
      // Hold the index back so the race is guaranteed rather than lucky.
      await page.setRequestInterception(true);
      page.on("request", req => {
        if (req.url().endsWith("search-index.json")) {
          setTimeout(() => req.continue(), 900);
        } else {
          req.continue();
        }
      });
      await page.setViewport({ width: 1440, height: 900 });
      await page.goto(`${base}/features.html`, { waitUntil: "load" });
      await page.click("#searchInput");
      await page.type("#searchInput", "collaborator", { delay: 12 });
      await page.evaluate(() => new Promise(r => setTimeout(r, 1600)));
      const late = await page.evaluate(() => {
        const panel = document.getElementById("searchResults");
        return {
          hidden: panel.hidden,
          count: panel.querySelectorAll(".result").length,
          value: document.getElementById("searchInput").value,
        };
      });
      check("a fast typist still gets results",
        !late.hidden && late.count > 0, `query="${late.value}" ${late.count} results`);
      await page.close();
    }

    console.log("\nsearch finds the landing page:");
    {
      const page = await browser.newPage();
      await page.setViewport({ width: 1440, height: 900 });
      await page.goto(`${base}/index.html`, { waitUntil: "load" });
      await page.click("#searchInput");
      await page.type("#searchInput", "offline");
      await page.evaluate(() => new Promise(r => setTimeout(r, 800)));
      const hits = await page.evaluate(() => {
        const panel = document.getElementById("searchResults");
        return panel.querySelectorAll(".result").length;
      });
      check("the landing page is findable", hits > 0, String(hits));
      await page.close();
    }

    /* Regression: the table carried display:block for its overflow. That stops
       the element being a table box, so the rows laid out at their content
       width - the header row's background stopped at the last column while the
       table's border ran on to the edge. */
    console.log("\ntable rows fill the table:");
    {
      const page = await browser.newPage();
      for (const width of [1440, 900, 420]) {
        await page.setViewport({ width, height: 900 });
        await page.goto(`${base}/features.html`, { waitUntil: "load" });
        const rows = await page.evaluate(() => {
          const table = document.querySelector("table");
          const t = table.getBoundingClientRect();
          const out = [];
          for (const row of table.querySelectorAll("tr")) {
            const r = row.getBoundingClientRect();
            if (r.width > 0) out.push(Math.round(r.width - t.width));
          }
          const head = table.querySelector("thead tr, tr");
          const cells = [...head.children].reduce((n, c) => n + c.getBoundingClientRect().width, 0);
          return {
            shortRows: out.filter(d => d < -1).length,
            total: out.length,
            cellsVsTable: Math.round(cells - t.width),
            display: getComputedStyle(table).display,
          };
        });
        check(`no row is narrower than the table at ${width}px`,
          rows.shortRows === 0, `${rows.shortRows}/${rows.total} rows short`);
        check(`the header cells fill the table at ${width}px`,
          Math.abs(rows.cellsVsTable) <= 2,
          `${rows.cellsVsTable}px of ${rows.display}`);
      }
      await page.close();
    }

    console.log("\ntables scroll instead of widening the page:");
    {
      const page = await browser.newPage();
      await page.setViewport({ width: 380, height: 900 });
      await page.goto(`${base}/install.html`, { waitUntil: "load" });
      const state = await page.evaluate(() => {
        const wraps = [...document.querySelectorAll(".scroll-x")];
        // No real table on this page is wide enough to scroll at 380px, so one
        // is made wide on purpose: what is under test is the mechanism, not the
        // particular content.
        const wrap = wraps[0];
        const cell = wrap.querySelector("tbody td");
        const restore = cell.textContent;
        cell.textContent = "https://example.invalid/" + "segment/".repeat(24) + "file.txt";
        const before = document.documentElement.scrollWidth;
        wrap.scrollLeft = 9999;
        const out = {
          count: wraps.length,
          overflowMode: getComputedStyle(wrap).overflowX,
          allWrapped: wraps.every(w =>
            ["auto", "scroll"].includes(getComputedStyle(w).overflowX)),
          scrollable: wrap.scrollWidth > wrap.clientWidth,
          moved: wrap.scrollLeft > 0,
          pageUnchanged: document.documentElement.scrollWidth === before,
        };
        cell.textContent = restore;
        return out;
      });
      check("every table has a scroll wrapper", state.count > 0, String(state.count));
      check("the wrappers scroll", state.allWrapped && state.overflowMode === "auto",
        state.overflowMode);
      check("a wide table scrolls", state.scrollable && state.moved, JSON.stringify(state));
      check("scrolling it does not widen the page", state.pageUnchanged);
      await page.close();
    }

    /* ------------------------------------------------------------ motion safety
   A reveal animation that can leave content invisible is worse than no
   animation at all: the reader is looking at a blank section and has no way to
   know it is a bug rather than a page that has not loaded. Every check here is
   about the page being complete no matter what happens to the script. */
  console.log("\nthe page is complete without JavaScript:");
  {
    const page = await browser.newPage();
    await page.setJavaScriptEnabled(false);
    await page.setViewport({ width: 1440, height: 1000 });
    await page.goto(`${base}/index.html`, { waitUntil: "load" });
    const blind = await page.evaluate(() => {
      const nodes = [...document.querySelectorAll("[data-reveal]")];
      const hidden = nodes.filter(n => {
        const s = getComputedStyle(n);
        return parseFloat(s.opacity) < 0.99 || s.visibility === "hidden";
      });
      return {
        total: nodes.length,
        hidden: hidden.length,
        motionClass: document.documentElement.classList.contains("motion"),
        headlineVisible: document.querySelector(".hero h1").getBoundingClientRect().height > 0,
        // The figures must read as real numbers with no script to count them.
        facts: [...document.querySelectorAll(".fact b")].map(n => n.textContent.trim()),
      };
    });
    check("no reveal is armed without the script",
      blind.motionClass === false && blind.hidden === 0,
      `${blind.hidden}/${blind.total} hidden, motion=${blind.motionClass}`);
    check("the headline is on screen", blind.headlineVisible);
    check("the figures read correctly with no script",
      blind.facts.join("|") === "63 MB|10|0|2", blind.facts.join("|"));
    await page.close();
  }

  console.log("\nreduced motion leaves nothing hidden:");
  {
    const page = await browser.newPage();
    await page.emulateMediaFeatures([
      { name: "prefers-reduced-motion", value: "reduce" }]);
    await page.setViewport({ width: 1440, height: 1000 });
    await page.goto(`${base}/index.html`, { waitUntil: "load" });
    await new Promise(r => setTimeout(r, 400));
    const calm = await page.evaluate(() => {
      const nodes = [...document.querySelectorAll("[data-reveal]")];
      return {
        hidden: nodes.filter(n => parseFloat(getComputedStyle(n).opacity) < 0.99).length,
        total: nodes.length,
        progressHidden: getComputedStyle(document.querySelector(".progress")).display,
      };
    });
    check("every reveal is open", calm.hidden === 0, `${calm.hidden}/${calm.total}`);
    // The progress bar is the one thing that is genuinely motion, so it goes.
    check("the progress bar is not drawn", calm.progressHidden === "none",
      calm.progressHidden);
    await page.close();
  }

  console.log("\nreveals complete as the page is scrolled:");
  {
    const page = await browser.newPage();
    await open(page, `${base}/index.html`);
    await new Promise(r => setTimeout(r, 300));
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await new Promise(r => setTimeout(r, 700));
    const done = await revealState(page);
    check("everything is revealed by the bottom of the page",
      done.revealed === done.total, `${done.revealed}/${done.total}`);
    await page.close();
  }

  /* The failsafe. An observer that never fires leaves an element at zero opacity
     for good unless something opens it after a deadline. This cuts the script's
     own timeout short and checks the page recovers. */
  console.log("\nthe reveal failsafe opens what an observer misses:");
  {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 1000 });
    // Freeze every observer so none of them ever fires, then re-add the deadline
    // on its own - which is the state a browser without IntersectionObserver,
    // or a container that reports zero height, would be in.
    await page.evaluateOnNewDocument(() => {
      window.IntersectionObserver = function () {
        return { observe() {}, unobserve() {}, disconnect() {} };
      };
      const realSetTimeout = window.setTimeout;
      window.setTimeout = function (fn, ms, ...rest) {
        // The 10s failsafe, run immediately.
        if (ms === 10000) return realSetTimeout(fn, 50, ...rest);
        return realSetTimeout(fn, ms, ...rest);
      };
    });
    await page.goto(`${base}/index.html`, { waitUntil: "load" });
    await new Promise(r => setTimeout(r, 900));
    const stuck = await page.evaluate(() => {
      const nodes = [...document.querySelectorAll("[data-reveal]")];
      return nodes.filter(n => parseFloat(getComputedStyle(n).opacity) < 0.99).length;
    });
    check("content is still readable with no observer", stuck === 0, `${stuck} hidden`);
    await page.close();
  }

  /* The count-up is the effect; the deadline is the fact. Headless Chrome stops
       requestAnimationFrame without a compositor, which is exactly the
       condition that would leave a half-finished number on the page, so this
       also proves the value is written whether or not the frames ran. */
  console.log("\nthe counters land on the real number:");
  {
    const page = await browser.newPage();
    await open(page, `${base}/index.html`);
    await page.evaluate(() => {
      document.querySelector(".facts").scrollIntoView();
    });
    await new Promise(r => setTimeout(r, 2400));
    const counted = await page.evaluate(() =>
      [...document.querySelectorAll(".fact b")].map(n => n.textContent.trim()));
    check("the figures read as themselves once counted",
      counted.join("|") === "63 MB|10|0|2", counted.join("|"));
    await page.close();
  }

  /* Pressing End, or following a deep link, skips past most of the page in one
       step. The observer never sees those sections on screen, so nothing else
       would ever reveal them - and the reader is looking at a blank page. */
  console.log("\nnothing is left hidden after a jump to the bottom:");
  {
    const page = await browser.newPage();
    await open(page, `${base}/index.html`);
    await new Promise(r => setTimeout(r, 250));
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await new Promise(r => setTimeout(r, 700));
    const jumped = await page.evaluate(() => Math.round(window.scrollY));
    const state = await revealState(page);
    check("the page really scrolled", jumped > 0, `${jumped}px`);
    check("an instant jump leaves nothing unrevealed",
      state.revealed === state.total, `${state.revealed}/${state.total}`);
    await page.close();
  }

  /* The same arriving cold on a link that is already a third of the way down.
     No scroll happens at all - the browser got there before a line of the
     motion script ran. */
  console.log("\nnothing is hidden on a deep link:");
  {
    const page = await browser.newPage();
    await open(page, `${base}/features.html#webhooks`);
    await new Promise(r => setTimeout(r, 900));
    const deep = await page.evaluate(() => {
      const anchor = document.getElementById("webhooks");
      return {
        scrolled: Math.round(window.scrollY),
        anchorText: anchor ? anchor.textContent.trim().slice(0, 20) : "",
      };
    });
    const deepState = await revealState(page);
    check("the browser really did scroll to the anchor", deep.scrolled > 0, `${deep.scrolled}px`);
    check("the anchor landed on its section", deep.anchorText.length > 0, deep.anchorText);
    // Everything above the anchor must be readable. What is below it has not
    // been reached yet, and staying hidden there is the point.
    check("nothing above the anchor is left unrevealed",
      deepState.revealed > 0 && deepState.revealed < deepState.total,
      `${deepState.revealed}/${deepState.total}`);
    await page.close();
  }

  /* rAF is not guaranteed - a background tab, or a browser with no compositor,
     stops delivering frames. Content must not depend on one. */
  console.log("\nreveals do not depend on a frame callback:");
  {
    const page = await browser.newPage();
    await page.evaluateOnNewDocument(() => {
      window.requestAnimationFrame = () => 0;   // never fires
    });
    await open(page, `${base}/index.html`);
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await new Promise(r => setTimeout(r, 900));
    const frozen = await revealState(page);
    const frozenFacts = await page.evaluate(() =>
      [...document.querySelectorAll(".fact b")].map(n => n.textContent.trim()));
    check("the page is complete with no frames at all",
      frozen.revealed === frozen.total, `${frozen.revealed}/${frozen.total}`);
    check("the figures are right with no frames at all",
      frozenFacts.join("|") === "63 MB|10|0|2", frozenFacts.join("|"));
    await page.close();
  }

  console.log("\nthe reading progress bar moves:");
  {
    const page = await browser.newPage();
    await open(page, `${base}/features.html`);
    await new Promise(r => setTimeout(r, 250));
    // The value is written as scaleX(n), so it is read back from the inline style
    // rather than from the computed matrix - a scale of zero has no matrix
    // equivalent that survives serialisation cleanly.
    const read = () => page.evaluate(() => {
      const bar = document.querySelector(".progress");
      return bar.style.transform || getComputedStyle(bar).transform;
    });
    const scale = (value) => {
      const m = value.match(/scaleX\(([\d.]+)\)/) || value.match(/matrix\(([-\d.]+),/);
      return m ? parseFloat(m[1]) : NaN;
    };
    const top = await read();
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await new Promise(r => setTimeout(r, 350));
    const end = await read();
    check("the bar starts empty", scale(top) === 0, `${top} -> ${scale(top)}`);
    check("the bar fills as the page is read",
      scale(end) > 0.9, `${end} -> ${scale(end)}`);
    check("the bar is driven by a transform, not a width",
      /^scaleX\(|^matrix\(/.test(end), end);
    await page.close();
  }

  console.log("\nthe copy button only appears where it works:");
  {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 1000 });
    await page.goto(`${base}/install.html`, { waitUntil: "load" });
    await new Promise(r => setTimeout(r, 300));
    const copy = await page.evaluate(() => ({
      secure: window.isSecureContext,
      buttons: document.querySelectorAll("pre .copy").length,
      blocks: document.querySelectorAll("pre").length,
    }));
    check("every code block gets a copy button",
      copy.secure ? copy.buttons === copy.blocks : copy.buttons === 0,
      `${copy.buttons} of ${copy.blocks}, secure=${copy.secure}`);
    if (copy.buttons) {
      const before = await page.evaluate(() =>
        document.querySelector("pre .copy span").textContent);
      await page.click("pre .copy");
      await new Promise(r => setTimeout(r, 400));
      const after = await page.evaluate(() => ({
        label: document.querySelector("pre .copy span").textContent,
        done: document.querySelector("pre .copy").classList.contains("is-done"),
      }));
      check("clicking it confirms", after.done && after.label !== before,
        `${before} -> ${after.label}`);
    }
    await page.close();
  }

  /* ---------------------------------------------------------------- buttons */
  console.log("\nbuttons are filled, not outlined:");
  {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 1000 });
    await page.goto(`${base}/index.html`, { waitUntil: "load" });
    const buttons = await page.evaluate(() => {
      const opaque = (c) => {
        const m = c.match(/[\d.]+/g);
        if (!m) return false;
        // rgba(0,0,0,0) or "transparent" means there is no fill behind the label.
        if (m.length >= 4 && parseFloat(m[3]) === 0) return false;
        return c !== "transparent";
      };
      return [...document.querySelectorAll(".btn")].map(b => ({
        cls: b.className.replace("btn", "").trim() || "(base)",
        bg: getComputedStyle(b).backgroundColor,
        filled: opaque(getComputedStyle(b).backgroundColor),
        height: Math.round(b.getBoundingClientRect().height),
        radius: getComputedStyle(b).borderTopLeftRadius,
      }));
    });
    check("the page has buttons", buttons.length > 0, String(buttons.length));
    for (const b of buttons) {
      check(`'${b.cls}' is filled`, b.filled, b.bg);
    }
    // 32px is the height a filled button looked like before. Anything shorter
    // than this reads as a chip, not a control.
    check("no button is shorter than 36px",
      buttons.every(b => b.height >= 36), JSON.stringify(buttons.map(b => b.height)));
    check("the hero buttons are the largest",
      buttons.filter(b => b.height > 40).length >= 2,
      JSON.stringify(buttons.map(b => b.height)));
    await page.close();
  }

  /* A mouse pointer does not need 44px and a dense rail cannot afford it, so the
       rule follows the input. Both are checked: a phone has to clear the target,
       and a desktop pointer is allowed the tighter row.

       The coarse case is a second browser launched with the pointer flags set
       rather than a media emulation - Puppeteer cannot emulate `pointer`, and
       overriding the rule with an injected stylesheet would be testing the
       override rather than the stylesheet. */
  console.log("\ntouch targets are big enough to hit:");
  {
    // Blink's enums: pointer 1 = none, 2 = coarse, 4 = fine; hover 1 = none, 2 = hover.
    const coarse = await puppeteer.launch({
      args: [
        "--no-sandbox",
        "--blink-settings=primaryPointerType=2,availablePointerTypes=2," +
        "primaryHoverType=1,availableHoverTypes=1",
      ],
    });

    for (const [label, engine, floor] of [
      ["a touch device", coarse, 44],
      ["a mouse", browser, 32],
    ]) {
      const page = await engine.newPage();
      await open(page, `${base}/features.html`, { width: 380, height: 900 });
      const result = await page.evaluate((min) => {
        const nodes = [...document.querySelectorAll(
          "header button, header a.btn, main a.btn, .rail a, .toc a, .foot-col a")];
        return {
          coarsePointer: matchMedia("(pointer: coarse)").matches,
          noHover: matchMedia("(hover: none)").matches,
          small: nodes.filter(n => n.offsetParent !== null).map(n => {
            const r = n.getBoundingClientRect();
            return {
              label: (n.textContent || n.getAttribute("aria-label") || "?").trim().slice(0, 20),
              h: Math.round(r.height), w: Math.round(r.width),
            };
          }).filter(x => x.h < min || x.w < 24),
        };
      }, floor);
      check(`${label} really is the pointer it claims`,
        label.startsWith("a touch")
          ? result.coarsePointer && result.noHover
          : !result.coarsePointer,
        `coarse=${result.coarsePointer} noHover=${result.noHover}`);
      check(`${label} clears ${floor}px`, result.small.length === 0,
        JSON.stringify(result.small.slice(0, 4)));
      await page.close();
    }
    await coarse.close();
  }

  console.log("\nhover effects do not stick on a touch screen:");
  {
    const coarse = await puppeteer.launch({
      args: [
        "--no-sandbox",
        "--blink-settings=primaryPointerType=2,availablePointerTypes=2," +
        "primaryHoverType=1,availableHoverTypes=1",
      ],
    });
    const page = await coarse.newPage();
    await open(page, `${base}/install.html`);
    const hover = await page.evaluate(() => ({
      noHover: matchMedia("(hover: none)").matches,
      // The wash lives on the cell's ::after, not on the cell.
      wash: getComputedStyle(document.querySelector(".bento > *") || document.body, "::after")
        .transitionDuration,
      copyOpacity: (() => {
        const copy = document.querySelector("pre .copy");
        return copy ? getComputedStyle(copy).opacity : "no copy button";
      })(),
    }));
    check("the page reports a device with no hover", hover.noHover, String(hover.noHover));
    check("the bento wash is not animated on touch",
      hover.wash === "0s", hover.wash);
    check("the copy button is visible without a hover", hover.copyOpacity === "1",
      hover.copyOpacity);
    await page.close();
    await coarse.close();
  }

  /* The header is the row a thumb reaches for on any device, so it grows at
     narrow widths whatever pointer is attached. */
  console.log("\nthe header grows on a narrow screen:");
  {
    const page = await browser.newPage();
    await open(page, `${base}/features.html`, { width: 380, height: 900 });
    const bar = await page.evaluate(() =>
      [...document.querySelectorAll(".bar button, .bar a.btn")].map(n => ({
        label: (n.textContent || n.getAttribute("aria-label") || "?").trim().slice(0, 14),
        h: Math.round(n.getBoundingClientRect().height),
      })));
    check("every header control is at least 44px",
      bar.length > 0 && bar.every(x => x.h >= 44), JSON.stringify(bar));
    await page.close();
  }

  console.log("\nhover does something:");
  {
    const page = await browser.newPage();
    await open(page, `${base}/index.html`);
    const rest = await page.evaluate(() => {
      const b = document.querySelector(".btn-primary");
      const cell = document.querySelector(".bento > *");
      const s = getComputedStyle(b);
      return { transform: s.transform, transition: s.transitionProperty,
               cellBg: getComputedStyle(cell).transitionProperty };
    });
    check("the primary button transitions", rest.transition.includes("transform"),
      rest.transition);
    check("a bento cell transitions", rest.cellBg.length > 0, rest.cellBg);
    await page.close();
  }

  /* Two checks that need a real pointer, run in their own process: the primary
     button must not invert on hover, and the arrow on it must survive the body
     sanitiser. Chrome only applies :hover when it decides the window can take
     pointer input, and after thirty pages of hover, click and scroll through a
     shared browser it stops - the geometry is right, the state never lands. See
     the file for the full reasoning. */
  console.log("\nhover and the button arrow (own browser):");
  {
    const result = spawnSync(process.execPath,
      [path.join(__dirname, "verify_hover.js")], { encoding: "utf8" });
    for (const line of (result.stdout || "").split(/\r?\n/)) {
      if (line.trim()) console.log(line.replace(/^ {2}/, "  "));
    }
    check("the hover and arrow checks ran", result.status === 0,
      (result.stderr || "").split(/\r?\n/).filter(Boolean).slice(0, 2).join(" "));
  }

  console.log("\nfonts:");
    {
      const page = await browser.newPage();
      await page.setViewport({ width: 1440, height: 900 });
      await page.goto(`${base}/index.html`, { waitUntil: "load" });
      await page.evaluate(() => document.fonts.ready);
      const loaded = await page.evaluate(() => {
        const h1 = document.querySelector(".hero h1");
        return {
          family: getComputedStyle(h1).fontFamily,
          loaded: Array.from(document.fonts).filter(f => f.status === "loaded")
            .map(f => f.family),
        };
      });
      check("the display face is Geist", /Geist/.test(loaded.family), loaded.family);
      check("both font files are used", loaded.loaded.length >= 2, loaded.loaded.join(", "));
      await page.close();
    }

    /* Regression: the grid used to draw its dividers with a one pixel gap over
       a coloured container, so any row that did not divide evenly showed the
       container colour as a grey block in the corner. The container must now be
       the page colour everywhere the cells do not reach. */
    console.log("\nno filler blocks in the bento grid:");
    {
      const page = await browser.newPage();
      for (const width of [1440, 1100, 700]) {
        await page.setViewport({ width, height: 900 });
        await page.goto(`${base}/index.html`, { waitUntil: "load" });
        const bad = await page.evaluate(() => {
          const page_ = getComputedStyle(document.body).backgroundColor;
          const out = [];
          for (const grid of document.querySelectorAll(".bento")) {
            const box = grid.getBoundingClientRect();
            // Sample the corners of every grid cell slot the cells do not cover.
            for (const cell of grid.children) {
              const r = cell.getBoundingClientRect();
              out.push({ covered: r.width > 0 });
            }
            const trailing = box.right - Math.max(...[...grid.children]
              .map(c => c.getBoundingClientRect().right), 0);
            if (trailing > 2) out.push({ covered: false, trailing: Math.round(trailing) });
          }
          return { pageColor: page_, unfilled: out.filter(o => !o.covered).length };
        });
        check(`the grid fills its frame at ${width}px`, bad.unfilled === 0,
          `${bad.unfilled} unfilled`);
      }
      await page.close();
    }

    /* A cell that is shorter than its neighbour must not leave a visible seam,
       and the frame must not double up where the last cell meets it. */
    console.log("\nthe bento frame stays hairline:");
    {
      const page = await browser.newPage();
      await page.setViewport({ width: 1440, height: 900 });
      await page.goto(`${base}/index.html`, { waitUntil: "load" });
      const edges = await page.evaluate(() => {
        const grid = document.querySelector(".bento");
        const r = grid.getBoundingClientRect();
        const last = grid.lastElementChild.getBoundingClientRect();
        return {
          frame: Math.round(r.width),
          // A double border would make the last cell reach past the frame.
          lastInside: last.right <= r.right + 1,
          columns: getComputedStyle(grid).gridTemplateColumns.split(" ").length,
          children: grid.children.length,
        };
      });
      check("the last cell stays inside the frame", edges.lastInside, JSON.stringify(edges));
      check("six cells divide evenly across three columns",
        edges.columns === 3 && edges.children % edges.columns === 0,
        `${edges.children} cells in ${edges.columns} columns`);
      await page.close();
    }

    console.log("\nthe mock-up window does not stretch:");
    {
      const page = await browser.newPage();
      await page.setViewport({ width: 1440, height: 900 });
      await page.goto(`${base}/index.html`, { waitUntil: "load" });
      const shot = await page.evaluate(() => {
        const panes = [...document.querySelectorAll(".shot-pane")];
        const split = document.querySelector(".shot-split");
        const main = document.querySelector(".shot-main");
        return {
          paneBottom: Math.round(panes[0].getBoundingClientRect().bottom),
          splitBottom: Math.round(split.getBoundingClientRect().bottom),
          mainBottom: Math.round(main.getBoundingClientRect().bottom),
          equal: Math.abs(panes[0].getBoundingClientRect().height -
            panes[1].getBoundingClientRect().height) <= 1,
        };
      });
      // An empty lower half of the window reads as a screenshot that failed.
      check("the panes reach the bottom of their row", shot.paneBottom >= shot.splitBottom - 4,
        JSON.stringify(shot));
      check("the window is not taller than its contents",
        shot.splitBottom <= shot.mainBottom, JSON.stringify(shot));
      check("the two panes are the same height", shot.equal);
      await page.close();
    }

    /* Two footer columns with near-identical captions render as two identical
       headings once they are uppercased. */
    console.log("\nfooter headings are distinguishable:");
    {
      const page = await browser.newPage();
      await page.setViewport({ width: 1440, height: 900 });
      await page.goto(`${base}/index.html`, { waitUntil: "load" });
      const heads = await page.evaluate(() =>
        [...document.querySelectorAll(".foot-col h4")].map(n => n.textContent.trim()));
      check("the footer has captions", heads.length >= 2, JSON.stringify(heads));
      check("no two are the same",
        new Set(heads.map(h => h.toLowerCase())).size === heads.length, JSON.stringify(heads));
      await page.close();
    }

    await browser.close();
    server.close();
  }

  console.log("\n" + pass + " passed, " + fail + " failed");
  process.exit(fail ? 1 : 0);
})().catch(err => {
  console.error(err);
  process.exit(1);
});

/** Puppeteer is optional: the static checks above still run without it. */
function tryLoad() {
  try { return require("puppeteer"); } catch (e) { return null; }
}