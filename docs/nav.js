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
    if (a.href.replace(/index\.html$/, '') === here)
      a.setAttribute('aria-current', 'page');
    return a;
  }
  // Two audiences: people trying the corpus (Library, Showcase, Feedback) and the proposal (About menu)
  inner.appendChild(link('', 'Gpura Corpus', 'brand'));
  var lib = link('library/', 'Library');
  if (/\/(library|book|read|specimen)\//.test(here)) lib.setAttribute('aria-current', 'page');
  inner.appendChild(lib);
  inner.appendChild(link('showcase/', 'Showcase'));
  inner.appendChild(Object.assign(document.createElement('a'), {
    href: 'https://github.com/beniza/gpura-corpus/issues/new?template=corpus-feedback.md', textContent: 'Feedback' }));
  var about = document.createElement('details');
  var asum = document.createElement('summary');
  asum.textContent = 'About';
  var amenu = document.createElement('div');
  amenu.className = 'menu';
  [['proposal/', 'Proposal', 'Why Gpura should build the corpus (English and Malayalam)'],
   ['paper/', 'Paper', 'The encoding model, pipeline, experiments and costs'],
   ['walkthrough/', 'Walkthrough', 'Three pages of one book, from scan to corpus']].forEach(function (x) {
    var a = link(x[0], '');
    var t = document.createElement('span'); t.textContent = x[1];
    var sm = document.createElement('small'); sm.textContent = x[2];
    a.appendChild(t); a.appendChild(sm); amenu.appendChild(a);
    if (a.getAttribute('aria-current')) asum.style.color = 'var(--accent,#2b6a8a)';
  });
  var code = Object.assign(document.createElement('a'), { href: 'https://github.com/beniza/gpura-corpus' });
  var ct = document.createElement('span'); ct.textContent = 'Code';
  var cs = document.createElement('small'); cs.textContent = 'The pipeline on GitHub (MIT; data CC0)';
  code.appendChild(ct); code.appendChild(cs); amenu.appendChild(code);
  about.appendChild(asum); about.appendChild(amenu);
  inner.appendChild(about);
  document.addEventListener('click', function (e) { if (!about.contains(e.target)) about.open = false; });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') about.open = false; });

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
