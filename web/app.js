/* 應用程式專用：建新教授、停點回覆、繼續流水線（由 Claude Code 在背景跑）。
   只有在應用程式裡打開（有 /api）才顯示；離線單檔版沒有這一區。 */
const API = (path, body) => fetch("/api/" + path, body === undefined ? {cache: "no-store"} :
  {method: "POST", headers: {"Content-Type": "application/json", "X-Phdeasy-App": "1"}, body: JSON.stringify(body)})
  .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || r.status); return j; });

const STAGE_ZH = {setup: "找文章與全文", stop1: "停 1：等你確認", ingest: "轉成文字", network: "合作與領域", grants: "研究計畫",
  cards: "文章解析卡", profile: "總覽撰寫", verify: "獨立驗收", stop2: "停 2：等你決定", halted: "熔斷：等你決定"};
const WAITING = new Set(["stop1", "stop2", "halted"]);
let pollTimer = null;

let wasSyncing = null;
function appBanner(st){
  /* 最上方的狀態列：第一次選雲端帳號、正在同步（同步完自動重新整理，資料才是最新的） */
  let el = document.getElementById("app-banner");
  if (!el){ el = document.createElement("div"); el.id = "app-banner"; el.className = "wrap"; document.querySelector("main").before(el); }
  if (st.need_account){
    el.innerHTML = `<div class="card" style="margin-top:12px;border:2px solid var(--fg)"><h3 style="margin-top:0">選擇放教授檔案的 Google 帳號</h3>
      <p class="small">這台電腦登入了多個 Google 雲端硬碟帳號。選一次就好，之後會記住。</p>
      <div class="row">${st.drive_choices.map(a => `<button class="btn btn-green" data-acct="${esc(a)}">${esc(a)}</button>`).join("")}</div></div>`;
    el.querySelectorAll("[data-acct]").forEach(b => b.onclick = async () => { b.disabled = true; try { await API("account", {account: b.dataset.acct}); } catch (e) { alert(e.message); b.disabled = false; } });
  } else if (st.syncing){
    el.innerHTML = `<div class="card" style="margin-top:12px" role="status"><span class="pill y">同步中</span> 正在從 Google 雲端硬碟拉最新的教授檔案，第一次會比較久…完成後會自動重新整理。</div>`;
  } else {
    el.innerHTML = st.blocked ? `<div class="card" style="margin-top:12px"><span class="pill y">只能看</span> 另一台電腦（${esc(st.blocked)}）正在用：已拉下雲端的資料給你看，但這台先不推上去、不跑流水線。那台關掉後重開這個程式。</div>` : "";
    if (wasSyncing) location.reload();
  }
  wasSyncing = st.syncing || st.need_account;
}

async function pipelinePanel(){
  let st;
  try { st = await API("status"); } catch (e) { return; }  // 不是在應用程式裡：不顯示
  document.getElementById("pipeline").hidden = false;
  document.getElementById("nav-pipeline").hidden = false;
  appBanner(st);
  renderPipeline(st);
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => { try { const s = await API("status"); appBanner(s); renderPipeline(s); } catch (e) {} }, wasSyncing ? 1500 : 3000);
}

function check(ok, good, bad){ return `<li>${ok ? `<span class="pill g">✓</span> ${good}` : `<span class="pill r">✗</span> ${bad}`}</li>`; }

let lastShape = "";
function renderPipeline(st){
  const el = document.querySelector("#pipeline .body");
  /* 每 3 秒更新：只有紀錄變多時只換紀錄那一塊，不打斷你正在打字的欄位 */
  const shape = JSON.stringify({...st, log: undefined});
  const logEl = el.querySelector(".log");
  if (shape === lastShape && logEl){
    const atBottom = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 20;
    logEl.textContent = (st.log || []).join("\n");
    if (atBottom) logEl.scrollTop = logEl.scrollHeight;
    return;
  }
  lastShape = shape;
  const keep = {name: el.querySelector("#np-name")?.value, inst: el.querySelector("#np-inst")?.value,
                orcid: el.querySelector("#np-orcid")?.value, reply: el.querySelector("#reply")?.value,
                logTop: el.querySelector(".log")?.scrollTop, focus: document.activeElement?.id};
  const ready = st.claude && st.uv;
  const job = st.job, running = st.running;
  const profs = st.professors || [];
  el.innerHTML = `
    <div class="card"><h3 style="margin-top:0">這台電腦</h3><ul class="checks">
      ${check(st.claude, `Claude Code：${esc(st.claude)}`, `找不到 Claude Code。請先安裝並登入：<a href="https://claude.com/claude-code" target="_blank" rel="noopener">claude.com/claude-code</a>，裝好後重開這個程式。`)}
      ${check(st.uv, `uv：${esc(st.uv)}`, `找不到 uv（流水線的 Python 工具）。<button class="btn btn-yellow" id="install-uv">安裝 uv</button>`)}
      ${check(st.drive, `Google 雲端硬碟：${esc(st.drive)}`, "找不到 Google 雲端硬碟：請安裝 Google Drive 電腦版並登入。沒有也能跑，但結果不會同步到別台。")}
      ${st.blocked ? `<li><span class="pill y">!</span> 另一台電腦（${esc(st.blocked)}）正在用：這台先不同步，那台關掉後重開這個程式。</li>` : ""}
    </ul></div>

    <div class="card" style="margin-top:12px"><h3 style="margin-top:0">建新教授</h3>
      <p class="small muted">按下開始後，Claude Code 會在背景找身分、列文章、找全文，跑到停 1 停下來，請你確認。這段通常要 10–30 分鐘；看資料時保持程式開著。</p>
      <label for="np-name">教授姓名（必填）</label><input type="text" id="np-name" placeholder="例：Liliana Laranjo">
      <label for="np-inst">學校／機構（必填）</label><input type="text" id="np-inst" placeholder="例：The University of Sydney（Westmead Applied Research Centre）">
      <label for="np-orcid">ORCID（選填）</label><input type="text" id="np-orcid" placeholder="0000-0000-0000-0000">
      <div class="row" style="margin-top:12px"><button class="btn btn-green" id="np-start" ${!ready || running ? "disabled" : ""}>開始建檔</button>
        <span class="small muted">${!ready ? "先裝好上面打 ✗ 的項目" : running ? "已經有一個工作在跑" : ""}</span></div>
    </div>

    <div class="card" style="margin-top:12px"><h3 style="margin-top:0">各教授進度</h3>
      ${profs.length ? `<ul>${profs.map(p => `<li class="row" style="margin:6px 0"><strong>${esc(p.name || p.slug)}</strong>
        <span class="pill ${WAITING.has(p.stage) ? "y" : p.stage === "stop2" ? "g" : ""}">${esc(STAGE_ZH[p.stage] || p.stage)}</span>
        ${p.report ? `<a class="btn btn-green" href="../runs/${esc(p.slug)}/${esc(p.report)}" target="_blank" rel="noopener">看${p.stage === "stop1" ? "停 1" : "停 2"}報告</a>` : ""}
        ${p.stage !== "stop2" ? `<button class="btn btn-green" data-continue="${esc(p.slug)}" ${!ready || running ? "disabled" : ""}>${WAITING.has(p.stage) ? "我確認了，繼續跑" : "繼續跑"}</button>` : ""}</li>`).join("")}</ul>`
        : `<div class="empty">還沒有教授。用上面的表單建第一位。</div>`}
    </div>

    ${job ? `<div class="card" style="margin-top:12px"><h3 style="margin-top:0">目前的工作：${esc(job.title)}</h3>
      <div class="row">${running ? `<span class="pill y">執行中</span><button class="btn btn-red" id="job-stop">停止</button>`
        : job.status === "done" ? `<span class="pill g">這一段跑完了</span>` : `<span class="pill r">中斷（${esc(job.status)}）</span>`}
        ${job.cost_usd != null ? `<span class="small muted">本段用量約 US$${Number(job.cost_usd).toFixed(2)}</span>` : ""}</div>
      ${job.result && !running ? `<h3>Claude Code 的回報</h3><div class="card" style="white-space:pre-wrap">${esc(job.result)}</div>` : ""}
      <details ${running ? "open" : ""}><summary class="small" style="cursor:pointer;min-height:44px;display:flex;align-items:center">過程紀錄（${(st.log || []).length} 行）</summary>
        <div class="log" aria-live="polite">${esc((st.log || []).join("\n"))}</div></details>
      ${!running && job.session ? `<label for="reply">回覆 Claude Code（例：停 1 的決定、要它修什麼）</label>
        <textarea id="reply" placeholder="例：身分確認是這位；外部候選兩篇都加入；其他照你的建議，繼續跑到停 2。"></textarea>
        <div class="row" style="margin-top:8px"><button class="btn btn-green" id="reply-send" ${!ready ? "disabled" : ""}>送出並繼續</button>
        <span class="small muted">會接著同一個對話跑；停 1 確認後它會一路跑到停 2。</span></div>` : ""}
    </div>` : ""}`;

  if (keep.name) el.querySelector("#np-name").value = keep.name;
  if (keep.inst) el.querySelector("#np-inst").value = keep.inst;
  if (keep.orcid) el.querySelector("#np-orcid").value = keep.orcid;
  if (keep.reply && el.querySelector("#reply")) el.querySelector("#reply").value = keep.reply;
  const log = el.querySelector(".log"); if (log) log.scrollTop = running ? log.scrollHeight : (keep.logTop || 0);
  if (keep.focus && document.getElementById(keep.focus)) document.getElementById(keep.focus).focus();

  const act = (fn) => async (ev) => { ev.target.disabled = true; try { await fn(); renderPipeline(await API("status")); } catch (e) { alert(e.message); ev.target.disabled = false; } };
  el.querySelector("#np-start")?.addEventListener("click", act(async () => {
    const name = el.querySelector("#np-name").value.trim(), institution = el.querySelector("#np-inst").value.trim();
    if (!name || !institution) throw new Error("姓名和學校都要填");
    await API("new", {name, institution, orcid: el.querySelector("#np-orcid").value.trim()});
    ["#np-name", "#np-inst", "#np-orcid"].forEach(s => el.querySelector(s).value = "");
  }));
  el.querySelectorAll("[data-continue]").forEach(b => b.addEventListener("click", act(() => API("continue", {slug: b.dataset.continue}))));
  el.querySelector("#reply-send")?.addEventListener("click", act(async () => {
    const text = el.querySelector("#reply").value.trim();
    if (!text) throw new Error("先寫要回覆的內容");
    await API("reply", {text}); el.querySelector("#reply").value = "";
  }));
  el.querySelector("#job-stop")?.addEventListener("click", act(async () => { if (confirm("確定停止？已完成的部分會保留，之後可以按「繼續跑」。")) await API("stop", {}); }));
  el.querySelector("#install-uv")?.addEventListener("click", act(async () => {
    if (!confirm("從 uv 官方網站（astral.sh）下載並安裝 uv 到你的使用者資料夾，不需要管理員權限。要安裝嗎？")) return;
    const r = await API("install-uv", {}); alert(r.ok ? "uv 已安裝" : "安裝失敗：" + (r.error || ""));
  }));
}
