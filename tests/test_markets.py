import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scalper import config
from scalper.markets import (
    _parse_market,
    compute_market_changes,
    fetch_markets,
    get_all_token_ids,
)
from scalper.models import Market


def _make_gamma_item(
    condition_id="cond_0",
    question="Test Market?",
    tokens=None,
    volume=50_000,
    category="Crypto",
):
    if tokens is None:
        tokens = ["yes_0", "no_0"]
    return {
        "conditionId": condition_id,
        "question": question,
        "clobTokenIds": json.dumps(tokens),
        "volume24hr": volume,
        "category": category,
        "active": True,
        "closed": False,
    }


def _make_market(cid, name="M", volume=50_000, cat="Crypto"):
    return Market(
        condition_id=cid,
        token_id_yes=f"{cid}_yes",
        token_id_no=f"{cid}_no",
        name=name,
        volume_24h=volume,
        category=cat,
    )


def test_parse_market_valid():
    item = _make_gamma_item(
        condition_id="abc123",
        question="Will X happen?",
        tokens=["tok_yes", "tok_no"],
        volume=75_000,
        category="Politics",
    )
    m = _parse_market(item)
    assert m is not None
    assert m.condition_id == "abc123"
    assert m.token_id_yes == "tok_yes"
    assert m.token_id_no == "tok_no"
    assert m.name == "Will X happen?"
    assert m.volume_24h == 75_000
    assert m.category == "Politics"


def test_parse_market_low_volume():
    item = _make_gamma_item(volume=5_000)
    assert _parse_market(item) is None


def test_parse_market_missing_condition_id():
    item = _make_gamma_item()
    item["conditionId"] = ""
    assert _parse_market(item) is None


def test_parse_market_missing_tokens():
    item = _make_gamma_item()
    item["clobTokenIds"] = ""
    assert _parse_market(item) is None


def test_parse_market_invalid_token_json():
    item = _make_gamma_item()
    item["clobTokenIds"] = "not json"
    assert _parse_market(item) is None


def _mock_response(data, status=200):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=data)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


@pytest.mark.asyncio
async def test_fetch_markets_pagination():
    page1 = [
        _make_gamma_item(
            condition_id=f"cond_{i}",
            tokens=[f"yes_{i}", f"no_{i}"],
            volume=100_000 - i * 100,
        )
        for i in range(100)
    ]
    page2 = [
        _make_gamma_item(
            condition_id=f"cond_{100 + i}",
            tokens=[f"yes_{100 + i}", f"no_{100 + i}"],
            volume=90_000 - i * 100,
        )
        for i in range(50)
    ]

    session_mock = MagicMock()
    session_mock.get = MagicMock(side_effect=[
        _mock_response(page1),
        _mock_response(page2),
    ])
    session_mock.__aenter__ = AsyncMock(return_value=session_mock)
    session_mock.__aexit__ = AsyncMock(return_value=False)

    with patch("scalper.markets.aiohttp.ClientSession", return_value=session_mock):
        markets = await fetch_markets()

    assert len(markets) == 150
    assert markets[0].volume_24h >= markets[-1].volume_24h
    assert session_mock.get.call_count == 2


def test_get_all_token_ids():
    markets = [_make_market(f"c{i}") for i in range(3)]
    tokens = get_all_token_ids(markets)
    assert len(tokens) == 6
    assert "c0_yes" in tokens
    assert "c0_no" in tokens
    assert "c2_yes" in tokens


def test_compute_market_changes():
    old = [_make_market("A"), _make_market("B"), _make_market("C")]
    new = [_make_market("B"), _make_market("C"), _make_market("D")]
    added, removed = compute_market_changes(old, new)

    assert set(added) == {"D_yes", "D_no"}
    assert set(removed) == {"A_yes", "A_no"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_markets_live():
    markets = await fetch_markets()
    assert len(markets) > 0
    print(f"\nFound {len(markets)} markets")
    for m in markets[:5]:
        print(f"  {m.name[:60]} — ${m.volume_24h:,.0f} — {m.category}")
    assert all(m.volume_24h >= config.MIN_VOLUME_24H for m in markets)
    assert all(m.token_id_yes for m in markets)
    assert all(m.token_id_no for m in markets)
