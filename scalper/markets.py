import json
import logging

import aiohttp

from scalper import config
from scalper.models import Market

logger = logging.getLogger(__name__)


def _parse_market(item: dict) -> Market | None:
    condition_id = item.get("conditionId", "")
    if not condition_id:
        return None

    raw_tokens = item.get("clobTokenIds", "")
    if not raw_tokens:
        return None

    try:
        tokens = json.loads(raw_tokens) if isinstance(raw_tokens, str) else raw_tokens
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(tokens, list) or len(tokens) < 2:
        return None

    volume = float(item.get("volume24hr") or 0)
    if volume < config.MIN_VOLUME_24H:
        return None

    return Market(
        condition_id=condition_id,
        token_id_yes=tokens[0],
        token_id_no=tokens[1],
        name=item.get("question", "Unknown"),
        volume_24h=volume,
        category=item.get("category") or "",
    )


async def fetch_markets() -> list[Market]:
    all_markets: list[Market] = []
    offset = 0
    limit = 100

    async with aiohttp.ClientSession() as session:
        while True:
            params = {
                "active": "true",
                "closed": "false",
                "limit": str(limit),
                "offset": str(offset),
                "order": "volume24hr",
                "ascending": "false",
            }
            async with session.get(config.GAMMA_API_URL, params=params) as resp:
                if resp.status != 200:
                    logger.error("Gamma API returned %d", resp.status)
                    break
                data = await resp.json()

            if not data:
                break

            for item in data:
                market = _parse_market(item)
                if market is not None:
                    all_markets.append(market)

            if len(data) < limit:
                break
            offset += limit

            if all(
                (item.get("volume24hr") or 0) < config.MIN_VOLUME_24H
                for item in data
            ):
                break

    all_markets.sort(key=lambda m: m.volume_24h, reverse=True)
    logger.info(
        "Fetched %d qualifying markets (total volume: $%s)",
        len(all_markets),
        f"{sum(m.volume_24h for m in all_markets):,.0f}",
    )
    return all_markets


def get_all_token_ids(markets: list[Market]) -> list[str]:
    return [m.token_id_yes for m in markets]


def compute_market_changes(
    old: list[Market], new: list[Market]
) -> tuple[list[str], list[str]]:
    old_conds = {m.condition_id for m in old}
    new_conds = {m.condition_id for m in new}

    added_conds = new_conds - old_conds
    removed_conds = old_conds - new_conds

    new_by_cond = {m.condition_id: m for m in new}
    old_by_cond = {m.condition_id: m for m in old}

    added_tokens = []
    for cond in added_conds:
        m = new_by_cond[cond]
        added_tokens.append(m.token_id_yes)

    removed_tokens = []
    for cond in removed_conds:
        m = old_by_cond[cond]
        removed_tokens.append(m.token_id_yes)

    return added_tokens, removed_tokens


def build_token_to_market_map(markets: list[Market]) -> dict[str, Market]:
    mapping = {}
    for m in markets:
        mapping[m.token_id_yes] = m
    return mapping


async def refresh_markets(
    current_markets: list[Market],
) -> tuple[list[Market], list[str], list[str]]:
    new_markets = await fetch_markets()
    added_tokens, removed_tokens = compute_market_changes(current_markets, new_markets)
    logger.info(
        "Market refresh: %d added tokens, %d removed tokens",
        len(added_tokens),
        len(removed_tokens),
    )
    return new_markets, added_tokens, removed_tokens
