"""合併閱讀者：中文解析卡的每一句旁邊直接寫英文（text_en），組裝後從留下來的說法產生 i18n.json，條數一定對得上。"""
from pipeline.i18n import check_card_i18n, i18n_from_card

KW = {"title_zh": "穿戴裝置步數預測化放療住院", "keywords_zh": ["穿戴裝置", "步數", "機器學習", "住院", "化放療", "預測"],
      "keywords_en": ["wearable", "step count", "machine learning", "hospitalization", "chemoradiation", "prediction"]}


def card(findings):
    return {"fields": {
        "summary": {"status": "ok", "text": "用 120 位病人的步數預測住院。", "text_en": "Used step counts of 120 patients to predict hospitalization."},
        "design": {"status": "not_in_source"},
        "sample": {"status": "ok", "text": "120 位病人", "text_en": "120 patients"},
        "gap": {"status": "ok", "claims": [{"text": "缺乏即時預測", "text_en": "Lack of real-time prediction"}]},
        "solves": {"status": "not_in_source"},
        "findings": {"status": "ok", "claims": findings},
        "limitations": {"status": "ok", "author_stated": [{"text": "單一中心", "text_en": "Single centre"}], "inferred": []}}}


def test_i18n_follows_surviving_claims():
    a = card([{"text": "AUC 0.83", "text_en": "AUC 0.83"}, {"text": "成本下降 20%", "text_en": "Costs fell 20%"}])
    final = card([{"text": "成本下降 20%", "text_en": "Costs fell 20%"}])  # 推翻者拿掉第一條
    tr = i18n_from_card(final, {**a, **KW})
    assert tr["en"]["findings"] == ["Costs fell 20%"] and tr["title_zh"] == KW["title_zh"]
    assert check_card_i18n(final, tr) == []


def test_missing_english_is_caught():
    final = card([{"text": "成本下降 20%"}])  # 閱讀者漏寫英文
    fails = check_card_i18n(final, i18n_from_card(final, KW))
    assert any(f["path"] == "findings[0]" and f["why"] == "missing" for f in fails)
