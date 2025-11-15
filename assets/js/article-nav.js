<script>
/* Article Prev/Next rotation using /articles.json (circular by date) 
   Put this either (A) at the end of each article HTML before </body>
   or (B) save as /assets/js/article-nav.js and include <script src="/assets/js/article-nav.js" defer></script>
*/
(function(){
  const url = '/articles.json?ver=1';
  fetch(url, {cache:'no-cache'}).then(r => r.ok ? r.json() : Promise.reject(r)).then(list => {
    if(!Array.isArray(list) || !list.length) return;
    // newest first
    list.sort((a,b) => String(b.date).localeCompare(String(a.date)));
    // current filename
    const currentFile = (location.pathname.split('/').pop() || '').toLowerCase();
    // try to find using url or id fallback
    let idx = list.findIndex(item => {
      if(!item.url) return false;
      const u = item.url.split('/').pop().toLowerCase();
      if(u === currentFile) return true;
      if(item.id && (item.id.toLowerCase() === currentFile.replace('.html',''))) return true;
      return false;
    });
    if(idx === -1) {
      // try matching slug-like names from file (strip extension)
      const base = currentFile.replace('.html','');
      idx = list.findIndex(it => (it.slug && it.slug.toLowerCase() === base) || (it.id && it.id.toLowerCase() === base));
    }
    if(idx === -1) idx = 0; // fallback to first

    const prevIdx = (idx - 1 + list.length) % list.length;
    const nextIdx = (idx + 1) % list.length;
    const prev = list[prevIdx], next = list[nextIdx];

    // elements expected in article footer
    const prevEl = document.getElementById('prevLink');
    const nextEl = document.getElementById('nextLink');
    const allEl = document.getElementById('allArticles');

    if(prevEl && prev && prev.url) {
      prevEl.href = ('/' + prev.url).replace(/\/+/g,'/');
      prevEl.textContent = '← ' + (prev.title || 'Previous');
    }
    if(nextEl && next && next.url) {
      nextEl.href = ('/' + next.url).replace(/\/+/g,'/');
      nextEl.textContent = (next.title || 'Next') + ' →';
    }
    if(allEl && !allEl.getAttribute('href')) {
      allEl.href = '/articles.html';
    }
  }).catch(()=>{/*silently ignore*/});
})();
</script>
