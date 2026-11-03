/* Site-wide navigation bar. Every page loads it with <script src=".../nav.js" defer>.
   The list of books comes from specimen/index.json, which run.py's site stage rewrites,
   so a newly encoded book shows up here without editing any page. */
(function () {
  var me = document.currentScript || document.querySelector('script[src$="nav.js"]');
  var root = new URL('.', me.src);
  var here = location.href.split('#')[0].replace(/index\.html$/, '');
  var u = function (p) { return new URL(p, root).href; };

  var css = document.createElement('style');
  css.textContent =
    '.gnav{position:sticky;top:0;z-index:50;background:var(--surface,#fff);border-bottom:1px solid var(--line,#ddd);' +
    'font-family:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;font-size:.9rem;line-height:1.4}' +
    '.gnav .in{max-width:1100px;margin:0 auto;padding:0 16px;display:flex;align-items:center;gap:4px;flex-wrap:wrap;min-height:46px}' +
    '.gnav a,.gnav summary{color:var(--fg,#1b2220);text-decoration:none;padding:6px 10px;border-radius:6px;cursor:pointer;white-space:nowrap}' +
    '.gnav a:hover,.gnav summary:hover{background:var(--sunk,rgba(0,0,0,.05))}' +
    '.gnav a[aria-current="page"]{color:var(--accent,#2b6a8a);font-weight:600}' +
    '.gnav .brand{font-weight:700;margin-right:6px}' +
    '.gnav details{position:relative}.gnav summary{list-style:none}.gnav summary::-webkit-details-marker{display:none}' +
    '.gnav summary::after{content:" \\25BE";color:var(--muted,#5a6662)}' +
    '.gnav .menu{position:absolute;left:0;top:calc(100% + 4px);min-width:min(320px,calc(100vw - 32px));background:var(--surface,#fff);' +
    'border:1px solid var(--line,#ddd);border-radius:8px;padding:6px;box-shadow:0 8px 24px rgba(0,0,0,.12);display:flex;flex-direction:column}' +
    '.gnav .menu a{white-space:normal;display:flex;flex-direction:column;gap:2px}' +
    '.gnav .menu small{color:var(--muted,#5a6662);font-size:.78rem}' +
    '.gnav .ml{font-family:"Noto Serif Malayalam",serif}' +
    '@media (max-width:520px){.gnav .menu{position:fixed;left:16px;right:16px;top:auto}}';
  document.head.appendChild(css);

  var nav = document.createElement('nav');
  nav.className = 'gnav';
  nav.setAttribute('aria-label', 'Site');
  var inner = document.createElement('div');
  inner.className = 'in';
  nav.appendChild(inner);

  function link(href, text, cls) {
    var a = document.createElement('a');
    a.href = u(href);
    a.textContent = text;
    if (cls) a.className = cls;
    if (a.href.replace(/index\.html$/, '') === here) a.setAttribute('aria-current', 'page');
    return a;
  }
  inner.appendChild(link('', 'Gpura Corpus', 'brand'));
  inner.appendChild(link('proposal/', 'Proposal'));
  inner.appendChild(link('paper/', 'Paper'));
  inner.appendChild(link('walkthrough/', 'Walkthrough'));

  // Showcase: one encoded page per layout type (docs/showcase.json), then every book (specimen/index.json)
  var dd = document.createElement('details');
  var sm = document.createElement('summary');
  sm.textContent = 'Showcase';
  var menu = document.createElement('div');
  menu.className = 'menu';
  dd.appendChild(sm);
  dd.appendChild(menu);
  inner.appendChild(dd);
  inner.appendChild(Object.assign(document.createElement('a'), { href: 'https://github.com/beniza/gpura-corpus', textContent: 'Code' }));

  document.addEventListener('click', function (e) { if (!dd.contains(e.target)) dd.open = false; });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') dd.open = false; });

  function head(text) {
    var h = document.createElement('div');
    h.className = 'mh';
    h.textContent = text;
    menu.appendChild(h);
  }
  function entry(href, title, note, ml) {
    var a = link(href, '');
    var t = document.createElement('span');
    if (ml) t.className = 'ml';
    t.textContent = title;
    var s = document.createElement('small');
    s.textContent = note;
    a.appendChild(t);
    a.appendChild(s);
    menu.appendChild(a);
    if (a.href.split('#')[0].replace(/index\.html$/, '') === here) sm.style.color = 'var(--accent,#2b6a8a)';
  }
  Promise.all([
    fetch(u('showcase.json')).then(function (r) { return r.json(); }).catch(function () { return []; }),
    fetch(u('specimen/index.json')).then(function (r) { return r.json(); }).catch(function () { return []; })
  ]).then(function (res) {
    var show = res[0], books = res[1];
    var byItem = {};
    books.forEach(function (b) { byItem[b.item] = b; });
    if (show.length) head('By page layout');
    show.forEach(function (s) {
      var b = byItem[s.item] || {};
      entry('specimen/' + s.item + '/#' + s.page, s.layout,
        [b.title_en || s.item, b.date, 'p. ' + parseInt(s.page.slice(1), 10), s.text].filter(Boolean).join(' · '));
    });
    if (books.length) head('All books');
    books.forEach(function (b) {
      entry('specimen/' + b.item + '/', b.title,
        [b.title_en, b.date, b.pages + (b.pages === 1 ? ' page' : ' pages'), b.automatic ? 'automatic' : 'reviewed'].filter(Boolean).join(' · '), true);
    });
    if (!show.length && !books.length) dd.remove();
  });

  // Malayalam script style: old (traditional orthography, RIT Rachana) or new (reformed, Noto Serif Malayalam).
  // Same Unicode text either way: only the font changes, so search and copy are unaffected.
  var gf = document.createElement('link');
  gf.rel = 'stylesheet';
  gf.href = 'https://fonts.googleapis.com/css2?family=Noto+Serif+Malayalam:wght@400;600&display=swap';
  document.head.appendChild(gf);
  var lipiCss = document.createElement('style');
  lipiCss.textContent =
    '@font-face{font-family:"RIT Rachana";src:url("' + u('fonts/rit-rachana/RIT-Rachana-Regular.woff2') + '") format("woff2");font-weight:400;font-display:swap}' +
    '@font-face{font-family:"RIT Rachana";src:url("' + u('fonts/rit-rachana/RIT-Rachana-Bold.woff2') + '") format("woff2");font-weight:700;font-display:swap}' +
    'html[data-lipi="old"] :is(.ml,[lang="ml"],.reading,.tei-reading,.tei-text,.rt-line){font-family:"RIT Rachana","Noto Serif Malayalam",serif!important}' +
    'html[data-lipi="new"] :is(.ml,[lang="ml"],.reading,.tei-reading,.tei-text,.rt-line){font-family:"Noto Serif Malayalam",serif!important}' +
    'html :is([lang="ml"],.tei-reading) :is([lang="en"],.controls,.who){font-family:"IBM Plex Sans",system-ui,sans-serif!important}' +
    '.gnav .lipi{margin-left:auto;display:inline-flex;border:1px solid var(--line,#ddd);border-radius:7px;overflow:hidden}' +
    '.gnav .lipi button{font:inherit;font-size:.82rem;border:0;background:none;color:var(--muted,#5a6662);padding:5px 10px;cursor:pointer}' +
    '.gnav .lipi button[aria-pressed="true"]{background:var(--fg,#1b2220);color:var(--bg,#fff)}' +
    '.gnav .menu .mh{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted,#5a6662);padding:8px 10px 2px;font-weight:600}';
  document.head.appendChild(lipiCss);
  var lipi = 'new';
  try { lipi = localStorage.getItem('gpura-lipi') || 'new'; } catch (e) {}
  document.documentElement.dataset.lipi = lipi;
  var seg = document.createElement('div');
  seg.className = 'lipi';
  seg.setAttribute('role', 'group');
  seg.setAttribute('aria-label', 'Malayalam script style');
  [['old', 'Old script', 'പഴയ ലിപി: traditional orthography (RIT Rachana)'],
   ['new', 'New script', 'പുതിയ ലിപി: reformed orthography (Noto Serif Malayalam)']].forEach(function (o) {
    var b = document.createElement('button');
    b.type = 'button';
    b.textContent = o[1];
    b.title = o[2];
    b.setAttribute('aria-pressed', String(lipi === o[0]));
    b.addEventListener('click', function () {
      lipi = o[0];
      document.documentElement.dataset.lipi = lipi;
      try { localStorage.setItem('gpura-lipi', lipi); } catch (e) {}
      seg.querySelectorAll('button').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      document.dispatchEvent(new CustomEvent('gpura-lipi', { detail: lipi }));
    });
    seg.appendChild(b);
  });
  inner.appendChild(seg);

  document.body.insertBefore(nav, document.body.firstChild);
})();
