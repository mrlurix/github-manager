/* Security checks for the documentation site's client script.
   Run: node tools/verify_site_security.js
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.join(__dirname, "..", "docs_src", "assets");
const source = fs.readFileSync(path.join(root, "app.js"), "utf8");

let pass = 0, fail = 0;
function check(name, ok, detail) {
  if (ok) { pass++; console.log("  [PASS] " + name); }
  else { fail++; console.log("  [FAIL] " + name + (detail ? " -> " + detail : "")); }
}

// Pull safeHref out of the file so the real implementation is what gets tested.
const match = source.match(/function safeHref\(url\)[\s\S]*?\n  \}/);
check("safeHref exists in app.js", !!match);
if (!match) { console.log("\n" + pass + " passed, " + fail + " failed"); process.exit(1); }

const escapeMatch = source.match(/function escapeHtml\(text\) \{[\s\S]*?\n  \}/);
check("escapeHtml exists in app.js", !!escapeMatch);
if (!escapeMatch) { console.log("\n" + pass + " passed, " + fail + " failed"); process.exit(1); }

const sandbox = {};
vm.createContext(sandbox);
// The real implementations, not stubs: a test against a stub only proves the
// stub is safe.
vm.runInContext(escapeMatch[0] + "\n" + match[0], sandbox);
const safeHref = sandbox.safeHref;
const escapeHtml = sandbox.escapeHtml;

console.log("\nattribute escaping:");
check("a plain relative page is kept", safeHref("features.html") === "features.html", safeHref("features.html"));
check("an anchor is kept", safeHref("security.html#rate-limits") === "security.html#rate-limits", safeHref("security.html#rate-limits"));
check("a bare fragment is kept", safeHref("#top") === "#top", safeHref("#top"));
check("an empty url degrades to #", safeHref("") === "#", safeHref(""));

console.log("\nscript urls are refused:");
for (const [name, bad] of Object.entries({
  "javascript": "javascript:alert(1)",
  "uppercase javascript": "JaVaScRiPt:alert(1)",
  "data html": "data:text/html,<script>alert(1)</script>",
  "vbscript": "vbscript:msgbox(1)",
  "file": "file:///C:/Windows/win.ini",
  "protocol relative": "//evil.example.com/x",
  "http absolute": "http://evil.example.com/x"
})) {
  const out = safeHref(bad);
  check(name + " is refused", out === "#", out);
}

console.log("\nescaping:");
check("double quotes are escaped", escapeHtml('a"b') === "a&quot;b", escapeHtml('a"b'));
check("single quotes are escaped", escapeHtml("a'b") === "a&#39;b", escapeHtml("a'b"));
check("angle brackets are escaped", escapeHtml("<b>") === "&lt;b&gt;", escapeHtml("<b>"));
check("ampersand is escaped", escapeHtml("a&b") === "a&amp;b", escapeHtml("a&b"));

console.log("\nquotes cannot break out of the attribute:");
for (const [name, bad] of Object.entries({
  'double quote': 'features.html" onmouseover="alert(1)',
  "single quote": "features.html' onmouseover='alert(1)",
  "space separated attr": "features.html onmouseover=alert(1)"
})) {
  const out = safeHref(bad);
  const noQuote = !out.includes('"') && !out.includes("'");
  check(name + " cannot escape the attribute", noQuote, out);
}

console.log("\nescaping blocks traversal out of the pages folder:");
for (const [name, bad] of Object.entries({
  "parent": "../secrets.html",
  "nested parent": "a/../../secrets.html",
  "absolute path": "/etc/passwd"
})) {
  check(name + " degrades to #", safeHref(bad) === "#", safeHref(bad));
}

console.log("\nno raw interpolation sinks:");
const sinks = source.match(/innerHTML|outerHTML|insertAdjacentHTML|document\.write|new Function|eval\(/g) || [];
check("the only sinks are innerHTML assignments", sinks.every(s => s === "innerHTML"), sinks.join(","));
check("the result href no longer interpolates hit.url raw",
  !/href="'\s*\+\s*hit\.url/.test(source));
check("the result href goes through safeHref", /href="'\s*\+\s*safeHref\(hit\.url\)/.test(source));
check("the page label is escaped", /escapeHtml\(hit\.page\)/.test(source));
check("the query is escaped", /escapeHtml\(query\)/.test(source));
check("keyboard navigation re-checks the href", /safeHref\(items\[active\]\.getAttribute/.test(source));

console.log("\ngenerated pages:");
const outDir = path.join(__dirname, "..", "docs");
if (fs.existsSync(outDir)) {
  const pages = fs.readdirSync(outDir).filter(f => f.endsWith(".html"));
  check("the site has pages", pages.length > 0, String(pages.length));
  for (const name of pages) {
    const html = fs.readFileSync(path.join(outDir, name), "utf8");
    check(name + " carries a CSP", /Content-Security-Policy/.test(html));
    check(name + " has no inline script", !/<script(?![^>]*\bsrc=)[^>]*>/i.test(html));
    check(name + " has no inline event handler",
      !/\son[a-z]+\s*=/i.test(html.replace(/<[^>]*>/g, "")));
    // Only attribute values count. The word "javascript:" legitimately appears in
    // the security page, where it documents the very thing being refused.
    const attrValues = (html.match(/(?:href|src|action|data)\s*=\s*["'][^"']*["']/gi) || [])
      .join(" ");
    check(name + " has no javascript: url", !/javascript\s*:/i.test(attrValues), attrValues.slice(0, 80));
    check(name + " has no data: url", !/data\s*:\s*text\/html/i.test(attrValues));
    check(name + " has no frame, object or form", !/<(iframe|object|embed|form|frame)\b/i.test(html));
    // Assets must be same-origin. Hyperlinks to github.com are the point of the
    // documentation, so only loaded resources are checked.
    const assets = (html.match(/<(?:script|img|link|iframe|source)\b[^>]*>/gi) || []).join(" ");
    const remoteAssets = assets.match(/(?:src|href)\s*=\s*["']https?:[^"']*/gi) || [];
    check(name + " loads no remote asset", remoteAssets.length === 0, remoteAssets.join(" | "));
    // Outbound links must not hand the opener window to the destination.
    const anchors = html.match(/<a\b[^>]*href\s*=\s*["']https?:[^>]*>/gi) || [];
    const unsafe = anchors.filter(a => !/rel\s*=\s*["'][^"']*noopener/i.test(a));
    check(name + " outbound links carry noopener", unsafe.length === 0, unsafe.join(" | "));
  }
} else {
  check("docs/ exists (run python tools/build_docs.py)", false, outDir);
}

console.log("\n" + pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);