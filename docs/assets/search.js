/* Client-side search over the index built by tools/build_docs.py. The
   normaliser here mirrors the Python one step for step, so that a query and the
   stored text are folded identically. Both sides must agree: if they drift, a
   query silently stops matching text that is visibly right in front of you. */

/* eslint-env browser */
(function () {
  "use strict";

  var ZWNJ = "‌";
  var TATWEEL = /ـ+/g;
  /* Anything that is not a letter, a digit or a space. This has to be
     Unicode-aware: the ASCII \w class would cut an accented letter out of the
     middle of a word, so "café" would index as "caf" + "". */
  var PUNCT = /[^\p{L}\p{N}\s؀-ۿ]+/gu;
  /* Combining marks, dropped after NFD. Covers Latin accents and the Arabic
     vowel marks as well, since those are category Mn too. */
  var COMBINING = /\p{Mn}/gu;
  /* Characters that read as ASCII but are stored as something else, so a query
     typed with a straight apostrophe matches text written with a curly one. */
  var TYPOGRAPHIC = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "‒": "-", "−": "-",
    "‑": "-", "‐": "-", "⁃": "-"
  };

  /** Fold text so a loosely typed query still matches: case, accents,
      typographic punctuation and Arabic letter variants all collapse. */
  function normalise(text) {
    if (!text) return "";
    var value = String(text);
    if (value.normalize) {
      value = value.normalize("NFKC").normalize("NFD")
        .replace(COMBINING, "").normalize("NFC");
    }
    var out = "";
    for (var i = 0; i < value.length; i++) {
      var ch = value[i];
      var code = value.charCodeAt(i);
      // Arabic-Indic and Extended Arabic-Indic digits become ASCII.
      if (code >= 0x0660 && code <= 0x0669) { out += String(code - 0x0660); continue; }
      if (code >= 0x06f0 && code <= 0x06f9) { out += String(code - 0x06f0); continue; }
      if (Object.prototype.hasOwnProperty.call(TYPOGRAPHIC, ch)) {
        out += TYPOGRAPHIC[ch];
        continue;
      }
      switch (ch) {
        case "ي": case "ى": out += "ی"; break;   // ARABIC YEH / ALEF MAKSURA
        case "ك": case "ﭐ": case "ﮐ": case "ﮑ": out += "ک"; break;
        case "ة": out += "ه"; break;                // TEH MARBUTA
        case "ؤ": out += "و"; break;
        case "إ": case "أ": case "آ": out += "ا"; break;
        case ZWNJ: out += " "; break;               // ZERO WIDTH NON-JOINER
        default: out += ch;
      }
    }
    return out
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

  var State = { entries: null, loading: false };

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
    var lower = normalise(raw);
    for (var i = 0; i < words.length; i++) {
      // Prefer the folded text. In an English document the query and the text
      // differ only by case and accents, so the offsets line up with what the
      // reader will see in the excerpt.
      var foldedAt = lower.indexOf(words[i]);
      if (foldedAt !== -1) {
        return { text: lower, at: foldedAt, word: words[i] };
      }
    }
    return { text: normalise(raw), at: 0, word: words[0] || "" };
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