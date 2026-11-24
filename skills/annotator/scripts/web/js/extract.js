// Runs in the page: returns paragraphs + figures in reading order and tags media with data-wa-id.
window.__WA_EXTRACT__ = function () {
  const C = window.__WA_COMMON__;
  const root = C.pickRoot();
  const media = C.mediaList(root);
  const mset = new Set(media);
  const out = { title: document.title, url: location.href, paragraphs: [], figures: [], order: [] };
  let pi = 0, fi = 0;
  root.querySelectorAll(C.BLOCK_SEL + ',' + C.MEDIA_SEL).forEach(el => {
    if (C.isMedia(el)) {
      if (!mset.has(el)) return;
      const tag = el.tagName.toLowerCase();
      const id = 'f' + (++fi);
      el.setAttribute('data-wa-id', id);
      const r = el.getBoundingClientRect();
      const fig = el.closest('figure');
      const cap = fig && fig.querySelector('figcaption');
      out.figures.push({
        id, index: media.indexOf(el),
        kind: tag === 'img' ? 'img' : tag === 'iframe' ? 'embed' : /^(video|svg|canvas)$/.test(tag) ? tag : 'background',
        src: el.currentSrc || el.src || el.getAttribute('data-src') || ((/url\((['"]?)(.*?)\1\)/.exec(el.getAttribute('style') || '') || [])[2]) || '',
        alt: (el.getAttribute('alt') || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim(),
        caption: cap ? cap.textContent.replace(/\s+/g, ' ').trim() : '',
        w: Math.round(r.width), h: Math.round(r.height),
        natural_w: el.naturalWidth || el.videoWidth || 0, natural_h: el.naturalHeight || el.videoHeight || 0,
        duration: (tag === 'video' && isFinite(el.duration)) ? el.duration : null,
      });
      out.order.push(id);
      return;
    }
    if (!el.matches(C.BLOCK_SEL) || !C.isLeaf(el) || !C.visible(el)) return;
    const t = C.textNodesOf(el).map(n => n.nodeValue).join('').replace(/\s+/g, ' ').trim();
    if (!t) return;
    const id = 'p' + (++pi);
    out.paragraphs.push({ id, tag: el.tagName.toLowerCase(), text: t });
    out.order.push(id);
  });
  return out;
};
