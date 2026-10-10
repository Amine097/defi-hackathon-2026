"""Recursive token lineage: decompose a Pendle PT into the tokens and base assets it is a claim on.

PT -> SY -> underlying (Pendle API) -> ERC-4626 asset() (on-chain) -> issuer reserves (data/registry.json) -> base:*
Every edge records weight (share of the parent's value, None = unknown), source, as_of and confidence.
Unknown weights are never guessed: exposure.py turns them into an explicit UNKNOWN share.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import sources

REGISTRY = Path(__file__).resolve().parents[3] / "data" / "registry.json"
BASES = {"base:ETH": "ETH", "base:BTC": "BTC", "base:SOL": "SOL", "base:USD_FIAT": "US dollars (bank/T-bills)",
         "base:HEDGED_DELTA_NEUTRAL": "Hedged crypto (delta-neutral)", "base:UNKNOWN": "Unknown"}
FIAT_STABLES = {"USDC", "USDT", "PYUSD", "USD1", "FDUSD", "TUSD", "USDP", "RLUSD"}
SYNTH_STABLES = {"USDE", "USDS", "DAI", "FRAX", "LUSD", "GHO", "USD0", "CRVUSD", "USDTB", "APXUSD", "USDAT", "TRUSD"}
MAX_DEPTH = 8

_SEL_ASSET, _SEL_CONVERT, _SEL_DECIMALS, _SEL_SYMBOL = "0x38d52e0f", "0x07a2d13a", "0x313ce567", "0x95d89b41"


def load_registry(path: Path = REGISTRY) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("tokens", {})
    except (OSError, ValueError):
        return {}


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _addr(word_hex: str | None) -> str | None:
    if not word_hex or len(word_hex) < 66:
        return None
    a = "0x" + word_hex[-40:].lower()
    return None if int(a, 16) == 0 else a


def _int(word_hex: str | None) -> int | None:
    try:
        return int(word_hex[2:66], 16) if word_hex else None
    except ValueError:
        return None


def _symbol(address: str) -> str | None:
    r = sources.eth_call(address, _SEL_SYMBOL)
    if not r:
        return None
    b = bytes.fromhex(r[2:])
    try:
        n = int.from_bytes(b[32:64], "big")
        if 0 < n <= 64:
            return b[64:64 + n].decode("utf-8", "ignore") or None
    except Exception:
        pass
    return b[:32].rstrip(b"\0").decode("utf-8", "ignore") or None


def erc4626(address: str) -> dict | None:
    """{'asset', 'rate'} if the token answers ERC-4626 asset(); rate = assets per 1 share (None if unreadable)."""
    try:
        asset = _addr(sources.eth_call(address, _SEL_ASSET))
        if not asset:
            return None
        dec, adec = _int(sources.eth_call(address, _SEL_DECIMALS)), _int(sources.eth_call(asset, _SEL_DECIMALS))
        rate = None
        if dec is not None and adec is not None and dec <= 36:
            raw = _int(sources.eth_call(address, _SEL_CONVERT + hex(10 ** dec)[2:].rjust(64, "0")))
            rate = raw / 10 ** adec if raw else None
        return {"asset": asset, "rate": rate}
    except Exception:
        return None


def token_type(symbol: str, reg: dict | None = None, is_4626: bool = False) -> str:
    if reg and reg.get("type"):
        return reg["type"]
    s = (symbol or "").upper()
    if is_4626:
        return "wrapper_4626"
    if s.startswith("PT-"):
        return "pendle_pt"
    if s.startswith("SY-"):
        return "pendle_sy"
    if s in FIAT_STABLES:
        return "stablecoin_fiat"
    if s in SYNTH_STABLES:
        return "stablecoin_synthetic"
    if s in ("WETH", "ETH"):
        return "base"
    return "other"


def is_stable_like(tok: dict) -> bool:
    return tok.get("type") in ("stablecoin_fiat", "stablecoin_synthetic")


class Lineage:
    def __init__(self, root: str):
        self.root = root
        self.tokens: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.cycles: list[dict] = []

    def add_token(self, tid: str, symbol: str, ttype: str, **extra) -> dict:
        t = self.tokens.setdefault(tid, {"id": tid, "symbol": symbol, "type": ttype})
        t.update({k: v for k, v in extra.items() if v is not None})
        return t

    def add_edge(self, parent: str, child: str, weight, source: str, confidence: str, via: str,
                 as_of: str | None = None, **extra) -> None:
        if any(e["parent"] == parent and e["child"] == child for e in self.edges):
            return
        self.edges.append({"parent": parent, "child": child, "weight": weight, "source": source,
                           "as_of": as_of or _today(), "confidence": confidence, "via": via, **extra})

    def children(self, tid: str) -> list[dict]:
        return [e for e in self.edges if e["parent"] == tid]

    def to_dict(self) -> dict:
        return {"root": self.root, "tokens": list(self.tokens.values()), "edges": self.edges, "cycles": self.cycles}


def _expand(lin: Lineage, tid: str, stack: list[str], registry: dict, hints: dict, depth: int) -> None:
    if tid.startswith("base:") or depth > MAX_DEPTH:
        return
    tok = lin.tokens[tid]
    reg = registry.get(tid)
    if not lin.children(tid):
        v = erc4626(tid) if tok.get("type") not in ("pendle_pt", "pendle_sy") else None
        if v:
            tok["type"] = reg.get("type", "wrapper_4626") if reg else "wrapper_4626"
            tok["rate"] = v["rate"]
            child = v["asset"]
            if child not in lin.tokens:
                creg = registry.get(child)
                sym = (creg or {}).get("symbol") or _symbol(child) or child[:10]
                lin.add_token(child, sym, token_type(sym, creg))
            lin.add_edge(tid, child, 1.0, "on-chain ERC-4626 asset()", "high",
                         f"{tok['symbol']} is a vault share redeemable for {lin.tokens[child]['symbol']}"
                         + (f" (1 share = {v['rate']:.4f})" if v["rate"] else ""), rate=v["rate"])
        elif reg:
            tok["issuer"] = reg.get("issuer")
            if reg.get("note"):
                tok["note"] = reg["note"]
            for c in reg.get("components", []):
                to = c["to"].lower() if c["to"].startswith("0x") else c["to"]
                if to.startswith("base:"):
                    lin.add_token(to, BASES.get(to, to[5:]), "base")
                elif to not in lin.tokens:
                    creg = registry.get(to)
                    sym = (creg or {}).get("symbol") or to[:10]
                    lin.add_token(to, sym, token_type(sym, creg))
                lin.add_edge(tid, to, c.get("weight"), f"registry: {reg.get('source_url')}", reg.get("confidence", "low"),
                             c.get("note") or "", as_of=reg.get("as_of"), source_url=reg.get("source_url"))
        hint = hints.get(tid)
        if hint and hint["address"] != tid and not any(e["weight"] for e in lin.children(tid)):
            if hint["address"] not in lin.tokens:
                hreg = registry.get(hint["address"])
                lin.add_token(hint["address"], hint["symbol"], token_type(hint["symbol"], hreg), price_usd=hint.get("price_usd"))
            lin.add_edge(tid, hint["address"], None, "Pendle API accountingAsset", "low",
                         f"{tok['symbol']} is valued/redeemed in {hint['symbol']}; how much of its backing is "
                         f"{hint['symbol']} is not published")
    for e in lin.children(tid):
        c = e["child"]
        if c in stack:
            loop = stack[stack.index(c):] + [c]
            ws = [x["weight"] for x in lin.edges if any(x["parent"] == a and x["child"] == b for a, b in zip(loop, loop[1:]))]
            g = None if None in ws or not ws else _prod(ws)
            lin.cycles.append({"path": [lin.tokens[t]["symbol"] for t in loop], "gain": g,
                               "amplification": (1 / (1 - g)) if g is not None and g < 1 else None,
                               "unstable": g is not None and g >= 1})
            e["cycle"] = True
            continue
        _expand(lin, c, stack + [c], registry, hints, depth + 1)


def _prod(xs):
    out = 1.0
    for x in xs:
        out *= x
    return out


def trace_pendle(pend: dict, registry: dict | None = None) -> Lineage:
    """pend = Pendle /v1/{chain}/markets/{address} payload (pt, sy, underlyingAsset, accountingAsset)."""
    registry = load_registry() if registry is None else registry
    pt, sy, und, acc = pend["pt"], pend["sy"], pend["underlyingAsset"], pend.get("accountingAsset") or {}
    pa, sa, ua = pt["address"].lower(), sy["address"].lower(), und["address"].lower()
    lin = Lineage(pa)
    usd = lambda t: (t.get("price") or {}).get("usd")  # noqa: E731
    lin.add_token(pa, pt["symbol"], "pendle_pt", price_usd=usd(pt), expiry=pt.get("expiry"))
    lin.add_token(sa, sy["symbol"], "pendle_sy", price_usd=usd(sy))
    lin.add_token(ua, und["symbol"], token_type(und["symbol"], registry.get(ua)), price_usd=usd(und))
    lin.add_edge(pa, sa, 1.0, "Pendle API market.sy", "high", f"{pt['symbol']} redeems for {sy['symbol']} at maturity")
    lin.add_edge(sa, ua, 1.0, "Pendle API market.underlyingAsset", "high", f"{sy['symbol']} wraps {und['symbol']}")
    hints = {}
    if acc.get("address") and acc["address"].lower() != ua:
        hints[ua] = {"address": acc["address"].lower(), "symbol": acc["symbol"], "price_usd": usd(acc)}
    _expand(lin, ua, [pa, sa, ua], registry, hints, 2)
    return lin
