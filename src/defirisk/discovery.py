"""Dependency discovery (owner: A). Output must follow models.DepGraph."""
from pathlib import Path

from .models import DepGraph

MOCK = Path(__file__).resolve().parents[2] / "data" / "mock_graph.json"


def discover(position_ref: str, use_mock: bool = True) -> DepGraph:
    """position_ref: e.g. 'pendle:1:<market address>'.

    TODO real discovery:
      1. Pendle API  -> market, SY, PT/YT, underlying (e.g. sUSDe)
      2. Underlying  -> yield source (Ethena), custody/CEX hedge risk
      3. Oracle      -> Pendle PT oracle / Chainlink feed used by lending market
      4. Lending     -> Morpho/Aave market using PT as collateral (LLTV, TVL)
      5. Chain       -> settlement chain node
    Fill p_fail / loss_given_failure from audits, incidents, DefiLlama, history.
    """
    if use_mock:
        return DepGraph.load(str(MOCK))
    raise NotImplementedError("real discovery not implemented yet")
