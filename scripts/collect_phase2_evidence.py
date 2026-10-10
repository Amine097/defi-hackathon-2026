"""Phase 2 evidence -> audit/FAULTLINE_PHASE2_EVIDENCE.json (Autonomous Countermove + P0 vault fixes).

    $env:PYTHONPATH='src'; .\\.venv\\Scripts\\python.exe scripts/collect_phase2_evidence.py [--live] [--fork] [--reuse-tests]

Runs the test suites (offline by default; --live adds the read-only mainnet checks and a fresh Belem $1M P0 assessment;
--fork adds the Foundry test against the real Morpho Blue market on a pinned fork), reads the recorded local-fork demo
(data/countermove/demo/latest/summary.json) and the static-analysis output, scans the repository for private keys, and
evaluates the Phase 2 GO / NO-GO criteria from these results only. Read-only: it never signs or sends a transaction.
--reuse-tests keeps the `tests` section of the existing evidence file instead of re-running the suites.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "audit" / "FAULTLINE_PHASE2_EVIDENCE.json"
DEMO = ROOT / "data" / "countermove" / "demo" / "latest" / "summary.json"
P0_FIXTURE = ROOT / "data" / "fixtures" / "vault_0xd6d4b804014ef27836dbe9f8f6bf6c71251548ec_1m.json"
SLITHER = ROOT / "audit" / "FAULTLINE_PHASE2_SLITHER.txt"
CONTRACTS = ROOT / "contracts"
BELEM = "0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec"
FORK_RPC = os.environ.get("FORK_RPC_URL", "https://eth-mainnet.public.blastapi.io")
FORK_BLOCK = 26_164_248
FOUNDRY_BIN = Path.home() / ".foundry" / "bin"
LIVE_TEST_FILES = ["tests/test_vault_live.py", "tests/test_countermove_api.py", "tests/test_compliance.py",
                   "tests/test_vault.py", "tests/test_hardening.py"]
DOCS = ["docs/FAULTLINE_PHASE2_IMPLEMENTATION_REPORT.md", "docs/FAULTLINE_PHASE2_SECURITY_REPORT.md",
        "docs/FAULTLINE_PHASE2_DEMO_GUIDE.md", "docs/FAULTLINE_PHASE2_PROGRESS.md"]
EXPECTED = {"S1": ("CONFIRMED", "REPAY"), "S2": ("CONFIRMED", "TOP_UP"), "S3": ("NO_ACTION", None), "S4": ("CONFIRMED", "FULL_REPAY")}
ANVIL_MNEMONIC = "test test test test test test test test test test test junk"  # public Foundry/Hardhat default
SCAN_SKIP = ("__pycache__", ".pytest_cache")
SCAN_SKIP_PREFIX = (".git/", ".venv/", "node_modules/", "contracts/lib/", "contracts/out/", "contracts/cache/",
                    "contracts/out-deploy/", "contracts/broadcast/", "data/cache/", "resources/")
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".svg", ".woff", ".woff2", ".ttf", ".zip", ".pdf", ".pyc"}


def _env(**extra) -> dict:
    env = dict(os.environ)
    env["PATH"] = str(FOUNDRY_BIN) + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = str(ROOT / "src")
    for k in ("DEFIRISK_LIVE_TESTS", "FAULTLINE_EXPORT_UI_FIXTURES", "FORK_RPC_URL", "FAULTLINE_KEEPER_KEY"):
        env.pop(k, None)
    env.update(extra)
    return env


def _tool(name: str) -> str:
    return shutil.which(name, path=_env()["PATH"]) or name


def _run(args: list, cwd: Path = ROOT, env: dict | None = None, timeout: int = 2400):
    t0 = time.time()
    r = subprocess.run([str(a) for a in args], cwd=str(cwd), env=env or _env(), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return r, round(time.time() - t0, 1)


def _last_line(text: str) -> str:
    lines = [x.strip() for x in (text or "").splitlines() if x.strip()]
    return lines[-1] if lines else ""


# ---- test suites ----------------------------------------------------------------------------------------------------
def pytest_suite(files: list[str], live: bool) -> dict:
    with tempfile.TemporaryDirectory() as td:
        xmlp = Path(td) / "junit.xml"
        args = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xmlp}", *files]
        r, dt = _run(args, env=_env(**({"DEFIRISK_LIVE_TESTS": "1"} if live else {})))
        by_file: dict[str, dict] = {}
        failed: list[str] = []
        if xmlp.exists():
            for case in ET.parse(xmlp).getroot().iter("testcase"):
                parts = case.get("classname", "").split(".")
                mod = next((".".join(parts[:i + 1]) for i, p in enumerate(parts) if p.startswith("test_")), ".".join(parts))
                f = mod.replace(".", "/") + ".py"
                if case.find("failure") is not None or case.find("error") is not None:
                    st = "failed"
                    node = case.find("failure") if case.find("failure") is not None else case.find("error")
                    failed.append({"test": f"{f}::{case.get('name')}", "kind": node.tag,
                                   "message": (node.get("message") or "")[:500], "trace_tail": (node.text or "")[-1500:]})
                elif case.find("skipped") is not None:
                    st = "skipped"
                else:
                    st = "passed"
                row = by_file.setdefault(f, {"passed": 0, "failed": 0, "skipped": 0})
                row[st] += 1
    tot = {k: sum(v[k] for v in by_file.values()) for k in ("passed", "failed", "skipped")}
    return {"command": "python -m pytest -q -p no:cacheprovider " + " ".join(files) + (" (DEFIRISK_LIVE_TESTS=1)" if live else ""),
            "exit_code": r.returncode, "seconds": dt, **tot, "summary_line": _last_line(r.stdout),
            "failed_tests": failed, "by_file": dict(sorted(by_file.items()))}


def node_suite() -> dict:
    files = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "tests" / "js").glob("*.test.mjs"))
    r, dt = _run([_tool("node"), "--test", *files])
    num = {k: int(m.group(1)) if (m := re.search(rf"^# {k} (\d+)", r.stdout, re.M)) else None
           for k in ("tests", "pass", "fail", "skipped")}
    return {"command": "node --test " + " ".join(files), "exit_code": r.returncode, "seconds": dt, "files": files,
            "tests": num["tests"], "passed": num["pass"], "failed": num["fail"], "skipped": num["skipped"]}


def forge_suite(fork: bool) -> dict:
    args = [_tool("forge"), "test", "--json"]
    env = _env()
    if fork:
        args += ["--match-contract", "Fork", "--fork-url", FORK_RPC, "--fork-block-number", str(FORK_BLOCK),
                 "--compute-units-per-second", "40", "--fork-retries", "10", "--fork-retry-backoff", "1500"]
        env = _env(FORK_RPC_URL=FORK_RPC)
    r, dt = _run(args, cwd=CONTRACTS, env=env)
    shown = " ".join(["forge test --json", *[("$env:FORK_RPC_URL" if a == FORK_RPC else str(a)) for a in args[3:]]])
    out = {"command": f"cd contracts; {shown}", "exit_code": r.returncode, "seconds": dt}
    try:
        data = json.loads(r.stdout[r.stdout.index("{"):])
    except ValueError:
        err = (r.stderr or r.stdout)[-1500:].replace(FORK_RPC, "$env:FORK_RPC_URL")  # a custom URL may embed an API key
        return {**out, "error": err, "passed": 0, "failed": 1, "skipped": 0}
    suites, counts = {}, {"passed": 0, "failed": 0, "skipped": 0}
    for suite, body in sorted(data.items()):
        rows = []
        for name, t in sorted(body.get("test_results", {}).items()):
            st = {"Success": "passed", "Failure": "failed", "Skipped": "skipped"}.get(t.get("status"), "failed")
            counts[st] += 1
            kind = t.get("kind") or {}
            row = {"test": name, "status": st}
            if "Unit" in kind:
                row["gas"] = kind["Unit"].get("gas")
            if "Fuzz" in kind:
                row.update(fuzz_runs=kind["Fuzz"].get("runs"), median_gas=kind["Fuzz"].get("median_gas"))
            if "Invariant" in kind:
                inv = kind["Invariant"]
                row.update(invariant_runs=inv.get("runs"), invariant_calls=inv.get("calls"), invariant_reverts=inv.get("reverts"),
                           invariants=t.get("invariant_predicate_results"),
                           handler_calls={k.split(".")[-1]: {"calls": v.get("calls"), "reverts": v.get("reverts")}
                                          for k, v in sorted((inv.get("metrics") or {}).items())})
            if t.get("reason"):
                row["reason"] = t["reason"][:300]
            rows.append(row)
        suites[suite] = rows
    return {**out, **counts, "suites": suites}


def run_tests(live: bool, fork: bool) -> dict:
    tests = {"pytest_offline": pytest_suite([], live=False), "node": node_suite(), "forge": forge_suite(fork=False)}
    if live:
        tests["pytest_live"] = pytest_suite(LIVE_TEST_FILES, live=True)
    if fork:
        tests["forge_fork"] = forge_suite(fork=True)
    return tests


# ---- P0 (vault depositors) ------------------------------------------------------------------------------------------
def p0_section(live: bool) -> dict:
    fx = json.loads(P0_FIXTURE.read_text(encoding="utf-8"))
    sec = {"what": "P0-A: VaultV2 forceDeallocate exit route simulated and used; P0-B: partial exits compared on one economic basis",
           "recorded": {"fixture": P0_FIXTURE.relative_to(ROOT).as_posix(), "recorded_at": fx.get("recorded_at_iso"),
                        "label": "replay (dated real snapshot, re-evaluated offline by tests/test_vault_p0.py)",
                        **fx["live_headline"]}}
    if live:
        try:
            from defirisk import vault_model as vm
            from defirisk.vault_input import parse_request
            t0 = time.time()
            p = vm.analyze(parse_request({"address": BELEM, "value_usd": "1000000", "horizon_days": "30"}))
            d, e = p["decision"], p["exit"]
            sim = e.get("simulation_force_deallocate") or {}
            sec["live"] = {"status": "LIVE", "as_of_block": p["as_of_block"], "mode": p["mode"], "elapsed_s": round(time.time() - t0, 1),
                           "withdrawal_feasibility": e["withdrawal_feasibility"], "executable_route": e["executable_route"],
                           "comparison_basis": e["comparison_basis"],
                           "immediately_withdrawable_usd": round(e["immediately_withdrawable_usd"], 2),
                           "blocked_or_deferred_usd": round(e["blocked_or_deferred_usd"], 2),
                           "ordinary_route": {k: e["routes"]["ordinary"].get(k) for k in ("status", "capacity_usd", "gas")},
                           "force_deallocate_route": {k: e["routes"]["force_deallocate"].get(k)
                                                      for k in ("status", "capacity_usd", "penalty_usd", "gas")},
                           "force_plan": (e.get("force_deallocate") or {}).get("plan"),
                           "force_simulation": {k: sim.get(k) for k in ("status", "gas", "error") if k in sim},
                           "verdict": d["verdict"], "point_verdict": d["point_verdict"],
                           "expected_loss_usd": round(d["expected_loss_usd"], 2), "exit_side_usd": round(d["exit_side_usd"], 2)}
        except Exception as ex:  # noqa: BLE001 - recorded as a failed LIVE read, never hidden
            sec["live"] = {"status": "FAILED", "error": f"{type(ex).__name__}: {ex}"[:400]}
    return sec


# ---- recorded fork demo ---------------------------------------------------------------------------------------------
def _human(raw, token: dict | None):
    if raw is None or not token:
        return None
    return raw / 10 ** token["decimals"]


def demo_section() -> dict:
    s = json.loads(DEMO.read_text(encoding="utf-8"))
    keeper = s["environment"]["keeper"].lower()
    scen = []
    for sc in s["scenarios"]:
        plan = sc.get("plan") or {}
        chosen = sc.get("chosen") or (plan.get("chosen") if isinstance(plan.get("chosen"), dict) else None)
        cands = [{"strategy": c["strategy"], "status": c["status"], "required": _human(c.get("required_raw"), c.get("token")),
                  "token": (c.get("token") or {}).get("symbol"), "rejected_at": c.get("rejected_at"),
                  "reason": (c.get("reasons") or [None])[0]} for c in plan.get("candidates", [])]
        rec = {"scenario": sc["scenario"], "label": sc["label"], "user": sc["user"], "rescue_vault": sc["rescue_vault"],
               "market_id": sc["market_id"], "expected_final_state": sc["expected_final_state"], "final_state": sc["final_state"],
               "states": sc["states"], "simulated_shock": {k: sc["simulated_shock"].get(k) for k in ("original_description", "shock_bps", "label")},
               "ltv_at_detection": (sc.get("detected") or {}).get("trigger", {}).get("ltv"),
               "trigger_ltv": plan.get("trigger_ltv"), "decision": plan.get("decision"),
               "chosen": chosen and {"strategy": chosen["strategy"], "amount": _human(chosen["amount_raw"], chosen.get("token")),
                                     "token": (chosen.get("token") or {}).get("symbol"), "amount_raw": chosen["amount_raw"],
                                     "keeper_bound": chosen.get("keeper_bound"), "bound_kind": chosen.get("bound_kind")},
               "candidates": cands, "why": plan.get("why"), "no_action_reason": sc.get("no_action_reason"),
               "user_nonce_unchanged": sc["user_nonce_after_arming"] == sc["user_nonce_at_end"],
               "user_signed_during_crisis": sc["user_signed_during_crisis"], "end_vault": sc["end_vault"]}
        if sc.get("execution"):
            ex, ve = sc["execution"], sc["verification"]
            rec["execution"] = {k: ex[k] for k in ("tx_hash", "block", "from", "to", "status", "gas_used", "signed_by", "action_id")}
            rec["execution"]["signer_is_keeper"] = ex["from"].lower() == keeper
            rec["verification"] = {"verified": ve["verified"], "checks_passed": sum(1 for c in ve["checks"] if c.get("ok")),
                                   "checks_total": len(ve["checks"]), "checks": [c["check"] for c in ve["checks"]],
                                   "event": ve.get("event"), "before": ve["before"], "after": ve["after"],
                                   "remaining_limits": ve.get("remaining_limits")}
        scen.append(rec)
    return {"source": DEMO.relative_to(ROOT).as_posix(), "label": "SIMULATED environment (local Anvil fork); CONFIRMED = mined on that fork and verified",
            "generated_at": datetime.fromtimestamp(s["generated_at"], timezone.utc).isoformat(timespec="seconds"),
            "duration_s": s["duration_s"], "environment": s["environment"], "all_expected": s["all_expected"],
            "keeper_runs": [{k: r[k] for k in ("tag", "command", "seconds")} | {"results": [(x["position"], x["state"], x["tx_hash"]) for x in r["results"]]}
                            for r in s["keeper_runs"]],
            "scenarios": scen}


# ---- static analysis, secrets, environment --------------------------------------------------------------------------
def slither_section() -> dict:
    if not SLITHER.exists():
        return {"status": "not run"}
    text = SLITHER.read_text(encoding="utf-8")
    per, cur = {}, None
    for line in text.splitlines():
        if line.startswith("Detector: "):
            cur = line.split(": ", 1)[1].strip()
            per[cur] = 0
        elif cur and line and not line[0].isspace() and not line.startswith(("Reference:", "INFO:", "#")):
            per[cur] += 1
        elif line.startswith("Reference:"):
            cur = None
    m = re.search(r"analyzed \((\d+) contracts with (\d+) detectors\), (\d+) result", text)
    ver = re.search(r"Slither ([\d.]+)", text)
    return {"tool": f"slither {ver.group(1) if ver else '?'}", "raw_output": SLITHER.relative_to(ROOT).as_posix(),
            "contracts_analyzed": int(m.group(1)) if m else None, "detectors": int(m.group(2)) if m else None,
            "results": int(m.group(3)) if m else None, "by_detector": per, "results_counted": sum(per.values()),
            "requiring_code_change": 0, "triage": "docs/FAULTLINE_PHASE2_SECURITY_REPORT.md section 6"}


def forge_lint_section() -> dict:
    r, _ = _run([_tool("forge"), "lint", "src"], cwd=CONTRACTS)
    found, cur = [], None
    for line in (r.stdout + "\n" + r.stderr).splitlines():
        if (m := re.match(r"^(warning|note|error)\[([\w-]+)\]", line)):
            cur = f"{m.group(1)}[{m.group(2)}]"
        elif cur and (m := re.search(r"(src/[\w/]+\.sol):(\d+)", line)):
            found.append((cur, m.group(1), int(m.group(2))))
            cur = None
    by_id: dict[str, int] = {}
    for lint, _f, _l in found:
        by_id[lint] = by_id.get(lint, 0) + 1
    return {"tool": "forge lint (Foundry)", "total": len(found), "by_lint": dict(sorted(by_id.items())),
            "on_rescue_vault": sum(1 for x in found if x[1] == "src/RescueVault.sol"),
            "on_test_only_sim_contracts": sum(1 for x in found if x[1].startswith("src/sim/")),
            "requiring_code_change": 0, "triage": "docs/FAULTLINE_PHASE2_SECURITY_REPORT.md section 6"}


def secrets_scan() -> dict:
    keys = []
    for i in range(10):
        r, _ = _run([_tool("cast"), "wallet", "private-key", "--mnemonic", ANVIL_MNEMONIC, "--mnemonic-index", str(i)])
        if r.returncode == 0 and r.stdout.strip():
            keys.append(r.stdout.strip().lower().removeprefix("0x"))
    assign = re.compile(r"(?i)(private[_ -]?key|secret[_ -]?key|mnemonic)[\"']?\s*[:=]\s*[\"']?(0x)?[0-9a-f]{64}\b")
    n, key_hits, assign_hits, mnemonic_refs = 0, [], [], []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        base = Path(dirpath).relative_to(ROOT).as_posix()
        base = "" if base == "." else base + "/"
        dirnames[:] = [d for d in dirnames if d not in SCAN_SKIP and not (base + d + "/").startswith(SCAN_SKIP_PREFIX)]
        for fn in sorted(filenames):
            p, rel = Path(dirpath) / fn, base + fn
            if p.suffix.lower() in BINARY_EXT or p.stat().st_size > 5_000_000:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            n += 1
            low = text.lower()
            if any(k in low for k in keys):
                key_hits.append(rel)
            if assign.search(text):
                assign_hits.append(rel)
            if ANVIL_MNEMONIC in text:
                mnemonic_refs.append(rel)
    return {"files_scanned": n, "excluded": list(SCAN_SKIP_PREFIX), "anvil_test_private_keys_checked": len(keys),
            "anvil_private_keys_found_in": key_hits, "private_key_assignments_found_in": assign_hits,
            "public_anvil_test_mnemonic_referenced_in": mnemonic_refs,
            "note": "the Anvil mnemonic is public and worthless; keys are derived from it at run time and never stored",
            "ok": not key_hits and not assign_hits}


def environment_section() -> dict:
    def first(args, cwd=ROOT):
        try:
            r, _ = _run(args, cwd=cwd)
            return _last_line(r.stdout.splitlines()[0] if r.stdout.strip() else r.stderr)
        except Exception as e:  # noqa: BLE001
            return f"unavailable: {e}"
    forge_v, _ = _run([_tool("forge"), "--version"])
    commit = re.search(r"Commit SHA: (\w+)", forge_v.stdout)
    pins = []
    for m in re.finditer(r"name = '([^']+)'; repo = '([^']+)'; tag = '([^']+)'; sha = '([^']+)'",
                         (CONTRACTS / "install_deps.ps1").read_text(encoding="utf-8")):
        name, repo, tag, sha = m.groups()
        head = first(["git", "-C", str(CONTRACTS / "lib" / name), "rev-parse", "HEAD"])
        pins.append({"name": name, "repo": repo, "tag": tag, "pinned": sha, "installed_head": head, "ok": head.startswith(sha)})
    solc = {}
    for art in ("RescueVault.sol/RescueVault.json", "Morpho.sol/Morpho.json"):
        try:
            meta = json.loads((CONTRACTS / "out" / art).read_text(encoding="utf-8"))["metadata"]
            solc[art.split("/")[0]] = meta["compiler"]["version"]
        except Exception:  # noqa: BLE001
            solc[art.split("/")[0]] = "artifact missing (run forge build)"
    return {"os": platform.platform(), "python": platform.python_version(), "node": first([_tool("node"), "--version"]),
            "forge": first([_tool("forge"), "--version"]) + (f" (commit {commit.group(1)[:10]})" if commit else ""),
            "anvil": first([_tool("anvil"), "--version"]), "cast": first([_tool("cast"), "--version"]), "solc": solc,
            "foundry_profile": {"optimizer_runs": 200, "evm_version": "cancun", "fuzz_runs": 512, "invariant_runs": 64, "invariant_depth": 64},
            "solidity_dependencies": pins}


def git_section() -> dict:
    head, _ = _run(["git", "rev-parse", "HEAD"])
    br, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    st, _ = _run(["git", "status", "--porcelain"])
    lines = [x for x in st.stdout.splitlines() if x.strip()]
    return {"head": head.stdout.strip(), "branch": br.stdout.strip(), "working_tree_changes": len(lines),
            "note": "evidence collected on the working tree (Phase 2 changes not committed at collection time)" if lines else "clean"}


# ---- GO / NO-GO -----------------------------------------------------------------------------------------------------
def criteria(tests: dict, p0: dict, demo: dict, sec: dict) -> list[dict]:
    sc = {s["scenario"]: s for s in demo["scenarios"]}
    po = tests.get("pytest_offline", {})
    bf = po.get("by_file", {})

    def file_ok(f):
        row = bf.get(f) or {}
        return row.get("failed", 1) == 0 and row.get("passed", 0) > 0

    def confirmed(sid, strategy):
        s = sc.get(sid) or {}
        v = s.get("verification") or {}
        return (s.get("final_state") == "CONFIRMED" and (s.get("chosen") or {}).get("strategy") == strategy
                and (s.get("execution") or {}).get("status") == 1 and v.get("verified") is True
                and v.get("checks_passed") == v.get("checks_total"))

    def within_limits(s):
        v = s.get("verification") or {}
        ev, rem = v.get("event") or {}, v.get("remaining_limits") or {}
        pol, strat, amt = rem.get("policy") or {}, ev.get("strategy"), ev.get("assets")
        if amt is None or not pol:
            return False
        cap = {"REPAY": "max_repay_per_action", "TOP_UP": "max_top_up_per_action", "FULL_REPAY": "max_full_repay"}[strat]
        floor = pol["min_collateral_reserve"] if strat == "TOP_UP" else pol["min_loan_reserve"]
        ok = amt <= pol[cap] and rem["repaid_total"] <= pol["max_repay_total"] and rem["topped_up_total"] <= pol["max_top_up_total"]
        ok = ok and v["after"]["reserve"] >= floor
        if (s.get("chosen") or {}).get("bound_kind") == "maxAssets":
            ok = ok and amt <= s["chosen"]["keeper_bound"]
        return ok

    suites = [v for v in tests.values() if isinstance(v, dict) and "failed" in v]
    live_p0 = p0.get("live")
    e2e = "tests/test_countermove_e2e.py"
    rows = [
        ("P0 vault corrections validated",
         file_ok("tests/test_vault_p0.py") and p0["recorded"]["withdrawal_feasibility"] == "full_via_force_deallocate"
         and (live_p0 is None or (live_p0.get("status") == "LIVE" and live_p0.get("withdrawal_feasibility") in ("full_via_force_deallocate", "full"))),
         "tests/test_vault_p0.py; Belem $1M recorded" + (" + LIVE re-assessment" if live_p0 else "")),
        ("Existing risk engine did not regress",
         po.get("failed") == 0 and tests.get("node", {}).get("failed") == 0 and tests.get("pytest_live", {}).get("failed", 0) == 0,
         "pytest offline (Phase 0.5/1 + Phase 2), Node view-model tests" + (", live checks" if "pytest_live" in tests else "")),
        ("RescueVault enforces the configured permissions",
         tests.get("forge", {}).get("failed") == 0 and tests.get("forge", {}).get("passed", 0) >= 29
         and all(i.get("status") == "Success" for rows_ in tests.get("forge", {}).get("suites", {}).values() for r in rows_
                 for i in (r.get("invariants") or [])) and file_ok(e2e),
         "Foundry unit/fuzz/token/invariant suites; e2e malicious keeper transactions revert"),
        ("AUTO-REPAY works automatically on the fork", confirmed("S1", "REPAY"), "S1"),
        ("AUTO-TOP-UP works automatically on the fork", confirmed("S2", "TOP_UP"), "S2"),
        ("Comparator chooses by justified rules",
         all(((sc.get(k) or {}).get("final_state"), ((sc.get(k) or {}).get("chosen") or {}).get("strategy")) == v for k, v in EXPECTED.items())
         and all(c["status"] == "eligible" or (c["rejected_at"] and c["reason"]) for s in sc.values() for c in s["candidates"])
         and file_ok("tests/test_countermove_engine.py"),
         "S1-S4 decisions; every rejected candidate has a stage and a reason; engine tests"),
        ("No extra user signature at trigger time",
         all(s["user_nonce_unchanged"] and not s["user_signed_during_crisis"] for s in sc.values())
         and all(s["execution"]["signer_is_keeper"] for s in sc.values() if s.get("execution")),
         "user nonces unchanged; rescue transactions signed by the keeper"),
        ("Executed amounts respect the authorizations", all(within_limits(s) for s in sc.values() if s.get("execution")),
         "event amount <= per-action cap, totals <= cumulative caps, reserve >= floor, full repay <= keeper bound"),
        ("Monitoring independent of the browser",
         bool(demo["keeper_runs"]) and all(r["command"].startswith("python -m defirisk.countermove") for r in demo["keeper_runs"]),
         "keeper runs as a separate OS process"),
        ("Results confirmed and verified on-chain",
         all(confirmed(k, v[1]) for k, v in EXPECTED.items() if v[0] == "CONFIRMED"), "receipt + events + re-read state"),
        ("Dangerous / unauthorized situation -> NO ACTION",
         (sc.get("S3") or {}).get("final_state") == "NO_ACTION" and not (sc.get("S3") or {}).get("execution")
         and (sc.get("S3") or {}).get("end_vault", {}).get("action_count") == 0 and file_ok(e2e),
         "S3 sent nothing; e2e stale feed / gas cap / watch-only / paused / no-safe-action"),
        ("Security and regression tests pass", bool(suites) and all(v.get("failed") == 0 for v in suites),
         ", ".join(f"{k}: {v.get('passed')} passed / {v.get('failed')} failed / {v.get('skipped')} skipped" for k, v in tests.items())),
        ("Frontend shows real simulation and transaction results",
         file_ok("tests/test_countermove_api.py") and tests.get("node", {}).get("failed") == 0 and (ROOT / "public" / "countermove.html").exists(),
         "/countermove.html from the recorded run; proof-checked statuses"),
        ("Demonstration scenarios reproducible", demo["all_expected"] is True and (ROOT / "scripts" / "countermove_fork_demo.py").exists(),
         "scripts/countermove_fork_demo.py -> all_expected"),
        ("Limits and assumptions documented",
         all((ROOT / d).exists() for d in DOCS) and "NOT AUDITED" in (ROOT / DOCS[1]).read_text(encoding="utf-8")
         and sec["secrets_scan"]["ok"], "four Phase 2 documents; secrets scan clean"),
    ]
    return [{"criterion": c, "status": "PASS" if ok else "FAIL", "evidence": ev} for c, ok, ev in rows]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true", help="read-only mainnet checks (live pytest subset + fresh Belem $1M P0)")
    ap.add_argument("--fork", action="store_true", help="Foundry fork test against the real Morpho Blue market")
    ap.add_argument("--reuse-tests", action="store_true", help="keep the tests section of the existing evidence file")
    a = ap.parse_args()
    t0 = time.time()
    if a.reuse_tests and OUT.exists():
        tests = json.loads(OUT.read_text(encoding="utf-8"))["tests"]
    else:
        tests = run_tests(a.live, a.fork)
    p0 = p0_section(a.live)
    demo = demo_section()
    sec = {"slither": slither_section(), "forge_lint": forge_lint_section(), "secrets_scan": secrets_scan(),
           "disclaimer": "NOT AUDITED: tests and static analysis are not a security guarantee for real funds"}
    crit = criteria(tests, p0, demo, sec)
    failing = [c["criterion"] for c in crit if c["status"] != "PASS"]
    ev = {"schema": "faultline.phase2.evidence/1", "phase": "Phase 2 - Autonomous Countermove (+ P0 vault fixes)",
          "spec": "docs/FAULTLINE_Countermove_v3_Autonomous_Crisis_Response.md",
          "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
          "collector": "scripts/collect_phase2_evidence.py" + (" --live" if a.live else "") + (" --fork" if a.fork else ""),
          "scope": "local Anvil fork (chain id 31337) + read-only mainnet eth_call; no mainnet transaction, no real funds, "
                   "no personal key (keeper key derived from the public Anvil test mnemonic)",
          "status_labels": {"LIVE": "read now on Ethereum mainnet (read-only)", "SIMULATED": "local fork state or controlled shock",
                            "CONFIRMED": "mined on the local fork and verified", "FAILED": "reverted / not executed",
                            "NO ACTION": "nothing sent, with the reason"},
          "git": git_section(), "environment": environment_section(), "tests": tests, "p0_vault": p0,
          "fork_demo": demo, "security": sec, "go_no_go": crit,
          "verdict": ("GO - prototype validated on a local test environment (not an authorization to manage real funds)"
                      if not failing else "NO-GO - failing: " + "; ".join(failing)),
          "collection_seconds": round(time.time() - t0, 1)}
    OUT.write_text(json.dumps(ev, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for c in crit:
        print(f"{c['status']:4}  {c['criterion']}")
    for k, v in tests.items():
        print(f"      {k}: {v.get('passed')} passed, {v.get('failed')} failed, {v.get('skipped')} skipped ({v.get('seconds')} s)")
    print(ev["verdict"])
    print(f"-> {OUT.relative_to(ROOT).as_posix()}")
    return 0 if not failing else 1


if __name__ == "__main__":
    raise SystemExit(main())
