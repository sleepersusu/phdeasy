from pipeline.grants import (
    normalize_award,
    nih_numbers,
    name_match,
    inst_match,
    nih_projects,
    ack_snippets,
    merge_grants,
)


def test_normalize_nih_variants_share_key():
    keys = {normalize_award(x) for x in ["1R01HS027803-01A1", "5R01HS027803-04", "R01 HS027803", "R01HS027803", "HS027803"]}
    assert keys == {"NIH:HS027803"}


def test_normalize_nih_partial_and_spaces():
    assert normalize_award("K23 MD015089") == "NIH:MD015089"
    assert normalize_award("UL1 TR001872") == "NIH:TR001872"


def test_normalize_non_nih():
    assert normalize_award("CBET-1234567") == "ID:1234567"  # NSF 學門前綴拿掉，與純數字編號合併
    assert normalize_award(None) is None


def test_nih_numbers_found_in_text_but_not_random_words():
    t = "Funded by NIH grants R01HL123456, K24 NR015812 and UL1TR001872; see HELLO123456 and 2020."
    assert nih_numbers(t) == ["R01HL123456", "K24NR015812", "UL1TR001872"]


def test_name_match():
    assert name_match("YOSHIMI  FUKUOKA", "Yoshimi Fukuoka")
    assert name_match("FUKUOKA, YOSHIMI", "Yoshimi Fukuoka")
    assert name_match("Y. FUKUOKA", "Yoshimi Fukuoka")
    assert not name_match("KENJI FUKUOKA", "Yoshimi Fukuoka")
    assert not name_match("YOSHIMI TANAKA", "Yoshimi Fukuoka")


def test_inst_match():
    assert inst_match("UNIVERSITY OF CALIFORNIA, SAN FRANCISCO", "University of California, San Francisco")
    assert not inst_match("UNIVERSITY OF CALIFORNIA BERKELEY", "University of California, San Francisco")


NIH = {"results": [
    {"core_project_num": "R01HS027803", "project_num": "5R01HS027803-04", "fiscal_year": 2024, "project_title": "Diabetes prevention",
     "organization": {"org_name": "UNIVERSITY OF CALIFORNIA, SAN FRANCISCO"}, "principal_investigators": [{"full_name": "YOSHIMI  FUKUOKA", "is_contact_pi": True}],
     "project_start_date": "2021-08-01T00:00:00", "project_end_date": "2026-07-31T00:00:00", "award_amount": 398606, "agency_ic_admin": {"abbreviation": "AHRQ"}},
    {"core_project_num": "R01HS027803", "project_num": "1R01HS027803-01A1", "fiscal_year": 2021, "project_title": "Diabetes prevention",
     "organization": {"org_name": "UNIVERSITY OF CALIFORNIA, SAN FRANCISCO"}, "principal_investigators": [{"full_name": "YOSHIMI  FUKUOKA", "is_contact_pi": True}],
     "project_start_date": "2021-08-01T00:00:00", "project_end_date": "2026-07-31T00:00:00", "award_amount": 400000, "agency_ic_admin": {"abbreviation": "AHRQ"}},
    {"core_project_num": "K23MD015089", "project_num": "5K23MD015089-03", "fiscal_year": 2022, "project_title": "Mentee grant",
     "organization": {"org_name": "UNIVERSITY OF CALIFORNIA, SAN FRANCISCO"}, "principal_investigators": [{"full_name": "TUNG NGUYEN", "is_contact_pi": True}],
     "project_start_date": "2020-01-01T00:00:00", "project_end_date": "2024-12-31T00:00:00", "award_amount": 100000, "agency_ic_admin": {"abbreviation": "NIMHD"}},
    {"core_project_num": "R21XX000001", "project_num": "R21XX000001", "fiscal_year": 2023, "project_title": "Other place",
     "organization": {"org_name": "OSAKA UNIVERSITY"}, "principal_investigators": [{"full_name": "YOSHIMI FUKUOKA"}],
     "project_start_date": "2023-01-01T00:00:00", "project_end_date": "2024-01-01T00:00:00", "award_amount": 1, "agency_ic_admin": {"abbreviation": "NIA"}},
]}


def test_nih_projects_collapse_years_and_classify_role():
    ps = {p["key"]: p for p in nih_projects(NIH, "Yoshimi Fukuoka", "University of California, San Francisco")}
    p = ps["NIH:HS027803"]
    assert p["award_id"] == "R01HS027803" and p["fiscal_years"] == [2021, 2024]
    assert p["target_role"] == "pi" and p["status"] == "confirmed"
    assert p["total_award"] == 798606 and p["start"] == "2021-08-01" and p["end"] == "2026-07-31"
    assert ps["NIH:MD015089"]["target_role"] == "other_pi" and ps["NIH:MD015089"]["pi_names"] == ["TUNG NGUYEN"]
    assert ps["NIH:XX000001"]["status"] == "pending"  # 只有姓名吻合，機構不符


def test_ack_snippets_from_marked_text():
    text = """[p.7]
Conclusions blah.
Acknowledgments
This study was supported by the National Institute of Nursing Research (K24NR015812).
Conflicts of Interest
None declared.
[p.8]
References
"""
    sn = ack_snippets(text)
    assert len(sn) == 1
    assert sn[0]["loc"] == "p.7" and "K24NR015812" in sn[0]["text"]


def test_ack_snippets_xml_paragraph():
    text = "## Acknowledgments\n[§43] This project was supported by the Noyce Foundation.\n[§44] Other."
    sn = ack_snippets(text)
    assert sn[0]["loc"] == "§43" and "Noyce" in sn[0]["text"]


def test_merge_grants_links_works_and_evidence():
    projects = [{"key": "NIH:HS027803", "award_id": "R01HS027803", "funder": "AHRQ", "title": "Diabetes prevention", "target_role": "pi", "status": "confirmed",
                 "pi_names": ["YOSHIMI FUKUOKA"], "start": "2021-08-01", "end": "2026-07-31", "total_award": 1, "fiscal_years": [2021], "source": "nih_pi"}]
    openalex = [{"work_id": "W1", "funder": "AHRQ", "award_id": "R01 HS027803"}]
    mentions = [
        {"work_id": "W2", "funder": "Noyce Foundation", "award_id": None, "quote": "supported by the Noyce Foundation", "loc": "§43", "check": "ok"},
        {"work_id": "W3", "funder": "Noyce Foundation", "award_id": None, "quote": "Noyce Foundation", "loc": "p.9", "check": "ok"},
        {"work_id": "W2", "funder": "AHRQ", "award_id": "R01HS027803", "quote": "AHRQ R01HS027803", "loc": "§43", "check": "ok"},
    ]
    g = {x["key"]: x for x in merge_grants(projects, openalex, mentions)}
    assert g["NIH:HS027803"]["works"] == ["W1", "W2"]
    assert {e["type"] for e in g["NIH:HS027803"]["evidence"]} == {"nih_pi", "openalex", "ack"}
    noyce = g["FUNDER:noyce foundation"]
    assert noyce["works"] == ["W2", "W3"] and noyce["target_role"] == "acknowledged" and noyce["status"] == "acknowledged"


def test_merge_grants_ignores_failed_quotes():
    mentions = [{"work_id": "W2", "funder": "Fake Fund", "award_id": None, "quote": "x", "loc": "p.1", "check": "not_found"}]
    assert merge_grants([], [], mentions) == []


def test_nsf_projects_pi_and_copi():
    from pipeline.grants import nsf_projects
    resp = {"response": {"award": [
        {"id": "2212345", "title": "Chatbots", "piFirstName": "Yoshimi", "piLastName": "Fukuoka", "awardeeName": "University of California-San Francisco",
         "startDate": "09/01/2022", "expDate": "08/31/2025", "fundsObligatedAmt": "500000", "coPDPI": []},
        {"id": "2299999", "title": "Other", "piFirstName": "Kenji", "piLastName": "Sagae", "awardeeName": "San Francisco State University",
         "startDate": "01/01/2023", "expDate": "12/31/2025", "fundsObligatedAmt": "1", "coPDPI": ["Yoshimi Fukuoka"]},
    ]}}
    ps = {p["key"]: p for p in nsf_projects(resp, "Yoshimi Fukuoka", "University of California, San Francisco")}
    assert ps["ID:NSF2212345"]["target_role"] == "pi" and ps["ID:NSF2212345"]["start"] == "2022-09-01"
    assert ps["ID:NSF2299999"]["target_role"] == "co_pi"


def test_mention_check_requires_award_id_in_quote():
    from pipeline.grants import check_mention
    text = "[p.7]\nThis study was supported by the National Institute of Nursing Research (K24NR015812).\n"
    ok = {"work_id": "W1", "funder": "NINR", "award_id": "K24NR015812", "quote": "supported by the National Institute of Nursing Research (K24NR015812)", "loc": "p.7"}
    assert check_mention(text, ok) == "ok"
    bad_id = {**ok, "award_id": "R01NR999999"}
    assert check_mention(text, bad_id) == "award_id_not_in_quote"
    fake = {**ok, "quote": "supported by the Gates Foundation grant OPP123"}
    assert check_mention(text, fake) == "not_found"


def test_nih_core_needs_activity_code():
    from pipeline.grants import nih_core
    assert nih_core("5R01HL104147-05") == "R01HL104147"
    assert nih_core("K23 MD015089") == "K23MD015089"
    assert nih_core("UL1 TR001872") == "UL1TR001872"
    assert nih_core("TR001870") is None
    assert nih_core("CBET-1234567") is None


def test_ack_snippets_keep_context_lines_around_match():
    text = """[p.6]
Discussion text.
This work was funded by the National Cancer Institute
(R01CA123456), the National Center for Advancing Translational
Sciences (KL2TR000143), Mt. Zion Health Fund.
Unrelated closing line one.
Unrelated closing line two.
Unrelated closing line three.
"""
    sn = ack_snippets(text)
    assert "National Center for Advancing Translational" in sn[0]["text"]
    assert "Unrelated closing line three" not in sn[0]["text"]


def test_ack_snippets_rejoin_hyphenated_line_breaks():
    text = "[p.7]\nFunding: This work was funded by the Alzhei-\nmer's Association AARGD-NTF-20-684334.\n"
    sn = ack_snippets(text)
    assert "Alzheimer's Association" in sn[0]["text"]
    assert "Alzhei- mer" not in sn[0]["text"]


def test_normalize_award_unicode_dash_and_prefix_variants():
    assert normalize_award("AARGD-NTF-20–684334") == normalize_award("AARGD-NTF-20-684334")
    assert normalize_award("CMMI-1450963") == normalize_award("1450963")
    assert normalize_award("UCSF CTSI Grant Number UL1 TR000004") == "NIH:TR000004"


def test_merge_funder_only_keys_ignore_punctuation():
    m = [
        {"work_id": "W1", "funder": "University of California, San Francisco", "award_id": None, "quote": "q" * 20, "loc": "p.1", "check": "ok"},
        {"work_id": "W2", "funder": "University of California San Francisco", "award_id": None, "quote": "q" * 20, "loc": "p.1", "check": "ok"},
    ]
    g = merge_grants([], [], m)
    assert len(g) == 1 and g[0]["works"] == ["W1", "W2"]


def test_apply_verdicts():
    from pipeline.grants import apply_verdicts
    grants = [{"key": "A", "status": "confirmed", "target_role": "pi"},
              {"key": "B", "status": "acknowledged", "target_role": "acknowledged"},
              {"key": "C", "status": "other", "target_role": "pi"},
              {"key": "D", "status": "pending", "target_role": "pi"}]
    verdicts = [{"key": "A", "verdict": "keep"}, {"key": "B", "verdict": "reject", "reason": "重複"},
                {"key": "C", "verdict": "keep", "role_fix": "other_pi"}, {"key": "D", "verdict": "unresolved", "reason": "只有姓名"}]
    final, rejected, unresolved, missing = apply_verdicts(grants, verdicts)
    assert [g["key"] for g in final] == ["A", "C", "D"]
    assert [g["key"] for g in rejected] == ["B"]
    assert final[1]["target_role"] == "other_pi"
    assert final[2]["status"] == "pending" and [g["key"] for g in unresolved] == ["D"]
    assert missing == []


def test_refute_only_required_for_her_own_and_pending_grants():
    # 本人 2026-10-26：推翻只看她主持與待確認的；致謝提及、合作者主持的靠腳本逐字核對引句
    from pipeline.grants import apply_verdicts, in_refute_scope
    grants = [{"key": "A", "status": "confirmed", "target_role": "pi"}, {"key": "B", "status": "acknowledged", "target_role": "acknowledged"},
              {"key": "C", "status": "other", "target_role": "other_pi"}, {"key": "D", "status": "pending", "target_role": "pi"}]
    assert [g["key"] for g in grants if in_refute_scope(g)] == ["A", "D"]
    final, rejected, unresolved, missing = apply_verdicts(grants, [{"key": "A", "verdict": "keep"}])
    assert missing == ["D"]
    assert {g["key"]: g["refute"]["verdict"] for g in final} == {"A": "keep", "B": "not_in_scope", "C": "not_in_scope"}


def test_apply_verdicts_reports_missing_and_bad_verdict():
    from pipeline.grants import apply_verdicts
    grants = [{"key": "A", "status": "confirmed", "target_role": "pi"}, {"key": "B", "status": "pending", "target_role": "pi"}]
    _, _, _, missing = apply_verdicts(grants, [{"key": "A", "verdict": "maybe"}])
    assert missing == ["A", "B"]  # 不合法的 verdict 視同漏判


def test_apply_verdicts_rejects_promoting_acknowledged_to_pi():
    from pipeline.grants import apply_verdicts
    grants = [{"key": "B", "status": "acknowledged", "target_role": "acknowledged"}]
    final, _, unresolved, _ = apply_verdicts(grants, [{"key": "B", "verdict": "keep", "role_fix": "pi"}])
    assert final[0]["target_role"] == "acknowledged"  # 沒有 API 證據不能升格
    assert [g["key"] for g in unresolved] == ["B"] and final[0]["status"] == "pending"


def test_nih_center_grant_takes_parent_title_and_pi():
    resp = {"results": [
        {"core_project_num": "P50AR063043", "project_num": "5P50AR063043-05", "subproject_id": "6662", "fiscal_year": 2018,
         "project_title": "Sex differences in bone shape", "organization": {"org_name": "UCSF"}, "principal_investigators": [{"full_name": "Nancy E Lane"}],
         "project_start_date": "2013-09-01T00:00:00", "project_end_date": "2019-08-31T00:00:00", "award_amount": 10, "agency_ic_admin": {"abbreviation": "NIAMS"}},
        {"core_project_num": "P50AR063043", "project_num": "5P50AR063043-05", "subproject_id": None, "fiscal_year": 2018,
         "project_title": "UCSF Specialized Center of Research on Sex Differences", "organization": {"org_name": "UCSF"}, "principal_investigators": [{"full_name": "Wendy Katzman"}],
         "project_start_date": "2013-09-01T00:00:00", "project_end_date": "2019-08-31T00:00:00", "award_amount": 100, "agency_ic_admin": {"abbreviation": "NIAMS"}},
    ]}
    p = nih_projects(resp, "Yoshimi Fukuoka", "UCSF")[0]
    assert p["title"] == "UCSF Specialized Center of Research on Sex Differences"
    assert p["pi_names"][0] == "Wendy Katzman"
    assert p["total_award"] == 100  # 子計畫金額已含在母計畫內，不重複加


def test_funder_key_folds_ligatures():
    from pipeline.grants import funder_key
    assert funder_key("UCSF Diabetes Family Fund for Innovative Patient Care Education and Scientiﬁc Discovery Award") == \
        funder_key("UCSF Diabetes Family Fund for Innovative Patient Care Education and Scientific Discovery Award")


def test_nhmrc_projects_header_variants_and_roles():
    from pipeline.grants import nhmrc_projects
    rows = [
        {"APP ID": 2009001, "Grant Title": "Digital health for hypertension", "CIA Name": "Associate Professor Liliana Laranjo",
         "Administering Institution": "The University of Sydney", "Total": 1500000, "Scheme": "Investigator Grants", "Start Year": 2023},
        {"Application ID": "2019876", "Title": "Heart failure trial", "Chief Investigator A": "Professor Clara Chow",
         "Chief Investigators": "Chow C, Laranjo L, Redfern J", "Admin Institution": "The University of Sydney", "Budget": "2,000,000", "Grant Type": "Ideas", "Start Year": "2024"},
        {"APP ID": 1, "Grant Title": "Unrelated", "CIA Name": "Dr Jane Smith", "Administering Institution": "Monash University", "Total": 1},
    ]
    ps = {p["key"]: p for p in nhmrc_projects(rows, "Liliana Laranjo", "The University of Sydney", "2023")}
    assert set(ps) == {"ID:NHMRC2009001", "ID:NHMRC2019876"}
    a = ps["ID:NHMRC2009001"]
    assert a["target_role"] == "pi" and a["status"] == "confirmed" and a["funder"] == "NHMRC" and a["total_award"] == 1500000
    assert a["start"] == "2023" and a["round"] == "2023"
    b = ps["ID:NHMRC2019876"]
    assert b["target_role"] == "co_pi" and b["pi_names"][0] == "Professor Clara Chow" and b["total_award"] == 2000000


def test_inst_match_accepts_list_of_institutions():
    insts = ["University of Technology Sydney", "The University of Sydney", "Westmead Hospital"]
    assert inst_match("University of Sydney", insts)
    assert not inst_match("Monash University", insts)


def test_nhmrc_numbers_unify_with_funder_context():
    k = "ID:NHMRC2017642"
    assert normalize_award("NHMRC 2017642") == k
    assert normalize_award("2017642", funder="National Health and Medical Research Council") == k
    assert normalize_award("GNT2017642", funder="NHMRC") == k
    assert normalize_award("APP2017642", funder="Australian National Health and Medical Research Council (NHMRC)") == k
    assert normalize_award("2017642") == "ID:2017642"  # 沒有補助單位脈絡時不亂猜


def test_merge_attaches_ack_to_nhmrc_project():
    projects = [{"key": "ID:NHMRC2017642", "award_id": "NHMRC 2017642", "funder": "NHMRC", "title": "Digital health", "target_role": "pi",
                 "status": "confirmed", "pi_names": ["Liliana Laranjo"], "source": "nhmrc"}]
    mentions = [{"work_id": "W1", "funder": "National Health and Medical Research Council", "award_id": "2017642",
                 "quote": "grant number 2017642", "loc": "p.1", "check": "ok"}]
    g = merge_grants(projects, [], mentions)
    assert len(g) == 1 and g[0]["works"] == ["W1"]


def test_merge_splits_multiple_award_ids_in_one_mention():
    m = [{"work_id": "W1", "funder": "NHMRC", "award_id": "2022036, 2022566; 2044237", "quote": "grants 2022036, 2022566 and 2044237", "loc": "p.1", "check": "ok"}]
    keys = sorted(g["key"] for g in merge_grants([], [], m))
    assert keys == ["ID:NHMRC2022036", "ID:NHMRC2022566", "ID:NHMRC2044237"]


def test_nhmrc_keeps_announced_date_and_sub_type():
    import datetime
    from pipeline.grants import nhmrc_projects
    rows = [{"APP ID": 2017642, "Date Announced": datetime.datetime(2022, 10, 12), "CIA Name": "Dr Liliana Laranjo",
             "Grant Type": "Investigator Grants", "Sub Type": "Emerging Leadership 1 ", "Grant Title": "Digital health",
             "Admin Institution": "University of Sydney", "Total": 636434.15, "Plain Description": "Apps."}]
    p = nhmrc_projects(rows, "Liliana Laranjo", "The University of Sydney", "2022")[0]
    assert p["announced"] == "2022-10-12" and p["scheme"] == "Investigator Grants – Emerging Leadership 1"
    assert p["abstract"] == "Apps." and p["start"] is None


def test_currency_by_source():
    from pipeline.grants import currency
    assert currency({"source": "nhmrc"}) == "AUD" and currency({"source": "arc"}) == "AUD"
    assert currency({"key": "NIH:HL114180"}) == "USD" and currency({"source": "nsf"}) == "USD"
    assert currency({"source": "openalex"}) is None


def test_merge_cli_ignores_dropped_works(tmp_path):
    import json, sys
    sys.path.insert(0, "scripts")
    import grants as cli
    run = tmp_path / "r"
    gd = run / "work" / "grants"
    gd.mkdir(parents=True)
    (run / "work" / "works.json").write_text(json.dumps([{"id": "W1"}]))
    (gd / "projects.json").write_text("[]")
    (gd / "openalex_awards.json").write_text(json.dumps([{"work_id": "W2", "funder": "NHMRC", "award_id": "2017642"}]))
    (gd / "mentions_checked.json").write_text(json.dumps([{"work_id": "W1", "funder": "NHMRC", "award_id": "2017642", "quote": "q", "loc": "p.1", "check": "ok"},
                                                          {"work_id": "W2", "funder": "NHMRC", "award_id": "2017642", "quote": "q", "loc": "p.1", "check": "ok"}]))
    cli.merge(run)
    g = json.loads((gd / "grants.json").read_text())
    assert [x["works"] for x in g] == [["W1"]]


def test_openalex_awards_batches_over_100_ids():
    # OpenAlex 的 filter OR 最多 100 個值；128 篇一次查會回 http_400
    from pipeline.grants import openalex_awards

    calls = []

    def fake_fetch(ids):
        assert len(ids) <= 50, f"一次查 {len(ids)} 個 id"
        calls.append(ids)
        return {"results": [{"id": f"https://openalex.org/{i}",
                             "awards": [{"funder_display_name": "NIH", "funder_award_id": "R01CA5"}] if i == "W5" else [],
                             "funders": [{"display_name": "NSF"}] if i == "W7" else []} for i in ids]}

    awards, pages = openalex_awards([f"W{i}" for i in range(128)], fake_fetch)
    assert len(calls) == 3 and sum(map(len, calls)) == 128 and len(pages) == 3
    assert {"work_id": "W5", "funder": "NIH", "award_id": "R01CA5"} in awards
    assert {"work_id": "W7", "funder": "NSF", "award_id": None} in awards
    assert len(awards) == 2


def test_owner_grant_overrides_from_professor_email():
    """教授在信裡親口說的經費（本人轉述）：改成她主持、補上期間，證據記「本人轉述教授來信」；沒有的 key 也能新增。"""
    from pipeline.grants import apply_owner_grants
    grants = [{"key": "ID:NHMRC2017642", "status": "confirmed", "target_role": "pi", "start": None, "end": None, "evidence": [], "works": []},
              {"key": "FUNDER:sydney horizon fellowship", "status": "acknowledged", "target_role": "acknowledged", "evidence": [], "works": ["W1"]}]
    dec = {"grant_overrides": {
        "ID:NHMRC2017642": {"start": "2023", "end": "2027-12", "note": "教授 2026-09-21 來信"},
        "FUNDER:sydney horizon fellowship": {"status": "confirmed", "target_role": "pi", "start": "2024", "end": "2029", "note": "教授 2026-09-21 來信"},
        "OWNER:new": {"status": "confirmed", "target_role": "pi", "funder": "X", "note": "教授來信"}}}
    out = apply_owner_grants(grants, dec)
    by = {g["key"]: g for g in out}
    assert by["ID:NHMRC2017642"]["end"] == "2027-12" and by["ID:NHMRC2017642"]["status"] == "confirmed"
    h = by["FUNDER:sydney horizon fellowship"]
    assert h["status"] == "confirmed" and h["target_role"] == "pi" and h["works"] == ["W1"]
    assert h["evidence"][-1] == {"type": "owner", "text": "教授 2026-09-21 來信"}
    assert by["OWNER:new"]["funder"] == "X" and by["OWNER:new"]["works"] == []
    assert apply_owner_grants(grants, {}) == grants
