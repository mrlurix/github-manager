/* Motion for the documentation site.
   ---------------------------------------------------------------------------
   Everything here is additive. If this file fails to load, is blocked, or runs on
   a browser without IntersectionObserver, the pages are complete and static:
   the reveal states live behind html.motion, which is only set once the
   observers are known to be in place. A reader never gets a blank section
   because an animation did not fire.

   What it does:
     - sets html.motion, which is what arms the CSS
     - reveals [data-reveal] elements as they come into view, with a stagger
     - counts the figures in .fact up to their real value
     - tracks reading progress in the bar under the header
     - marks the current heading in the table of contents
     - adds a copy button to a code block, only where it can actually work

   Run: assets/motion.js
*/
(function () {
  "use strict";

  var root = document.documentElement;
  var reduced = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* A reader who asked for no motion should get a still page - but the *same*
     page. The copy button, the table-of-contents tracking and the progress bar
     are not animations; they are a control and two pieces of navigation, and
     returning early here took all three away from anyone with the setting on.
     So this skips the reveals only, and falls through to the features. */
  var still = reduced || !("IntersectionObserver" in window);

  if (still) {
    document.querySelectorAll("[data-reveal]").forEach(function (node) {
      node.classList.add("is-revealed");
    });
  }

  // ------------------------------------------------------------------ reveals
  /* One observer for the whole page rather than one per element. Each target
     gets its own observer otherwise, and a long features page ends up with
     several hundred of them all firing on the same frame. */
  var pending = [];

  function reveal(node) {
    node.classList.add("is-revealed");
    var i = pending.indexOf(node);
    if (i !== -1) pending.splice(i, 1);
  }

  /* The stagger is read from data-stagger, which the sanitiser allows by name.
     It is applied as a custom property rather than an inline transition, so the
     delay lives in one place - the stylesheet - and the markup stays presentable. */
  var observer = new IntersectionObserver(function (entries) {
    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i];
      if (!entry.isIntersecting) continue;
      reveal(entry.target);
      observer.unobserve(entry.target);
    }
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });

  function arm() {
    /* Nothing to observe, and nothing to observe with. */
    if (still) return;

    var nodes = document.querySelectorAll("[data-reveal]");
    var group = 0;
    var lastGroup = null;

    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      var step = node.getAttribute("data-stagger");

      // A new stagger group restarts the count. That is what stops the third
      // section from waiting a second and a half for its turn.
      if (step !== lastGroup) { group = 0; lastGroup = step; }
      if (step === "1") {
        // 70ms apart, capped at eight: past that a reader is waiting on the
        // animation rather than reading the section.
        node.style.setProperty("--reveal-delay", Math.min(group, 8) * 70 + "ms");
        group++;
      }
      pending.push(node);
      observer.observe(node);
    }

    /* The observer's callback is delivered during the browser's rendering steps, so
       it only ever hears about an element that was, at some point, intersecting
       the viewport. Several very ordinary things skip that:

         - pressing End, or following an anchor jump, slides past two thirds of
           the page in one step, and none of those sections were ever on screen
         - a browser with no compositor, or a tab in the background, does not
           run rendering steps at all

       In both cases the reader is left looking at a blank page, with no way to
       tell that is a bug rather than a page that has not finished loading.

       So anything the reader has actually reached - anything with a top edge
       above the bottom of the window - is treated as arrived. The observer is
       what makes the timing pleasant; this is what makes it correct.

       It runs on every scroll tick for immediacy, and on a timer as well,
       because a scroll event is itself only delivered while the page is live.
       The timer is cleared the moment there is nothing left to reveal, so a page
       that has been read costs nothing. */
    var ticker = 0;

    function stopTicker() {
      if (ticker) { clearInterval(ticker); ticker = 0; }
    }

    function sweep() {
      var limit = window.innerHeight;
      for (var i = pending.length - 1; i >= 0; i--) {
        if (pending[i].getBoundingClientRect().top < limit) reveal(pending[i]);
      }
      if (!pending.length) stopTicker();
    }

    window.addEventListener("scroll", sweep, { passive: true });
    window.addEventListener("resize", sweep, { passive: true });

    /* Anything already on screen at load reveals immediately, and so does anything
       the page has already scrolled to - arriving on a deep link leaves the
       browser scrolled before a line of this runs. A short settle is allowed
       for that, because the anchor jump happens after DOMContentLoaded and the
       first pass would otherwise measure a page still at the top.

       Every one of these is started after `ticker` is assigned, not before. A
       `var` is hoisted but its assignment is not, so a start call placed above
       the declaration sees undefined, fails an `=== null` guard silently, and
       the guarantee never runs. */
    if (!ticker) ticker = setInterval(sweep, 200);
    requestAnimationFrame(sweep);
    setTimeout(sweep, 120);
    setTimeout(sweep, 600);

    /* The failsafe. If anything above went wrong - an observer that never fires,
       an element inside a collapsed container that reports as zero-height - the
       content still ends up visible. Nothing on this page is more important
       than being read.
       Ten seconds is far past any animation's duration and short enough that
       nobody has scrolled away and forgotten. */
    setTimeout(function () {
      pending.slice().forEach(reveal);
      stopTicker();
    }, 10000);
  }

  /* The class is added last, once every observer exists. Anything that reads it
     as "animations are on" is therefore looking at a page that will finish.

     Only when motion is actually wanted: the class is what makes the stylesheet
     hide the reveals, and a still page has nothing to hide - it has already
     been opened above. */
  arm();
  if (!still) root.classList.add("motion");

  // ---------------------------------------------------------------- counters
  /* The figures count up to the number already written in the markup. Reading
     the number rather than taking it as an argument is the point: the value is
     in the HTML, so a reader without JavaScript, or with it blocked, still
     reads "63 MB" rather than a zero.

     The count-up is decoration over a value that is already correct, so a still
     page is left showing the real figure rather than animating to it. */
  var counters = new IntersectionObserver(function (entries) {
    for (var i = 0; i < entries.length; i++) {
      if (!entries[i].isIntersecting) continue;
      count(entries[i].target);
      counters.unobserve(entries[i].target);
    }
  }, { threshold: 0.4 });

  function count(node) {
    var target = parseInt(node.getAttribute("data-count"), 10);
    var suffix = node.getAttribute("data-count-suffix") || "";
    if (isNaN(target)) return;

    var duration = 1100;
    var start = performance.now();
    var finished = false;

    function write(value) {
      if (finished) return;
      node.textContent = value + suffix;
    }

    function frame() {
      // performance.now() rather than the frame timestamp. The timestamp a
      // frame is handed is not guaranteed to advance with wall time - a
      // coalesced or backgrounded frame can carry a stale one - and a count-up
      // that measures itself against that can run backwards.
      var done = Math.min(1, (performance.now() - start) / duration);
      /* Cubic ease-out: fast at first, settling. A linear count-up looks like a
         machine reading a number, which is exactly the impression to avoid. */
      var eased = 1 - Math.pow(1 - done, 3);
      write(Math.round(target * eased));
      if (done < 1) requestAnimationFrame(frame);
    }

    /* Two guards, because the frame loop cannot be relied on to finish.
       requestAnimationFrame does not run in a background tab, and a count-up
       that stops part-way leaves a wrong number on the page - "3 MB" where it
       should say 63. A figure that is incorrect is worse than one that never
       moved, so the real value is written whether or not the animation gets to
       run, and `finished` stops a late frame from overwriting it. */
    setTimeout(function () {
      finished = true;
      node.textContent = target + suffix;
    }, duration);

    requestAnimationFrame(frame);
  }

  function armCounters() {
    /* The markup already holds the finished value, so there is nothing to do on
       a still page - and animating to it would contradict the setting. */
    if (still) return;
    var nodes = document.querySelectorAll("[data-count]");
    for (var i = 0; i < nodes.length; i++) counters.observe(nodes[i]);
  }

  // ---------------------------------------------------------------- progress
  /* Transform rather than width: a width change relayouts the header on every
     scroll event, and a transform does not. */
  var bar = document.querySelector(".progress");
  var ticking = false;

  function progress() {
    if (!bar) return;
    var doc = document.documentElement;
    var span = doc.scrollHeight - doc.clientHeight;
    var value = span > 0 ? Math.min(1, doc.scrollTop / span) : 0;
    bar.style.transform = "scaleX(" + value + ")";
    ticking = false;
  }

  function armProgress() {
    if (!bar) return;
    window.addEventListener("scroll", function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(progress);
    }, { passive: true });
    window.addEventListener("resize", progress, { passive: true });
    progress();
  }

  // -------------------------------------------------------------------- toc
  /* Marks the heading the reader is currently at. Cheap because the handler is
     throttled through rAF and only reads cached offsets. */
  var tocLinks = [];
  var headings = [];

  function collectToc() {
    tocLinks = [].slice.call(document.querySelectorAll(".toc a[href^='#']"));
    headings = tocLinks
      .map(function (link) {
        return document.getElementById(decodeURIComponent(link.hash.slice(1)));
      })
      .filter(Boolean);
    if (headings.length) tocLinks = tocLinks.slice(0, headings.length);
  }

  function markToc() {
    var line = window.innerHeight * 0.28;
    var current = 0;
    for (var i = 0; i < headings.length; i++) {
      if (headings[i].getBoundingClientRect().top <= line) current = i;
    }
    /* At the very bottom the last heading is always the one being read, even if
       it never crosses the line - a short final section would otherwise be
       unreachable in the list. */
    if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 4) {
      current = headings.length - 1;
    }
    for (var j = 0; j < tocLinks.length; j++) {
      tocLinks[j].classList.toggle("is-current", j === current);
    }
  }

  function armToc() {
    collectToc();
    if (!headings.length) return;
    var queued = false;
    var onScroll = function () {
      if (queued) return;
      queued = true;
      requestAnimationFrame(function () { markToc(); queued = false; });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    markToc();
  }

  // -------------------------------------------------------------- copy button
  /* Added here rather than in the build because it is the one control that
     needs a capability check: the async clipboard API is unavailable on an
     insecure origin, and this site is also opened from file:// during
     development. Where it cannot work, no button appears - a button that
     silently does nothing is worse than no button. */
  var COPY_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true">' +
    '<rect x="9" y="9" width="11" height="11" rx="2"/>' +
    '<path d="M5 15H4.5A1.5 1.5 0 0 1 3 13.5v-9A1.5 1.5 0 0 1 4.5 3h9A1.5 1.5 0 0 1 15 4.5V5"/>' +
    "</svg>";

  function armCopy() {
    if (!navigator.clipboard || !window.isSecureContext) return;
    var blocks = document.querySelectorAll("pre");
    for (var i = 0; i < blocks.length; i++) {
      (function (block) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "copy";
        button.innerHTML = COPY_ICON + "<span>Copy</span>";
        button.setAttribute("aria-label", "Copy this code block");
        button.addEventListener("click", function () {
          var text = block.querySelector("code");
          navigator.clipboard.writeText(text ? text.textContent : block.textContent)
            .then(function () {
              button.classList.add("is-done");
              button.querySelector("span").textContent = "Copied";
              setTimeout(function () {
                button.classList.remove("is-done");
                button.querySelector("span").textContent = "Copy";
              }, 1600);
            })
            .catch(function () { /* the clipboard can be denied; leave it alone */ });
        });
        block.appendChild(button);
      })(blocks[i]);
    }
  }

  // ------------------------------------------------------------------- start
  /* Copy buttons and the table of contents run for every reader, still or not.
     Counters are the one exception and they opt out inside armCounters(). */
  function start() {
    armCounters();
    armProgress();
    armToc();
    armCopy();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();