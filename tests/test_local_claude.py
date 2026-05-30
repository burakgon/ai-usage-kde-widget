from datetime import date

from conftest import fixture
from ai_usage_kde.usage.local_claude import aggregate_files


def test_aggregate_today_tokens_and_cost():
    today = date(2026, 5, 30)
    res = aggregate_files([fixture("transcript_sample.jsonl")], today=today)
    # today's assistant lines: opus(1000 in,1000 out) + sonnet(1e6 in)
    assert res.today_tokens == 1000 + 1000 + 1_000_000
    # cost: opus (1000/1e6*15 + 1000/1e6*75) + sonnet (1e6/1e6*3) = 0.015+0.075+3.0
    assert round(res.today_cost_usd, 6) == round(0.015 + 0.075 + 3.0, 6)


def test_model_split_by_tokens_today():
    today = date(2026, 5, 30)
    res = aggregate_files([fixture("transcript_sample.jsonl")], today=today)
    # opus tokens today = 2000, sonnet = 1_000_000 -> sonnet dominates
    assert round(res.model_split["sonnet"], 4) == round(1_000_000 / 1_002_000, 4)
    assert round(res.model_split["opus"], 4) == round(2_000 / 1_002_000, 4)


def test_last7days_has_two_dated_buckets():
    today = date(2026, 5, 30)
    res = aggregate_files([fixture("transcript_sample.jsonl")], today=today)
    by_date = {d.date: d for d in res.last7days}
    assert by_date[date(2026, 5, 30)].tokens == 1_002_000
    assert by_date[date(2026, 5, 29)].tokens == 1000  # opus 500 in + 500 out


def test_pre_cutoff_line_excluded():
    today = date(2026, 5, 30)  # 7-day window is 2026-05-24 .. 2026-05-30
    res = aggregate_files([fixture("transcript_sample.jsonl")], today=today)
    # the 2026-05-23 line (7777 tokens) is before the cutoff and must be dropped
    assert res.today_tokens == 1_002_000
    assert sum(b.tokens for b in res.last7days) == 1_002_000 + 1000
    assert date(2026, 5, 23) not in {b.date for b in res.last7days}
