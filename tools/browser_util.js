/* Shared by the browser-driven checks.
 *
 * The pages ship a Content-Security-Policy with "style-src 'self'" and no
 * 'unsafe-inline'. Several checks work by injecting a <style> tag to simulate a
 * hover, a focus ring or a reduced-motion preference. With the policy tightened
 * those injections are refused, and puppeteer reports it as
 * "Error: Could not load style" - the policy working exactly as intended, not
 * a layout regression.
 *
 * So the harness opts out for the rules it injects itself. Nothing here weakens
 * what ships: the production policy is asserted directly by
 * verify_site_security.js, and check_no_inline_styles() in build_docs.py fails
 * the build if a real page ever needs the concession that was removed.
 */
function bypassCsp(browser) {
  const open = browser.newPage.bind(browser);
  browser.newPage = async function () {
    const page = await open.apply(browser, arguments);
    await page.setBypassCSP(true);
    return page;
  };
  return browser;
}

module.exports = { bypassCsp };
