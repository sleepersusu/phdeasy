from pipeline.crosscheck import (
    orcid_records,
    pubmed_records,
    europepmc_records,
    s2_records,
    pick_s2_author,
    arxiv_records,
    external_only,
)


def test_orcid_records_filters_year_and_lowercases():
    data = {
        "group": [
            {
                "external-ids": {"external-id": [{"external-id-type": "doi", "external-id-value": "10.1/ABC"}]},
                "work-summary": [{"publication-date": {"year": {"value": "2023"}}, "title": {"title": {"value": "T1"}}}],
            },
            {
                "external-ids": {"external-id": [{"external-id-type": "doi", "external-id-value": "10.1/old"}]},
                "work-summary": [{"publication-date": {"year": {"value": "2019"}}, "title": {"title": {"value": "T2"}}}],
            },
            {
                "external-ids": {"external-id": []},
                "work-summary": [{"publication-date": None, "title": {"title": {"value": "T3"}}}],
            },
        ]
    }
    assert orcid_records(data, 2022, 2026) == [{"doi": "10.1/abc", "title": "T1", "year": 2023, "source": "orcid"}]


def test_pubmed_records_reads_esummary():
    data = {
        "result": {
            "uids": ["11", "22"],
            "11": {"title": "A.", "pubdate": "2024 Mar", "articleids": [{"idtype": "doi", "value": "10.1/A"}, {"idtype": "pubmed", "value": "11"}]},
            "22": {"title": "Old.", "pubdate": "2020", "articleids": []},
        }
    }
    assert pubmed_records(data, 2022, 2026) == [{"doi": "10.1/a", "title": "A.", "year": 2024, "source": "pubmed", "pmid": "11"}]


def test_europepmc_records():
    data = {"resultList": {"result": [{"doi": "10.1/X", "title": "X", "pubYear": "2025", "pmid": "9"}, {"title": "noDOI", "pubYear": "2023"}]}}
    recs = europepmc_records(data, 2022, 2026)
    assert recs[0] == {"doi": "10.1/x", "title": "X", "year": 2025, "source": "europepmc", "pmid": "9"}
    assert recs[1]["doi"] is None and recs[1]["title"] == "noDOI"


def test_pick_s2_author_prefers_overlap_with_known_dois():
    cands = {
        "s2-wrong": [{"externalIds": {"DOI": "10.9/zzz"}}],
        "s2-right": [{"externalIds": {"DOI": "10.1/A"}}, {"externalIds": {"DOI": "10.1/b"}}],
    }
    assert pick_s2_author(cands, {"10.1/a", "10.1/b"}) == "s2-right"


def test_pick_s2_author_none_when_no_overlap():
    assert pick_s2_author({"x": [{"externalIds": {"DOI": "10.9/z"}}]}, {"10.1/a"}) is None


def test_s2_records():
    papers = [{"title": "P", "year": 2022, "externalIds": {"DOI": "10.1/P"}, "openAccessPdf": {"url": "http://p.pdf"}}, {"title": "Q", "year": 2010, "externalIds": {}}]
    assert s2_records(papers, 2022, 2026) == [{"doi": "10.1/p", "title": "P", "year": 2022, "source": "semantic_scholar"}]


def test_arxiv_records_parses_atom():
    atom = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
 <entry><id>http://arxiv.org/abs/2301.00001v1</id><published>2023-01-02T00:00:00Z</published>
  <title>Inverse Optimization for
   Physical Activity</title><arxiv:doi>10.1/ARX</arxiv:doi></entry>
 <entry><id>http://arxiv.org/abs/1901.1v1</id><published>2019-01-02T00:00:00Z</published><title>Old</title></entry>
</feed>"""
    assert arxiv_records(atom, 2022, 2026) == [
        {"doi": "10.1/arx", "title": "Inverse Optimization for Physical Activity", "year": 2023, "source": "arxiv", "arxiv_id": "2301.00001"}
    ]


def test_external_only_by_doi_and_title_and_merges_sources():
    works = [
        {"doi": "10.1/a", "title": "Known Study About Walking", "merged_dois": ["10.2196/preprints.1"]},
    ]
    recs = [
        {"doi": "10.1/a", "title": "x", "source": "orcid"},
        {"doi": "10.2196/preprints.1", "title": "y", "source": "pubmed"},
        {"doi": None, "title": "Known study about walking", "source": "arxiv"},
        {"doi": "10.1/new", "title": "New One", "year": 2024, "source": "pubmed"},
        {"doi": "10.1/NEW", "title": "New One", "year": 2024, "source": "europepmc"},
    ]
    out = external_only(works, recs)
    assert len(out) == 1
    assert out[0]["doi"] == "10.1/new"
    assert out[0]["sources"] == ["europepmc", "pubmed"]


def test_epmc_abstract_strips_tags():
    from pipeline.crosscheck import epmc_abstract
    data = {"resultList": {"result": [{"abstractText": "<h4>Background</h4>Heart <i>attack</i> risk.<br/>Done."}]}}
    assert epmc_abstract(data) == "Background Heart attack risk. Done."
    assert epmc_abstract({"resultList": {"result": []}}) is None
