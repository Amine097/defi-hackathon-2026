import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from defirisk.api_payload import build_payload


def test_payload_shape():
    p = build_payload()
    assert {"position", "nodes", "edges", "decision", "scenarios", "book"} <= p.keys()
    assert p["decision"]["verdict"] in ("STAY", "EXIT")
    assert len(p["book"]["pockets"]) == 10
