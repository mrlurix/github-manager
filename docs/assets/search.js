/* Client-side search over the Persian-normalised index built by
   tools/build_docs.py. The normaliser here mirrors the Python one so that the
   query and the stored text are folded identically. */

/* eslint-env browser */
(function () {
  "use strict";

  var ZWNJ = "‌";
  var DIACRITICS = /[ً-ٰٟۖ-ۭ]/g;
  var TATWEEL = /ـ+/g;
  var PUNCT = /[^\w\s؀-ۿ]+/g;

  /** Fold Persian text: Arabic yeh/kaf, ZWNJ, diacritics, digits. */
  function normalise(text) {
    if (!text) return "";
    var value = String(text).normalize ? String(text).normalize("NFKC") : String(text);
    var out = "";
    for (var i = 0; i < value.length; i++) {
      var ch = value[i];
      var code = value.charCodeAt(i);
      // Arabic-Indic and Extended Arabic-Indic digits become ASCII.
      if (code >= 0x0660 && code <= 0x0669) { out += String(code - 0x0660); continue; }
      if (code >= 0x06f0 && code <= 0x06f9) { out += String(code - 0x06f0); continue; }
      switch (ch) {
        case "ي": case "ى": out += "ی"; break;   // ARABIC YEH / ALEF MAKSURA
        case "ك": case "ﮐ": case "ﮑ": out += "ک"; break;
        case "ة": out += "ه"; break;                // TEH MARBUTA
        case "ؤ": out += "و"; break;
        case "إ": case "أ": case "آ": out += "ا"; break;
        case ZWNJ: out += " "; break;               // ZERO WIDTH NON-JOINER
        default: out += ch;
      }
    }
    return out
      .replace(DIACRITICS, "")
      .replace(TATWEEL, "")
      .replace(PUNCT, " ")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  /** Split a query into terms, so all terms must appear (AND). */
  function terms(query) {
    return normalise(query).split(" ").filter(function (t) { return t.length > 0; });
  }

  var State = { entries: null, loading: false, cache: null };

  function load(cb) {
    if (State.entries) return cb(State.entries);
    if (State.loading) return;
    State.loading = true;
    fetch("search-index.json")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        State.entries = data.map(function (e) {
          return {
            url: e.url,
            page: e.page,
            title: e.title,
            heading: e.heading || "",
            raw: e.raw || e.text || "",
            haystack: normalise((e.title || "") + " " + (e.heading || "") + " " + (e.text || ""))
          };
        });
        State.loading = false;
        cb(State.entries);
      })
      .catch(function () {
        State.loading = false;
        cb([]);
      });
  }

  /** Score an entry: title hits weigh more than body hits. */
  function score(entry, words) {
    // No terms means no query. Without this an entry with a heading scores 2
    // from the heading bonus alone and an empty search would return results.
    if (!words || !words.length) return 0;
    var title = normalise(entry.title + " " + entry.heading);
    var total = 0;
    for (var i = 0; i < words.length; i++) {
      var w = words[i];
      var inTitle = title.indexOf(w);
      var inBody = entry.haystack.indexOf(w);
      if (inTitle === -1 && inBody === -1) return 0;   // every term must appear
      if (inTitle !== -1) total += 10 - Math.min(9, inTitle);
      else total += 4;
      // Whole-word hits beat a substring in the middle of another word.
      if ((" " + entry.haystack).indexOf(" " + w) !== -1) total += 3;
    }
    if (entry.heading) total += 2;
    return total;
  }

  /** Pull a readable excerpt around the first matching term. */
  function locate(entry, words) {
    var raw = entry.raw || "";
    var lower = raw.toLowerCase();
    for (var i = 0; i < words.length; i++) {
      // Prefer a hit in the original text so the excerpt keeps its ZWNJ and
      // vowel marks; fall back to the folded text when the query was typed
      // with Arabic yeh/kaf.
      var at = lower.indexOf(words[i]);
      if (at !== -1) {
        return { text: raw, at: at, word: words[i] };
      }
      var folded = normalise(raw);
      var foldedAt = folded.indexOf(words[i]);
      if (foldedAt !== -1) {
        return { text: folded, at: foldedAt, word: words[i] };
      }
    }
    return { text: raw, at: 0, word: words[0] || "" };
  }

  function snippet(entry, words) {
    var found = locate(entry, words);
    var from = Math.max(0, found.at - 45);
    var out = (from > 0 ? "…" : "") + found.text.slice(from, from + 165);
    return out + (from + 165 < found.text.length ? "…" : "");
  }

  window.DocSearch = {
    normalise: normalise,
    terms: terms,
    load: load,
    score: score,
    locate: locate,
    snippet: snippet,
    highlight: function (text, words) {
      var safe = String(text).replace(/[&<>"]/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
      });
      if (!words.length) return safe;
      var alt = words.map(function (w) {
        return w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      }).join("|");
      return safe.replace(new RegExp("(" + alt + ")", "gi"), "<mark>$1</mark>");
    }
  };
})();