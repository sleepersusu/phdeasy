"""OpenAlex 文章資料：標準化、去重、年份過濾。全部是純函式，網路呼叫在 setup_*.py。"""
import re
from difflib import SequenceMatcher

FULL_TYPES = {"article", "review", "preprint", "book-chapter", "dissertation", "report"}
PREPRINT_TITLE_RATIO = 0.80
NEAR_DUP_RATIO = 0.95


def strip_prefix(url):
    if not url:
        return None
    return url.rsplit("/", 1)[-1]


def bare_doi(doi):
    if not doi:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip()).lower()


def reconstruct_abstract(inv):
    if not inv:
        return None
    pos = [(i, word) for word, idxs in inv.items() for i in idxs]
    return " ".join(word for _, word in sorted(pos))


def card_kind(type_):
    return "full" if type_ in FULL_TYPES else "short"


def normalize_title(t):
    t = (t or "").lower()
    t = re.sub(r"^abstract\s+\d+\s*:\s*", "", t)
    return re.sub(r"[^\w]+", " ", t).strip()


def _similar(a, b):
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def normalize_work(w, target_author_id):
    authors = []
    target_pos, target_corr = None, False
    for a in w.get("authorships") or []:
        aid = strip_prefix((a.get("author") or {}).get("id"))
        authors.append(
            {
                "id": aid,
                "name": (a.get("author") or {}).get("display_name"),
                "orcid": (a.get("author") or {}).get("orcid"),
                "position": a.get("author_position"),
                "is_corresponding": bool(a.get("is_corresponding")),
                "institutions": [i.get("display_name") for i in a.get("institutions") or []],
            }
        )
        if aid == target_author_id:
            target_pos, target_corr = a.get("author_position"), bool(a.get("is_corresponding"))

    pdfs = []
    for loc in [w.get("best_oa_location")] + list(w.get("locations") or []):
        u = (loc or {}).get("pdf_url")
        if u and u not in pdfs:
            pdfs.append(u)

    ids = w.get("ids") or {}
    topic = w.get("primary_topic") or {}
    return {
        "id": strip_prefix(w["id"]),
        "doi": bare_doi(w.get("doi")),
        "title": w.get("title") or w.get("display_name"),
        "year": w.get("publication_year"),
        "type": w.get("type"),
        "kind": card_kind(w.get("type")),
        "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name"),
        "authors": authors,
        "target_position": target_pos,
        "target_corresponding": target_corr,
        "abstract": reconstruct_abstract(w.get("abstract_inverted_index")),
        "pdf_candidates": pdfs,
        "landing_pages": [
            (loc or {}).get("landing_page_url")
            for loc in [w.get("best_oa_location")] + list(w.get("locations") or [])
            if (loc or {}).get("landing_page_url")
        ],
        "pmcid": strip_prefix(ids.get("pmcid")),
        "pmid": strip_prefix(ids.get("pmid")),
        "topic": {
            "name": topic.get("display_name"),
            "subfield": (topic.get("subfield") or {}).get("display_name"),
            "field": (topic.get("field") or {}).get("display_name"),
            "domain": (topic.get("domain") or {}).get("display_name"),
        },
        "is_retracted": bool(w.get("is_retracted")),
        "merged_dois": [],
        "preprint_ids": [],
    }


def _jmir_pair(pre_doi, pub_doi):
    if not pre_doi or not pub_doi:
        return False
    m = re.match(r"10\.2196/preprints\.(\d+)$", pre_doi)
    return bool(m) and re.match(rf"10\.2196/{m.group(1)}$", pub_doi) is not None


def dedupe(works, year_from, year_to):
    """回傳 (kept, dropped)。dropped 每筆有 id、reason，合併者另有 kept。"""
    kept, dropped = [], []
    in_range = []
    for w in works:
        if w["year"] is None or not (year_from <= w["year"] <= year_to):
            dropped.append({"id": w["id"], "title": w["title"], "reason": "year_out_of_range"})
        else:
            in_range.append(w)

    by_doi = {}
    for w in in_range:
        if w["doi"] and w["doi"] in by_doi:
            dropped.append({"id": w["id"], "title": w["title"], "reason": "same_doi", "kept": by_doi[w["doi"]]["id"]})
            continue
        if w["doi"]:
            by_doi[w["doi"]] = w
        kept.append(w)

    published = [w for w in kept if w["type"] != "preprint"]
    final = []
    for w in kept:
        if w["type"] == "preprint":
            match = next((p for p in published if _jmir_pair(w["doi"], p["doi"])), None)
            if match is None:
                best = max(published, key=lambda p: _similar(p["title"], w["title"]), default=None)
                if best is not None and best["kind"] == "full" and _similar(best["title"], w["title"]) >= PREPRINT_TITLE_RATIO:
                    match = best
            if match is not None:
                match["preprint_ids"].append(w["id"])
                if w["doi"]:
                    match["merged_dois"].append(w["doi"])
                match["pdf_candidates"].extend(u for u in w["pdf_candidates"] if u not in match["pdf_candidates"])
                dropped.append({"id": w["id"], "title": w["title"], "reason": "preprint_of", "kept": match["id"]})
                continue
        final.append(w)

    for i, w in enumerate(final):
        for prev in final[:i]:
            if w["kind"] == prev["kind"] == "full" and _similar(w["title"], prev["title"]) >= NEAR_DUP_RATIO:
                w["possible_duplicate_of"] = prev["id"]
                break
    return final, dropped


def fill_target_by_name(work, surname):
    """OpenAlex 沒把目標作者連到作者 id 時（外部候選常見），用姓氏補作者序，並標 name_only。"""
    if work.get("target_position"):
        return work
    for a in work["authors"]:
        if surname.lower() in (a.get("name") or "").lower().split():
            work["target_position"] = a["position"]
            work["target_corresponding"] = a["is_corresponding"]
            work["target_link"] = "name_only"
            break
    return work


def apply_lead_scope(works):
    """範圍 A：本人是第一、最後或通訊作者的才做完整卡；其他完整卡改短卡並標 not_led（仍抓全文供計畫致謝用）。"""
    for w in works:
        led = w.get("target_position") in ("first", "last") or w.get("target_corresponding")
        if w["kind"] == "full" and not led:
            w["kind"], w["short_reason"] = "short", "not_led"
    return works


def apply_no_content(works, ids):
    """完整卡卻完全沒有內容（無全文也無摘要）的改成短卡，理由 no_content。"""
    for w in works:
        if w["id"] in ids and w["kind"] == "full":
            w["kind"], w["short_reason"] = "short", "no_content"
    return works
