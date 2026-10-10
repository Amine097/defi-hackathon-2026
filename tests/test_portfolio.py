import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from defirisk.cli import run  # type: ignore[import-not-found]  # noqa: E402
from defirisk.portfolio import Pocket, evaluate_book  # type: ignore[import-not-found]  # noqa: E402
from defirisk.scenarios import SCENARIOS  # type: ignore[import-not-found]  # noqa: E402


def test_book_one_pocket_hit():
    g, _, _ = run()
    pockets = [Pocket(f"P{i}", 0.1, deepcopy(g)) for i in range(10)]
    r = evaluate_book(pockets, 10_000_000, SCENARIOS[0], affected={"P0"})
    assert sum(x.affected for x in r.pockets) == 1
    assert r.total_optimal_usd <= r.total_stay_loss_usd
    assert 0 <= r.pct_of_book <= 1
