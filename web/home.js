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
function renderMeEdit(m){
  /* 本人自己改簡介與研究興趣（例：不想做某個領域就刪掉）；存檔後舊版留在 runs/_me/history/ */
  const row = (i, it) => `<div class="row int-row" style="flex-wrap:nowrap;margin:6px 0"><input type="text" value="${esc(it.zh || "")}" placeholder="中文" style="flex:1">
    <input type="text" value="${esc(it.en || "")}" placeholder="English" style="flex:1"><button type="button" class="btn btn-sm" data-int-del aria-label="刪掉這個興趣">刪掉</button></div>`;
  body("me").innerHTML = `<form id="me-form" class="match-form" style="max-width:none">
    <div><label for="me-sum-zh">簡介（中文）</label><textarea id="me-sum-zh" rows="3">${esc(m.summary_zh || "")}</textarea></div>
    <div><label for="me-sum-en">簡介（English）</label><textarea id="me-sum-en" rows="3">${esc(m.summary || "")}</textarea></div>
    <div><strong>研究興趣</strong><div class="small muted">刪掉不想做的；改了之後各教授的比對會標「過期」，可以按「重新比對」。</div><div id="int-list">${(m.interests || []).map((it, i) => row(i, it)).join("")}</div>
      <button type="button" class="btn btn-sm" id="int-add">＋ 新增興趣</button></div>
    <div class="row"><button class="btn btn-green" type="submit">儲存</button><button class="btn" type="button" id="me-cancel">取消</button><span class="small" id="me-msg"></span></div></form>`;
  const f = document.getElementById("me-form");
  f.addEventListener("click", ev => { if (ev.target.matches("[data-int-del]")) ev.target.closest(".int-row").remove(); });
  document.getElementById("int-add").onclick = () => { document.getElementById("int-list").insertAdjacentHTML("beforeend", row(0, {})); document.querySelector("#int-list .int-row:last-child input").focus(); };
  document.getElementById("me-cancel").onclick = () => renderMe(m);
  f.onsubmit = async ev => {
    ev.preventDefault();
    const interests = [...f.querySelectorAll(".int-row")].map(r => { const [zh, en] = r.querySelectorAll("input"); return {zh: zh.value.trim(), en: en.value.trim()}; }).filter(i => i.zh || i.en);
    try {
      await API("me-update", {summary: f.querySelector("#me-sum-en").value, summary_zh: f.querySelector("#me-sum-zh").value, interests});
      document.getElementById("me-msg").textContent = "已儲存。";
      setTimeout(() => location.reload(), 600);
    } catch (e) { document.getElementById("me-msg").textContent = "儲存失敗：" + e.message; }
  };
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
  const head = document.querySelector("#me h2");
  if (window.APP_REMATCH && head && !document.getElementById("me-edit")){
    head.insertAdjacentHTML("afterend", `<div style="text-align:right;margin:-34px 0 8px"><button class="btn btn-sm" id="me-edit">編輯簡介與研究興趣</button></div>`);
    document.getElementById("me-edit").onclick = () => renderMeEdit(H.me);
  }
}


const CONF = {high: ["g", "信心 高"], medium: ["y", "信心 中"], low: ["r", "信心 低"]};
function renderProposal(){
  /* Research Proposal：每位目標教授一份。有上傳的計畫書（例：跟 Liliana 定案的）可以打開、看版本、每段 AI 編修；
     沒有的列出 AI 依她的方向與經費擬的草稿各版 */
  const el = body("proposal");
  if (!el) return;
  const ps = H.professors || [];
  if (!ps.length){ el.innerHTML = `<div class="empty">還沒有目標教授。</div>`; return; }
  el.innerHTML = ps.map(p => {
    const key = `proposal--${p.slug}`, has = !!(H.docs || {})[key], pr = p.proposal || {};
    const drafts = (pr.versions || []).length ? `<ul class="vlist">${pr.versions.map(v => { const c = CONF[v.level] || ["", "?"];
        return `<li><span class="pill ${c[0]}">${c[1]}</span> <strong>${esc(v.id)}</strong>｜${bi(v.direction_zh, v.direction_en)}</li>`; }).join("")}</ul>` : "";
    return `<details class="profcard" ${has ? "open" : ""}><summary><div class="pc-head"><div><strong class="pc-name">${esc(p.name)}</strong><div class="small muted">${esc(p.institution || "")}</div></div>
        ${has ? `<span class="pill g">第 ${(H.docs[key].versions.slice(-1)[0] || {}).n} 版</span>` : (pr.versions || []).length ? `<span class="pill y">AI 草稿 ${pr.versions.length} 版</span>` : `<span class="pill">還沒有</span>`}</div></summary>
      <div class="pc-body" data-doc-root>${has ? "" : drafts ? `<div class="small muted">AI 依她的方向與經費擬的草稿（<a href="professor.html?p=${encodeURIComponent(p.slug)}&v=proposal">到她的頁面看全文</a>）：</div>${drafts}` : ""}<div data-doc-slot="${esc(key)}"></div></div></details>`;
  }).join("");
  el.querySelectorAll("[data-doc-slot]").forEach(slot => renderDoc(slot.dataset.docSlot, slot));
}

/* ===== 本人的文件：上傳就顯示、每段 AI 編修、版本 ===== */
const DOC_NAMES = {proposal: ["Research Proposal", "研究計畫書"], ps: ["Personal Statement", "個人陳述"], sop: ["Statement of Purpose", "研究目的陳述"]};
const ME_ROOT = () => OFFLINE_HOME ? "_me/" : "../runs/_me/";
const DOC_VIEW = {};  // key → 正在看的版本號
function lrHTML(zh, en){ return `<div class="lr"><div class="en" lang="en">${esc(en || "")}</div><div class="zh">${zh ? esc(zh) : '<span class="muted">（翻譯中／尚無中文）</span>'}</div></div>`; }
function docBlocksHTML(doc, editable){
  /* 依顯示順序編號可編修的段落（跟 scripts/pipeline/mydocs.py 的 blocks_of 同順序）；計畫書有章節、圖、表 */
  let k = 0;
  const editBtn = () => editable ? `<button class="btn btn-sm" data-doc-edit="${k}">AI 編修</button>` : "";
  const block = b => {
    if (["p", "h2", "h3", "note"].includes(b.type)){
      const html = `<div class="docb ${b.type}" data-block="${k}">${b.type === "note" ? '<span class="pill y">待填</span> ' : ""}${lrHTML(b.zh, b.en)}<div class="docb-tools">${editBtn()}</div></div>`;
      k++; return html;
    }
    if (b.type === "figure") return `<figure class="doc-fig"><img loading="lazy" src="${esc(ME_ROOT() + b.src)}" alt="${esc(b.caption_en || "圖")}"><figcaption class="small">${lrHTML(b.caption_zh, b.caption_en)}</figcaption></figure>`;
    if (b.type === "table"){
      const t = rows => `<div class="tablebox"><table><thead><tr>${rows[0].map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.slice(1).map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
      const rz = (b.rows_zh || []).length === b.rows.length ? b.rows_zh : null;
      return `<figure class="doc-tbl"><figcaption class="small">${lrHTML(b.caption_zh, b.caption_en)}</figcaption><div class="lr"><div class="en">${t(b.rows)}</div><div class="zh">${rz ? t(rz) : ""}</div></div></figure>`;
    }
    if (b.type === "ref") return `<li class="small" lang="en">${esc(b.en.replace(/^\d+\.\s*/, ""))}</li>`;
    return "";
  };
  if (doc.sections) return doc.sections.map(sec => {
    const refs = (sec.blocks || []).filter(b => b.type === "ref"), rest = (sec.blocks || []).filter(b => b.type !== "ref");
    return `<details class="doc-sec" ${sec.key === "references" ? "" : "open"}><summary><strong>${esc(sec.heading_zh || "")}｜<span lang="en">${esc(sec.heading_en || "")}</span></strong></summary>
      ${rest.map(block).join("")}${refs.length ? `<ol class="doc-refs">${refs.map(block).join("")}</ol>` : ""}</details>`;
  }).join("");
  return (doc.blocks || []).map(block).join("");
}
async function renderDoc(key, el, opts = {}){
  /* 一份文件：版本選單、上傳新版、翻成中文、每段 AI 編修 */
  const info = (H.docs || {})[key];
  const kind = key.split("--")[0], [nameEn, nameZh] = DOC_NAMES[kind];
  const app = !!window.APP_REMATCH;
  const upload = app ? `<label class="btn btn-green" style="cursor:pointer">上傳 Word／PDF${info ? "（存成新版本）" : ""}<input type="file" accept=".docx,.pdf" hidden data-doc-upload="${esc(key)}"></label>` : "";
  if (!info){ el.innerHTML = `<div class="empty">還沒有 ${nameEn}。${app ? "" : "在應用程式裡打開可以上傳。"}<div class="row" style="margin-top:10px">${upload}</div><div class="small" data-doc-msg></div></div>`; return; }
  const vs = info.versions, cur = DOC_VIEW[key] || vs[vs.length - 1].n, latest = vs[vs.length - 1].n;
  let doc = info.latest;
  if (cur !== latest && !OFFLINE_HOME){ try { doc = await getJSON(`${ME_ROOT()}docs/${key}/v${cur}/doc.json`); } catch (e) {} }
  const v = vs.find(x => x.n === cur) || vs[vs.length - 1];
  const texts = (doc.sections ? doc.sections.flatMap(x => x.blocks || []) : doc.blocks || []).filter(b => ["p", "h2", "h3", "note"].includes(b.type));
  const needZh = texts.some(b => !b.zh);
  const ORIGIN = {upload: "上傳", "ai-edit": "AI 編修"};
  el.innerHTML = `<div class="doc-bar">
      <div class="row"><label class="small" for="ver-${esc(key)}">版本</label><select id="ver-${esc(key)}" data-doc-ver="${esc(key)}">${[...vs].reverse().map(x =>
        `<option value="${x.n}" ${x.n === cur ? "selected" : ""}>第 ${x.n} 版｜${esc(ORIGIN[x.origin] || x.origin)}｜${esc((x.created || "").slice(0, 10))}${x.note ? "｜" + esc(x.note) : ""}</option>`).join("")}</select>
        ${cur !== latest ? '<span class="pill y">舊版本（只能看）</span>' : '<span class="pill g">最新版</span>'}</div>
      <div class="row">${needZh && app ? `<button class="btn" data-doc-translate="${esc(key)}" data-v="${cur}">翻成中文</button>` : ""}${upload}</div></div>
    ${v.origin === "ai-edit" && v.changed ? `<div class="small muted" style="margin:8px 0">這一版是從第 ${v.base} 版 AI 編修第 ${v.changed.map(i => i + 1).join("、")} 段而來${v.note ? "：" + esc(v.note) : ""}。</div>` : ""}
    <div class="small" data-doc-msg></div>
    <h3 style="margin:14px 0 6px">${lrHTML(doc.title_zh, doc.title || nameEn)}</h3>
    <div class="doc-body" data-doc-key="${esc(key)}" data-v="${cur}">${docBlocksHTML(doc, app && cur === latest)}</div>`;
  if (v.origin === "ai-edit") (v.changed || []).forEach(i => el.querySelector(`.docb[data-block="${i}"]`)?.classList.add("changed"));
}
function renderStatement(kind){
  const el = body(kind);
  if (el) renderDoc(kind, el);
}
document.addEventListener("change", async ev => {
  const t = ev.target;
  if (t.matches("[data-doc-ver]")){ DOC_VIEW[t.dataset.docVer] = +t.value; renderDoc(t.dataset.docVer, t.closest("[data-doc-slot]") || t.closest("section .body")); return; }
  if (t.matches("[data-doc-upload]") && t.files.length){
    const key = t.dataset.docUpload, [kind, slug] = key.split("--"), f = t.files[0], ext = f.name.split(".").pop().toLowerCase();
    const msg = (t.closest("[data-doc-slot]") || t.closest("section .body")).querySelector("[data-doc-msg]");
    msg.textContent = "上傳中…";
    try {
      const q = new URLSearchParams({kind, ext, ...(slug ? {for: slug} : {})});
      const r = await fetch(`/api/doc-upload?${q}`, {method: "POST", headers: {"X-Phdeasy-App": "1"}, body: await f.arrayBuffer()}).then(x => x.json());
      if (r.error) throw new Error(r.error);
      msg.textContent = `已存成第 ${r.version} 版。${r.translating ? "中文正在背景翻譯（右上角工作進度看進度），" : ""}重新整理就會看到。`;
      setTimeout(() => location.reload(), 1200);
    } catch (e) { msg.textContent = "上傳失敗：" + e.message; }
  }
});
document.addEventListener("click", async ev => {
  const ed = ev.target.closest("[data-doc-edit]"), tr = ev.target.closest("[data-doc-translate]"), go = ev.target.closest("[data-doc-go]");
  if (ed){
    const box = ed.closest(".docb");
    if (box.querySelector(".doc-ask")) return;
    box.insertAdjacentHTML("beforeend", `<div class="doc-ask row"><input type="text" placeholder="要怎麼改？例：更精簡、更強調研究動機（空白＝整體潤飾）" style="flex:1">
      <button class="btn btn-green btn-sm" data-doc-go>交給 AI</button><button class="btn btn-sm" onclick="this.closest('.doc-ask').remove()">取消</button></div>`);
    box.querySelector(".doc-ask input").focus();
    return;
  }
  if (go){
    const box = go.closest(".docb"), bodyEl = go.closest(".doc-body");
    go.disabled = true;
    try {
      await API("doc-edit", {key: bodyEl.dataset.docKey, version: +bodyEl.dataset.v, block: +box.dataset.block, instruction: box.querySelector(".doc-ask input").value});
      box.querySelector(".doc-ask").innerHTML = `<span class="small">已交給 AI，改好會存成新版本（右上角工作進度看進度），完成後重新整理。</span>`;
    } catch (e) { alert(e.message); go.disabled = false; }
    return;
  }
  if (tr){
    tr.disabled = true;
    try { await API("doc-translate", {key: tr.dataset.docTranslate, version: +tr.dataset.v}); tr.textContent = "翻譯中…（完成後重新整理）"; }
    catch (e) { alert(e.message); tr.disabled = false; }
  }
});

function renderCaps(){
  /* 工作經歷（本人 2026-10-26：取代「我能做到的事」）：每段經歷條列，括號裡是重點技能 */
  const xs = (H.me || {}).experience || [];
  const head = document.querySelector("#capabilities h2");
  if (head) head.textContent = "工作經歷｜Experience";
  const group = (k, label) => {
    const list = xs.filter(x => x.kind === k);
    return list.length ? `<h3 class="label">${label}</h3>${list.map(x => `<div class="exp">
      <div class="exp-head"><div><strong>${bi(x.role_zh, x.role)}</strong><div class="small">${esc(x.org)}${x.place ? "｜" + esc(x.place) : ""}</div></div><span class="small muted">${esc(x.dates || "")}</span></div>
      <ul class="bullets">${(x.bullets || []).map(b => `<li>${bi(b.zh, b.en, "div")}</li>`).join("")}</ul>
      ${(x.skills || []).length ? `<div class="small skills">（重點技能：${x.skills.map((sk, i) => `<span class="pill">${bi((x.skills_zh || [])[i], sk)}</span>`).join(" ")}）</div>` : ""}</div>`).join("")}` : "";
  };
  body("capabilities").innerHTML = xs.length ? group("professional", "工作｜Professional") + group("research", "研究｜Research")
    + `<div class="src">內容出處：${esc((H.me || {}).experience_src || "CV")}</div>` : `<div class="empty">還沒有工作經歷。</div>`;
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
  const docs = await getJSON("../runs/_me/docs/index.json").catch(() => ({}));
  const profs = [];
  for (const p of list){
    try { profs.push(summarize(p, await getJSON("../runs/" + p.data), me)); }
    catch (e) { profs.push({slug: p.slug, name: p.name, institution: p.institution, built: false, counts: {}, n_strong: 0, n_overlap_papers: 0, shared_terms: [], top_papers: [], top_grants: [], design_overlap: []}); }
  }
  return {me, professors: profs, docs};
}

let OFFLINE_HOME = false;
const PAGES = [["index.html", "簡介"], ["professors.html", "目標教授"], ["proposals.html", "Research Proposal"], ["ps.html", "Personal Statement"], ["sop.html", "Statement of Purpose"]];
const MORE = [["settings.html", "設定與工作進度"]];
const PAGE_SECTIONS = {"index.html": ["me", "capabilities"], "me.html": ["me", "capabilities"], "professors.html": ["professors"], "proposals.html": ["proposal"],
                       "ps.html": ["ps"], "sop.html": ["sop"], "pipeline.html": ["pipeline", "settings"], "settings.html": ["pipeline", "settings"]};
function setupHomeViews(){
  /* 頁籤（參考 USyd 教授個人頁）：簡介｜目標教授｜Research Proposal｜Personal Statement｜Statement of Purpose；設定與工作進度在右上角齒輪。
     離線單檔版全部在一頁，頁籤變成頁內連結 */
  const tabs = document.getElementById("tabs");
  const here = location.pathname.split("/").pop() || "index.html";
  if (OFFLINE_HOME){
    tabs.innerHTML = [["me", "簡介"], ["professors", "目標教授"], ["proposal", "Research Proposal"], ["ps", "Personal Statement"], ["sop", "Statement of Purpose"]].map(([id, l]) => `<a href="#${id}">${l}</a>`).join("");
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
