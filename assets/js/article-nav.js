// assets/js/article-nav.js
(function(){
  // safe guard
  if (window.__SEECHUR_ART_NAV__) return;
  window.__SEECHUR_ART_NAV__ = true;

  const jsonUrl = '/articles.json?ver=1';

  function safeText(t){ return typeof t==='string' ? t : ''; }

  fetch(jsonUrl, {cache:'no-cache'}).then(r => {
    if(!r.ok) throw new Error('no articles.json');
    return r.json();
  }).then(list => {
    if(!Array.isArray(list) || list.length === 0) return;

    // sort newest-first (ISO-like strings)
    list.sort((a,b) => String(b.date).localeCompare(String(a.date)));

    // current file name (e.g. lakadong-...html)
    const currentFile = (location.pathname.split('/').pop() || '').toLowerCase();

    // find index by url filename or id
    let idx = list.findIndex(item => {
      if(!item || !item.url) return false;
      const u = (item.url.split('/').pop() || '').toLowerCase();
      if(u === currentFile) return true;
      // fallback – match slug/id
      return (item.id && (item.id.toLowerCase() === currentFile.replace('.html','')));
    });
    if(idx === -1){
      // not found -> try by matching title slug fragment
      idx = list.findIndex(item => safeText(item.url).toLowerCase().includes(currentFile.replace('.html','')));
    }
    if(idx === -1) idx = 0;

    const prevIdx = (idx - 1 + list.length) % list.length;
    const nextIdx = (idx + 1) % list.length;
    const prev = list[prevIdx];
    const next = list[nextIdx];

    // wire elements if present (IDs: prevLink, nextLink)
    const prevEl = document.getElementById('prevLink');
    const nextEl = document.getElementById('nextLink');

    if(prevEl && prev && prev.url){
      prevEl.href = '/' + prev.url.replace(/^\//,'');
      prevEl.textContent = '← ' + safeText(prev.title || 'Previous');
      prevEl.style.display = '';
    }
    if(nextEl && next && next.url){
      nextEl.href = '/' + next.url.replace(/^\//,'');
      nextEl.textContent = (safeText(next.title) || 'Next') + ' →';
      nextEl.style.display = '';
    }

  }).catch(()=>{ /* ignore errors quietly */ });

})();

