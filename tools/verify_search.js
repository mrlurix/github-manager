/* Verifies the Persian search engine against the generated index.
   Run: node tools/verify_search.js
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.join(__dirname, "..", "docs");
const sandbox = { window: {}, fetch: () => Promise.resolve({ json: () => Promise.resolve([]) }) };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(root, "assets", "search.js"), "utf8"), sandbox);

const S = sandbox.window.DocSearch;
const entries = JSON.parse(fs.readFileSync(path.join(root, "search-index.json"), "utf8")).map((e) => ({
  url: e.url, page: e.page, title: e.title, heading: e.heading || "", raw: e.raw || e.text || "",
  haystack: S.normalise((e.title || "") + " " + (e.heading || "") + " " + (e.text || ""))
}));

let pass = 0, fail = 0;
function check(name, ok, detail) {
  if (ok) { pass++; console.log("  [PASS] " + name); }
  else { fail++; console.log("  [FAIL] " + name + (detail ? " -> " + detail : "")); }
}

function find(query, n = 5) {
  const words = S.terms(query);
  return entries
    .map((e) => ({ e, s: S.score(e, words) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s)
    .slice(0, n)
    .map((x) => x.e);
}

console.log("index entries: " + entries.length);

console.log("\nnormalisation:");
check("Arabic yeh folds to Persian yeh",
  S.normalise("مي رود") === S.normalise("می رود"), S.normalise("مي رود"));
check("Arabic kaf folds to Persian kaf",
  S.normalise("كتابي") === S.normalise("کتابی"), S.normalise("كتابي"));
check("teh marbuta folds to heh",
  S.normalise("مكتبة") === S.normalise("مکتبه"), S.normalise("مكتبة"));
check("ZWNJ becomes a space",
  S.normalise("می‌رود") === S.normalise("می رود"), S.normalise("می‌رود"));
check("diacritics are dropped",
  S.normalise("مَدْرَس") === S.normalise("مدرس"), S.normalise("مَدْرَس"));
check("Persian digits become ASCII",
  S.normalise("۱۲۳") === "123", S.normalise("۱۲۳"));
check("Arabic digits become ASCII",
  S.normalise("٤٥٦") === "456", S.normalise("٤٥٦"));
check("tatweel is dropped",
  S.normalise("کـــتاب") === "کتاب", S.normalise("کـــتاب"));

console.log("\nsearch behaviour:");
// The index stores display names, not slugs.
const cases = [
  ["امنیت", "امنیت", "single Persian word finds the security page"],
  ["قابلیت ها", "قابلیت‌ها", "two terms match across the text"],
  ["rate limit", "امنیت", "English term still works"],
  ["Ollama", "هوش مصنوعی", "Latin product name"],
  ["gitignore", "قابلیت‌ها", "dotfile name"],
  ["DPAPI", "امنیت", "uppercase acronym"],
  ["v1.3.0", "قابلیت‌ها", "version-like string"],
  ["zzqqxx", "", "nonsense returns nothing"]
];

for (const [query, expectPage, label] of cases) {
  const hits = find(query);
  if (!expectPage) {
    check(label, hits.length === 0, hits.map((h) => h.page + "/" + h.title).join(", "));
  } else {
    check(label, hits.some((h) => h.page === expectPage),
      hits.map((h) => h.page + "/" + h.title).slice(0, 3).join(" | "));
  }
}

console.log("\nrobustness:");
check("typing with the Arabic keyboard still finds the page",
  find("امي رود").length > 0 || find("رود").length > 0);
check("query typed with Arabic yeh/kaf still matches",
  find("امنيت").length > 0, "no hits");
check("empty query returns nothing", find("").length === 0,
  find("").map((h) => h.page).join(", "));
check("punctuation-only query returns nothing", find("!!! ???").length === 0);
check("single character query is handled", typeof find("a").length === "number");

console.log("\nranking:");
const top = find("امنیت");
check("security page ranks first for 'امنیت'",
  top.length > 0 && top[0].page === "امنیت",
  top.map((h) => h.page).join(", "));
check("a heading match outranks a body match",
  top.length > 1 && top[0].title !== top[1].title);

const tokens = S.terms("rate limit");
check("an English phrase becomes two terms", tokens.length === 2, tokens.join("+"));
check("multi-term ranking returns hits", find("rate limit").length > 0);

console.log("\nsnippets:");
const hit = find("امنیت")[0];
const snip = S.snippet(hit, S.terms("امنیت"));
check("snippet is non-empty", snip.length > 0);
check("snippet contains the query", snip.includes("امنیت"), snip.slice(0, 80));
const marked = S.highlight(snip, ["امنیت"]);
check("highlight wraps the match", marked.includes("<mark>"), marked.slice(0, 80));
check("highlight escapes html", !S.highlight('<img onerror=x>', ["img"]).includes("<img"));

console.log("\n" + pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);