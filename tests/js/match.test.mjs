// 首頁比對的邏輯測試（node 執行；由 tests/test_match_js.py 呼叫）
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const src = readFileSync(new URL("../../web/site_match.js", import.meta.url), "utf8");
const M = new Function(src + "; return { tokenize, expandQuery, buildIndex, rankDocs, displayTerms };")();

// 斷詞：英文詞（去複數）＋中文雙字
assert.deepEqual(M.tokenize("Chatbots for Women"), ["chatbot", "women"]);
assert.ok(M.tokenize("聊天機器人").includes("機器"));

// 跨語擴充：中文查詢會帶出英文同義詞
assert.ok(M.expandQuery("我想做身體活動的聊天機器人").includes("chatbot"));
assert.ok(M.expandQuery("physical activity").includes("身體"));

const docs = [
  { id: "W1", kind: "paper", text: "AI HeartBot chatbot increases women's heart attack knowledge 聊天機器人 女性 心臟病" },
  { id: "W2", kind: "paper", text: "Physical activity app for Asian Americans 身體活動 亞裔 手機應用" },
  { id: "W3", kind: "paper", text: "Readmission of children on mechanical ventilation 兒童 呼吸器 再入院" },
];
const idx = M.buildIndex(docs);

// 中文輸入要能比對到含英文的文章，並列出命中的詞
const r = M.rankDocs("我想用聊天機器人幫助女性預防心臟病", idx);
assert.equal(r[0].id, "W1");
assert.ok(r[0].matched.length >= 2);
assert.ok(r.every(x => x.score > 0));

// 方法與族群：英文輸入
const r2 = M.rankDocs("mobile app to increase physical activity", idx);
assert.equal(r2[0].id, "W2");

// 完全不相關的輸入不會硬湊結果
assert.deepEqual(M.rankDocs("量子電腦晶片製程", idx), []);

// 空輸入
assert.deepEqual(M.rankDocs("   ", idx), []);
// 一般性學術詞不算主題
const gen = M.tokenize("本研究分析結果顯示目的");
assert.ok(!gen.includes("研究") && !gen.includes("分析") && !gen.includes("結果") && !gen.includes("顯示"));
// 顯示用：把命中的雙字片段還原成完整詞（來自本人輸入與中英對照表），不顯示「體活」這種碎片
const shown = M.displayTerms("我想做身體活動、chatbot", ["身體", "體活", "活動", "physical", "activity", "chatbot", "聊天"]);
assert.ok(shown.includes("身體活動") && shown.includes("chatbot") && shown.includes("physical activity"));
assert.ok(!shown.includes("體活") && !shown.includes("身體"));
// 一般性健康研究用詞不算主題命中
const g2 = M.tokenize("Health interventions for patients with disease: clinical information evaluation");
assert.deepEqual(g2, []);
// 顯示詞去掉標點
assert.ok(!M.displayTerms("chatbot evaluation.", ["chatbot"]).some(t => /[.,;]$/.test(t)));
console.log("ok");
