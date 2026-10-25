// 讓 Python（首頁產生器）重用前端同一份比對邏輯：stdin 讀 {docs, query}，stdout 印排序結果
import { readFileSync } from "node:fs";
const src = readFileSync(new URL("../../web/site_match.js", import.meta.url), "utf8");
const M = new Function(src + "; return { buildIndex, rankDocs, displayTerms };")();
const { docs, query } = JSON.parse(readFileSync(0, "utf8"));
const ranked = M.rankDocs(query, M.buildIndex(docs)).map(r => ({ ...r, terms: M.displayTerms(query, r.matched) }));
process.stdout.write(JSON.stringify(ranked));
