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

  var NAVY = '#292E38';
  var ORANGE = '#FF5400';
  var CREAM = '#FAFAF7';
  var RADIUS = '4px';

  var HOME_ID = '__home';

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
    '  position: fixed; right: 20px; bottom: 20px; z-index: 2147483000;',
    '  display: flex; flex-direction: column; align-items: flex-end; gap: 12px;',
    '  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;',
    '  color: ' + NAVY + '; font-size: 15px; line-height: 1.5;',
    '  -webkit-font-smoothing: antialiased;',
    '}',

    /* ---- launcher ---- */
    '.launcher {',
    '  width: 60px; height: 60px; border: 0; border-radius: 50%;',
    '  background: ' + ORANGE + '; color: #FFFFFF; cursor: pointer;',
    '  display: flex; align-items: center; justify-content: center;',
    '  box-shadow: 0 6px 20px rgba(41, 46, 56, 0.28);',
    '  transition: transform 140ms ease, box-shadow 140ms ease;',
    '  flex: none;',
    '}',
    '.launcher:hover { transform: translateY(-2px); box-shadow: 0 10px 26px rgba(41, 46, 56, 0.32); }',
    '.launcher:active { transform: translateY(0); }',
    '.launcher:focus-visible { outline: 3px solid ' + NAVY + '; outline-offset: 3px; }',
    '.launcher svg { width: 30px; height: 30px; fill: #FFFFFF; }',
    '.launcher .icon-close { width: 24px; height: 24px; }',

    /* ---- panel ---- */
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
    '.head-title { font-size: 15px; font-weight: 650; letter-spacing: -0.01em; }',
    '.head-sub { font-size: 12px; color: rgba(41, 46, 56, 0.62); margin-top: 1px; }',
    '.close {',
    '  flex: none; width: 30px; height: 30px; border: 0; border-radius: ' + RADIUS + ';',
    '  background: transparent; color: ' + NAVY + '; cursor: pointer;',
    '  display: flex; align-items: center; justify-content: center;',
    '}',
    '.close:hover { background: rgba(41, 46, 56, 0.07); }',
    '.close:focus-visible { outline: 2px solid ' + ORANGE + '; outline-offset: 1px; }',
    '.close svg { width: 18px; height: 18px; }',

    /* ---- feed ---- */
    '.feed {',
    '  flex: 1 1 auto; min-height: 0; overflow-y: auto;',
    '  padding: 16px; display: flex; flex-direction: column; gap: 12px;',
    '  overscroll-behavior: contain;',
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
    '.bubble a {',
    '  color: ' + ORANGE + '; font-weight: 600; text-decoration: none;',
    '  border-bottom: 1px solid rgba(255, 84, 0, 0.4);',
    '}',
    '.bubble a:hover { border-bottom-color: ' + ORANGE + '; }',
    '.links { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }',
    '.intro { font-size: 13px; color: rgba(41, 46, 56, 0.66); padding: 2px 2px 0; }',

    /* ---- options ---- */
    '.options {',
    '  flex: none; padding: 12px 16px 14px;',
    '  border-top: 1px solid rgba(41, 46, 56, 0.10);',
    '  display: flex; flex-direction: column; gap: 8px;',
    '  max-height: 46%; overflow-y: auto; overscroll-behavior: contain;',
    '}',
    '.options-label {',
    '  font-size: 11px; font-weight: 650; letter-spacing: 0.07em;',
    '  text-transform: uppercase; color: rgba(41, 46, 56, 0.5); margin-bottom: 2px;',
    '}',
    '.chip {',
    '  display: flex; align-items: center; gap: 10px; width: 100%; text-align: left;',
    '  font: inherit; font-size: 14.5px; color: ' + NAVY + '; cursor: pointer;',
    '  background: #FFFFFF; border: 1px solid rgba(41, 46, 56, 0.16);',
    '  border-radius: ' + RADIUS + '; padding: 10px 12px;',
    '  transition: border-color 120ms ease, background 120ms ease;',
    '}',
    '.chip:hover { border-color: ' + ORANGE + '; background: #FFF6F1; }',
    '.chip:focus-visible { outline: 2px solid ' + ORANGE + '; outline-offset: 1px; }',
    '.chip .text { flex: 1 1 auto; }',
    '.chip .caret { flex: none; color: ' + ORANGE + '; font-size: 17px; line-height: 1; }',
    '.chip.ghost { background: transparent; border-style: dashed; color: rgba(41, 46, 56, 0.72); }',
    '.chip.ghost:hover { background: rgba(255, 84, 0, 0.05); }',

    /* ---- footer ---- */
    '.foot {',
    '  flex: none; display: flex; align-items: center; justify-content: space-between;',
    '  gap: 10px; padding: 9px 16px 11px;',
    '  border-top: 1px solid rgba(41, 46, 56, 0.10);',
    '  font-size: 11.5px; color: rgba(41, 46, 56, 0.55);',
    '}',
    '.restart {',
    '  font: inherit; font-size: 11.5px; font-weight: 600; color: ' + ORANGE + ';',
    '  background: transparent; border: 0; border-radius: ' + RADIUS + ';',
    '  padding: 3px 5px; cursor: pointer;',
    '}',
    '.restart:hover { background: rgba(255, 84, 0, 0.09); }',
    '.restart:focus-visible { outline: 2px solid ' + ORANGE + '; outline-offset: 1px; }',

    /* ---- small screens ---- */
    '@media (max-width: 480px) {',
    '  .wrap { right: 12px; left: 12px; bottom: 12px; align-items: stretch; }',
    '  .panel { width: auto; height: 74vh; max-height: calc(100vh - 108px); }',
    '  .launcher { align-self: flex-end; }',
    '}',

    '@media (prefers-reduced-motion: reduce) {',
    '  .panel, .launcher, .chip { transition: none; }',
    '}'
  ].join('\n');

  /* ------------------------------------------------------------------ */
  /* Widget                                                              */
  /* ------------------------------------------------------------------ */

  function build(data) {
    var meta = data.meta || {};
    var questions = data.questions || {};
    var route = pickRoute(data.routes || {}, script.getAttribute('data-route') || queryRoute() || window.location.pathname);
    var starters = (route.starters || []).filter(function (id) { return questions[id]; });

    if (!starters.length) return; /* nothing to ask here - stay off the page */

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
    panel.setAttribute('aria-label', meta.title || 'Questions about visiting');

    var head = el('div', 'head');
    var mark = el('span', 'mark');
    mark.innerHTML = CROSS_SVG;
    var headText = el('div', 'head-text');
    headText.appendChild(el('div', 'head-title', meta.title || 'Planning a visit?'));
    if (meta.subtitle) headText.appendChild(el('div', 'head-sub', meta.subtitle));
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

    var foot = el('div', 'foot');
    foot.appendChild(el('span', null, meta.footerHint || 'Tap a question to see the answer.'));
    var restart = el('button', 'restart', meta.restartLabel || 'Start over');
    restart.type = 'button';
    foot.appendChild(restart);

    panel.appendChild(head);
    panel.appendChild(feed);
    panel.appendChild(options);
    panel.appendChild(foot);

    /* launcher --------------------------------------------------------- */
    var launcher = el('button', 'launcher');
    launcher.type = 'button';
    launcher.setAttribute('aria-label', meta.launcherLabel || 'Ask a question about visiting');
    launcher.setAttribute('aria-expanded', 'false');
    launcher.innerHTML = CROSS_SVG;

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
        node.links.forEach(function (link) {
          var a = el('a', null, link.label || link.href);
          a.href = link.href;
          if (/^https?:/i.test(link.href) && link.href.indexOf(window.location.host) === -1) {
            a.target = '_blank';
            a.rel = 'noopener noreferrer';
          }
          links.appendChild(a);
        });
        bubble.appendChild(links);
      }
      row.appendChild(bubble);
      feed.appendChild(row);
    }

    function renderOptions(ids, atHome) {
      options.textContent = '';
      options.appendChild(el('div', 'options-label', atHome
        ? (meta.startersLabel || 'Common questions')
        : (meta.followupsLabel || 'People also ask')));

      ids.forEach(function (id) {
        var node = questions[id];
        if (!node) return;
        options.appendChild(chip(node.label, id, false));
      });

      if (!atHome) {
        options.appendChild(chip(meta.homeLabel || 'Back to the main questions', HOME_ID, true));
      }
    }

    function chip(label, id, ghost) {
      var button = el('button', 'chip' + (ghost ? ' ghost' : ''));
      button.type = 'button';
      button.appendChild(el('span', 'text', label));
      button.appendChild(el('span', 'caret', ghost ? '‹' : '›'));
      button.addEventListener('click', function () { select(id); });
      return button;
    }

    function scrollFeed() {
      feed.scrollTop = feed.scrollHeight;
    }

    function goHome(silent) {
      if (!silent) askedBubble(meta.homeLabel || 'Back to the main questions');
      renderOptions(starters, true);
      scrollFeed();
      focusFirstOption();
    }

    function select(id) {
      if (id === HOME_ID) { goHome(false); return; }
      var node = questions[id];
      if (!node) return;

      askedBubble(node.label);
      answerBubble(node);

      var followups = (node.followups || []).filter(function (fid) { return questions[fid]; });
      if (followups.length) {
        renderOptions(followups, false);
      } else {
        renderOptions(starters.filter(function (sid) { return sid !== id; }), true);
      }
      scrollFeed();
      focusFirstOption();
    }

    function focusFirstOption() {
      var first = options.querySelector('.chip');
      if (first) first.focus({ preventScroll: true });
    }

    function seed() {
      feed.textContent = '';
      if (route.intro || meta.intro) {
        var row = el('div', 'row from-church');
        var bubble = el('div', 'bubble');
        bubble.appendChild(el('p', null, route.intro || meta.intro));
        row.appendChild(bubble);
        feed.appendChild(row);
      }
      renderOptions(starters, true);
      feed.scrollTop = 0;
    }

    /* ---- open / close ------------------------------------------------ */

    var isOpen = false;

    function open() {
      if (isOpen) return;
      isOpen = true;
      panel.classList.add('is-visible');
      launcher.setAttribute('aria-expanded', 'true');
      launcher.innerHTML = CLOSE_SVG;
      launcher.querySelector('svg').setAttribute('class', 'icon-close');
      launcher.setAttribute('aria-label', 'Close');
      requestAnimationFrame(function () { panel.classList.add('is-open'); });
      focusFirstOption();
    }

    function close() {
      if (!isOpen) return;
      isOpen = false;
      panel.classList.remove('is-open');
      launcher.setAttribute('aria-expanded', 'false');
      launcher.innerHTML = CROSS_SVG;
      launcher.setAttribute('aria-label', meta.launcherLabel || 'Ask a question about visiting');
      window.setTimeout(function () {
        if (!isOpen) panel.classList.remove('is-visible');
      }, 190);
      launcher.focus({ preventScroll: true });
    }

    launcher.addEventListener('click', function () { isOpen ? close() : open(); });
    closeBtn.addEventListener('click', close);
    restart.addEventListener('click', function () { seed(); focusFirstOption(); });
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
