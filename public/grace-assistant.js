/*!
 * Grace Assistant - a tap-only guest assistant for church websites.
 *
 * There is no text input anywhere. Every question a guest can ask, and every
 * answer they get back, comes from answers.json. The widget never generates
 * language of its own.
 *
 * Usage:
 *   <script src="/grace-assistant.js" data-answers="/answers.json" defer></script>
 *
 * Optional attributes:
 *   data-answers  URL of the answers file            (default "answers.json")
 *   data-route    Force a route instead of reading location.pathname
 *                 (also accepts ?ga-route=/plan-your-visit/ for testing)
 */
(function () {
  'use strict';

  var script = document.currentScript || (function () {
    var all = document.getElementsByTagName('script');
    return all[all.length - 1];
  })();

  var ANSWERS_URL = script.getAttribute('data-answers') || 'answers.json';

  /* Optional follow-up ranking service. Empty string = never called, and the
     widget behaves exactly as it did before this existed. */
  var ROUTER_URL = script.getAttribute('data-router') || '';
  var ROUTER_TIMEOUT_MS = 2000;

  /* Guest-flow experiment, DEFAULT OFF. Every path it gates is written as
     `HIDE_TAPPED && ...`, so with the flag absent the widget behaves exactly as
     it did before this existed. Query-only and hyphenated to match the existing
     ?ga-route= idiom - window.location.search is the only environment this
     widget has ever read, and one convention beats two. */
  var HIDE_TAPPED = /[?&]ga-hide-tapped=1(?:&|$)/.test(window.location.search);

  /* PROVISIONAL copy - T rewrites it. Hardcoded on purpose: the per-route
     override plumbing (route.X || meta.X || literal) could carry this in one
     line, but the Sheet cannot emit the key yet - that needs a publish.py
     change and a PLACEMENT column, both out of scope for this pass. */
  var EXHAUSTION_NOTE =
    'That covers everything I can answer here. Want to talk with a real person?';

  var NAVY = '#292E38';
  var ORANGE = '#FF5400';
  var CREAM = '#FAFAF7';
  var RADIUS = '4px';

  var HOME_ID = '__home';
  var TALK_PERSON_ID = 'talk-person';

  /* Grace registers these families document-wide (useanyfont + Typekit).
     Naming them here lights the widget up on discovergrace.com and the demo
     clones; everywhere else the fallbacks carry it. No font files shipped.
     'greyclif-regular' is spelled with one f in Grace's own CSS - verbatim. */
  /* Font pinning. Grace registers five faces via useanyfont; ONE of them is a
     trial cut - 4619Greycliff-CF.woff2 reports family 'FSP DEMO - Greycliff CF'
     and stamps a watermark glyph on the apostrophe. That file is the one served
     as CSS family 'greycliff-cf', so the widget must never name it. Verified
     clean, by file:
       3382Greyclif-Regular.woff2  Greycliff CF Regular     400  -> 'greyclif-regular'
       8171Greycliff-Demi.woff2    Greycliff CF Demi Bold   600  -> 'greycliff-demi'
       2430Greycliff-Bold.woff2    Greycliff CF Bold        700  -> 'greycliff-bold'
       3135Quincy-Black.woff2      Quincy CF Black          900  -> 'quincy-black'
     Each @font-face omits a font-weight descriptor, so every family is a
     weight-400 face and 'greycliff-bold' is a separate FAMILY, not a weight.
     Emphasis therefore switches family rather than raising font-weight, and
     stays at 500 so browsers do not synthesise bold on top of an already-bold
     file. Off Grace's site all of these fall through to the system stack. */
  var SYSTEM = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
  var SERIF  = "'quincy-black', Georgia, 'Times New Roman', serif";
  var SANS   = "'greyclif-regular', " + SYSTEM;
  var SANS_MED = "'greycliff-demi', 'greycliff-bold', 'greyclif-regular', " + SYSTEM;

  /* ------------------------------------------------------------------ */
  /* Route handling                                                      */
  /* ------------------------------------------------------------------ */

  function queryRoute() {
    var m = /[?&]ga-route=([^&]+)/.exec(window.location.search);
    return m ? decodeURIComponent(m[1]) : null;
  }

  function normalize(path) {
    if (!path) return '/';
    path = String(path).toLowerCase().split('?')[0].split('#')[0];
    if (path.charAt(0) !== '/') path = '/' + path;
    if (path.charAt(path.length - 1) !== '/') path += '/';
    return path;
  }

  function pickRoute(routes, path) {
    var here = normalize(path);
    if (routes[here]) return routes[here];

    var best = null;
    var bestLen = -1;
    for (var key in routes) {
      if (key === 'default' || !Object.prototype.hasOwnProperty.call(routes, key)) continue;
      var candidate = normalize(key);
      if (here.indexOf(candidate) === 0 && candidate.length > bestLen) {
        best = routes[key];
        bestLen = candidate.length;
      }
    }
    return best || routes['default'] || { starters: [] };
  }

  /* ------------------------------------------------------------------ */
  /* Markup                                                              */
  /* ------------------------------------------------------------------ */

  var CROSS_SVG =
    '<svg viewBox="0 0 44 44" aria-hidden="true" focusable="false">' +
      '<circle cx="22" cy="8"  r="4"/>' +
      '<circle cx="12" cy="20" r="4"/>' +
      '<circle cx="22" cy="20" r="4"/>' +
      '<circle cx="32" cy="20" r="4"/>' +
      '<circle cx="22" cy="32" r="4"/>' +
    '</svg>';

  var CLOSE_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
      '<path d="M6 6 L18 18 M18 6 L6 18" fill="none" stroke="currentColor" ' +
      'stroke-width="2.4" stroke-linecap="round"/>' +
    '</svg>';

  var CSS = [
    ':host { all: initial; }',
    '*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }',

    '.wrap {',
    /* env() only resolves non-zero when the HOST page's viewport meta carries
       viewport-fit=cover. discovergrace.com does not, so these insets are 0
       there today and the literal offsets are what actually apply. They are
       kept so the widget becomes correct the moment that meta is fixed. */
    '  position: fixed;',
    '  right: calc(20px + env(safe-area-inset-right, 0px));',
    '  bottom: calc(20px + env(safe-area-inset-bottom, 0px));',
    '  z-index: 2147483000;',
    '  display: flex; flex-direction: column; align-items: flex-end; gap: 12px;',
    '  font-family: ' + SANS + ';',
    '  color: ' + NAVY + '; font-size: 15px; line-height: 1.5;',
    '  -webkit-font-smoothing: antialiased;',
    '}',

    /* ---- launcher ---- */
    /* Brand guide p.5: the monogram never appears without identifying copy, so
       the launcher is a lockup - white label pill plus the orange bug. */
    /* The wrapper is a positioning device only - no fill, no border, no radius,
       no shadow, no outline. Every visible state lives on .launcher-pill and
       .launcher-bug. (The old single-button launcher's chrome used to live here
       and was inherited by the new lockup, which is what drew the box.) */
    '.launcher {',
    '  border: 0; background: none; padding: 0; margin: 0;',
    '  border-radius: 0; box-shadow: none; outline: none;',
    '  -webkit-appearance: none; appearance: none;',
    '  cursor: pointer; display: flex; align-items: center; gap: 10px;',
    '  flex: none; -webkit-tap-highlight-color: transparent;',
    '}',
    '.launcher-pill {',
    '  background: #FFFFFF; color: ' + NAVY + '; border-radius: 999px;',
    '  font-family: ' + SANS_MED + '; padding: 9px 16px; font-size: 11px; font-weight: 500;',
    '  letter-spacing: 0.12em; text-transform: uppercase; white-space: nowrap;',
    '  box-shadow: 0 2px 8px rgba(41, 46, 56, 0.15);',
    '}',
    '.launcher-bug {',
    '  width: 60px; height: 60px; border-radius: 50%; flex: none;',
    '  background: ' + ORANGE + '; color: #FFFFFF;',
    '  display: flex; align-items: center; justify-content: center;',
    '  box-shadow: 0 6px 20px rgba(41, 46, 56, 0.28);',
    '  transition: box-shadow 140ms ease;',
    '}',
    '.launcher:focus { outline: none; }',
    '.launcher:focus-visible { outline: none; }',
    /* states attach to the two visible pieces, never the wrapper */
    '.launcher-pill, .launcher-bug { transition: transform 140ms ease, box-shadow 140ms ease; }',
    '.launcher:active .launcher-bug { transform: translateY(1px); }',
    '.launcher:active .launcher-pill { transform: translateY(1px); }',
    '.launcher:focus-visible .launcher-bug { outline: 3px solid ' + NAVY + '; outline-offset: 3px; }',
    '.launcher:focus-visible .launcher-pill { outline: 2px solid ' + NAVY + '; outline-offset: 2px; }',
    '.launcher-bug svg { width: 30px; height: 30px; fill: #FFFFFF; }',
    '.launcher .icon-close { width: 24px; height: 24px; }',

    /* ---- panel ---- */
    /* Four stacked, non-overlapping children: head / scroll / pinned / foot.
       Only .scroll flexes; the other three are flex: none. min-height: 0 on the
       scroll body is what lets it shrink below its content on iOS - without it a
       flex child refuses to shrink and the body never scrolls. */
    '.panel {',
    '  display: none; flex-direction: column; overflow: hidden;',
    '  width: 372px; max-width: calc(100vw - 32px);',
    '  height: 560px; max-height: calc(100vh - 132px);',
    '  background: ' + CREAM + '; border-radius: ' + RADIUS + ';',
    '  border: 1px solid rgba(41, 46, 56, 0.10);',
    '  box-shadow: 0 18px 48px rgba(41, 46, 56, 0.22);',
    '  opacity: 0; transform: translateY(10px);',
    '  transition: opacity 170ms ease, transform 170ms ease;',
    '}',
    '.panel.is-visible { display: flex; }',
    '.panel.is-open { opacity: 1; transform: translateY(0); }',

    /* ---- header ---- */
    '.head {',
    '  display: flex; align-items: center; gap: 10px; flex: none;',
    '  padding: 14px 14px 12px 16px;',
    '  border-bottom: 1px solid rgba(41, 46, 56, 0.10);',
    '  background: ' + CREAM + ';',
    '}',
    '.mark { width: 22px; height: 22px; flex: none; }',
    '.mark svg { width: 22px; height: 22px; fill: ' + ORANGE + '; display: block; }',
    '.head-text { flex: 1 1 auto; min-width: 0; }',
    '.head-title { font-family: ' + SERIF + '; font-size: 21px; line-height: 1;',
    '  font-weight: 400; letter-spacing: 0; }',
    '.head-sub { font-family: ' + SANS_MED + '; font-size: 9.5px; font-weight: 500;',
    '  letter-spacing: 0.14em;',
    '  text-transform: uppercase; color: rgba(41, 46, 56, 0.55); margin-top: 3px; }',
    /* route title, now a body heading above the intro */
    '.route-heading { font-family: ' + SERIF + '; font-size: 24px; line-height: 1.15;',
    '  font-weight: 400; color: ' + NAVY + '; padding: 2px 2px 2px; }',
    '.close {',
    '  flex: none; width: 44px; height: 44px; border: 0; border-radius: ' + RADIUS + ';',
    '  background: transparent; color: ' + NAVY + '; cursor: pointer;',
    '  display: flex; align-items: center; justify-content: center;',
    '  -webkit-tap-highlight-color: transparent;',
    '}',
    '.close:active { background: rgba(41, 46, 56, 0.10); }',
    '.close:focus-visible { outline: 2px solid ' + ORANGE + '; outline-offset: 1px; }',
    '.close svg { width: 18px; height: 18px; }',

    /* ---- feed ---- */
    /* ONE scroll region: route heading + transcript + section label + chips all
       live inside .scroll. Header is fixed above it, pinned row and footer below.
       Nothing inside has its own overflow, so nothing can clip. */
    '.scroll {',
    '  flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain;',
    '  scrollbar-width: thin; scrollbar-color: rgba(41, 46, 56, 0.28) transparent;',
    /* Cosmetic breathing room only. The pinned row and footer are flex siblings
       below this box, not an overlay, so nothing here needs to clear them. */
    '  padding-bottom: 16px;',
    /* Bottom-edge fade signalling "there is more below". A mask on the scroll box
       itself - no extra element, no positioned ancestor, no layout shift. The
       fade sits at the box's bottom edge, which is exactly above the pinned row.
       Removed once there is nothing left to scroll to. */
    '  -webkit-mask-image: linear-gradient(to bottom, #000 calc(100% - 24px), transparent 100%);',
    '  mask-image: linear-gradient(to bottom, #000 calc(100% - 24px), transparent 100%);',
    '}',
    '.scroll.at-end { -webkit-mask-image: none; mask-image: none; }',
    '.scroll::-webkit-scrollbar { width: 6px; }',
    '.scroll::-webkit-scrollbar-track { background: transparent; }',
    '.scroll::-webkit-scrollbar-thumb {',
    '  background: rgba(41, 46, 56, 0.28); border-radius: 999px;',
    '}',
    '.scroll::-webkit-scrollbar-thumb:hover { background: rgba(41, 46, 56, 0.42); }',
    '.feed {',
    '  flex: none; overflow: visible;',
    '  padding: 16px; display: flex; flex-direction: column; gap: 12px;',
    '}',
    '.row { display: flex; }',
    '.row.from-guest { justify-content: flex-end; }',
    '.row.from-church { justify-content: flex-start; }',
    '.bubble { max-width: 86%; border-radius: ' + RADIUS + '; padding: 11px 13px; font-size: 14.5px; }',
    '.from-guest .bubble { background: ' + NAVY + '; color: ' + CREAM + '; }',
    '.from-church .bubble {',
    '  background: #FFFFFF; color: ' + NAVY + ';',
    '  border: 1px solid rgba(41, 46, 56, 0.12);',
    '}',
    '.bubble p + p { margin-top: 9px; }',
    /* Answer links render as a stacked pair: links[0] is the primary action,
       links[1+] are secondary. Geometry matches the chips so the panel reads as
       one system. */
    '.bubble a {',
    '  display: block; text-align: left; text-decoration: none;',
    '  font-family: ' + SANS_MED + '; font-weight: 500; font-size: 14px;',
    '  border-radius: ' + RADIUS + '; padding: 10px 12px;',
    '  -webkit-tap-highlight-color: transparent;',
    '  transition: background 120ms ease, border-color 120ms ease;',
    '}',
    '.bubble a.primary { background: ' + ORANGE + '; color: #FFFFFF; border: 1px solid ' + ORANGE + '; }',
    '.bubble a.secondary { background: #FFFFFF; color: ' + NAVY + '; border: 1px solid rgba(41, 46, 56, 0.28); }',
    '.bubble a.primary:active { background: #E04A00; border-color: #E04A00; }',
    '.bubble a.secondary:active { background: rgba(41, 46, 56, 0.06); }',
    '.bubble a:focus-visible { outline: 2px solid ' + NAVY + '; outline-offset: 2px; }',
    '.links { margin-top: 10px; display: flex; flex-direction: column; gap: 10px; }',
    '.link-wrap { display: flex; flex-direction: column; gap: 3px; }',
    '.link-caption { font-size: 11px; color: rgba(41, 46, 56, 0.55); padding: 0 2px;',
    '  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }',
    '.intro { font-size: 13px; color: rgba(41, 46, 56, 0.66); padding: 2px 2px 0; }',
    '.bubble.is-intro { font-size: 15px; line-height: 1.5; }',

    /* ---- options ---- */
    '.options {',
    '  flex: none; padding: 4px 16px 0;',
    '  display: flex; flex-direction: column; gap: 8px;',
    '  overflow: visible;',
    '}',
    '.options-label {',
    '  font-family: ' + SANS_MED + '; font-size: 11px; font-weight: 500; letter-spacing: 0.07em;',
    '  text-transform: uppercase; color: rgba(41, 46, 56, 0.5); margin-bottom: 2px;',
    '}',
    '.chip {',
    '  display: flex; align-items: center; gap: 10px; width: 100%; text-align: left;',
    '  font: inherit; font-family: ' + SANS_MED + '; font-weight: 500;',
    '  font-size: 14.5px; color: ' + NAVY + '; cursor: pointer;',
    '  background: #FFFFFF; border: 1px solid rgba(41, 46, 56, 0.16);',
    '  border-radius: ' + RADIUS + '; padding: 10px 12px;',
    '  transition: border-color 120ms ease, background 120ms ease;',
    '  -webkit-tap-highlight-color: transparent;',
    '}',
    '.chip:active { border-color: ' + ORANGE + '; background: #FFF6F1; transform: scale(0.98); }',
    '.chip:focus-visible { outline: 2px solid ' + ORANGE + '; outline-offset: 1px; }',
    '.chip .text { flex: 1 1 auto; }',
    '.chip .caret { flex: none; color: ' + ORANGE + '; font-size: 17px; line-height: 1; }',
    '.chip.ghost { background: transparent; border-style: dashed; color: rgba(41, 46, 56, 0.72); }',
    '.chip.ghost:active { background: rgba(255, 84, 0, 0.09); }',

    /* ---- pinned action row ---- */
    '.pinned {',
    '  flex: none; display: flex; gap: 8px; padding: 10px 16px 12px;',
    '  border-top: 1px solid rgba(41, 46, 56, 0.10); background: ' + CREAM + ';',
    '}',
    '.pin-btn {',
    '  flex: 1 1 0; font: inherit; font-family: ' + SANS_MED + '; font-weight: 500;',
    '  font-size: 13.5px;',
    '  border-radius: ' + RADIUS + '; padding: 10px 12px; cursor: pointer;',
    '  background: #FFFFFF; color: ' + NAVY + ';',
    '  border: 1px solid rgba(41, 46, 56, 0.22);',
    '  -webkit-tap-highlight-color: transparent;',
    '  transition: background 120ms ease, border-color 120ms ease;',
    '}',
    '.pin-btn.person { border-color: ' + ORANGE + '; color: ' + ORANGE + '; }',
    '.pin-btn:active { background: rgba(41, 46, 56, 0.06); }',
    '.pin-btn.person:active { background: rgba(255, 84, 0, 0.08); }',
    '.pin-btn:focus-visible { outline: 2px solid ' + ORANGE + '; outline-offset: 1px; }',

    /* ---- footer ---- */
    '.foot {',
    '  flex: none; display: flex; align-items: center; justify-content: space-between;',
    '  gap: 10px; padding: 9px 16px calc(11px + env(safe-area-inset-bottom, 0px));',
    '  border-top: 1px solid rgba(41, 46, 56, 0.10);',
    '  font-size: 11.5px; color: rgba(41, 46, 56, 0.55);',
    '}',
    '.restart {',
    '  font: inherit; font-size: 11.5px; font-weight: 600; color: ' + ORANGE + ';',
    '  background: transparent; border: 0; border-radius: ' + RADIUS + ';',
    '  padding: 3px 5px; cursor: pointer;',
    '  -webkit-tap-highlight-color: transparent;',
    '}',
    '.restart:active { background: rgba(255, 84, 0, 0.12); }',
    '.restart:focus-visible { outline: 2px solid ' + ORANGE + '; outline-offset: 1px; }',

    /* ---- small screens ---- */
    '@media (max-width: 480px) {',
    '  .wrap { right: 0; left: 0; bottom: 0; align-items: stretch; }',
    '  .panel {',
    '    width: auto; border-radius: 0; border-left: 0; border-right: 0;',
    '    height: 100vh; max-height: 100vh;',
    '    padding-top: env(safe-area-inset-top, 0px);',
    '  }',
    /* On a full-height sheet the launcher would overlap the panel; the header X
       (44px target) is the close affordance there. */
    '  .wrap.is-open .launcher { display: none; }',
    /* the panel header lockup stays complete at every width - the icon-only
       allowance is the LAUNCHER's, never the panel's */
    /* The sheet needs .wrap flush to the bottom, but the launcher must not be:
       at bottom 0 iOS Safari's toolbar draws over it. env() is 0 without
       viewport-fit=cover, so max() supplies a floor that clears the toolbar
       regardless, and grows with the inset if the host page ever opts in. */
    '  .launcher {',
    '    align-self: flex-end;',
    '    margin-right: 16px;',
    '    margin-bottom: max(34px, calc(16px + env(safe-area-inset-bottom, 0px)));',
    '  }',
    '  .launcher-pill { display: none; }',
    '}',
    '@supports (height: 100dvh) {',
    '  @media (max-width: 480px) {',
    '    .panel { height: 100dvh; max-height: 100dvh; }',
    '  }',
    '}',

    /* ---- hover, desktop only ------------------------------------------ */
    /* iOS emulates :hover on tap and leaves it applied, so the pale hover
       background sticks to whatever chip sat under the finger. Gating the
       whole set on a hover-capable pointer means touch devices never get
       these rules at all - nothing to stick. :active and :focus-visible are
       deliberately outside this block; both self-clear. */
    '@media (hover: hover) {',
    '  .launcher:hover .launcher-bug { transform: translateY(-2px); box-shadow: 0 10px 26px rgba(41, 46, 56, 0.32); }',
    '  .launcher:hover .launcher-pill { transform: translateY(-2px); }',
    '  .close:hover { background: rgba(41, 46, 56, 0.07); }',
    '  .bubble a.primary:hover { background: #E04A00; border-color: #E04A00; }',
    '  .bubble a.secondary:hover { border-color: rgba(41, 46, 56, 0.55); }',
    '  .chip:hover { border-color: ' + ORANGE + '; background: #FFF6F1; }',
    '  .chip.ghost:hover { background: rgba(255, 84, 0, 0.05); }',
    '  .restart:hover { background: rgba(255, 84, 0, 0.09); }',
    '  .pin-btn:hover { border-color: rgba(41, 46, 56, 0.5); }',
    '  .pin-btn.person:hover { background: rgba(255, 84, 0, 0.06); }',
    '}',

    '@media (prefers-reduced-motion: reduce) {',
    '  .panel, .launcher-pill, .launcher-bug, .chip { transition: none; }',
    '}'
  ].join('\n');

  /* ------------------------------------------------------------------ */
  /* Widget                                                              */
  /* ------------------------------------------------------------------ */

  function build(data) {
    var meta = data.meta || {};
    var questions = data.questions || {};
    var routePath = normalize(script.getAttribute('data-route') || queryRoute() || window.location.pathname);
    var route = pickRoute(data.routes || {}, routePath);
    var starters = (route.starters || []).filter(function (id) { return questions[id]; });

    if (!starters.length) return; /* nothing to ask here - stay off the page */

    /* Flag-gated state. In-memory only for this pageview: no localStorage, no
       sessionStorage, no cookies. A reload is the reset, by design. */
    var tapped = {};
    var exhausted = false; /* latch - the handoff fires at most once per pass */

    var host = document.createElement('div');
    host.setAttribute('data-grace-assistant', '');
    var root = host.attachShadow ? host.attachShadow({ mode: 'open' }) : host;

    var style = document.createElement('style');
    style.textContent = CSS;
    root.appendChild(style);

    var wrap = el('div', 'wrap');
    root.appendChild(wrap);

    /* panel ------------------------------------------------------------ */
    var panel = el('div', 'panel');
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'Grace guest assistant');

    var head = el('div', 'head');
    var mark = el('span', 'mark');
    mark.innerHTML = CROSS_SVG;
    var headText = el('div', 'head-text');
    /* Header is the brand lockup - always 'Grace' + eyebrow, never the route
       title. The route title is a body heading now (see seed()). */
    headText.appendChild(el('div', 'head-title', meta.title || 'Grace'));
    var subtitle = route.subtitle || meta.subtitle || 'Guest Assistant';
    headText.appendChild(el('div', 'head-sub', subtitle));
    var closeBtn = el('button', 'close');
    closeBtn.type = 'button';
    closeBtn.setAttribute('aria-label', 'Close');
    closeBtn.innerHTML = CLOSE_SVG;
    head.appendChild(mark);
    head.appendChild(headText);
    head.appendChild(closeBtn);

    var feed = el('div', 'feed');
    feed.setAttribute('role', 'log');
    feed.setAttribute('aria-live', 'polite');

    var options = el('div', 'options');
    var scroll = el('div', 'scroll');
    scroll.appendChild(feed);
    scroll.appendChild(options);
    var pinned = el('div', 'pinned');

    var foot = el('div', 'foot');
    foot.appendChild(el('span', null,
      route.footerHint || meta.footerHint || 'Tap a question to see the answer.'));
    var restart = el('button', 'restart', meta.restartLabel || 'Start over');
    restart.type = 'button';
    foot.appendChild(restart);

    panel.appendChild(head);
    panel.appendChild(scroll);
    panel.appendChild(pinned);
    panel.appendChild(foot);

    /* launcher --------------------------------------------------------- */
    var launcher = el('button', 'launcher');
    launcher.type = 'button';
    launcher.setAttribute('aria-label', route.launcherLabel || meta.launcherLabel || 'Ask a question about visiting');
    launcher.setAttribute('aria-expanded', 'false');
    var launcherPill = el('span', 'launcher-pill',
      route.launcherLabel || meta.launcherLabel || 'Ask Grace');
    var launcherBug = el('span', 'launcher-bug');
    launcherBug.innerHTML = CROSS_SVG;
    launcher.appendChild(launcherPill);
    launcher.appendChild(launcherBug);

    scroll.addEventListener('scroll', updateEdgeFade, { passive: true });

    wrap.appendChild(panel);
    wrap.appendChild(launcher);
    document.body.appendChild(host);

    /* ---- rendering --------------------------------------------------- */

    function askedBubble(text) {
      var row = el('div', 'row from-guest');
      row.appendChild(el('div', 'bubble', text));
      feed.appendChild(row);
    }

    function answerBubble(node) {
      var row = el('div', 'row from-church');
      var bubble = el('div', 'bubble');
      var paras = Array.isArray(node.answer) ? node.answer : [node.answer || ''];
      paras.forEach(function (text) {
        bubble.appendChild(el('p', null, text));
      });
      if (Array.isArray(node.links) && node.links.length) {
        var links = el('div', 'links');
        node.links.forEach(function (link, i) {
          var wrapEl = el('div', 'link-wrap');
          var a = el('a', i === 0 ? 'primary' : 'secondary', link.label || link.href);
          a.href = link.href;
          if (/^https?:/i.test(link.href) && link.href.indexOf(window.location.host) === -1) {
            a.target = '_blank';
            a.rel = 'noopener noreferrer';
          }
          wrapEl.appendChild(a);
          var caption = destinationCaption(link);
          if (caption) wrapEl.appendChild(el('div', 'link-caption', caption));
          links.appendChild(wrapEl);
        });
        bubble.appendChild(links);
      }
      row.appendChild(bubble);
      feed.appendChild(row);
    }

    /* One muted line under each action saying where it actually goes, so a
       guest knows before they tap. Derived from the href, never authored. */
    function destinationCaption(link) {
      var href = String(link.href || '');
      var label = String(link.label || '');
      if (href.indexOf('461746') !== -1) return 'Message goes to the church office';
      if (href.indexOf('tel:') === 0) return 'Calls the church office';
      if (href.indexOf('churchcenter.com') !== -1) {
        var noun = /^give/i.test(label) ? 'giving'
                 : label.toLowerCase().replace(/^(open|see|go to|start|view)\s+/, '');
        return 'Opens ' + (noun || 'the page') + ' \u00b7 Church Center';
      }
      if (href.charAt(0) === '/') return 'Opens discovergrace.com' + href;
      var m = /^https?:\/\/([^\/]+)/i.exec(href);
      if (m) return 'Opens ' + m[1];
      return '';
    }

    /* atHome picks the section label; isHomeCard decides whether Back appears.
       They are NOT the same: an answer card can offer the starter chips as its
       browse list and still need a Back button. */
    function renderOptions(ids, atHome, labelOverride, isHomeCard) {
      /* talk-person is a pinned action now, never a chip. The filter is
         belt-and-suspenders while the Sheet's follow-up lists still mention it.
         The same pass drops anything already tapped, so all three callers -
         seed(), the follow-up render and the starter fallback - inherit the
         hiding from one place and none of them has to remember to. */
      var visible = ids.filter(function (id) {
        if (id === TALK_PERSON_ID) return false;
        if (HIDE_TAPPED && tapped[id]) return false;
        return !!questions[id];
      });

      /* Exhaustion. select() already drops to the starter pool whenever a
         follow-up list filters to nothing, so the only way to arrive here empty
         is that the starter pool is empty too - which is exactly the approved
         condition (current list empty AND starter pool empty). The latch stops
         the handoff re-firing out of talk-person's own render, and out of Back
         landing on the same empty starters card afterwards. */
      if (HIDE_TAPPED && !exhausted && !visible.length && questions[TALK_PERSON_ID]) {
        enterExhaustion();
        return;
      }

      options.textContent = '';
      /* A section heading over zero chips reads as a broken card. Suppressed
         only under the flag - flag-off rendering stays byte-identical. */
      if (visible.length || !HIDE_TAPPED) {
        options.appendChild(el('div', 'options-label', labelOverride || (atHome
          ? (meta.startersLabel || 'Common questions')
          : (meta.followupsLabel || 'People also ask'))));
      }

      visible.forEach(function (id) {
        options.appendChild(chip(questions[id].label, id, false));
      });

      renderPinned(isHomeCard === undefined ? atHome : isHomeCard);
    }

    /* The handoff, via the same handler a tap on the pinned button invokes.
       Two ordering rules, both load-bearing:
         1. Latch BEFORE select(). talk-person has no follow-ups, so select()
            re-enters renderOptions through the starter fallback - still empty -
            and without the latch would call straight back in here forever.
         2. Inject the note AFTER select() returns. select() clears the feed, so
            a note written first would be wiped before the guest ever saw it. */
    function enterExhaustion() {
      exhausted = true;
      select(TALK_PERSON_ID, { suppressEcho: true });

      var row = el('div', 'row from-church');
      var bubble = el('div', 'bubble is-intro');
      bubble.appendChild(el('p', null, EXHAUSTION_NOTE));
      row.appendChild(bubble);
      feed.insertBefore(row, feed.firstChild);
      resetScroll();
    }

    /* Fixed two-button row under the chips: Back (answer views only) and Talk to
       a person (always, straight out of questions['talk-person']). */
    function renderPinned(atHome) {
      pinned.textContent = '';
      if (!atHome) {
        pinned.appendChild(pinButton(meta.homeLabel || '\u2190 Back', '', function () {
          goHome();
        }));
      }
      var person = questions[TALK_PERSON_ID];
      if (person) {
        pinned.appendChild(pinButton(person.label, ' person', function () {
          select(TALK_PERSON_ID);
        }));
      }
    }

    function pinButton(label, extraClass, onClick) {
      var b = el('button', 'pin-btn' + (extraClass || ''), label);
      b.type = 'button';
      b.addEventListener('click', onClick);
      return b;
    }

    function chip(label, id, ghost) {
      var button = el('button', 'chip' + (ghost ? ' ghost' : ''));
      button.type = 'button';
      button.appendChild(el('span', 'text', label));
      button.appendChild(el('span', 'caret', ghost ? '‹' : '›'));
      button.addEventListener('click', function () { select(id); });
      return button;
    }

    /* Single-exchange card model: each view REPLACES the last, and every view
       rests at the top so the question bubble is the first thing a guest sees.
       Nothing accumulates, so nothing pushes the top of the card out of sight. */
    function resetScroll() {
      scroll.scrollTop = 0;
      updateEdgeFade();
    }

    /* The fade is only meaningful while something is still below the fold. */
    function updateEdgeFade() {
      var atEnd = scroll.scrollTop + scroll.clientHeight >= scroll.scrollHeight - 1;
      scroll.classList.toggle('at-end', atEnd);
    }

    /* Back is the history - it returns to the starters card, at the top. */
    function goHome() {
      seed();
      focusFirstOption();
    }

    /* Guards against a slow reply landing after the guest has moved on: every
       request takes a ticket, and only the newest ticket may touch the DOM. */
    var rankTicket = 0;

    /* Input modality. WebKit paints a focus ring on programmatic .focus() even
       for a touch or mouse user, so a guest who taps a question sees the next
       chip highlighted as if they had tabbed to it. We only move focus when the
       guest is actually driving from the keyboard. */
    var lastInputWasKeyboard = false;

    var KEYBOARD_KEYS = {
      Tab: 1, Enter: 1, ' ': 1, Spacebar: 1,
      ArrowUp: 1, ArrowDown: 1, ArrowLeft: 1, ArrowRight: 1,
      Home: 1, End: 1
    };

    function markPointer() { lastInputWasKeyboard = false; }
    function markKeyboard(event) {
      if (event && KEYBOARD_KEYS[event.key]) lastInputWasKeyboard = true;
    }

    ['pointerdown', 'mousedown', 'touchstart'].forEach(function (type) {
      var opts = { capture: true, passive: true };
      root.addEventListener(type, markPointer, opts);
      document.addEventListener(type, markPointer, opts);
    });
    root.addEventListener('keydown', markKeyboard, true);
    document.addEventListener('keydown', markKeyboard, true);

    /**
     * Optional enhancement. Asks the router to reorder the follow-up chips that
     * are ALREADY on screen. Any failure is silent - the static chips stay put.
     * Never throws into the render path.
     */
    function rankFollowups(tappedId, followups) {
      var ticket = ++rankTicket;
      var controller = new AbortController();
      var timer = setTimeout(function () { controller.abort(); }, ROUTER_TIMEOUT_MS);

      fetch(ROUTER_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          page: routePath,
          tappedId: tappedId,
          history: [], /* TODO: send the IDs the guest has already tapped - the
                          router accepts them today, the widget does not track
                          them yet. Future enhancement. */
          candidateIds: followups
        }),
        signal: controller.signal
      })
        .then(function (response) {
          return response.ok ? response.json() : null;
        })
        .then(function (data) {
          if (ticket !== rankTicket) return;      /* guest already tapped again */
          if (!data || !Array.isArray(data.ids) || !data.ids.length) return;

          /* reorder disabled 2026-08-27 (layout-shift misclicks); revisit with
             render-once design if corpus grows. The POST stays so we keep
             collecting ranking signal - it just no longer touches the DOM. */
          console.debug('ga-rank', tappedId, data.ids);
        })
        .catch(function () { /* offline, aborted, bad JSON - static chips stand */ })
        .then(function () { clearTimeout(timer); });
    }

    /* opts.suppressEcho drops the guest bubble. A tap is a question the guest
       asked, so it is echoed; the exhaustion handoff is the widget's own move,
       and echoing 'Talk to a person' there would put words in their mouth. */
    function select(id, opts) {
      if (id === HOME_ID) { goHome(); return; }
      var node = questions[id];
      if (!node) return;

      /* Record before rendering, so the question just tapped is already gone
         from the lists this same render builds. talk-person is exempt: it is a
         pinned action and must never count toward exhaustion. */
      if (HIDE_TAPPED && id !== TALK_PERSON_ID) tapped[id] = true;

      /* Clear first - this view is the whole card, not another entry in a log. */
      feed.textContent = '';
      if (!(opts && opts.suppressEcho)) askedBubble(node.label);
      answerBubble(node);

      var followups = (node.followups || []).filter(function (fid) {
        return questions[fid] && fid !== TALK_PERSON_ID;
      });
      /* A follow-up list that filters to nothing is NOT exhaustion while
         starters remain - it drops to the browse list below, which renderOptions
         filters again. Flag off, this is the same array as followups. */
      var visibleFollowups = followups.filter(function (fid) {
        return !(HIDE_TAPPED && tapped[fid]);
      });
      /* After 'Talk to a person' the remaining chips are a browsing offer, not a
         follow-up set - the mockup labels them accordingly. */
      var override = id === TALK_PERSON_ID ? 'OR KEEP BROWSING' : null;
      if (visibleFollowups.length) {
        renderOptions(visibleFollowups, false, override, false);
      } else {
        /* No follow-ups: offer the starters as a browse list, but this is still
           an answer card, so Back stays. */
        renderOptions(starters.filter(function (sid) { return sid !== id; }), true, override, false);
      }
      resetScroll();
      focusFirstOption();

      /* Everything above already happened. This can only reorder what is there. */
      if (ROUTER_URL && visibleFollowups.length >= 2) {
        try {
          rankFollowups(id, visibleFollowups);
        } catch (err) {
          /* never let the enhancement break the answer that is already shown */
        }
      }
    }

    /* Only moves focus for keyboard users. Pointer/touch guests get the answer
       and the new chips with no ring - the aria-live region still announces the
       answer either way, so screen-reader flow is unchanged. */
    function focusFirstOption() {
      if (!lastInputWasKeyboard) return;
      var first = options.querySelector('.chip');
      if (first) first.focus({ preventScroll: true });
    }

    function seed() {
      feed.textContent = '';
      if (route.title) {
        feed.appendChild(el('div', 'route-heading', route.title));
      }
      if (route.intro || meta.intro) {
        var row = el('div', 'row from-church');
        var bubble = el('div', 'bubble is-intro');
        bubble.appendChild(el('p', null, route.intro || meta.intro));
        row.appendChild(bubble);
        feed.appendChild(row);
      }
      renderOptions(starters, true, null, true);
      resetScroll();
    }

    /* ---- open / close ------------------------------------------------ */

    var isOpen = false;

    function open() {
      if (isOpen) return;
      isOpen = true;
      panel.classList.add('is-visible');
      wrap.classList.add('is-open');
      launcher.setAttribute('aria-expanded', 'true');
      launcherBug.innerHTML = CLOSE_SVG;
      launcherPill.style.display = 'none';
      launcher.setAttribute('aria-label', 'Close');
      requestAnimationFrame(function () { panel.classList.add('is-open'); });
      /* If the guest closed the panel mid-card, reopening should not flash the
         old scroll position before they can read the top. */
      resetScroll();
      focusFirstOption();
    }

    function close() {
      if (!isOpen) return;
      isOpen = false;
      panel.classList.remove('is-open');
      wrap.classList.remove('is-open');
      launcher.setAttribute('aria-expanded', 'false');
      launcherBug.innerHTML = CROSS_SVG;
      launcherPill.style.display = '';
      launcher.setAttribute('aria-label', route.launcherLabel || meta.launcherLabel || 'Ask a question about visiting');
      window.setTimeout(function () {
        if (!isOpen) panel.classList.remove('is-visible');
      }, 190);
      /* Same rule as focusFirstOption: only move focus when the guest is
         actually driving from the keyboard. Returning focus to the launcher
         after a tap paints a ring on it in WebKit, as if it had been tabbed to.
         Keyboard users still get it - closing must not strand focus on a panel
         that is no longer there. */
      if (lastInputWasKeyboard) launcher.focus({ preventScroll: true });
    }

    launcher.addEventListener('click', function () { isOpen ? close() : open(); });
    closeBtn.addEventListener('click', close);
    /* Start over is the labelled reset, so it clears the flag-gated state too:
       otherwise a guest who has already been handed to a person taps it and
       lands on a card with no questions on it. Back does not clear - Back is
       navigation, not a reset. Both lines are no-ops with the flag off. */
    restart.addEventListener('click', function () {
      tapped = {};
      exhausted = false;
      seed();
      focusFirstOption();
    });
    root.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && isOpen) { event.stopPropagation(); close(); }
    });

    seed();
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function start() {
    fetch(ANSWERS_URL, { credentials: 'same-origin' })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(build)
      .catch(function (error) {
        /* Fail quietly on the visitor's side - a broken answers file should
           never put a broken widget on the church's website. */
        console.error('[grace-assistant] could not load ' + ANSWERS_URL + ':', error);
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
