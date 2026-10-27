/* AI 小幫手（照 ieltsgod 的寫作頁管理畫面）：Claude／Gemini（Antigravity CLI）／ChatGPT（Codex CLI）三張卡片，
   點一張就設定那一位：① 安裝 → ② 登入 → ③ 測試連線；右邊選模型；額度用血條顯示；已連線的點一下設成預設。
   問 AI、翻譯、研究類型分類這些「問一次」的小工作用預設那位，失敗會自動換下一位測試過的。
   背景建檔另外選 Claude Code 或 Codex（Gemini 的 Antigravity 在背景不能操作檔案）。 */
(() => {
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const post = (p, b, ms) => { const c = new AbortController(), t = setTimeout(() => c.abort(), ms || 60000);
    return fetch("/api/" + p, {method: "POST", headers: {"Content-Type": "application/json", "X-Phdeasy-App": "1"}, body: JSON.stringify(b || {}), signal: c.signal})
      .then(r => r.json().then(j => r.ok ? j : Promise.reject(j)), () => Promise.reject({error: "連不到程式"})).finally(() => clearTimeout(t)); };
  const css = `
  .aibox{display:flex;flex-direction:column;gap:10px}
  .aipick{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
  .aicard{border:1px solid #e3e5e8;border-radius:12px;padding:10px;background:#fff;display:flex;flex-direction:column;gap:8px}
  .aicard.focus{border-color:#15803d;box-shadow:0 0 0 2px rgba(21,128,61,.18)}
  .aicard.def{background:#f3faf5}
  .aicard .ai{display:flex;gap:10px;align-items:flex-start;text-align:left;border:none;background:none;font:inherit;cursor:pointer;padding:0;color:inherit;min-height:44px}
  .aicard .nm{display:flex;flex-direction:column;gap:1px;min-width:0;flex:1}
  .aicard .nm>span{font-size:.8rem;color:#5b5f66}
  .aicard .uses{color:#15803d!important;font-weight:600}
  .aicard .st{font-weight:600}.aicard .st.ok{color:#15803d!important}.aicard .st.bad{color:#b91c1c!important}.aicard .st.mid{color:#8a6100!important}
  .bot{width:52px;height:48px;flex:0 0 auto}
  .bot .face{stroke:#111;stroke-width:2}.bot .eye{fill:#111}.bot .ln{stroke:#111;stroke-width:2;fill:none;stroke-linecap:round}
  .bot .led{fill:#c7cbd1;stroke:#fff;stroke-width:1.5}.bot.ready .led{fill:#2e9e5b}.bot.fail .led{fill:#d64545}.bot.busy .led{fill:#e0a100;animation:aipulse 1s infinite}.bot.off{opacity:.45}
  @keyframes aipulse{50%{opacity:.35}}
  @media (prefers-reduced-motion:reduce){.bot.busy .led{animation:none}}
  .mlist{display:flex;flex-wrap:wrap;gap:4px}
  .mopt{font:inherit;font-size:.78rem;min-height:30px;padding:0 8px;border-radius:7px;border:1px solid #d5d8dc;background:#fff;cursor:pointer}
  .mopt.on{background:#111;color:#fff;border-color:#111}
  .aiact{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
  .aigrid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,260px);gap:6px 12px;align-items:center;font-size:.9rem}
  .aigrid select{min-height:36px;width:100%}
  @media (max-width:640px){.aigrid{grid-template-columns:1fr}}
  .fl-lanes{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px;align-items:start}
  .fl-lane{border:2px dashed #9aa0a6;border-radius:18px;padding:12px;display:flex;flex-direction:column;align-items:stretch}
  .fl-head{display:flex;flex-direction:column;gap:6px;margin-bottom:10px}
  .fl-head b{font-size:.95rem}.fl-head select{min-height:36px}
  .fl-row{display:flex;gap:8px}.fl-row>.fl-node{flex:1}
  .fl-node{display:flex;flex-direction:column;gap:2px;text-align:left;font:inherit;font-size:.85rem;padding:8px 10px;border-radius:8px;border:2px solid #111;background:#fff;color:#111}
  .fl-script{border-color:#9aa0a6;background:#f4f5f6;color:#3f4348}
  .fl-tools{font-size:.75rem;color:#6b7076}
  .fl-ai{border-color:#15803d;background:#f3faf5;cursor:pointer;min-height:44px}
  .fl-ai:hover{background:#e3f4e8}.fl-ai:focus-visible{outline:3px solid #15803d;outline-offset:2px}
  .fl-ai[disabled]{cursor:default;opacity:.65}
  .fl-ai.own{box-shadow:0 0 0 3px rgba(21,128,61,.25)}
  .fl-main{border-style:double;border-width:4px}
  .fl-tag{font-size:.72rem;font-weight:700;color:#15803d}
  .fl-model{font-size:.78rem;font-weight:700;margin-top:2px}
  .fl-arrow{align-self:center;width:2px;height:16px;background:#555;position:relative;margin:2px 0 6px}
  .fl-arrow::after{content:"";position:absolute;left:-5px;bottom:-6px;border:6px solid transparent;border-top:7px solid #555;border-bottom:0}
  .fl-pop{position:fixed;z-index:600;background:#fff;border:1px solid #111;border-radius:10px;padding:10px;box-shadow:0 8px 24px rgba(0,0,0,.18);display:flex;flex-direction:column;gap:4px;min-width:220px;max-width:calc(100vw - 16px)}
  .fl-opt{font:inherit;font-size:.88rem;text-align:left;min-height:40px;padding:0 10px;border:1px solid #d5d8dc;border-radius:8px;background:#fff;cursor:pointer}
  .fl-opt:hover{background:#f4f5f6}.fl-opt.on{background:#15803d;color:#fff;border-color:#15803d}
  .aimsg{font-size:.9rem;line-height:1.6}
  .aimsg .note{font-size:.82rem;color:#5b5f66}
  .spin{display:inline-block;width:12px;height:12px;border:2px solid #c7cbd1;border-top-color:#15803d;border-radius:50%;animation:aispin .8s linear infinite;vertical-align:-1px;margin-right:6px}
  @keyframes aispin{to{transform:rotate(360deg)}}
  .aialert{position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:500;background:#111;color:#fff;padding:10px 16px;border-radius:10px;font-size:.9rem;max-width:min(560px,92vw);display:flex;gap:10px;align-items:center}
  .aialert.bad{background:#b91c1c}.aialert button{font:inherit;background:none;border:1px solid currentColor;color:inherit;border-radius:6px;min-height:28px;cursor:pointer}`;
  document.head.insertAdjacentHTML("beforeend", `<style>${css}</style>`);

  const AI_META = {stepfun: {plan: "用 StepFun 開放平台的 API key（按用量計費，或 Step Plan 訂閱）"}, claude: {plan: "需要 Claude 付費訂閱"}, gemini: {plan: "用有 Google AI Pro／Ultra 方案的 Google 帳號登入（透過 Antigravity CLI）"}, codex: {plan: "需要 ChatGPT 付費方案"}};
  // 三隻原創的小動物：大象（Claude）、長頸鹿（Gemini）、企鵝（ChatGPT）——照 ieltsgod
  function robotSVG(k, cls){
    const parts = {
      claude: `<ellipse class="face" cx="9" cy="22" rx="8" ry="11" fill="#b6c2d1"/><ellipse class="face" cx="47" cy="22" rx="8" ry="11" fill="#b6c2d1"/>
        <ellipse class="face" cx="28" cy="22" rx="15" ry="14" fill="#c9d3df"/><path class="face" d="M23 30 Q22 44 30 46 Q34 46 33 42 Q29 42 30 32 Z" fill="#c9d3df"/>
        <circle class="eye" cx="22" cy="20" r="2.4"/><circle class="eye" cx="34" cy="20" r="2.4"/><path class="ln" d="M20 32 Q17 36 19 39 M36 32 Q39 36 37 39"/>`,
      gemini: `<line class="ln" x1="22" y1="12" x2="21" y2="4"/><line class="ln" x1="34" y1="12" x2="35" y2="4"/>
        <circle cx="21" cy="4" r="2.6" fill="#a8672d" stroke="#111" stroke-width="1.5"/><circle cx="35" cy="4" r="2.6" fill="#a8672d" stroke="#111" stroke-width="1.5"/>
        <path class="face" d="M18 14 Q28 8 38 14 Q41 26 37 36 Q36 48 28 48 Q20 48 19 36 Q15 26 18 14 Z" fill="#f2c14e"/>
        <circle cx="22" cy="16" r="2.2" fill="#a8672d"/><circle cx="35" cy="25" r="2" fill="#a8672d"/><circle cx="20" cy="30" r="1.6" fill="#a8672d"/>
        <ellipse cx="28" cy="40" rx="8" ry="6" fill="#f7dc93" stroke="#111" stroke-width="2"/><circle class="eye" cx="23" cy="23" r="2.4"/><circle class="eye" cx="33" cy="23" r="2.4"/>
        <circle cx="25.5" cy="40" r="1" fill="#111"/><circle cx="30.5" cy="40" r="1" fill="#111"/>`,
      codex: `<path class="face" d="M28 4 Q46 6 46 28 Q46 48 28 48 Q10 48 10 28 Q10 6 28 4 Z" fill="#2b2f36"/>
        <path d="M28 14 Q40 16 40 30 Q40 44 28 44 Q16 44 16 30 Q16 16 28 14 Z" fill="#fff" stroke="#111" stroke-width="1.5"/>
        <circle cx="23" cy="24" r="2.4" fill="#2b2f36"/><circle cx="33" cy="24" r="2.4" fill="#2b2f36"/>
        <path d="M24 30 L32 30 L28 35 Z" fill="#f29a2e" stroke="#111" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 30 Q4 38 10 42 M48 30 Q52 38 46 42" class="ln"/>`,
      // StepFun：原創的貓頭鷹
      stepfun: `<path class="face" d="M12 10 L18 16 Q28 8 38 16 L44 10 L44 30 Q44 48 28 48 Q12 48 12 30 Z" fill="#8a6f5a"/>
        <circle cx="21" cy="25" r="7" fill="#fff" stroke="#111" stroke-width="1.5"/><circle cx="35" cy="25" r="7" fill="#fff" stroke="#111" stroke-width="1.5"/>
        <circle class="eye" cx="21" cy="25" r="2.8"/><circle class="eye" cx="35" cy="25" r="2.8"/>
        <path d="M26 31 L30 31 L28 36 Z" fill="#f29a2e" stroke="#111" stroke-width="1.2" stroke-linejoin="round"/><path class="ln" d="M20 41 Q28 45 36 41"/>`};
    return `<svg class="bot ${cls}" viewBox="0 0 56 52" aria-hidden="true">${parts[k]}<circle class="led" cx="49" cy="46" r="4.5"/></svg>`;
  }
  let AI = {}, PV = null, CFG = {}, aiBusy = "", aiTimer = null, AGYS = null, agyTimer = 0, AGYCODE = "", AINOTE = {}, ROOT = null;
  const ORDER3 = ["claude", "gemini", "codex", "stepfun"];
  let TASKS = {}, JOBS = null, SFKEY = null, KEYEDIT = false;
  const aiReady = pv => { const s = AI[pv]; return !!(s && s.installed && s.loggedIn !== false && s.tested && s.tested.ok); };
  const defAI = () => [CFG.provider, ...ORDER3].find(k => k && aiReady(k));
  function aiState(s){
    if (!s) return ["…", "mid"];
    if (!s.installed) return s.installing ? ["安裝中…", "mid"] : ["未安裝", "bad"];
    if (s.loggedIn === false) return s.loggingIn || s.terminal ? ["登入中…", "mid"] : ["未登入", "bad"];
    if (!s.tested) return ["未測試", "mid"];
    return s.tested.ok ? ["已連線 ✓", "ok"] : ["連線失敗", "bad"];
  }
  // 額度血條：像遊戲一樣，滿血是整條綠色，用掉多少就扣多少（綠 → 黃 → 紅）
  function hpBar(k, q, tested){
    const hm = t => new Date(t * 1000).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
    const ago = t => { if (!t) return ""; const m = Math.round((Date.now() - t) / 60000); return m < 1 ? "剛剛檢查" : m < 60 ? m + " 分鐘前檢查" : m < 48 * 60 ? Math.round(m / 60) + " 小時前檢查" : "很久沒檢查"; };
    let pct = 100, lab = "";
    if (q && q.state === "out"){ pct = 0; lab = "額度用完" + (q.resets ? "，" + hm(q.resets) + " 恢復" : ""); }
    else if (q && q.left != null){ pct = Math.max(0, Math.min(100, q.left)); lab = "剩 " + pct + "%" + (q.resets ? "・" + hm(q.resets) + " 重置" : ""); }
    else if (q && q.state === "warn"){ pct = 20; lab = "快用完了"; }
    else if (k === "gemini") lab = "可以用（Google 不提供 %）";
    else if (q) lab = "額度充足（快用完時才會顯示剩幾 %）";
    else lab = "可以用";
    const when = ago((q && q.t) || (tested && tested.t)), col = pct > 50 ? "#2e9e5b" : pct > 20 ? "#e0a100" : "#d64545";
    return `<span title="額度：${esc(lab)}" style="display:block;margin-top:3px"><span style="display:flex;align-items:center;gap:6px"><b style="font-size:10px;letter-spacing:.5px">HP</b>
      <span style="position:relative;flex:1;min-width:70px;max-width:140px;height:9px;border-radius:5px;background:rgba(127,127,127,.22);overflow:hidden">
      <span style="position:absolute;inset:0 auto 0 0;width:${pct}%;background:${col};border-radius:5px;transition:width .6s ease"></span></span></span>
      <span style="font-size:11px">${esc(lab)}${when ? "・" + when : ""}</span></span>`;
  }
  /* ---------- Antigravity（Gemini）登入：程式在背景操作 agy，使用者只要貼上網頁給的 code ---------- */
  function agyPanel(){
    const s = AGYS, sp = '<span class="spin"></span>';
    const steps = n => `<div class="note" style="margin-bottom:6px">${["打開登入頁", "在瀏覽器登入", "貼上 code", "完成"].map((t, i) => i < n ? '<b style="color:#15803d">✓</b> ' + t : i === n ? "<b>" + t + "</b>" : t).join("　→　")}</div>`;
    const link = s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">瀏覽器沒有跳出來？點這裡打開登入頁</a>` : "";
    const err = s.error ? `<div style="color:#b91c1c;margin:4px 0">${esc(s.error)}</div>` : "";
    const scr = s.screen ? `<details style="margin-top:6px"><summary class="note" style="cursor:pointer">技術細節（出問題時截圖）</summary><pre style="white-space:pre-wrap;font-size:11px;max-height:160px;overflow:auto">${esc(s.screen)}</pre></details>` : "";
    const cancel = '<button type="button" class="btn btn-sm" data-agy="cancel">取消</button>';
    if (s.state === "starting" || s.state === "browser") return steps(0) + sp + "正在打開 Google 登入頁…" + scr;
    if (s.state === "need_code") return steps(2) + '<ol style="margin:0 0 6px;padding-left:20px;line-height:1.7"><li>在打開的網頁用<b>有 Google AI Pro／Ultra 方案的帳號</b>登入，按「允許」</li><li>網頁最後會給你一串 <b>code</b>：按旁邊的複製，貼到下面，按「送出」</li></ol>'
      + `<div class="row" style="gap:6px;flex-wrap:wrap"><input id="agyCode" type="text" placeholder="貼上 code" value="${esc(AGYCODE)}" autocomplete="off" style="flex:1;min-width:220px;font-family:ui-monospace,Menlo,monospace"><button type="button" class="btn btn-green btn-sm" data-agy="send">送出</button>${cancel}</div>` + err + '<div style="margin-top:4px">' + link + "</div>" + scr;
    if (s.state === "finishing") return steps(3) + sp + "登入中，正在幫你完成剩下的設定（主題、條款、信任資料夾）…約 30 秒" + scr;
    if (s.state === "testing") return steps(3) + sp + "測試連線中…" + scr;
    if (s.state === "done") return steps(4) + '<b style="color:#15803d">已登入並連線成功 ✓</b> 可以用 Gemini 了。';
    if (s.state === "error") return err + `<div class="row" style="gap:6px;margin-top:4px"><button type="button" class="btn btn-green btn-sm" data-agy="restart">重新開始</button><button type="button" class="btn btn-sm" data-act="terminal">改用終端機登入</button>${cancel}</div>` + scr;
    return "";
  }
  async function agyStart(){ AGYCODE = ""; try { AGYS = await post("ai-agy", {action: "start"}); } catch (err) { AGYS = {state: "error", error: (err && err.error) || "沒辦法開始登入"}; } renderAI(); agyWatch(); }
  function agyWatch(){ clearInterval(agyTimer); agyTimer = setInterval(async () => { let s; try { s = await post("ai-agy", {}); } catch (e) { return; }
    const changed = !AGYS || s.state !== AGYS.state || s.url !== AGYS.url || s.error !== AGYS.error;
    AGYS = s; if (changed){ if (s.state === "done"){ clearInterval(agyTimer); await checkEngine(); } renderAI(); }
    if (s.state === "error" || s.state === "done" || !s.state) clearInterval(agyTimer); }, 1000); }
  async function checkEngine(){
    let g = {}; try { g = await post("ai-engine", {}, 90000); } catch (e) {}
    AI = g.providers || {}; CFG = {provider: g.provider, autoSwitch: g.autoSwitch}; TASKS = g.tasks || {}; JOBS = g.jobs || null; SFKEY = g.stepfunKey || null;
    if (!PV || !AI[PV]) PV = g.selected || "claude";
    renderAI(); return AI[PV] || {};
  }
  async function setDefault(pv){
    try { await post("ai-settings", {provider: pv}); CFG.provider = pv; } catch (err) {}
    renderAI(); msg(`已把 <b>${esc(AI[pv].name)}</b> 設為預設：問 AI、翻譯、研究類型分類都改用它（它額度用完會自動換下一位）。`);
  }
  const msg = h => { const m = ROOT && ROOT.querySelector(".aimsg"); if (m) m.innerHTML = h; };
  function renderAI(){
    if (!ROOT || !document.body.contains(ROOT)) return;
    const pick = ORDER3.map(k => { const s = AI[k] || {}, [t, c] = aiState(AI[k]);
      const busy = (k === PV && aiBusy) || s.installing || s.loggingIn, cls = busy ? "busy" : !s.installed ? "off" : aiReady(k) ? "ready" : (s.tested && !s.tested.ok) ? "fail" : "";
      const role = busy ? "工作中…" : s.cool ? `暫停中：${s.cool.why}（約 ${s.cool.min} 分鐘）` : aiReady(k) ? "已連線 ✓" : t;
      const ms = s.installed && !s.needsAgy ? (s.models || []) : [];
      return `<div class="aicard${k === PV ? " focus" : ""}${defAI() === k ? " def" : ""}"><button type="button" class="ai" data-pv="${k}" aria-label="${esc(s.name || k)}：${esc(role)}">${robotSVG(k, cls)}
          <span class="nm"><b>${esc(s.name || k)}</b><span>${esc(s.tool || "")}</span>${defAI() === k ? '<span class="uses">預設</span>' : ""}<span class="st ${s.cool ? "bad" : aiReady(k) ? "ok" : c}">${esc(role)}</span>${s.installed ? hpBar(k, s.quota, s.tested) : ""}</span></button>
        ${ms.length ? `<div class="mlist" role="radiogroup" aria-label="${esc(s.name || k)} 的模型">${ms.map(m => `<button type="button" class="mopt${m.v === s.model ? " on" : ""}" data-mpv="${k}" data-model="${esc(m.v)}" role="radio" aria-checked="${m.v === s.model}" title="${esc(m.bad ? "你的帳號目前不能用這個模型（試過失敗，先關掉，一週後可以再試）" : m.note)}" ${aiBusy || m.bad ? "disabled" : ""} style="${m.bad ? "opacity:.4;text-decoration:line-through" : ""}">${esc(m.name)}</button>`).join("")}${aiBusy === "model" && k === PV ? '<span class="note"><span class="spin"></span>切換中</span>' : ""}</div>` : ""}</div>`; }).join("");
    const s = AI[PV] || {}, nm = s.name || PV, tool = s.tool || "";
    let act = "", m = "";
    if (PV === "stepfun"){
      // StepFun：不用安裝或登入，貼 key（存在你雲端硬碟的金鑰檔，畫面只顯示末四碼）
      const keyForm = `<div class="row" style="gap:6px;flex-wrap:wrap;width:100%"><input id="sfKey" type="password" autocomplete="off" placeholder="貼上 StepFun 的 API key" style="flex:1;min-width:240px"><button type="button" class="btn btn-green btn-sm" data-sf="save">儲存並測試</button>${SFKEY ? '<button type="button" class="btn btn-sm" data-sf="cancel">取消</button>' : ""}</div>`;
      if (!SFKEY || KEYEDIT) act = keyForm;
      else act = `<span class="small">key：<code>${esc(SFKEY)}</code></span><button type="button" class="btn btn-sm" data-sf="edit">換 key</button><button type="button" class="btn btn-sm" data-sf="remove">移除 key</button><button type="button" class="btn btn-green btn-sm" data-act="test" ${aiBusy ? "disabled" : ""}>${aiBusy === "test" ? '<span class="spin"></span>測試中…' : "測試連線"}</button>`;
      m = !SFKEY ? `到 <a href="https://platform.stepfun.ai" target="_blank" rel="noopener">StepFun 開放平台</a>「介面金鑰」頁建立一組 key，貼在上面。key 存在你雲端硬碟的金鑰檔，每台電腦同步，畫面只會顯示末四碼。`
        : s.tested ? (s.tested.ok ? `已連線（${new Date(s.tested.t).toLocaleString()}，${esc(s.tested.msg || "")}）。下面「各小工作」與「背景工作」可以選用 StepFun。` : "連線失敗：" + esc(s.tested.msg || "")) : "按「測試連線」確認 key 可以用。";
    } else if (!s.installed){
      if (s.needsNode) m = `${nm} 要先安裝 Node.js：到 <a href="https://nodejs.org" target="_blank" rel="noopener">nodejs.org</a> 下載 LTS 版，裝好後重開程式，再回來按「安裝」。`;
      act = `<button type="button" class="btn btn-green btn-sm" data-act="install" ${s.installing || aiBusy ? "disabled" : ""}>① 安裝 ${esc(tool)}</button>`;
      if (s.installing) m = '<span class="spin"></span>正在安裝（約 1～2 分鐘）…' + (s.installLog && s.installLog.length ? ' <span style="font-family:ui-monospace,monospace;font-size:11px">' + esc(String(s.installLog[s.installLog.length - 1]).slice(0, 80)) + "</span>" : "");
      else if (s.installDone && !s.installOk) m = esc(s.installError || "安裝沒有成功，可以再按一次。");
      else if (!m) m = `${(AI_META[PV] || {}).plan}。`;
    } else if (s.needsAgy){
      act = `<button type="button" class="btn btn-green btn-sm" data-act="install" ${s.installing || aiBusy ? "disabled" : ""}>安裝 Antigravity CLI</button>`;
      m = s.installing ? '<span class="spin"></span>正在安裝 Antigravity CLI（約 1 分鐘）…' : (s.installDone && !s.installOk ? esc(s.installError || "安裝沒有成功，可以再按一次。") + " " : "") +
        "Google 從 2026/6/18 起停止讓 Google 帳號（包括 Google AI Pro／Ultra 付費方案）使用舊的 Gemini CLI，改成 <b>Antigravity CLI</b>。按左邊安裝，裝好後按「② 登入」用有方案的帳號登入。";
    } else if (s.needsGit){
      act = `<a class="btn btn-green btn-sm" href="https://git-scm.com/downloads/win" target="_blank" rel="noopener">下載 Git for Windows</a><button type="button" class="btn btn-sm" data-act="test" ${aiBusy ? "disabled" : ""}>${aiBusy === "test" ? '<span class="spin"></span>測試中…' : "裝好了，測試連線"}</button>`;
      m = "Windows 上的 Claude Code 還需要一個免費工具 <b>Git for Windows</b> 才能執行。按左邊下載，安裝時一路按「Next」就好；裝好後回來按「裝好了，測試連線」（不用重開程式）。";
    } else {
      // 順序：① 安裝 → ② 登入 → ③ 測試連線。還沒確定登入就先登入，登入好才測試
      const li = s.loggedIn == null && s.tested && s.tested.ok ? true : s.loggedIn, authFail = s.tested && !s.tested.ok && /log ?in|auth|credential|unauthori[sz]ed|401|api key/i.test(s.tested.msg || "");
      const needLogin = li !== true || authFail;
      if (needLogin) act += `<button type="button" class="btn btn-green btn-sm" data-act="login" ${aiBusy || s.loggingIn ? "disabled" : ""}>② 登入 ${esc(nm)}</button>`;
      if (li === true) act += `<button type="button" class="btn btn-sm" data-act="logout" ${aiBusy ? "disabled" : ""}>登出／換帳號</button>`;
      if (needLogin || (s.tested && !s.tested.ok)) act += `<button type="button" class="btn btn-sm" data-act="terminal" ${aiBusy ? "disabled" : ""}>用終端機登入／設定</button>`;
      act += `<button type="button" class="btn ${needLogin ? "" : "btn-green "}btn-sm" data-act="test" ${aiBusy || li === false || s.loggingIn ? "disabled" : ""}>${aiBusy === "test" ? '<span class="spin"></span>測試中…' : (li === null && !authFail ? "③ 已經登入過？直接測試" : "③ 測試連線")}</button>`;
      if (s.terminal) m = PV === "gemini" ? "已打開一個終端機視窗：照畫面用 Google 帳號登入（有問「是否信任這個資料夾」就選信任）。完成後關掉那個終端機，回來按「測試連線」。" : `已打開一個終端機視窗，照畫面登入 ${esc(nm)}，完成後關掉它，回來按「測試連線」。`;
      else if (s.loggingIn) m = `<span class="spin"></span>已打開 ${esc(nm)} 的登入頁，在瀏覽器登入並按「授權」，完成後這裡會自動更新。` + (s.loginUrl ? ` <a href="${esc(s.loginUrl)}" target="_blank" rel="noopener">沒有跳出來？點這裡</a>` : "");
      else if (s.loggedIn === false) m = `還沒登入 ${esc(nm)}（${(AI_META[PV] || {}).plan}）。先按「② 登入」，在打開的網頁登入並授權，完成後再按「③ 測試連線」。`;
      else if (s.loggedIn == null && !s.tested) m = `看不出這台電腦有沒有登入過 ${esc(nm)}。沒登入過就先按「② 登入」；確定登入過，可以直接按「③ 測試」。`;
      else if (authFail) m = "連線失敗：還沒登入或登入過期（" + esc(s.tested.msg || "") + "）。按「② 登入」重新登入，再測試一次。";
      else if (s.tested && s.tested.ok) m = `已連線（上次測試 ${new Date(s.tested.t).toLocaleString()}，${esc(s.tested.msg || "")}）。${defAI() === PV ? "" : "點上面這張卡片可以設成預設。"}`;
      else if (s.tested) m = "連線失敗：" + esc(s.tested.msg || "") + "。";
      else m = "按「測試連線」確認可以用（約 10～30 秒）。";
      const ok = x => x ? '<b style="color:#15803d">✓</b>' : "", tOk = s.tested && s.tested.ok;
      m = `<div class="note" style="margin-bottom:4px">① 安裝 ${ok(1)}　→　② 登入 ${s.loggedIn === true || (s.loggedIn == null && tOk) ? ok(1) : s.loggingIn ? '<span class="spin"></span>' : s.loggedIn === false ? '<span style="color:#b91c1c">還沒</span>' : "？"}　→　③ 測試連線 ${tOk ? ok(1) : (s.tested ? '<span style="color:#b91c1c">失敗</span>' : "")}</div>` + m;
    }
    if (AINOTE[PV] && s.loggedIn !== true){ m = AINOTE[PV]; if (!/data-act="terminal"/.test(act)) act += `<button type="button" class="btn btn-sm" data-act="terminal">用終端機登入</button>`; }
    if (PV === "gemini" && AGYS && AGYS.state){ m = agyPanel(); act = act.replace(/<button[^>]*data-act="login"[^>]*>.*?<\/button>/, ""); }
    ROOT.querySelector(".aipick").innerHTML = pick;
    ROOT.querySelector(".aiact").innerHTML = act;
    ROOT.querySelector(".aimsg").innerHTML = m;
    const au = ROOT.querySelector("#aiAuto"); if (au) au.checked = CFG.autoSwitch !== false;
    renderRouting();
  }
  /* 各小工作用哪一位、背景工作每一類用哪個引擎、各角色用哪個模型（本人 2026-10-27：要能自己搭配、隨時改） */
  function renderRouting(){
    const box = ROOT.querySelector(".airoute"); if (!box) return;
    const ready = ORDER3.filter(aiReady), name = k => (AI[k] || {}).name || k;
    const sel = (attr, opts, cur) => `<select ${attr}>${opts.map(([v, l]) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
    let h = "";
    if (JOBS) h += flowHTML();
    box.innerHTML = h;
  }
  /* 流程圖（照本人給的圖：每一類工作一個虛線框，框裡一步一步往下，旁邊寫用的工具）：
     灰色＝腳本做、不用 AI；綠色＝會派 AI，點一下換模型；每個框的標題列選這一類用哪個引擎 */
  const LANES = [
    {group: "build", title: "建檔：一位教授近五年的文章", nodes: [
      {s: "找教授身分、列出近五年文章", tools: "OpenAlex、ORCID、PubMed"},
      {ai: ["setup.focus", "setup.programs"]},
      {s: "找全文", tools: "Unpaywall、Europe PMC、PMC、Zotero"},
      {s: "轉成文字、抓圖表", tools: "PyMuPDF"},
      {s: "合作者與研究領域", tools: "腳本計算"},
      {s: "查研究計畫", tools: "NIH RePORTER、NSF、GRB、UKRI"},
      {ai: ["grants.extract", "grants.refute"]},
      {ai: ["cards.reader", "cards.refute"]},
      {ai: ["digest.digester"]},
      {ai: ["profile.writer", "profile.refute"]},
      {ai: ["match.matcher"]},
      {ai: ["verify.judge"]},
      {s: "總檢查、組成教授頁", tools: "E2E 腳本、網頁、RIS"}]},
    {group: "library", title: "Meeting：教授給的文獻", nodes: [
      {s: "上傳 PDF／貼 DOI／Zotero", tools: "OpenAlex 查 DOI 與標題"},
      {task: "classify"},
      {s: "找全文、轉文字、抓圖表", tools: "同建檔的腳本"},
      {ai: ["library.digester"]},
      {ai: ["library.drafter"]}]},
    {group: "research", title: "查詢與比對", nodes: [
      {s: "依你的研究興趣找教授", tools: "OpenAlex"},
      {ai: ["research.discover"]},
      {ai: ["research.match"]},
      {ai: ["research.propose"]}]},
    {group: "docs", title: "我的文件", nodes: [
      {s: "上傳 Word／PDF", tools: "依原檔分段"},
      {ai: ["docs.editor"]},
      {ai: ["docs.translator"]}]},
    {group: null, title: "閱讀時「問一次」的小工作", nodes: [{task: "ask"}, {task: "translate"}]},
  ];
  const STEPS = () => Object.fromEntries((JOBS.steps || []).map(x => [x.id, x]));
  const engOf = g => ((JOBS.groups || []).find(x => x.id === g) || {}).engine || "claude";
  const modelName = (e, v) => ((JOBS.models[e] || []).find(m => m.v === v) || {}).name || v || "帳號預設";
  function stepModel(id){
    const st = STEPS()[id], e = engOf(st.group);
    if (e === "codex") return {e, v: "", name: "Codex 帳號預設", own: false};
    const own = ((JOBS.stepModels || {})[e] || {})[id];
    return {e, v: own || "", name: modelName(e, own || JOBS.tiers[e][st.tier]), own: !!own};
  }
  function flowHTML(){
    const S = STEPS(), name = k => (AI[k] || {}).name || k, ready = ORDER3.filter(aiReady);
    const arrow = '<div class="fl-arrow" aria-hidden="true"></div>';
    const node = n => {
      if (n.s) return `<div class="fl-node fl-script"><span>${esc(n.s)}</span><span class="fl-tools">${esc(n.tools)}</span></div>`;
      if (n.task){ const t = TASKS[n.task] || {};
        return `<button type="button" class="fl-node fl-ai" data-flow-task="${n.task}" aria-haspopup="true"><span class="fl-tag">AI 小工作</span><span>${esc(t.label || n.task)}</span>
          <span class="fl-model">${esc(t.choice ? name(t.choice) : `自動（${name(t.using) || "沒有"}）`)}</span></button>`; }
      return `<div class="fl-row">${n.ai.map(id => { const st = S[id], m = stepModel(id);
        return `<button type="button" class="fl-node fl-ai${m.own ? " own" : ""}" data-flow-step="${id}" aria-haspopup="true" ${m.e === "codex" ? "disabled" : ""}>
          <span class="fl-tag">${esc(st.role)}</span><span>${esc(st.label)}</span><span class="fl-model">${esc(m.name)}${m.own ? "（你選的）" : ""}</span></button>`; }).join("")}</div>`;
    };
    const lanes = LANES.map(L => {
      const head = L.group ? `<select data-jobgroup="${L.group}" aria-label="${esc(L.title)}用哪個引擎">${Object.entries(JOBS.engines).map(([v, l]) =>
        `<option value="${v}" ${engOf(L.group) === v ? "selected" : ""}>${esc(l)}${v === "stepfun" && !SFKEY ? "（先貼 key）" : ""}</option>`).join("")}</select>` : "";
      const main = L.group && engOf(L.group) !== "codex" ? `<button type="button" class="fl-node fl-ai fl-main" data-flow-main="${L.group}"><span class="fl-tag">主控</span><span>照流程派工、跑腳本</span>
        <span class="fl-model">${esc(modelName(engOf(L.group), JOBS.tiers[engOf(L.group)].main))}</span></button>${arrow}` : "";
      return `<section class="fl-lane"><div class="fl-head"><b>${esc(L.title)}</b>${head}</div>${main}${L.nodes.map(node).join(arrow)}</section>`;
    }).join("");
    return `<h4 style="margin:18px 0 4px">流程圖：哪一步用哪個模型</h4>
      <div class="small muted" style="margin-bottom:8px">灰色是腳本做的，不用 AI；綠色會用 AI，點一下換模型（框的標題列選這一類用 Claude、StepFun 或 Codex）。改了之後，新開始的工作才會用新設定。</div>
      <div class="fl-lanes">${lanes}</div>
      <details style="margin-top:10px"><summary class="small" style="cursor:pointer;min-height:36px">沒有特別選的步驟：各角色預設用哪個模型</summary>
        ${["claude", "stepfun"].map(e => `<div class="small" style="margin:8px 0 4px"><b>${esc(JOBS.engines[e])}</b></div><div class="aigrid">${Object.entries(JOBS.roles).map(([r, lab]) =>
          `<span>${esc(lab)}</span><select data-tier="${e}" data-role="${r}">${JOBS.models[e].map(m => `<option value="${esc(m.v)}" ${m.v === (JOBS.tiers[e][r] || "") ? "selected" : ""}>${esc(m.name)}</option>`).join("")}</select>`).join("")}
          ${e === "stepfun" ? `<span>StepFun 方案</span><select data-sfbase="1">${Object.entries(JOBS.bases).map(([v, l]) => `<option value="${v}" ${v === JOBS.stepfunBase ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>` : ""}</div>`).join("")}</details>`;
  }
  // 點流程圖上的 AI 步驟：跳出小框選模型
  let popEl = null;
  const popClose = () => { if (popEl){ popEl.remove(); popEl = null; } };
  function popAt(btn, title, opts, onPick){
    popClose(); const r = btn.getBoundingClientRect(); popEl = document.createElement("div"); popEl.className = "fl-pop"; popEl.setAttribute("role", "dialog"); popEl.setAttribute("aria-label", title);
    popEl.innerHTML = `<div class="small" style="font-weight:700;margin-bottom:6px">${esc(title)}</div>` + opts.map(o => `<button type="button" class="fl-opt${o.on ? " on" : ""}" data-v="${esc(o.v)}">${esc(o.l)}</button>`).join("");
    document.body.appendChild(popEl);
    popEl.style.left = Math.max(8, Math.min(innerWidth - popEl.offsetWidth - 8, r.left)) + "px";
    popEl.style.top = Math.max(8, Math.min(innerHeight - popEl.offsetHeight - 8, r.bottom + 6)) + "px";
    popEl.onclick = ev => { const b = ev.target.closest("[data-v]"); if (!b) return; popClose(); onPick(b.dataset.v); };
    const f = popEl.querySelector(".fl-opt.on") || popEl.querySelector(".fl-opt"); if (f) f.focus();
  }
  document.addEventListener("mousedown", e => { if (popEl && !popEl.contains(e.target) && !e.target.closest("[data-flow-step],[data-flow-task],[data-flow-main]")) popClose(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") popClose(); });
  document.addEventListener("click", e => {
    if (!ROOT || !ROOT.contains(e.target)) return;
    const st = e.target.closest("[data-flow-step]"), tk = e.target.closest("[data-flow-task]"), mn = e.target.closest("[data-flow-main]");
    if (st){ const id = st.dataset.flowStep, s0 = STEPS()[id], m = stepModel(id);
      return popAt(st, `${s0.role}：${s0.label}`, [{v: "", l: `照角色預設（${modelName(m.e, JOBS.tiers[m.e][s0.tier])}）`, on: !m.own},
        ...JOBS.models[m.e].filter(x => x.v).map(x => ({v: x.v, l: x.name, on: m.own && x.v === m.v}))],
        v => saveRouting({jobs: {steps: {[m.e]: {[id]: v}}}}, `已更新：${s0.label} 改用 ${v ? modelName(m.e, v) : "角色預設"}，新開始的工作才會用。`)); }
    if (tk){ const k = tk.dataset.flowTask, t = TASKS[k] || {}, ready = ORDER3.filter(aiReady);
      return popAt(tk, t.label || k, [{v: "", l: "自動（StepFun 測試成功就用它，否則預設那位）", on: !t.choice}, ...ready.map(v => ({v, l: (AI[v] || {}).name || v, on: t.choice === v}))],
        v => saveRouting({tasks: {[k]: v}}, "已更新：這個小工作用哪一位。")); }
    if (mn){ const g = mn.dataset.flowMain, e2 = engOf(g);
      return popAt(mn, "主控：照流程派工、跑腳本", JOBS.models[e2].map(x => ({v: x.v, l: x.name, on: x.v === (JOBS.tiers[e2].main || "")})),
        v => saveRouting({jobs: {tiers: {[e2]: {main: v}}}}, "已更新主控用的模型（這個引擎的每一類工作都用它）。")); }
  });
  async function saveRouting(body, okMsg){
    try { const g = await post("ai-settings", body); TASKS = g.tasks || TASKS; JOBS = g.jobs || JOBS; renderRouting(); if (okMsg) msg(okMsg); }
    catch (err) { msg(esc((err && err.error) || "沒有存到")); checkEngine(); }
  }
  document.addEventListener("change", e => {
    if (!ROOT || !ROOT.contains(e.target)) return;
    const t = e.target;
    if (t.dataset.task) return saveRouting({tasks: {[t.dataset.task]: t.value}}, "已更新：各小工作用哪一位。");
    if (t.dataset.jobgroup){
      if (t.value === "stepfun" && !SFKEY){ msg("先在上面 StepFun 卡片貼 key，才能讓背景工作用 StepFun。"); return renderRouting(); }
      return saveRouting({jobs: {groups: {[t.dataset.jobgroup]: t.value}}}, "已更新：之後新開始的這類背景工作會用新的引擎。");
    }
    if (t.dataset.tier) return saveRouting({jobs: {tiers: {[t.dataset.tier]: {[t.dataset.role]: t.value}}}}, "已更新：之後新開始的背景工作會用新的模型搭配。");
    if (t.dataset.sfbase) return saveRouting({jobs: {stepfunBase: t.value}}, "已更新 StepFun 方案。");
  });
  // 等待登入／安裝：超過 limit 秒還沒完成就顯示失敗（背景仍會再看一陣子）
  function aiPoll(until, ms, limit, onFail){ clearInterval(aiTimer); const t0 = Date.now(); let failed = false; aiTimer = setInterval(async () => { let s = {}; try { s = await checkEngine(); } catch (e) {} const sec = (Date.now() - t0) / 1000;
    if (until(s)){ clearInterval(aiTimer); aiBusy = ""; renderAI(); return; }
    if (limit && !failed && sec > limit){ failed = true; aiBusy = ""; renderAI(); if (onFail) onFail(s); }
    if (sec > Math.max(300, (limit || 0) * 3)){ clearInterval(aiTimer); aiBusy = ""; renderAI(); if (!failed && onFail) onFail(s); } }, ms || 3000); }

  document.addEventListener("input", e => { if (e.target && e.target.id === "agyCode") AGYCODE = e.target.value; });
  document.addEventListener("keydown", e => { if (e.target && e.target.id === "agyCode" && e.key === "Enter" && !e.isComposing){ e.preventDefault(); const b = document.querySelector('[data-agy="send"]'); if (b) b.click(); } });
  document.addEventListener("change", e => { if (e.target && e.target.id === "aiAuto") post("ai-settings", {autoSwitch: e.target.checked}).catch(() => {}); });
  document.addEventListener("click", async e => {
    if (!ROOT || !ROOT.contains(e.target)) return;
    const ag = e.target.closest("[data-agy]");
    if (ag){ const a = ag.dataset.agy;
      if (a === "send"){ const c = ((document.getElementById("agyCode") || {}).value || "").trim(); if (!c) return; ag.disabled = true; ag.textContent = "送出中…";
        try { AGYS = await post("ai-agy", {action: "code", code: c}); AGYCODE = ""; } catch (err) { AGYS = Object.assign({}, AGYS, {error: (err && err.error) || "送出失敗"}); } renderAI(); agyWatch(); }
      if (a === "restart") agyStart();
      if (a === "cancel"){ try { await post("ai-agy", {action: "cancel"}); } catch (err) {} clearInterval(agyTimer); AGYS = null; renderAI(); }
      return; }
    const mb = e.target.closest("[data-model]");
    if (mb){ if (aiBusy) return; const pv = mb.dataset.mpv, mo = mb.dataset.model, s = AI[pv] || {}; PV = pv;
      if (mo === s.model) return; const name = ((s.models || []).find(x => x.v === mo) || {}).name || mo;
      aiBusy = "model"; renderAI(); let r = {};
      try { r = await post("ai-model", {provider: pv, model: mo}, 120000); } catch (err) { r = {ok: false, error: (err && err.error) || "切換失敗"}; }
      aiBusy = ""; await checkEngine();
      msg(r.ok ? `已換成 <b>${esc(name)}</b>，重新連線成功 ✓` : esc(r.error || ("換成 " + name + " 後連線失敗：" + ((r.tested || {}).msg || ""))));
      return; }
    const pb = e.target.closest("[data-pv]");
    if (pb){ const k = pb.dataset.pv; PV = k; if (aiReady(k) && defAI() !== k) setDefault(k); else renderAI(); return; }
    const sf = e.target.closest("[data-sf]");
    if (sf){ const a = sf.dataset.sf;
      if (a === "edit"){ KEYEDIT = true; renderAI(); const i = document.getElementById("sfKey"); if (i) i.focus(); return; }
      if (a === "cancel"){ KEYEDIT = false; renderAI(); return; }
      if (a === "remove"){ if (!confirm("移除 StepFun 的 key？用 StepFun 的工作會改回自動或預設那位。")) return;
        try { await post("ai-key", {provider: "stepfun", remove: true}); } catch (err) {} KEYEDIT = false; await checkEngine(); msg("已移除 StepFun 的 key。"); return; }
      if (a === "save"){ const i = document.getElementById("sfKey"), v = (i && i.value || "").trim(); if (!v) return;
        aiBusy = "test"; renderAI(); msg('<span class="spin"></span>儲存並測試連線中…');
        try { await post("ai-key", {provider: "stepfun", key: v}, 90000); KEYEDIT = false; } catch (err) { aiBusy = ""; renderAI(); msg(esc((err && err.error) || "沒有存到")); return; }
        aiBusy = ""; await checkEngine(); return; }
    }
    const b = e.target.closest("[data-act]"); if (!b) return; const act = b.dataset.act, pv = PV; delete AINOTE[pv];
    if (act === "install"){ aiBusy = "install"; renderAI(); try { await post("ai-install", {provider: pv}); } catch (err) { aiBusy = ""; renderAI(); msg(esc((err && err.error) || "沒辦法開始安裝")); return; }
      aiPoll(s => !s.installing && (s.installDone || (s.installed && !s.needsAgy)), 3000, 300, () => msg("安裝超過 5 分鐘還沒完成，當作失敗。可以再按一次。")); }
    if (act === "login" && pv === "gemini" && /Antigravity/.test((AI[pv] || {}).tool || "")){ agyStart(); return; }
    if (act === "login"){ aiBusy = "login"; renderAI(); try { await post("ai-login", {provider: pv}); } catch (err) { aiBusy = ""; renderAI(); msg(esc((err && err.error) || "沒辦法開始登入")); return; } aiBusy = "";
      aiPoll(s => s.loggedIn === true && !s.loggingIn, 3000, 60, () => { AINOTE[pv] = "按下登入後 60 秒還沒完成，當作失敗。如果一直沒有看到登入網頁，請按「用終端機登入」，在跳出來的視窗裡照指示登入。"; renderAI(); }); }
    if (act === "logout"){ if (!confirm(`登出 ${AI[pv].name}？\n\n這台電腦上的 ${AI[pv].tool} 會整個登出（你在其他地方用它也會受影響），之後要重新登入。`)) return;
      try { await post("ai-logout", {provider: pv}); } catch (err) { msg(esc((err && err.error) || "登出失敗")); return; } await checkEngine(); msg(`已登出 ${esc(AI[pv].name)}，按「登入」用另一個帳號登入。`); return; }
    if (act === "terminal"){ try { await post("ai-terminal", {provider: pv}); msg(`已打開一個終端機視窗，裡面是 ${esc(AI[pv].name)}。照畫面完成登入或驗證（有問「是否信任這個資料夾」就選信任），看到可以輸入文字時就完成了，關掉視窗後回來按「測試連線」。`); } catch (err) { msg("沒辦法打開終端機"); } return; }
    if (act === "test"){ aiBusy = "test"; renderAI(); let terr = ""; try { await post("ai-test", {provider: pv}, 90000); } catch (err) { terr = (err && err.error) || ""; } aiBusy = ""; await checkEngine(); if (terr) msg(esc(terr)); }
  });

  // 設定頁「AI 小幫手」那一列：畫框架，第一次打開時讀三位的狀態
  window.aiHelperHTML = () => `<div class="aibox" id="aiBox"><div class="aipick" role="group" aria-label="四位 AI"><div class="note small muted"><span class="spin"></span>讀取中…</div></div>
    <div class="aiact"></div><div class="aimsg" aria-live="polite"></div>
    <label class="small"><input type="checkbox" id="aiAuto" checked> 這位額度用完、沒登入或沒回應時，自動換下一位已測試成功的 AI</label>
    <div class="airoute"></div></div>`;
  window.aiHelperMount = () => { ROOT = document.getElementById("aiBox"); if (!ROOT) return; if (Object.keys(AI).length) renderAI(); checkEngine(); };
  // 每 5 分鐘更新一次（血條、暫停）
  setInterval(() => { if (ROOT && document.body.contains(ROOT) && !aiBusy && !document.hidden) checkEngine().catch(() => {}); }, 5 * 60 * 1000);

  // 畫面錯誤（白畫面、按了沒反應）：送到程式，寫進會同步的 _logs，別台電腦或 Claude 也看得到
  const report = msg => { try { fetch("/api/client-error", {method: "POST", headers: {"Content-Type": "application/json", "X-Phdeasy-App": "1"},
    body: JSON.stringify({page: location.pathname + location.search, msg: String(msg).slice(0, 4000)})}).catch(() => {}); } catch (e) {} };
  window.addEventListener("error", e => report(`${e.message} @ ${e.filename}:${e.lineno}:${e.colno}\n${e.error && e.error.stack || ""}`));
  window.addEventListener("unhandledrejection", e => report("未處理的錯誤：" + ((e.reason && (e.reason.stack || e.reason.message)) || e.reason)));
  // 設定頁 15 秒後還是空白：記下來（看得出是程式沒回應還是畫面壞掉）
  if (/settings\.html$/.test(location.pathname)) setTimeout(() => {
    const p = document.querySelector("#pipeline .body"), s = document.querySelector("#settings .body");
    if (p && s && !p.textContent.trim() && !s.textContent.trim()){
      const t0 = Date.now();
      fetch("/api/status", {cache: "no-store"}).then(r => report(`設定頁 15 秒還是空白；再要一次狀態：${r.status}，${Date.now() - t0} ms`), e => report("設定頁 15 秒還是空白；狀態要不到：" + e));
    } }, 15000);

  // 通知：自動換 AI、全部不能用（每 15 秒看一次，任何一頁都會跳）
  let since = Date.now() - 60000;
  const show = a => { const d = document.createElement("div"); d.className = "aialert" + (a.level === "bad" ? " bad" : ""); d.setAttribute("role", "status");
    d.innerHTML = `<span>${esc(a.msg)}</span><button type="button">知道了</button>`; d.querySelector("button").onclick = () => d.remove(); document.body.appendChild(d);
    if (a.level !== "bad") setTimeout(() => d.remove(), 8000); };
  const poll = async () => { try { const j = await post("ai-alerts", {since}, 10000); (j.alerts || []).forEach(show); if (j.now) since = j.now; } catch (e) {} setTimeout(poll, 15000); };
  if (location.protocol.startsWith("http")) setTimeout(poll, 3000);
})();
