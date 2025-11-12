<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Post-Harvest Processing of Lakadong Turmeric — From Rhizome to Golden Powder • Seechur Agro</title>
<meta name="description" content="A detailed look at how Lakadong turmeric undergoes careful post-harvest processing to preserve curcumin quality and aroma." />
<link rel="stylesheet" href="/assets/style.css"/>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">
</head>
<body class="article-page">

<!-- Navbar include (keeps navigation identical to index) -->
<div id="navbar-placeholder"></div>
<script>
(function loadNavbar(){
  fetch('/navbar.html',{cache:'no-cache'}).then(r=>r.text()).then(html=>{
    const host=document.getElementById('navbar-placeholder');
    host.innerHTML=html;
    // execute any scripts inside the navbar include
    host.querySelectorAll('script').forEach(s=>{
      const n=document.createElement('script');
      if(s.src){ n.src = s.src; } else { n.textContent = s.textContent; }
      document.body.appendChild(n);
    });
    // mark active link for Articles
    document.querySelectorAll('.menu a').forEach(a=>{
      const href=(a.getAttribute('href')||'').toLowerCase();
      if(href.endsWith('articles.html')) a.classList.add('active');
    });
  }).catch(()=>{/* ignore */});
})();
</script>

<main class="container">
  <header class="article-hero">
    <img src="/images/uploads/lakadong-rhizome.jpg" alt="Lakadong turmeric rhizomes">
    <div class="article-hero__meta">
      <span class="pill">Lakadong</span>
      <time datetime="2025-11-11">Nov 11, 2025</time>
    </div>
    <h1>Post-Harvest Processing of Lakadong Turmeric — From Rhizome to Golden Powder</h1>
    <p class="subtitle">Processing steps that preserve curcumin content and quality.</p>
  </header>

  <div class="meta" style="margin-top:8px">
    <span id="rt" class="badge">Reading: —</span>
    <span class="byline">By <b>Seechur Agro — Editorial Team</b></span>
  </div>

  <article class="article-card" id="article">
    <p><strong>Processing Lakadong turmeric</strong> is a blend of <strong>science and tradition</strong>, ensuring every rhizome retains its natural curcumin strength and aroma.</p>

    <h2>1. Cleaning and Sorting</h2>
    <p>Freshly harvested rhizomes are washed thoroughly to remove soil and fibrous roots. Sorting helps separate mother and finger rhizomes, which have slightly different curcumin concentrations.</p>
    <img src="/images/uploads/turmeric-cleaning.jpg" alt="Turmeric cleaning" class="article-image"/>

    <h2>2. Boiling or Curing</h2>
    <p>The cleaned rhizomes are boiled at around <strong>95°C for 45 minutes</strong> to gelatinize the starch and bring out the rich golden color. This also reduces drying time and improves grinding texture.</p>
    <img src="/images/uploads/turmeric-boiling.jpg" alt="Turmeric boiling" class="article-image"/>

    <h2>3. Drying</h2>
    <p>The boiled rhizomes are sun-dried for 10–15 days or mechanically dried at <strong>50–60°C</strong>. Proper drying is essential to maintain curcumin content and prevent mold.</p>

    <h2>4. Polishing and Grading</h2>
    <p>Once fully dry, the outer layer is lightly polished by hand or in rotating drums. The result — bright golden-yellow rhizomes with a natural sheen.</p>

    <h2>5. Grinding and Packaging</h2>
    <p>The polished turmeric is ground into fine powder under controlled temperature. The powder is then vacuum-sealed to retain aroma, color, and active compounds.</p>

    <hr/>

    <p><strong>Seechur Agro Pvt. Ltd.</strong> ensures every step — from cultivation to packaging — aligns with our traceability and purity standards, making <strong>Lakadong turmeric</strong> a globally trusted ingredient.</p>
  </article>

  <div class="meta" style="margin-top:12px">
    <a class="btn" href="/articles.html">← All articles</a>
    <a class="btn" href="/articles/water-use-efficiency.html">Next → Water Use Efficiency</a>
  </div>
</main>

<footer>© <span id="year"></span> Seechur Agro Private Limited • Human by Chance, Farmer by Choice</footer>

<script>
(function(){
  // footer year
  const y=document.getElementById('year'); if(y) y.textContent=new Date().getFullYear();

  // Reading time calculation
  const el=document.getElementById('article'); if(!el) return;
  const words=(el.innerText||'').trim().split(/\s+/).length;
  const mins=Math.max(1, Math.round(words/220));
  const rt=document.getElementById('rt'); if(rt) rt.textContent=`Reading: ~${mins} min`;
})();
</script>
</body>
</html>
