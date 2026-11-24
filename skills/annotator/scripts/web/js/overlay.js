// Overlay runtime. Needs window.__WA__ = {title, summary, notes:[...]} and common.js loaded first.
(function () {
  'use strict';
  const C = window.__WA_COMMON__;
  const TYPES = {
    CONCERN:     { label: 'Concern',     color: '#e5484d' },
    VERIFY:      { label: 'To verify',   color: '#f5a524' },
    SPECULATION: { label: 'Speculation', color: '#8e4ec6' },
    NOTE:        { label: 'Note',        color: '#3e63dd' },
    CHECKED:     { label: 'Checked',     color: '#12a594' },
    STRENGTH:    { label: 'Strength',    color: '#30a46c' },
  };
  const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* ignore */ } },
  };
  const tcolor = a => (TYPES[a.type] || TYPES.NOTE).color;

  const css = `
  .ga-ui,.ga-mark,.ga-box{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .ga-mark{background:color-mix(in srgb,var(--c) 24%,transparent);border-bottom:2px solid var(--c);color:inherit;border-radius:2px;cursor:pointer;padding:0 1px}
  .ga-mark.ga-off{background:none;border-bottom-color:transparent}
  .ga-mark.ga-flash,.ga-figwrap.ga-flash{outline:3px solid var(--c,#333);outline-offset:2px}
  .ga-badge{background:var(--c);color:#fff;font:700 10px/1 system-ui,sans-serif;padding:2px 4px;border-radius:8px;margin-left:2px;cursor:pointer;vertical-align:super}
  .ga-badge.ga-off{display:none}
  .ga-figwrap{position:relative;display:inline-block;vertical-align:top;max-width:100%;line-height:0}
  .ga-box{position:absolute;box-sizing:border-box;border:2px solid var(--c);background:color-mix(in srgb,var(--c) 14%,transparent);cursor:pointer;z-index:5}
  .ga-box.ga-whole{border-style:dashed;background:none}
  .ga-figwrap-self{position:relative}
  .ga-box.ga-off{display:none}
  .ga-box .ga-badge{position:absolute;left:-2px;top:-2px;margin:0;border-radius:0 0 6px 0;vertical-align:baseline;line-height:1.1;font-size:11px;padding:2px 6px;white-space:nowrap}
  .ga-ui{font-family:system-ui,-apple-system,Segoe UI,sans-serif}
  #ga-launch{position:fixed;right:16px;bottom:16px;z-index:2147483000;background:#111;color:#fff;border:0;border-radius:20px;padding:9px 14px;font:600 13px system-ui,sans-serif;cursor:pointer;box-shadow:0 2px 10px #0006}
  #ga-drawer{position:fixed;top:0;right:0;width:370px;max-width:92vw;height:100vh;z-index:2147483001;overflow:auto;background:#fff;color:#1a1a1a;border-left:1px solid #ddd;box-shadow:-4px 0 18px #0002;padding:14px 14px 40px;font-size:13px;line-height:1.45;display:none;text-align:left}
  #ga-drawer.open{display:block}
  @media (prefers-color-scheme:dark){#ga-drawer{background:#161616;color:#eee;border-color:#333}.ga-card{border-color:#333!important}.ga-chip{color:#eee!important}}
  #ga-drawer h3{margin:0 0 4px;font-size:15px}
  #ga-drawer h4{margin:16px 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;opacity:.7}
  .ga-sum{margin:8px 0;padding:8px 10px;border-radius:6px;background:#8881;font-size:12.5px}
  .ga-row{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
  .ga-chip{border:1.5px solid var(--c);background:transparent;color:#222;border-radius:12px;padding:2px 8px;font-size:11px;cursor:pointer}
  .ga-chip.on{background:var(--c);color:#fff!important}
  .ga-card{border:1px solid #e3e3e3;border-left:4px solid var(--c);border-radius:6px;padding:8px 10px;margin:8px 0;cursor:pointer}
  .ga-card.sel{box-shadow:0 0 0 2px var(--c)}
  .ga-card .hd{font-weight:700;font-size:11px;color:var(--c);margin-bottom:3px}
  .ga-card .lk{margin-top:5px;font-size:11px;opacity:.85}
  .ga-card .lk a{color:inherit;text-decoration:underline;margin-right:6px;cursor:pointer}
  .ga-btn{border:1px solid #bbb;background:transparent;color:inherit;border-radius:6px;padding:3px 8px;font-size:11px;cursor:pointer;margin-right:4px}
  body.ga-shift{margin-right:370px!important}
  #ga-print{display:none;color:#111;background:#fff;padding:18px 24px;font-size:12px;line-height:1.45}
  #ga-print h2{font-size:17px;margin:0 0 6px}
  #ga-print .it{border-left:4px solid var(--c);padding:3px 8px;margin:6px 0;break-inside:avoid}
  #ga-print .it b{color:var(--c)}
  @media print{.ga-box[data-frame]{border:0;background:none}#ga-print{display:block;break-before:page}#ga-launch,#ga-drawer{display:none!important}body.ga-shift{margin-right:0!important}}
  `;

  function wrapRange(nodes, starts, s, e, a) {
    const marks = [];
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i], ns = starts[i], ne = ns + n.nodeValue.length;
      if (ne <= s || ns >= e) continue;
      const r = document.createRange();
      r.setStart(n, Math.max(s, ns) - ns);
      r.setEnd(n, Math.min(e, ne) - ns);
      const mk = document.createElement('mark');
      mk.className = 'ga-mark';
      mk.dataset.key = a.key;
      mk.style.setProperty('--c', tcolor(a));
      mk.title = (TYPES[a.type] || TYPES.NOTE).label + ': ' + a.note;
      mk.appendChild(r.extractContents());
      r.insertNode(mk);
      marks.unshift(mk);
    }
    if (!marks.length) return false;
    const b = document.createElement('sup');
    b.className = 'ga-ui ga-badge'; b.dataset.key = a.key; b.style.setProperty('--c', tcolor(a));
    marks[marks.length - 1].after(b);
    a.el = marks[0]; a.marks = marks; a.badge = b; a.kindEl = 'text';
    return true;
  }

  function anchorText(a, ROOT) {
    const re = new RegExp(a.quote.split(/\s+/).map(esc).join('\\s+'));
    const blocks = [...ROOT.querySelectorAll(C.BLOCK_SEL)].filter(C.isLeaf);
    for (const b of blocks) {                      // tier 1: within one block, across inline tags
      const nodes = C.textNodesOf(b);
      if (!nodes.length) continue;
      let full = ''; const starts = [];
      for (const n of nodes) { starts.push(full.length); full += n.nodeValue; }
      const m = re.exec(full);
      if (m && wrapRange(nodes, starts, m.index, m.index + m[0].length, a)) return true;
    }
    for (const n of C.textNodesOf(ROOT)) {         // tier 2: any single text node
      const m = re.exec(n.nodeValue);
      if (m && wrapRange([n], [0], m.index, m.index + m[0].length, a)) return true;
    }
    return false;
  }

  // Figure placement: the wrapper hugs the displayed media element; boxes are laid out in px against the
  // *content* rectangle of the media (honours object-fit/object-position for img/video and viewBox +
  // preserveAspectRatio for inline svg), so a normalised [x,y,w,h] lands on the same pixels of the figure
  // that the PNG given to the reader showed. Re-laid-out on resize and image load (responsive pages).
  const REPLACED = /^(IMG|VIDEO|SVG|CANVAS|IFRAME)$/i;
  function wrapFigure(el) {
    const target = el.closest('picture') || el;
    if (!REPLACED.test(el.tagName)) {               // CSS background-image block etc.: overlay inside the element itself
      if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
      el.classList.add('ga-figwrap-self');
      return el;
    }
    if (target.parentElement && target.parentElement.classList.contains('ga-figwrap')) return target.parentElement;
    const r = target.getBoundingClientRect();
    const w = document.createElement('span');
    w.className = 'ga-figwrap';
    w.style.width = Math.round(r.width) + 'px';
    target.parentNode.insertBefore(w, target);
    w.appendChild(target);
    const fit = el.tagName === 'IMG' || el.tagName === 'VIDEO' ? getComputedStyle(el).objectFit : 'fill';
    if (!fit || fit === 'fill') { el.style.width = '100%'; el.style.height = 'auto'; }
    else { w.style.height = Math.round(r.height) + 'px'; w.style.width = Math.round(r.width) + 'px'; }
    return w;
  }

  function contentRect(el, wrap) {
    const wr = wrap.getBoundingClientRect(), er = el.getBoundingClientRect();
    let x = er.left - wr.left, y = er.top - wr.top, w = er.width, h = er.height;
    let nw = 0, nh = 0, fit = 'fill', pos = [0.5, 0.5];
    const tag = el.tagName.toUpperCase();
    if (tag === 'IMG') { nw = el.naturalWidth; nh = el.naturalHeight; }
    else if (tag === 'VIDEO') { nw = el.videoWidth; nh = el.videoHeight; }
    else if (tag === 'SVG') {
      const vb = (el.getAttribute('viewBox') || '').trim().split(/[\s,]+/).map(Number);
      if (vb.length === 4 && vb[2] > 0 && vb[3] > 0) { nw = vb[2]; nh = vb[3]; }
      const par = (el.getAttribute('preserveAspectRatio') || 'xMidYMid meet').trim().split(/\s+/);
      if (par[0] === 'none') fit = 'fill';
      else {
        fit = par[1] === 'slice' ? 'cover' : 'contain';
        pos = [/xMin/.test(par[0]) ? 0 : /xMax/.test(par[0]) ? 1 : 0.5, /YMin/.test(par[0]) ? 0 : /YMax/.test(par[0]) ? 1 : 0.5];
      }
    }
    if (tag === 'IMG' || tag === 'VIDEO') {
      const cs = getComputedStyle(el);
      fit = cs.objectFit || 'fill';
      pos = cs.objectPosition.split(' ').map((v, i) => v.endsWith('%') ? parseFloat(v) / 100 : (v === 'left' || v === 'top' ? 0 : v === 'right' || v === 'bottom' ? 1 : 0.5));
      if (pos.length < 2) pos[1] = 0.5;
    }
    // border/padding of the element box are not part of the content box
    const cs2 = getComputedStyle(el);
    if (tag !== 'SVG') {
      const bl = parseFloat(cs2.borderLeftWidth) + parseFloat(cs2.paddingLeft), bt = parseFloat(cs2.borderTopWidth) + parseFloat(cs2.paddingTop);
      const br = parseFloat(cs2.borderRightWidth) + parseFloat(cs2.paddingRight), bb = parseFloat(cs2.borderBottomWidth) + parseFloat(cs2.paddingBottom);
      x += bl; y += bt; w -= bl + br; h -= bt + bb;
    }
    if (!nw || !nh || fit === 'fill') return { x, y, w, h };
    let s;
    if (fit === 'contain') s = Math.min(w / nw, h / nh);
    else if (fit === 'cover') s = Math.max(w / nw, h / nh);
    else if (fit === 'scale-down') s = Math.min(1, Math.min(w / nw, h / nh));
    else if (fit === 'none') s = 1;
    else return { x, y, w, h };
    const cw = nw * s, ch = nh * s;
    return { x: x + (w - cw) * pos[0], y: y + (h - ch) * pos[1], w: cw, h: ch };
  }

  function layoutFigure(a) {
    const box = a.box_el, wrap = a.wrap, el = a.media;
    if (!box || !wrap || !el) return;
    let c;
    if (wrap.classList.contains('ga-figwrap-self')) {
      const wr = wrap.getBoundingClientRect(); c = { x: 0, y: 0, w: wr.width, h: wr.height };
    } else c = contentRect(el, wrap);
    const [x, y, w, h] = (a.box && a.box.length === 4) ? a.box : [0, 0, 1, 1];
    box.style.left = (c.x + x * c.w) + 'px'; box.style.top = (c.y + y * c.h) + 'px';
    box.style.width = (w * c.w) + 'px'; box.style.height = (h * c.h) + 'px';
  }

  function anchorFigure(a, MEDIA) {
    let el = a.figure ? document.querySelector('[data-wa-id="' + a.figure + '"]') : null;   // stable id written by fetch (browser or static)
    if (!el) {
      const tail = (a.fig_src || '').slice(-40);
      el = tail ? MEDIA.find(e => ((e.currentSrc || e.src || '').slice(-40)) === tail) : null;
    }
    if (!el && a.fig_index != null) el = MEDIA[a.fig_index];
    if (!el) return false;
    const wrap = wrapFigure(el);
    const box = document.createElement('div');
    box.className = 'ga-ui ga-box'; box.dataset.key = a.key; box.style.setProperty('--c', tcolor(a));
    if (!(a.box && a.box.length === 4)) box.classList.add('ga-whole');
    box.title = (TYPES[a.type] || TYPES.NOTE).label + ': ' + a.note;
    if (a.frame) box.dataset.frame = a.frame;
    const b = document.createElement('span');
    b.className = 'ga-badge'; b.dataset.key = a.key; b.style.setProperty('--c', tcolor(a));
    box.appendChild(b);
    wrap.appendChild(box);
    a.el = wrap; a.box_el = box; a.badge = b; a.kindEl = 'figure'; a.wrap = wrap; a.media = el;
    layoutFigure(a);
    if (el.tagName === 'IMG' && !el.complete) el.addEventListener('load', () => layoutFigure(a));
    return true;
  }

  function thumb(a) {
    if (!a.frame_img) return null;
    const w = document.createElement('div');
    w.style.cssText = 'position:relative;display:inline-block;max-width:100%;line-height:0;margin:6px 0;border:1px solid #8884';
    const im = document.createElement('img');
    im.src = a.frame_img; im.style.cssText = 'display:block;max-width:100%;width:340px';
    w.append(im);
    if (a.box) {
      const b = document.createElement('div');
      b.style.cssText = 'position:absolute;box-sizing:border-box;border:2px solid ' + tcolor(a) + ';background:' + tcolor(a) + '22;' +
        'left:' + a.box[0] * 100 + '%;top:' + a.box[1] * 100 + '%;width:' + a.box[2] * 100 + '%;height:' + a.box[3] * 100 + '%';
      w.append(b);
    }
    const c = document.createElement('div');
    c.style.cssText = 'font-size:11px;line-height:1.3;opacity:.75;margin-top:3px';
    c.textContent = 'Figure ' + a.figure.replace(/^f/, '') + ', frame ' + a.frame + (a.fig_frames ? '/' + a.fig_frames : '') + (a.frame_t != null ? ' (t\u2248' + a.frame_t + 's)' : '');
    const o = document.createElement('div'); o.append(w, c);
    return o;
  }

  window.__WA_START__ = function () {
    if (window.__WA_BUILT__) return window.__WA_STATUS__;
    window.__WA_BUILT__ = true;
    const WA = window.__WA__ || { notes: [] };
    const A = WA.notes;
    const ROOT = C.pickRoot();
    const MEDIA = C.mediaList(ROOT);

    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    A.forEach(a => { if (a.figure) anchorFigure(a, MEDIA); else anchorText(a, ROOT); });
    const ok = A.filter(a => a.el);
    const missed = A.filter(a => !a.el);
    ok.sort((x, y) => (x.el.compareDocumentPosition(y.el) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1);
    ok.forEach((a, i) => {
      a.n = i + 1;
      const fr = a.frame ? ' \u00b7 frame ' + a.frame + (a.fig_frames ? '/' + a.fig_frames : '') : '';
      a.badge.textContent = a.kindEl === 'figure' ? '#' + a.n + ' \u00b7 ' + a.figure + fr : a.n;
    });
    const byKey = Object.fromEntries(ok.map(a => [a.key, a]));

    const launch = document.createElement('button');
    launch.id = 'ga-launch'; launch.className = 'ga-ui';
    launch.textContent = '\u270E Notes (' + ok.length + ')';
    const drawer = document.createElement('div');
    drawer.id = 'ga-drawer'; drawer.className = 'ga-ui';
    const print = document.createElement('div');
    print.id = 'ga-print'; print.className = 'ga-ui';
    document.body.append(launch, drawer, print);

    // Printable notes list (shown only in print / PDF)
    const ph = document.createElement('h2'); ph.textContent = 'Reading notes \u2014 ' + (WA.title || document.title);
    print.append(ph);
    if (WA.summary) { const s = document.createElement('div'); s.textContent = WA.summary; s.style.marginBottom = '8px'; print.append(s); }
    ok.forEach(a => {
      const t = TYPES[a.type] || TYPES.NOTE;
      const d = document.createElement('div'); d.className = 'it'; d.style.setProperty('--c', t.color);
      const b = document.createElement('b');
      b.textContent = '#' + a.n + ' ' + t.label.toUpperCase() + (a.pri === 'high' ? ' \u2605' : '') + (a.figure ? ' \u00b7 Figure ' + a.figure.replace(/^f/, '') + (a.frame ? ' frame ' + a.frame : '') : '') + ': ';
      d.append(b, document.createTextNode(a.note));
      const th = thumb(a); if (th) d.append(th);
      print.append(d);
    });

    const hiddenTypes = new Set(store.get('ga-hidden', []));
    let allHidden = store.get('ga-allhidden', false);
    function applyVis() {
      ok.forEach(a => {
        const off = allHidden || hiddenTypes.has(a.type);
        (a.marks || [a.box_el]).forEach(x => x.classList.toggle('ga-off', off));
        a.badge.classList.toggle('ga-off', off && a.kindEl === 'text');
      });
      drawer.querySelectorAll('.ga-chip').forEach(c => c.classList.toggle('on', !hiddenTypes.has(c.dataset.type)));
    }
    function card(a) {
      const t = TYPES[a.type] || TYPES.NOTE;
      const d = document.createElement('div');
      d.className = 'ga-card'; d.dataset.key = a.key; d.style.setProperty('--c', t.color);
      const hd = document.createElement('div'); hd.className = 'hd';
      hd.textContent = '#' + a.n + '  ' + t.label.toUpperCase() + (a.pri === 'high' ? '  \u2605' : '') +
        (a.figure ? '  \u00b7  Figure ' + a.figure.replace(/^f/, '') + (a.frame ? ', frame ' + a.frame : '') : '');
      const body = document.createElement('div'); body.textContent = a.note;
      d.append(hd, body);
      const th = thumb(a); if (th) d.append(th);
      const ls = (a.links || []).filter(k => byKey[k]);
      if (ls.length) {
        const lk = document.createElement('div'); lk.className = 'lk'; lk.append('Related: ');
        ls.forEach(k => {
          const l = document.createElement('a'); l.textContent = '#' + byKey[k].n;
          l.addEventListener('click', e => { e.stopPropagation(); toggle(true); jump(byKey[k]); });
          lk.append(l);
        });
        d.append(lk);
      }
      d.addEventListener('click', () => jump(a));
      return d;
    }
    function render() {
      drawer.textContent = '';
      const h = document.createElement('h3'); h.textContent = 'Reading notes';
      const sub = document.createElement('div'); sub.style.opacity = '.7';
      sub.textContent = 'Click a highlight, box or card. These are reader annotations, not the authors\u2019.';
      const row = document.createElement('div'); row.className = 'ga-row';
      const tog = document.createElement('button'); tog.className = 'ga-btn';
      tog.textContent = allHidden ? 'Show highlights' : 'Hide highlights';
      tog.onclick = () => { allHidden = !allHidden; store.set('ga-allhidden', allHidden); tog.textContent = allHidden ? 'Show highlights' : 'Hide highlights'; applyVis(); };
      const close = document.createElement('button'); close.className = 'ga-btn'; close.textContent = 'Close';
      close.onclick = () => toggle(false);
      row.append(tog, close);
      const chips = document.createElement('div'); chips.className = 'ga-row';
      Object.keys(TYPES).forEach(k => {
        const count = ok.filter(a => a.type === k).length;
        if (!count) return;
        const c = document.createElement('button');
        c.className = 'ga-chip'; c.dataset.type = k; c.style.setProperty('--c', TYPES[k].color);
        c.textContent = TYPES[k].label + ' ' + count;
        c.onclick = () => { hiddenTypes.has(k) ? hiddenTypes.delete(k) : hiddenTypes.add(k); store.set('ga-hidden', [...hiddenTypes]); applyVis(); };
        chips.append(c);
      });
      drawer.append(h, sub);
      if (WA.summary) { const s = document.createElement('div'); s.className = 'ga-sum'; s.textContent = WA.summary; drawer.append(s); }
      drawer.append(row, chips);
      const high = ok.filter(a => a.pri === 'high');
      if (high.length) { const h4 = document.createElement('h4'); h4.textContent = '\u2605 Needs attention first'; drawer.append(h4); high.forEach(a => drawer.append(card(a))); }
      const h4b = document.createElement('h4'); h4b.textContent = 'All notes in reading order';
      drawer.append(h4b); ok.forEach(a => drawer.append(card(a)));
      if (missed.length) {
        const m = document.createElement('div'); m.style.cssText = 'margin-top:14px;opacity:.6;font-size:11px';
        m.textContent = 'Could not anchor on this page version: ' + missed.map(a => a.key).join(', ');
        drawer.append(m);
      }
      applyVis();
    }
    function toggle(open) {
      const o = open === undefined ? !drawer.classList.contains('open') : open;
      drawer.classList.toggle('open', o);
      document.body.classList.toggle('ga-shift', o);
      store.set('ga-open', o);
    }
    function select(key) {
      drawer.querySelectorAll('.ga-card.sel').forEach(c => c.classList.remove('sel'));
      const cs = drawer.querySelectorAll('.ga-card[data-key="' + key + '"]');
      cs.forEach(x => x.classList.add('sel'));
      if (cs.length) cs[cs.length - 1].scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
    function jump(a) {
      a.el.scrollIntoView({ block: 'center', behavior: 'smooth' });
      a.el.classList.add('ga-flash'); a.el.style.setProperty('--c', tcolor(a));
      setTimeout(() => a.el.classList.remove('ga-flash'), 1400);
      select(a.key);
    }
    document.addEventListener('click', e => {
      const t = e.target.closest && e.target.closest('.ga-mark, .ga-badge, .ga-box');
      if (!t) return;
      e.preventDefault(); toggle(true); select(t.dataset.key);
    }, true);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') toggle(false); });
    launch.onclick = () => toggle();

    const relayout = () => ok.forEach(a => { if (a.kindEl === 'figure') layoutFigure(a); });
    window.addEventListener('resize', relayout);
    window.addEventListener('load', relayout);
    if (window.ResizeObserver) { const ro = new ResizeObserver(relayout); ok.forEach(a => { if (a.media) ro.observe(a.media); }); }
    render();
    if (store.get('ga-open', false)) toggle(true);
    window.__WA_STATUS__ = { anchored: ok.length, total: A.length, missed: missed.map(a => a.key) };
    return window.__WA_STATUS__;
  };
})();
