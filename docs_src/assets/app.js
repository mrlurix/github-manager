/* Page behaviour: theme, navigation and the search box.

   No framework and no build step, because the site is served straight from the
   folder. Everything here is defensive about its own DOM: a script that assumes
   an element exists will throw on the one page where it does not, and that
   takes the search box down with it. */
(function () {
  "use strict";

  var root = document.documentElement;
  var S = window.DocSearch;

  // ------------------------------------------------------------------ theme
  /* The theme is resolved before first paint by the markup, so this only fills
     in a default. A theme already on the element is one the reader chose and is
     not overwritten. */
  var stored = null;
  try { stored = localStorage.getItem("ghm-theme"); } catch (e) { /* private mode */ }
  var prefersLight = window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: light)").matches;
  if (!root.getAttribute("data-theme")) {
    root.setAttribute("data-theme", stored || (prefersLight ? "light" : "dark"));
  }
  /* ?theme=light / ?theme=dark pins the theme, so a link can share one look. */
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

  /* Following the system while the reader has expressed no preference of their
     own. Once they click the toggle, stored wins and this stops firing. */
  try {
    if (!stored && window.matchMedia) {
      var scheme = window.matchMedia("(prefers-color-scheme: light)");
      var onScheme = function (event) {
        try { if (localStorage.getItem("ghm-theme")) return; } catch (e) { return; }
        root.setAttribute("data-theme", event.matches ? "light" : "dark");
      };
      if (scheme.addEventListener) scheme.addEventListener("change", onScheme);
      else if (scheme.addListener) scheme.addListener(onScheme);
    }
  } catch (e) { /* ignore */ }

  // -------------------------------------------------------------- navigation
  /* One button, and the navigation is whatever this page has.

     A documentation page has the rail, a full-height column of every section,
     and the bar's own links are hidden at narrow widths to make room for it.
     The landing page has no rail by design, so at the same width its links were
     hidden and there was nothing left to open: the hamburger rendered, was
     clickable, and did absolutely nothing, and the page had no navigation at
     all on a phone.

     So the button drives whichever of the two exists rather than being wired to
     one of them. Same gesture, same result, on every page. */
  var toggle = document.getElementById("navToggle");
  var rail = document.getElementById("rail");
  var topNav = document.querySelector(".top-nav");
  var drawer = rail || topNav;

  function isOpen() {
    return drawer ? drawer.classList.contains("is-open") : false;
  }

  function setNav(open) {
    if (!drawer) return;
    drawer.classList.toggle("is-open", open);
    if (toggle) toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  if (toggle && drawer) {
    toggle.addEventListener("click", function () {
      setNav(!isOpen());
    });

    /* Choosing a destination closes the drawer: leaving it open over the page
       the reader just asked for would hide the result. */
    drawer.addEventListener("click", function (event) {
      if (event.target.closest("a")) setNav(false);
    });

    /* A tap outside dismisses it. The rail is a full-height panel over a
       scrim, so this mostly matters for the landing page's dropdown, where
       there is no scrim to tap. */
    document.addEventListener("click", function (event) {
      if (!isOpen()) return;
      if (event.target.closest("#rail, .top-nav, #navToggle")) return;
      setNav(false);
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && isOpen()) {
        setNav(false);
        toggle.focus();
      }
    });

    /* A resize past the breakpoint puts the links back in the bar and removes
       the rail's drawer, so leaving the class set would hide a menu that is no
       longer there. */
    window.addEventListener("resize", function () {
      if (window.innerWidth > 900) setNav(false);
    });
  }

  // ------------------------------------------------------------------ search
  var input = document.getElementById("searchInput");
  var panel = document.getElementById("searchResults");
  if (!input || !panel || !S) return;

  var active = -1;

  /* On a narrow screen the box is an overlay opened from the magnifier. It is
     closed again on Escape and whenever a result is followed, so the reader is
     never left with a sheet across the top of the page they asked for. */
  var searchToggle = document.getElementById("searchToggle");
  function setSearching(on) {
    document.body.classList.toggle("searching", on);
    if (searchToggle) searchToggle.setAttribute("aria-expanded", on ? "true" : "false");
  }
  if (searchToggle) {
    searchToggle.addEventListener("click", function () {
      var on = !document.body.classList.contains("searching");
      setSearching(on);
      if (on) input.focus();
    });
  }

  function close() {
    panel.hidden = true;
    panel.innerHTML = "";
    active = -1;
  }

  /* Following a result navigates, so the overlay does not need to be torn down -
     but a click on the panel itself can be a miss on a touch screen. */
  panel.addEventListener("click", function (event) {
    if (!event.target.closest(".result")) setSearching(false);
  });

  function escapeHtml(text) {
    /* The single quote is escaped as well as the double one. Attributes here are
       double-quoted so it cannot break out today, but a value that is only safe
       in one quoting style is one style change away from not being safe. */
    return String(text).replace(/[&<>"']/g, function (c) {
      return {
        "&": "&amp;", "<": "&lt;", ">": "&gt;",
        '"': "&quot;", "'": "&#39;"
      }[c];
    });
  }

  /* Builds the href attribute for a result.

     The url is generated data, but it lands in an attribute position inside a
     string handed to innerHTML, so it is escaped like any other value - and the
     scheme is checked, because "javascript:" here would be script execution on
     the documentation site. Only a same-site relative link is ever produced;
     anything else degrades to "#" rather than being rendered as a link. */
  function safeHref(url) {
    var text = String(url == null ? "" : url).trim();
    /* Strip control characters, which can hide a scheme from a naive check. */
    text = text.replace(/[\x00-\x1f\x7f]/g, "");
    /* Backslashes become forward slashes, because that is what the browser
       does when it resolves the value. "\/evil.example" has no scheme and no
       leading "//", so the test below called it a relative path - and the URL
       parser in the browser reads it as https://evil.example. Checking the
       normalised form is what makes the check agree with the resolver. */
    text = text.replace(/\\/g, "/");
    if (!text || text.charAt(0) === "#") {
      return escapeHtml(text || "#");
    }
    if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(text) || text.indexOf("/") === 0) {
      return "#";
    }
    /* Refuse to climb out of the pages directory. */
    if (text.indexOf("..") !== -1) {
      return "#";
    }
    return escapeHtml(text);
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
      /* highlight() escapes first and then wraps the matches, so both the title
         and the excerpt pass through it. The excerpt is generated data too -
         feeding it to innerHTML raw would be the same mistake as an unescaped
         href. */
      html += '<a class="result" href="' + safeHref(hit.url) + '">' +
        '<span class="result-title"><span class="result-page">' +
        escapeHtml(hit.page) + "</span>" +
        S.highlight(hit.title, words) + "</span>" +
        '<span class="result-text">' + S.highlight(S.snippet(hit, words), words) + "</span>" +
        "</a>";
    }
    panel.innerHTML = html;
    panel.hidden = false;
    active = -1;
  }

  function search() {
    var query = input.value;
    var words = S.terms(query);
    if (!words.length) { close(); return; }
    S.load(function (entries) {
      /* The reader usually kept typing while the index was still in flight, and
         every keystroke after the first is dropped by the load guard inside
         load(). Returning here would leave a fast typist with no results at
         all - so run again against whatever is in the box now. load() answers
         synchronously from cache the second time, so this settles. */
      if (input.value !== query) { search(); return; }
      var hits = [];
      for (var i = 0; i < entries.length; i++) {
        var value = S.score(entries[i], words);
        if (value > 0) hits.push({ entry: entries[i], score: value });
      }
      hits.sort(function (a, b) { return b.score - a.score; });
      render(hits.slice(0, 10).map(function (h) { return h.entry; }), words, query);
    });
  }

  input.addEventListener("input", search);
  input.addEventListener("focus", function () { if (input.value) search(); });

  function mark(items) {
    for (var i = 0; i < items.length; i++) {
      items[i].classList.toggle("is-active", i === active);
      if (i === active) items[i].scrollIntoView({ block: "nearest" });
    }
  }

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
      var href = safeHref(items[active].getAttribute("href"));
      if (href.charAt(0) !== "#") window.location.href = href;
    } else if (event.key === "Escape") {
      input.value = "";
      close();
      setSearching(false);
      input.blur();
    }
  });

  document.addEventListener("click", function (event) {
    if (!event.target.closest(".search")) close();
  });

  /* "/" and Ctrl-K both go to the box. Neither fires while a field already has
     focus, so "/" stays a slash in the search box itself. */
  document.addEventListener("keydown", function (event) {
    var combo = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
    var slash = event.key === "/" && document.activeElement !== input &&
      !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if (combo || slash) {
      event.preventDefault();
      setSearching(true);
      input.focus();
      input.select();
    }
    if (event.key === "Escape" && document.activeElement === input) {
      input.value = "";
      close();
      setSearching(false);
      input.blur();
    }
  });
})();