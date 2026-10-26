"""機構不符的標記：OpenAlex 沒給「最近機構」時，改用他在這批文章裡常掛的機構，不要整批都標不符。"""
from setup_list_works import affiliation_flags, main_institutions


def w(i, *insts):
    return {"id": i, "title": i, "authors": [{"id": "A1", "institutions": list(insts)}, {"id": "A2", "institutions": ["Other U"]}]}


def test_main_institutions_falls_back_to_frequent_ones():
    works = [w(f"W{i}", "UCSF") for i in range(8)] + [w("W8", "UCSF", "UC Berkeley"), w("W9", "UC Berkeley"), w("W10", "Duke University")]
    assert main_institutions({"last_known_institutions": [{"display_name": "UCSF"}]}, works, "A1") == {"UCSF"}
    got = main_institutions({"last_known_institutions": None}, works, "A1")  # OpenAlex 沒給：用 ≥10% 的文章都掛的機構
    assert got == {"UCSF", "UC Berkeley"}
    assert [f["id"] for f in affiliation_flags(works, "A1", got)] == ["W10"]  # 只標真的少見的，不是整批


def test_empty_main_institutions_flags_nothing():
    assert affiliation_flags([w("W1", "UCSF")], "A1", set()) == []
