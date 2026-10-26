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

async function pipelinePanel(){
  let st;
  try { st = await API("status"); } catch (e) { return; }  // 不是在應用程式裡：不顯示
  window.APP_REMATCH = true;  // 教授卡片顯示「重新比對」按鈕
  if (document.getElementById("professors") && !document.getElementById("professors").hidden) renderProfs(H.professors);
  document.getElementById("professors")?.addEventListener("click", async ev => {
    const b = ev.target.closest("[data-rematch]");
    if (!b) return;
    if (!confirm("請 Claude Code 依你目前的研究興趣與 CV 項目重新比對這位教授？約需 10–20 分鐘，進度在「建新教授」那一區。")) return;
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
function renderPipeline(st){
  const el = document.querySelector("#pipeline:not([hidden]) .body");
  if (!el) return;  // 這一頁沒有「建新教授」區
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
  const keep = {reply: el.querySelector("#reply")?.value,
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

  if (keep.reply && el.querySelector("#reply")) el.querySelector("#reply").value = keep.reply;
  const log = el.querySelector(".log"); if (log) log.scrollTop = running ? log.scrollHeight : (keep.logTop || 0);
  if (keep.focus && document.getElementById(keep.focus)) document.getElementById(keep.focus).focus();

  const act = (fn) => async (ev) => { ev.target.disabled = true; try { await fn(); renderPipeline(await API("status")); } catch (e) { alert(e.message); ev.target.disabled = false; } };
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


/* 設定：Google 雲端硬碟帳號（切換、立刻同步）、Claude Code（測試、登入）、金鑰檔、uv */
let lastSettings = "";
function renderSettings(st){
  const el = document.querySelector("#settings:not([hidden]) .body");
  if (!el) return;
  const g = st.settings || {};
  const shape = JSON.stringify({g, syncing: st.syncing, blocked: st.blocked, claude: st.claude, uv: st.uv, running: st.running, v: st.version, u: st.update && st.update.latest});
  if (shape === lastSettings) return;
  lastSettings = shape;
  const t = g.claude_test;
  el.innerHTML = `
    <div class="grid">
      <div class="card"><h3 style="margin-top:0">Google 雲端硬碟</h3>
        ${g.drives && g.drives.length ? `<p class="small">教授檔案放在：<br><span class="muted">${esc(g.folder || "（還沒選帳號）")}</span></p>
          <div class="small" style="margin-bottom:6px">這台電腦登入的帳號（按一下就換成這個帳號）：</div>
          <div class="row">${g.drives.map(a => a === g.account ? `<span class="pill g">✓ ${esc(a)}（使用中）</span>`
            : `<button class="btn btn-yellow" data-switch="${esc(a)}" ${st.running || st.syncing ? "disabled" : ""}>換成 ${esc(a)}</button>`).join("")}</div>
          <p class="small muted">要加別的帳號：在 Google Drive 電腦版的設定裡「新增帳戶」，再重開這個程式。換帳號後會從那個帳號的雲端重新同步，不會刪掉任何一邊的檔案。</p>
          <div class="row"><button class="btn btn-green" id="sync-now" ${st.syncing ? "disabled" : ""}>${st.syncing ? "同步中…" : "立刻同步"}</button>
          ${st.blocked ? `<span class="pill y">另一台（${esc(st.blocked)}）正在用：只拉不推</span>` : ""}</div>`
        : `<p><span class="pill r">✗</span> 這台電腦找不到 Google 雲端硬碟。</p>
          <ol class="small"><li>安裝 <a href="https://www.google.com/drive/download/" target="_blank" rel="noopener">Google Drive 電腦版</a></li><li>用你的 Google 帳號登入</li><li>重開這個程式</li></ol>`}
      </div>
      <div class="card"><h3 style="margin-top:0">AI（Claude Code）</h3>
        ${st.claude ? `<p class="small"><span class="pill g">✓</span> 已安裝：<span class="muted">${esc(st.claude)}</span></p>
          ${t ? `<p class="small">${t.ok ? `<span class="pill g">✓ 可以用</span>` : `<span class="pill r">✗ 不能用</span>`} ${esc(t.msg)}</p>` : `<p class="small muted">還沒測試過能不能用。</p>`}
          <div class="row"><button class="btn btn-green" id="claude-test">測試能不能用</button><button class="btn btn-yellow" id="claude-login">登入／換帳號</button></div>
          <p class="small muted">「登入／換帳號」會開一個終端機視窗跑 Claude Code：照畫面登入（瀏覽器會跳出 Claude 的登入頁）；要換帳號就在裡面輸入 <code>/logout</code> 再登入。完成後關掉那個視窗，回來按「測試能不能用」。</p>`
        : `<p><span class="pill r">✗</span> 這台還沒裝 Claude Code（只看資料不需要；要建新教授、處理例外才需要）。</p>
          <ol class="small"><li>到 <a href="https://claude.com/claude-code" target="_blank" rel="noopener">claude.com/claude-code</a> 照說明安裝</li><li>重開這個程式，再回來按「登入」</li></ol>`}
      </div>
      <div class="card"><h3 style="margin-top:0">金鑰</h3>
        <p class="small">Semantic Scholar：${g.keys && g.keys.S2_API_KEY ? `<span class="pill g">✓ 已設定</span>` : `<span class="pill y">沒設定</span>（不設也能用，只是常被限流）`}</p>
        <button class="btn btn-green" id="open-secrets">打開金鑰檔</button>
        <p class="small muted">金鑰檔在你的雲端硬碟裡，每台電腦都會同步到；程式不會顯示金鑰內容。打開後在等號後面貼上 key、存檔即可。</p>
      </div>
      <div class="card"><h3 style="margin-top:0">版本</h3>
        <p class="small">目前版本：<strong>${esc(st.version || "dev")}</strong>${st.update && st.update.latest ? `｜最新：${esc(st.update.latest)}` : ""}</p>
        ${st.version && st.version !== "dev" ? `<button class="btn btn-green" id="check-update">檢查更新</button><div class="small" id="update-result" style="margin-top:8px" aria-live="polite">${window.UPDATE_MSG || ""}</div><p class="small muted">打開程式時與每 6 小時會自動檢查；有新版會出現在最上方。</p>`
          : `<p class="small muted">開發版（從 repo 直接跑）：用 git pull 更新。</p>`}
      </div>
      <div class="card"><h3 style="margin-top:0">流水線工具（uv）</h3>
        ${st.uv ? `<p class="small"><span class="pill g">✓</span> 已安裝：<span class="muted">${esc(st.uv)}</span></p>`
          : `<p class="small"><span class="pill r">✗</span> 沒有 uv（要建新教授才需要）。</p><button class="btn btn-yellow" id="install-uv2">安裝 uv</button>`}
        <p class="small muted">流水線放在：${esc(g.workspace || "")}</p>
      </div>
    </div>`;
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
  el.querySelector("#open-secrets")?.addEventListener("click", act(() => API("open-secrets", {})));
  el.querySelector("#install-uv2")?.addEventListener("click", act(async () => {
    if (!confirm("從 uv 官方網站（astral.sh）下載並安裝 uv 到你的使用者資料夾，不需要管理員權限。要安裝嗎？")) throw new Error("已取消");
    const r = await API("install-uv", {}); if (!r.ok) throw new Error("安裝失敗：" + (r.error || ""));
  }));
}
