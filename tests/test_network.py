from pipeline.network import (
    coauthor_stats,
    role_summary,
    topic_counts,
    year_counts,
    author_lists_md,
    compare_counts,
)

T = "A0"


def au(id_, name, pos="middle", corr=False, inst=("UCSF",)):
    return {"id": id_, "name": name, "position": pos, "is_corresponding": corr, "institutions": list(inst)}


WORKS = [
    {"id": "W1", "year": 2022, "kind": "full", "target_position": "last", "target_corresponding": True,
     "authors": [au("A1", "Ann Lee", "first"), au("A2", "Bo Kim"), au(T, "Yoshimi Fukuoka", "last", True)],
     "topic": {"name": "mHealth", "subfield": "Health Informatics", "field": "Medicine", "domain": "Health"}},
    {"id": "W2", "year": 2023, "kind": "full", "target_position": "first", "target_corresponding": True,
     "authors": [au(T, "Y. Fukuoka", "first", True), au("A1", "Ann  Lee", "middle", inst=("Stanford",)), au("A3", "Cy Wu", "last")],
     "topic": {"name": "mHealth", "subfield": "Health Informatics", "field": "Medicine", "domain": "Health"}},
    {"id": "W3", "year": 2023, "kind": "short", "target_position": "middle", "target_corresponding": False,
     "authors": [au("A1", "Ann Lee", "first"), au(None, "Yoshimi Fukuoka", "middle"), au(None, "Dee Unlinked", "last")],
     "topic": {"name": "Cancer QoL", "subfield": "Oncology", "field": "Medicine", "domain": "Health"}},
]


def test_coauthor_counts_by_id_excluding_target():
    stats = coauthor_stats(WORKS, T, "Fukuoka")
    top = stats[0]
    assert top["key"] == "A1" and top["n"] == 3
    assert top["works"] == ["W1", "W2", "W3"]
    assert top["years"] == {2022: 1, 2023: 2}
    assert top["as_first"] == 2 and top["as_last"] == 0
    assert top["institutions"][0] == ("UCSF", 2)
    assert all(s["key"] != T for s in stats)
    assert not any("Fukuoka" in s["name"] for s in stats)  # 沒連 id 的本人也要排除


def test_unlinked_coauthor_keyed_by_name_and_flagged():
    stats = coauthor_stats(WORKS, T, "Fukuoka")
    d = next(s for s in stats if s["name"] == "Dee Unlinked")
    assert d["key"].startswith("name:") and d["linked"] is False


def test_most_common_name_variant_wins():
    stats = coauthor_stats(WORKS, T, "Fukuoka")
    assert stats[0]["name"] == "Ann Lee"


def test_sort_is_deterministic_on_ties():
    stats = coauthor_stats(WORKS, T, "Fukuoka")
    ones = [s["name"] for s in stats if s["n"] == 1]
    assert ones == sorted(ones)


def test_role_summary():
    r = role_summary(WORKS)
    assert r == {"first": 1, "middle": 1, "last": 1, "unknown": 0, "corresponding": 2, "total": 3}


def test_topic_and_year_counts():
    t = topic_counts(WORKS)
    assert t["topic"][0] == ("mHealth", 2)
    assert t["field"] == [("Medicine", 3)]
    assert year_counts(WORKS) == {2022: 1, 2023: 2}


def test_author_lists_md_has_every_work_and_ids():
    md = author_lists_md(WORKS, T, "Fukuoka")
    assert md.count("## W") == 3
    assert "Ann Lee (A1)" in md and "Dee Unlinked (無 id)" in md
    assert "Yoshimi Fukuoka (本人)" in md and "Y. Fukuoka (本人)" in md


def test_author_lists_md_shows_name_linked_id():
    works = WORKS + [{"id": "W4", "year": 2022, "kind": "full", "authors": [au(None, "Ann B Lee")], "topic": {}}]
    assert "Ann B Lee (A1，姓名對應)" in author_lists_md(works, T, "Fukuoka")


def test_compare_counts_passes_when_equal():
    stats = coauthor_stats(WORKS, T, "Fukuoka")
    agent = [{"key": "A1", "n": 3}, {"key": "A2", "n": 1}, {"key": "A3", "n": 1}, {"key": "name:dee unlinked", "n": 1}]
    assert compare_counts(stats, agent, top=10) == []


def test_compare_counts_catches_off_by_one():
    stats = coauthor_stats(WORKS, T, "Fukuoka")
    agent = [{"key": "A1", "n": 2}, {"key": "A2", "n": 1}, {"key": "A3", "n": 1}]
    diffs = compare_counts(stats, agent, top=10)
    assert {"key": "A1", "script": 3, "agent": 2} in diffs


def test_compare_counts_catches_agent_inventing_or_missing_author():
    stats = coauthor_stats(WORKS, T, "Fukuoka")
    agent = [{"key": "A1", "n": 3}, {"key": "A9", "n": 5}]
    diffs = compare_counts(stats, agent, top=2)
    keys = {d["key"] for d in diffs}
    assert "A9" in keys  # 腳本裡沒有的人
    assert "A2" in keys or "A3" in keys or "name:dee unlinked" in keys  # 腳本前 2 名中 agent 漏掉的


def test_unlinked_name_merged_into_unique_linked_match():
    works = WORKS + [{"id": "W4", "year": 2022, "kind": "full", "target_position": "middle", "target_corresponding": False,
                      "authors": [au(None, "Ann B Lee", "first"), au(None, "Yoshimi Fukuoka")], "topic": {}}]
    stats = coauthor_stats(works, T, "Fukuoka")
    a1 = next(s for s in stats if s["key"] == "A1")
    assert a1["n"] == 4 and "W4" in a1["works"]
    assert a1["merged_names"] == ["Ann B Lee"]
    assert not any(s["name"] == "Ann B Lee" for s in stats)


def test_ambiguous_unlinked_name_stays_separate():
    works = [
        {"id": "W1", "year": 2022, "kind": "full", "authors": [au("A1", "Li Zhang"), au("A2", "Lan Zhang"), au(T, "Y Fukuoka")], "topic": {}},
        {"id": "W2", "year": 2022, "kind": "full", "authors": [au(None, "L Zhang"), au(T, "Y Fukuoka")], "topic": {}},
    ]
    stats = coauthor_stats(works, T, "Fukuoka")
    assert any(s["key"] == "name:l zhang" for s in stats)


def test_merge_does_not_double_count_same_work():
    works = [
        {"id": "W1", "year": 2022, "kind": "full", "authors": [au("A1", "Ann Lee"), au(None, "Ann Lee"), au(T, "Y Fukuoka")], "topic": {}},
    ]
    stats = coauthor_stats(works, T, "Fukuoka")
    assert stats[0]["n"] == 1


def test_possible_splits_flags_same_name_different_ids():
    from pipeline.network import possible_splits
    stats = [
        {"key": "A1", "name": "Thomas J. Hoffmann", "n": 6, "linked": True},
        {"key": "A2", "name": "Thomas J. Hoffmann", "n": 1, "linked": True},
        {"key": "A3", "name": "Yoo Jung Oh", "n": 5, "linked": True},
        {"key": "A4", "name": "Jung Oh Yoo", "n": 1, "linked": True},
        {"key": "A5", "name": "Ann Lee", "n": 2, "linked": True},
        {"key": "name:x", "name": "Thomas Hoffmann", "n": 1, "linked": False},
    ]
    groups = possible_splits(stats)
    keys = [sorted(g["keys"]) for g in groups]
    assert ["A1", "A2"] in keys
    assert ["A3", "A4"] in keys
    assert not any("A5" in k for k in keys)
    assert all("name:x" not in k for k in keys)  # 沒 id 的不在這裡處理
    g = next(g for g in groups if "A1" in g["keys"])
    assert g["combined_n_max"] == 7


def test_name_merge_blocked_when_orcids_differ():
    works = [
        {"id": "W1", "year": 2022, "kind": "full", "authors": [{**au("A1", "Li Zhang"), "orcid": "https://orcid.org/0000-0001"}, au(T, "Y Fukuoka")], "topic": {}},
        {"id": "W2", "year": 2022, "kind": "full", "authors": [{**au(None, "Li Zhang"), "orcid": "https://orcid.org/0000-0009"}, au(T, "Y Fukuoka")], "topic": {}},
    ]
    stats = coauthor_stats(works, T, "Fukuoka")
    assert any(s["key"] == "name:li zhang" for s in stats)


def test_competition_rank_for_ties():
    from pipeline.network import competition_ranks
    assert competition_ranks([10, 9, 4, 4, 4, 3]) == [1, 2, 3, 3, 3, 6]
