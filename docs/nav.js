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
  inner.appendChild(link('paper/', 'Paper'));
  inner.appendChild(link('proposal/', 'Proposal'));
  inner.appendChild(link('walkthrough/', 'Walkthrough'));

  var dd = document.createElement('details');
  var sm = document.createElement('summary');
  sm.textContent = 'Books';
  var menu = document.createElement('div');
  menu.className = 'menu';
  dd.appendChild(sm);
  dd.appendChild(menu);
  inner.appendChild(dd);
  inner.appendChild(Object.assign(document.createElement('a'), { href: 'https://github.com/beniza/gpura-corpus', textContent: 'Code' }));

  document.addEventListener('click', function (e) { if (!dd.contains(e.target)) dd.open = false; });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') dd.open = false; });

  fetch(u('specimen/index.json')).then(function (r) { return r.json(); }).then(function (books) {
    books.forEach(function (b) {
      var a = link('specimen/' + b.item + '/', '');
      var t = document.createElement('span');
      t.className = 'ml';
      t.textContent = b.title;
      var s = document.createElement('small');
      s.textContent = [b.title_en, b.date, b.pages + ' pages', b.automatic ? 'automatic' : 'reviewed'].filter(Boolean).join(' · ');
      a.appendChild(t);
      a.appendChild(s);
      menu.appendChild(a);
      if (a.getAttribute('aria-current')) sm.style.color = 'var(--accent,#2b6a8a)';
    });
  }).catch(function () { dd.remove(); });

  document.body.insertBefore(nav, document.body.firstChild);
})();
