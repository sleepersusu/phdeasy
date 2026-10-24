from pipeline.works import (
    reconstruct_abstract,
    normalize_work,
    dedupe,
    card_kind,
)

TARGET = "A1"


def raw(wid, title, year=2023, type_="article", doi=None, **kw):
    w = {
        "id": f"https://openalex.org/{wid}",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "title": title,
        "publication_year": year,
        "type": type_,
        "authorships": [
            {
                "author_position": "first",
                "author": {"id": "https://openalex.org/A2", "display_name": "B Co", "orcid": None},
                "institutions": [{"display_name": "UCSF"}],
                "is_corresponding": False,
            },
            {
                "author_position": "last",
                "author": {"id": f"https://openalex.org/{TARGET}", "display_name": "Target", "orcid": None},
                "institutions": [{"display_name": "UCSF"}],
                "is_corresponding": True,
            },
        ],
        "ids": {},
        "abstract_inverted_index": None,
        "best_oa_location": None,
        "locations": [],
        "primary_location": {"source": {"display_name": "J Test"}},
        "primary_topic": None,
        "is_retracted": False,
    }
    w.update(kw)
    return w


def test_reconstruct_abstract_orders_by_position():
    inv = {"world": [1], "hello": [0], "again": [3], "hello,": [2]}
    assert reconstruct_abstract(inv) == "hello world hello, again"


def test_reconstruct_abstract_none():
    assert reconstruct_abstract(None) is None


def test_normalize_strips_prefixes_and_finds_target():
    w = normalize_work(raw("W9", "T", doi="10.1/ABC"), TARGET)
    assert w["id"] == "W9"
    assert w["doi"] == "10.1/abc"
    assert w["authors"][1]["id"] == TARGET
    assert w["target_position"] == "last"
    assert w["target_corresponding"] is True
    assert w["venue"] == "J Test"


def test_normalize_collects_pdf_candidates_without_duplicates():
    w = normalize_work(
        raw(
            "W9",
            "T",
            best_oa_location={"pdf_url": "http://a/x.pdf"},
            locations=[{"pdf_url": "http://a/x.pdf"}, {"pdf_url": "http://b/y.pdf"}, {"pdf_url": None}],
            ids={"pmcid": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123"},
        ),
        TARGET,
    )
    assert w["pdf_candidates"] == ["http://a/x.pdf", "http://b/y.pdf"]
    assert w["pmcid"] == "PMC123"


def test_card_kind():
    assert card_kind("article") == "full"
    assert card_kind("review") == "full"
    assert card_kind("preprint") == "full"
    assert card_kind("conference-abstract") == "short"
    assert card_kind("editorial") == "short"
    assert card_kind("erratum") == "short"


def _norm(*raws):
    return [normalize_work(r, TARGET) for r in raws]


def test_dedupe_filters_years_outside_range():
    kept, dropped = dedupe(_norm(raw("W1", "Old", year=2021), raw("W2", "New", year=2022)), 2022, 2026)
    assert [w["id"] for w in kept] == ["W2"]
    assert dropped[0]["id"] == "W1" and dropped[0]["reason"] == "year_out_of_range"


def test_dedupe_same_doi_keeps_one():
    kept, dropped = dedupe(_norm(raw("W1", "A", doi="10.1/x"), raw("W2", "A copy", doi="10.1/X")), 2022, 2026)
    assert len(kept) == 1
    assert dropped[0]["reason"] == "same_doi"


def test_dedupe_jmir_preprint_paired_by_doi_pattern():
    kept, dropped = dedupe(
        _norm(
            raw("W1", "Analyzing Public Conversations About Heart Disease", doi="10.2196/40764"),
            raw("W2", "Totally Different Wording Here", type_="preprint", doi="10.2196/preprints.40764"),
        ),
        2022,
        2026,
    )
    assert [w["id"] for w in kept] == ["W1"]
    assert dropped[0]["reason"] == "preprint_of" and dropped[0]["kept"] == "W1"


def test_dedupe_preprint_paired_by_similar_title():
    kept, dropped = dedupe(
        _norm(
            raw("W1", "Analyzing Public Conversations About Heart Disease and Stroke on Twitter", doi="10.2196/1"),
            raw("W2", "Analyzing Public Conversations of Heart Disease and Stroke on Twitter", type_="preprint", doi="10.21203/rs.3"),
        ),
        2022,
        2026,
    )
    assert [w["id"] for w in kept] == ["W1"]
    assert dropped[0]["kept"] == "W1"


def test_dedupe_preprint_pdf_becomes_fallback_for_published():
    kept, _ = dedupe(
        _norm(
            raw("W1", "Same Title Of A Study", doi="10.1/a"),
            raw("W2", "Same Title Of A Study", type_="preprint", best_oa_location={"pdf_url": "http://pre/p.pdf"}),
        ),
        2022,
        2026,
    )
    assert "http://pre/p.pdf" in kept[0]["pdf_candidates"]
    assert kept[0]["preprint_ids"] == ["W2"]


def test_dedupe_unpaired_preprint_kept():
    kept, dropped = dedupe(_norm(raw("W1", "Alone", type_="preprint")), 2022, 2026)
    assert [w["id"] for w in kept] == ["W1"] and dropped == []


def test_dedupe_flags_but_keeps_near_duplicate_articles():
    kept, dropped = dedupe(
        _norm(
            raw("W1", "Quality of life among colorectal cancer survivors", doi="10.1/a"),
            raw("W2", "Quality of life among colorectal cancer survivors", doi="10.1/b"),
        ),
        2022,
        2026,
    )
    assert len(kept) == 2 and dropped == []
    assert kept[1]["possible_duplicate_of"] == "W1"


def test_dedupe_conference_abstract_not_merged_into_article():
    kept, _ = dedupe(
        _norm(
            raw("W1", "Perceived Susceptibility to and Severity of Cardiovascular Disease", doi="10.1/a"),
            raw("W2", "Abstract 15069: Perceived Susceptibility to and Severity of Cardiovascular Disease", type_="conference-abstract"),
        ),
        2022,
        2026,
    )
    assert len(kept) == 2
    assert kept[1]["kind"] == "short"


def test_fill_target_by_name_when_author_id_missing():
    from pipeline.works import fill_target_by_name
    r = raw("W9", "T")
    r["authorships"][1]["author"] = {"id": None, "display_name": "Yoshimi Fukuoka", "orcid": None}
    w = normalize_work(r, TARGET)
    assert w["target_position"] is None
    fill_target_by_name(w, "Fukuoka")
    assert w["target_position"] == "last" and w["target_corresponding"] is True
    assert w["target_link"] == "name_only"


def test_fill_target_by_name_noop_when_linked():
    from pipeline.works import fill_target_by_name
    w = normalize_work(raw("W9", "T"), TARGET)
    fill_target_by_name(w, "Target")
    assert "target_link" not in w
