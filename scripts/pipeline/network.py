"""合作與領域：全部用腳本算，不讓 LLM 數。合作者以 OpenAlex 作者 id 計數；沒 id 的用正規化姓名，標 linked=False。"""
from collections import Counter, defaultdict


def _norm_name(name):
    return " ".join((name or "").split())


def _key(a):
    return a["id"] if a.get("id") else "name:" + _norm_name(a.get("name")).lower()


def _sig(name):
    parts = _norm_name(name).lower().replace(".", "").split()
    return (parts[-1], parts[0][0]) if parts else None


def _name_links(works, target_id, surname):
    """沒 id 的作者：姓氏＋名字首字母只對得上唯一一位有 id 的作者時，回傳 {名字: 該 id}。"""
    by_sig = defaultdict(set)
    orcid_of = {}
    for w in works:
        for a in w.get("authors") or []:
            if a.get("id") and a["id"] != target_id:
                by_sig[_sig(a.get("name"))].add(a["id"])
                if a.get("orcid"):
                    orcid_of[a["id"]] = a["orcid"]
    links = {}
    for w in works:
        for a in w.get("authors") or []:
            if not a.get("id") and not _is_target(a, target_id, surname):
                ids = by_sig.get(_sig(a.get("name")), set())
                if len(ids) == 1:
                    aid = next(iter(ids))
                    if a.get("orcid") and orcid_of.get(aid) and a["orcid"] != orcid_of[aid]:
                        continue  # ORCID 不同，不是同一人
                    links[_norm_name(a.get("name"))] = aid
    return links


def _is_target(a, target_id, surname):
    if a.get("id"):
        return a["id"] == target_id
    return surname.lower() in _norm_name(a.get("name")).lower().split()


def coauthor_stats(works, target_id, surname, aliases=None):
    """aliases：本人在停 2 決定合併的作者 id {別名 id: 主 id}。"""
    aliases = aliases or {}
    acc = defaultdict(lambda: {"names": Counter(), "merged": set(), "owner_ids": set(), "works": [], "years": Counter(), "insts": Counter(), "first": 0, "last": 0, "corr": 0})
    links = _name_links(works, target_id, surname)
    for w in works:
        seen = set()
        for a in w.get("authors") or []:
            if _is_target(a, target_id, surname):
                continue
            name = _norm_name(a.get("name"))
            k = _key(a) if a.get("id") else links.get(name, _key(a))
            alias_of = k if k in aliases else None
            k = aliases.get(k, k)
            if k in seen:
                continue
            seen.add(k)
            s = acc[k]
            if alias_of:
                s["owner_ids"].add(alias_of)
            if a.get("id") or not k.startswith("A"):
                s["names"][name] += 1
            else:
                s["merged"].add(name)
            s["works"].append(w["id"])
            s["years"][w.get("year")] += 1
            for i in a.get("institutions") or []:
                s["insts"][i] += 1
            s["first"] += a.get("position") == "first"
            s["last"] += a.get("position") == "last"
            s["corr"] += bool(a.get("is_corresponding"))
    out = []
    for k, s in acc.items():
        name = sorted((s["names"] or Counter(s["merged"])).items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        out.append(
            {
                "key": k,
                "name": name,
                "linked": not k.startswith("name:"),
                "merged_names": sorted(s["merged"]),
                "owner_merged_ids": sorted(s["owner_ids"]),
                "n": len(s["works"]),
                "works": sorted(s["works"]),
                "years": dict(sorted(s["years"].items())),
                "institutions": sorted(s["insts"].items(), key=lambda kv: (-kv[1], kv[0])),
                "as_first": s["first"],
                "as_last": s["last"],
                "as_corresponding": s["corr"],
            }
        )
    out.sort(key=lambda s: (-s["n"], s["name"].lower(), s["key"]))
    return out


def role_summary(works):
    r = {"first": 0, "middle": 0, "last": 0, "unknown": 0, "corresponding": 0, "total": len(works)}
    for w in works:
        r[w.get("target_position") if w.get("target_position") in ("first", "middle", "last") else "unknown"] += 1
        r["corresponding"] += bool(w.get("target_corresponding"))
    return r


def topic_counts(works):
    out = {}
    for level in ("domain", "field", "subfield", "topic"):
        key = "name" if level == "topic" else level
        c = Counter((w.get("topic") or {}).get(key) or "（未分類）" for w in works)
        out[level] = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
    return out


def year_counts(works):
    return dict(sorted(Counter(w.get("year") for w in works).items()))


def author_lists_md(works, target_id, surname, aliases=None):
    """給計數 agent 的輸入：每篇一節，列出所有作者與用來計數的 id。不附任何統計結果。"""
    aliases = aliases or {}
    links = _name_links(works, target_id, surname)
    lines = ["# 作者清單", ""]
    for w in sorted(works, key=lambda w: w["id"]):
        lines.append(f"## {w['id']}")
        for a in w.get("authors") or []:
            name = _norm_name(a.get("name"))
            if _is_target(a, target_id, surname):
                tag = "本人"
            elif a.get("id") in aliases:
                tag = f"{aliases[a['id']]}，本人決定合併 {a['id']}"
            elif a.get("id"):
                tag = a["id"]
            elif name in links:
                tag = f"{links[name]}，姓名對應"
            else:
                tag = "無 id"
            lines.append(f"- {name} ({tag})")
        lines.append("")
    return "\n".join(lines)


def compare_counts(stats, agent, top=10, min_n=1):
    """比對腳本與計數 agent。範圍：腳本前 top 名（含同分）中 n ≥ min_n 的人，加上 agent 列出的所有人。"""
    script = {s["key"]: s["n"] for s in stats}
    ranked = [s for s in stats if s["n"] >= min_n]
    cut = ranked[top - 1]["n"] if len(ranked) >= top else (ranked[-1]["n"] if ranked else 0)
    keys = {s["key"] for s in ranked if s["n"] >= cut}
    agent_n = {a["key"]: a["n"] for a in agent}
    keys |= set(agent_n)
    diffs = []
    for k in sorted(keys):
        if script.get(k, 0) != agent_n.get(k, 0):
            diffs.append({"key": k, "script": script.get(k, 0), "agent": agent_n.get(k, 0)})
    return diffs


def _compatible(x, y):
    """同姓，名字相容（相同或一方是另一方的首字母），兩邊都有中間名時也要相容。"""
    tx = _norm_name(x).lower().replace(".", " ").replace("-", " ").split()
    ty = _norm_name(y).lower().replace(".", " ").replace("-", " ").split()
    if len(tx) < 2 or len(ty) < 2 or tx[-1] != ty[-1]:
        return False
    ok = lambda a, b: a == b or (len(a) == 1 and b.startswith(a)) or (len(b) == 1 and a.startswith(b))
    gx, gy = tx[:-1], ty[:-1]
    if not ok(gx[0], gy[0]):
        return False
    return not (len(gx) > 1 and len(gy) > 1 and not ok(gx[1], gy[1]))


def possible_splits(stats):
    """OpenAlex 可能把同一人拆成多個作者 id：姓名詞組相同（不論順序）或姓氏＋名首字母相同。只列出，不合併。"""
    linked = [s for s in stats if s["linked"]]
    parent = {s["key"]: s["key"] for s in linked}

    def find(k):
        while parent[k] != k:
            k = parent[k]
        return k

    def tokens(name):
        return frozenset(_norm_name(name).lower().replace(".", "").replace("-", " ").split())

    for i, a in enumerate(linked):
        for b in linked[i + 1:]:
            if tokens(a["name"]) == tokens(b["name"]) or _compatible(a["name"], b["name"]):
                parent[find(b["key"])] = find(a["key"])
    groups = defaultdict(list)
    for s in linked:
        groups[find(s["key"])].append(s)
    out = []
    for members in groups.values():
        if len(members) > 1:
            out.append({"keys": [m["key"] for m in members], "names": [m["name"] for m in members],
                        "counts": [m["n"] for m in members], "combined_n_max": sum(m["n"] for m in members)})
    return sorted(out, key=lambda g: -g["combined_n_max"])


def competition_ranks(ns):
    """同分同名次（1, 2, 3, 3, 3, 6）。"""
    out = []
    for i, n in enumerate(ns):
        out.append(out[-1] if i and n == ns[i - 1] else i + 1)
    return out


def check_consistency(net, works):
    """network.json 自我核對（取代獨立計數 agent）：總篇數、每位合作者的篇數＝文章清單、文章都存在、年度加總、依篇數排序。"""
    ids = {w["id"] for w in works}
    fails = []
    if net.get("works_total") != len(works) or (net.get("roles") or {}).get("total", len(works)) != len(works):
        fails.append({"key": "-", "why": "works_total_mismatch"})
    prev = None
    for c in net.get("coauthors") or []:
        ws = c.get("works") or []
        if c.get("n") != len(set(ws)):
            fails.append({"key": c["key"], "why": "n_not_equal_works"})
        if set(ws) - ids:
            fails.append({"key": c["key"], "why": "unknown_work"})
        if sum((c.get("years") or {}).values()) != len(set(ws)):
            fails.append({"key": c["key"], "why": "years_sum_mismatch"})
        if prev is not None and c.get("n", 0) > prev:
            fails.append({"key": c["key"], "why": "not_sorted"})
        prev = c.get("n", 0)
    return fails
