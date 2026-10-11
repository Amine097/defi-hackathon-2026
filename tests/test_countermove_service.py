"""Persistent keeper service (countermove/service.py): single instance, heartbeat, backoff, chain-head checks, finality,
and the read-only status endpoints built on them. Fake RPC + scripted watcher: no chain needed (the Anvil version is
tests/test_countermove_arm_e2e.py)."""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from defirisk.countermove import status
from defirisk.countermove.chain import RPCError
from defirisk.countermove.evidence import EvidenceStore
from defirisk.countermove.journal import Journal
from defirisk.countermove.service import KeeperService, Lease, LeaseHeld, read_health

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.countermove import respond  # noqa: E402

VAULT = "0x" + "22" * 20
TX = "0x" + "ab" * 32
CFG = {"positions": [{"id": "P", "rescue_vault": VAULT, "label": "test"}]}


class FakeRPC:
    def __init__(self, chain_id=31337):
        self.cid, self.head, self.fail, self.receipts = chain_id, 10, False, {}
        self.hashes = {}

    def chain_id(self):
        return self.cid

    def _hash(self, n):
        return self.hashes.get(n, f"0x{n:064x}")

    def block(self, tag="latest"):
        if self.fail:
            raise RPCError("connection refused")
        n = self.head if tag == "latest" else int(tag)
        return {"number": n, "timestamp": 1_700_000_000 + n, "hash": self._hash(n), "base_fee": 1}

    def receipt(self, tx):
        if self.fail:
            raise RPCError("connection refused")
        return self.receipts.get(tx)


class ScriptedWatcher:
    """Mimics Watcher.tick(): journals each scripted record and updates state like Watcher._log."""

    def __init__(self, journal):
        self.journal, self.script, self.calls = journal, [], 0

    def tick(self):
        self.calls += 1
        recs = self.script.pop(0) if self.script else [{"state": "WATCHING", "decision": "HOLD"}]
        out = []
        for r in recs:
            r = {"vault": VAULT, **r}
            rec = self.journal.append("P", r.pop("state"), **r)
            extra = {}
            if rec["state"] in ("CONFIRMED", "FAILED", "NO_ACTION"):
                extra["last_terminal"] = {"state": rec["state"], "at": rec["ts"], "reason": rec.get("reason"),
                                          "tx_hash": rec.get("tx_hash")}
            self.journal.update("P", state=rec["state"], last_event=rec, **extra)
            out.append(rec)
        return out


def svc(tmp_path, rpc=None, store=None, **kw):
    rpc = rpc or FakeRPC()
    j = Journal(tmp_path / "journal")
    w = ScriptedWatcher(j)
    kw.setdefault("sleep", lambda s: None)
    s = KeeperService(CFG, rpc, j, None, state_dir=tmp_path / "state", store=store, watcher=w, **kw)
    return s, rpc, w


def health(s):
    return json.loads(s.health_path.read_text(encoding="utf-8"))


def test_lease_is_exclusive_in_process_and_released(tmp_path):
    a, _, _ = svc(tmp_path)
    b, _, _ = svc(tmp_path)
    a.start()
    with pytest.raises(LeaseHeld, match="another keeper"):
        b.start()
    a.stop()
    assert health(a)["status"] == "stopped"
    b.start()
    assert b.lease.held
    b.stop()


def test_lease_is_exclusive_across_processes(tmp_path):
    code = ("import sys, time; sys.path.insert(0, 'src'); from defirisk.countermove.service import Lease; "
            f"L = Lease(r'{tmp_path}'); L.acquire(); print('locked', flush=True); time.sleep(30)")
    p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True,
                         cwd=str(Path(__file__).resolve().parents[1]))
    try:
        assert p.stdout.readline().strip() == "locked"
        with pytest.raises(LeaseHeld) as e:
            Lease(tmp_path).acquire()
        assert "'pid':" in str(e.value)  # the holder is identified (the venv launcher may re-spawn: pid differs)
    finally:
        p.kill()
        p.wait()
    deadline = time.time() + 5
    while True:  # the OS frees the lock when the holder dies: no stale-lease cleanup needed
        try:
            lease = Lease(tmp_path)
            lease.acquire()
            lease.release()
            break
        except LeaseHeld:
            if time.time() > deadline:
                raise
            time.sleep(0.1)


def test_refuses_non_local_chain_and_unknown_environment(tmp_path):
    s, _, _ = svc(tmp_path, rpc=FakeRPC(chain_id=1))
    with pytest.raises(ValueError, match="not a local test chain"):
        s.start()
    assert not s.lease.held
    with pytest.raises(ValueError, match="local test chains"):
        svc(tmp_path, environment="mainnet")


def test_tick_requires_the_lock(tmp_path):
    s, _, _ = svc(tmp_path)
    with pytest.raises(LeaseHeld):
        s.tick()


def test_chain_id_unknown_at_start_is_checked_before_any_decision(tmp_path):
    class LateRPC(FakeRPC):
        def chain_id(self):
            if self.fail:
                raise RPCError("connection refused")
            return self.cid

    rpc = LateRPC(chain_id=1)
    rpc.fail = True
    s, _, w = svc(tmp_path, rpc=rpc)
    s.start()  # RPC down: the chain id is unknown, start() cannot refuse yet
    assert s.chain_id is None and s.tick()["skipped"] == "rpc_unavailable"
    rpc.fail = False
    with pytest.raises(ValueError, match="not a local test chain"):
        s.tick()  # the endpoint came back as mainnet: refused before the watcher runs
    assert w.calls == 0 and not s.lease.held and health(s)["status"] == "stopped"


def test_heartbeat_and_positions(tmp_path):
    s, _, w = svc(tmp_path)
    s.start()
    r = s.tick()
    h = health(s)
    assert r["status"] == "ok" and h["status"] == "ok" and h["chain_id"] == 31337 and h["head"]["number"] == 10
    assert h["positions"][0]["vault"] == VAULT and h["positions"][0]["state"] == "WATCHING"
    assert h["watch_only"] is True and h["schema"] == "faultline.keeper.health/1"
    s.stop()


def test_rpc_outage_backs_off_and_never_decides(tmp_path):
    store = EvidenceStore(tmp_path / "ev.sqlite")
    s, rpc, w = svc(tmp_path, store=store, interval_s=2, max_backoff_s=10)
    s.start()
    rpc.fail = True
    delays, statuses = [], []
    for _ in range(4):
        statuses.append(s.tick()["status"])
        delays.append(s.next_delay())
    assert w.calls == 0  # no decision on a chain we cannot read
    assert statuses == ["degraded", "degraded", "unavailable", "unavailable"]
    assert delays == [4, 8, 10, 10]
    assert health(s)["consecutive_rpc_errors"] == 4
    assert len(store.query(kinds=["error"])) == 4
    rpc.fail = False
    assert s.tick()["status"] == "ok" and s.next_delay() == 2
    s.stop()
    store.close()


def test_head_regression_is_flagged(tmp_path):
    store = EvidenceStore(tmp_path / "ev.sqlite")
    s, rpc, _ = svc(tmp_path, store=store)
    s.start()
    s.tick()
    rpc.head = 8
    s.tick()
    assert health(s)["reorg_suspected"] is True

    def flagged():
        return [r for r in store.query(kinds=["observation"]) if r["payload"].get("event") == "head_regressed"]

    assert len(flagged()) == 1
    rpc.hashes[8] = "0xdead"
    s.tick()  # same height, different hash
    assert len(flagged()) == 2
    s.stop()
    store.close()


def test_stale_head_skips_decisions(tmp_path):
    s, rpc, w = svc(tmp_path, max_head_age_s=60, clock=lambda: 1_700_000_000 + 10 + 3600)
    s.start()
    r = s.tick()
    assert r["skipped"] == "stale_head" and w.calls == 0 and health(s)["status"] == "degraded"
    s.stop()


def _confirm(w, rpc, block=10):
    rpc.receipts[TX] = {"transactionHash": TX, "blockNumber": hex(block), "blockHash": rpc._hash(block), "status": "0x1"}
    w.script.append([{"state": "CONFIRMED", "tx_hash": TX, "block": block, "verification": {"verified": True}}])


def test_finality_after_confirmation_depth(tmp_path):
    store = EvidenceStore(tmp_path / "ev.sqlite")
    s, rpc, w = svc(tmp_path, store=store, confirmations=3)
    s.start()
    _confirm(w, rpc)
    s.tick()
    fin = health(s)["positions"][0]["finality"]
    assert fin["status"] == "pending" and fin["confirmations"] == 1
    rpc.head = 11
    s.tick()
    assert health(s)["positions"][0]["finality"]["status"] == "pending"
    rpc.head = 12
    s.tick()
    h = health(s)["positions"][0]
    assert h["finality"]["status"] == "final" and h["finality"]["confirmations"] == 3
    assert h["last_terminal"]["state"] == "CONFIRMED" and h["state"] == "WATCHING"
    assert len(store.query(kinds=["finality"])) == 1
    s.stop()
    # persisted: a restarted service does not re-track or re-finalise
    s2, _, _ = svc(tmp_path, rpc=rpc, store=store, confirmations=3)
    assert s2.finality.items[TX]["status"] == "final"
    store.close()


def test_reorg_removes_receipt_and_journals_failed(tmp_path):
    store = EvidenceStore(tmp_path / "ev.sqlite")
    s, rpc, w = svc(tmp_path, store=store, confirmations=3)
    s.start()
    _confirm(w, rpc)
    s.tick()
    del rpc.receipts[TX]  # the block holding the tx was reorganised away
    rpc.head = 11
    r = s.tick()
    assert r["finality"][0]["status"] == "reorged"
    failed = [e for e in s.journal.entries("P") if e["state"] == "FAILED"]
    assert len(failed) == 1 and failed[0]["event"] == "reorged" and failed[0]["tx_hash"] == TX
    assert s.journal.entries("P")[-1]["state"] == "WATCHING"  # journaled BEFORE the watcher's next decision
    st = s.journal.state()["P"]
    assert st["last_terminal"]["state"] == "FAILED"
    h = health(s)["positions"][0]
    assert h["finality"]["status"] == "reorged"
    # the journal's FAILED(reorged) record and the service's own finality check are both kept
    assert {r["state"] for r in store.query(kinds=["finality"])} == {"FAILED", "REORGED"}
    s.stop()
    store.close()


def test_reincluded_in_another_block_must_reverify(tmp_path):
    s, rpc, w = svc(tmp_path, confirmations=2)
    s.start()
    _confirm(w, rpc)
    s.tick()
    rpc.hashes[10] = "0xnewblock"  # same tx, re-mined in a different block 10 after a reorg
    rpc.receipts[TX] = {**rpc.receipts[TX], "blockHash": "0xnewblock"}
    rpc.head = 11
    s.tick()
    it = s.finality.items[TX]
    assert it["reincluded"] is True and it["reverified"] is False and it["status"] == "reorged"
    s.stop()


def test_run_survives_a_bad_tick_and_stops_cleanly(tmp_path):
    s, _, w = svc(tmp_path)

    def boom():
        raise KeyError("bug")

    w.tick = boom
    s.start()
    assert s.run(max_ticks=2) == 2
    h = health(s)
    assert h["status"] == "stopped" and not s.lease.held


def test_read_health_marks_stale(tmp_path):
    s, _, _ = svc(tmp_path, interval_s=1, clock=lambda: 1000.0)
    s.start()
    s.tick()
    assert read_health(s.health_path, now=1005.0)["status"] == "ok"
    h = read_health(s.health_path, now=1000.0 + 16)
    assert h["status"] == "stale" and h["reported_status"] == "ok"
    s.stop()
    assert read_health(s.health_path, now=99_999)["status"] == "stopped"
    assert read_health(tmp_path / "nope.json") is None


# ---- read-only status endpoints ---------------------------------------------------------------------------------
@pytest.fixture()
def no_env(monkeypatch):
    for k in ("FAULTLINE_KEEPER_HEALTH", "FAULTLINE_EVIDENCE_DB", "FAULTLINE_ARM_RPC_URL", "FAULTLINE_ARM_ENVIRONMENT"):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def test_status_endpoints_say_unavailable_without_configuration(no_env):
    code, k = respond("/api/countermove?action=keeper-status")
    assert code == 200 and k["status"] == "UNAVAILABLE" and k["monitoring"] is False
    code, p = respond(f"/api/countermove?action=policy-status&vault={VAULT}")
    assert code == 200 and p["state"] == "UNAVAILABLE" and p["armed"] is False and p["monitoring"] is False
    assert "FAULTLINE_ARM_RPC_URL" in p["reason"]
    code, e = respond("/api/countermove?action=evidence&source=store")
    assert code == 200 and e["store"]["status"] == "UNAVAILABLE"


def test_status_endpoints_validate_input(no_env):
    for q in ("action=policy-status", "action=policy-status&vault=0x12", "action=evidence&limit=0",
              "action=evidence&limit=abc", "action=evidence&source=web", "action=evidence&position=a%20b",
              f"action=policy-status&vault={VAULT}&required_loan_raw=-5", "action=nope"):
        code, body = respond("/api/countermove?" + q)
        assert code == 400 and body["error"]["code"] == "invalid_input", q


def test_policy_status_never_takes_an_rpc_from_the_request(no_env):
    code, p = respond(f"/api/countermove?action=policy-status&vault={VAULT}&rpc_url=http://169.254.169.254/")
    assert p["state"] == "UNAVAILABLE" and "FAULTLINE_ARM_RPC_URL" in p["reason"]


def test_evidence_serves_the_recorded_fork_run_labelled(no_env):
    code, e = respond("/api/countermove?action=evidence&source=recorded&limit=5")
    rec = e["recorded"]
    if rec["status"] == "UNAVAILABLE":
        pytest.skip("no recorded run")
    assert rec["environment"] == "fork" and len(rec["events"]) == 5
    assert all(x["environment"] == "fork" for x in rec["events"])
    assert len(rec["integrity"]["journal_sha256"]) == 64
    code, e2 = respond(f"/api/countermove?action=evidence&source=recorded&limit=5&since={rec['next_since']}")
    assert e2["recorded"]["events"][0]["seq"] == rec["next_since"] + 1


def test_status_endpoints_read_a_running_keeper(tmp_path, no_env):
    store = EvidenceStore(tmp_path / "ev.sqlite")
    s, _, _ = svc(tmp_path, store=store)
    s.start()
    s.tick()
    store.append("observation", environment="local-test", payload={"x": 1}, position="P", idem="x")
    no_env.setenv("FAULTLINE_KEEPER_HEALTH", str(s.health_path))
    no_env.setenv("FAULTLINE_EVIDENCE_DB", str(store.path))
    k = status.keeper_status({})
    assert k["status"] == "OK" and k["monitoring"] is True
    e = status.evidence({"source": "store", "position": "P"})
    assert e["store"]["status"] == "ok" and e["store"]["integrity"]["ok"] and e["store"]["events"]
    s.stop()
    assert status.keeper_status({})["status"] == "STOPPED"
    # vault unreadable -> UNAVAILABLE even with a healthy keeper record
    no_env.setenv("FAULTLINE_ARM_RPC_URL", "http://127.0.0.1:9")
    p = status.policy_status({"vault": VAULT})
    assert p["state"] == "UNAVAILABLE" and "vault read failed" in p["reason"]
    store.close()
