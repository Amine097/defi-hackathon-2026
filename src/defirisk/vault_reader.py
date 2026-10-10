"""On-chain discovery of a Morpho vault from its address (P1-01 / P1-02 / P1-05 reads).

Every number used by the decision is read with eth_call at ONE pinned block; the Morpho API (indexer) is only used
for labels, the borrower list and as an independent cross-check (lag / disagreement is reported, never hidden).

Type detection never trusts a label: an address is a supported vault only if the official Morpho factory says so
on-chain (VaultV2Factory.isVaultV2 / MetaMorphoFactory.isMetaMorpho).

V2 semantics (docs.morpho.org, assets-flow / force-deallocate): maxWithdraw / maxRedeem return 0 by design; an
ordinary withdrawal is served by idle assets, then by the liquidity adapter (market encoded in liquidityData), capped
by that market's free liquidity. Assets in other markets need a reallocation or forceDeallocate (penalty): a separate,
nonstandard branch.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from . import morpho
from .data import http, sources
from .keccak import keccak256, selector
from .vault_input import VaultError

FACTORY_V2 = {"0xA1D94F746dEfa1928926b84fB2596c06926C0405": "Morpho VaultV2Factory"}
FACTORY_V1 = {"0xA9c3D3a366466Fa809d1Ae982Fb2c46E5fC41101": "MetaMorpho Factory v1.0",
              "0x1897A8997241C1cD4bD0698647e4EB7213535c24": "MetaMorpho Factory v1.1"}
SHARE_BALANCE_SLOTS = {"v2": (12,), "v1": tuple(range(0, 16))}  # verified at run time via balanceOf under override
EUR_USD_FEED = "0xb49f677943BC038e9857d61E7d053CaA2C1734C1"  # Chainlink EUR / USD (8 decimals)
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
WITHDRAWAL_OPTIONS = "https://api.morpho.org/v0/vaults-v2/{chain}:{address}/withdrawal-options"
KYBER = "https://aggregator-api.kyberswap.com/ethereum/api/v1/routes"
USD_LIKE = {"USDC", "USDT", "DAI", "USDS", "PYUSD", "USD0", "USDE", "FRAX", "LUSD", "GHO", "RLUSD", "USDTB", "CRVUSD"}
RECON_TOL = 0.005  # 0.5%: interest accrued between components, rounding, V2 maxRate smoothing
MAX_MARKETS = 40
MAX_BORROWERS = 50
SECONDS_PER_YEAR = 365 * 86400
_SLOT_CACHE: dict = {}


class SourceDown(VaultError):
    def __init__(self, what: str):
        super().__init__("source_unavailable", 503, f"critical source unavailable: {what}")


# ---- low-level reads ----------------------------------------------------------------------------------------
def _pad(a: str) -> str:
    return a[2:].lower().rjust(64, "0")


def _call(to: str, sig: str, args: str, block: int) -> list[int] | None:
    """eth_call -> words. None = the call reverted / returned nothing (a real answer). Raises SourceDown when no
    RPC answered at all (so an outage is never mistaken for 'function absent')."""
    tag = hex(block)
    body = {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
            "params": [{"to": to, "data": selector(sig) + args}, tag]}
    r = sources._rpc_call(body, revert_ok=True)
    if r is None:
        raise SourceDown("Ethereum JSON-RPC (eth_call)")
    res = r.get("result")
    return sources._words(res) if res and res != "0x" else None


def _one(to: str, sig: str, block: int, args: str = "") -> int:
    w = _call(to, sig, args, block)
    if not w:
        raise VaultError("read_failed", 422, f"{sig} reverted on {to}: not readable as a supported vault")
    return w[0]


def _addr(word: int) -> str:
    return morpho._addr(word)


def _string(to: str, sig: str, block: int) -> str | None:
    tag = hex(block)
    r = sources._rpc_call({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                           "params": [{"to": to, "data": selector(sig)}, tag]}, revert_ok=True)
    res = (r or {}).get("result")
    if not res or res == "0x":
        return None
    b = bytes.fromhex(res[2:])
    try:
        if len(b) >= 64 and int.from_bytes(b[:32], "big") == 32:
            n = int.from_bytes(b[32:64], "big")
            return b[64:64 + n].decode("utf-8", "ignore")
        return b[:32].rstrip(b"\0").decode("utf-8", "ignore")
    except Exception:
        return None


def market_id(loan: str, coll: str, oracle: str, irm: str, lltv: int) -> str:
    raw = b"".join(int(x, 16).to_bytes(32, "big") for x in (loan, coll, oracle, irm)) + lltv.to_bytes(32, "big")
    return "0x" + keccak256(raw).hex()


# ---- P1-01: contract type ------------------------------------------------------------------------------------
def detect(address: str, block: int) -> dict:
    code = sources._rpc("eth_getCode", [address, hex(block)])
    if code is None:
        raise SourceDown("Ethereum JSON-RPC (eth_getCode)")
    if code in ("0x", "0x0", ""):
        raise VaultError("not_found", 404, "no contract at this address on Ethereum mainnet (EOA or not deployed)",
                         {"as_of_block": block})
    for f, name in FACTORY_V2.items():
        if (_call(f, "isVaultV2(address)", _pad(address), block) or [0])[0] == 1:
            return {"version": "v2", "factory": f, "factory_name": name, "code_bytes": (len(code) - 2) // 2}
    for f, name in FACTORY_V1.items():
        if (_call(f, "isMetaMorpho(address)", _pad(address), block) or [0])[0] == 1:
            return {"version": "v1", "factory": f, "factory_name": name, "code_bytes": (len(code) - 2) // 2}
    raise VaultError("unsupported_contract", 422,
                     "contract is not a Morpho vault: not registered by the Morpho VaultV2 or MetaMorpho factories",
                     {"as_of_block": block, "checked_factories": list(FACTORY_V2) + list(FACTORY_V1)})


# ---- markets -------------------------------------------------------------------------------------------------
def read_market(mid: str, holder: str, block: int, ts: int) -> dict:
    """Morpho Blue market at the block, interest accrued to the block timestamp, plus `holder`'s supply."""
    import math
    mk = morpho.read_market(mid, block)
    p, st0 = mk["params"], mk["state"]
    if int(p["loan_token"], 16) == 0:
        raise VaultError("read_failed", 422, f"market {mid} does not exist on Morpho Blue")
    rate = morpho.borrow_rate_view(p, st0, block)
    st = morpho.accrue(st0, rate, ts)
    pos = morpho.read_position(mid, holder, block)
    supply = morpho.to_assets_down(pos["supply_shares"], st["total_supply_assets"], st["total_supply_shares"])
    has_coll = int(p["collateral_token"], 16) != 0
    price = None
    if has_coll and int(p["oracle"], 16) != 0:
        w = _call(p["oracle"], "price()", "", block)
        price = w[0] if w else None
    util = st["total_borrow_assets"] / st["total_supply_assets"] if st["total_supply_assets"] else 0.0
    borrow_apy = math.expm1((rate or 0) / morpho.WAD * SECONDS_PER_YEAR)
    return {
        "id": mid, "loan_token": p["loan_token"], "collateral_token": p["collateral_token"] if has_coll else None,
        "oracle": p["oracle"], "irm": p["irm"], "lltv": p["lltv"] / morpho.WAD, "lltv_raw": p["lltv"],
        "loan_decimals": _one(p["loan_token"], "decimals()", block),
        "collateral_decimals": _one(p["collateral_token"], "decimals()", block) if has_coll else None,
        "collateral_symbol": _string(p["collateral_token"], "symbol()", block) if has_coll else None,
        "total_supply_raw": st["total_supply_assets"], "total_supply_shares": st["total_supply_shares"],
        "total_borrow_raw": st["total_borrow_assets"], "total_borrow_shares": st["total_borrow_shares"],
        "liquidity_raw": max(st["total_supply_assets"] - st["total_borrow_assets"], 0),
        "vault_supply_shares": pos["supply_shares"], "vault_supply_raw": supply,
        "oracle_price_raw": price, "borrow_rate_per_s": rate, "borrow_apy": borrow_apy, "utilization": util,
        "fee": st["fee"] / morpho.WAD, "supply_apy": borrow_apy * util * (1 - st["fee"] / morpho.WAD),
        "interest_accrued_seconds": st["accrued_seconds"], "lif": morpho.liquidation_incentive_factor(p["lltv"]) / morpho.WAD,
        "source": f"Morpho Blue {morpho.MORPHO_BLUE} idToMarketParams/market/position + IRM borrowRateView @ block {block}",
    }


def borrowers(m: dict, block: int) -> dict:
    """Borrowers of a market (Morpho API list, largest first) valued with the ON-CHAIN totals and oracle price of
    the pinned block. Debt not covered by the list is reported (the model assumes it sits at the LLTV: worst case)."""
    from .data.http import post_json
    out = {"items": [], "covered_borrow_raw": 0, "status": "ok", "source": "Morpho API marketPositions + on-chain totals/oracle"}
    if m["total_borrow_raw"] == 0 or not m["collateral_token"]:
        return out
    q = """query($m:[String!],$f:Int){ marketPositions(first:$f, orderBy:BorrowShares, orderDirection:Desc,
      where:{marketUniqueKey_in:$m, chainId_in:[1]}){ items{ user{address} state{ borrowShares collateral } } } }"""
    try:
        r = post_json(sources.MORPHO, {"query": q, "variables": {"m": [m["id"]], "f": MAX_BORROWERS}}, timeout=30)
        if r.get("errors"):
            raise RuntimeError(r["errors"][0]["message"])
        items = r["data"]["marketPositions"]["items"]
    except Exception as e:
        out.update(status="unavailable", error=f"{type(e).__name__}: {e}"[:200])
        return out
    price = m["oracle_price_raw"]
    for i in items:
        sh = int(i["state"]["borrowShares"] or 0)
        if sh <= 0:
            continue
        debt = morpho.to_assets_up(sh, m["total_borrow_raw"], m["total_borrow_shares"])
        coll = int(i["state"]["collateral"] or 0)
        coll_value = morpho.mul_div_down(coll, price, morpho.ORACLE_PRICE_SCALE) if price else None
        out["items"].append({"address": i["user"]["address"], "borrow_shares": sh, "debt_raw": debt, "collateral_raw": coll,
                             "collateral_value_raw": coll_value,
                             "ltv": (debt / coll_value) if coll_value else None})
        out["covered_borrow_raw"] += debt
    out["coverage"] = min(out["covered_borrow_raw"] / m["total_borrow_raw"], 1.0)
    return out


# ---- vault reads ---------------------------------------------------------------------------------------------
def _v2_adapter(vault: str, ad: str, block: int) -> dict:
    real = _call(ad, "realAssets()", "", block)
    info = {"address": ad, "real_assets_raw": real[0] if real else None, "market_ids": [], "type": "unknown",
            "supported": False}
    pen = _call(vault, "forceDeallocatePenalty(address)", _pad(ad), block)
    info["force_deallocate_penalty"] = pen[0] / morpho.WAD if pen else None
    n = _call(ad, "marketIdsLength()", "", block)
    if n is not None:
        info["type"] = "MorphoMarketV1AdapterV2"
        info["market_ids"] = ["0x" + f"{_one(ad, 'marketIds(uint256)', block, f'{i:064x}'):064x}" for i in range(min(n[0], MAX_MARKETS))]
        info["supported"] = n[0] <= MAX_MARKETS
        return info
    n = _call(ad, "marketParamsListLength()", "", block)
    if n is not None:
        info["type"] = "MorphoMarketV1Adapter"
        for i in range(min(n[0], MAX_MARKETS)):
            w = _call(ad, "marketParamsList(uint256)", f"{i:064x}", block)
            if not w:
                return info
            info["market_ids"].append(market_id(_addr(w[0]), _addr(w[1]), _addr(w[2]), _addr(w[3]), w[4]))
        info["supported"] = n[0] <= MAX_MARKETS
        return info
    w = _call(ad, "morphoVaultV1()", "", block)
    if w:
        info.update(type="MorphoVaultV1Adapter", inner_vault=_addr(w[0]))
        info["supported"] = True
    return info


def _decode_liquidity_market(raw_words: list[int] | None) -> str | None:
    """liquidityData() = abi bytes; for a Morpho market adapter it is abi.encode(MarketParams) (5 words)."""
    if not raw_words or len(raw_words) < 7 or raw_words[1] != 160:
        return None
    loan, coll, oracle, irm, lltv = raw_words[2:7]
    return market_id(_addr(loan), _addr(coll), _addr(oracle), _addr(irm), lltv)


def _read_markets(ids_by_holder: list[tuple[str, str]], block: int, ts: int) -> list[dict]:
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(lambda x: dict(read_market(x[0], x[1], block, ts), holder=x[1]), ids_by_holder))


def read_v1(address: str, block: int, ts: int, scale: float = 1.0, via: str | None = None) -> dict:
    """MetaMorpho (V1): withdraw queue markets and the vault's supply in each (scaled when nested in a V2 adapter)."""
    n = _one(address, "withdrawQueueLength()", block)
    ids = ["0x" + f"{_one(address, 'withdrawQueue(uint256)', block, f'{i:064x}'):064x}" for i in range(min(n, MAX_MARKETS))]
    mkts = _read_markets([(i, address) for i in ids], block, ts)
    for q, m in enumerate(mkts):
        m["withdraw_queue_index"] = q
        m["vault_supply_raw_unscaled"] = m["vault_supply_raw"]
        m["vault_supply_raw"] = int(m["vault_supply_raw"] * scale)
        m["via"] = via or address
    return {"market_ids": ids, "markets": mkts, "queue_complete": n <= MAX_MARKETS}


def read_vault(address: str, version: str, block: int, ts: int) -> dict:
    asset = _addr(_one(address, "asset()", block))
    snap = {"address": address, "version": version, "asset_address": asset,
            "name": _string(address, "name()", block), "symbol": _string(address, "symbol()", block),
            "decimals": _one(address, "decimals()", block),
            "asset_decimals": _one(asset, "decimals()", block), "asset_symbol": _string(asset, "symbol()", block),
            "total_assets_raw": _one(address, "totalAssets()", block),
            "total_supply_raw": _one(address, "totalSupply()", block)}
    snap["share_price_raw"] = _one(address, "convertToAssets(uint256)", block, f"{10 ** snap['decimals']:064x}")
    snap["idle_raw"] = _one(asset, "balanceOf(address)", block, _pad(address))
    snap["adapters"], snap["markets"], warnings = [], [], []
    if version == "v2":
        perf = _call(address, "performanceFee()", "", block)
        mgmt = _call(address, "managementFee()", "", block)
        snap["fees"] = {"performance": perf[0] / morpho.WAD if perf else None,
                        "management_annual": mgmt[0] / morpho.WAD * SECONDS_PER_YEAR if mgmt else None,
                        "source": "VaultV2 performanceFee() / managementFee() (per second, annualised)"}
        gates = {k: _addr((_call(address, f"{k}()", "", block) or [0])[0])
                 for k in ("sendSharesGate", "receiveAssetsGate", "receiveSharesGate", "sendAssetsGate")}
        snap["gates"] = {**gates, "withdraw_open": int(gates["sendSharesGate"], 16) == 0 and int(gates["receiveAssetsGate"], 16) == 0}
        la = _call(address, "liquidityAdapter()", "", block)
        snap["liquidity_adapter"] = _addr(la[0]) if la and la[0] else None
        snap["liquidity_market"] = _decode_liquidity_market(_call(address, "liquidityData()", "", block))
        n = _one(address, "adaptersLength()", block)
        jobs = []
        for i in range(n):
            ad = _addr(_one(address, "adapters(uint256)", block, f"{i:064x}"))
            info = _v2_adapter(address, ad, block)
            snap["adapters"].append(info)
            if info["type"].startswith("MorphoMarketV1Adapter"):
                jobs += [(mid, ad) for mid in info["market_ids"]]
            elif info["type"] == "MorphoVaultV1Adapter":
                inner = info["inner_vault"]
                sh = _one(inner, "balanceOf(address)", block, _pad(ad))
                held = _one(inner, "convertToAssets(uint256)", block, f"{sh:064x}")
                tot = _one(inner, "totalAssets()", block)
                v1 = read_v1(inner, block, ts, held / tot if tot else 0.0, via=ad)
                info["market_ids"] = v1["market_ids"]
                info["inner_assets_raw"] = held
                for m in v1["markets"]:
                    m["holder"] = ad
                snap["markets"] += v1["markets"]
            else:
                warnings.append(f"adapter {ad} of unknown type: its {info['real_assets_raw']} raw assets are unattributed")
        snap["markets"] += _read_markets(jobs, block, ts)
    else:
        fee = _call(address, "fee()", "", block)
        snap["fees"] = {"performance": fee[0] / morpho.WAD if fee else None, "management_annual": 0.0,
                        "source": "MetaMorpho fee() (performance fee on interest)"}
        snap["gates"] = {"withdraw_open": True, "note": "MetaMorpho V1 has no withdrawal gates"}
        snap["liquidity_adapter"] = snap["liquidity_market"] = None
        v1 = read_v1(address, block, ts)
        snap["adapters"].append({"address": address, "type": "MetaMorpho withdrawQueue", "supported": v1["queue_complete"],
                                 "market_ids": v1["market_ids"], "real_assets_raw": sum(m["vault_supply_raw"] for m in v1["markets"]),
                                 "force_deallocate_penalty": None})
        snap["markets"] = v1["markets"]
    snap["warnings"] = warnings
    return snap


def reconcile(snap: dict) -> dict:
    """sum(identified market supply) + idle + unattributed == totalAssets, per adapter and for the vault."""
    rows = []
    attributed = 0
    for ad in snap["adapters"]:
        in_mk = sum(m["vault_supply_raw"] for m in snap["markets"] if m.get("holder") == ad["address"]
                    or (snap["version"] == "v1"))
        real = ad.get("real_assets_raw")
        if ad.get("type") == "MorphoVaultV1Adapter":
            real = ad.get("inner_assets_raw", real)
        gap = (real - in_mk) if (real is not None and ad.get("supported")) else None
        rows.append({"adapter": ad["address"], "type": ad.get("type"), "reported_raw": real, "markets_raw": in_mk,
                     "gap_raw": gap, "gap_pct": (gap / real) if gap is not None and real else None})
        attributed += in_mk if ad.get("supported") else 0
    known = attributed + snap["idle_raw"]
    total = snap["total_assets_raw"]
    unattributed = max(total - known, 0)
    gap_pct = (known - total) / total if total else 0.0
    return {"adapters": rows, "markets_raw": attributed, "idle_raw": snap["idle_raw"], "total_assets_raw": total,
            "unattributed_raw": unattributed, "unattributed_pct": unattributed / total if total else 0.0,
            "gap_pct": gap_pct, "tolerance": RECON_TOL, "within_tolerance": abs(gap_pct) <= RECON_TOL,
            "coverage": min(known / total, 1.0) if total else 0.0,
            "rule": "coverage = (idle + supply resolved in Morpho markets) / totalAssets; any shortfall is kept as an "
                    "'unattributed' exposure with a conservative failure model (never zero risk)"}


# ---- prices --------------------------------------------------------------------------------------------------
def currency_of(symbol: str | None) -> str:
    s = (symbol or "").upper()
    if "EUR" in s:
        return "EUR"
    return "USD" if s in USD_LIKE or s.startswith("USD") else "OTHER"


def asset_price(asset: str, symbol: str | None, block: int) -> dict:
    key = f"ethereum:{asset.lower()}"
    out = {"currency": currency_of(symbol), "price_usd": None}
    try:
        px = sources.llama_prices([key]).get(key) or {}
    except Exception as e:
        px = {}
        out["error"] = f"DefiLlama: {type(e).__name__}"
    if px.get("price"):
        out.update(price_usd=px["price"], timestamp=px.get("timestamp"), confidence=px.get("confidence"),
                   source=f"DefiLlama coins current {key}", age_s=max(http.now() - (px.get("timestamp") or 0), 0))
    if out["currency"] == "EUR":
        w = _call(EUR_USD_FEED, "latestRoundData()", "", block)
        if w:
            fx = w[1] / 1e8
            out["fx"] = {"pair": "EUR/USD", "rate": fx, "updated_at": w[3], "source": f"Chainlink {EUR_USD_FEED} @ block {block}"}
            if out["price_usd"]:
                out["peg_vs_eur"] = out["price_usd"] / fx
                out["decomposition"] = (f"USD price {out['price_usd']:.5f} = EUR/USD {fx:.5f} (FX) x token/EUR "
                                        f"{out['peg_vs_eur']:.5f} (peg): FX moves and token depeg are separate risks")
    return out


# ---- cross-checks (indexer) ----------------------------------------------------------------------------------
def api_vault(address: str, version: str) -> dict:
    from .data.http import post_json
    if version == "v2":
        q = """query($a:String!){ vaultV2ByAddress(address:$a, chainId:1){ address name symbol totalAssets idleAssets
          liquidity netApy netApyExcludingRewards avgNetApy performanceFee managementFee rewards{asset{symbol} supplyApr}
          asset{address symbol decimals price{usd}} } }"""
        key = "vaultV2ByAddress"
    else:
        q = """query($a:String!){ vaultByAddress(address:$a, chainId:1){ address name symbol
          asset{address symbol decimals price{usd}} state{ totalAssets netApy netApyExcludingRewards fee } } }"""
        key = "vaultByAddress"
    try:
        r = post_json(sources.MORPHO, {"query": q, "variables": {"a": address}}, timeout=20)
        if r.get("errors"):
            return {"status": "error", "error": r["errors"][0].get("message", "")[:200], "fetched_at": http.LAST["fetched_at"]}
        d = r["data"][key]
        if version == "v1":
            d = {**d, "totalAssets": d["state"]["totalAssets"], "netApy": d["state"]["netApy"],
                 "netApyExcludingRewards": d["state"]["netApyExcludingRewards"]}
        return {"status": "ok", "data": d, "fetched_at": http.LAST["fetched_at"], "cached": http.LAST["cached"],
                "source": f"Morpho GraphQL {key}"}
    except Exception as e:
        return {"status": "unavailable", "error": f"{type(e).__name__}: {e}"[:200]}


def api_withdrawal_options(address: str) -> dict:
    from .data.http import get_json
    try:
        d = get_json(WITHDRAWAL_OPTIONS.format(chain=1, address=address), timeout=15)["data"]
        return {"status": "ok", "idle_raw": int(d["idle_assets"]),
                "liquidity_adapter_available_raw": int(d["liquidity_adapter_available_assets"]),
                "adapters": [{"address": a["adapter_address"], "force_deallocatable_raw": int(a["force_deallocatable_assets"]),
                              "penalty": int(a["penalty_rate_wad"]) / morpho.WAD} for a in d.get("adapter_penalties", [])],
                "source": "Morpho REST v0 vaults-v2 withdrawal-options", "fetched_at": http.LAST["fetched_at"]}
    except Exception as e:
        return {"status": "unavailable", "error": f"{type(e).__name__}: {e}"[:200]}


def conversion_quote(asset: str, amount_raw: int, price_usd: float, decimals: int) -> dict:
    """Indicative quote to convert the withdrawn asset into USDC (KyberSwap public route, NOT executed/simulated)."""
    from .data.http import get_json
    try:
        r = get_json(KYBER, {"tokenIn": asset, "tokenOut": USDC, "amountIn": str(amount_raw)}, timeout=15)
        s = r["data"]["routeSummary"]
        out_usd = float(s["amountOutUsd"])
        in_usd = amount_raw / 10 ** decimals * price_usd
        return {"status": "indicative", "amount_in_raw": amount_raw, "usdc_out_raw": int(s["amountOut"]),
                "usdc_out": int(s["amountOut"]) / 1e6, "value_in_usd": in_usd, "proceeds_usd": out_usd,
                "cost_usd": max(in_usd - out_usd, 0.0) + float(s.get("gasUsd") or 0), "gas_usd": float(s.get("gasUsd") or 0),
                "source": "KyberSwap aggregator route (public API, indicative: not simulated on-chain)",
                "fetched_at": http.LAST["fetched_at"]}
    except Exception as e:
        return {"status": "unquantified", "error": f"{type(e).__name__}: {e}"[:200]}


# ---- P1-05: read-only withdrawal simulation -----------------------------------------------------------------
def _with_shares(vault: str, slot: int, shares: int) -> dict:
    s = "0x" + keccak256(sources._w(sources.DEAD) + sources._w(slot)).hex()
    return {vault: {"stateDiff": {s: "0x" + sources._w(shares).hex()}}}


def _share_slot(vault: str, version: str, block: int) -> int | None:
    if (vault, version) in _SLOT_CACHE:
        return _SLOT_CACHE[(vault, version)]
    probe = 10 ** 20 + 12345
    for slot in SHARE_BALANCE_SLOTS[version]:
        r = sources._override_rpc("eth_call", [{"to": vault, "data": selector("balanceOf(address)") + _pad(sources.DEAD)},
                                               hex(block), _with_shares(vault, slot, probe)])
        if r is None:
            return None
        if r.get("result") and r["result"] != "0x" and int(r["result"], 16) == probe:
            _SLOT_CACHE[(vault, version)] = slot
            return slot
    return None


def simulate_redeem(vault: str, version: str, shares: int, block: int) -> dict:
    """eth_call redeem(shares, 0xdEaD, 0xdEaD) from 0xdEaD, whose share balance is set by a state override, at the
    pinned block. No transaction is sent. Also reads maxRedeem(0xdEaD) under the same state (V2: 0 by design)."""
    slot = _share_slot(vault, version, block)
    if slot is None:
        return {"status": "unavailable", "reason": "no RPC accepted state overrides or share balance slot not verified"}
    ov = _with_shares(vault, slot, shares)
    data = selector("redeem(uint256,address,address)") + f"{shares:064x}" + _pad(sources.DEAD) * 2
    call = {"from": sources.DEAD, "to": vault, "data": data}
    r = sources._override_rpc("eth_call", [dict(call, gas=hex(15_000_000)), hex(block), ov])
    mr = sources._override_rpc("eth_call", [{"to": vault, "data": selector("maxRedeem(address)") + _pad(sources.DEAD)},
                                            hex(block), ov])
    max_redeem = int(mr["result"], 16) if mr and mr.get("result") and mr["result"] != "0x" else None
    if not r:
        return {"status": "unavailable", "reason": "RPC did not answer the simulation"}
    if not r.get("result") or r["result"] == "0x":
        return {"status": "reverted", "reason": str(r.get("error"))[:200], "shares": shares, "block": block,
                "max_redeem_contract": max_redeem, "share_balance_slot": slot, "fetched_at": http.now()}
    g = sources._override_rpc("eth_estimateGas", [call, hex(block), ov])
    return {"status": "simulated", "shares": shares, "assets_out_raw": int(r["result"][:66], 16), "block": block,
            "gas_estimate": int(g["result"], 16) if g and g.get("result") else None, "max_redeem_contract": max_redeem,
            "share_balance_slot": slot, "fetched_at": http.now(),
            "method": "eth_call redeem() with a state override on the share balance of 0xdEaD (read-only, no tx)"}


# ---- entry point -----------------------------------------------------------------------------------------------
def max_withdraw_v1(vault: str, total_supply: int, block: int) -> dict:
    """MetaMorpho V1 only: maxWithdraw(0xdEaD) with 0xdEaD holding EVERY share (state override) = the contract's own
    withdrawQueue liquidity walk. Independent check of the capacity computed from market reads. Read-only."""
    slot = _share_slot(vault, "v1", block)
    if slot is None:
        return {"status": "unavailable"}
    r = sources._override_rpc("eth_call", [{"to": vault, "data": selector("maxWithdraw(address)") + _pad(sources.DEAD)},
                                           hex(block), _with_shares(vault, slot, total_supply)])
    if not r or not r.get("result") or r["result"] == "0x":
        return {"status": "unavailable"}
    return {"status": "ok", "max_withdraw_raw": int(r["result"], 16), "block": block,
            "method": "eth_call maxWithdraw(0xdEaD) with balanceOf(0xdEaD) = totalSupply (state override)"}


def snapshot(address: str) -> dict:
    """Full read of a vault at one pinned block. Raises VaultError (404 / 422 / 503)."""
    blk = sources.eth_block("latest")
    if not blk:
        raise SourceDown("Ethereum JSON-RPC (eth_getBlockByNumber)")
    block, ts = blk["number"], blk["timestamp"]
    kind = detect(address, block)
    try:
        snap = read_vault(address, kind["version"], block, ts)
    except RuntimeError as e:
        if "eth_call" in str(e):
            raise SourceDown("Ethereum JSON-RPC (market reads)") from e
        raise
    snap.update(kind, as_of_block=block, block_timestamp=ts, observed_at=http.now(), chain_id=1)
    with ThreadPoolExecutor(max_workers=6) as pool:
        bfut = {m["id"] + m.get("holder", ""): pool.submit(borrowers, m, block) for m in snap["markets"]}
        api_f = pool.submit(api_vault, address, kind["version"])
        wo_f = pool.submit(api_withdrawal_options, address) if kind["version"] == "v2" else None
        px_f = pool.submit(asset_price, snap["asset_address"], snap["asset_symbol"], block)
        for m in snap["markets"]:
            m["borrowers"] = bfut[m["id"] + m.get("holder", "")].result()
        snap["api"] = api_f.result()
        snap["withdrawal_options_api"] = wo_f.result() if wo_f else {"status": "not_applicable"}
        snap["asset_price"] = px_f.result()
    snap["reconciliation"] = reconcile(snap)
    return snap
