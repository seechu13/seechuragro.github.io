// build.js — converter with inlined navbar (final)
const fs = require("fs");
const path = require("path");
const matter = require("gray-matter");
const MarkdownIt = require("markdown-it");
const slugify = require("slugify");

const md = new MarkdownIt({ html: true, linkify: true, typographer: true });
const root = __dirname;
const articlesDir = path.join(root, "articles");
const rootJson = path.join(root, "articles.json");
const articleJson = path.join(articlesDir, "articles.json");

function readMdFiles() {
  if (!fs.existsSync(articlesDir)) return [];
  return fs
    .readdirSync(articlesDir)
    .filter((f) => f.endsWith(".md"))
    .map((f) => path.join(articlesDir, f));
}

function safeSlug(title, filename) {
  let base = title && title.length ? String(title) : path.basename(filename, ".md");
  base = base.replace(/[—–−]/g, "-").replace(/-+/g, "-");
  return slugify(base, { lower: true, strict: true });
}
function normalizeImagePaths(html) {
  if (!html) return html;
  html = html.replace(/src=["']\.\.\/images\//g, 'src="/images/');
  html = html.replace(/src=["']\.\//g, 'src="/');
  html = html.replace(/src=["']images\//g, 'src="/images/');
  html = html.replace(/src=["']assets\//g, 'src="/assets/');
  return html;
}
function escapeHtml(s = "") {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

// ---- NAVBAR HTML (inlined) ----
// We embed the exact navbar HTML you provided but normalize paths to root (/).
const NAVBAR_HTML = `
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
<div class="nav-overlay" id="navOverlay" hidden></div>

<style>
  :root{ --nav-bg:rgba(10,25,10,0.7); --nav-solid:#1b4332; }
  .site-nav{ position:sticky; top:0; z-index:1000; background:var(--nav-bg); backdrop-filter:blur(6px); border-bottom:1px solid rgba(255,255,255,.12); }
  .nav-inner{ max-width:1100px; margin:0 auto; padding:10px 18px; display:flex; align-items:center; gap:14px; }
  .brand{ display:flex; align-items:center; text-decoration:none }
  .brand img{ width:110px; height:auto; object-fit:contain; display:block; filter:drop-shadow(0 4px 12px rgba(0,0,0,.45)); }
  .menu{ margin-left:auto; display:flex; gap:16px; flex-wrap:wrap }
  .menu a{ color:#ffffff; text-decoration:none; padding:6px 10px; border-radius:999px; transition:.25s; }
  .menu a:hover,.menu a.active{ background:rgba(255,255,255,0.18); }
  .nav-toggle{ display:none; margin-left:auto; border:1px solid rgba(255,255,255,.28); background:rgba(0,0,0,.25); color:#eafff5; padding:8px 12px; border-radius:10px; cursor:pointer; }
  .nav-overlay{ display:none; }
  @media (max-width:768px){
    .brand img{width:84px;}
    .nav-toggle{display:inline-block;}
    .menu{
      position:fixed; top:0; right:-80%; width:80%; height:100vh; margin:0; display:flex; flex-direction:column; gap:8px; padding:18px; background:var(--nav-solid); border-left:1px solid rgba(255,255,255,.18); box-shadow:-10px 0 24px rgba(0,0,0,.45); transition:right .28s ease-in-out;
    }
    .menu a{padding:12px 14px; border:1px solid rgba(255,255,255,.16); background:rgba(255,255,255,.06);}
    .site-nav.open .menu{ right:0; }
    .nav-overlay{ position:fixed; inset:0; z-index:999; background:rgba(0,0,0,.55); backdrop-filter:blur(2px); }
    .site-nav.open + .nav-overlay{ display:block; }
  }
</style>

<script>
(function(){
  if (window.__SEECHUR_NAVBAR_INIT__) return;
  window.__SEECHUR_NAVBAR_INIT__ = true;
  const nav = document.getElementById('siteNav');
  const toggle = document.getElementById('navToggle');
  const overlay = document.getElementById('navOverlay');
  function openMenu(){ nav.classList.add('open'); if(toggle) toggle.setAttribute('aria-expanded','true'); if(overlay) overlay.removeAttribute('hidden'); document.body.style.overflow='hidden'; }
  function closeMenu(){ nav.classList.remove('open'); if(toggle) toggle.setAttribute('aria-expanded','false'); if(overlay) overlay.setAttribute('hidden',''); document.body.style.overflow=''; }
  if (toggle) toggle.addEventListener('click', ()=>{ nav.classList.contains('open') ? closeMenu() : openMenu(); });
  if (overlay) overlay.addEventListener('click', closeMenu);
  document.addEventListener('keydown', (e)=>{ if(e.key==='Escape') closeMenu(); });
  const current = (location.pathname.split('/').pop() || 'index.html').toLowerCase();
  document.querySelectorAll('.menu a').forEach(a=>{
    const href = (a.getAttribute('href')||'').toLowerCase();
    if (href === current || (current==='' && href==='index.html')) a.classList.add('active');
  });
})();
</script>
`;

// Wrap with site CSS and footer; NAVBAR_HTML inserted at top of body
function wrapHtml(title, contentHtml, meta = {}) {
  const cssPath = "/assets/style.css";
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>${escapeHtml(title)} — Seechur Agro</title>
  <meta name="description" content="${escapeHtml(meta.excerpt || '')}"/>
  <link rel="stylesheet" href="${cssPath}"/>
  <style>
    .wrap{ max-width:1100px; margin:0 auto; padding:22px; }
    .breadcrumb{ color: #9fcfb0; margin-bottom:10px; font-size:0.95rem; }
    .article-hero h1{ font-size:2.4rem; margin:6px 0 10px; color:#e9fff2; }
    .meta-line{ color:#a9cdb6; margin-bottom:18px; }
    .article-body{ background: transparent; color: inherit; line-height:1.75; font-size:1.02rem; }
    .article-body img{ max-width:100%; height:auto; display:block; margin:18px 0; border-radius:8px; }
    footer.site-footer{ padding:28px 0; color:#d9ffe6; text-align:center; }
    @media (max-width:600px){ .article-hero h1{ font-size:1.6rem } .wrap{ padding:14px } }
  </style>
</head>
<body>
  ${NAVBAR_HTML}
  <main class="wrap">
    <div class="breadcrumb"><a href="/" style="color:inherit;text-decoration:none">Home</a> &nbsp; / &nbsp; <a href="/articles.html" style="color:inherit;text-decoration:none">Articles</a></div>
    <section class="article-hero">
      <h1>${escapeHtml(title)}</h1>
      ${meta.date ? `<div class="meta-line">Published: ${escapeHtml(meta.date)}</div>` : ""}
    </section>
    <article class="article-body">
      ${contentHtml}
    </article>
  </main>
  <footer class="site-footer">
    <div>&copy; ${new Date().getFullYear()} Seechur Agro Private Limited • Human by Chance, Farmer by Choice</div>
  </footer>
</body>
</html>`;
}

function buildArticles() {
  const mdFiles = readMdFiles();
  const summary = [];

  mdFiles.forEach((filePath) => {
    const raw = fs.readFileSync(filePath, "utf8");
    const parsed = matter(raw);
    const rendered = md.render(parsed.content || "");
    const contentHtml = normalizeImagePaths(rendered);

    const title = parsed.data.title || path.basename(filePath, ".md");
    const slug = safeSlug(parsed.data.title || title, path.basename(filePath));
    const date = parsed.data.date || new Date(fs.statSync(filePath).mtime).toISOString();
    const url = `/articles/${slug}.html`;

    let finalHtml = contentHtml;
    if (parsed.data.image && parsed.data.image.length) {
      const imgPath = String(parsed.data.image).startsWith("/") ? parsed.data.image : "/" + String(parsed.data.image).replace(/^\.?\//, "");
      if (!/^\s*<img/i.test(finalHtml)) {
        finalHtml = `<p><img src="${imgPath}" alt="${escapeHtml(title)}" /></p>\n` + finalHtml;
      }
    }

    const outHtml = wrapHtml(title, finalHtml, { date, excerpt: parsed.data.excerpt || "" });
    const outPath = path.join(articlesDir, `${slug}.html`);
    fs.writeFileSync(outPath, outHtml, "utf8");

    summary.push({
      id: slug,
      title,
      date,
      category: parsed.data.category || "",
      image: parsed.data.image ? (String(parsed.data.image).startsWith("/") ? parsed.data.image : "/" + String(parsed.data.image).replace(/^\.?\//, "")) : "",
      url,
      excerpt: parsed.data.excerpt || "",
      author: parsed.data.author || "Seechur Agro — Editorial Team",
    });

    console.log(`✅ Converted ${path.basename(filePath)} → ${slug}.html`);
  });

  summary.sort((a, b) => new Date(b.date) - new Date(a.date));
  fs.writeFileSync(articleJson, JSON.stringify(summary, null, 2), "utf8");
  console.log(`📘 Wrote /articles/articles.json with ${summary.length} items`);
  return summary;
}

function mergeRootJson(newArticles) {
  let rootData = [];
  if (fs.existsSync(rootJson)) {
    try {
      rootData = JSON.parse(fs.readFileSync(rootJson, "utf8"));
      fs.writeFileSync(path.join(articlesDir, "articles.orig.json"), JSON.stringify(rootData, null, 2), "utf8");
      console.log("💾 Backed up existing root articles.json");
    } catch (err) {
      console.warn("⚠️ Could not parse existing root articles.json, skipping backup/merge");
    }
  }
  const combinedMap = new Map();
  newArticles.concat(rootData || []).forEach((item) => combinedMap.set(item.url, item));
  const combined = Array.from(combinedMap.values());
  combined.sort((a, b) => new Date(b.date) - new Date(a.date));
  fs.writeFileSync(rootJson, JSON.stringify(combined, null, 2), "utf8");
  console.log(`✅ Updated root articles.json (${combined.length} total items)`);
}

function main() {
  console.log("🚀 Starting article build process...");
  if (!fs.existsSync(articlesDir)) {
    console.error("❌ articles directory not found:", articlesDir);
    process.exit(1);
  }
  const newArticles = buildArticles();
  mergeRootJson(newArticles);
  console.log("🎉 Build complete.");
}

main();
