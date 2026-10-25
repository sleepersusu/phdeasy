/* 資料：應用程式從 runs/ 讀（me.json、professors.json、各教授 data.json），比對在瀏覽器裡算；離線單檔版內嵌在 #inline-data */
let H = null;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const bi = (zh, en, tag = "span") => (zh ? `<${tag} class="t-zh">${esc(zh)}</${tag}>` : "") + (tag === "span" && zh && en ? " " : "") + (en ? `<${tag} class="t-en" lang="en">${esc(en)}</${tag}>` : "");
const body = id => $(`#${id} .body`) || document.createElement("div");  // 這一頁沒有這一區就畫到看不見的地方
const has = id => !!document.getElementById(id);
const paperLink = (p, id) => OFFLINE_HOME ? `${p.href}#paper-${id}` : `paper.html?p=${encodeURIComponent(p.slug)}&id=${encodeURIComponent(id)}`;
const STATUS = {confirmed: ["g", "本人主持"], pending: ["y", "待確認"], acknowledged: ["", "論文致謝提及"], other: ["", "合作者主持"]};

function setLang(l){
  document.body.className = "lang-" + l;
  document.querySelectorAll("[data-lang]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.lang === l)));
  try { localStorage.setItem("phdeasy:home:lang", l); } catch (e) {}
}

function renderMe(m){
  $("#name").textContent = m.name + (m.name_zh ? `（${m.name_zh}）` : "");
  $("#headline").innerHTML = bi(m.headline_zh, m.headline);
  const c = m.contact || {};
  $("#contact").innerHTML = [c.location && esc(c.location), c.email && esc(c.email), c.github && `<a href="https://${esc(c.github)}" target="_blank" rel="noopener">${esc(c.github)}</a>`].filter(Boolean).join("｜");
  body("me").innerHTML = `
    <div class="card">${bi(m.summary_zh, m.summary, "div")}<div class="src">出處：${esc(m.summary_src || "CV")}</div></div>
    <h3>研究興趣</h3><div class="chips">${(m.interests || []).map(i => `<span class="pill">${bi(i.zh, i.en)}</span>`).join("")}</div>
    <div class="grid" style="margin-top:16px">
      <div class="card"><h3 style="margin-top:0">學歷</h3><ul>${(m.education || []).map(e => `<li><strong>${esc(e.degree)}</strong>，${esc(e.school)}（${esc(e.years)}）${e.note ? `<div class="small muted">${esc(e.note)}</div>` : ""}</li>`).join("")}</ul></div>
      <div class="card"><h3 style="margin-top:0">發表</h3><ul>${(m.publications || []).map(p => `<li class="small">${esc(p.text)} ${p.doi ? `<a href="https://doi.org/${esc(p.doi)}" target="_blank" rel="noopener">DOI</a>` : ""}</li>`).join("")}</ul>
        <h3>專案</h3><ul>${(m.projects || []).map(p => `<li><a href="${esc(p.url)}" target="_blank" rel="noopener"><strong>${esc(p.name)}</strong></a><div class="small">${esc(p.zh || "")}</div></li>`).join("")}</ul></div>
    </div>`;
}

function renderProposal(p){
  if (!p){ body("proposal").innerHTML = `<div class="empty">還沒有研究計畫資料。</div>`; return; }
  if (H.me && H.me.proposal_with){  // 跟教授一起討論出來的計畫：放在那位教授的頁面（我們的進展），不算本人獨立的計畫
    const prof = (H.professors || []).find(x => x.slug === H.me.proposal_with);
    const name = prof ? prof.name : H.me.proposal_with;
    body("proposal").innerHTML = `<div class="card">「${bi(p.title_zh, p.title)}」是你跟 <strong>${esc(name)}</strong> 一起討論出來的，放在她的教授頁「我們的進展」。
      <div class="row" style="margin-top:8px"><a class="btn btn-green" href="professor.html?p=${encodeURIComponent(H.me.proposal_with)}&v=progress">看我們的進展 →</a></div>
      <p class="small muted" style="margin-top:8px">每位目標教授另外有一份依你的 CV 與她目前的經費做的「研究構想草稿」，在各教授頁裡。</p></div>`;
    return;
  }
  body("proposal").innerHTML = `
    <div class="card">
      <h3 style="margin-top:0">${bi(p.title_zh, p.title, "div")}</h3>
      <div class="small muted">${esc(p.subtitle || "")}</div>
      <div class="small" style="margin-top:6px">${esc(p.supervisor || "")}</div>
      <div style="margin-top:10px">${bi(p.synopsis_zh, p.synopsis, "div")}</div>
      <div class="src">出處：${esc(p.src || "研究計畫書")}</div>
    </div>
    <h3>研究缺口</h3><ol>${(p.gaps || []).map(g => `<li>${bi(g.zh, g.en, "div")}</li>`).join("")}</ol>
    <h3>三個研究</h3><div class="grid">${(p.studies || []).map(s => `<div class="card"><strong>${bi(s.name_zh, s.name, "div")}</strong><div class="small" style="margin-top:6px">${bi(s.detail_zh, s.detail, "div")}</div></div>`).join("")}</div>`;
}

function renderCaps(cs){
  body("capabilities").innerHTML = `<p class="muted small">整理自你的 CV，每一區都附出處，方便你面談時直接對應到具體經驗。</p>
    <div class="grid">${(cs || []).map(c => `<div class="card"><h3 style="margin-top:0">${bi(c.area_zh, c.area, "div")}</h3>
      <ul>${c.items.map((it, i) => `<li>${bi((c.items_zh || [])[i], it, "div")}</li>`).join("")}</ul><div class="src">出處：${esc(c.src)}</div></div>`).join("")}</div>`;
}

const FIT = {strong: ["g", "強相關"], partial: ["y", "部分相關"], none: ["", "沒有相關"]};
function kpis(p, middle){
  const c = p.counts || {};
  return `<div class="kpis">
    <div class="kpi"><div class="n">${c.works ?? "–"}</div><div class="l">篇文章（2022–2026）</div></div>${middle}
    <div class="kpi"><div class="n">${c.grants_pi ?? "–"}</div><div class="l">個本人主持計畫</div></div>
    <div class="kpi"><div class="n">${c.coauthors ?? "–"}</div><div class="l">位合作者</div></div></div>`;
}
function recommendBlock(p){
  const r = p.recommend, ts = r.targets, hit = ts.filter(t => t.fit !== "none"), miss = ts.filter(t => t.fit === "none");
  const link = w => `<a href="${esc(paperLink(p, w.id))}">${bi(w.title_zh, w.title)}</a>`;
  const n = k => ts.filter(t => t.fit === k).length;
  return kpis(p, `<div class="kpi"><div class="n">${n("strong")}／${n("partial")}</div><div class="l">你的 ${ts.length} 個興趣與 CV 項目：強相關／部分相關</div></div>`) +
    (r.stale ? `<div class="card" role="status"><span class="pill y">比對過期</span> 你的研究興趣或研究計畫改過了，這份推薦是用舊的內容比的。${window.APP_REMATCH ? `<button class="btn btn-yellow" data-rematch="${esc(p.slug)}">重新比對</button>` : "請跟 Claude 說「重新比對 " + esc(p.name) + "」。"}</div>` : "") +
    (r.read_first.length ? `<div><strong>建議先看這幾篇</strong><ol>${r.read_first.map(w => `<li>${w.year ?? ""}｜${link(w)}</li>`).join("")}</ol></div>` : "") +
    `<div><strong>依你的興趣與 CV 項目</strong>${hit.map(t => `<details class="card" style="margin-top:8px" ${t.fit === "strong" ? "open" : ""}>
        <summary style="cursor:pointer;min-height:44px;display:flex;flex-wrap:wrap;gap:8px;align-items:center"><span class="pill ${FIT[t.fit][0]}">${FIT[t.fit][1]}</span><strong>${esc(t.label_zh)}</strong>${t.kind === "cv" ? `<span class="small muted">（你的 CV：會的／做過的）</span>` : ""}</summary>
        <div class="small">${esc(t.why)}</div>
        ${t.papers.length ? `<ul>${t.papers.map(w => `<li>${link(w)}<div class="small muted">${esc(w.why)}</div></li>`).join("")}</ul>` : ""}
        ${t.grants.length ? `<div class="small"><strong>相關計畫</strong></div><ul>${t.grants.map(g => `<li>${STATUS[g.status] ? `<span class="pill ${STATUS[g.status][0]}">${STATUS[g.status][1]}</span>` : ""} ${bi(g.title_zh, g.title)} <span class="small muted">${esc(g.award_id || "")}</span><div class="small muted">${esc(g.why)}</div></li>`).join("")}</ul>` : ""}
      </details>`).join("")}
      ${miss.length ? `<div class="small muted" style="margin-top:8px">沒有找到相關研究：${miss.map(t => esc(t.label_zh)).join("、")}</div>` : ""}</div>
    <div class="small muted">推薦由 Claude 讀過她的文章解析與計畫後挑選，每筆都核對過原文、另有 agent 試著推翻；「適不適合」仍由你判斷。${window.APP_REMATCH && !r.stale ? ` <button class="btn btn-green" data-rematch="${esc(p.slug)}">重新比對</button>` : ""}</div>`;
}
function keywordBlock(p){
  return kpis(p, `<div class="kpi"><div class="n">${p.n_strong}</div><div class="l">篇與你的計畫用詞高度重疊<br><span class="small">（共 ${p.n_overlap_papers} 篇有任一重疊）</span></div></div>`) +
    `<div class="card"><span class="pill y">還沒比對</span> 還沒依你的興趣做推薦，以下只是用詞重疊（參考用）。${window.APP_REMATCH ? `<button class="btn btn-green" data-rematch="${esc(p.slug)}">依我的興趣比對</button>` : "請跟 Claude 說「比對 " + esc(p.name) + "」。"}</div>` +
    (p.top_papers.length ? `<div><strong>用詞最重疊的文章</strong><ol>${p.top_papers.map(w => `<li><span class="bar" aria-hidden="true"><span style="width:${w.pct}%"></span></span> ${w.year}｜<a href="${esc(paperLink(p, w.id))}">${bi(w.title_zh, w.title)}</a><div class="small muted">命中：${w.terms.map(esc).join("、")}</div></li>`).join("")}</ol></div>` : "");
}
function matchStars(r){
  /* 匹配程度 1–5 顆星：你的興趣與 CV 項目裡，強相關算 1、部分相關算 0.5，佔全部的比例換成星數 */
  if (!r || !r.targets.length) return null;
  const score = r.targets.reduce((a, t) => a + (t.fit === "strong" ? 1 : t.fit === "partial" ? 0.5 : 0), 0) / r.targets.length;
  return {n: Math.max(1, Math.min(5, Math.round(score * 5))), score};
}
function starsHTML(r){
  const s = matchStars(r);
  if (!s) return `<span class="pill y" title="還沒依你的興趣比對">還沒比對</span>`;
  const n = r.targets.length, st = r.targets.filter(t => t.fit === "strong").length, pa = r.targets.filter(t => t.fit === "partial").length;
  return `<span class="stars" role="img" aria-label="匹配程度 ${s.n} 顆星（共 5 顆）" title="你的 ${n} 個興趣與 CV 項目：強相關 ${st}、部分相關 ${pa}">${"★".repeat(s.n)}<span class="off">${"★".repeat(5 - s.n)}</span></span>`;
}
function renderProfs(ps){
  const el = body("professors");
  const head = document.querySelector("#professors h2");
  if (head && !document.getElementById("add-prof")){
    head.style.display = "flex"; head.style.justifyContent = "space-between"; head.style.alignItems = "center"; head.style.gap = "8px";
    head.insertAdjacentHTML("beforeend", window.APP_REMATCH ? `<a class="btn btn-green" id="add-prof" href="pipeline.html#new">＋ 新增教授</a>` : "");
  }
  if (!ps.length){ el.innerHTML = `<div class="empty">還沒有目標教授。按右上角「＋ 新增教授」，或跟 Claude 說「幫我建教授檔案：姓名，學校」。</div>`; return; }
  el.innerHTML = `<p class="muted">星星是匹配程度：依你的每個研究興趣與 CV 項目計畫，看她有多少強相關、部分相關的研究。點文章標題會跳到那篇的完整解析。</p>` +
    ps.map(p => {
      const c = p.counts || {};
      return `<article class="prof">
        <div class="row" style="justify-content:space-between;align-items:flex-start"><div><h3>${esc(p.name)}</h3></div>
          <div style="text-align:right">${starsHTML(p.recommend)}<div style="margin-top:6px">${p.built ? `<a class="btn btn-green" href="${esc(p.href)}">查看教授詳細資料 →</a>` : `<span class="pill y">詳細頁尚未產生</span>`}</div></div></div>
        <div class="muted small">${esc(p.institution || "")}</div>
        ${p.recommend ? recommendBlock(p) : keywordBlock(p)}
      </article>`;
    }).join("");
}

function designCode(w){
  const f = (w.card.fields || []).find(x => x.key === "design") || {};
  const m = String((f.facts || {})["設計類型"] || "").match(/（([a-z-]+)）/);
  return m ? m[1] : null;
}
function summarize(p, d, me){
  /* 與 pipeline/home.py 的 professor_summary 同一套規則：主題比對用 site_match.js，研究設計另外比 */
  const m = (me || {}).match || {};
  const query = [m.goal || "", (m.tags || "").replace(/,/g, " ")].join(" ").trim();
  const ranked = query ? rankDocs(query, buildIndex(d.match_docs)).map(r => ({...r, terms: displayTerms(query, r.matched)})) : [];
  const W = Object.fromEntries(d.works.map(w => [w.id, w])), G = Object.fromEntries(d.grants.map(g => [g.key, g]));
  const papers = ranked.filter(r => r.kind === "paper"), grants = ranked.filter(r => r.kind === "grant");
  const top = papers.length ? papers[0].score : 1, count = {}, designs = {};
  ranked.slice(0, 10).forEach(r => (r.terms || []).forEach(t => count[t] = (count[t] || 0) + 1));
  d.works.forEach(w => { const c = designCode(w); if (c) designs[c] = (designs[c] || 0) + 1; });
  return {slug: p.slug, href: `professor.html?p=${encodeURIComponent(p.slug)}`, built: true, name: d.professor.name, institution: d.professor.institution,
    counts: d.counts, stage: d.pipeline.stage, n_overlap_papers: papers.length, n_strong: papers.filter(r => r.score >= top * 0.5).length,
    shared_terms: Object.entries(count).sort((a, b) => b[1] - a[1]).map(x => x[0]).slice(0, 12),
    top_papers: papers.slice(0, 3).map(r => ({id: r.id, title: W[r.id].title, title_zh: W[r.id].title_zh, year: W[r.id].year, terms: (r.terms || []).slice(0, 6), pct: Math.round(r.score / top * 100)})),
    top_grants: grants.slice(0, 2).map(r => ({key: r.id, title: G[r.id].title || G[r.id].funder, title_zh: G[r.id].title_zh || G[r.id].funder_zh, status: G[r.id].status, award_id: G[r.id].award_id, end: G[r.id].end})),
    design_overlap: (m.methods || []).map(mth => ({method: mth, n: designs[mth] || 0})), designs,
    recommend: enrichRecommend(d.recommend, W, G)};
}
function enrichRecommend(r, W, G){
  /* prof-match 的推薦只存 id；這裡帶入標題、年份、計畫狀態給卡片顯示 */
  if (!r) return null;
  const paper = x => ({...x, title: (W[x.id] || {}).title, title_zh: (W[x.id] || {}).title_zh, year: (W[x.id] || {}).year});
  const grant = x => ({...x, title: (G[x.key] || {}).title || (G[x.key] || {}).funder, title_zh: (G[x.key] || {}).title_zh || (G[x.key] || {}).funder_zh,
    status: (G[x.key] || {}).status, award_id: (G[x.key] || {}).award_id});
  return {...r, targets: r.targets.map(t => ({...t, papers: t.papers.map(paper), grants: t.grants.map(grant)})), read_first: r.read_first.map(id => paper({id}))};
}
async function getJSON(u){ const r = await fetch(u, {cache: "no-store"}); if (!r.ok) throw new Error(u + "：" + r.status); return r.json(); }
async function loadHome(){
  const inline = document.getElementById("inline-data").textContent.trim();
  if (inline && inline !== "__INLINE__") return JSON.parse(inline);
  const me = await getJSON("../runs/_me/me.json").catch(() => null);
  const list = await getJSON("../runs/professors.json").catch(() => []);
  const profs = [];
  for (const p of list){
    try { profs.push(summarize(p, await getJSON("../runs/" + p.data), me)); }
    catch (e) { profs.push({slug: p.slug, name: p.name, institution: p.institution, built: false, counts: {}, n_strong: 0, n_overlap_papers: 0, shared_terms: [], top_papers: [], top_grants: [], design_overlap: []}); }
  }
  return {me, professors: profs};
}

let OFFLINE_HOME = false;
const PAGES = [["index.html", "首頁"], ["me.html", "我的資料"], ["professors.html", "目標教授"], ["pipeline.html", "工作進度"], ["settings.html", "設定"]];
function setupHomeViews(){
  /* 應用程式：每一塊是一個頁面（me.html、professors.html…），首頁是按鈕；離線單檔版：全部在一頁 */
  const nav = document.querySelector("nav.sections .wrap");
  const here = location.pathname.split("/").pop() || "index.html";
  if (OFFLINE_HOME){ document.getElementById("hub")?.remove(); return; }
  nav.innerHTML = PAGES.map(([f, label]) => `<a href="${f}" ${f === here ? 'aria-current="true"' : ""}>${label}</a>`).join("");
  if (here === "index.html"){
    document.querySelectorAll("main > section:not(#hub)").forEach(s => s.hidden = true);
    const hub = document.getElementById("hub");
    const ps = H.professors || [];
    const fit = p => p.recommend ? `${p.recommend.targets.filter(t => t.fit === "strong").length} 個興趣強相關` : "還沒比對";
    hub.querySelector(".body").innerHTML = `
      <div class="grid">
        <a class="card" href="me.html" style="text-decoration:none;border:2px solid var(--fg)"><strong style="font-size:1.15rem">我的資料</strong><div class="small muted">CV、研究興趣、我能做到的事</div></a>
        <a class="card" href="professors.html" style="text-decoration:none;border:2px solid var(--fg)"><strong style="font-size:1.15rem">目標教授</strong><div class="small muted">${ps.length} 位：匹配程度、該先看哪幾篇與哪個計畫；在這裡新增教授</div></a>
        <a class="card" href="pipeline.html" style="text-decoration:none;border:2px solid var(--fg)"><strong style="font-size:1.15rem">工作進度</strong><div class="small muted">Claude Code 在背景跑的工作、停點回覆</div></a>
        <a class="card" href="settings.html" style="text-decoration:none;border:2px solid var(--fg)"><strong style="font-size:1.15rem">設定</strong><div class="small muted">雲端帳號、AI、金鑰、版本</div></a>
      </div>`;
  } else {
    document.getElementById("hub")?.remove();
    const back = document.createElement("div");
    back.innerHTML = `<a class="btn btn-green" href="index.html" style="margin-top:12px">← 回首頁</a>`;
    document.querySelector("main").prepend(back);
  }
}

(async function init(){
  let l = "both"; try { l = localStorage.getItem("phdeasy:home:lang") || "both"; } catch (e) {}
  setLang(l);
  document.querySelectorAll("[data-lang]").forEach(b => b.onclick = () => setLang(b.dataset.lang));
  H = await loadHome();
  OFFLINE_HOME = document.getElementById("inline-data")?.textContent.trim() !== "__INLINE__";
  setupHomeViews();
  if (!H.me){
    $("#name").textContent = "我的博士申請首頁";
    body("me").innerHTML = `<div class="empty">還沒有你的個人資料。請把 CV 與研究計畫交給 Claude，它會整理成 runs/_me/me.json。</div>`;
    renderProposal(null); renderCaps([]);
  } else {
    renderMe(H.me); renderProposal(H.me.proposal); renderCaps(H.me.capabilities);
  }
  renderProfs(H.professors);
  if (typeof pipelinePanel === "function") pipelinePanel();
})();
