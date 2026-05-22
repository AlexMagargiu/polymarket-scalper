from scalper.detector import TrendDetector
from scalper.models import Market


def _make_market(token_yes="tok_yes"):
    m = Market(
        condition_id="cond_1",
        token_id_yes=token_yes,
        token_id_no=token_yes + "_no",
        name="Test Market",
        volume_24h=50000,
    )
    return {token_yes: m}


def _feed_surge(det, token_id, bid, ask, timestamp):
    """Feed a price update that should register as a surge.
    Seeds a low price 40s earlier, then fires the high price.
    Returns (surge, trend) tuple."""
    low_bid = bid - 0.12
    low_ask = ask - 0.12
    det.on_price_update(token_id, low_bid, low_ask, timestamp - 40)
    surge, trend = det.on_price_update(token_id, bid, ask, timestamp)
    return surge, trend


def test_single_surge_no_trend():
    det = TrendDetector(token_to_market=_make_market())
    surge, trend = _feed_surge(det, "tok_yes", 0.29, 0.31, 1000.0)
    assert surge is not None
    assert trend is None


def test_two_surges_no_trend():
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.29, 0.31, 1000.0)
    surge, trend = _feed_surge(det, "tok_yes", 0.39, 0.41, 1060.0)
    assert surge is not None
    assert trend is None


def test_three_ascending_surges_triggers_trend():
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.19, 0.21, 1000.0)
    _feed_surge(det, "tok_yes", 0.29, 0.31, 1060.0)
    surge, trend = _feed_surge(det, "tok_yes", 0.39, 0.41, 1120.0)
    assert trend is not None
    assert trend.surge_count >= 3
    assert trend.market_name == "Test Market"
    assert trend.first_surge_price < trend.current_price


def test_three_surges_not_ascending_no_trend():
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.29, 0.31, 1000.0)
    _feed_surge(det, "tok_yes", 0.39, 0.41, 1060.0)
    surge, trend = _feed_surge(det, "tok_yes", 0.24, 0.26, 1120.0)
    assert trend is None


def test_staircase_with_pullback_triggers_trend():
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.26, 0.28, 1000.0)
    _feed_surge(det, "tok_yes", 0.36, 0.38, 1060.0)
    _feed_surge(det, "tok_yes", 0.31, 0.33, 1120.0)
    surge, trend = _feed_surge(det, "tok_yes", 0.39, 0.41, 1180.0)
    assert trend is not None
    assert trend.surge_count >= 3


def test_trend_cooldown_prevents_duplicate():
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.19, 0.21, 1000.0)
    _feed_surge(det, "tok_yes", 0.29, 0.31, 1060.0)
    surge1, trend1 = _feed_surge(det, "tok_yes", 0.39, 0.41, 1120.0)
    assert trend1 is not None
    surge2, trend2 = _feed_surge(det, "tok_yes", 0.49, 0.51, 1180.0)
    assert trend2 is None


def test_surge_history_pruned_after_window():
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.19, 0.21, 1000.0)
    _feed_surge(det, "tok_yes", 0.29, 0.31, 1060.0)
    surge, trend = _feed_surge(det, "tok_yes", 0.39, 0.41, 1961.0)
    assert trend is None


def test_separate_tokens_independent():
    token_map = {
        "tok_a": Market("cond_a", "tok_a", "tok_a_no", "Market A", 50000),
        "tok_b": Market("cond_b", "tok_b", "tok_b_no", "Market B", 50000),
    }
    det = TrendDetector(token_to_market=token_map)
    _feed_surge(det, "tok_a", 0.19, 0.21, 1000.0)
    _feed_surge(det, "tok_a", 0.29, 0.31, 1060.0)
    surge_a, trend_a = _feed_surge(det, "tok_a", 0.39, 0.41, 1120.0)
    surge_b, trend_b = _feed_surge(det, "tok_b", 0.29, 0.31, 1120.0)
    assert trend_a is not None
    assert trend_b is None


def test_prune_stale_tokens():
    det = TrendDetector(token_to_market=_make_market())
    det.on_price_update("tok_yes", 0.29, 0.31, 1000.0)
    assert "tok_yes" in det._windows
    det.prune_stale_tokens(now=1000.0 + 660)
    assert "tok_yes" not in det._windows


def test_get_stats():
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.19, 0.21, 1000.0)
    _feed_surge(det, "tok_yes", 0.29, 0.31, 1060.0)
    _feed_surge(det, "tok_yes", 0.39, 0.41, 1120.0)
    stats = det.get_stats()
    assert stats["surges_detected"] >= 3
    assert stats["trends_fired"] >= 1
    assert stats["active_windows"] >= 1


def test_get_recent_surges():
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.19, 0.21, 1000.0)
    recent = det.get_recent_surges()
    assert len(recent) >= 1
    assert recent[0]["direction"] == "up"
