// build.js — automatic converter + root merge (final, updated)
const fs = require("fs");
const path = require("path");
const matter = require("gray-matter");
const MarkdownIt = require("markdown-it");
const slugify = require("slugify");

const md = new MarkdownIt({ html: true, linkify: true, typographer: true });
const articlesDir = path.join(__dirname, "articles");
const rootJson = path.join(__dirname, "articles.json"); // root-level index
const articleJson = path.join(articlesDir, "articles.json"); // /articles/articles.json

function readMdFiles() {
  if (!fs.existsSync(articlesDir)) {
    console.error("articles directory not found:", articlesDir);
    process.exit(1);
  }
  return fs
    .readdirSync(articlesDir)
    .filter((f) => f.endsWith(".md"))
    .map((f) => path.join(articlesDir, f));
}

// Normalize dashes for safe URLs and slugify
function safeSlug(title, filename) {
  let base = title && title.length ? title : path.basename(filename, ".md");
  base = base.replace(/[—–−]/g, "-"); // normalize dash variants
  base = base.replace(/[^a-zA-Z0-9\- ]+/g, ""); // remove odd chars
  base = base.replace(/\s+/g, "-"); // spaces -> dash
  base = base.replace(/-+/g, "-"); // collapse repeats
  return slugify(base, { lower: true, strict: true });
}

// Ensure images referenced in frontmatter are absolute (start with '/')
function normalizeImagePath(img) {
  if (!img) return "";
  // if data URL or absolute http(s) leave unchanged
  if (/^https?:\/\//i.test(img) || /^data:/i.test(img)) return img;
  if (img.startsWith("/")) return img;
  // assume site root assets path
  return "/" + img.replace(/^\/+/, "");
}

// The site wrapper includes the same navbar markup so every article page looks uniform.
// If you later update navbar.html, also update this wrapper or use server includes.
function wrapHtml(title, contentHtml, meta = {}) {
  const dateHtml = meta.date ? `<p class="meta">Published: ${meta.date}</p>` : "";
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>${escapeHtml(title)} • Seechur Agro</title>
  <link rel="stylesheet" href="/assets/style.css"/>
</head>
<body>
  <!-- NAVBAR (inlined so generated pages are identical) -->
  <nav class="site-nav" id="siteNav">
    <div class="nav-inner">
      <a class="brand" href="/index.html" aria-label="Seechur Agro home">
        <img src="/assets/logo.png" alt="Seechur Agro logo">
      </a>
      <button class="nav-toggle" id="navToggle" aria-expanded="false" aria-controls="mobileMenu" aria-label="Open Menu">
        ☰ Menu
      </button>
      <div class="menu" id="mobileMenu">
        <a href="/index.html">Home</a>
        <a href="/about.html">About</a>
        <a href="/why-lakadong.html">Why Lakadong</a>
        <a href="/portfolio.html">Portfolio</a>
        <a href="/market.html">Market</a>
        <a href="/financials.html">Financials</a>
        <a href="/team.html">Team</a>
        <a href="/faq.html">FAQ</a>
        <a href="/advisors.html">Advisors</a>
        <a href="/articles.html">Articles</a>
        <a href="/contact.html">Contact</a>
        <a href="/investor-pack.html">Investor Pack</a>
      </div>
    </div>
  </nav>

  <main class="container article-wrap">
    <article class="article-content">
      <h1 class="article-title">${escapeHtml(title)}</h1>
      ${dateHtml}
      <section class="article-body">
        ${contentHtml}
      </section>
    </article>
  </main>

  <footer class="site-footer">
    <p>© ${new Date().getFullYear()} Seechur Agro Pvt. Ltd. • Human by Chance, Farmer by Choice</p>
  </footer>

  <script>
    // small nav script to allow mobile drawer (kept minimal)
    (function(){
      if (window.__SEECHUR_NAVBAR_INIT__) return;
      window.__SEECHUR_NAVBAR_INIT__ = true;
      const nav = document.getElementById('siteNav');
      const toggle = document.getElementById('navToggle');
      const overlay = document.getElementById('navOverlay');
      function openMenu(){ nav.classList.add('open'); if(toggle) toggle.setAttribute('aria-expanded','true'); document.body.style.overflow='hidden';}
      function closeMenu(){ nav.classList.remove('open'); if(toggle) toggle.setAttribute('aria-expanded','false'); document.body.style.overflow='';}
      if (toggle) toggle.addEventListener('click', ()=>{ nav.classList.contains('open') ? closeMenu() : openMenu(); });
      document.addEventListener('keydown', (e)=>{ if(e.key==='Escape') closeMenu(); });
      // set active link
      const current = (location.pathname.split('/').pop() || 'index.html').toLowerCase();
      document.querySelectorAll('.menu a').forEach(a=>{ const href=(a.getAttribute('href')||'').toLowerCase(); if (href===current || (current==='' && href==='index.html')) a.classList.add('active'); });
    })();
  </script>
</body>
</html>`;
}

// basic escape for title insertion
function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, function(m){ return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[m]; });
}

function buildArticles() {
  const mdFiles = readMdFiles();
  const summary = [];

  mdFiles.forEach((filePath) => {
    const raw = fs.readFileSync(filePath, "utf8");
    const parsed = matter(raw);
    const contentHtml = md.render(parsed.content || "");
    const title = parsed.data.title || path.basename(filePath, ".md");
    const slug = safeSlug(parsed.data.title || parsed.data.title === "" ? parsed.data.title : path.basename(filePath));
    const date = parsed.data.date || new Date().toISOString();
    const url = `/articles/${slug}.html`;

    // normalize image
    const image = normalizeImagePath(parsed.data.image || "");

    // produce article HTML and write to /articles/<slug>.html
    const outPath = path.join(articlesDir, `${slug}.html`);
    const wrapped = wrapHtml(title, contentHtml, { date });
    fs.writeFileSync(outPath, wrapped, "utf8");

    summary.push({
      id: slug,
      title,
      date,
      category: parsed.data.category || "",
      image,
      url,
      excerpt: parsed.data.excerpt || parsed.data.subtitle || ""
    });

    console.log("✅ Converted", path.basename(filePath), "→", path.relative(__dirname, outPath));
  });

  // sort by date desc
  summary.sort((a, b) => new Date(b.date) - new Date(a.date));

  // write /articles/articles.json
  fs.writeFileSync(articleJson, JSON.stringify(summary, null, 2), "utf8");
  console.log(`📘 Wrote ${path.relative(__dirname, articleJson)} with ${summary.length} items`);
  return summary;
}

function mergeRootJson(newArticles) {
  let rootData = [];
  if (fs.existsSync(rootJson)) {
    try {
      rootData = JSON.parse(fs.readFileSync(rootJson, "utf8"));
      fs.writeFileSync(path.join(articlesDir, "articles.orig.json"), JSON.stringify(rootData, null, 2), "utf8");
      console.log("💾 Backed up existing root articles.json -> /articles/articles.orig.json");
    } catch (err) {
      console.warn("⚠️ Could not parse existing root articles.json, skipping backup/merge");
    }
  }

  // merge unique by url (prefer newArticles order)
  const combinedMap = new Map();
  newArticles.forEach(a => combinedMap.set(a.url, a));
  (rootData || []).forEach(a => { if(!combinedMap.has(a.url)) combinedMap.set(a.url, a); });

  const combined = Array.from(combinedMap.values());
  combined.sort((a,b)=> new Date(b.date) - new Date(a.date));

  fs.writeFileSync(rootJson, JSON.stringify(combined, null, 2), "utf8");
  console.log(`✅ Updated root ${path.relative(__dirname, rootJson)} (${combined.length} total items)`);
}

function main() {
  console.log("🚀 Starting article build process...");
  const newArticles = buildArticles();
  mergeRootJson(newArticles);
  console.log("🎉 Build complete.");
}

main();
