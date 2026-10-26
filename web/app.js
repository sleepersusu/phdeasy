/* 應用程式專用：建新教授、停點回覆、繼續流水線（由 Claude Code 在背景跑）。
   只有在應用程式裡打開（有 /api）才顯示；離線單檔版沒有這一區。 */
const API = (path, body) => fetch("/api/" + path, body === undefined ? {cache: "no-store"} :
  {method: "POST", headers: {"Content-Type": "application/json", "X-Phdeasy-App": "1"}, body: JSON.stringify(body)})
  .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || r.status); return j; });

const STAGE_ZH = {setup: "找文章與全文", stop1: "停在舊的停 1（按繼續跑）", ingest: "轉成文字", network: "合作與領域", grants: "研究計畫",
  cards: "文章解析卡", profile: "總覽撰寫", verify: "獨立驗收", stop2: "完成", halted: "熔斷：等你決定"};
const WAITING = new Set(["stop1", "halted"]);  // 不再停下等你（stop2＝完成）；只有舊批次的停 1 與熔斷要你按繼續
let pollTimer = null;

let wasSyncing = null;
function appBanner(st){
  /* 最上方的狀態列：第一次選雲端帳號、正在同步（同步完自動重新整理，資料才是最新的） */
  let el = document.getElementById("app-banner");
  if (!el){ el = document.createElement("div"); el.id = "app-banner"; el.className = "wrap"; document.querySelector("main").before(el); }
  if (wasSyncing && !st.syncing && !st.need_account){ wasSyncing = false; location.reload(); return; }  // 同步完：重新整理拿最新資料
  if (st.need_account){
    el.innerHTML = `<div class="card" style="margin-top:12px"><h3 style="margin-top:0">選擇放教授檔案的 Google 帳號</h3>
      <p class="small">這台電腦登入了多個 Google 雲端硬碟帳號。選一次就好，之後會記住。</p>
      <div class="row">${st.drive_choices.map(a => `<button class="btn btn-green" data-acct="${esc(a)}">${esc(a)}</button>`).join("")}</div></div>`;
    el.querySelectorAll("[data-acct]").forEach(b => b.onclick = async () => { b.disabled = true; try { await API("account", {account: b.dataset.acct}); } catch (e) { alert(e.message); b.disabled = false; } });
  } else if (st.syncing){
    el.innerHTML = `<div class="card" style="margin-top:12px" role="status"><span class="pill y">同步中</span> 正在從 Google 雲端硬碟拉最新的教授檔案，第一次會比較久…完成後會自動重新整理。</div>`;
  } else if (st.update && st.update.available){
    el.innerHTML = `<div class="card" style="margin-top:12px;border:2px solid var(--green)" role="status"><span class="pill g">有新版本</span>
      <strong>${esc(st.update.latest)}</strong>（你現在是 ${esc(st.update.current)}）
      ${st.update.release && st.update.release.page ? `<a href="${esc(st.update.release.page)}" target="_blank" rel="noopener" class="small">看更新內容</a>` : ""}
      <div class="row" style="margin-top:8px"><button class="btn btn-green" id="do-update" ${st.running ? "disabled" : ""}>更新並重開</button>
      <span class="small muted">${st.running ? "有工作在跑，跑完再更新" : "會先同步雲端，再自動安裝並重新打開；教授資料不會動。"}</span></div></div>`;
    el.querySelector("#do-update")?.addEventListener("click", async ev => {
      ev.currentTarget.disabled = true;
      try { await API("update", {}); location.href = "loading.html"; }  // 開機畫面會顯示下載百分比，裝好自動重開
      catch (e) { alert(e.message); ev.currentTarget.disabled = false; }
    });
  } else {
    el.innerHTML = st.blocked ? `<div class="card" style="margin-top:12px"><span class="pill y">只能看</span> 另一台電腦（${esc(st.blocked)}）正在用：已拉下雲端的資料給你看，但這台先不推上去、不跑流水線。那台關掉後重開這個程式。</div>` : "";
  }
  wasSyncing = st.syncing || st.need_account;
}

const dur = s => s < 90 ? "不到 2 分鐘" : s < 3600 ? `約 ${Math.round(s / 60)} 分鐘` : `約 ${Math.floor(s / 3600)} 小時 ${Math.round((s % 3600) / 60)} 分`;
function progressHTML(p){
  /* 進度條＋預估時間：看資料夾裡已產生的檔案算；速度是這次實際量到的，量不到用預設值，所以是「約」 */
  const cur = p.steps.find(x => x.key === p.current);
  return `<div style="margin:4px 0 12px">
    <div class="row" style="justify-content:space-between"><strong>${p.percent}%</strong><span class="small">預估還要 ${dur(p.eta_s)}${p.steps.at(-1).key === "verify" ? "（到全部跑完）" : ""}</span></div>
    <div role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${p.percent}" style="height:10px;background:#e5e7eb;border-radius:5px;overflow:hidden;margin-top:4px">
      <div style="height:100%;width:${p.percent}%;background:#15803d;transition:width .3s"></div></div>
    ${cur ? `<div class="small" style="margin-top:6px">目前：${esc(cur.label)}${cur.total > 1 ? ` ${cur.done}／${cur.total}` : ""}，這一步${dur(cur.eta_s)}</div>` : ""}
    <ol class="small muted" style="margin:6px 0 0;padding-left:20px">${p.steps.map(x => `<li>${x.key === p.current ? "▶ " : x.total && x.done >= x.total ? "✓ " : ""}${esc(x.label)}${x.total > 1 ? `（${x.done}／${x.total}）` : ""}</li>`).join("")}</ol>
  </div>`;
}

function jobsHTML(st, ready){
  /* 每個工作一列（最多同時 3 個在跑；每位教授一次一個）：狀態、進度條與預估時間、停止、回報、過程紀錄、回覆 */
  /* 舊版的程式（還沒重開）只給 job／running／log／progress：轉成一個工作的清單，畫面才看得到 */
  const jobs = st.jobs || (st.job ? [{...st.job, running: !!st.running, log: st.log || [], progress: st.progress || null}] : []);
  if (!jobs.length) return setRow("row-job", "目前的工作", '<span class="small muted">沒有在跑的工作</span>', '<div class="small muted">在「申請目標」新增教授、或在文件頁按 AI 編修，工作就會出現在這裡。可以同時跑 3 個（每位教授一次一個）。</div>');
  const nrun = jobs.filter(j => j.running).length, queue = st.queue || [];
  const row = job => {
    const running = job.running, id = esc(job.id);
    return setRow("row-job-" + job.id, running ? "▶ " + esc(job.title) : esc(job.title),
      `${running ? (job.progress ? `<span class="pill y">${job.progress.percent}%｜還要${dur(job.progress.eta_s)}</span>` : '<span class="pill y">執行中</span>') : job.status === "done" ? '<span class="pill g">跑完了</span>' : '<span class="pill r">中斷</span>'}`, `
      ${running && job.progress ? progressHTML(job.progress) : ""}
      <div class="row">${running ? `<button class="btn btn-red btn-sm" data-job-stop="${id}">停止</button>` : ""}
        ${job.cost_usd != null ? `<span class="small muted">本段用量約 US$${Number(job.cost_usd).toFixed(2)}</span>` : ""}</div>
      ${job.result && !running ? `<h3>Claude Code 的回報</h3><div class="card" style="white-space:pre-wrap">${esc(job.result)}</div>` : ""}
      <details ${running ? "open" : ""}><summary class="small" style="cursor:pointer;min-height:44px;display:flex;align-items:center">過程紀錄（${(job.log || []).length} 行）</summary>
        <div class="log" aria-live="polite" data-job-log="${id}">${esc((job.log || []).join("\n"))}</div></details>
      ${!running && job.session ? `<label for="reply-${id}">回覆 Claude Code（例：要它改什麼、再找哪篇）</label>
        <textarea id="reply-${id}" data-reply-box="${id}" placeholder="例：W123 不是他的文章，拿掉；或：重新找 W456 的全文。"></textarea>
        <div class="row" style="margin-top:8px"><button class="btn btn-green" data-reply-send="${id}" ${!ready ? "disabled" : ""}>送出並繼續</button>
        <span class="small muted">會接著同一個對話跑。</span></div>` : ""}`);
  };
  /* 分兩類：未完成（跑中、排隊、中斷）在上面，已完成收起來 */
  const todo = jobs.filter(j => j.running || j.status !== "done"), done = jobs.filter(j => !j.running && j.status === "done");
  return `<h3 style="margin:8px 0 4px">未完成 <span class="small muted">${todo.length + queue.length}｜${nrun ? `${nrun} 個在跑（最多同時 3 個）` : "沒有在跑的工作"}</span></h3>`
    + (todo.map(row).join("") || `<div class="small muted" style="margin:4px 0 8px">沒有未完成的工作</div>`)
    + queue.map(t => `<div class="small" style="margin:6px 0"><span class="pill">排隊中</span> ${esc(t)}</div>`).join("")
    + `<details style="margin-top:12px" ${OPEN_ROWS.has("done-jobs") ? "open" : ""} id="done-jobs" class="setrow"><summary style="cursor:pointer;min-height:40px;display:flex;align-items:center;gap:6px"><strong>已完成</strong><span class="small muted">${done.length}</span></summary>
      ${done.map(row).join("") || `<div class="small muted">還沒有完成的工作</div>`}</details>`;
}

async function pipelinePanel(){
  let st;
  try { st = await API("status"); } catch (e) { return; }  // 不是在應用程式裡：不顯示
  window.APP_REMATCH = true;  // 在應用程式裡：顯示只有應用程式才能用的按鈕（新增／查詢教授、編輯簡介、上傳文件、AI 編修）
  ["prof-tools", "add-prof-form", "disc-panel", "me-edit-wrap", "exp-edit-wrap"].forEach(id => document.getElementById(id)?.remove());  // 先前沒有這些按鈕的版本拿掉，重畫
  const redraw = (id, fn) => { if (document.querySelector(`#${id} .body`)) try { fn(); } catch (e) { console.error(e); } };  // 這一頁沒有的區塊不畫；一塊出錯不影響其他塊
  if (typeof H !== "undefined" && H){
    redraw("professors", () => renderProfs(H.professors));
    if (H.me){ redraw("me", () => renderMe(H.me)); redraw("capabilities", () => renderCaps()); }
    redraw("proposal", () => renderProposal());
    redraw("ps", () => renderStatement("ps"));
    redraw("sop", () => renderStatement("sop"));
  }
  document.getElementById("professors")?.addEventListener("click", async ev => {
    const b = ev.target.closest("[data-rematch]");
    if (!b) return;
    if (!confirm("請 Claude Code 依你目前的研究興趣與 CV 項目重新比對這位教授？約需 10–20 分鐘，進度在右上角齒輪「設定與工作進度」。")) return;
    b.disabled = true;
    try { await API("match", {slug: b.dataset.rematch}); location.href = "pipeline.html"; }
    catch (e) { alert(e.message); b.disabled = false; }
  });
  appBanner(st);
  renderPipeline(st);
  renderSettings(st);
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => { try { const s = await API("status"); appBanner(s); renderPipeline(s); renderSettings(s); } catch (e) {} }, wasSyncing ? 1500 : 3000);
}

function check(ok, good, bad){ return `<li>${ok ? `<span class="pill g">✓</span> ${good}` : `<span class="pill r">✗</span> ${bad}`}</li>`; }

let lastShape = "";
/* 設定與工作進度（本人 2026-10-26 合併成一頁）：每一項是一列，摘要在列上，點開才看到可以改的東西 */
const OPEN_ROWS = new Set(["row-job"]);
function setRow(id, title, status, inner){
  return `<details class="setrow" id="${id}" ${OPEN_ROWS.has(id) ? "open" : ""}><summary><span class="setrow-t">${title}</span><span class="setrow-s">${status}</span></summary><div class="setrow-b">${inner}</div></details>`;
}
document.addEventListener("toggle", ev => { const d = ev.target; if (d.classList && d.classList.contains("setrow")) d.open ? OPEN_ROWS.add(d.id) : OPEN_ROWS.delete(d.id); }, true);

function renderPipeline(st){
  const el = document.querySelector("#pipeline:not([hidden]) .body");
  if (!el) return;  // 這一頁沒有「建新教授」區
  /* 每 3 秒更新：只有紀錄變多時只換紀錄那一塊，不打斷你正在打字的欄位 */
  const shape = JSON.stringify({...st, log: undefined, progress: undefined, job: undefined,
    jobs: (st.jobs || (st.job ? [{...st.job, running: !!st.running, log: st.log}] : [])).map(j => ({...j, log: (j.log || []).length ? 1 : 0, progress: j.progress && [j.progress.percent, j.progress.current]}))});
  const logs = [...el.querySelectorAll("[data-job-log]")];
  if (shape === lastShape && logs.length){  // 只有紀錄或預估時間變：只換那幾塊，不打斷你正在打字的回覆
    for (const j of st.jobs || (st.job ? [{...st.job, log: st.log}] : [])){
      const lg = el.querySelector(`[data-job-log="${CSS.escape(j.id)}"]`);
      if (!lg) continue;
      const atBottom = lg.scrollTop + lg.clientHeight >= lg.scrollHeight - 20;
      lg.textContent = (j.log || []).join("\n");
      if (atBottom) lg.scrollTop = lg.scrollHeight;
    }
    return;
  }
  lastShape = shape;
  const keep = {replies: Object.fromEntries([...el.querySelectorAll("[data-reply-box]")].map(t => [t.dataset.replyBox, t.value])),
                focus: document.activeElement?.id};
  const ready = st.claude && st.uv;
  const running = st.jobs ? st.jobs.some(j => j.running) : !!st.running;
  const busy = new Set((st.jobs || (st.running && st.job ? [{...st.job, running: true}] : [])).filter(j => j.running).map(j => j.slug));
  const profs = st.professors || [];
  const tools = [st.claude, st.uv, st.drive].filter(Boolean).length;
  el.innerHTML =
    jobsHTML(st, ready) +
    setRow("row-profs", "各教授進度", `<span class="small muted">${profs.length} 位${profs.some(p => WAITING.has(p.stage)) ? "｜有等你確認的" : ""}</span>`,
      profs.length ? `<ul>${profs.map(p => `<li class="row" style="margin:6px 0"><strong>${esc(p.name || p.slug)}</strong>
        <span class="pill ${WAITING.has(p.stage) ? "y" : p.stage === "stop2" ? "g" : ""}">${esc(STAGE_ZH[p.stage] || p.stage)}</span>
        ${p.report ? `<a class="btn btn-green btn-sm" href="../runs/${esc(p.slug)}/${esc(p.report)}" target="_blank" rel="noopener">看${p.stage === "stop1" ? "停 1" : ""}報告</a>` : ""}
        ${p.stage !== "stop2" ? `<button class="btn btn-green btn-sm" data-continue="${esc(p.slug)}" ${!ready || busy.has(p.slug) ? "disabled" : ""}>${p.stage === "halted" ? "我看過了，繼續跑" : "繼續跑"}</button>` : ""}</li>`).join("")}</ul>`
        : `<div class="empty">還沒有教授。到「申請目標」按「＋ 新增教授」。</div>`) +
    setRow("row-tools", "這台電腦的工具", tools === 3 ? '<span class="pill g">✓ 齊全</span>' : `<span class="pill y">${3 - tools} 項沒裝</span>`, `<ul class="checks">
      ${check(st.claude, `Claude Code：${esc(st.claude)}`, `找不到 Claude Code。請先安裝並登入：<a href="https://claude.com/claude-code" target="_blank" rel="noopener">claude.com/claude-code</a>，裝好後重開這個程式。`)}
      ${check(st.uv, `uv：${esc(st.uv)}`, `找不到 uv（流水線的 Python 工具）。<button class="btn btn-yellow" id="install-uv">安裝 uv</button>`)}
      ${check(st.drive, `Google 雲端硬碟：${esc(st.drive)}`, "找不到 Google 雲端硬碟：請安裝 Google Drive 電腦版並登入。沒有也能跑，但結果不會同步到別台。")}
      ${st.blocked ? `<li><span class="pill y">!</span> 另一台電腦（${esc(st.blocked)}）正在用：這台先不同步，那台關掉後重開這個程式。</li>` : ""}
    </ul>`);

  for (const [id, v] of Object.entries(keep.replies)){ const t = el.querySelector(`[data-reply-box="${CSS.escape(id)}"]`); if (t && v) t.value = v; }
  el.querySelectorAll("[data-job-log]").forEach(lg => { lg.scrollTop = lg.scrollHeight; });
  if (keep.focus && document.getElementById(keep.focus)) document.getElementById(keep.focus).focus();

  const act = (fn) => async (ev) => { ev.target.disabled = true; try { await fn(); renderPipeline(await API("status")); } catch (e) { alert(e.message); ev.target.disabled = false; } };
  el.querySelectorAll("[data-continue]").forEach(b => b.addEventListener("click", act(() => API("continue", {slug: b.dataset.continue}))));
  el.querySelectorAll("[data-reply-send]").forEach(b => b.addEventListener("click", act(async () => {
    const box = el.querySelector(`[data-reply-box="${CSS.escape(b.dataset.replySend)}"]`), text = box.value.trim();
    if (!text) throw new Error("先寫要回覆的內容");
    await API("reply", {job: b.dataset.replySend, text}); box.value = "";
  })));
  el.querySelectorAll("[data-job-stop]").forEach(b => b.addEventListener("click", act(async () => {
    if (confirm("確定停止這個工作？已完成的部分會保留，之後可以按「繼續跑」。")) await API("stop", {job: b.dataset.jobStop}); })));
  el.querySelector("#install-uv")?.addEventListener("click", act(async () => {
    if (!confirm("從 uv 官方網站（astral.sh）下載並安裝 uv 到你的使用者資料夾，不需要管理員權限。要安裝嗎？")) return;
    const r = await API("install-uv", {}); alert(r.ok ? "uv 已安裝" : "安裝失敗：" + (r.error || ""));
  }));
}


/* 設定：Google 雲端硬碟帳號（切換、立刻同步）、Claude Code（測試、登入）、金鑰檔、uv */
let lastSettings = "";
function renderSettings(st){
  const el = document.querySelector("#settings:not([hidden]) .body");
  if (!el) return;
  const g = st.settings || {};
  const shape = JSON.stringify({g, syncing: st.syncing, blocked: st.blocked, claude: st.claude, codex: st.codex, engine: st.engine, ct: g.codex_test, uv: st.uv, running: st.running, v: st.version, u: st.update && st.update.latest});
  if (shape === lastSettings) return;
  lastSettings = shape;
  const t = g.claude_test;
  el.innerHTML =
    setRow("row-drive", "Google 雲端硬碟", g.account ? `<span class="small muted">${esc(g.account)}${st.syncing ? "｜同步中" : ""}</span>` : '<span class="pill r">沒有帳號</span>', `
        ${g.drives && g.drives.length ? `<p class="small">教授檔案放在：<br><span class="muted">${esc(g.folder || "（還沒選帳號）")}</span></p>
          <div class="small" style="margin-bottom:6px">這台電腦登入的帳號（按一下就換成這個帳號）：</div>
          <div class="row">${g.drives.map(a => a === g.account ? `<span class="pill g">✓ ${esc(a)}（使用中）</span>`
            : `<button class="btn btn-yellow" data-switch="${esc(a)}" ${st.running || st.syncing ? "disabled" : ""}>換成 ${esc(a)}</button>`).join("")}</div>
          <p class="small muted">要加別的帳號：在 Google Drive 電腦版的設定裡「新增帳戶」，再重開這個程式。換帳號後會從那個帳號的雲端重新同步，不會刪掉任何一邊的檔案。</p>
          <div class="row"><button class="btn btn-green" id="sync-now" ${st.syncing ? "disabled" : ""}>${st.syncing ? "同步中…" : "立刻同步"}</button>
          ${st.blocked ? `<span class="pill y">另一台（${esc(st.blocked)}）正在用：只拉不推</span>` : ""}</div>`
        : `<p><span class="pill r">✗</span> 這台電腦找不到 Google 雲端硬碟。</p>
          <ol class="small"><li>安裝 <a href="https://www.google.com/drive/download/" target="_blank" rel="noopener">Google Drive 電腦版</a></li><li>用你的 Google 帳號登入</li><li>重開這個程式</li></ol>`}`) +
    setRow("row-ai", "AI 引擎", `<span class="small muted">背景工作用 ${st.engine === "codex" ? "Codex" : "Claude Code"}</span>`, `
        <div class="row" role="radiogroup" aria-label="背景工作用哪個 AI">
          <label><input type="radio" name="engine" value="claude" ${st.engine !== "codex" ? "checked" : ""}> Claude Code（預設）</label>
          <label><input type="radio" name="engine" value="codex" ${st.engine === "codex" ? "checked" : ""}> Codex（ChatGPT，備用）</label></div>
        <p class="small muted">建檔、AI 編修、翻譯、補資訊這些背景工作用哪一個。Claude 額度用完時可以切到 Codex；這個選擇只存在這台電腦。</p>
        <h4 style="margin:12px 0 4px">Claude Code</h4>
        ${st.claude ? `<p class="small">${t ? (t.ok ? '<span class="pill g">✓ 可以用</span> ' : '<span class="pill r">✗ 不能用</span> ') + esc(t.msg) : '<span class="muted">已安裝，還沒測試</span>'}</p>
          <div class="row"><button class="btn btn-sm" id="claude-test">測試</button><button class="btn btn-sm" id="claude-login">登入／換帳號</button></div>`
        : `<p class="small">沒裝：到 <a href="https://claude.com/claude-code" target="_blank" rel="noopener">claude.com/claude-code</a> 安裝後重開。</p>`}
        <h4 style="margin:12px 0 4px">Codex CLI</h4>
        ${st.codex ? `<p class="small">${g.codex_test ? (g.codex_test.ok ? '<span class="pill g">✓ 可以用</span> ' : '<span class="pill r">✗ 不能用</span> ') + esc(g.codex_test.msg) : '<span class="muted">已安裝，還沒測試</span>'}</p>
          <div class="row"><button class="btn btn-sm" id="codex-test">測試</button><button class="btn btn-sm" id="codex-login">登入（ChatGPT 帳號）</button></div>`
        : `<p class="small">沒裝：在終端機執行 <code>npm install -g @openai/codex</code>，再按「登入」。</p>`}`) +
    setRow("row-applicant", "申請身分", g.applicant ? `<span class="pill g">${g.applicant.status === "international" ? "國際生" : "本地生"}</span> <span class="small muted">${esc([g.applicant.citizenship, g.applicant.intake && g.applicant.intake + " 入學"].filter(Boolean).join("｜"))}</span>` : '<span class="pill y">還沒設定</span>',
      `<form id="applicant-form" class="match-form" style="max-width:none">
         <div class="row" role="radiogroup" aria-label="申請身分">
           <label><input type="radio" name="status" value="international" ${!g.applicant || g.applicant.status === "international" ? "checked" : ""}> 國際生</label>
           <label><input type="radio" name="status" value="domestic" ${g.applicant && g.applicant.status === "domestic" ? "checked" : ""}> 本地生</label></div>
         <label>國籍<input type="text" name="citizenship" value="${esc((g.applicant || {}).citizenship || "Taiwan")}"></label>
         <label>想哪一年入學<input type="text" name="intake" value="${esc((g.applicant || {}).intake || String(new Date().getFullYear() + 1))}" placeholder="例：2027"></label>
         <button class="btn btn-green btn-sm" type="submit">儲存</button></form>
       <p class="small muted">查博士學程時，學費、獎學金、申請條件、截止日都照這個身分寫（國際生和本地生常常不同）。</p>`) +
    setRow("row-notion", "Notion", g.notion ? `<span class="pill g">✓ 已連接</span> <span class="small muted">${g.notion.fetched ? "匯入於 " + esc(g.notion.fetched.slice(0, 16).replace("T", " ")) : ""}</span>` : '<span class="pill">沒連接</span>',
      g.notion ? `<div class="row"><a class="btn btn-sm" href="${esc(g.notion.db_url || "#")}" target="_blank" rel="noopener">打開「博士申請追蹤」</a><button class="btn btn-green btn-sm" id="notion-import">立刻匯入</button></div>
          <p class="small muted">在 Notion 填教授、學程、截止日、狀態、會議；按「立刻匯入」（打開程式時也會自動匯入）。還沒建檔的教授會出現在「申請目標」等你按建檔。</p>`
        : `<ol class="small"><li>到 <a href="https://www.notion.so/profile/integrations" target="_blank" rel="noopener">notion.so/profile/integrations</a> 按「新增整合」（Internal），複製「Internal Integration Secret」</li>
            <li>在 Notion 開一個頁面（例：「博士申請」），右上角「…」→「連線」（Connections）→ 加入剛建的整合</li>
            <li>在那個頁面右上角「分享」→「複製連結」</li><li>把金鑰和連結貼在下面，按「連接」：程式會在那頁建「博士申請追蹤」資料庫，放進已建檔的教授</li></ol>
          <form id="notion-form" class="match-form" style="max-width:none"><label>整合金鑰<input type="password" name="token" autocomplete="off" placeholder="ntn_…"></label>
            <label>頁面連結<input type="text" name="link" placeholder="https://www.notion.so/…"></label><button class="btn btn-green btn-sm" type="submit">連接</button></form>
          <p class="small muted">金鑰存在你雲端硬碟的金鑰檔（每台電腦同步），程式不會顯示它。</p>`) +
    setRow("row-gcal", "Google 日曆", g.gcal && g.gcal.connected ? `<span class="pill g">✓ 已連接</span> <span class="small muted">${g.gcal.fetched ? "讀取於 " + esc(g.gcal.fetched.slice(0, 16).replace("T", " ")) : ""}</span>` : '<span class="pill">沒連接</span>',
      (g.gcal && g.gcal.connected ? `<div class="row"><button class="btn btn-green btn-sm" id="gcal-import">重新讀取會議</button><button class="btn btn-sm" id="gcal-login">重新登入</button></div>
          <p class="small muted">會議標題或說明寫了教授全名、與會者有教授的 email（教授卡片「編輯」可填），或是在教授頁建的會議，都會顯示在那位教授。</p>`
        : `<ol class="small"><li>到 <a href="https://console.cloud.google.com/apis/library/calendar-json.googleapis.com" target="_blank" rel="noopener">Google Cloud</a> 建一個專案，啟用「Google Calendar API」</li>
            <li>「OAuth 同意畫面」選「外部」，把自己的 Gmail 加到「測試使用者」</li>
            <li>「憑證」→「建立憑證」→「OAuth 用戶端 ID」→ 類型選「<strong>電腦版應用程式</strong>」→ 下載 JSON</li>
            <li>在下面選那個 JSON，再按「登入 Google」（會打開瀏覽器，允許「日曆活動」權限）</li></ol>
          <div class="row"><label class="btn btn-sm" style="cursor:pointer">${g.gcal && g.gcal.client ? "✓ 已上傳用戶端（換一個）" : "選用戶端 JSON"}<input type="file" id="gcal-client" accept=".json,application/json" hidden></label>
            <button class="btn btn-green btn-sm" id="gcal-login" ${g.gcal && g.gcal.client ? "" : "disabled"}>登入 Google</button></div>
          <p class="small muted">用戶端與登入權杖存在你雲端硬碟的 _me 資料夾（每台電腦同步），不會上傳到別處。</p>`)) +
    setRow("row-keys", "金鑰", g.keys && g.keys.S2_API_KEY ? '<span class="pill g">✓ Semantic Scholar 已設定</span>' : '<span class="pill y">沒設定</span>', `
        <p class="small">Semantic Scholar：${g.keys && g.keys.S2_API_KEY ? `<span class="pill g">✓ 已設定</span>` : `<span class="pill y">沒設定</span>（不設也能用，只是常被限流）`}</p>
        <button class="btn btn-green" id="open-secrets">打開金鑰檔</button>
        <p class="small muted">金鑰檔在你的雲端硬碟裡，每台電腦都會同步到；程式不會顯示金鑰內容。打開後在等號後面貼上 key、存檔即可。</p>`) +
    setRow("row-version", "版本", `<span class="small muted">${esc(st.version || "dev")}${st.update && st.update.available ? "｜有新版" : ""}</span>`, `
        <p class="small">目前版本：<strong>${esc(st.version || "dev")}</strong>${st.update && st.update.latest ? `｜最新：${esc(st.update.latest)}` : ""}</p>
        ${st.version && st.version !== "dev" ? `<button class="btn btn-green" id="check-update">檢查更新</button><div class="small" id="update-result" style="margin-top:8px" aria-live="polite">${window.UPDATE_MSG || ""}</div><p class="small muted">打開程式時與每 6 小時會自動檢查；有新版會出現在最上方。</p>`
          : `<p class="small muted">開發版（從 repo 直接跑）：用 git pull 更新。</p>`}`) +
    setRow("row-uv", "流水線工具（uv）", st.uv ? '<span class="pill g">✓ 已安裝</span>' : '<span class="pill r">沒裝</span>', `
        ${st.uv ? `<p class="small"><span class="pill g">✓</span> 已安裝：<span class="muted">${esc(st.uv)}</span></p>`
          : `<p class="small"><span class="pill r">✗</span> 沒有 uv（要建新教授才需要）。</p><button class="btn btn-yellow" id="install-uv2">安裝 uv</button>`}
        <p class="small muted">流水線放在：${esc(g.workspace || "")}</p>`);
  const act = fn => async ev => { const b = ev.currentTarget; b.disabled = true; try { await fn(); lastSettings = ""; renderSettings(await API("status")); } catch (e) { alert(e.message); b.disabled = false; } };
  el.querySelectorAll("[data-switch]").forEach(b => b.onclick = act(async () => {
    if (!confirm(`換成 ${b.dataset.switch} 的雲端硬碟？會從那個帳號重新同步教授檔案。`)) throw new Error("已取消");
    await API("account", {account: b.dataset.switch});
  }));
  el.querySelector("#sync-now")?.addEventListener("click", act(() => API("sync", {})));
  el.querySelector("#update-now")?.addEventListener("click", async () => {
    try { await API("update", {}); location.href = "loading.html"; } catch (e) { el.querySelector("#update-result").textContent = "更新失敗：" + e.message; } });
  el.querySelector("#check-update")?.addEventListener("click", async ev => {
    const b = ev.currentTarget, out = el.querySelector("#update-result");
    b.disabled = true; b.textContent = "檢查中…"; out.textContent = "";
    try {
      const r = await API("check-update", {});
      window.UPDATE_MSG = r.available ? `<span class="pill g">有新版本</span> ${esc(r.latest)}（目前 ${esc(r.current)}） <button class="btn btn-green" id="update-now">更新並重開</button>`
        : !r.latest ? `<span class="pill r">沒辦法檢查</span> 連不到 GitHub，網路好了再試` : `<span class="pill g">✓</span> 已經是最新版本 ${esc(r.current)}`;
      out.innerHTML = window.UPDATE_MSG;
    } catch (e) { out.textContent = "檢查失敗：" + e.message; }
    b.disabled = false; b.textContent = "檢查更新";
    lastSettings = ""; renderSettings(await API("status"));  // 重畫一次，讓「更新並重開」按鈕綁上
  });
  el.querySelector("#claude-test")?.addEventListener("click", act(async () => { el.querySelector("#claude-test").textContent = "測試中（最多 3 分鐘）…"; await API("test-claude", {}); }));
  el.querySelector("#claude-login")?.addEventListener("click", act(() => API("login-claude", {})));
  el.querySelector("#codex-test")?.addEventListener("click", act(async () => { el.querySelector("#codex-test").textContent = "測試中…"; await API("test-codex", {}); }));
  el.querySelector("#codex-login")?.addEventListener("click", act(() => API("login-codex", {})));
  el.querySelector("#gcal-import")?.addEventListener("click", act(async () => { const r = await API("gcal-import", {}); alert(`讀到 ${r.events} 個跟教授有關的會議`); }));
  el.querySelector("#gcal-login")?.addEventListener("click", act(async () => { await API("gcal-login", {}); alert("已在瀏覽器打開 Google 登入頁；允許後回到這裡（設定會自動更新）"); }));
  el.querySelector("#gcal-client")?.addEventListener("change", async ev => { const f = ev.target.files[0]; if (!f) return;
    try { await API("gcal-client", {json: await f.text()}); lastSettings = ""; renderSettings(await API("status")); } catch (e) { alert(e.message); } });
  el.querySelector("#applicant-form")?.addEventListener("submit", async ev => { ev.preventDefault(); const f = ev.target;
    try { await API("me-update", {applicant: {status: f.status.value, citizenship: f.citizenship.value, intake: f.intake.value}}); lastSettings = ""; renderSettings(await API("status")); }
    catch (e) { alert(e.message); } });
  el.querySelector("#notion-import")?.addEventListener("click", act(async () => { const r = await API("notion-import", {}); alert(`匯入 ${r.rows} 筆`); }));
  el.querySelector("#notion-form")?.addEventListener("submit", async ev => { ev.preventDefault(); const f = ev.target, b = f.querySelector("button"); b.disabled = true; b.textContent = "連接中…";
    try { const r = await API("notion-connect", {token: f.token.value, link: f.link.value}); f.token.value = ""; alert(`已連接，匯入 ${r.rows} 筆`); lastSettings = ""; renderSettings(await API("status")); }
    catch (e) { alert(e.message); b.disabled = false; b.textContent = "連接"; } });
  el.querySelectorAll('input[name="engine"]').forEach(r => r.onchange = async () => { try { await API("engine", {engine: r.value}); lastSettings = ""; renderSettings(await API("status")); } catch (e) { alert(e.message); } });
  el.querySelector("#open-secrets")?.addEventListener("click", act(() => API("open-secrets", {})));
  el.querySelector("#install-uv2")?.addEventListener("click", act(async () => {
    if (!confirm("從 uv 官方網站（astral.sh）下載並安裝 uv 到你的使用者資料夾，不需要管理員權限。要安裝嗎？")) throw new Error("已取消");
    const r = await API("install-uv", {}); if (!r.ok) throw new Error("安裝失敗：" + (r.error || ""));
  }));
}
