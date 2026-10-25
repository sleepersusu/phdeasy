// 首頁個人化比對：在瀏覽器本機算，輸入不離開本人電腦。
// 中文用雙字詞、英文用詞幹；SYN 把常見研究詞中英互相帶出，讓中文輸入也比得到英文文章。
// 比對分數只是重疊程度，不是「適不適合」的判斷。

const STOP_EN = new Set(("the a an and or of for to in on at by with from into as is are was were be been this that these those it its we our you your they their study studies research use using used based among between within via than more most also can may will would should could about over under after before during each per new two one " +
  // 健康研究裡到處都有、不代表主題的詞
  "health intervention disease patient clinical controlled information evaluation outcome data program care risk approach adult participant result method analysis effect associated increase").split(" "));
const STOP_ZH_BI = new Set("研究 本研 究分 分析 析結 結果 果顯 顯示 示目 目的 方法 我們 進行 相關 影響 探討 本文 以及 透過 可能 其中 發現 顯著 提升 增加 包括 主要 使用 參與 參與者 與者 此研 這項".split(" "));
const STOP_ZH_CHARS = "的我你他她想做用和與在是了也就都很及或為並於等這那些個要能可以會把被讓對從到".split("");

const SYN = [
  ["chatbot", "聊天機器人", "聊天", "conversational agent", "對話"],
  ["ai", "artificial intelligence", "人工智慧", "llm", "大型語言模型", "generative"],
  ["physical activity", "身體活動", "運動", "步數", "exercise", "walking", "steps", "活動量"],
  ["women", "女性", "婦女"],
  ["heart", "心臟", "心臟病", "cardiovascular", "心血管", "cvd", "heart attack", "心肌梗塞"],
  ["diabetes", "糖尿病", "prediabetes", "糖尿病前期"],
  ["weight", "體重", "減重", "肥胖", "obesity"],
  ["app", "應用程式", "手機", "mobile", "smartphone", "mhealth", "行動健康", "digital", "數位", "wearable", "穿戴"],
  ["text message", "簡訊", "sms"],
  ["rct", "隨機對照", "randomized", "隨機", "trial", "試驗"],
  ["qualitative", "質性", "訪談", "interview", "focus group", "焦點團體"],
  ["survey", "問卷", "調查", "cross-sectional", "橫斷"],
  ["machine learning", "機器學習", "prediction", "預測", "模型", "model"],
  ["systematic review", "系統性回顧", "文獻回顧", "review"],
  ["cancer", "癌症", "癌", "oncology", "colorectal", "大腸直腸"],
  ["older adults", "長者", "老人", "高齡", "aging", "老化", "elderly"],
  ["children", "兒童", "pediatric", "小兒"],
  ["nursing", "護理", "nurse", "護理師"],
  ["knowledge", "知識", "認知", "awareness", "覺察"],
  ["depression", "憂鬱", "depressive", "mental health", "心理健康"],
  ["asian", "亞裔", "filipino", "菲律賓", "chinese", "華人", "vietnamese", "越南"],
  ["self-efficacy", "自我效能"],
  ["behavior change", "行為改變", "behavioral", "行為"],
  ["quality of life", "生活品質"],
  ["social media", "社群媒體", "facebook", "twitter"],
  ["health disparities", "健康不平等", "disparities", "弱勢", "minority", "少數族群"],
];

function stem(w) {
  if (w.endsWith("'s")) w = w.slice(0, -2);
  if (w.length > 4 && w.endsWith("ies")) return w.slice(0, -3) + "y";
  if (w.length > 3 && w.endsWith("s") && !w.endsWith("ss")) return w.slice(0, -1);
  return w;
}

function tokenize(text) {
  const t = String(text || "").toLowerCase();
  const out = [];
  for (const m of t.matchAll(/[a-z][a-z0-9'-]*/g)) {
    for (const part of m[0].split("-")) {
      const w = stem(part.replace(/'$/, ""));
      if (w.length >= 2 && !STOP_EN.has(w)) out.push(w);
    }
  }
  for (const m of t.matchAll(/[一-鿿]+/g)) {
    const run = m[0];
    for (let i = 0; i + 1 < run.length; i++) {
      const bi = run.slice(i, i + 2);
      if (!STOP_ZH_CHARS.includes(bi[0]) && !STOP_ZH_CHARS.includes(bi[1]) && !STOP_ZH_BI.has(bi)) out.push(bi);
    }
  }
  return out;
}

function expandQuery(q) {
  const low = String(q || "").toLowerCase();
  const extra = [];
  for (const group of SYN) {
    if (group.some(term => low.includes(term.toLowerCase()))) extra.push(...group);
  }
  return [q, ...extra].join(" ");
}

function buildIndex(docs) {
  const df = new Map();
  const items = docs.map(d => {
    const tf = new Map();
    for (const tok of tokenize(d.text)) tf.set(tok, (tf.get(tok) || 0) + 1);
    for (const tok of tf.keys()) df.set(tok, (df.get(tok) || 0) + 1);
    return { ...d, tf };
  });
  return { items, df, n: docs.length };
}

function rankDocs(query, index) {
  if (!String(query || "").trim()) return [];
  const qtoks = [...new Set(tokenize(expandQuery(query)))];
  const out = [];
  for (const d of index.items) {
    let score = 0;
    const matched = [];
    for (const q of qtoks) {
      const tf = d.tf.get(q);
      if (!tf) continue;
      const idf = Math.log(1 + index.n / (index.df.get(q) || 1));
      score += idf * (1 + Math.log(tf));
      matched.push(q);
    }
    if (score > 0) out.push({ id: d.id, kind: d.kind, score, matched });
  }
  return out.sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
}

// 顯示用：候選詞＝本人輸入的分隔詞＋輸入中出現的中英對照組；某詞的所有斷詞都有命中才顯示該詞
function displayTerms(query, matched) {
  const hit = new Set(matched);
  const low = String(query || "").toLowerCase();
  const edge = new RegExp("^[" + STOP_ZH_CHARS.join("") + "]+|[" + STOP_ZH_CHARS.join("") + "]+$", "g");
  const cands = new Set(String(query || "").split(/[、，,;；。\s]+/).map(x => x.trim().replace(/[.,;:!?()]+$/, "").replace(edge, "")).filter(x => x && x.length <= 30));
  for (const group of SYN) if (group.some(t => low.includes(t.toLowerCase()))) group.forEach(t => cands.add(t));
  const out = [];
  for (const c of cands) {
    const toks = tokenize(c);
    if (toks.length && toks.every(t => hit.has(t)) && !out.includes(c)) out.push(c);
  }
  return out.sort((a, b) => b.length - a.length).filter((c, i, arr) => !arr.slice(0, i).some(longer => longer.toLowerCase().includes(c.toLowerCase())));
}
