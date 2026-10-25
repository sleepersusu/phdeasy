"""雙語：翻譯的條數、數字、空白都要被腳本抓到。"""
from pipeline.i18n import card_items, check_card_i18n, check_grants_i18n


def card():
    return {"id": "W1", "fields": {
        "summary": {"status": "ok", "text": "92 位女性，知識分數由 2.4 升到 3.1。", "citations": []},
        "design": {"status": "ok", "type": "rct", "text": "隨機對照試驗", "citations": []},
        "sample": {"status": "not_in_source"},
        "gap": {"status": "ok", "claims": [{"text": "缺乏聊天機器人研究", "citations": []}]},
        "solves": {"status": "not_in_source", "claims": []},
        "findings": {"status": "ok", "claims": [{"text": "P<.001", "citations": []}, {"text": "滿意度 88%", "citations": []}]},
        "limitations": {"status": "ok", "author_stated": [{"text": "便利樣本", "citations": []}], "inferred": [{"text": "無對照組", "basis": "單組", "citations": []}]},
    }}


GOOD = {"id": "W1", "title_zh": "聊天機器人研究",
        "en": {"summary": "92 women; knowledge scores rose from 2.4 to 3.1.", "design": "Randomized controlled trial",
               "gap": ["Few chatbot studies"], "findings": ["P<.001", "Satisfaction was 88%"],
               "limitations": {"author_stated": ["Convenience sample"], "inferred": ["No control group"]}},
        "keywords_zh": ["聊天機器人", "女性", "心臟病", "知識", "隨機對照試驗"],
        "keywords_en": ["chatbot", "women", "heart attack", "knowledge", "RCT"]}


def test_card_items_lists_only_present_texts():
    paths = [p for p, _ in card_items(card())]
    assert paths == ["summary", "design", "gap[0]", "findings[0]", "findings[1]", "limitations.author_stated[0]", "limitations.inferred[0]"]


def test_good_translation_passes():
    assert check_card_i18n(card(), GOOD) == []


def test_missing_item_caught():
    bad = {**GOOD, "en": {**GOOD["en"], "findings": ["P<.001"]}}
    assert any(f["path"] == "findings[1]" and f["why"] == "missing" for f in check_card_i18n(card(), bad))


def test_changed_number_caught():
    bad = {**GOOD, "en": {**GOOD["en"], "summary": "92 women; knowledge scores rose from 2.4 to 3.5."}}
    fails = check_card_i18n(card(), bad)
    assert any(f["path"] == "summary" and f["why"].startswith("numbers_differ") for f in fails)


def test_empty_translation_and_missing_title_caught():
    bad = {**GOOD, "title_zh": "", "en": {**GOOD["en"], "design": "  "}}
    whys = {(f["path"], f["why"]) for f in check_card_i18n(card(), bad)}
    assert ("title_zh", "empty") in whys and ("design", "empty") in whys


def test_keywords_needed_in_both_languages():
    bad = {**GOOD, "keywords_en": ["chatbot"]}
    assert any(f["path"] == "keywords_en" for f in check_card_i18n(card(), bad))


def test_grants_i18n_checks_title_and_abstract_numbers():
    grants = [{"key": "G1", "title": "Diabetes prevention in 2021", "abstract": "We will enroll 300 adults over 5 years."},
              {"key": "G2", "title": None, "funder": "Noyce Foundation", "abstract": None}]
    good = {"G1": {"title_zh": "2021 年糖尿病預防", "summary_en": "Enrolls 300 adults over 5 years.", "summary_zh": "5 年內收案 300 名成人。"},
            "G2": {"funder_zh": "諾伊斯基金會"}}
    assert check_grants_i18n(grants, good) == []
    bad = {"G1": {"title_zh": "糖尿病預防", "summary_en": "Enrolls 400 adults.", "summary_zh": "收案 300 名成人。"}}
    whys = {(f["key"], f["why"].split(":")[0]) for f in check_grants_i18n(grants, bad)}
    assert ("G1", "numbers_differ") in whys          # 標題的 2021 不見了
    assert ("G1", "number_not_in_abstract") in whys  # 400 不在原始摘要
    assert ("G2", "missing") in whys


def test_natural_number_translations_pass():
    from pipeline.i18n import numbers_match
    assert numbers_match("西班牙裔約四成", "about 40% were Hispanic")
    assert numbers_match("第二型糖尿病", "type 2 diabetes")
    assert numbers_match("兩組皆改善", "both 2 groups improved") and numbers_match("兩組皆改善", "both groups improved")
    assert numbers_match("第一個模型", "Model 1") and numbers_match("模型一", "the first model")
    assert numbers_match("共 92 位，十二週", "92 participants over twelve weeks")


def test_dropped_or_changed_digits_still_fail():
    from pipeline.i18n import numbers_match
    assert not numbers_match("西班牙裔約 40%", "a large proportion were Hispanic")  # 阿拉伯數字被丟掉
    assert not numbers_match("92 位女性", "93 women")
    assert not numbers_match("知識分數上升", "scores rose by 15%")  # 英文多出中文沒有的數字


def test_english_ordinal_words_need_not_be_in_chinese():
    from pipeline.i18n import numbers_match
    assert numbers_match("首要目標是建立模型，其次評估成效", "The first aim is to build a model; the second evaluates outcomes")
    assert numbers_match("第 1 個目標", "the first aim")  # 中文的 1 由 first 滿足
    assert not numbers_match("首要目標", "Aim 3 is to build a model")  # 阿拉伯數字仍要在中文找得到


def test_product_names_compounds_and_months():
    from pipeline.i18n import numbers_match
    assert numbers_match("以 Fitbit One 測量步數", "steps were measured with the Fitbit One")
    assert numbers_match("單因子變異數分析", "one-way ANOVA")
    assert numbers_match("共 26 篇研究", "twenty-six studies")
    assert numbers_match("2019 年 5 月 1 日開始", "began on May 1, 2019")
    assert numbers_match("雙臂試驗", "a two-arm trial")
    assert not numbers_match("共 26 篇研究", "twenty-five studies")
    assert not numbers_match("單因子變異數分析", "ANOVA with 3 factors")  # 多出的阿拉伯數字仍會被抓
