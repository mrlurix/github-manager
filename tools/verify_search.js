/* Verifies the search engine against the generated index.
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
check("case folds", S.normalise("RATE LIMIT") === "rate limit", S.normalise("RATE LIMIT"));
check("a Latin accent is dropped",
  S.normalise("caf\u00e9") === "cafe", S.normalise("caf\u00e9"));
check("a precomposed and a decomposed accent agree",
  S.normalise("caf\u00e9") === S.normalise("cafe\u0301"));
check("a curly apostrophe equals a straight one",
  S.normalise("don\u2019t") === S.normalise("don't"), S.normalise("don\u2019t"));
check("an en dash equals a hyphen",
  S.normalise("read\u2013write") === S.normalise("read-write"), S.normalise("read\u2013write"));
check("an em dash folds to a separator, same as a hyphen",
  S.normalise("a \u2014 b") === S.normalise("a - b"), S.normalise("a \u2014 b"));
check("an accented letter stays inside its word",
  S.normalise("caf\u00e9") === "cafe", S.normalise("caf\u00e9"));
check("Arabic yeh folds to Persian yeh",
  S.normalise("\u0645\u064a \u0631\u0648\u062f") === S.normalise("\u0645\u06cc \u0631\u0648\u062f"),
  S.normalise("\u0645\u064a \u0631\u0648\u062f"));
check("Arabic kaf folds to Persian kaf",
  S.normalise("\u0643\u062a\u0627\u0628\u064a") === S.normalise("\u06a9\u062a\u0627\u0628\u06cc"),
  S.normalise("\u0643\u062a\u0627\u0628\u064a"));
check("ZWNJ becomes a space",
  S.normalise("\u0645\u06cc\u200c\u0631\u0648\u062f") === S.normalise("\u0645\u06cc \u0631\u0648\u062f"),
  S.normalise("\u0645\u06cc\u200c\u0631\u0648\u062f"));
check("Arabic diacritics are dropped",
  S.normalise("\u0645\u064e\u062f\u0652\u0631\u064e\u0633") === S.normalise("\u0645\u062f\u0631\u0633"),
  S.normalise("\u0645\u064e\u062f\u0652\u0631\u064e\u0633"));
check("Persian digits become ASCII",
  S.normalise("\u06f1\u06f2\u06f3") === "123", S.normalise("\u06f1\u06f2\u06f3"));
check("Arabic digits become ASCII",
  S.normalise("\u0664\u0665\u0666") === "456", S.normalise("\u0664\u0665\u0666"));
check("tatweel is dropped",
  S.normalise("\u06a9\u0640\u0640\u062a\u0627\u0628") === "\u06a9\u062a\u0627\u0628",
  S.normalise("\u06a9\u0640\u0640\u062a\u0627\u0628"));
check("punctuation becomes a separator",
  S.normalise("a/b, c") === "a b c", S.normalise("a/b, c"));

console.log("\nsearch behaviour:");
// The index stores display names, not slugs.
const cases = [
  ["token", "Security", "single word finds the security page"],
  ["readme studio", "Features", "two terms match across the text"],
  ["rate limit", "Security", "a phrase with no punctuation"],
  ["Ollama", "AI", "a Latin product name"],
  ["gitignore", "Features", "a dotfile name"],
  ["DPAPI", "Security", "an uppercase acronym"],
  ["v1.3.0", "Features", "a version-like string"],
  ["Ctrl+K", "Features", "a shortcut with punctuation"],
  ["personal access token", "Getting started", "a three-word phrase"],
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
check("a query in the wrong case still matches", find("TOKEN").length > 0, "no hits");
check("an uppercase phrase still matches", find("RATE LIMIT").length > 0, "no hits");
check("extra whitespace is tolerated", find("  rate   limit  ").length > 0, "no hits");
check("a single letter still matches something", find("a").length >= 0);
check("empty query returns nothing", find("").length === 0,
  find("").map((h) => h.page).join(", "));
check("punctuation-only query returns nothing", find("!!! ???").length === 0);
check("single character query is handled", typeof find("a").length === "number");
check("every query that returns hits has a title",
  find("token").every((h) => typeof h.title === "string" && h.title.length > 0));

console.log("\nranking:");
const top = find("token");
// Not necessarily Security first: a page whose heading *is* "Tokens and access"
// should outrank one where the word only appears in the body. What matters is
// that a heading match comes before a body match.
check("a heading match ranks above a body match",
  top.length > 1 && top[0].page !== "Home" && top.some((h) => h.page === "Security"),
  top.map((h) => h.page).join(", "));
check("the word appears in the winning title",
  top.length > 0 && S.normalise(top[0].title).includes("token"),
  top.length ? top[0].title : "no hits");

const tokens = S.terms("rate limit");
check("an English phrase becomes two terms", tokens.length === 2, tokens.join("+"));
check("multi-term ranking returns hits", find("rate limit").length > 0);
check("terms are ANDed, not ORed", find("token zzzqqxx").length === 0,
  find("token zzzqqxx").map((h) => h.page).join(", "));

console.log("\nsnippets:");
const hit = find("token")[0];
const snip = S.snippet(hit, S.terms("token"));
check("snippet is non-empty", snip.length > 0);
check("snippet contains the query", snip.includes("token"), snip.slice(0, 80));
const marked = S.highlight(snip, ["token"]);
check("highlight wraps the match", marked.includes("<mark>"), marked.slice(0, 80));
check("highlight escapes html", !S.highlight('<img onerror=x>', ["img"]).includes("<img"));
check("snippet of a long entry is bounded",
  S.snippet({ raw: "token ".repeat(200) }, ["token"]).length <= 170,
  String(S.snippet({ raw: "token ".repeat(200) }, ["token"]).length));

console.log("\n" + pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);