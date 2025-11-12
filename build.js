// build.js — automatic converter + root merge (patched for site wrapper + image path fixes)
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

// Helpers
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
  base = base.replace(/-+/g, "-"); // collapse repeats
  return slugify(base, { lower: true, strict: true });
}

// Ensure image paths are absolute to site root (/images/ or /assets/)
function normalizeImagePaths(html) {
  if (!html) return html;
  // If images use relative path like images/ or ./images/ or ../images/ -> rewrite to /images/...
  html = html.replace(/src=["']\.\.\/images\//g, 'src="/images/');
  html = html.replace(/src=["']\.\//g, 'src="/');
  html = html.replace(/src=["']images\//g, 'src="/images/');
  // If some images wrote /assets/ already keep as is, but ensure leading slash
  html = html.replace(/src=["']assets\//g, 'src="/assets/');
  return html;
}

// Escape small bits used in title/meta
function escapeHtml(s = "") {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Wrap each article into a full page that matches main site layout
function wrapHtml(title, contentHtml, meta = {}) {
  const siteTitle = "Seechur Agro";
  const description = meta.excerpt || `${siteTitle} — Articles & Insights`;
  // Use site asset paths (assets folder). When your site is live, /assets/style.css will be served.
  const cssPath = "/assets/style.css";
  const logoPath = "/assets/logo.png";

  // include the same navbar placeholder approach as article listing for consistency
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>${escapeHtml(title)} — ${escapeHtml(siteTitle)}</title>
  <meta name="description" content="${escapeHtml(description)}"/>
  <link rel="stylesheet" href="${cssPath}"/>
  <style>
    /* article-specific overrides so content looks like the rest of the site */
    .site-header{ background: #0f2219; padding:16px 0; }
    .wrap{ max-width:1100px; margin:0 auto; padding:22px; }
    .breadcrumb{ color: #9fcfb0; margin-bottom:10px; font-size:0.95rem; }
    .article-hero h1{ font-size:2.4rem; margin:6px 0 10px; color: #e9fff2; }
    .meta-line{ color:#a9cdb6; margin-bottom:18px; }
    .article-body{ background: transparent; color: inherit; line-height:1.75; font-size:1.02rem; }
    .article-body img{ max-width:100%; height:auto; display:block; margin:18px 0; border-radius:8px; }
    footer.site-footer{ padding:28px 0; color:#d9ffe6; text-align:center; }
    /* small screens */
    @media (max-width:600px){ .article-hero h1{ font-size:1.6rem } .wrap{ padding:14px } }
  </style>
</head>
<body>
  <!-- Nav placeholder (reuses your navbar.html client-side include) -->
  <div id="navbar-placeholder"></div>
  <script>
    (function loadNavbar(){
      if(!document.getElementById('navbar-placeholder')) return;
      fetch('/admin/navbar.html', {cache:'no-cache'}).then(r=>r.text()).then(html=>{
        // If you don't have /admin/navbar.html, try root /navbar.html fallback
        if(!html || html.length < 10){
          return fetch('/navbar.html', {cache:'no-cache'}).then(r=>r.text()).then(h=>{ document.getElementById('navbar-placeholder').innerHTML = h; });
        }
        document.getElementById('navbar-placeholder').innerHTML = html;
        // relocate any scripts inside
        document.getElementById('navbar-placeholder').querySelectorAll('script').forEach(s=>{
          const n=document.createElement('script');
          if(s.src){ n.src=s.src; } else { n.textContent = s.textContent; }
          document.body.appendChild(n);
        });
      }).catch(()=>{ /* ignore if missing */ });
    })();
  </script>

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

// Build article pages and index JSON
function buildArticles() {
  const mdFiles = readMdFiles();
  const summary = [];

  mdFiles.forEach((filePath) => {
    const raw = fs.readFileSync(filePath, "utf8");
    const parsed = matter(raw);
    // Render markdown -> HTML
    const rendered = md.render(parsed.content || "");
    const contentHtml = normalizeImagePaths(rendered);

    const title = parsed.data.title || path.basename(filePath, ".md");
    const slug = safeSlug(parsed.data.title || title, path.basename(filePath));
    // Prefer frontmatter date; otherwise use file mtime as fallback
    const date = parsed.data.date || new Date(fs.statSync(filePath).mtime).toISOString();
    const url = `/articles/${slug}.html`;

    // If frontmatter specified a hero image, add a top image to content (only if not already present)
    let finalHtml = contentHtml;
    if (parsed.data.image && parsed.data.image.length) {
      const imgPath = String(parsed.data.image).startsWith("/") ? parsed.data.image : "/" + String(parsed.data.image).replace(/^\.?\//, "");
      // only prepend hero if content doesn't already start with an <img>
      if (!/^\s*<img/i.test(finalHtml)) {
        finalHtml = `<p><img src="${imgPath}" alt="${escapeHtml(title)}" /></p>\n` + finalHtml;
      }
    }

    // Wrap page
    const outHtml = wrapHtml(title, finalHtml, { date, excerpt: parsed.data.excerpt || "" });

    // Write HTML file to articles/<slug>.html
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
      // backup previous root JSON
      fs.writeFileSync(path.join(articlesDir, "articles.orig.json"), JSON.stringify(rootData, null, 2), "utf8");
      console.log("💾 Backed up existing root articles.json");
    } catch (err) {
      console.warn("⚠️ Could not parse existing root articles.json, skipping backup/merge of malformed file");
    }
  }

  // merge and remove duplicates by url
  const combinedMap = new Map();
  // prefer newArticles first (so newest edits take precedence)
  newArticles.concat(rootData || []).forEach((item) => {
    combinedMap.set(item.url, item);
  });
  const combined = Array.from(combinedMap.values());
  combined.sort((a, b) => new Date(b.date) - new Date(a.date));

  fs.writeFileSync(rootJson, JSON.stringify(combined, null, 2), "utf8");
  console.log(`✅ Updated root articles.json (${combined.length} total items)`);
}

// MAIN
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
