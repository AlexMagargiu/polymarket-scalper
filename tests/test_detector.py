from scalper.detector import SurgeDetector
from scalper.models import Direction, Market


def _make_market(token_yes="tok_yes", token_no="tok_no"):
    m = Market(
        condition_id="cond_1",
        token_id_yes=token_yes,
        token_id_no=token_no,
        name="Test Market",
        volume_24h=50000,
    )
    return {token_yes: m, token_no: m}


def test_surge_up_triggers():
    det = SurgeDetector(token_to_market=_make_market())
    base_time = 1000.0

    det.on_price_update("tok_yes", 0.19, 0.21, base_time - 40)
    det.on_price_update("tok_yes", 0.19, 0.21, base_time - 35)

    result = det.on_price_update("tok_yes", 0.30, 0.32, base_time)

    assert result is not None
    assert result.direction == Direction.UP
    assert result.magnitude >= 0.10
    assert result.market_name == "Test Market"


def test_surge_down_triggers():
    det = SurgeDetector(token_to_market=_make_market())
    base_time = 1000.0

    det.on_price_update("tok_yes", 0.79, 0.81, base_time - 40)
    det.on_price_update("tok_yes", 0.79, 0.81, base_time - 35)

    result = det.on_price_update("tok_yes", 0.68, 0.70, base_time)

    assert result is not None
    assert result.direction == Direction.DOWN
    assert result.magnitude >= 0.10


def test_below_threshold_no_surge():
    det = SurgeDetector(token_to_market=_make_market())
    base_time = 1000.0

    det.on_price_update("tok_yes", 0.19, 0.21, base_time - 40)

    result = det.on_price_update("tok_yes", 0.28, 0.30, base_time)

    assert result is None


def test_outside_window_no_surge():
    det = SurgeDetector(token_to_market=_make_market())
    base_time = 1000.0

    det.on_price_update("tok_yes", 0.19, 0.21, base_time - 90)

    result = det.on_price_update("tok_yes", 0.30, 0.32, base_time)

    assert result is None


def test_cooldown_prevents_duplicate():
    det = SurgeDetector(token_to_market=_make_market())

    # First surge at t=1000: seed at t=960 (40s ago), fire at t=1000
    det.on_price_update("tok_yes", 0.19, 0.21, 960.0)
    result1 = det.on_price_update("tok_yes", 0.30, 0.32, 1000.0)
    assert result1 is not None

    # Second attempt at t=1010: still within 60s cooldown of t=1000
    # Use a fresh detector window by seeding far enough back
    det2 = SurgeDetector(token_to_market=_make_market())
    det2._cooldowns = det._cooldowns.copy()  # carry over cooldown state
    det2.on_price_update("tok_yes", 0.19, 0.21, 970.0)
    result2 = det2.on_price_update("tok_yes", 0.30, 0.32, 1010.0)
    assert result2 is None  # blocked by cooldown

    # Third attempt at t=1061: cooldown expired (61s after t=1000)
    det3 = SurgeDetector(token_to_market=_make_market())
    det3._cooldowns = det._cooldowns.copy()
    det3.on_price_update("tok_yes", 0.19, 0.21, 1021.0)
    result3 = det3.on_price_update("tok_yes", 0.30, 0.32, 1061.0)
    assert result3 is not None  # cooldown expired


def test_window_boundary_just_inside():
    """Point at exactly 30s ago (window_end boundary) should be included."""
    det = SurgeDetector(token_to_market=_make_market())
    # Seed at exactly t-30 (window_end = timestamp - DETECTION_WINDOW_MIN = 1000 - 30 = 970)
    det.on_price_update("tok_yes", 0.19, 0.21, 970.0)
    result = det.on_price_update("tok_yes", 0.30, 0.32, 1000.0)
    assert result is not None  # 30s ago is inside the window


def test_window_boundary_just_outside():
    """Point at 29s ago (just outside the 30-60s window) should NOT be used."""
    det = SurgeDetector(token_to_market=_make_market())
    # Seed at t-29 — this is MORE recent than window_end (30s ago), so outside
    det.on_price_update("tok_yes", 0.19, 0.21, 971.0)
    result = det.on_price_update("tok_yes", 0.30, 0.32, 1000.0)
    assert result is None  # 29s ago is outside the 30-60s window


def test_separate_tokens_independent():
    token_map = {
        "tok_a": Market("cond_a", "tok_a", "tok_a_no", "Market A", 50000),
        "tok_b": Market("cond_b", "tok_b", "tok_b_no", "Market B", 50000),
    }
    det = SurgeDetector(token_to_market=token_map)
    base_time = 1000.0

    det.on_price_update("tok_a", 0.19, 0.21, base_time - 40)
    det.on_price_update("tok_b", 0.49, 0.51, base_time - 40)

    result_a = det.on_price_update("tok_a", 0.30, 0.32, base_time)
    result_b = det.on_price_update("tok_b", 0.54, 0.56, base_time)

    assert result_a is not None
    assert result_b is None


def test_old_data_pruned():
    det = SurgeDetector(token_to_market=_make_market())

    det.on_price_update("tok_yes", 0.29, 0.31, 0.0)
    assert len(det._windows["tok_yes"]) == 1

    det.on_price_update("tok_yes", 0.29, 0.31, 130.0)
    assert len(det._windows["tok_yes"]) == 1


def test_stats_tracking():
    det = SurgeDetector(token_to_market=_make_market())
    base_time = 1000.0

    det.on_price_update("tok_yes", 0.19, 0.21, base_time - 40)
    det.on_price_update("tok_yes", 0.30, 0.32, base_time)

    stats = det.get_stats()
    assert stats["surges_up"] == 1
    assert stats["surges_down"] == 0
    assert stats["active_windows"] >= 1


def test_recent_surges_ring_buffer():
    det = SurgeDetector(token_to_market=_make_market())
    base_time = 1000.0

    det.on_price_update("tok_yes", 0.19, 0.21, base_time - 40)
    det.on_price_update("tok_yes", 0.30, 0.32, base_time)

    recent = det.get_recent_surges()
    assert len(recent) == 1
    assert recent[0]["direction"] == "up"
    assert recent[0]["traded"] is False
    assert recent[0]["magnitude"] >= 0.10


def test_prune_stale_tokens():
    det = SurgeDetector(token_to_market=_make_market())

    det.on_price_update("tok_yes", 0.29, 0.31, 1000.0)
    assert "tok_yes" in det._windows

    det.prune_stale_tokens(now=1000.0 + 660)
    assert "tok_yes" not in det._windows
