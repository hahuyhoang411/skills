// Shared helpers: find the article root, leaf text blocks, text nodes, and meaningful media.
(function () {
  const BLOCK_SEL = 'p,li,h1,h2,h3,h4,h5,h6,blockquote,figcaption,pre,td,th,dd,dt,summary';
  const MEDIA_SEL = 'img,video,svg,canvas,iframe';
  const SKIP = 'script,style,noscript,template,.katex,math,.ga-ui,.ga-mark,.ga-box';
  const score = e => { let s = 0; e.querySelectorAll('p').forEach(p => { s += (p.textContent || '').length; }); return s; };

  function pickRoot() {
    let best = null, bs = 0;
    document.querySelectorAll('article,main,[role=main]').forEach(c => { const s = score(c); if (s > bs) { bs = s; best = c; } });
    const total = score(document.body);
    if (!(best && bs >= Math.min(500, total * 0.5))) {
      best = document.body;
      for (;;) {
        let nxt = null;
        for (const ch of best.children) { if (score(ch) >= 0.8 * total) { nxt = ch; break; } }
        if (!nxt) break;
        best = nxt;
      }
    }
    return best;
  }
  const isMedia = e => /^(IMG|VIDEO|SVG|CANVAS|IFRAME)$/i.test(e.tagName);
  const isLeaf = e => !e.querySelector(BLOCK_SEL);
  function visible(e) {
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const cs = getComputedStyle(e);
    return cs.display !== 'none' && cs.visibility !== 'hidden';
  }
  function textNodesOf(el) {
    const out = [];
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
      acceptNode(n) { const p = n.parentElement; return (!p || p.closest(SKIP)) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT; },
    });
    while (w.nextNode()) out.push(w.currentNode);
    return out;
  }
  function mediaList(root) {
    return [...root.querySelectorAll(MEDIA_SEL)].filter(e => {
      if (e.closest('.ga-ui,.ga-box,.katex,nav,footer,button')) return false;
      if (e.parentElement && e.parentElement.closest('svg')) return false;
      // Broken images collapse to a tiny alt-text box: keep them (so they are reported as unavailable)
      // unless they are display:none or declared as tiny icons.
      if (e.tagName === 'IMG' && e.complete && !e.naturalWidth && (e.getAttribute('src') || e.currentSrc)) {
        const cs = getComputedStyle(e);
        if (cs.display === 'none' || cs.visibility === 'hidden') return false;
        const dw = parseInt(e.getAttribute('width') || '', 10), dh = parseInt(e.getAttribute('height') || '', 10);
        if ((dw && dw < 64) || (dh && dh < 64)) return false;
        return true;
      }
      const r = e.getBoundingClientRect();
      if (r.width < 64 || r.height < 64) return false;
      return visible(e);
    });
  }
  window.__WA_COMMON__ = { BLOCK_SEL, MEDIA_SEL, pickRoot, isMedia, isLeaf, visible, textNodesOf, mediaList };
})();
