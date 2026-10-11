"""Durable evidence store (countermove/evidence.py): append-only, hash-chained, idempotent, labelled, concurrent-safe."""
import hashlib
import sqlite3
import threading

import pytest

from defirisk.countermove import api as cm
from defirisk.countermove.evidence import EvidenceStore, classify, import_journal
from defirisk.countermove.journal import Journal

TX = "0x" + "ab" * 32


@pytest.fixture()
def store(tmp_path):
    s = EvidenceStore(tmp_path / "ev.sqlite")
    yield s
    s.close()


def test_append_query_and_chain(store):
    a = store.append("observation", environment="local-test", payload={"x": 1}, position="P", idem="a")
    b = store.append("trigger", environment="local-test", payload={"x": 2}, position="P", idem="b")
    assert (a["seq"], b["seq"]) == (1, 2) and b["prev_hash"] == a["hash"]
    assert [r["kind"] for r in store.query(position="P")] == ["observation", "trigger"]
    assert store.query(since_seq=1)[0]["idem"] == "b"
    assert store.query(kinds=["trigger"])[0]["payload"] == {"x": 2}
    assert store.verify() == {"ok": True, "rows": 2, "head": b["hash"]}


def test_idempotent_and_one_receipt_per_tx(store):
    rec = {"ts": 1.0, "position": "P", "state": "CONFIRMED", "tx_hash": TX, "verification": {"verified": True}}
    first = store.record_journal(rec, environment="local-test")
    again = store.record_journal({**rec, "ts": 2.0}, environment="local-test")  # a replay with a different timestamp
    assert [r["kind"] for r in first] == ["receipt", "verification"]
    assert all(r["duplicate"] for r in again)
    assert len(store.query(kinds=["receipt"])) == 1 and store.count() == 2


def test_append_only_triggers(store):
    store.append("observation", environment="local-test", payload={}, idem="a")
    c = sqlite3.connect(store.path)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        c.execute("UPDATE events SET payload = '{}' WHERE seq = 1")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        c.execute("DELETE FROM events")
    c.close()


def test_tamper_is_detected(store):
    for i in range(3):
        store.append("observation", environment="local-test", payload={"i": i}, idem=str(i))
    store.close()
    c = sqlite3.connect(store.path)
    c.execute("DROP TRIGGER events_no_update")  # an attacker with file access
    c.execute("""UPDATE events SET payload = '{"i":99}' WHERE seq = 2""")
    c.commit()
    c.close()
    assert EvidenceStore(store.path).verify() == {"ok": False, "rows": 1, "broken_at_seq": 2}


def test_environment_labels(store):
    with pytest.raises(ValueError, match="never transacts on mainnet"):
        store.append("receipt", environment="mainnet-readonly", payload={}, tx_hash=TX)
    with pytest.raises(ValueError):
        store.append("observation", environment="mainnet", payload={})
    with pytest.raises(ValueError):
        store.append("made_up", environment="fork", payload={})
    assert store.append("observation", environment="mainnet-readonly", payload={"ltv": 0.8})["duplicate"] is False


def test_concurrent_writers_keep_a_valid_chain(store):
    errs = []

    def work(t):
        try:
            for i in range(25):
                store.append("heartbeat", environment="local-test", payload={"t": t, "i": i}, idem=f"{t}:{i}")
        except Exception as e:  # pragma: no cover - reported below
            errs.append(e)

    th = [threading.Thread(target=work, args=(t,)) for t in range(6)]
    [t.start() for t in th]
    [t.join() for t in th]
    assert not errs and store.count() == 150 and store.verify()["ok"]


def test_concurrent_processes_share_the_file(tmp_path):
    a, b = EvidenceStore(tmp_path / "e.sqlite"), EvidenceStore(tmp_path / "e.sqlite")
    for i in range(10):
        a.append("heartbeat", environment="fork", payload={"i": i}, idem=f"a{i}")
        b.append("heartbeat", environment="fork", payload={"i": i}, idem=f"b{i}")
    assert a.verify() == b.verify() and a.verify()["rows"] == 20
    a.close(), b.close()


def test_readonly_store(store, tmp_path):
    store.append("observation", environment="local-test", payload={}, idem="a")
    ro = EvidenceStore(store.path, readonly=True)
    assert ro.count() == 1 and ro.verify()["ok"]
    with pytest.raises(sqlite3.OperationalError):
        ro.append("observation", environment="local-test", payload={}, idem="b")
    ro.close()
    with pytest.raises(FileNotFoundError):
        EvidenceStore(tmp_path / "missing.sqlite", readonly=True)


def test_journal_sink_mirrors_and_never_blocks_the_journal(tmp_path, store):
    j = Journal(tmp_path / "j", sink=store.sink("local-test", 31337))
    j.append("P", "DETECTED", vault="0x" + "22" * 20)
    j.append("P", "EXECUTING", tx_hash=TX, nonce=7)
    j.append("P", "EXECUTING", tx_hash=TX, note="still pending")
    j.append("P", "CONFIRMED", tx_hash=TX, verification={"verified": True})
    kinds = [r["kind"] for r in store.query()]
    assert kinds == ["trigger", "execution_attempt", "observation", "receipt", "verification"]
    assert all(r["chain_id"] == 31337 and r["environment"] == "local-test" for r in store.query())

    def boom(_):
        raise RuntimeError("disk full")

    j2 = Journal(tmp_path / "j2", sink=boom)
    j2.append("P", "WATCHING")
    assert j2.sink_errors == 1 and len(j2.entries()) == 1


def test_classify():
    assert classify({"state": "WATCHING", "event": "rpc_error"}) == "error"
    assert classify({"state": "FAILED", "event": "reorged"}) == "finality"
    assert classify({"state": "FAILED"}) == "failure"
    assert classify({"state": "NO_ACTION"}) == "decision"
    assert classify({"state": "SOMETHING"}) == "transition"


def test_import_recorded_fork_run_is_read_only(tmp_path):
    src = cm.DEMO / "journal.jsonl"
    if not src.exists():
        pytest.skip("no recorded fork run")
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    st = EvidenceStore(tmp_path / "fork.sqlite")
    r1 = import_journal(src, st, environment="fork", chain_id=1)
    r2 = import_journal(src, st, environment="fork", chain_id=1)
    assert r1["rows_added"] > r1["records"] * 0.9 and r2["rows_added"] == 0
    receipts = st.query(kinds=["receipt"], limit=1000)
    assert len({r["tx_hash"] for r in receipts}) == len(receipts) > 0
    assert st.verify()["ok"] and all(r["environment"] == "fork" for r in st.query(limit=1000))
    st.close()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before
