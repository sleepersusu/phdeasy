"""工作進度的進度條與預估時間：從批次資料夾裡已產生的檔案數，算出目前在哪一步、做了幾成、還要多久。"""
import json

from pipeline.progress import estimate, steps_of


def mk(tmp_path, stage, n=10, fulltext=0, texts=0, cards=0, extra=()):
    r = tmp_path / "runs" / "x"
    (r / "work" / "text").mkdir(parents=True)
    (r / "state.json").write_text(json.dumps({"stage": stage}))
    (r / "work" / "works.json").write_text(json.dumps([{"id": f"W{i}"} for i in range(n)]))
    (r / "work" / "fulltext_log.jsonl").write_text("".join(json.dumps({"id": f"W{i}", "result": "x"}) + "\n" for i in range(fulltext)))
    for i in range(texts):
        (r / "work" / "text" / f"W{i}.txt").write_text(f"# W{i} | {'pdf' if i % 2 == 0 else 'none'} | t\n")
    for i in range(cards):
        (r / "work" / "cards" / f"W{i}").mkdir(parents=True)
        (r / "work" / "cards" / f"W{i}" / "card.json").write_text("{}")
    for p in extra:
        (r / p).parent.mkdir(parents=True, exist_ok=True)
        (r / p).write_text("{}")
    return r


def test_setup_counts_fulltext_attempts(tmp_path):
    r = mk(tmp_path, "setup", n=10, fulltext=4)
    s = {x["key"]: x for x in steps_of(r)}
    assert s["list"]["done"] == s["list"]["total"] == 1
    assert (s["fulltext"]["done"], s["fulltext"]["total"]) == (4, 10)


def test_cards_and_digest_counts(tmp_path):
    r = mk(tmp_path, "cards", n=10, fulltext=10, texts=10, cards=3, extra=["work/network.json", "out/data/grants.csv"])
    s = {x["key"]: x for x in steps_of(r)}
    assert s["fulltext"]["done"] == 10 and s["ingest"]["done"] == 10 and s["network"]["done"] == 1 and s["grants"]["done"] == 1
    assert (s["cards"]["done"], s["cards"]["total"]) == (3, 10)
    assert s["digest"]["total"] == 5  # 有全文或摘要的才整理重點（none 不算）


def test_estimate_span_stops_at_stop1_for_new_jobs(tmp_path):
    r = mk(tmp_path, "setup", n=10, fulltext=5)
    e = estimate(r, "new")
    assert [x["key"] for x in e["steps"]] == ["list", "fulltext"]  # 新建檔只跑到停 1
    assert e["current"] == "fulltext" and 0 < e["percent"] < 100
    assert e["eta_s"] > 0


def test_estimate_uses_measured_rate(tmp_path):
    r = mk(tmp_path, "cards", n=10, fulltext=10, texts=10, cards=4, extra=["work/network.json", "out/data/grants.csv"])
    # 這一步從 1000 秒時 2 篇，到 1100 秒時 4 篇：每篇 50 秒，剩 6 篇 → 這一步還要 300 秒
    e = estimate(r, "continue", samples={"cards": (1000, 2)}, now=1100)
    cur = next(x for x in e["steps"] if x["key"] == "cards")
    assert cur["eta_s"] == 300 and e["eta_s"] > 300  # 後面的步驟用預設時間加上去
    assert e["steps"][-1]["key"] == "verify"


def test_done_pipeline_is_100(tmp_path):
    r = mk(tmp_path, "stop2", n=2, fulltext=2, texts=2, cards=2,
           extra=["work/network.json", "out/data/grants.csv", "work/digest/W0.json", "out/profile.md", "out/match.json"])
    e = estimate(r, "continue")
    assert e["percent"] == 100 and e["eta_s"] == 0
