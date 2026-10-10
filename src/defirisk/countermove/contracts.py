"""ABI bindings for the contracts the Countermove keeper touches: RescueVault, Morpho Blue, Morpho oracles, Chainlink-style
feeds, IRMs and ERC20 tokens. Hand-written signatures, cross-checked against the Foundry artifact ABI in the tests."""
from __future__ import annotations

import json
from pathlib import Path

from .. import abi
from ..keccak import keccak256

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT = ROOT / "contracts" / "out" / "RescueVault.sol" / "RescueVault.json"
MORPHO_BLUE = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"

STRATEGY = {"REPAY": 1, "TOP_UP": 2, "FULL_REPAY": 4}
STRATEGY_NAME = {v: k for k, v in STRATEGY.items()}
POLICY_TYPES = "(uint8,uint64,uint32,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256)"
POLICY_FIELDS = ("allowed_strategies", "valid_until", "cooldown", "trigger_ltv", "min_ltv_after", "max_repay_per_action",
                 "max_top_up_per_action", "max_full_repay", "max_repay_total", "max_top_up_total", "min_loan_reserve",
                 "min_collateral_reserve")
SNAPSHOT_TYPES = "(uint256,uint256,uint256,uint256,uint256,uint256)"

RESCUE_EXECUTED = "RescueExecuted(bytes32,uint8,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256)"
RESCUE_EXECUTED_TOPIC = abi.event_topic(RESCUE_EXECUTED)
MORPHO_REPAY_TOPIC = abi.event_topic("Repay(bytes32,address,address,uint256,uint256)")
MORPHO_SUPPLY_COLLATERAL_TOPIC = abi.event_topic("SupplyCollateral(bytes32,address,address,uint256)")

ERRORS = {  # RescueVault custom errors + OpenZeppelin errors it can bubble up
    "ZeroAddress()": [], "MarketMismatch()": [], "NotOwner()": [], "NotKeeper()": [], "IsPaused()": [], "IsRevoked()": [],
    "InvalidPolicy(string)": ["string"], "StalePolicy(uint256,uint256)": ["uint256", "uint256"],
    "PolicyExpired(uint256)": ["uint256"], "StrategyNotAllowed(uint8)": ["uint8"],
    "ActionAlreadyExecuted(bytes32)": ["bytes32"], "CooldownActive(uint256)": ["uint256"], "NoDebt()": [],
    "NotAtRisk(uint256,uint256)": ["uint256", "uint256"], "ZeroAmount()": [],
    "ExceedsPerActionCap(uint256,uint256)": ["uint256", "uint256"], "ExceedsTotalCap(uint256,uint256)": ["uint256", "uint256"],
    "ExceedsDebt(uint256,uint256)": ["uint256", "uint256"], "ExceedsKeeperBound(uint256,uint256)": ["uint256", "uint256"],
    "ReserveFloor(uint256,uint256,uint256)": ["uint256", "uint256", "uint256"], "UnsupportedToken(address)": ["address"],
    "UnexpectedTokenMovement()": [], "UnexpectedPositionChange()": [], "NoImprovement(uint256,uint256)": ["uint256", "uint256"],
    "LtvAboveBound(uint256,uint256)": ["uint256", "uint256"], "LtvBelowFloor(uint256,uint256)": ["uint256", "uint256"],
    "ReentrancyGuardReentrantCall()": [], "SafeERC20FailedOperation(address)": ["address"],
    "Error(string)": ["string"], "Panic(uint256)": ["uint256"],
}
_BY_SELECTOR = {"0x" + keccak256(sig.encode())[:4].hex(): (sig.split("(")[0], types) for sig, types in ERRORS.items()}


def decode_revert(data: str | None) -> dict:
    """Revert data -> {'error': name, 'args': [...]} (unknown selectors are reported raw, never guessed)."""
    if not data or len(data) < 10:
        return {"error": "unknown", "args": [], "raw": data}
    name, types = _BY_SELECTOR.get(data[:10].lower(), (None, None))
    if name is None:
        return {"error": "unknown", "args": [], "raw": data}
    try:
        args = abi.decode(types, "0x" + data[10:]) if types else []
    except Exception:  # noqa: BLE001 - malformed revert payload is reported, not raised
        args = []
    return {"error": name, "args": args, "raw": data}


# ---- RescueVault --------------------------------------------------------------------------------------------------
def execute_calldata(strategy: str, action_id: str, amount: int, policy_nonce: int, bound: int) -> str:
    """REPAY / TOP_UP: bound = maxLtvAfter (WAD). FULL_REPAY: amount is ignored on-chain, bound = maxAssets."""
    if strategy == "REPAY":
        return abi.encode_call("executeRepay(bytes32,uint256,uint256,uint256)", [action_id, amount, policy_nonce, bound])
    if strategy == "TOP_UP":
        return abi.encode_call("executeTopUp(bytes32,uint256,uint256,uint256)", [action_id, amount, policy_nonce, bound])
    if strategy == "FULL_REPAY":
        return abi.encode_call("executeFullRepay(bytes32,uint256,uint256)", [action_id, bound, policy_nonce])
    raise ValueError(f"no on-chain action for strategy {strategy}")


def read_vault(rpc, vault: str, block: str | int = "latest") -> dict:
    pol = rpc.read(vault, "policy()", [], POLICY_TYPES, block)
    out = {"address": vault, "policy": dict(zip(POLICY_FIELDS, pol))}
    for name, sig, typ in (("policy_nonce", "policyNonce()", "uint256"), ("keeper", "keeper()", "address"),
                           ("paused", "paused()", "bool"), ("revoked", "revoked()", "bool"),
                           ("repaid_total", "repaidTotal()", "uint256"), ("topped_up_total", "toppedUpTotal()", "uint256"),
                           ("last_action_at", "lastActionAt()", "uint256"), ("action_count", "actionCount()", "uint256"),
                           ("owner", "OWNER()", "address"), ("beneficiary", "BENEFICIARY()", "address"),
                           ("loan_token", "LOAN_TOKEN()", "address"), ("collateral_token", "COLLATERAL_TOKEN()", "address"),
                           ("oracle", "ORACLE()", "address"), ("irm", "IRM()", "address"), ("lltv", "LLTV()", "uint256"),
                           ("market_id", "MARKET_ID()", "bytes32"), ("morpho", "MORPHO()", "address")):
        out[name] = rpc.read(vault, sig, [], typ, block)
    out["loan_reserve"] = erc20_balance(rpc, out["loan_token"], vault, block)
    out["collateral_reserve"] = erc20_balance(rpc, out["collateral_token"], vault, block)
    return out


def action_used(rpc, vault: str, action_id: str, block: str | int = "latest") -> bool:
    return rpc.read(vault, "actionUsed(bytes32)", [action_id], "bool", block)


def decode_rescue_event(log: dict) -> dict:
    vals = abi.decode("uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256", log["data"])
    keys = ("assets", "debt_before", "debt_after", "collateral_before", "collateral_after", "ltv_before", "ltv_after",
            "policy_nonce")
    return {"action_id": log["topics"][1], "strategy": STRATEGY_NAME.get(int(log["topics"][2], 16), "UNKNOWN"),
            **dict(zip(keys, vals)), "tx_hash": log.get("transactionHash"), "block": int(log["blockNumber"], 16)}


def artifact() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


# ---- Morpho Blue -----------------------------------------------------------------------------------------------------
def market_params(rpc, morpho: str, market_id: str, block: str | int = "latest") -> dict:
    loan, coll, oracle, irm, lltv = rpc.read(morpho, "idToMarketParams(bytes32)", [market_id],
                                             "address,address,address,address,uint256", block)
    return {"loan_token": loan, "collateral_token": coll, "oracle": oracle, "irm": irm, "lltv_raw": lltv}


def market_state(rpc, morpho: str, market_id: str, block: str | int = "latest") -> dict:
    v = rpc.read(morpho, "market(bytes32)", [market_id], "uint128,uint128,uint128,uint128,uint128,uint128", block)
    return dict(zip(("total_supply_assets", "total_supply_shares", "total_borrow_assets", "total_borrow_shares",
                     "last_update", "fee"), v))


def position(rpc, morpho: str, market_id: str, user: str, block: str | int = "latest") -> dict:
    s, b, c = rpc.read(morpho, "position(bytes32,address)", [market_id, user], "uint256,uint128,uint128", block)
    return {"supply_shares": s, "borrow_shares": b, "collateral": c}


def borrow_rate(rpc, params: dict, state: dict, block: str | int = "latest") -> int | None:
    """IRM borrowRateView(MarketParams, Market) at the market's last update (per-second WAD); None if unreadable."""
    if int(params["irm"], 16) == 0:
        return 0
    try:
        return rpc.read(params["irm"], "borrowRateView((address,address,address,address,uint256),"
                                       "(uint128,uint128,uint128,uint128,uint128,uint128))",
                        [abi.market_params_tuple(params),
                         [state[k] for k in ("total_supply_assets", "total_supply_shares", "total_borrow_assets",
                                             "total_borrow_shares", "last_update", "fee")]], "uint256", block)
    except Exception:  # noqa: BLE001 - a broken IRM is reported as unknown interest, never as zero risk
        return None


def oracle_price(rpc, oracle: str, block: str | int = "latest") -> int:
    return rpc.read(oracle, "price()", [], "uint256", block)


# ---- ERC20 ---------------------------------------------------------------------------------------------------------
def erc20_balance(rpc, token: str, holder: str, block: str | int = "latest") -> int:
    return rpc.read(token, "balanceOf(address)", [holder], "uint256", block)


def erc20_meta(rpc, token: str) -> dict:
    try:
        sym = rpc.read(token, "symbol()", [], "string")
    except Exception:  # noqa: BLE001 - some tokens return bytes32 symbols
        sym = token[:8]
    return {"address": token, "symbol": sym, "decimals": rpc.read(token, "decimals()", [], "uint8")}
