/* 資料：應用程式從 runs/ 讀（me.json、professors.json、各教授 data.json），比對在瀏覽器裡算；離線單檔版內嵌在 #inline-data */
let H = null;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const bi = (zh, en, tag = "span") => (zh ? `<${tag} class="t-zh">${esc(zh)}</${tag}>` : "") + (tag === "span" && zh && en ? " " : "") + (en ? `<${tag} class="t-en" lang="en">${esc(en)}</${tag}>` : "");
const body = id => $(`#${id} .body`) || document.createElement("div");  // 這一頁沒有這一區就畫到看不見的地方
const has = id => !!document.getElementById(id);
const paperLink = (p, id) => OFFLINE_HOME ? `${p.href}#paper-${id}` : `paper.html?p=${encodeURIComponent(p.slug)}&id=${encodeURIComponent(id)}`;
const STATUS = {confirmed: ["g", "主持人"], pending: ["y", "待確認"], acknowledged: ["", "論文致謝提及"], other: ["", "協同主持人"]};

const T = (zh, en) => `<span class="ll"><span class="t-zh">${esc(zh)}</span><span class="t-en" lang="en">${esc(en)}</span></span>`;  // 介面字：跟著語言切換
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
    ${(m.education || []).length ? `<div class="pedu"><div class="role" style="margin-bottom:6px">${T("學歷", "Education")}</div>${m.education.map(e =>
        `<div class="small"><strong>${esc(e.degree)}</strong><div class="muted">${esc(e.school)}（${esc(e.years)}）</div>${e.advisor ? `<div class="muted">${T("指導教授：", "Advisor: ")}${esc(e.advisor)}</div>` : ""}</div>`).join("")}</div>` : ""}
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
    <input type="text" value="${esc(it.en || "")}" placeholder="English" style="flex:1">${ibtn("trash", "刪掉這個興趣 Delete", "data-int-del", "btn-sm danger")}</div>`;
  body("me").innerHTML = `<form id="me-form" class="match-form" style="max-width:none">
    <div><label for="me-sum-zh">簡介（中文）</label><textarea id="me-sum-zh" rows="3">${esc(m.summary_zh || "")}</textarea></div>
    <div><label for="me-sum-en">簡介（English）</label><textarea id="me-sum-en" rows="3">${esc(m.summary || "")}</textarea></div>
    <div><strong>研究興趣</strong><div class="small muted">刪掉不想做的；改了之後各教授的比對會標「過期」，可以按「重新比對」。</div><div id="int-list">${(m.interests || []).map((it, i) => row(i, it)).join("")}</div>
      <button type="button" class="btn btn-sm" id="int-add">＋ 新增興趣</button></div>
    <div class="row"><button class="btn btn-green" type="submit">儲存</button><button class="btn" type="button" id="me-cancel">取消</button><span class="small" id="me-msg"></span></div></form>`;
  const f = document.getElementById("me-form");
  f.addEventListener("click", ev => { if (ev.target.closest("[data-int-del]")) ev.target.closest(".int-row").remove(); });
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
    <h3 class="label">${T("研究興趣", "Research interests")}</h3>
    <ul class="bullets cols2">${(m.interests || []).map(i => `<li>${bi(i.zh, i.en, "div")}</li>`).join("")}</ul>
    <h3 class="label">${T("發表", "Publications")}</h3>
    <ul class="bullets">${(m.publications || []).map(p => `<li class="small">${esc(p.text)} ${p.doi ? `<a href="https://doi.org/${esc(p.doi)}" target="_blank" rel="noopener">DOI</a>` : ""}</li>`).join("")}</ul>
    <h3 class="label">${T("專案", "Projects")}</h3>
    <ul class="bullets">${(m.projects || []).map(p => `<li><a href="${esc(p.url)}" target="_blank" rel="noopener"><strong>${esc(p.name)}</strong></a>
      ${p.summary ? `<div class="small" style="margin-top:4px">${bi(p.summary.zh, p.summary.en, "div")}</div>` : `<div class="small">${bi(p.zh, p.en, "div")}</div>`}
      ${(p.overview || []).length ? `<details style="margin-top:4px"><summary class="small" style="cursor:pointer;min-height:36px;display:flex;align-items:center">${T("專案大概", "Overview")}</summary>
        <ul class="small" style="margin:4px 0 0;padding-left:18px">${p.overview.map(o => `<li style="margin:4px 0">${bi(o.zh, o.en, "div")}</li>`).join("")}</ul></details>` : ""}</li>`).join("")}</ul>`;
  const head = document.querySelector("#me h2");
  if (window.APP_REMATCH && head && !document.getElementById("me-edit")){
    head.insertAdjacentHTML("afterend", `<div id="me-edit-wrap" style="text-align:right;margin:-34px 0 8px">${ibtn("edit", "編輯簡介與研究興趣 Edit", 'id="me-edit"')}</div>`);
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
  if (!ps.length){ el.innerHTML = `<div class="empty">還沒有申請目標。</div>`; return; }
  /* 定案的（有你上傳的計畫書）放最上面，再來是有 AI 草稿的，最後是還沒有的 */
  const rank = p => (H.docs || {})[`proposal--${p.slug}`] ? 0 : ((p.proposal || {}).versions || []).length ? 1 : 2;
  el.innerHTML = [...ps].sort((a, b) => rank(a) - rank(b)).map(p => {
    const key = `proposal--${p.slug}`, has = !!(H.docs || {})[key], pr = p.proposal || {};
    const drafts = (pr.versions || []).length ? `<ul class="vlist">${pr.versions.map(v => { const c = CONF[v.level] || ["", "?"];
        return `<li><span class="pill ${c[0]}">${c[1]}</span> <strong>${esc(v.id)}</strong>｜${bi(v.direction_zh, v.direction_en)}</li>`; }).join("")}</ul>` : "";
    return `<details class="profcard" ${has ? "open" : ""}><summary><div class="pc-head"><div><strong class="pc-name">${esc(p.name)}</strong><div class="small muted">${esc((p.owner || {}).institution || p.institution || "")}</div>
          ${(p.owner || {}).note ? `<div class="small" style="margin-top:2px">📝 ${esc(p.owner.note)}</div>` : ""}
          ${(() => { const now = new Date().toISOString(), up = ((H.cal || {}).events || []).filter(e => e.slug === p.slug && (e.end || e.start) >= now).sort((a, b) => a.start < b.start ? -1 : 1)[0];
            return up ? `<div class="small" style="margin-top:4px">📅 ${esc(up.summary)} <span class="pill g">${esc(new Date(up.start).toLocaleString([], {dateStyle: "medium", timeStyle: "short"}))}</span>${up.meet ? ` <a href="${esc(up.meet)}" target="_blank" rel="noopener">Meet</a>` : ""}</div>` : ""; })()}
          ${(() => { const a = ((H.apps || {}).rows || []).find(x => x.slug === p.slug); return a ? `<div class="small" style="margin-top:4px">${a.status ? `<span class="pill">${esc(a.status)}</span> ` : ""}${a.program ? esc(a.program) + " " : ""}${a.deadline ? `<span class="pill y">截止 ${esc(a.deadline)}</span> ` : ""}${a.meeting ? `<span class="pill g">會議 ${esc(a.meeting.slice(0, 16).replace("T", " "))}</span>` : ""}</div>` : ""; })()}</div>
        ${has ? `<span class="pill g">已定案｜第 ${(H.docs[key].versions.slice(-1)[0] || {}).n} 版</span>` : (pr.versions || []).length ? `<span class="pill y">AI 草稿 ${pr.versions.length} 版</span>` : `<span class="pill">還沒有</span>`}</div></summary>
      <div class="pc-body" data-doc-root>${has ? "" : drafts ? `<div class="small muted">AI 依她的方向與經費擬的草稿（<a href="professor.html?p=${encodeURIComponent(p.slug)}&v=proposal">到她的頁面看全文</a>）：</div>${drafts}` : ""}<div data-doc-slot="${esc(key)}"></div></div></details>`;
  }).join("");
  el.querySelectorAll("[data-doc-slot]").forEach(slot => renderDoc(slot.dataset.docSlot, slot));
}

/* ===== 本人的文件：上傳就顯示、每段 AI 編修、版本 ===== */
const DOC_NAMES = {proposal: ["Research Proposal", "研究計畫書"], ps: ["Personal Statement", "個人陳述"], sop: ["Statement of Purpose", "研究目的陳述"]};
const ME_ROOT = () => OFFLINE_HOME ? "_me/" : "../runs/_me/";
const DOC_VIEW = {};  // key → 正在看的版本號
function lrHTML(zh, en){ return `<div class="lr"><div class="en" lang="en">${esc(en || "")}</div><div class="zh">${zh ? esc(zh) : '<span class="muted">（翻譯中／尚無中文）</span>'}</div></div>`; }
const DOC_CUR = {};  // key → 正在顯示的那一版內容（本人編輯時拿原文）
function docTextBlocks(doc){
  return (doc.sections ? doc.sections.flatMap(x => x.blocks || []) : doc.blocks || []).filter(b => ["p", "h2", "h3", "note"].includes(b.type));
}
function docBlocksHTML(doc, editable){
  /* 依顯示順序編號可編修的段落（跟 scripts/pipeline/mydocs.py 的 blocks_of 同順序）；計畫書有章節、圖、表 */
  let k = 0;
  const editBtn = () => editable ? `${ibtn("edit", "編輯這段 Edit", `data-doc-op="edit" data-b="${k}"`, "btn-sm")}
    ${ibtn("plus", "下面加一段 Add below", `data-doc-op="insert_after" data-b="${k}"`, "btn-sm")}
    ${ibtn("trash", "刪除這段 Delete", `data-doc-op="delete" data-b="${k}"`, "btn-sm danger")}
    ${ibtn("sparkles", "AI 編修這段 AI edit", `data-doc-edit="${k}"`, "btn-sm btn-green")}` : "";
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
  const ORIGIN = {upload: "上傳", "ai-edit": "AI 編修", edit: "手動編輯", delete: "刪段落", insert: "加段落"};
  el.innerHTML = `<div class="doc-bar">
      <div class="row"><label class="small" for="ver-${esc(key)}">版本</label><select id="ver-${esc(key)}" data-doc-ver="${esc(key)}">${[...vs].reverse().map(x =>
        `<option value="${x.n}" ${x.n === cur ? "selected" : ""}>第 ${x.n} 版｜${esc(ORIGIN[x.origin] || x.origin)}｜${esc((x.created || "").slice(0, 10))}${x.note ? "｜" + esc(x.note) : ""}</option>`).join("")}</select>
        ${cur !== latest ? '<span class="pill y">舊版本（只能看）</span>' : '<span class="pill g">最新版</span>'}</div>
      <div class="row">${needZh && app ? `${ibtn("translate", "翻成中文 Translate", `data-doc-translate="${esc(key)}" data-v="${cur}"`)}` : ""}${upload}</div></div>
    ${v.base ? `<div class="small muted" style="margin:8px 0">這一版是從第 ${v.base} 版${v.note ? "：" + esc(v.note) : ""}。</div>` : ""}
    <div class="small" data-doc-msg></div>
    <h3 style="margin:14px 0 6px">${lrHTML(doc.title_zh, doc.title || nameEn)}</h3>
    <div class="doc-body" data-doc-key="${esc(key)}" data-v="${cur}">${docBlocksHTML(doc, app && cur === latest)}</div>`;
  DOC_CUR[key] = doc;
  if (v.base) (v.changed || []).forEach(i => el.querySelector(`.docb[data-block="${i}"]`)?.classList.add("changed"));
}
function renderStatement(kind){
  const el = body(kind);
  if (!el) return;
  if (kind === "sop") return renderSop(el);
  renderDoc(kind, el);
}
function renderSop(el){
  /* Statement of Purpose：一個學校的一個系所一份（本人 2026-10-26），依申請目標的學校 → 系所列出 */
  const schools = (H.targets || {}).schools || [];
  if (!schools.length){ el.innerHTML = `<div class="empty">還沒有申請目標的學校系所。到「申請目標」按右上角的學校 icon 新增，這裡就會出現每個系所一份 SOP。</div>`; return; }
  el.innerHTML = schools.map(sc => `<section class="school" style="margin-bottom:16px"><h3 style="margin:6px 0 4px">🏛 ${esc(sc.name)}</h3>
    ${sc.departments.map(d => { const key = `sop--${d.id}`, info = (H.docs || {})[key], n = info ? (info.versions.slice(-1)[0] || {}).n : null;
      return `<details class="profcard" ${info ? "open" : ""}><summary><div class="pc-head"><div><strong class="pc-name">${esc(d.name)}</strong></div>
          ${info ? `<span class="pill g" style="flex:none;white-space:nowrap">第 ${n} 版</span>` : `<span class="pill" style="flex:none;white-space:nowrap">還沒有</span>`}</div></summary>
        <div class="pc-body" data-doc-root><div data-doc-slot="${esc(key)}"></div></div></details>`; }).join("")}</section>`).join("");
  el.querySelectorAll("[data-doc-slot]").forEach(slot => renderDoc(slot.dataset.docSlot, slot));
}
document.addEventListener("change", async ev => {
  const t = ev.target;
  if (t.matches("[data-doc-ver]")){ DOC_VIEW[t.dataset.docVer] = +t.value; renderDoc(t.dataset.docVer, t.closest("[data-doc-slot]") || t.closest("section .body")); return; }
  if (t.matches("[data-doc-upload]") && t.files.length){
    const key = t.dataset.docUpload, cut = key.indexOf("--"), kind = cut < 0 ? key : key.slice(0, cut), slug = cut < 0 ? "" : key.slice(cut + 2);  // 系所 id 本身可能含 --
    const f = t.files[0], ext = f.name.split(".").pop().toLowerCase();
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
  const op = ev.target.closest("[data-doc-op]");
  if (op){  // 本人自己改：編輯、刪除、下面加一段 → 存成新版本
    const box = op.closest(".docb"), bodyEl = op.closest(".doc-body"), key = bodyEl.dataset.docKey, v = +bodyEl.dataset.v, b = +op.dataset.b;
    if (op.dataset.docOp === "delete"){
      if (!confirm(`刪掉第 ${b + 1} 段？會存成新版本，舊版還在。`)) return;
      try { await API("doc-change", {key, version: v, op: "delete", block: b}); location.reload(); } catch (e) { alert(e.message); }
      return;
    }
    if (box.querySelector(".doc-form")) return;
    const cur = op.dataset.docOp === "edit" ? docTextBlocks(DOC_CUR[key])[b] || {} : {};
    box.insertAdjacentHTML("beforeend", `<form class="doc-form match-form" style="max-width:none;margin-top:8px">
      <label>English<textarea name="en" rows="4">${esc(cur.en || "")}</textarea></label>
      <label>中文<textarea name="zh" rows="3">${esc(cur.zh || "")}</textarea></label>
      <div class="row"><button class="btn btn-green btn-sm" type="submit">${T("存成新版本", "Save as new version")}</button><button class="btn btn-sm" type="button" onclick="this.closest('.doc-form').remove()">${T("取消", "Cancel")}</button></div></form>`);
    const f = box.querySelector(".doc-form");
    f.en.focus();
    f.onsubmit = async e => { e.preventDefault();
      try { await API("doc-change", {key, version: v, op: op.dataset.docOp, block: b, en: f.en.value, zh: f.zh.value}); location.reload(); } catch (err) { alert(err.message); } };
    return;
  }
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

function renderExpEdit(){
  /* 工作經歷與學歷：新增、修改、刪除（每條條列一行一點；技能用逗號分開） */
  const m = H.me || {};
  const xrow = x => `<fieldset class="exp-row"><legend><select name="kind"><option value="professional" ${x.kind !== "research" ? "selected" : ""}>工作</option><option value="research" ${x.kind === "research" ? "selected" : ""}>研究</option></select>
      ${ibtn("trash", "刪掉這段 Delete", "data-row-del", "btn-sm danger")}</legend>
    <div class="row"><label style="flex:1">職稱（English）<input name="role" value="${esc(x.role || "")}"></label><label style="flex:1">職稱（中文）<input name="role_zh" value="${esc(x.role_zh || "")}"></label></div>
    <div class="row"><label style="flex:2">單位<input name="org" value="${esc(x.org || "")}"></label><label style="flex:1">地點<input name="place" value="${esc(x.place || "")}"></label><label style="flex:1">期間<input name="dates" value="${esc(x.dates || "")}" placeholder="Feb 2025 – Present"></label></div>
    <label>做了什麼（English，一行一點）<textarea name="b_en" rows="4">${esc((x.bullets || []).map(b => b.en || "").join("\n"))}</textarea></label>
    <label>做了什麼（中文，一行一點，跟上面對齊）<textarea name="b_zh" rows="3">${esc((x.bullets || []).map(b => b.zh || "").join("\n"))}</textarea></label>
    <label>Skills（逗號分開）<input name="skills" value="${esc((x.skills || []).join(", "))}"></label></fieldset>`;
  const erow = e => `<div class="row edu-row"><input name="degree" value="${esc(e.degree || "")}" placeholder="學位" style="flex:1"><input name="school" value="${esc(e.school || "")}" placeholder="學校" style="flex:2">
    <input name="years" value="${esc(e.years || "")}" placeholder="2018–2020" style="width:8em">${ibtn("trash", "刪掉 Delete", "data-row-del", "btn-sm danger")}</div>`;
  body("capabilities").innerHTML = `<form id="exp-form" class="match-form" style="max-width:none">
    <h3 class="label">${T("工作經歷", "Experience")}</h3><div id="exp-list">${(m.experience || []).map(xrow).join("")}</div>
    <button type="button" class="btn btn-sm" id="exp-add">＋ 新增一段經歷</button>
    <h3 class="label">${T("學歷", "Education")}</h3><div id="edu-list">${(m.education || []).map(erow).join("")}</div>
    <button type="button" class="btn btn-sm" id="edu-add">＋ 新增學歷</button>
    <div class="row" style="margin-top:12px"><button class="btn btn-green" type="submit">儲存</button><button class="btn" type="button" id="exp-cancel">取消</button><span class="small" id="exp-msg"></span></div></form>`;
  const f = document.getElementById("exp-form");
  f.addEventListener("click", ev => { if (ev.target.closest("[data-row-del]")) (ev.target.closest(".exp-row") || ev.target.closest(".edu-row")).remove(); });
  document.getElementById("exp-add").onclick = () => document.getElementById("exp-list").insertAdjacentHTML("beforeend", xrow({}));
  document.getElementById("edu-add").onclick = () => document.getElementById("edu-list").insertAdjacentHTML("beforeend", erow({}));
  document.getElementById("exp-cancel").onclick = () => renderCaps();
  f.onsubmit = async ev => {
    ev.preventDefault();
    const val = (el, n) => el.querySelector(`[name="${n}"]`).value.trim();
    const experience = [...f.querySelectorAll(".exp-row")].map(r => {
      const en = val(r, "b_en").split("\n").map(x => x.trim()), zh = val(r, "b_zh").split("\n").map(x => x.trim());
      const old = (m.experience || []).find(x => x.org === val(r, "org") && x.role === val(r, "role")) || {};
      const skills = val(r, "skills").split(",").map(x => x.trim()).filter(Boolean);
      return {kind: val(r, "kind"), role: val(r, "role"), role_zh: val(r, "role_zh"), org: val(r, "org"), place: val(r, "place"), dates: val(r, "dates"),
              bullets: en.map((e, i) => ({en: e, zh: zh[i] || ""})).filter(b => b.en || b.zh), skills,
              skills_zh: JSON.stringify(skills) === JSON.stringify(old.skills || []) ? old.skills_zh || [] : []};
    });
    const education = [...f.querySelectorAll(".edu-row")].map(r => ({degree: val(r, "degree"), school: val(r, "school"), years: val(r, "years")})).filter(e => e.degree || e.school);
    try { await API("me-update", {experience, education}); document.getElementById("exp-msg").textContent = "已儲存。"; setTimeout(() => location.reload(), 600); }
    catch (e) { document.getElementById("exp-msg").textContent = "儲存失敗：" + e.message; }
  };
}

function renderCaps(){
  /* 工作經歷（本人 2026-10-26：取代「我能做到的事」）：每段經歷條列，最後一行 Skills */
  const xs = (H.me || {}).experience || [];

  const group = (k, label) => {
    const list = xs.filter(x => x.kind === k);
    return list.length ? `<h3 class="label">${label}</h3>${list.map(x => `<div class="exp">
      <div class="exp-head"><div><strong>${bi(x.role_zh, x.role)}</strong><div class="small">${esc(x.org)}${x.place ? "｜" + esc(x.place) : ""}</div></div><span class="small muted">${esc(x.dates || "")}</span></div>
      <ul class="bullets">${(x.bullets || []).map(b => `<li>${bi(b.zh, b.en, "div")}</li>`).join("")}</ul>
      ${(x.skills || []).length ? `<div class="small skills"><span class="sk-ic" aria-hidden="true">⚙</span><span class="sk-l">Skills:</span> ${x.skills.map((sk, i) => `<span class="pill">${bi((x.skills_zh || [])[i], sk)}</span>`).join(" ")}</div>` : ""}</div>`).join("")}` : "";
  };
  if (window.APP_REMATCH && !document.getElementById("exp-edit-wrap")){
    const h = document.querySelector("#capabilities h2");
    h?.insertAdjacentHTML("afterend", `<div id="exp-edit-wrap" style="text-align:right;margin:-34px 0 8px"><button class="btn btn-sm" id="exp-edit">${T("編輯工作經歷與學歷", "Edit experience & education")}</button></div>`);
    document.getElementById("exp-edit").onclick = renderExpEdit;
  }
  body("capabilities").innerHTML = xs.length ? group("professional", T("工作", "Professional")) + group("research", T("研究", "Research"))
    : `<div class="empty">${T("還沒有工作經歷。", "No experience yet.")}</div>`;
}

const FIT = {strong: ["g", "強相關"], partial: ["y", "部分相關"], none: ["", "沒有相關"]};
function kpis(p, middle){
  const c = p.counts || {};
  return `<div class="kpis">
    <div class="kpi"><div class="n">${c.works ?? "–"}</div><div class="l">篇文章（2022–2026）</div></div>${middle}
    <div class="kpi"><div class="n">${c.grants_pi ?? "–"}</div><div class="l">個主持人計畫</div></div>
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
/* 查詢教授：依你的研究興趣找近幾年主導相關研究的人（scripts/discover.py），可以篩選、點開看論文，滿意才加入 */
const DF = {funded: false, min_led: 2, min_h: 10, recent: true, country: "", qs: 0, us: 0, full: false, lab: false};
const FUND = {full: ["g", "全額資助"], partial: ["y", "部分資助"], none: ["r", "自費"], unknown: ["", "資助不明"]};
/* 全額資助看教授本人掛名的學程；沒查到學程才看學校層級（同 pipeline/discover.py best_funding） */
const bestFunding = c => (c.programs || []).length ? ["full", "partial", "none", "unknown"].find(v => c.programs.some(p => (p.funding || {}).value === v)) : c.phd_funding;
let DISC = null;
function progDialog(p){
  /* 查詢教授的博士學程：點學程名稱跳出詳細資訊（學費、資助、要繳文件、截止日，各附出處） */
  const a = (u, t) => u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${t}</a>` : "";
  const f = p.funding || {}, [k, t] = FUND[f.value] || FUND.unknown, dept = p.basis === "department";
  const row = (n, v) => v ? `<dt><strong>${n}</strong></dt><dd style="margin:0 0 6px">${v}</dd>` : "";
  let d = document.getElementById("dprog-dialog");
  if (!d){ d = document.createElement("dialog"); d.id = "dprog-dialog"; d.style.cssText = "max-width:640px;width:calc(100% - 32px);border:1px solid #ddd;border-radius:12px;padding:20px";
    d.addEventListener("click", ev => { if (ev.target === d) d.close(); }); document.body.appendChild(d); }
  d.innerHTML = `<div class="row" style="justify-content:space-between;align-items:flex-start;flex-wrap:nowrap;gap:12px"><h3 style="margin:0">${esc(p.name)}</h3>
      ${ibtn("x", "關閉 Close", `onclick="this.closest('dialog').close()"`, "btn-sm")}</div>
    <div style="margin:8px 0"><span class="pill ${dept ? "y" : "g"}">${dept ? "系所的博士班（教授本人沒掛名）" : "教授本人掛名"}</span> <span class="pill ${k}">${t}${f.years ? `・${f.years} 年` : ""}</span></div>
    <dl class="small" style="margin:0">${row("透過", p.via && esc(p.via))}${row("入學", p.intake && esc(p.intake))}${row("修業年限", p.duration && esc(p.duration))}
      ${row("學費", p.tuition && p.tuition.text && `${esc(p.tuition.text)} ${a(p.tuition.src, "出處")}`)}
      ${row("資助", [f.stipend && esc(f.stipend), f.note && esc(f.note), a(f.src, "出處")].filter(Boolean).join(" "))}
      ${row("要繳的文件與資格", (p.requirements || []).length && `<ul style="margin:0;padding-left:18px">${p.requirements.map(x => `<li>${esc(x)}</li>`).join("")}</ul>${a(p.requirements_src, "出處")}`)}
      ${row("截止日", p.deadline && esc(p.deadline))}</dl>
    <div class="row small" style="margin-top:10px">${a(p.url || p.src, "學程頁")}${!dept ? a(p.member_src, "教員名單") : ""}</div>`;
  d.showModal();
}
document.addEventListener("click", ev => { const b = ev.target.closest("[data-dprog]"); if (!b) return;
  const [cid, pi] = b.dataset.dprog.split(":"); const c = ((DISC || {}).candidates || []).find(x => x.id === cid); if (c) progDialog(c.programs[+pi]); });
async function loadDiscover(){ try { DISC = await getJSON("../runs/_discover/latest.json"); } catch (e) { DISC = null; } return DISC; }
function discFilter(cs){
  const y = new Date().getFullYear() - 1;
  const within = (r, mx) => !mx || (r != null && r <= mx);  // 跟 scripts/pipeline/discover.py 的 apply_filters 同一套
  return cs.filter(c => (!DF.funded || (c.funders || []).length) && (c.n_led || 0) >= DF.min_led && (c.h_index || 0) >= DF.min_h
    && (!DF.recent || (c.last_year || 0) >= y) && (!DF.country || c.country === DF.country)
    && within(c.qs_rank, DF.qs) && within(c.usnews_rank, DF.us) && (!DF.full || bestFunding(c) === "full") && (!DF.lab || c.lab_url));
}
async function renderDiscover(){
  const el = document.getElementById("disc-panel");
  if (!DISC) await loadDiscover();
  const cs = (DISC || {}).candidates || [], countries = [...new Set(cs.map(c => c.country).filter(Boolean))].sort();
  const list = discFilter(cs);
  el.innerHTML = `<div class="row" style="justify-content:space-between">
      <div class="small muted">${DISC ? `${esc((DISC.created || "").slice(0, 10))} 查的｜${DISC.since} 年起｜依你的 ${DISC.interests.length} 個研究興趣` : "還沒查過"}</div>
      <div class="row"><input type="text" id="disc-q" placeholder="另外加關鍵字（選填）" style="width:14em"><button class="btn btn-green btn-sm" id="disc-run">${DISC ? "重新查詢" : "開始查詢"}</button>
        ${DISC ? `<button class="btn btn-sm" id="disc-enrich" title="AI 上網查學校的 QS／US News 排名、每位教授本人掛名的博士學程與資助、實驗室網址；每個值附出處；已補過的不重查">${DISC.enriched ? "補新出現的人" : "補排名與學程"}</button>` : ""}</div></div>
    ${DISC && !DISC.enriched ? `<div class="small muted">排名、學程還沒補：按「補排名與學程」（AI 上網查，每個值附出處，約 5–15 分鐘）。</div>` : ""}
    <div class="row small" style="margin:10px 0">
      <label><input type="checkbox" id="df-funded" ${DF.funded ? "checked" : ""}> 有經費</label>
      <label>主導至少 <select id="df-led">${[1, 2, 3, 5].map(n => `<option ${n === DF.min_led ? "selected" : ""}>${n}</option>`).join("")}</select> 篇</label>
      <label>h-index ≥ <select id="df-h">${[0, 10, 20, 30].map(n => `<option ${n === DF.min_h ? "selected" : ""}>${n}</option>`).join("")}</select></label>
      <label><input type="checkbox" id="df-recent" ${DF.recent ? "checked" : ""}> 去年後還有發表</label>
      <label>國家 <select id="df-country"><option value="">全部</option>${countries.map(c => `<option ${c === DF.country ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></label>
      <label>QS <select id="df-qs">${[[0, "不限"], [50, "前 50"], [100, "前 100"], [200, "前 200"]].map(([v, l]) => `<option value="${v}" ${v === DF.qs ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label>US News <select id="df-us">${[[0, "不限"], [50, "前 50"], [100, "前 100"], [200, "前 200"]].map(([v, l]) => `<option value="${v}" ${v === DF.us ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label><input type="checkbox" id="df-full" ${DF.full ? "checked" : ""}> 全額資助（看他掛名的學程）</label>
      <label><input type="checkbox" id="df-lab" ${DF.lab ? "checked" : ""}> 有實驗室網址</label>
      <span class="muted">${list.length}／${cs.length} 位</span></div>
    <div class="small muted" style="margin-bottom:6px">「主導」＝最後作者或通訊作者，而且那篇的標題或摘要真的寫到你的興趣（不是只有主題標籤）。</div>
    <div id="disc-msg" class="small"></div>
    ${list.map(c => `<details class="profcard"><summary><div class="pc-head"><div><strong class="pc-name">${esc(c.name)}</strong>
        <div class="small muted">${esc(c.institution || "")}${c.country ? "｜" + esc(c.country) : ""}</div>
        <div class="small" style="margin-top:4px">主導 ${c.n_led} 篇 · h-index ${c.h_index ?? "–"} · 最近 ${c.last_year || "–"} ${(c.funders || []).length ? '<span class="pill g">有經費</span>' : '<span class="pill">沒列經費</span>'}</div>
        <div class="small" style="margin-top:4px">${c.qs_rank ? `<span class="pill">QS #${c.qs_rank}</span> ` : ""}${c.usnews_rank ? `<span class="pill">US News #${c.usnews_rank}</span> ` : ""}${bestFunding(c) ? `<span class="pill ${FUND[bestFunding(c)][0]}">${FUND[bestFunding(c)][1]}</span> ` : ""}${c.lab_url ? '<span class="pill">🔬 實驗室</span>' : ""}</div></div>
        <div class="row" style="gap:4px;justify-content:flex-end;max-width:45%">${c.interests.map(i => `<span class="pill">${esc(i)}</span>`).join("")}</div></div></summary>
      <div class="pc-body">
        <ol class="top5">${c.papers.slice(0, 6).map(p => `<li>${p.doi ? `<a href="${esc(p.doi)}" target="_blank" rel="noopener">${esc(p.title)}</a>` : esc(p.title)} <span class="small muted">${p.year}</span></li>`).join("")}</ol>
        ${(c.funders || []).length ? `<div class="small"><strong>經費：</strong>${c.funders.slice(0, 6).map(esc).join("、")}</div>` : ""}
        ${(c.programs || []).length ? `<div class="small"><strong>博士學程：</strong>${c.programs.map((p, pi) => { const f = p.funding || {}, [k, t] = FUND[f.value] || FUND.unknown;
            return `<div style="margin:2px 0 4px 8px"><button type="button" data-dprog="${esc(c.id)}:${pi}" style="all:unset;cursor:pointer;text-decoration:underline;font-weight:600">${esc(p.name)}</button>
              <span class="muted">｜${esc((p.via || (p.basis === "department" ? "所屬系所的博士班" : "本人掛名")).split(/[（(；;]/)[0].trim())}</span> <span class="pill ${k}">${t}</span></div>`; }).join("")}</div>`
          : c.programs ? `<div class="small muted">查過：他本人沒掛名、系所的博士班也查不到</div>` : ""}
        ${!(c.programs || []).length && c.funding_note ? `<div class="small"><strong>學校博士班資助（備用）：</strong>${esc(c.funding_note)} ${c.funding_src ? `<a href="${esc(c.funding_src)}" target="_blank" rel="noopener">出處</a>` : ""}</div>` : ""}
        ${c.qs_rank || c.usnews_rank ? `<div class="small"><strong>排名：</strong>${c.qs_rank ? `QS #${c.qs_rank} <a href="${esc(c.qs_src)}" target="_blank" rel="noopener">出處</a>` : ""} ${c.usnews_rank ? `US News #${c.usnews_rank} <a href="${esc(c.usnews_src)}" target="_blank" rel="noopener">出處</a>` : ""}</div>` : ""}
        <div class="row" style="margin-top:10px">${c.lab_url ? `<a class="btn btn-sm" href="${esc(c.lab_url)}" target="_blank" rel="noopener">🔬 實驗室網站</a>` : ""}<a class="btn btn-sm" href="https://openalex.org/${esc(c.id)}" target="_blank" rel="noopener">OpenAlex</a>
          ${c.orcid ? `<a class="btn btn-sm" href="https://orcid.org/${esc(c.orcid)}" target="_blank" rel="noopener">ORCID</a>` : ""}
          <button class="btn btn-green btn-sm" data-disc-add="${esc(c.id)}">＋ 加入申請目標</button></div>
      </div></details>`).join("") || `<div class="empty">${cs.length ? "沒有符合篩選的，放寬條件看看。" : "按「開始查詢」。"}</div>`}`;
  const re = () => renderDiscover();
  el.querySelector("#df-funded").onchange = e => { DF.funded = e.target.checked; re(); };
  el.querySelector("#df-led").onchange = e => { DF.min_led = +e.target.value; re(); };
  el.querySelector("#df-h").onchange = e => { DF.min_h = +e.target.value; re(); };
  el.querySelector("#df-recent").onchange = e => { DF.recent = e.target.checked; re(); };
  el.querySelector("#df-country").onchange = e => { DF.country = e.target.value; re(); };
  el.querySelector("#df-qs").onchange = e => { DF.qs = +e.target.value; re(); };
  el.querySelector("#df-us").onchange = e => { DF.us = +e.target.value; re(); };
  el.querySelector("#df-full").onchange = e => { DF.full = e.target.checked; re(); };
  el.querySelector("#df-lab").onchange = e => { DF.lab = e.target.checked; re(); };
  el.querySelector("#disc-enrich")?.addEventListener("click", async ev => {
    ev.target.disabled = true;
    try { await API("discover-enrich", {}); el.querySelector("#disc-msg").textContent = "已交給 AI 補資訊（右上角齒輪看進度），完成後重新整理。"; }
    catch (e) { alert(e.message); ev.target.disabled = false; }
  });
  el.querySelector("#disc-run").onclick = async ev => {
    ev.target.disabled = true;
    const before = (DISC || {}).created, msg = el.querySelector("#disc-msg");
    try {
      await API("discover", {query: el.querySelector("#disc-q").value});
      msg.textContent = "查詢中（OpenAlex，約 1–3 分鐘）…";
      for (let i = 0; i < 90; i++){ await new Promise(r => setTimeout(r, 3000)); await loadDiscover(); if (DISC && DISC.created !== before) break; }
      renderDiscover();
    } catch (e) { msg.textContent = "查詢失敗：" + e.message; ev.target.disabled = false; }
  };
  el.querySelectorAll("[data-disc-add]").forEach(b => b.onclick = async () => {
    const c = cs.find(x => x.id === b.dataset.discAdd);
    if (!confirm(`把 ${c.name}（${c.institution}）加入申請目標？Claude Code 會開始建她的教授檔案（約 10–30 分鐘）。`)) return;
    b.disabled = true;
    try { await API("new", {name: c.name, institution: c.institution, orcid: c.orcid || ""}); location.href = "settings.html"; }
    catch (e) { alert(e.message); b.disabled = false; }
  });
}

function renderProfs(ps){
  /* 目標教授：每位一張收合卡，只放重要資訊與「必讀前五篇」（跟你最相關的），其他點進教授頁看；右上角可依星星排序 */
  const el = body("professors");
  const head = document.querySelector("#professors h2");
  if (head && !document.getElementById("prof-tools")){
    head.insertAdjacentHTML("afterend", `<div id="prof-tools" class="tools">
        <select id="prof-sort" class="tool-select" aria-label="排序 Sort" title="排序 Sort">
        <option value="stars">★ 高→低</option><option value="stars-asc">★ 低→高</option><option value="name">A–Z</option></select>
        ${window.APP_REMATCH ? `<button class="btn btn-icon ghost" id="disc-btn" aria-expanded="false" aria-controls="disc-panel" title="查詢教授 Find professors" aria-label="查詢教授">${icon("search")}</button>
          <button class="btn btn-icon ghost" id="add-dept-btn" aria-expanded="false" aria-controls="add-dept-form" title="新增學校／系所 Add school" aria-label="新增學校／系所">${icon("school")}</button>
          <button class="btn btn-icon ghost" id="add-prof-btn" aria-expanded="false" aria-controls="add-prof-form" title="新增教授 Add professor" aria-label="新增教授">${icon("user-plus")}</button>` : ""}</div>
      ${window.APP_REMATCH ? `<form class="card" id="add-dept-form" hidden style="margin-bottom:12px">
        <p class="small muted" style="margin-top:0">新增後會在背景查這個系所的教員名單（每人附官方個人頁），查好後在系所底下展開「教員名單」，勾選想了解的教授再按建檔。</p>
        <label for="nd-school">學校（必填）</label><input type="text" id="nd-school" list="nd-schools" placeholder="例：University of California, San Francisco" required>
        <datalist id="nd-schools">${((H.targets || {}).schools || []).map(sc => `<option value="${esc(sc.name)}">`).join("")}</datalist>
        <label for="nd-dept">系所、學程或研究中心（必填）</label><input type="text" id="nd-dept" placeholder="例：Computational Precision Health PhD" required>
        <label for="nd-url">系所網址（選填，有的話查得比較準）</label><input type="url" id="nd-url" placeholder="https://…">
        <div class="row" style="margin-top:12px"><button class="btn btn-green" type="submit">新增並查教員名單</button><button class="btn" type="button" id="nd-cancel">取消</button></div>
      </form>` : ""}
      ${window.APP_REMATCH ? `<div class="card" id="disc-panel" hidden style="margin-bottom:12px"></div>` : ""}
      ${window.APP_REMATCH ? `<form class="card" id="add-prof-form" hidden style="margin-bottom:12px">
        <p class="small muted" style="margin-top:0">按「開始建檔」後，Claude Code 會在背景一路跑完：找身分、列文章、挑跟你最相關的必讀前五篇並完整解析、合作網絡、研究計畫、總覽（進度與預估時間在右上角「工作進度」）。有問題的地方事後在教授頁按按鈕處理，不用中途確認。</p>
        <label for="np-name">教授姓名（必填）</label><input type="text" id="np-name" placeholder="例：Liliana Laranjo" required>
        <label for="np-inst">學校／機構（必填）</label><input type="text" id="np-inst" placeholder="例：The University of Sydney（Westmead Applied Research Centre）" required>
        <label for="np-orcid">ORCID（選填）</label><input type="text" id="np-orcid" placeholder="0000-0000-0000-0000">
        <label for="np-dept">放進哪個學校系所（選填）</label><select id="np-dept">${deptOptions("")}</select>
        <div class="row" style="margin-top:12px"><button class="btn btn-green" type="submit">開始建檔</button><button class="btn" type="button" id="np-cancel">取消</button></div>
      </form>` : ""}`);
    { const bar = document.createElement("div"); bar.className = "sec-head"; head.before(bar); bar.append(head, document.getElementById("prof-tools")); }
    document.getElementById("prof-sort").onchange = ev => { PROF_SORT = ev.target.value; renderProfs(H.professors); };
    const form = document.getElementById("add-prof-form"), btn = document.getElementById("add-prof-btn");
    if (form){  // 點「＋ 新增教授」才打開填寫欄位
      const toggle = open => { form.hidden = !open; btn.setAttribute("aria-expanded", String(open)); if (open) form.querySelector("#np-name").focus(); };
      btn.onclick = () => toggle(form.hidden);
      form.querySelector("#np-cancel").onclick = () => toggle(false);
      form.onsubmit = async ev => {
        ev.preventDefault();
        const sub = form.querySelector('[type="submit"]'); sub.disabled = true;
        try { await API("new", {name: form.querySelector("#np-name").value.trim(), institution: form.querySelector("#np-inst").value.trim(),
                                orcid: form.querySelector("#np-orcid").value.trim(), dept: form.querySelector("#np-dept").value}); location.href = "pipeline.html"; }
        catch (e) { alert(e.message); sub.disabled = false; }
      };
      if (location.hash === "#new") toggle(true);
    }
    const dform = document.getElementById("add-dept-form"), dbtn2 = document.getElementById("add-dept-btn");
    if (dform){
      const tg = open => { dform.hidden = !open; dbtn2.setAttribute("aria-expanded", String(open)); if (open) dform.querySelector("#nd-school").focus(); };
      dbtn2.onclick = () => tg(dform.hidden);
      dform.querySelector("#nd-cancel").onclick = () => tg(false);
      dform.onsubmit = async ev => { ev.preventDefault(); const b = dform.querySelector('[type="submit"]'); b.disabled = true;
        try { const r = await API("target-add", {school: dform.querySelector("#nd-school").value.trim(), department: dform.querySelector("#nd-dept").value.trim(), url: dform.querySelector("#nd-url").value.trim()});
          alert(r.job && r.job.queued ? "已新增；查教員名單排隊中（目前有 3 個工作在跑）" : "已新增，正在背景查教員名單（右上角齒輪看進度，約 5–10 分鐘）"); location.reload(); }
        catch (e) { alert(e.message); b.disabled = false; } };
    }
    const dbtn = document.getElementById("disc-btn"), dpanel = document.getElementById("disc-panel");
    if (dbtn) dbtn.onclick = () => { dpanel.hidden = !dpanel.hidden; dbtn.setAttribute("aria-expanded", String(!dpanel.hidden)); if (!dpanel.hidden) renderDiscover(); };
  }
  const removed = ps.filter(p => (p.owner || {}).archived);
  ps = ps.filter(p => !(p.owner || {}).archived);
  const removedHTML = removed.length ? `<details class="item" style="margin-top:12px"><summary style="cursor:pointer;min-height:40px;display:flex;align-items:center">${T("已移除", "Removed")}（${removed.length}）</summary>
    ${removed.map(p => `<div class="row" style="justify-content:space-between;margin:6px 0"><span>${esc(p.name)} <span class="small muted">${esc(p.institution || "")}</span></span>
      ${window.APP_REMATCH ? `${ibtn("restore", "還原 Restore", `data-prof-restore="${esc(p.slug)}"`)}` : ""}</div>`).join("")}</details>` : "";
  if (!ps.length){ el.innerHTML = `<div class="empty">還沒有申請目標。按上面的「＋ 新增教授」，或跟 Claude 說「幫我建教授檔案：姓名，學校」。</div>` + removedHTML; return; }
  const score = p => (matchStars(p.recommend) || {score: -1}).score;
  const list = [...ps].sort(PROF_SORT === "name" ? (a, b) => (a.name || "").localeCompare(b.name || "")
    : PROF_SORT === "stars-asc" ? (a, b) => score(a) - score(b) : (a, b) => score(b) - score(a));
  const card = p => {
    const c = p.counts || {}, r = p.recommend;
    const strong = r ? r.targets.filter(t => t.fit === "strong").length : null, partial = r ? r.targets.filter(t => t.fit === "partial").length : null;
    const top5 = r ? (r.read_first || []).slice(0, 5) : (p.top_papers || []).slice(0, 5);
    const facts = [c.works != null && T(`${c.works} 篇`, `${c.works} papers`), c.grants_pi != null && T(`主持計畫 ${c.grants_pi}`, `${c.grants_pi} grants as PI`),
                   c.coauthors != null && T(`合作者 ${c.coauthors}`, `${c.coauthors} co-authors`), r && T(`強 ${strong}／部分 ${partial}`, `${strong} strong / ${partial} partial`)].filter(Boolean);
    return `<details class="profcard">
      <summary><div class="pc-head"><div><strong class="pc-name">${esc(p.name)}</strong><div class="small muted">${esc((p.owner || {}).institution || p.institution || "")}</div>
          ${(p.owner || {}).note ? `<div class="small" style="margin-top:2px">📝 ${esc(p.owner.note)}</div>` : ""}
          ${(() => { const now = new Date().toISOString(), up = ((H.cal || {}).events || []).filter(e => e.slug === p.slug && (e.end || e.start) >= now).sort((a, b) => a.start < b.start ? -1 : 1)[0];
            return up ? `<div class="small" style="margin-top:4px">📅 ${esc(up.summary)} <span class="pill g">${esc(new Date(up.start).toLocaleString([], {dateStyle: "medium", timeStyle: "short"}))}</span>${up.meet ? ` <a href="${esc(up.meet)}" target="_blank" rel="noopener">Meet</a>` : ""}</div>` : ""; })()}
          ${(() => { const a = ((H.apps || {}).rows || []).find(x => x.slug === p.slug); return a ? `<div class="small" style="margin-top:4px">${a.status ? `<span class="pill">${esc(a.status)}</span> ` : ""}${a.program ? esc(a.program) + " " : ""}${a.deadline ? `<span class="pill y">截止 ${esc(a.deadline)}</span> ` : ""}${a.meeting ? `<span class="pill g">會議 ${esc(a.meeting.slice(0, 16).replace("T", " "))}</span>` : ""}</div>` : ""; })()}
          <div class="small facts" style="margin-top:4px">${facts.join(" · ")}</div></div>${starsHTML(r)}</div></summary>
      <div class="pc-body">
        ${top5.length ? `<div class="small muted" style="margin-bottom:4px">${T("必讀前五篇", "Top 5 to read")}</div>
          <ol class="top5">${top5.map(w => `<li><a href="${esc(paperLink(p, w.id))}">${bi(w.title_zh, w.title)}</a> <span class="small muted">${esc(w.year || "")}</span></li>`).join("")}</ol>`
          : `<div class="small muted">${T("還沒比對。", "Not matched yet.")}</div>`}
        <div class="row" style="margin-top:10px">${p.built ? `<a class="btn btn-green" href="${esc(p.href)}">${T("教授頁", "Profile")} ${icon("arrow", 16)}</a>` : `<span class="pill y">詳細頁尚未產生</span>`}
          ${window.APP_REMATCH ? `${ibtn("match", r ? "重新比對 Re-match" : "依我的興趣比對 Match", `data-rematch="${esc(p.slug)}"`)}
            ${ibtn("edit", "編輯 Edit", `data-prof-edit="${esc(p.slug)}"`)}${ibtn("trash", "移除 Remove", `data-prof-remove="${esc(p.slug)}"`, "danger")}` : ""}</div>
        <form class="prof-edit" data-slug="${esc(p.slug)}" hidden style="margin-top:10px">
          ${window.APP_REMATCH ? `<label>${T("學校系所", "Department")}<select name="dept">${deptOptions(deptOf(p.slug))}</select></label>` : ""}
          <label>${T("顯示的機構", "Institution")}<input type="text" name="institution" value="${esc((p.owner || {}).institution || p.institution || "")}"></label>
          <label>Email<input type="email" name="email" value="${esc((p.owner || {}).email || "")}" placeholder="對 Google 日曆的會議用"></label>
          <label>${T("備註", "Note")}<input type="text" name="note" value="${esc((p.owner || {}).note || "")}" placeholder="例：11/3 面談、想申請 2027 入學"></label>
          <div class="row" style="margin-top:6px"><button class="btn btn-green btn-sm" type="submit">${T("儲存", "Save")}</button><button class="btn btn-sm" type="button" data-cancel>${T("取消", "Cancel")}</button></div></form>
      </div></details>`;
  };
  el.innerHTML = targetsHTML(list, card) + notionPendingHTML() + removedHTML;
}

document.addEventListener("input", ev => {
  const q = ev.target.closest("[data-fac-q]"); if (!q) return;
  const v = q.value.trim().toLowerCase();
  document.querySelectorAll(`[data-fac-list="${CSS.escape(q.dataset.facQ)}"] [data-fac-row]`).forEach(r => { r.style.display = !v || r.textContent.toLowerCase().includes(v) ? "" : "none"; });
});
document.addEventListener("click", async ev => {
  const b = ev.target.closest("[data-fac-build], [data-fac-refresh], [data-dept-remove]");
  if (!b) return;
  ev.preventDefault();
  try {
    if (b.dataset.facBuild){
      const names = [...document.querySelectorAll(`[data-fac="${CSS.escape(b.dataset.facBuild)}"]:checked`)].map(x => x.value);
      if (!names.length) return alert("先勾選教授");
      if (!confirm(`幫這 ${names.length} 位建教授檔案？${names.length > 3 ? "同時最多跑 3 位，其他會排隊自動開始。" : ""}\n${names.join("、")}`)) return;
      b.disabled = true;
      const r = await API("faculty-build", {dept: b.dataset.facBuild, names});
      alert(`已開始 ${r.started.length} 位${r.queued.length ? `、排隊 ${r.queued.length} 位` : ""}${r.existing.length ? `、已經有檔案 ${r.existing.length} 位（放進這個系所）` : ""}。進度在右上角齒輪。`);
      location.reload();
    } else if (b.dataset.facRefresh){
      b.disabled = true;
      const r = await API("faculty-lookup", {dept: b.dataset.facRefresh});
      alert(r.queued ? "查教員名單排隊中" : "正在背景查教員名單（約 5–10 分鐘）");
    } else if (b.dataset.deptRemove){
      if (!confirm("移除這個系所？裡面教授的檔案都會留著，只是改列在「還沒分學校系所」。")) return;
      await API("target-remove", {dept: b.dataset.deptRemove}); location.reload();
    }
  } catch (e) { alert(e.message); b.disabled = false; }
});
function facDialog(deptId){
  /* 教員名單彈出視窗：條列姓名、職稱、專長、研究興趣；勾選後建檔（同時最多 3 位，其他排隊） */
  let sc, d;
  for (const x of (H.targets || {}).schools || []) for (const y of x.departments) if (y.id === deptId){ sc = x; d = y; }
  if (!d) return;
  const f = d.faculty || {}, people = f.people || [], built = new Set((H.professors || []).map(p => p.slug));
  let dlg = document.getElementById("fac-dialog");
  if (!dlg){ dlg = document.createElement("dialog"); dlg.id = "fac-dialog";
    dlg.style.cssText = "max-width:880px;width:calc(100% - 32px);max-height:calc(100vh - 48px);border:1px solid #ddd;border-radius:12px;padding:0";
    dlg.addEventListener("click", ev => { if (ev.target === dlg) dlg.close(); }); document.body.appendChild(dlg); }
  const cell = v => v ? esc(Array.isArray(v) ? v.join("、") : v) : `<span class="muted">—</span>`;
  dlg.innerHTML = `<div style="display:flex;flex-direction:column;max-height:calc(100vh - 48px)">
    <div style="padding:16px 20px;border-bottom:1px solid #eee"><div class="row" style="justify-content:space-between;flex-wrap:nowrap;gap:12px">
      <div><strong style="font-size:1.1rem">${esc(d.name)}</strong><div class="small muted">${esc(sc.name)}｜${T("教員", "Faculty")} ${people.length} ${T("位", "")}${f.src ? `｜<a href="${esc(f.src)}" target="_blank" rel="noopener">${T("名單出處", "source")}</a>` : ""}</div></div>
      <span class="row" style="gap:6px;flex:none">${ibtn("refresh", "重新查教員名單 Refresh", `data-fac-refresh="${esc(d.id)}"`)}${ibtn("x", "關閉 Close", `onclick="this.closest('dialog').close()"`)}</span></div>
      <input type="search" data-fac-q="${esc(d.id)}" placeholder="搜尋姓名、專長或興趣" style="width:100%;margin-top:10px"></div>
    <div style="overflow:auto;padding:4px 20px" data-fac-list="${esc(d.id)}">
      <table class="small" style="width:100%;border-collapse:collapse">
        <thead><tr style="text-align:left;position:sticky;top:0;background:#fff"><th style="width:32px"></th><th>${T("教授", "Name")}</th><th>${T("專長", "Expertise")}</th><th>${T("研究興趣", "Interests")}</th></tr></thead>
        <tbody>${people.map(x => { const has = built.has(slugOfName(x.name));
          return `<tr data-fac-row style="border-top:1px solid #f0f0f0;vertical-align:top">
            <td style="padding:8px 4px">${has ? `<span class="pill g" title="已建檔">✓</span>` : `<input type="checkbox" data-fac="${esc(d.id)}" value="${esc(x.name)}" aria-label="選 ${esc(x.name)}" style="width:18px;height:18px">`}</td>
            <td style="padding:8px 6px;min-width:150px">${x.profile_url ? `<a href="${esc(x.profile_url)}" target="_blank" rel="noopener"><strong>${esc(x.name)}</strong></a>` : `<strong>${esc(x.name)}</strong>`}<div class="muted">${esc(x.title || "")}</div></td>
            <td style="padding:8px 6px">${cell(x.expertise)}</td><td style="padding:8px 6px">${cell(x.interests || x.research)}</td></tr>`; }).join("")}</tbody></table></div>
    <div class="row" style="padding:12px 20px;border-top:1px solid #eee;justify-content:space-between">
      <span class="small muted" data-fac-count>${T("已勾 0 位", "0 selected")}</span>
      <button type="button" class="btn btn-green" data-fac-build="${esc(d.id)}">${T("詳細查詢勾選的教授", "Build selected")}</button></div></div>`;
  dlg.addEventListener("change", () => { const n = dlg.querySelectorAll("[data-fac]:checked").length; const c = dlg.querySelector("[data-fac-count]"); if (c) c.textContent = `已勾 ${n} 位${n > 3 ? "（同時最多跑 3 位，其他排隊）" : ""}`; });
  dlg.showModal();
}
document.addEventListener("click", ev => { const b = ev.target.closest("[data-fac-open]"); if (b) facDialog(b.dataset.facOpen); });
function deptOptions(sel){
  return `<option value="">${T("（不分系所）", "(none)")}</option>` + ((H.targets || {}).schools || []).map(sc => `<optgroup label="${esc(sc.name)}">${sc.departments.map(d =>
    `<option value="${esc(d.id)}" ${d.id === sel ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</optgroup>`).join("");
}
function deptOf(slug){
  for (const sc of (H.targets || {}).schools || []) for (const d of sc.departments) if ((d.members || []).includes(slug)) return d.id;
  return "";
}
const slugOfName = n => { const toks = (n || "").split(",")[0].replace(/\(.*?\)/g, " ").normalize("NFKD").replace(/[^\x00-\x7f]/g, "").split(/[^A-Za-z-]+/)
  .filter(x => x && !/^(dr|prof|professor|md|phd|ms|mph|rn)$/i.test(x));
  return toks.length > 1 ? `${toks.at(-1)}-${toks[0]}`.toLowerCase() : (toks[0] || "").toLowerCase(); };  // 同 pipeline/jobs.py slug_of
function targetsHTML(list, card){
  /* 目標學校 → 系所 → 教授；每個系所可以展開教員名單，勾選後建檔 */
  const t = H.targets || {schools: []}, by = Object.fromEntries(list.map(p => [p.slug, p])), used = new Set();
  const built = new Set((H.professors || []).map(p => p.slug));
  const dept = d => {
    const mem = new Set(d.members || []);
    const ps = list.filter(p => mem.has(p.slug)); ps.forEach(p => used.add(p.slug));  // 照右上角的排序（list 已排好），不是加入系所的順序
    const f = d.faculty, people = (f && f.people) || [];
    const fac = !window.APP_REMATCH ? "" : people.length
      ? `<div class="row small" style="margin:6px 0 10px;gap:8px"><button type="button" class="btn btn-sm" data-fac-open="${esc(d.id)}">${icon("users", 16)} ${T("教員名單", "Faculty")}（${people.length}）</button>
          <span class="muted">${T("打開勾選想詳細查詢的教授", "open to pick professors")}</span></div>`
      : `<div class="row small" style="margin:6px 0 10px"><span class="muted">${T("還沒有教員名單", "No faculty list yet")}</span>${ibtn("users", "查教員名單 Find faculty", `data-fac-refresh="${esc(d.id)}"`)}</div>`;
    return `<details class="dept" open style="margin:8px 0 14px 4px"><summary style="cursor:pointer;min-height:40px;display:flex;align-items:center;gap:8px">
        <strong>${esc(d.name)}</strong><span class="small muted" style="flex:none">${ps.length} 位</span><span style="margin-left:auto;display:flex;gap:2px;flex:none">${d.url ? ilink("external", "系所網站 Department site", esc(d.url), "ghost") : ""}
        ${window.APP_REMATCH ? ibtn("trash", "移除系所 Remove department", `data-dept-remove="${esc(d.id)}"`, "ghost") : ""}</span></summary>
      ${fac}${ps.map(card).join("") || `<div class="small muted" style="margin:4px 0 8px">${T("這個系所還沒有建檔的教授", "No professors yet")}</div>`}</details>`;
  };
  const schools = (t.schools || []).map(sc => `<section class="school" style="margin-bottom:18px"><h3 style="margin:6px 0 2px">🏛 ${esc(sc.name)}</h3>${sc.departments.map(dept).join("")}</section>`).join("");
  const rest = list.filter(p => !used.has(p.slug));
  return schools + (rest.length ? `<section class="school"><h3 style="margin:6px 0 2px">${T("還沒分學校系所", "Not in a department")}</h3>
    <div class="small muted" style="margin-bottom:6px">${T("在教授卡片按「編輯」選系所", "Use Edit to choose a department")}</div>${rest.map(card).join("")}</section>` : "");
}
function notionPendingHTML(){
  /* Notion 裡填了、但還沒建檔的教授：按「建檔」才開始 */
  const rows = ((H.apps || {}).rows || []).filter(r => !r.slug && r.name);
  if (!rows.length) return "";
  return `<details class="item" open style="margin-top:12px"><summary style="cursor:pointer;min-height:40px;display:flex;align-items:center">${T("Notion 裡還沒建檔", "In Notion, not built yet")}（${rows.length}）</summary>
    ${rows.map(r => `<div class="row" style="justify-content:space-between;margin:6px 0"><span><strong>${esc(r.name)}</strong> <span class="small muted">${esc(r.institution || "")}${r.program ? "｜" + esc(r.program) : ""}${r.deadline ? "｜截止 " + esc(r.deadline) : ""}</span></span>
      ${window.APP_REMATCH ? `<button class="btn btn-green btn-sm" data-notion-build="${esc(r.page_id)}">${T("建檔", "Build")}</button>` : ""}</div>`).join("")}</details>`;
}
document.addEventListener("click", async ev => {
  const b = ev.target.closest("[data-notion-build]");
  if (!b) return;
  const r = ((H.apps || {}).rows || []).find(x => x.page_id === b.dataset.notionBuild);
  if (!r.institution){ alert("Notion 那一列還沒填「學校」，填好再匯入。"); return; }
  if (!confirm(`幫 ${r.name}（${r.institution}）建教授檔案？Claude Code 會在背景一路跑完。`)) return;
  b.disabled = true;
  try { await API("new", {name: r.name, institution: r.institution, orcid: r.orcid || ""}); location.href = "settings.html"; } catch (e) { alert(e.message); b.disabled = false; }
});
document.addEventListener("click", async ev => {
  const ed = ev.target.closest("[data-prof-edit]"), rm = ev.target.closest("[data-prof-remove]"), rs = ev.target.closest("[data-prof-restore]"), cn = ev.target.closest(".prof-edit [data-cancel]");
  if (ed){ const f = document.querySelector(`.prof-edit[data-slug="${ed.dataset.profEdit}"]`); f.hidden = !f.hidden; return; }
  if (cn){ cn.closest(".prof-edit").hidden = true; return; }
  try {
    if (rm){ if (!confirm("移除這位教授？檔案都會留著，之後可以在「已移除」還原。")) return; await API("prof-remove", {slug: rm.dataset.profRemove}); location.reload(); }
    if (rs){ await API("prof-restore", {slug: rs.dataset.profRestore}); location.reload(); }
  } catch (e) { alert(e.message); }
});
document.addEventListener("submit", async ev => {
  const f = ev.target.closest(".prof-edit");
  if (!f) return;
  ev.preventDefault();
  try { await API("prof-update", {slug: f.dataset.slug, institution: f.institution.value, email: f.email.value, note: f.note.value});
        if (f.dept && f.dept.value !== deptOf(f.dataset.slug)) await API("prof-assign", {slug: f.dataset.slug, dept: f.dept.value});
        location.reload(); } catch (e) { alert(e.message); }
});

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
  return {slug: p.slug, href: `professor.html?p=${encodeURIComponent(p.slug)}`, built: true, name: d.professor.name, institution: ((d.basic || {}).position || {}).institution || d.professor.institution,  // ORCID 的機構乾淨，停 1 的機構可能夾註記
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
  const apps = await getJSON("../runs/_me/applications.json").catch(() => null);
  const targets = await getJSON("../runs/_me/targets.json").catch(() => ({schools: []}));  // 目標學校 → 系所 → 教授
  const cal = await getJSON("../runs/_me/calendar.json").catch(() => null);  // Google 日曆裡跟教授有關的會議  // Notion「博士申請追蹤」匯入的
  const profs = [];
  for (const p of list){
    const owner = await getJSON(`../runs/${p.slug}/owner.json`).catch(() => ({}));
    try { profs.push({...summarize(p, await getJSON("../runs/" + p.data), me), owner}); }
    catch (e) { profs.push({slug: p.slug, name: p.name, institution: p.institution, built: false, counts: {}, n_strong: 0, n_overlap_papers: 0, shared_terms: [], top_papers: [], top_grants: [], design_overlap: []}); }
  }
  return {me, professors: profs, docs, apps, cal, targets};
}

let OFFLINE_HOME = false;
const PAGES = [["index.html", T("簡介", "Profile")], ["professors.html", T("申請目標", "Applications")], ["proposals.html", "Research Proposal"], ["ps.html", "Personal Statement"], ["sop.html", "Statement of Purpose"]];
const MORE = [["settings.html", "設定與工作進度"]];
const PAGE_SECTIONS = {"index.html": ["me", "capabilities"], "me.html": ["me", "capabilities"], "professors.html": ["professors"], "proposals.html": ["proposal"],
                       "ps.html": ["ps"], "sop.html": ["sop"], "pipeline.html": ["pipeline", "settings"], "settings.html": ["pipeline", "settings"]};
function setupHomeViews(){
  /* 頁籤（參考 USyd 教授個人頁）：簡介｜申請目標｜Research Proposal｜Personal Statement｜Statement of Purpose；設定與工作進度在右上角齒輪。
     離線單檔版全部在一頁，頁籤變成頁內連結 */
  const tabs = document.getElementById("tabs");
  const here = location.pathname.split("/").pop() || "index.html";
  if (OFFLINE_HOME){
    tabs.innerHTML = [["me", T("簡介", "Profile")], ["professors", T("申請目標", "Applications")], ["proposal", "Research Proposal"], ["ps", "Personal Statement"], ["sop", "Statement of Purpose"]].map(([id, l]) => `<a href="#${id}">${l}</a>`).join("");
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
