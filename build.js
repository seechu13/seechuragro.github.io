// build.js
const fs = require('fs');
const path = require('path');
const matter = require('gray-matter');
const MarkdownIt = require('markdown-it');
const slugify = require('slugify');

const md = new MarkdownIt({ html: true, linkify: true, typographer: true });
const articlesDir = path.join(__dirname, 'articles');

function readMdFiles() {
  return fs.readdirSync(articlesDir)
    .filter(f => f.endsWith('.md'))
    .map(f => path.join(articlesDir, f));
}

function safeSlug(title, filename) {
  // normalize fancy dashes and spaces before slugifying
  let base = title && title.length ? title : path.basename(filename, '.md');
  base = base.replace(/[—–−]/g, '-'); // convert all dash variants to a simple "-"
  base = base.replace(/-+/g, '-');    // collapse multiple consecutive dashes
  return slugify(base, { lower: true, strict: true });
}


function wrapHtml(title, contentHtml, meta = {}) {
  // Basic wrapper — tweak to match your site's look (links to /assets/style.css)
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
      <a href="/">Home</a> | <a href="/articles.html">Articles</a> | <a href="/about.html">About</a>
    </nav>
  </header>
  <main class="article-content">
    <article>
      <h1>${title}</h1>
      ${meta.date ? `<p class="meta">Published: ${meta.date}</p>` : ''}
      ${contentHtml}
    </article>
  </main>
  <footer>
    <p>&copy; ${new Date().getFullYear()} Seechur Agro Pvt. Ltd.</p>
  </footer>
</body>
</html>`;
}

function main() {
  const mdFiles = readMdFiles();
  const summary = [];

  mdFiles.forEach(filePath => {
    const raw = fs.readFileSync(filePath, 'utf8');
    const parsed = matter(raw);
    const html = md.render(parsed.content);
    const title = parsed.data.title || path.basename(filePath, '.md');
    const slug = safeSlug(parsed.data.title, path.basename(filePath));
    const date = parsed.data.date || new Date().toISOString();
    const url = `/articles/${slug}.html`;

    // Write the HTML file
    const outPath = path.join(articlesDir, `${slug}.html`);
    const wrapped = wrapHtml(title, html, { date });
    fs.writeFileSync(outPath, wrapped, 'utf8');

    // Save metadata for JSON index
    summary.push({
      title,
      date,
      url,
      excerpt: parsed.data.excerpt || '',
      image: parsed.data.image || ''
    });
    console.log('Converted', filePath, '→', outPath);
  });

  // sort by date desc
  summary.sort((a, b) => new Date(b.date) - new Date(a.date));

  // write JSON index
  fs.writeFileSync(path.join(articlesDir, 'articles.json'), JSON.stringify(summary, null, 2), 'utf8');
  console.log('Wrote articles/articles.json with', summary.length, 'items');
}

main();

