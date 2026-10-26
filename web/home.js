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
  document.querySelectorAll("[data-lang]").forEach(b => b.setAttribute("aria-checked", String(b.dataset.lang === l)));
  try { localStorage.setItem("phdeasy:home:lang", l); } catch (e) {}
}

function initLangMenu(onPick){
  /* 右上角語言圖示：點開選單，選了就關；點外面或按 Esc 也會關 */
  const btn = document.getElementById("lang-btn"), menu = document.getElementById("lang-menu");
  if (!btn || !menu) return;
  const close = () => { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); };
  btn.onclick = ev => { ev.stopPropagation(); const open = menu.hidden; menu.hidden = !open; btn.setAttribute("aria-expanded", String(open));
    if (open) (menu.querySelector('[aria-checked="true"]') || menu.querySelector("button")).focus(); };
  menu.querySelectorAll("[data-lang]").forEach(b => b.onclick = () => { onPick(b.dataset.lang); close(); btn.focus(); });
  document.addEventListener("click", ev => { if (!menu.hidden && !menu.contains(ev.target)) close(); });
  document.addEventListener("keydown", ev => { if (ev.key === "Escape" && !menu.hidden){ close(); btn.focus(); } });
}


function renderCard(m){
  /* 左邊固定的個人卡（參考 USyd 教授個人頁）：職稱、姓名、地點、聯絡方式 */
  const el = document.getElementById("pcard");
  if (!el) return;
  if (!m){ el.innerHTML = `<div class="small muted">還沒有個人資料</div>`; return; }
  const c = m.contact || {};
  const initials = (m.name || "").replace(/\(.*?\)/g, "").trim().split(/[\s-]+/).filter(Boolean).map(x => x[0]).slice(0, 2).join("").toUpperCase();
  const role = (m.headline || "").split("·")[0].trim();
  const row = (icon, html) => html ? `<li><span class="ic" aria-hidden="true">${icon}</span><span>${html}</span></li>` : "";
  el.innerHTML = `<div class="avatar" aria-hidden="true">${esc(initials)}</div>
    ${role ? `<div class="role">${esc(role)}</div>` : ""}
    <h1 class="pname">${esc((m.name || "").replace(/\s*\(.*?\)\s*/g, " ").trim())}</h1>
    ${/\(.*?\)/.test(m.name || "") || m.name_zh ? `<div class="small muted">${esc([(m.name.match(/\((.*?)\)/) || [])[1], m.name_zh].filter(Boolean).join("・"))}</div>` : ""}
    ${(() => { const rest = (t, sep) => (t || "").split(sep).slice(1).map(x => x.trim()).filter(Boolean).join(" · ");  // 第一段已經是上面的職稱
      const en = rest(m.headline, "·"), zh = rest(m.headline_zh, "｜");
      return en || zh ? `<div class="small" style="margin-top:8px">${bi(zh, en, "div")}</div>` : ""; })()}
    ${(m.education || []).length ? `<div class="pedu"><div class="role" style="margin-bottom:6px">學歷｜Education</div>${m.education.map(e =>
        `<div class="small"><strong>${esc(e.degree)}</strong><div class="muted">${esc(e.school)}（${esc(e.years)}）</div></div>`).join("")}</div>` : ""}
    <ul class="plinks">
      ${row("⌖", c.location && esc(c.location))}
      ${row("✉", c.email && `<a href="mailto:${esc(c.email)}">${esc(c.email)}</a>`)}
      ${row("⌥", c.github && `<a href="https://${esc(c.github)}" target="_blank" rel="noopener">${esc(c.github)}</a>`)}
    </ul>`;
}

function splitSentences(t, zh){
  return (t || "").split(zh ? /(?<=。)/ : /(?<=\.)\s+(?=[A-Z])/).map(x => x.trim()).filter(Boolean);
}
function renderMe(m){
  /* 簡介：條列式；學歷在左邊個人卡，這裡不重複 */
  const en = splitSentences(m.summary), zh = splitSentences(m.summary_zh, true);
  const bio = en.length === zh.length ? en.map((e, i) => [zh[i], e]) : [[m.summary_zh, m.summary]];
  body("me").innerHTML = `
    <ul class="bullets">${bio.map(([z, e]) => `<li>${bi(z, e, "div")}</li>`).join("")}</ul>
    <h3 class="label">研究興趣｜Research interests</h3>
    <ul class="bullets cols2">${(m.interests || []).map(i => `<li>${bi(i.zh, i.en, "div")}</li>`).join("")}</ul>
    <h3 class="label">發表｜Publications</h3>
    <ul class="bullets">${(m.publications || []).map(p => `<li class="small">${esc(p.text)} ${p.doi ? `<a href="https://doi.org/${esc(p.doi)}" target="_blank" rel="noopener">DOI</a>` : ""}</li>`).join("")}</ul>
    <h3 class="label">專案｜Projects</h3>
    <ul class="bullets">${(m.projects || []).map(p => `<li><a href="${esc(p.url)}" target="_blank" rel="noopener"><strong>${esc(p.name)}</strong></a><div class="small">${esc(p.zh || "")}</div></li>`).join("")}</ul>
    <div class="src">內容出處：${esc([...new Set([m.summary_src, m.interests_src, "CV"].filter(Boolean))].join("；"))}</div>`;
}


const CONF = {high: ["g", "信心 高"], medium: ["y", "信心 中"], low: ["r", "信心 低"]};
function renderProposal(){
  /* 計畫書：每位目標教授一列。跟她定案的放定案版；其他教授是 AI 依她的方向與經費擬的幾個版本 */
  const el = body("proposal");
  if (!el) return;
  const ps = H.professors || [];
  if (!ps.length){ el.innerHTML = `<div class="empty">還沒有目標教授。</div>`; return; }
  const href = p => OFFLINE_HOME ? p.href : `professor.html?p=${encodeURIComponent(p.slug)}&v=proposal`;
  el.innerHTML = ps.map(p => {
    const pr = p.proposal || {};
    const body = pr.joint ? `<div class="row">${'<span class="pill g">已定案</span>'}<strong>${bi(pr.joint_title_zh, pr.joint_title)}</strong></div>`
      : (pr.versions || []).length ? `<ul class="vlist">${pr.versions.map(v => { const c = CONF[v.level] || ["", "?"];
          return `<li><span class="pill ${c[0]}">${c[1]}</span> <strong>${esc(v.id)}</strong>｜${bi(v.direction_zh, v.direction_en)}</li>`; }).join("")}</ul>${pr.stale ? `<div class="small muted">你的 CV 或她的資料改過，這幾版可能過期。</div>` : ""}`
      : `<div class="small muted">還沒有計畫書。到她的頁面可以產生 AI 草稿。</div>`;
    return `<article class="card" style="margin-bottom:12px"><div class="row" style="justify-content:space-between;align-items:flex-start">
        <div><h3 style="margin:0">${esc(p.name)}</h3><div class="small muted">${esc(p.institution || "")}</div></div>
        <a class="btn btn-green" href="${esc(href(p))}">${pr.joint ? "看定案版" : (pr.versions || []).length ? "看草稿" : "到她的頁面"} →</a></div>
      <div style="margin-top:10px">${body}</div></article>`;
  }).join("");
}

function renderStatement(kind){
  /* Personal Statement／SOP：左英右中逐段對照；[方括號] 的待填段落標黃 */
  const el = body(kind);
  if (!el) return;
  const st = ((H.me || {}).statements || {})[kind];
  if (!st){ el.innerHTML = `<div class="empty">還沒有${kind === "sop" ? " SOP" : " Personal Statement"}。把 Word 檔給 Claude，它會用 <code>me_proposal.py statement ${kind} &lt;檔案&gt;</code> 匯入並翻成中文。</div>`; return; }
  const lr = (zh, en) => `<div class="lr"><div class="en" lang="en">${esc(en || "")}</div><div class="zh">${zh ? esc(zh) : '<span class="muted">（尚無中文）</span>'}</div></div>`;
  el.innerHTML = `<div class="card"><div class="small muted">出處：${esc(st.src || "")}</div>
      <h3 style="margin:8px 0 0">${lr(st.title_zh, st.title)}</h3></div>
    ${st.blocks.map(b => `<div class="${b.type === "note" ? "item attn" : "stmt-p"}">${b.type === "note" ? '<span class="pill y">待填</span> ' : ""}${lr(b.zh, b.en)}</div>`).join("")}`;
}

function renderCaps(cs){
  /* 我能做到的事：條列式；跟發表、專案、學歷重複的項目不再列（那些在上面或左邊個人卡） */
  const m = H.me || {};
  const dupKeys = [...(m.projects || []).map(p => (p.name || "").split(/\s+[—-]\s+/)[0]), ...(m.education || []).map(e => e.school)].filter(Boolean);
  const isDup = it => (/^first-author publication/i.test(it) && (m.publications || []).length) || dupKeys.some(k => it.includes(k));
  body("capabilities").innerHTML = (cs || []).map(c => {
    const items = c.items.map((it, i) => [it, (c.items_zh || [])[i]]).filter(([it]) => !isDup(it));
    return items.length ? `<h3 class="label">${esc(c.area_zh || c.area)}｜${esc(c.area)}</h3>
      <ul class="bullets">${items.map(([it, z]) => `<li>${bi(z, it, "div")}</li>`).join("")}</ul>` : "";
  }).join("") || `<div class="empty">還沒有資料。</div>`;
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
    (r.stale ? `<div class="card" role="status"><span class="pill y">比對過期</span> 你的研究興趣或 CV 改過了，這份推薦是用舊的內容比的。${window.APP_REMATCH ? `<button class="btn btn-yellow" data-rematch="${esc(p.slug)}">重新比對</button>` : "請跟 Claude 說「重新比對 " + esc(p.name) + "」。"}</div>` : "") +
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
let PROF_SORT = "stars";
function renderProfs(ps){
  /* 目標教授：每位一張收合卡，只放重要資訊與「必讀前五篇」（跟你最相關的），其他點進教授頁看；右上角可依星星排序 */
  const el = body("professors");
  const head = document.querySelector("#professors h2");
  if (head && !document.getElementById("prof-tools")){
    head.insertAdjacentHTML("afterend", `<div class="row" id="prof-tools" style="justify-content:space-between;align-items:flex-end;margin:-4px 0 12px;flex-wrap:nowrap">
      <span class="small muted">星星＝你的興趣與 CV 項目裡，<br>她有多少強相關、部分相關的研究。</span>
      <span class="row" style="flex:none"><label class="small" for="prof-sort">排序</label><select id="prof-sort">
        <option value="stars">星星多→少</option><option value="stars-asc">星星少→多</option><option value="name">姓名</option></select>
        ${window.APP_REMATCH ? `<button class="btn btn-green" id="add-prof-btn" aria-expanded="false" aria-controls="add-prof-form">＋ 新增教授</button>` : ""}</span></div>
      ${window.APP_REMATCH ? `<form class="card" id="add-prof-form" hidden style="margin-bottom:12px">
        <p class="small muted" style="margin-top:0">按「開始建檔」後，Claude Code 會在背景找身分、列文章、找全文，跑到停 1 停下來請你確認（通常 10–30 分鐘，進度在右上角「工作進度」）。</p>
        <label for="np-name">教授姓名（必填）</label><input type="text" id="np-name" placeholder="例：Liliana Laranjo" required>
        <label for="np-inst">學校／機構（必填）</label><input type="text" id="np-inst" placeholder="例：The University of Sydney（Westmead Applied Research Centre）" required>
        <label for="np-orcid">ORCID（選填）</label><input type="text" id="np-orcid" placeholder="0000-0000-0000-0000">
        <div class="row" style="margin-top:12px"><button class="btn btn-green" type="submit">開始建檔</button><button class="btn" type="button" id="np-cancel">取消</button></div>
      </form>` : ""}`);
    document.getElementById("prof-sort").onchange = ev => { PROF_SORT = ev.target.value; renderProfs(ps); };
    const form = document.getElementById("add-prof-form"), btn = document.getElementById("add-prof-btn");
    if (form){  // 點「＋ 新增教授」才打開填寫欄位
      const toggle = open => { form.hidden = !open; btn.setAttribute("aria-expanded", String(open)); if (open) form.querySelector("#np-name").focus(); };
      btn.onclick = () => toggle(form.hidden);
      form.querySelector("#np-cancel").onclick = () => toggle(false);
      form.onsubmit = async ev => {
        ev.preventDefault();
        const sub = form.querySelector('[type="submit"]'); sub.disabled = true;
        try { await API("new", {name: form.querySelector("#np-name").value.trim(), institution: form.querySelector("#np-inst").value.trim(),
                                orcid: form.querySelector("#np-orcid").value.trim()}); location.href = "pipeline.html"; }
        catch (e) { alert(e.message); sub.disabled = false; }
      };
      if (location.hash === "#new") toggle(true);
    }
  }
  if (!ps.length){ el.innerHTML = `<div class="empty">還沒有目標教授。按上面的「＋ 新增教授」，或跟 Claude 說「幫我建教授檔案：姓名，學校」。</div>`; return; }
  const score = p => (matchStars(p.recommend) || {score: -1}).score;
  const list = [...ps].sort(PROF_SORT === "name" ? (a, b) => (a.name || "").localeCompare(b.name || "")
    : PROF_SORT === "stars-asc" ? (a, b) => score(a) - score(b) : (a, b) => score(b) - score(a));
  el.innerHTML = list.map(p => {
    const c = p.counts || {}, r = p.recommend;
    const strong = r ? r.targets.filter(t => t.fit === "strong").length : null, partial = r ? r.targets.filter(t => t.fit === "partial").length : null;
    const top5 = r ? (r.read_first || []).slice(0, 5) : (p.top_papers || []).slice(0, 5);
    const facts = [c.works != null && `${c.works} 篇（2022–2026）`, c.grants_pi != null && `本人主持計畫 ${c.grants_pi}`, c.coauthors != null && `合作者 ${c.coauthors} 位`,
                   r && `強相關 ${strong}／部分相關 ${partial}`].filter(Boolean);
    return `<details class="profcard">
      <summary><div class="pc-head"><div><strong class="pc-name">${esc(p.name)}</strong><div class="small muted">${esc(p.institution || "")}</div>
          <div class="small" style="margin-top:4px">${facts.map(esc).join("｜")}</div></div>${starsHTML(r)}</div></summary>
      <div class="pc-body">
        ${top5.length ? `<div class="small muted" style="margin-bottom:4px">必讀前五篇（跟你最相關）</div>
          <ol class="top5">${top5.map(w => `<li><a href="${esc(paperLink(p, w.id))}">${bi(w.title_zh, w.title)}</a> <span class="small muted">${esc(w.year || "")}</span></li>`).join("")}</ol>`
          : `<div class="small muted">還沒比對，沒有推薦的必讀文章。</div>`}
        <div class="row" style="margin-top:10px">${p.built ? `<a class="btn btn-green" href="${esc(p.href)}">進入教授頁 →</a>` : `<span class="pill y">詳細頁尚未產生</span>`}
          ${window.APP_REMATCH ? `<button class="btn" data-rematch="${esc(p.slug)}">${r ? "重新比對" : "依我的興趣比對"}</button>` : ""}</div>
      </div></details>`;
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
    recommend: enrichRecommend(d.recommend, W, G), proposal: proposalSummary(d)};
}
function proposalSummary(d){
  /* 計畫書頁籤用：定案版或 AI 草稿各版的方向與信心（與 pipeline/home.py 同一套） */
  const j = d.joint_proposal, pd = d.proposal_draft;
  return {joint: !!j, joint_title: j && j.title, joint_title_zh: j && j.title_zh, stale: !!(pd && pd.stale),
    versions: ((pd && pd.versions) || []).map(v => ({id: v.id, level: (v.confidence || {}).level, direction_zh: (v.direction || {}).zh, direction_en: (v.direction || {}).en}))};
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
const PAGES = [["index.html", "簡介"], ["professors.html", "目標教授"], ["proposals.html", "計畫書"], ["ps.html", "Personal Statement"], ["sop.html", "SOP"]];
const MORE = [["pipeline.html", "工作進度"], ["settings.html", "設定"]];
const PAGE_SECTIONS = {"index.html": ["me", "capabilities"], "me.html": ["me", "capabilities"], "professors.html": ["professors"], "proposals.html": ["proposal"],
                       "ps.html": ["ps"], "sop.html": ["sop"], "pipeline.html": ["pipeline"], "settings.html": ["settings"]};
function setupHomeViews(){
  /* 頁籤（參考 USyd 教授個人頁）：簡介｜目標教授｜計畫書｜Personal Statement｜SOP；工作進度與設定在右上角。
     離線單檔版全部在一頁，頁籤變成頁內連結 */
  const tabs = document.getElementById("tabs");
  const here = location.pathname.split("/").pop() || "index.html";
  if (OFFLINE_HOME){
    tabs.innerHTML = [["me", "簡介"], ["professors", "目標教授"], ["proposal", "計畫書"], ["ps", "Personal Statement"], ["sop", "SOP"]].map(([id, l]) => `<a href="#${id}">${l}</a>`).join("");
    return;
  }
  const cur = here === "me.html" ? "index.html" : here;
  tabs.innerHTML = PAGES.map(([f, label]) => `<a href="${f}" ${f === cur ? 'aria-current="page"' : ""}>${label}</a>`).join("");
  MORE.forEach(([f]) => { const a = document.querySelector(`.topicons a[href="${f}"]`); if (a && f === cur) a.setAttribute("aria-current", "page"); });
  const show = PAGE_SECTIONS[here] || PAGE_SECTIONS["index.html"];
  document.querySelectorAll(".pmain > section").forEach(sec => { sec.hidden = !show.includes(sec.id); });
}

(async function init(){
  let l = "both"; try { l = localStorage.getItem("phdeasy:home:lang") || "both"; } catch (e) {}
  setLang(l);
  initLangMenu(setLang);
  H = await loadHome();
  OFFLINE_HOME = document.getElementById("inline-data")?.textContent.trim() !== "__INLINE__";
  setupHomeViews();
  renderCard(H.me);
  if (!H.me){
    body("me").innerHTML = `<div class="empty">還沒有你的個人資料。請把 CV 與研究計畫交給 Claude，它會整理成 runs/_me/me.json。</div>`;
    renderCaps([]);
  } else {
    renderMe(H.me); renderCaps(H.me.capabilities);
  }
  renderProposal(); renderStatement("ps"); renderStatement("sop");
  renderProfs(H.professors);
  if (typeof pipelinePanel === "function") pipelinePanel();
})();
