"""Run: python test_listener.py — parse_bid against shapes captured from Autura's Ably feed on 2026-11-18."""
import sys, types

# parse_bid is pure; stub the listener's runtime imports so this runs without Ably or a database
sys.modules.setdefault("ably", types.SimpleNamespace(AblyRealtime=object))
sys.modules.setdefault("db", types.SimpleNamespace(get_db=None, query=None))
from scrapers.autura.auction_listener import parse_bid

END = "2026-11-18T18:18:26.000000Z"
def msg(bid, winning=None, winning_total=None):
    d = {"bid": {"bid_amount": bid, "total_amount": bid + bid // 8, "auction": {"bidding_end_at": END}}}
    if winning is not None:
        d["inventory"] = {"winningBid": {"bid_amount": winning, "total_amount": winning_total}}
    return d

CASES = [
    ("proxy beat the placed bid: standing bid wins", msg(40000, 42500, 47813), (425.0, END)),
    ("placed bid is the winning bid",               msg(60000, 60000, 67500), (600.0, END)),
    ("no inventory: fall back to the placed bid",   msg(50000),               (500.0, END)),
    ("no amount at all",                            {"bid": {}},              None),
]
for label, data, expected in CASES:
    assert parse_bid(data) == expected, (label, parse_bid(data))
print(f"ok: {len(CASES)} cases")

# Anything that isn't a bid (AUCTION_UPDATED) re-reads the lot instead of being parsed as one
import asyncio
from scrapers.autura import auction_listener as L
seen = []
L._refresh_lot = seen.append
asyncio.run(L._on_update("A1", types.SimpleNamespace(name="AUCTION_UPDATED", data={"auction_id": "A1"})))
assert seen == ["A1"], seen
print("ok: AUCTION_UPDATED -> lot refresh")
