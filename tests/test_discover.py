"""查詢教授：只算「主導」（最後作者或通訊作者）、標題或摘要真的寫到你的興趣的論文；經費看論文上的資助單位；可以篩選。"""
from pipeline.discover import aggregate, apply_filters, interest_query


def work(wid, year, authors, funders=(), title="T"):
    return {"id": f"https://openalex.org/{wid}", "title": title, "publication_year": year, "doi": None,
            "authorships": [{"author_position": pos, "is_corresponding": corr, "author": {"id": f"https://openalex.org/{aid}", "display_name": name},
                             "institutions": [{"display_name": inst, "country_code": cc}]} for pos, corr, aid, name, inst, cc in authors],
            "awards": [{"funder_display_name": f, "funder_award_id": "X1"} for f in funders]}


A = ("last", False, "A1", "Prof Lee", "Uni A", "AU")
B = ("first", True, "A2", "Dr Kim", "Uni B", "US")
C = ("middle", False, "A3", "Mid Author", "Uni C", "GB")


def test_interest_query_strips_symbols():
    assert interest_query("Wearables / IoT & Remote Patient Monitoring") == "wearables iot remote patient monitoring"


def test_only_leading_authors_counted_and_evidence_kept():
    res = {"Digital health": [work("W1", 2025, [B, C, A], funders=["NHMRC"], title="App trial"), work("W2", 2023, [C, A])],
           "Healthy ageing": [work("W3", 2022, [A, C])]}
    cs = {c["id"]: c for c in aggregate(res, exclude=set())}
    assert set(cs) == {"A1", "A2"}  # 中間作者不算主導
    lee = cs["A1"]
    assert lee["n_led"] == 3 and lee["interests"] == ["Digital health", "Healthy ageing"] and lee["last_year"] == 2025
    assert lee["funders"] == ["NHMRC"] and lee["institution"] == "Uni A" and lee["country"] == "AU"
    assert lee["papers"][0]["title"] == "App trial"  # 新的在前
    assert cs["A2"]["n_led"] == 1
    assert [c["id"] for c in aggregate(res, exclude={"A1"})] == ["A2"]  # 已經是目標教授的不再列


def test_filters():
    cs = [{"id": "A1", "n_led": 3, "funders": ["NHMRC"], "last_year": 2025, "country": "AU"},
          {"id": "A2", "n_led": 1, "funders": [], "last_year": 2022, "country": "US"}]
    assert [c["id"] for c in apply_filters(cs, funded=True)] == ["A1"]
    assert [c["id"] for c in apply_filters(cs, min_led=2)] == ["A1"]
    assert [c["id"] for c in apply_filters(cs, active_since=2025)] == ["A1"]
    assert [c["id"] for c in apply_filters(cs, country="US")] == ["A2"]
    assert len(apply_filters(cs)) == 2


def test_group_and_journal_bylines_are_not_people():
    from pipeline.discover import looks_like_person
    assert looks_like_person("Liliana Laranjo") and looks_like_person("Kim, J.")
    for n in ("The Lancet Healthy Longevity", "GBD 2021 Collaborators", "Editorial Board", "Diabetes Prevention Program Research Group"):
        assert not looks_like_person(n)


def test_min_h_index_filter():
    cs = [{"id": "A1", "n_led": 3, "funders": [], "last_year": 2025, "h_index": 30}, {"id": "A2", "n_led": 3, "funders": [], "last_year": 2025, "h_index": 2}]
    assert [c["id"] for c in apply_filters(cs, min_h=10)] == ["A1"]


def test_enrichment_checked_merged_and_filtered():
    from pipeline.discover import check_enrich, merge_enrich, apply_filters
    enr = {"institutions": {"Uni A": {"qs": {"rank": 42, "year": 2026, "src": "https://www.topuniversities.com/x"},
                                      "usnews": {"rank": 88, "src": "https://www.usnews.com/x"},
                                      "funding": {"value": "full", "note": "PhD 全額", "src": "https://unia.edu/phd"}},
                            "Uni B": {"qs": {"rank": 150, "src": ""}, "funding": {"value": "maybe"}}},
           "people": {"A1": {"lab_url": "https://lab.unia.edu", "src": "https://unia.edu/staff/lee"}}}
    whys = {f["why"] for f in check_enrich(enr)}
    assert {"no_source", "bad_funding_value"} <= whys  # 沒附出處、亂填的值都會被抓
    good = {"institutions": {"Uni A": enr["institutions"]["Uni A"]}, "people": enr["people"]}
    assert check_enrich(good) == []
    cs = merge_enrich([{"id": "A1", "institution": "Uni A", "n_led": 3, "funders": [], "last_year": 2025},
                       {"id": "A2", "institution": "Uni C", "n_led": 3, "funders": [], "last_year": 2025}], good)
    assert cs[0]["qs_rank"] == 42 and cs[0]["phd_funding"] == "full" and cs[0]["lab_url"] == "https://lab.unia.edu"
    assert [c["id"] for c in apply_filters(cs, qs_max=50)] == ["A1"]
    assert [c["id"] for c in apply_filters(cs, usnews_max=50)] == []
    assert [c["id"] for c in apply_filters(cs, full_funding=True)] == ["A1"]
    assert [c["id"] for c in apply_filters(cs, has_lab=True)] == ["A1"]


CPH = {"name": "Computational Precision Health (UCSF–UC Berkeley joint PhD)", "url": "https://computationalhealth.ucsf.edu/",
       "member_src": "https://computationalhealth.ucsf.edu/faculty/page/3",
       "funding": {"value": "full", "years": 5, "note": "學費、雜費＋生活津貼 5 年", "src": "https://computationalhealth.ucsf.edu/?p=181"}}


def test_programs_checked():
    """教授掛名的博士學程：要有官方教員名單出處；資助要有出處；值只能是四種。"""
    from pipeline.discover import check_enrich, check_programs
    assert check_programs([CPH]) == []
    bad = [{**CPH, "member_src": None}, {**CPH, "funding": {"value": "full"}}, {**CPH, "funding": {"value": "lots", "src": "https://x"}},
           {**CPH, "name": ""}]
    assert [f["why"] for f in check_programs(bad)] == ["no_member_source", "no_source", "bad_funding_value", "no_name"]
    whys = {f["why"] for f in check_enrich({"people": {"A1": {"programs": [{**CPH, "member_src": "x"}]}}})}
    assert whys == {"no_member_source"}


def test_full_funding_uses_professor_programs_over_school():
    from pipeline.discover import apply_filters, merge_enrich
    enr = {"institutions": {"UCSF": {"funding": {"value": "unknown"}}, "Uni B": {"funding": {"value": "full", "src": "https://b"}}},
           "people": {"A1": {"programs": [CPH]}, "A3": {"programs": [{**CPH, "funding": {"value": "partial", "src": "https://p"}}]}}}
    cs = merge_enrich([{"id": a, "institution": i, "n_led": 1} for a, i in (("A1", "UCSF"), ("A2", "Uni B"), ("A3", "Uni B"))], enr)
    assert cs[0]["programs"][0]["name"].startswith("Computational Precision Health")
    # A1：學校查不到，但他掛名的學程全額 → 算；A2：沒查到學程，用學校的；A3：他掛名的學程只有部分資助 → 不算（看學程，不看學校）
    assert [c["id"] for c in apply_filters(cs, full_funding=True)] == ["A1", "A2"]


def test_reenrich_keeps_previous_on_new_search():
    """重新查詢：之前補過的人與學校照留，只有新出現的要補。"""
    from pipeline.discover import enrich_todo, merge_enrich
    enr = {"institutions": {"UCSF": {"qs": {"rank": 20, "src": "https://q"}}}, "people": {"A1": {"programs": [CPH]}}}
    cs = merge_enrich([{"id": "A1", "institution": "UCSF"}, {"id": "A9", "institution": "Uni Z"}], enr)
    assert cs[0]["qs_rank"] == 20 and cs[1].get("programs") is None
    todo = enrich_todo(cs, enr)
    assert todo["institutions"] == ["Uni Z"] and [p["id"] for p in todo["people"]] == ["A9"]


def test_combine_enrich_accumulates():
    from pipeline.discover import combine_enrich
    old = {"institutions": {"UCSF": {"qs": {"rank": 20, "src": "https://q"}}}, "people": {"A1": {"lab_url": "https://l", "src": "https://s"}}}
    got = combine_enrich(old, {"institutions": {"Uni Z": {}}, "people": {"A1": {"programs": [CPH]}}})
    assert set(got["institutions"]) == {"UCSF", "Uni Z"} and got["people"]["A1"]["lab_url"] == "https://l" and got["people"]["A1"]["programs"]


DEPT = {"name": "Doctor of Philosophy (Medicine and Health)", "basis": "department", "url": "https://www.sydney.edu.au/courses/phd-medicine",
        "src": "https://www.sydney.edu.au/courses/phd-medicine", "intake": "2027", "duration": "3–4 年全職",
        "tuition": {"text": "國際生每年約 AUD 50,000（獎學金可免）", "src": "https://www.sydney.edu.au/fees"},
        "requirements": ["研究計畫書", "CV", "指導教授同意", "英文成績 IELTS 6.5"], "requirements_src": "https://www.sydney.edu.au/apply",
        "funding": {"value": "partial", "note": "RTP 獎學金需競爭", "src": "https://www.sydney.edu.au/scholarships"}}


def test_department_program_fallback_checked():
    """教授本人沒掛名學程時，改查她系所／學院下一年度的博士班：不需要教員名單，但學程頁、學費、繳交文件都要有出處。"""
    from pipeline.discover import check_programs
    assert check_programs([DEPT]) == []
    whys = lambda p: [f["why"] for f in check_programs([p])]
    assert whys({**DEPT, "src": None}) == ["no_program_source"]
    assert whys({**DEPT, "tuition": {"text": "AUD 50,000"}}) == ["no_tuition_source"]
    assert whys({**DEPT, "requirements_src": None}) == ["no_requirements_source"]
    assert whys({**DEPT, "basis": "guess"}) == ["bad_basis"]
    assert whys({**CPH, "member_src": None}) == ["no_member_source"]  # 本人掛名的仍要教員名單
