/* Page behaviour: theme, mobile navigation and the search box. */
(function () {
  "use strict";

  var root = document.documentElement;
  var S = window.DocSearch;

  // ------------------------------------------------------------------ theme
  var stored = null;
  try { stored = localStorage.getItem("ghm-theme"); } catch (e) { /* private mode */ }
  var prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
  // Do not clobber a theme the page already declares; only fill in the default.
  if (!root.getAttribute("data-theme")) {
    root.setAttribute("data-theme", stored || (prefersLight ? "light" : "dark"));
  }
  // ?theme=light / ?theme=dark pins the theme, so a link can share one look.
  try {
    var forced = new URLSearchParams(window.location.search).get("theme");
    if (forced === "light" || forced === "dark") {
      root.setAttribute("data-theme", forced);
      localStorage.setItem("ghm-theme", forced);
    }
  } catch (e) { /* no query string support */ }

  var themeBtn = document.getElementById("themeToggle");
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("ghm-theme", next); } catch (e) { /* ignore */ }
    });
  }

  // ------------------------------------------------------------ mobile nav
  var toggle = document.getElementById("navToggle");
  var sidebar = document.getElementById("sidebar");
  if (toggle && sidebar) {
    toggle.addEventListener("click", function () {
      var open = sidebar.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    sidebar.addEventListener("click", function (event) {
      if (event.target.classList.contains("nav-link")) {
        sidebar.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  // ---------------------------------------------------------------- search
  var input = document.getElementById("searchInput");
  var panel = document.getElementById("searchResults");
  if (!input || !panel) return;

  var active = -1;
  var lastResults = [];

  function close() {
    panel.hidden = true;
    panel.innerHTML = "";
    active = -1;
    lastResults = [];
  }

  function render(hits, words, query) {
    if (!query.trim()) { close(); return; }
    if (!hits.length) {
      panel.innerHTML = '<p class="result-empty">No results for &ldquo;' +
        escapeHtml(query) + "&rdquo;.</p>";
      panel.hidden = false;
      return;
    }
    var html = "";
    for (var i = 0; i < hits.length; i++) {
      var hit = hits[i];
      var title = S.highlight(hit.title, words);
      var body = S.highlight(S.snippet(hit, words), words);
      html += '<a class="result" href="' + hit.url + '">' +
        '<span class="result-title"><span class="result-page">' +
        escapeHtml(hit.page) + "</span>" + title + "</span>" +
        (body ? '<span class="result-text">' + body + "</span>" : "") +
        "</a>";
    }
    panel.innerHTML = html;
    panel.hidden = false;
    active = -1;
    lastResults = hits;
  }

  function escapeHtml(text) {
    return String(text).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function search() {
    var query = input.value;
    var words = S.terms(query);
    if (!words.length) { close(); return; }
    S.load(function (entries) {
      if (input.value !== query) return;   // the user kept typing
      var hits = [];
      for (var i = 0; i < entries.length; i++) {
        var value = S.score(entries[i], words);
        if (value > 0) hits.push({ entry: entries[i], score: value });
      }
      hits.sort(function (a, b) { return b.score - a.score; });
      render(hits.slice(0, 12).map(function (h) { return h.entry; }), words, query);
    });
  }

  input.addEventListener("input", search);
  input.addEventListener("focus", function () { if (input.value) search(); });

  input.addEventListener("keydown", function (event) {
    var items = panel.querySelectorAll(".result");
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (items.length) { active = (active + 1) % items.length; mark(items); }
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (items.length) { active = (active - 1 + items.length) % items.length; mark(items); }
    } else if (event.key === "Enter" && active >= 0 && items[active]) {
      event.preventDefault();
      window.location.href = items[active].getAttribute("href");
    } else if (event.key === "Escape") {
      input.value = "";
      close();
      input.blur();
    }
  });

  function mark(items) {
    for (var i = 0; i < items.length; i++) {
      items[i].classList.toggle("is-active", i === active);
      if (i === active) items[i].scrollIntoView({ block: "nearest" });
    }
  }

  document.addEventListener("click", function (event) {
    if (!event.target.closest(".search")) close();
  });

  document.addEventListener("keydown", function (event) {
    var combo = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
    var slash = event.key === "/" && document.activeElement !== input &&
      !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if (combo || slash) {
      event.preventDefault();
      input.focus();
      input.select();
    }
    if (event.key === "Escape" && document.activeElement === input) {
      input.value = "";
      close();
      input.blur();
    }
  });

  // "/" hint on desktop.
  var hint = document.getElementById("searchHint");
  if (hint && window.matchMedia && !window.matchMedia("(max-width: 960px)").matches) {
    hint.textContent = "Ctrl K";
  }
})();