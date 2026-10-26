/* 資料：應用程式從 runs/ 讀（me.json、professors.json、各教授 data.json），比對在瀏覽器裡算；離線單檔版內嵌在 #inline-data */
let H = null;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const bi = (zh, en, tag = "span") => (zh ? `<${tag} class="t-zh">${esc(zh)}</${tag}>` : "") + (tag === "span" && zh && en ? " " : "") + (en ? `<${tag} class="t-en" lang="en">${esc(en)}</${tag}>` : "");
const body = id => $(`#${id} .body`) || document.createElement("div");  // 這一頁沒有這一區就畫到看不見的地方
const has = id => !!document.getElementById(id);
const paperLink = (p, id) => OFFLINE_HOME ? `${p.href}#paper-${id}` : `paper.html?p=${encodeURIComponent(p.slug)}&id=${encodeURIComponent(id)}`;
const STATUS = {confirmed: ["g", "本人主持"], pending: ["y", "待確認"], acknowledged: ["", "論文致謝提及"], other: ["", "合作者主持"]};

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
    <h3 class="label">${T("研究興趣", "Research interests")}</h3>
    <ul class="bullets cols2">${(m.interests || []).map(i => `<li>${bi(i.zh, i.en, "div")}</li>`).join("")}</ul>
    <h3 class="label">${T("發表", "Publications")}</h3>
    <ul class="bullets">${(m.publications || []).map(p => `<li class="small">${esc(p.text)} ${p.doi ? `<a href="https://doi.org/${esc(p.doi)}" target="_blank" rel="noopener">DOI</a>` : ""}</li>`).join("")}</ul>
    <h3 class="label">${T("專案", "Projects")}</h3>
    <ul class="bullets">${(m.projects || []).map(p => `<li><a href="${esc(p.url)}" target="_blank" rel="noopener"><strong>${esc(p.name)}</strong></a><div class="small">${bi(p.zh, p.en, "div")}</div></li>`).join("")}</ul>`;
  const head = document.querySelector("#me h2");
  if (window.APP_REMATCH && head && !document.getElementById("me-edit")){
    head.insertAdjacentHTML("afterend", `<div id="me-edit-wrap" style="text-align:right;margin:-34px 0 8px"><button class="btn btn-sm" id="me-edit">編輯簡介與研究興趣</button></div>`);
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
    return `<details class="profcard" ${has ? "open" : ""}><summary><div class="pc-head"><div><strong class="pc-name">${esc(p.name)}</strong><div class="small muted">${esc((p.owner || {}).institution || p.institution || "")}</div>
          ${(p.owner || {}).note ? `<div class="small" style="margin-top:2px">📝 ${esc(p.owner.note)}</div>` : ""}</div>
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
const DOC_CUR = {};  // key → 正在顯示的那一版內容（本人編輯時拿原文）
function docTextBlocks(doc){
  return (doc.sections ? doc.sections.flatMap(x => x.blocks || []) : doc.blocks || []).filter(b => ["p", "h2", "h3", "note"].includes(b.type));
}
function docBlocksHTML(doc, editable){
  /* 依顯示順序編號可編修的段落（跟 scripts/pipeline/mydocs.py 的 blocks_of 同順序）；計畫書有章節、圖、表 */
  let k = 0;
  const editBtn = () => editable ? `<button class="btn btn-sm" data-doc-op="edit" data-b="${k}">${T("編輯", "Edit")}</button>
    <button class="btn btn-sm" data-doc-op="insert_after" data-b="${k}">${T("下面加一段", "Add below")}</button>
    <button class="btn btn-sm btn-red" data-doc-op="delete" data-b="${k}">${T("刪除", "Delete")}</button>
    <button class="btn btn-sm btn-green" data-doc-edit="${k}">AI 編修</button>` : "";
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
      <div class="row">${needZh && app ? `<button class="btn" data-doc-translate="${esc(key)}" data-v="${cur}">翻成中文</button>` : ""}${upload}</div></div>
    ${v.base ? `<div class="small muted" style="margin:8px 0">這一版是從第 ${v.base} 版${v.note ? "：" + esc(v.note) : ""}。</div>` : ""}
    <div class="small" data-doc-msg></div>
    <h3 style="margin:14px 0 6px">${lrHTML(doc.title_zh, doc.title || nameEn)}</h3>
    <div class="doc-body" data-doc-key="${esc(key)}" data-v="${cur}">${docBlocksHTML(doc, app && cur === latest)}</div>`;
  DOC_CUR[key] = doc;
  if (v.base) (v.changed || []).forEach(i => el.querySelector(`.docb[data-block="${i}"]`)?.classList.add("changed"));
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
      <button type="button" class="btn btn-sm btn-red" data-row-del>刪掉這段</button></legend>
    <div class="row"><label style="flex:1">職稱（English）<input name="role" value="${esc(x.role || "")}"></label><label style="flex:1">職稱（中文）<input name="role_zh" value="${esc(x.role_zh || "")}"></label></div>
    <div class="row"><label style="flex:2">單位<input name="org" value="${esc(x.org || "")}"></label><label style="flex:1">地點<input name="place" value="${esc(x.place || "")}"></label><label style="flex:1">期間<input name="dates" value="${esc(x.dates || "")}" placeholder="Feb 2025 – Present"></label></div>
    <label>做了什麼（English，一行一點）<textarea name="b_en" rows="4">${esc((x.bullets || []).map(b => b.en || "").join("\n"))}</textarea></label>
    <label>做了什麼（中文，一行一點，跟上面對齊）<textarea name="b_zh" rows="3">${esc((x.bullets || []).map(b => b.zh || "").join("\n"))}</textarea></label>
    <label>Skills（逗號分開）<input name="skills" value="${esc((x.skills || []).join(", "))}"></label></fieldset>`;
  const erow = e => `<div class="row edu-row"><input name="degree" value="${esc(e.degree || "")}" placeholder="學位" style="flex:1"><input name="school" value="${esc(e.school || "")}" placeholder="學校" style="flex:2">
    <input name="years" value="${esc(e.years || "")}" placeholder="2018–2020" style="width:8em"><button type="button" class="btn btn-sm btn-red" data-row-del>刪掉</button></div>`;
  body("capabilities").innerHTML = `<form id="exp-form" class="match-form" style="max-width:none">
    <h3 class="label">${T("工作經歷", "Experience")}</h3><div id="exp-list">${(m.experience || []).map(xrow).join("")}</div>
    <button type="button" class="btn btn-sm" id="exp-add">＋ 新增一段經歷</button>
    <h3 class="label">${T("學歷", "Education")}</h3><div id="edu-list">${(m.education || []).map(erow).join("")}</div>
    <button type="button" class="btn btn-sm" id="edu-add">＋ 新增學歷</button>
    <div class="row" style="margin-top:12px"><button class="btn btn-green" type="submit">儲存</button><button class="btn" type="button" id="exp-cancel">取消</button><span class="small" id="exp-msg"></span></div></form>`;
  const f = document.getElementById("exp-form");
  f.addEventListener("click", ev => { if (ev.target.matches("[data-row-del]")) (ev.target.closest(".exp-row") || ev.target.closest(".edu-row")).remove(); });
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
/* 查詢教授：依你的研究興趣找近幾年主導相關研究的人（scripts/discover.py），可以篩選、點開看論文，滿意才加入 */
const DF = {funded: false, min_led: 2, min_h: 10, recent: true, country: "", qs: 0, us: 0, full: false, lab: false};
const FUND = {full: ["g", "全額獎學金"], partial: ["y", "部分資助"], none: ["r", "自費"], unknown: ["", "資助不明"]};
let DISC = null;
async function loadDiscover(){ try { DISC = await getJSON("../runs/_discover/latest.json"); } catch (e) { DISC = null; } return DISC; }
function discFilter(cs){
  const y = new Date().getFullYear() - 1;
  const within = (r, mx) => !mx || (r != null && r <= mx);  // 跟 scripts/pipeline/discover.py 的 apply_filters 同一套
  return cs.filter(c => (!DF.funded || (c.funders || []).length) && (c.n_led || 0) >= DF.min_led && (c.h_index || 0) >= DF.min_h
    && (!DF.recent || (c.last_year || 0) >= y) && (!DF.country || c.country === DF.country)
    && within(c.qs_rank, DF.qs) && within(c.usnews_rank, DF.us) && (!DF.full || c.phd_funding === "full") && (!DF.lab || c.lab_url));
}
async function renderDiscover(){
  const el = document.getElementById("disc-panel");
  if (!DISC) await loadDiscover();
  const cs = (DISC || {}).candidates || [], countries = [...new Set(cs.map(c => c.country).filter(Boolean))].sort();
  const list = discFilter(cs);
  el.innerHTML = `<div class="row" style="justify-content:space-between">
      <div class="small muted">${DISC ? `${esc((DISC.created || "").slice(0, 10))} 查的｜${DISC.since} 年起｜依你的 ${DISC.interests.length} 個研究興趣` : "還沒查過"}</div>
      <div class="row"><input type="text" id="disc-q" placeholder="另外加關鍵字（選填）" style="width:14em"><button class="btn btn-green btn-sm" id="disc-run">${DISC ? "重新查詢" : "開始查詢"}</button>
        ${DISC ? `<button class="btn btn-sm" id="disc-enrich" title="AI 上網查每所學校的 QS／US News 排名、博士班是否全額資助，以及實驗室網址；每個值附出處">${DISC.enriched ? "重新補排名與獎學金" : "補排名與獎學金"}</button>` : ""}</div></div>
    ${DISC && !DISC.enriched ? `<div class="small muted">排名、獎學金還沒補：按「補排名與獎學金」（AI 上網查，每個值附出處，約 5–15 分鐘）。</div>` : ""}
    <div class="row small" style="margin:10px 0">
      <label><input type="checkbox" id="df-funded" ${DF.funded ? "checked" : ""}> 有經費</label>
      <label>主導至少 <select id="df-led">${[1, 2, 3, 5].map(n => `<option ${n === DF.min_led ? "selected" : ""}>${n}</option>`).join("")}</select> 篇</label>
      <label>h-index ≥ <select id="df-h">${[0, 10, 20, 30].map(n => `<option ${n === DF.min_h ? "selected" : ""}>${n}</option>`).join("")}</select></label>
      <label><input type="checkbox" id="df-recent" ${DF.recent ? "checked" : ""}> 去年後還有發表</label>
      <label>國家 <select id="df-country"><option value="">全部</option>${countries.map(c => `<option ${c === DF.country ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></label>
      <label>QS <select id="df-qs">${[[0, "不限"], [50, "前 50"], [100, "前 100"], [200, "前 200"]].map(([v, l]) => `<option value="${v}" ${v === DF.qs ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label>US News <select id="df-us">${[[0, "不限"], [50, "前 50"], [100, "前 100"], [200, "前 200"]].map(([v, l]) => `<option value="${v}" ${v === DF.us ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label><input type="checkbox" id="df-full" ${DF.full ? "checked" : ""}> 全額獎學金</label>
      <label><input type="checkbox" id="df-lab" ${DF.lab ? "checked" : ""}> 有實驗室網址</label>
      <span class="muted">${list.length}／${cs.length} 位</span></div>
    <div class="small muted" style="margin-bottom:6px">「主導」＝最後作者或通訊作者，而且那篇的標題或摘要真的寫到你的興趣（不是只有主題標籤）。</div>
    <div id="disc-msg" class="small"></div>
    ${list.map(c => `<details class="profcard"><summary><div class="pc-head"><div><strong class="pc-name">${esc(c.name)}</strong>
        <div class="small muted">${esc(c.institution || "")}${c.country ? "｜" + esc(c.country) : ""}</div>
        <div class="small" style="margin-top:4px">主導 ${c.n_led} 篇 · h-index ${c.h_index ?? "–"} · 最近 ${c.last_year || "–"} ${(c.funders || []).length ? '<span class="pill g">有經費</span>' : '<span class="pill">沒列經費</span>'}</div>
        <div class="small" style="margin-top:4px">${c.qs_rank ? `<span class="pill">QS #${c.qs_rank}</span> ` : ""}${c.usnews_rank ? `<span class="pill">US News #${c.usnews_rank}</span> ` : ""}${c.phd_funding ? `<span class="pill ${FUND[c.phd_funding][0]}">${FUND[c.phd_funding][1]}</span> ` : ""}${c.lab_url ? '<span class="pill">🔬 實驗室</span>' : ""}</div></div>
        <div class="row" style="gap:4px;justify-content:flex-end;max-width:45%">${c.interests.map(i => `<span class="pill">${esc(i)}</span>`).join("")}</div></div></summary>
      <div class="pc-body">
        <ol class="top5">${c.papers.slice(0, 6).map(p => `<li>${p.doi ? `<a href="${esc(p.doi)}" target="_blank" rel="noopener">${esc(p.title)}</a>` : esc(p.title)} <span class="small muted">${p.year}</span></li>`).join("")}</ol>
        ${(c.funders || []).length ? `<div class="small"><strong>經費：</strong>${c.funders.slice(0, 6).map(esc).join("、")}</div>` : ""}
        ${c.funding_note ? `<div class="small"><strong>博士班資助：</strong>${esc(c.funding_note)} ${c.funding_src ? `<a href="${esc(c.funding_src)}" target="_blank" rel="noopener">出處</a>` : ""}</div>` : ""}
        ${c.qs_rank || c.usnews_rank ? `<div class="small"><strong>排名：</strong>${c.qs_rank ? `QS #${c.qs_rank} <a href="${esc(c.qs_src)}" target="_blank" rel="noopener">出處</a>` : ""} ${c.usnews_rank ? `US News #${c.usnews_rank} <a href="${esc(c.usnews_src)}" target="_blank" rel="noopener">出處</a>` : ""}</div>` : ""}
        <div class="row" style="margin-top:10px">${c.lab_url ? `<a class="btn btn-sm" href="${esc(c.lab_url)}" target="_blank" rel="noopener">🔬 實驗室網站</a>` : ""}<a class="btn btn-sm" href="https://openalex.org/${esc(c.id)}" target="_blank" rel="noopener">OpenAlex</a>
          ${c.orcid ? `<a class="btn btn-sm" href="https://orcid.org/${esc(c.orcid)}" target="_blank" rel="noopener">ORCID</a>` : ""}
          <button class="btn btn-green btn-sm" data-disc-add="${esc(c.id)}">＋ 加入目標教授</button></div>
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
    if (!confirm(`把 ${c.name}（${c.institution}）加入目標教授？Claude Code 會開始建她的教授檔案（約 10–30 分鐘）。`)) return;
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
    head.insertAdjacentHTML("afterend", `<div class="row" id="prof-tools" style="justify-content:space-between;align-items:flex-end;margin:-4px 0 12px;flex-wrap:nowrap">
      <span></span>
      <span class="row" style="flex:none"><label class="small" for="prof-sort">${T("排序", "Sort")}</label><select id="prof-sort">
        <option value="stars">★ ↓</option><option value="stars-asc">★ ↑</option><option value="name">A–Z</option></select>
        ${window.APP_REMATCH ? `<button class="btn" id="disc-btn" aria-expanded="false" aria-controls="disc-panel">🔍 ${T("查詢教授", "Find professors")}</button>
          <button class="btn btn-green" id="add-prof-btn" aria-expanded="false" aria-controls="add-prof-form">＋ ${T("新增教授", "Add")}</button>` : ""}</span></div>
      ${window.APP_REMATCH ? `<div class="card" id="disc-panel" hidden style="margin-bottom:12px"></div>` : ""}
      ${window.APP_REMATCH ? `<form class="card" id="add-prof-form" hidden style="margin-bottom:12px">
        <p class="small muted" style="margin-top:0">按「開始建檔」後，Claude Code 會在背景找身分、列文章、找全文，跑到停 1 停下來請你確認（通常 10–30 分鐘，進度在右上角「工作進度」）。</p>
        <label for="np-name">教授姓名（必填）</label><input type="text" id="np-name" placeholder="例：Liliana Laranjo" required>
        <label for="np-inst">學校／機構（必填）</label><input type="text" id="np-inst" placeholder="例：The University of Sydney（Westmead Applied Research Centre）" required>
        <label for="np-orcid">ORCID（選填）</label><input type="text" id="np-orcid" placeholder="0000-0000-0000-0000">
        <div class="row" style="margin-top:12px"><button class="btn btn-green" type="submit">開始建檔</button><button class="btn" type="button" id="np-cancel">取消</button></div>
      </form>` : ""}`);
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
                                orcid: form.querySelector("#np-orcid").value.trim()}); location.href = "pipeline.html"; }
        catch (e) { alert(e.message); sub.disabled = false; }
      };
      if (location.hash === "#new") toggle(true);
    }
    const dbtn = document.getElementById("disc-btn"), dpanel = document.getElementById("disc-panel");
    if (dbtn) dbtn.onclick = () => { dpanel.hidden = !dpanel.hidden; dbtn.setAttribute("aria-expanded", String(!dpanel.hidden)); if (!dpanel.hidden) renderDiscover(); };
  }
  const removed = ps.filter(p => (p.owner || {}).archived);
  ps = ps.filter(p => !(p.owner || {}).archived);
  const removedHTML = removed.length ? `<details class="item" style="margin-top:12px"><summary style="cursor:pointer;min-height:40px;display:flex;align-items:center">${T("已移除", "Removed")}（${removed.length}）</summary>
    ${removed.map(p => `<div class="row" style="justify-content:space-between;margin:6px 0"><span>${esc(p.name)} <span class="small muted">${esc(p.institution || "")}</span></span>
      ${window.APP_REMATCH ? `<button class="btn btn-sm" data-prof-restore="${esc(p.slug)}">${T("還原", "Restore")}</button>` : ""}</div>`).join("")}</details>` : "";
  if (!ps.length){ el.innerHTML = `<div class="empty">還沒有目標教授。按上面的「＋ 新增教授」，或跟 Claude 說「幫我建教授檔案：姓名，學校」。</div>` + removedHTML; return; }
  const score = p => (matchStars(p.recommend) || {score: -1}).score;
  const list = [...ps].sort(PROF_SORT === "name" ? (a, b) => (a.name || "").localeCompare(b.name || "")
    : PROF_SORT === "stars-asc" ? (a, b) => score(a) - score(b) : (a, b) => score(b) - score(a));
  el.innerHTML = list.map(p => {
    const c = p.counts || {}, r = p.recommend;
    const strong = r ? r.targets.filter(t => t.fit === "strong").length : null, partial = r ? r.targets.filter(t => t.fit === "partial").length : null;
    const top5 = r ? (r.read_first || []).slice(0, 5) : (p.top_papers || []).slice(0, 5);
    const facts = [c.works != null && T(`${c.works} 篇`, `${c.works} papers`), c.grants_pi != null && T(`主持計畫 ${c.grants_pi}`, `${c.grants_pi} grants as PI`),
                   c.coauthors != null && T(`合作者 ${c.coauthors}`, `${c.coauthors} co-authors`), r && T(`強 ${strong}／部分 ${partial}`, `${strong} strong / ${partial} partial`)].filter(Boolean);
    return `<details class="profcard">
      <summary><div class="pc-head"><div><strong class="pc-name">${esc(p.name)}</strong><div class="small muted">${esc((p.owner || {}).institution || p.institution || "")}</div>
          ${(p.owner || {}).note ? `<div class="small" style="margin-top:2px">📝 ${esc(p.owner.note)}</div>` : ""}
          <div class="small facts" style="margin-top:4px">${facts.join(" · ")}</div></div>${starsHTML(r)}</div></summary>
      <div class="pc-body">
        ${top5.length ? `<div class="small muted" style="margin-bottom:4px">${T("必讀前五篇", "Top 5 to read")}</div>
          <ol class="top5">${top5.map(w => `<li><a href="${esc(paperLink(p, w.id))}">${bi(w.title_zh, w.title)}</a> <span class="small muted">${esc(w.year || "")}</span></li>`).join("")}</ol>`
          : `<div class="small muted">${T("還沒比對。", "Not matched yet.")}</div>`}
        <div class="row" style="margin-top:10px">${p.built ? `<a class="btn btn-green" href="${esc(p.href)}">${T("進入教授頁", "Open profile")} →</a>` : `<span class="pill y">詳細頁尚未產生</span>`}
          ${window.APP_REMATCH ? `<button class="btn" data-rematch="${esc(p.slug)}">${r ? "重新比對" : "依我的興趣比對"}</button>
            <button class="btn btn-sm" data-prof-edit="${esc(p.slug)}">${T("編輯", "Edit")}</button><button class="btn btn-sm btn-red" data-prof-remove="${esc(p.slug)}">${T("移除", "Remove")}</button>` : ""}</div>
        <form class="prof-edit" data-slug="${esc(p.slug)}" hidden style="margin-top:10px">
          <label>${T("顯示的機構", "Institution")}<input type="text" name="institution" value="${esc((p.owner || {}).institution || p.institution || "")}"></label>
          <label>${T("備註", "Note")}<input type="text" name="note" value="${esc((p.owner || {}).note || "")}" placeholder="例：11/3 面談、想申請 2027 入學"></label>
          <div class="row" style="margin-top:6px"><button class="btn btn-green btn-sm" type="submit">${T("儲存", "Save")}</button><button class="btn btn-sm" type="button" data-cancel>${T("取消", "Cancel")}</button></div></form>
      </div></details>`;
  }).join("") + removedHTML;
}
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
  try { await API("prof-update", {slug: f.dataset.slug, institution: f.institution.value, note: f.note.value}); location.reload(); } catch (e) { alert(e.message); }
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
  const profs = [];
  for (const p of list){
    const owner = await getJSON(`../runs/${p.slug}/owner.json`).catch(() => ({}));
    try { profs.push({...summarize(p, await getJSON("../runs/" + p.data), me), owner}); }
    catch (e) { profs.push({slug: p.slug, name: p.name, institution: p.institution, built: false, counts: {}, n_strong: 0, n_overlap_papers: 0, shared_terms: [], top_papers: [], top_grants: [], design_overlap: []}); }
  }
  return {me, professors: profs, docs};
}

let OFFLINE_HOME = false;
const PAGES = [["index.html", T("簡介", "Profile")], ["professors.html", T("目標教授", "Professors")], ["proposals.html", "Research Proposal"], ["ps.html", "Personal Statement"], ["sop.html", "Statement of Purpose"]];
const MORE = [["settings.html", "設定與工作進度"]];
const PAGE_SECTIONS = {"index.html": ["me", "capabilities"], "me.html": ["me", "capabilities"], "professors.html": ["professors"], "proposals.html": ["proposal"],
                       "ps.html": ["ps"], "sop.html": ["sop"], "pipeline.html": ["pipeline", "settings"], "settings.html": ["pipeline", "settings"]};
function setupHomeViews(){
  /* 頁籤（參考 USyd 教授個人頁）：簡介｜目標教授｜Research Proposal｜Personal Statement｜Statement of Purpose；設定與工作進度在右上角齒輪。
     離線單檔版全部在一頁，頁籤變成頁內連結 */
  const tabs = document.getElementById("tabs");
  const here = location.pathname.split("/").pop() || "index.html";
  if (OFFLINE_HOME){
    tabs.innerHTML = [["me", T("簡介", "Profile")], ["professors", T("目標教授", "Professors")], ["proposal", "Research Proposal"], ["ps", "Personal Statement"], ["sop", "Statement of Purpose"]].map(([id, l]) => `<a href="#${id}">${l}</a>`).join("");
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
