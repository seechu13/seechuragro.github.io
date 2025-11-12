// build.js — automatic converter + root merge (updated)
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

// Normalize dashes for safe URLs and generate slugs cleanly
function safeSlug(title, filename) {
  let base = title && title.length ? title : path.basename(filename, ".md");
  base = base.replace(/[—–−]/g, "-"); // normalize dash variants
  base = base.replace(/['"“”‘’]/g, ""); // remove quotes
  base = base.replace(/\s+/g, "-"); // spaces -> dash
  base = base.replace(/-+/g, "-"); // collapse repeats
  return slugify(base, { lower: true, strict: true });
}

// Wrap each article into a full HTML page that matches site layout.
// Important: it references /assets/style.css and includes navbar via fetch('/navbar.html')
// so the navbar and logo are shared with root site and work from /articles/.
function wrapHtml(title, contentHtml, meta = {}) {
  // meta.date should be an ISO date string if present
  const dateDisplay = meta.date ? `<p class="meta">Published: ${new Date(meta.date).toUTCString()}</p>` : "";
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>${escapeHtml(title)}</title>
  <meta name="description" content="${escapeHtml(meta.excerpt || '')}" />
  <link rel="stylesheet" href="/assets/style.css"/>
</head>
<body>
  <!-- shared navbar (loaded at runtime so one copy for whole site) -->
  <div id="navbar-placeholder"></div>
  <script>
  (function loadNavbar(){
    // load navbar from absolute path so works from /articles/ and root
    fetch('/navbar.html',{cache:'no-cache'}).then(r=>r.text()).then(html=>{
      const host=document.getElementById('navbar-placeholder'); host.innerHTML=html;
      // run any scripts in navbar.html safely (same approach used site-wide)
      host.querySelectorAll('script').forEach(s=>{
        const n=document.createElement('script');
        if(s.src){ n.src=s.src; } else { n.textContent=s.textContent; }
        document.body.appendChild(n);
      });
    }).catch(()=>{/* ignore if no navbar.html found */});
  })();
  </script>

  <main class="container article-page">
    <article class="article-wrap">
      <h1 class="article-title">${escapeHtml(title)}</h1>
      ${dateDisplay}
      <div class="article-body">
        ${contentHtml}
      </div>
    </article>
  </main>

  <footer class="site-footer">
    <p>© ${new Date().getFullYear()} Seechur Agro Private Limited • Human by Chance, Farmer by Choice</p>
  </footer>
</body>
</html>`;
}

// simple html escaper for title/meta strings
function escapeHtml(s){ return String(s||'').replace(/[&<>"']/g, c=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c])); }

function buildArticles() {
  const mdFiles = readMdFiles();
  const summary = [];

  mdFiles.forEach((filePath) => {
    const raw = fs.readFileSync(filePath, "utf8");
    const parsed = matter(raw);
    const html = md.render(parsed.content);

    const title = parsed.data.title || path.basename(filePath, ".md");
    const slug = safeSlug(parsed.data.title || title, path.basename(filePath));
    const date = parsed.data.date || new Date().toISOString();
    const url = `/articles/${slug}.html`;

    // Write the HTML file into /articles/
    const outPath = path.join(articlesDir, `${slug}.html`);
    const wrapped = wrapHtml(title, html, { date, excerpt: parsed.data.excerpt || '' });
    fs.writeFileSync(outPath, wrapped, "utf8");

    summary.push({
      id: slug,
      title,
      date,
      category: parsed.data.category || "",
      image: parsed.data.image || "",
      url,
      excerpt: parsed.data.excerpt || "",
      author: parsed.data.author || { name: "Seechur Agro — Editorial Team" }
    });

    console.log(`✅ Converted ${path.basename(filePath)} → ${path.relative(root, outPath)}`);
  });

  // sort by date desc
  summary.sort((a, b) => new Date(b.date) - new Date(a.date));

  // ensure articles directory exists and write /articles/articles.json
  if (!fs.existsSync(articlesDir)) fs.mkdirSync(articlesDir);
  fs.writeFileSync(articleJson, JSON.stringify(summary, null, 2), "utf8");
  console.log(`📘 Wrote ${path.relative(root, articleJson)} with ${summary.length} items`);

  return summary;
}

function mergeRootJson(newArticles) {
  let rootData = [];
  if (fs.existsSync(rootJson)) {
    try {
      rootData = JSON.parse(fs.readFileSync(rootJson, "utf8"));
      // backup existing root articles.json
      fs.writeFileSync(path.join(articlesDir, "articles.orig.json"), JSON.stringify(rootData, null, 2), "utf8");
      console.log("💾 Backed up existing root articles.json");
    } catch (err) {
      console.warn("⚠️ Could not parse existing root articles.json, skipping merge");
    }
  }

  // combine, remove duplicates by url (newArticles first -> take latest)
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
