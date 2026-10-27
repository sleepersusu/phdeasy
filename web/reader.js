/* 全文閱讀工具（學 ieltsgod 的閱讀題）：選取文字 → 螢光筆、清除、筆記、問 AI（可追問、可存成筆記）、翻成中文、收藏到計畫書素材。
   標記與筆記存在 runs/<教授>/annotations/<文章>.json（討論文獻在 library/annotations/），經雲端硬碟同步。
   格式：{段落 key: [[開始, 結束], …], "n:<key>": [[開始, 結束, 筆記 id], …], _notes: {id: {text, quote, t}}}
   用法：await Reader.load({slug, id, lib, title}) → 用 Reader.hl(key, 文字, 位置) 產生可標記的 HTML → Reader.bind(容器)。 */
const Reader = (() => {
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const post = (p, b) => fetch("/api/" + p, {method: "POST", headers: {"Content-Type": "application/json", "X-Phdeasy-App": "1"}, body: JSON.stringify(b || {})})
    .then(r => r.json().then(j => r.ok ? j : Promise.reject(j), () => Promise.reject({error: r.status === 404 ? "這個功能要用應用程式打開" : `應用程式回應錯誤（${r.status}）`})),
      () => Promise.reject({error: "連不到應用程式：請確認 phdeasy 還開著"}));
  const ic = (n, s = 16) => typeof icon === "function" ? icon(n, s) : "";
  const R = {ctx: null, store: null, ok: false, blocks: [], source: null, HLT: {}, LOC: {}};

  async function load(ctx){
    R.ctx = ctx;
    try {
      const j = await post("paper-text", {slug: ctx.slug, id: ctx.id, lib: !!ctx.lib});
      R.store = j.store || {}; R.blocks = j.blocks || []; R.source = j.source; R.zh = j.zh || {}; R.zhJob = j.zh_job; R.ok = true;
    } catch (e) { R.store = {}; R.ok = false; R.err = e && e.error; }
    return R;
  }
  let saveT = null;
  function save(){ if (!R.ok) return; clearTimeout(saveT); saveT = setTimeout(() => post("annot-save", {...R.ctx, store: R.store}).catch(e => toast((e && e.error) || "標記沒有存到")), 500); }

  // ---------- 畫出可標記的文字 ----------
  function hl(key, text, loc){
    text = String(text || ""); R.HLT[key] = text; if (loc) R.LOC[key] = loc;
    const S = R.store || {}, ms = (S[key] || []).filter(m => m[1] <= text.length).slice().sort((a, b) => a[0] - b[0]);
    const ns = (S["n:" + key] || []).filter(m => m[1] <= text.length), NT = S._notes || {};
    const cuts = new Set([0, text.length]); ms.forEach(m => { cuts.add(m[0]); cuts.add(m[1]); }); ns.forEach(m => { cuts.add(m[0]); cuts.add(m[1]); });
    const pts = [...cuts].sort((a, b) => a - b); let h = "";
    for (let k = 0; k < pts.length - 1; k++){
      const a = pts[k], b = pts[k + 1]; let seg = esc(text.slice(a, b));
      if (ms.some(m => a >= m[0] && b <= m[1])) seg = `<mark class="rd-hl">${seg}</mark>`;
      const n = ns.find(m => a >= m[0] && b <= m[1] && NT[m[2]]);
      if (n) seg = `<span class="rd-note" data-hn="${esc(n[2])}" title="筆記：${esc(NT[n[2]].text)}">${seg}</span>${b === n[1] ? `<sup class="rd-nmark" data-hn="${esc(n[2])}" aria-hidden="true">✎</sup>` : ""}`;
      h += seg;
    }
    return `<span data-hlk="${esc(key)}">${h}</span>`;
  }
  const rer = keys => keys.forEach(k => { const el = document.querySelector(`[data-hlk="${CSS.escape(k)}"]`); if (el) el.outerHTML = hl(k, R.HLT[k]); });

  // ---------- 小框框（可拖曳、不會跑出畫面） ----------
  function place(d, rect, w, hgt){ d.style.left = Math.max(8, Math.min(innerWidth - w, rect.left)) + "px"; d.style.top = Math.max(8, Math.min(innerHeight - hgt, rect.bottom + 8)) + "px"; }
  function dragBox(d){
    const bar = d.firstElementChild; bar.classList.add("rd-drag"); bar.title = "按住拖曳可以移動";
    const fit = () => { const r = d.getBoundingClientRect(); d.style.left = Math.max(4, Math.min(innerWidth - r.width - 4, r.left)) + "px"; d.style.top = Math.max(4, Math.min(innerHeight - r.height - 4, r.top)) + "px"; };
    bar.addEventListener("pointerdown", e => {
      if (e.button !== 0 || e.target.closest("button")) return; e.preventDefault();
      const r = d.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top; bar.setPointerCapture(e.pointerId);
      const mv = ev => { d.style.left = (ev.clientX - dx) + "px"; d.style.top = (ev.clientY - dy) + "px"; fit(); };
      const up = () => { bar.removeEventListener("pointermove", mv); bar.removeEventListener("pointerup", up); };
      bar.addEventListener("pointermove", mv); bar.addEventListener("pointerup", up);
    });
    try { new ResizeObserver(fit).observe(d); } catch (e) {}
  }
  let boxEl = null, popEl = null;
  const boxClose = () => { if (boxEl){ boxEl.remove(); boxEl = null; } };
  const popClose = () => { if (popEl){ popEl.remove(); popEl = null; } };
  const md = t => esc(t).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br>");

  function noteBox(rect, text, onSave, onDel){
    popClose(); boxClose(); const d = document.createElement("div"); d.className = "rd-box"; boxEl = d;
    d.innerHTML = `<div class="rd-bar"><b>${ic("edit", 15)} 筆記</b><button type="button" class="rd-x" data-nb="x" aria-label="關閉">${ic("x", 15)}</button></div>
      <textarea rows="4" maxlength="5000" placeholder="寫下你的筆記，例如：這裡的樣本跟我的研究 1 很像，可以問她怎麼招募">${esc(text || "")}</textarea>
      <div class="rd-row"><button type="button" class="rd-btn primary" data-nb="save">儲存</button>${onDel ? `<button type="button" class="rd-btn" data-nb="del">刪除筆記</button>` : ""}<span class="rd-hint">⌘/Ctrl＋Enter 儲存</span></div>`;
    document.body.appendChild(d); place(d, rect, 340, 220); dragBox(d);
    const ta = d.querySelector("textarea"); ta.focus(); ta.selectionStart = ta.value.length;
    ta.addEventListener("keydown", e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)){ e.preventDefault(); d.querySelector('[data-nb="save"]').click(); } if (e.key === "Escape") boxClose(); });
    d.addEventListener("click", e => { const b = e.target.closest("[data-nb]"); if (!b) return; const k = b.dataset.nb;
      if (k === "save"){ const v = ta.value.trim(); boxClose(); if (v) onSave(v); else if (onDel) onDel(); }
      else if (k === "del"){ boxClose(); onDel(); } else boxClose(); });
  }

  // 問 AI：在框框裡打問題，回答顯示在框框裡；可以一直追問，也可以把問答存成筆記。translate=true：直接翻成中文
  function askBox(rect, sel, ctx, onNote, translate){
    popClose(); boxClose(); const d = document.createElement("div"); d.className = "rd-box rd-ask"; boxEl = d;
    const H = []; let busy = false;
    const paint = () => { const lg = d.querySelector(".rd-log");
      lg.innerHTML = H.map(h => `${h.q ? `<div class="rd-q">${esc(h.q)}</div>` : ""}<div class="rd-a">${h.a == null ? `<span class="rd-hint">AI 回答中…</span>` : h.err ? `<span class="rd-err">${esc(h.err)}</span>` : md(h.a)}</div>`).join("");
      lg.scrollTop = lg.scrollHeight; d.querySelector('[data-ak="note"]').hidden = !H.some(h => h.a); };
    d.innerHTML = `<div class="rd-bar"><b>${ic(translate ? "translate" : "chat", 15)} ${translate ? "翻成中文" : "問 AI"}</b><button type="button" class="rd-x" data-ak="x" aria-label="關閉">${ic("x", 15)}</button></div>
      <div class="rd-quote" lang="en">${esc(sel.length > 220 ? sel.slice(0, 220) + "…" : sel)}</div><div class="rd-log" aria-live="polite"></div>
      <textarea rows="2" maxlength="1000" placeholder="${translate ? "對譯文有疑問可以接著問" : "想問什麼？例如：這個研究設計是什麼意思？樣本怎麼來的？"}"></textarea>
      <div class="rd-row"><button type="button" class="rd-btn primary" data-ak="send">送出</button><button type="button" class="rd-btn" data-ak="note" hidden>存成筆記</button><span class="rd-hint" data-hint>按兩次 Enter 送出・Shift＋Enter 換行</span></div>`;
    document.body.appendChild(d); place(d, rect, 400, 440); dragBox(d);
    const ta = d.querySelector("textarea");
    const run = async (q, path) => { busy = true; const h = {q, a: null}; H.push(h); paint();
      try { const r = await post(path, {sel, ctx, title: R.ctx && R.ctx.title, q: q || "", history: H.slice(0, -1).filter(x => x.a).map(x => ({q: x.q || "（翻成中文）", a: x.a}))}); h.a = r.a || ""; }
      catch (e) { h.err = (e && e.error) || "AI 沒有回應，請再試一次"; h.a = ""; }
      busy = false; if (boxEl === d){ paint(); ta.focus(); } };
    const send = () => { const q = ta.value.trim(); if (!q || busy) return; ta.value = ""; run(q, "ask"); };
    if (translate) run("", "translate"); else ta.focus();
    // 按兩次 Enter 才送出：注音選字時按的 Enter 不會誤送
    let armed = 0; const hint = d.querySelector("[data-hint]"), hint0 = hint.textContent, disarm = () => { armed = 0; hint.textContent = hint0; };
    ta.addEventListener("keydown", e => {
      if (e.key === "Escape"){ boxClose(); return; }
      if (e.isComposing || e.keyCode === 229) return;
      if (e.key === "Enter" && !e.shiftKey){ e.preventDefault(); if (!ta.value.trim()) return;
        if (armed && Date.now() - armed < 1500){ disarm(); send(); } else { const t = armed = Date.now(); hint.textContent = "再按一次 Enter 送出"; setTimeout(() => { if (armed === t) disarm(); }, 1500); } return; }
      if (armed) disarm();
    });
    d.addEventListener("click", e => { const b = e.target.closest("[data-ak]"); if (!b) return; const k = b.dataset.ak;
      if (k === "x") boxClose(); else if (k === "send") send();
      else if (k === "note" && onNote){ const txt = H.filter(x => x.a).map(x => (x.q ? "Q：" + x.q + "\nA：" : "譯：") + x.a.replace(/\*\*/g, "")).join("\n\n"); boxClose(); onNote(txt); } });
  }

  function toast(msg){ const d = document.createElement("div"); d.className = "rd-toast"; d.setAttribute("role", "status"); d.textContent = msg; document.body.appendChild(d); setTimeout(() => d.remove(), 3200); }
  const offset = (el, node, off) => { const r = document.createRange(); r.selectNodeContents(el); try { r.setEnd(node, off); } catch (e) { return 0; } return r.toString().length; };
  const noteKeys = id => Object.keys(R.store).filter(k => k.startsWith("n:") && (R.store[k] || []).some(m => m[2] === id)).map(k => k.slice(2));

  function addNote(rect, key, s, e, init){
    noteBox(rect, init || "", v => {
      const id = "n" + Date.now(); R.store._notes = R.store._notes || {};
      R.store._notes[id] = {text: v, t: Date.now(), quote: (R.HLT[key] || "").slice(s, e).slice(0, 400)};
      (R.store["n:" + key] = R.store["n:" + key] || []).push([s, e, id]); rer([key]); save(); toast("筆記已存");
    });
  }

  // ---------- 選取 → 工具列 ----------
  function bind(root){
    root.addEventListener("click", ev => {
      const n = ev.target.closest("[data-hn]"); if (!n) return;
      const sel = getSelection(); if (sel && !sel.isCollapsed) return;
      const id = n.dataset.hn, nt = (R.store._notes || {})[id]; if (!nt) return; ev.preventDefault();
      const keys = noteKeys(id);
      noteBox(n.getBoundingClientRect(), nt.text, v => { nt.text = v; nt.t = Date.now(); rer(keys); save(); },
        () => { keys.forEach(k => { R.store["n:" + k] = (R.store["n:" + k] || []).filter(m => m[2] !== id); if (!R.store["n:" + k].length) delete R.store["n:" + k]; }); delete R.store._notes[id]; rer(keys); save(); });
    });
    const go = () => setTimeout(() => {
      const sel = getSelection(); if (!sel || sel.isCollapsed || !sel.rangeCount) return;
      const r = sel.getRangeAt(0), host = n => { const el = n.nodeType === 1 ? n : n.parentElement; return el && el.closest("[data-hlk]"); };
      const a = host(r.startContainer), b = host(r.endContainer);
      if (!a || a !== b || !root.contains(a)){ if (a || b) toast("一次選一段裡面的文字"); return; }
      const key = a.dataset.hlk, s = offset(a, r.startContainer, r.startOffset), e = offset(a, r.endContainer, r.endOffset); if (e - s < 1) return;
      const txt = sel.toString().trim(), rc = r.getBoundingClientRect(), has = (R.store[key] || []).some(m => m[0] < e && m[1] > s);
      popClose(); popEl = document.createElement("div"); popEl.className = "rd-pop"; popEl.setAttribute("role", "toolbar"); popEl.setAttribute("aria-label", "選取文字的工具");
      const B = (k, n, label) => `<button type="button" class="rd-btn" data-hl="${k}">${ic(n, 15)}<span>${label}</span></button>`;
      popEl.innerHTML = B("add", "highlight", "螢光筆") + (has ? B("rm", "eraser", "清除") : "") + B("note", "edit", "筆記") + B("ask", "chat", "問 AI") + B("tr", "translate", "翻成中文") + B("clip", "bookmark", "收藏素材");
      document.body.appendChild(popEl);
      popEl.style.left = Math.max(8, Math.min(innerWidth - popEl.offsetWidth - 8, rc.left)) + "px";
      popEl.style.top = Math.max(8, rc.top > 60 ? rc.top - popEl.offsetHeight - 8 : rc.bottom + 8) + "px";
      if (!R.ok) popEl.querySelectorAll("button").forEach(x => { x.disabled = true; x.title = R.err || "要用應用程式打開才能標記"; });
      popEl.onclick = ev => {
        const k = ev.target.closest("[data-hl]"); if (!k) return; const act = k.dataset.hl;
        const ctx = (R.HLT[key] || "").slice(Math.max(0, s - 1500), e + 1500);
        sel.removeAllRanges(); popClose();
        if (act === "note") return addNote(rc, key, s, e);
        if (act === "ask" || act === "tr") return askBox(rc, txt, ctx, v => addNote(rc, key, s, e, v), act === "tr");
        if (act === "clip") return post("clip-add", {text: txt, slug: R.ctx.slug, paper: R.ctx.id, lib: !!R.ctx.lib, title: R.ctx.title, loc: R.LOC[key] || ""})
          .then(c => toast(c.dup ? "這段已經收藏過了" : "已收藏到計畫書素材（首頁「研究計畫書」看得到）"), err => toast((err && err.error) || "收藏失敗"));
        let L = (R.store[key] || []).slice();
        if (act === "add"){ L.push([s, e]); L.sort((x, y) => x[0] - y[0]); const M = []; L.forEach(m => { const z = M[M.length - 1]; if (z && m[0] <= z[1]) z[1] = Math.max(z[1], m[1]); else M.push(m.slice()); }); L = M; }
        else L = L.flatMap(m => m[1] <= s || m[0] >= e ? [m] : [[m[0], s], [e, m[1]]].filter(x => x[1] > x[0]));
        if (L.length) R.store[key] = L; else delete R.store[key];
        rer([key]); save();
      };
    }, 0);
    root.addEventListener("mouseup", go); root.addEventListener("touchend", go);
  }
  document.addEventListener("mousedown", e => { if (popEl && !popEl.contains(e.target)) popClose(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") popClose(); });

  // 這篇所有的筆記（給「我的筆記」列表）
  const notes = () => Object.entries((R.store && R.store._notes) || {}).map(([id, n]) => ({id, ...n, key: noteKeys(id)[0]})).sort((a, b) => a.t - b.t);
  // 整篇翻成中文（背景一批一批翻）：回傳最新的 {zh, job}
  async function translateAll(){ await post("paper-translate", R.ctx); return refreshZh(); }
  async function refreshZh(){ const j = await post("paper-text", R.ctx); R.zh = j.zh || {}; R.zhJob = j.zh_job; return R; }
  return {load, hl, bind, notes, toast, translateAll, refreshZh, get state(){ return R; }};
})();
