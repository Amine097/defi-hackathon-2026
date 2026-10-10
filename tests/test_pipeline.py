import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from defirisk.cli import run


def test_pipeline_runs():
    g, sim, d = run()
    assert d.verdict in ("STAY", "EXIT")
    assert 0 <= sim.expected_loss_usd <= g.position.value_usd
