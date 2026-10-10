import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from defirisk.cli import run


def test_pipeline_runs():
    g, sim, d = run()
    assert d.point_verdict in ("STAY", "EXIT")
    assert d.verdict == "REVIEW" and any("mock" in r for r in d.reasons)  # mock data never yields a firm verdict
    assert 0 <= sim.expected_loss_usd <= g.position.value_usd
