// build.js — safe converter + root merge (final)
const fs = require("fs");
const path = require("path");
const matter = require("gray-matter");
const MarkdownIt = require("markdown-it");
const slugify = require("slugify");

const md = new MarkdownIt({ html: true, linkify: true, typographer: true });
const articlesDir = path.join(__dirname, "articles");
const rootJson = path.join(__dirname, "articles.json");
const articleJson = path.join(articlesDir, "articles.json");

function readMdFiles() {
  if (!fs.existsSync(articlesDir)) return [];
  return fs
    .readdirSync(articlesDir)
    .filter((f) => f.endsWith(".md"))
    .map((f) => path.join(articlesDir, f));
}

// Normalize dashes for safe URLs
function safeSlug(title, filename) {
  let base = title && title.length ? String(title) : path.basename(filename, ".md");
  base = base.replace(/[—–−]/g, "-"); // normalize dash variants
  base = base.replace(/[^A-Za-z0-9\- ]+/g, ""); // remove odd chars
  base = base.replace(/\s+/g, "-"); // spaces -> dash
  base = base.replace(/-+/g, "-"); // collapse repeats
  return slugify(base, { lower: true, strict: true });
}

// Wrap each article into HTML and include the site navbar loader so styles/nav are consistent
function wrapHtml(title, contentHtml, meta = {}) {
  // we intentionally use root-based paths (/assets/) so pages render correctly
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>${title}</title>
  <meta name="description" content="${(meta.excerpt||"").replace(/"/g, '&quot;')}" />
  <link rel="stylesheet" href="/assets/style.css"/>
</head>
<body>
  <!-- Shared navbar include -->
  <div id="navbar-placeholder"></div>
  <script>
  (function loadNavbar(){
    fetch('/navbar.html',{cache:'no-cache'}).then(r=>r.text()).then(html=>{
      const host=document.getElementById('navbar-placeholder'); host.innerHTML=html;
      host.querySelectorAll('script').forEach(s=>{
        const n=document.createElement('script');
        if(s.src){ n.src=s.src; } else { n.textContent=s.textContent; }
        document.body.appendChild(n);
      });
      // highlight Articles
      document.querySelectorAll('.menu a').forEach(a=>{
        const href=(a.getAttribute('href')||'').toLowerCase();
        if(href.endsWith('articles.html')) a.classList.add('active');
      });
    }).catch(()=>{ /* silent fallback */ });
  })();
  </script>

  <main class="container article-wrap">
    <article class="article-card">
      <header class="article-header">
        <h1>${title}</h1>
        ${meta.date ? `<div class="meta">Published: ${new Date(meta.date).toLocaleString()}</div>` : ""}
      </header>

      <section class="article-body">
        ${contentHtml}
      </section>

      <footer class="article-footer">
        <p>© ${new Date().getFullYear()} Seechur Agro Pvt. Ltd.</p>
      </footer>
    </article>
  </main>
</body>
</html>`;
}

function buildArticles() {
  const mdFiles = readMdFiles();
  const summary = [];

  mdFiles.forEach((filePath) => {
    const raw = fs.readFileSync(filePath, "utf8");
    const parsed = matter(raw);
    // render markdown -> HTML
    const html = md.render(parsed.content || "");
    const title = parsed.data.title || path.basename(filePath, ".md");
    const slug = safeSlug(parsed.data.title || title, path.basename(filePath));
    const date = parsed.data.date || new Date().toISOString();
    const url = `/articles/${slug}.html`;

    // Ensure articles directory exists
    if (!fs.existsSync(articlesDir)) fs.mkdirSync(articlesDir, { recursive: true });

    // Write the HTML file
    const outPath = path.join(articlesDir, `${slug}.html`);
    const wrapped = wrapHtml(title, html, { date, excerpt: parsed.data.excerpt || "" });
    fs.writeFileSync(outPath, wrapped, "utf8");

    // Summary object (match shape used by articles.html)
    summary.push({
      id: slug,
      title,
      date,
      category: parsed.data.category || "",
      image: parsed.data.image ? (parsed.data.image.startsWith("/") ? parsed.data.image : `/${parsed.data.image}`) : "",
      url,
      excerpt: parsed.data.excerpt || parsed.data.subtitle || "",
      author: parsed.data.author || { name: "Seechur Agro — Editorial Team" }
    });

    console.log(`✅ Converted ${path.basename(filePath)} → ${slug}.html`);
  });

  // sort by date desc
  summary.sort((a, b) => new Date(b.date) - new Date(a.date));

  // write /articles/articles.json
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
      console.warn("⚠️ Could not parse existing root articles.json, skipping merge");
    }
  }

  // merge and de-dup by url
  const combined = [...newArticles, ...rootData].filter(
    (a, i, arr) => arr.findIndex((b) => b.url === a.url) === i
  );
  combined.sort((a, b) => new Date(b.date) - new Date(a.date));

  fs.writeFileSync(rootJson, JSON.stringify(combined, null, 2), "utf8");
  console.log(`✅ Updated root articles.json (${combined.length} total items)`);
}

// MAIN
function main() {
  console.log("🚀 Starting article build process...");
  const newArticles = buildArticles();
  mergeRootJson(newArticles);
  console.log("🎉 Build complete.");
}

main();
