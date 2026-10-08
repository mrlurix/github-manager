/* Hover behaviour for the buttons, checked without depending on Chrome
   deciding to deliver a synthetic pointer event.
   Run: node tools/verify_hover.js

   Why not just hover the element: it works most of the time and fails the rest,
   with no useful error. Chrome applies :hover only when it judges the window
   can take pointer input; when it declines, the geometry is still correct -
   elementFromPoint at the button's centre returns the button - but
   `matches(":hover")` stays false and the button reads as though it had no
   hover state at all. Thirty pages of interaction through a shared browser is
   enough to get there, and a test that flakes for a reason unrelated to the
   page is worse than no test.

   So the geometry is checked at runtime, in verify_layout.js, where it is
   reliable, and the cascade is checked here by reading the stylesheet, because
   that is the part that actually went wrong. `.btn:hover` is two selectors
   deep; a bare `.btn-primary` is one. The hover therefore won, and the primary
   button inverted to dark exactly when someone was deciding whether to press
   it - the one moment it must not.

   Exits 0 when the button behaves, 1 when it does not.
*/
const fs = require("fs");
const path = require("path");

const css = fs.readFileSync(
  path.join(__dirname, "..", "docs_src", "assets", "style.css"), "utf8");

let pass = 0, fail = 0;
function check(name, ok, detail) {
  if (ok) { pass++; console.log("  [PASS] " + name); }
  else { fail++; console.log("  [FAIL] " + name + (detail ? " -> " + detail : "")); }
}

/* --------------------------------------------------------------- the parser
   A brace-matching walk rather than a regex. The file nests rules inside
   @media and @keyframes, and a regex cannot tell a rule inside one of those
   from one outside - which is the whole question here, since the reduced-motion
   block re-declares most of these selectors to switch the animation off.
   ------------------------------------------------------------------------- */
function parse(source) {
  const stack = [];
  const out = [];
  let prelude = "";
  let inComment = false;

  const mediaAt = (depth) => {
    let n = 0;
    for (let i = 0; i < depth && i < stack.length; i++) {
      if (stack[i].startsWith("@media")) n++;
    }
    return n;
  };

  for (let i = 0; i < source.length; i++) {
    const ch = source[i];
    const next = source[i + 1];
    if (inComment) {
      if (ch === "*" && next === "/") { inComment = false; i++; }
      continue;
    }
    if (ch === "/" && next === "*") { inComment = true; i++; continue; }
    if (ch === "{") {
      // Push the head and remember how deep in @media this rule sits. A stack,
      // not a counter: with a counter, the inner rule's closing brace is
      // mistaken for the @media's, and every later rule is attributed to a
      // media block it is not in.
      stack.push(prelude.trim());
      out.push({ head: stack[stack.length - 1], media: mediaAt(stack.length), body: "" });
      prelude = "";
      continue;
    }
    if (ch === "}") {
      // Whichever head opened last is the one closing here.
      if (out.length) out[out.length - 1].body = prelude;
      stack.pop();
      prelude = "";
      continue;
    }
    prelude += ch;
  }

  const flat = [];
  for (const rule of out) {
    if (rule.head.startsWith("@")) continue;
    for (const selector of rule.head.split(",")) {
      const clean = selector.trim();
      if (clean) flat.push({ selector: clean, body: rule.body, media: rule.media });
    }
  }
  return flat;
}

const all = parse(css);
const atTop = all.filter(r => r.media === 0);
const body = (selector) => atTop.find(r => r.selector === selector);

/* -------------------------------------------------------------- specificity
   (ids, classes + attributes + pseudo-classes, elements + pseudo-elements). */
function specificity(selector) {
  const s = selector;
  const pseudoElement = /::[a-z-]+/.test(s);
  const withoutPseudoElements = s.replace(/::[a-z-]+/g, "");
  return [
    (s.match(/#[a-zA-Z0-9_-]+/g) || []).length,
    (withoutPseudoElements.match(/\.[a-zA-Z0-9_-]+/g) || []).length +
      (withoutPseudoElements.match(/\[[^\]]+\]/g) || []).length +
      (withoutPseudoElements.match(/:(?!:)[a-z-]+/g) || []).length,
    (withoutPseudoElements.replace(/[.#][a-zA-Z0-9_-]+/g, "")
      .replace(/\[[^\]]+\]/g, "")
      .replace(/:[a-z-]+(\([^)]*\))?/g, "")
      .match(/(^|[\s>+~,])([a-zA-Z][a-zA-Z0-9]*)/g) || []).length + (pseudoElement ? 1 : 0),
  ];
}

const compare = (a, b) => {
  for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return a[i] - b[i];
  return 0;
};

console.log("\nthe primary button, read from the stylesheet:");
{
  const base = body(".btn.btn-primary");
  const hover = body(".btn.btn-primary:hover");
  const generic = body(".btn:hover");

  check("the primary variant exists", !!base, base ? "" : "no .btn.btn-primary rule");
  // The base rule is not a hover state, so it is not compared against
  // `.btn:hover` - the two only contend on the same element once the pointer is
  // already there, and the hover rule is the one that has to win that. What
  // matters here is that it repeats the base class, which is what makes its own
  // :hover rule outrank `.btn:hover` further down.
  check("it repeats the base class",
    !!base && specificity(base.selector)[1] >= 2,
    base ? `${base.selector} = ${JSON.stringify(specificity(base.selector))}` : "");
  check("it is filled", !!base && /background:\s*var\(--text\)/.test(base.body),
    base && JSON.stringify(base.body.slice(0, 60)));
  check("the label is the dark one", !!base && /color:\s*var\(--bg\)/.test(base.body),
    base && JSON.stringify(base.body.slice(0, 60)));

  check("the primary hover rule exists", !!hover,
    hover ? "" : "no .btn.btn-primary:hover rule");
  check("it stays filled on hover",
    !!hover && /background:\s*var\(--text\)/.test(hover.body),
    hover && JSON.stringify(hover.body.slice(0, 80)));
  check("it does not hand back a transform",
    !!hover && !/transform:\s*none/.test(hover.body),
    hover && JSON.stringify(hover.body.slice(0, 80)));
  check("the hover rule outranks the plain hover",
    !!hover && compare(specificity(hover.selector), specificity(".btn:hover")) > 0,
    hover ? `${JSON.stringify(specificity(hover.selector))} vs ` +
      `${JSON.stringify(specificity(".btn:hover"))}` : "");

  check("the generic hover rule exists", !!generic,
    generic ? "" : "no .btn:hover rule");
  check("a hover lifts the button",
    !!generic && /transform:\s*translateY\(-/.test(generic.body),
    generic && JSON.stringify(generic.body.slice(0, 90)));
  const active = body(".btn:active");
  check("a press goes back down rather than sticking lifted",
    !!active && /translateY\(0\)/.test(active.body) && /scale\(/.test(active.body),
    active && JSON.stringify(active.body.slice(0, 60)));
}

console.log("\nevery variant's hover outranks the generic one:");
{
  // The base variant does not need to outrank `.btn:hover` - it is not a hover
  // state, and the two only ever apply to the same element when it is hovered,
  // at which point the more specific of the two wins. What has to hold is that
  // each variant's own :hover rule does outrank it, or the generic hover colour
  // bleeds through and the button changes weight when the pointer arrives.
  for (const variant of ["btn-primary", "btn-solid", "btn-ghost"]) {
    const b = body(`.btn.${variant}`);
    const h = body(`.btn.${variant}:hover`);
    check(`${variant} is declared with the base class`, !!b, b ? b.selector : "missing");
    check(`${variant}'s hover exists`, !!h, h ? "" : `no .btn.${variant}:hover rule`);
    if (h) {
      check(`${variant}'s hover outranks the generic one`,
        compare(specificity(h.selector), specificity(".btn:hover")) > 0,
        `${h.selector} ${JSON.stringify(specificity(h.selector))} vs ` +
        `${JSON.stringify(specificity(".btn:hover"))}`);
    }
  }
}

console.log("\nthe sheen is only there for motion:");
{
  const after = body(".btn::after");
  check("the sheen is an element on the button", !!after, after ? "" : "no .btn::after rule");
  const animated = all.filter(r =>
    r.selector === ".btn:hover::after" && r.media > 0);
  check("its sweep is inside a motion-preference query",
    animated.length > 0, `${animated.length} rules`);
}

console.log("\nthe arrow:");
{
  // The body sanitiser drops <svg> - it can carry script, event handlers and
  // external references - so an arrow written as one vanished silently and the
  // buttons looked unfinished.
  const page = fs.readFileSync(
    path.join(__dirname, "..", "docs_src", "pages", "index.md"), "utf8");
  check("the landing page has no inline svg",
    !/<svg/.test(page), (page.match(/<svg[^>]*>/g) || []).slice(0, 2).join(" "));
  check("it uses a drawn arrow instead",
    /class="btn-arrow"/.test(page), String(page.includes("btn-arrow")));
  const arrow = body(".btn-arrow");
  check("the arrow is styled from borders",
    !!arrow && /border-top/.test(arrow.body) && !/url\(/.test(arrow.body),
    arrow && JSON.stringify(arrow.body.slice(0, 60)));
  check("the arrow steps on hover",
    !!body(".btn:hover .btn-arrow"), "no .btn:hover .btn-arrow rule");
}

console.log("\nround, not square:");
{
  // The ask was round. A 6px corner on a 40px button reads as square, so the
  // buttons go all the way to a pill and the panels take the larger --r, or the
  // two look like they came from different sites.
  const root = /:root\s*\{([\s\S]*?)\n\}/.exec(css);
  const token = (name) => {
    const m = root && new RegExp(name + ":\\s*([^;]+)").exec(root[1]);
    return m ? m[1].trim() : null;
  };
  check("the button token is a full pill", token("--r-btn") === "999px",
    String(token("--r-btn")));
  check("the panel token is properly round", parseInt(token("--r"), 10) >= 10,
    String(token("--r")));
  check("the header has its own, larger radius",
    parseInt(token("--r-head"), 10) >= parseInt(token("--r"), 10),
    String(token("--r-head")));

  const head = body(".site-header");
  check("the header is inset, so the curve has an edge to sit inside",
    !!head && /margin:/.test(head.body) && /border:/.test(head.body),
    head && JSON.stringify(head.body.slice(0, 90)));
  check("it is rounded, not a full-bleed bar with square corners",
    !!head && /border-radius:/.test(head.body) && !/border-bottom:\s*1px/.test(head.body),
    head && JSON.stringify(head.body.slice(0, 110)));

  // Every interactive thing inherits the pill, so none of them is left square.
  const square = all.filter(r =>
    r.media === 0 &&
    /(^|[\s,>])\.(btn|icon-btn|search-icon-button)(\s|,|:|\{|$)/.test(r.selector) &&
    /border-radius/.test(r.body) &&
    !/999px|50%|--r-btn/.test(r.body));
  check("nothing interactive was left square", square.length === 0,
    square.map(r => r.selector).join(" | "));

  // And a pill needs the horizontal room, or the curve eats the label.
  const btn = body(".btn");
  check("a pill button is given the extra padding it needs",
    !!btn && /padding-inline:\s*1[6-9]px|padding-inline:\s*2\dpx/.test(btn.body),
    btn && JSON.stringify(btn.body.slice(0, 140)));
}

console.log("\nreduced motion turns it all off:");
{
  const blanket = /@media \(prefers-reduced-motion: reduce\)[\s\S]*?transition-duration:\s*0\.01ms/.test(css);
  check("the blanket rule is present", blanket, String(blanket));
  const progress = /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.progress\s*\{\s*display:\s*none/.test(css);
  check("the progress bar is not drawn either", progress, String(progress));
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);