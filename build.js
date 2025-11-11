// build.js — automatic converter + root merge (final)
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
  return fs
    .readdirSync(articlesDir)
    .filter((f) => f.endsWith(".md"))
    .map((f) => path.join(articlesDir, f));
}

// Normalize dashes for safe URLs
function safeSlug(title, filename) {
  let base = title && title.length ? title : path.basename(filename, ".md");
  base = base.replace(/[—–−]/g, "-"); // normalize dash variants
  base = base.replace(/-+/g, "-"); // collapse repeats
  return slugify(base, { lower: true, strict: true });
}

// Wrap each article into HTML
function wrapHtml(title, contentHtml, meta = {}) {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>${title}</title>
  <link rel="stylesheet" href="/assets/style.css"/>
</head>
<body>
  <header>
    <nav>
      <a href="/">Home</a> | 
      <a href="/articles.html">Articles</a> | 
      <a href="/about.html">About</a>
    </nav>
  </header>
  <main class="article-content">
    <article>
      <h1>${title}</h1>
      ${meta.date ? `<p class="meta">Published: ${meta.date}</p>` : ""}
      ${contentHtml}
    </article>
  </main>
  <footer>
    <p>&copy; ${new Date().getFullYear()} Seechur Agro Pvt. Ltd.</p>
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
    const html = md.render(parsed.content);
    const title = parsed.data.title || path.basename(filePath, ".md");
    const slug = safeSlug(parsed.data.title, path.basename(filePath));
    const date = parsed.data.date || new Date().toISOString();
    const url = `/articles/${slug}.html`;

    // Write the HTML file
    const outPath = path.join(articlesDir, `${slug}.html`);
    const wrapped = wrapHtml(title, html, { date });
    fs.writeFileSync(outPath, wrapped, "utf8");

    summary.push({
      id: slug,
      title,
      date,
      category: parsed.data.category || "",
      image: parsed.data.image || "",
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
      fs.writeFileSync(
        path.join(articlesDir, "articles.orig.json"),
        JSON.stringify(rootData, null, 2),
        "utf8"
      );
      console.log("💾 Backed up existing root articles.json");
    } catch (err) {
      console.warn("⚠️ Could not parse existing root articles.json, skipping merge");
    }
  }

  // merge and remove duplicates by url
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
