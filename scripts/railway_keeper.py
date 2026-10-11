"""FAULTLINE keeper as a hosted service (Railway): ONE container = a local Anvil test chain (chain id 31337, test tokens,
a SIMULATED ETH/USD feed) + the persistent keeper service + a read-only status API. It never touches Ethereum mainnet and
holds no real key: the keeper signs with an encrypted keystore of PUBLIC Anvil test account #1.

    python scripts/railway_keeper.py

First start (empty data dir): starts Anvil, deploys Morpho Blue v1.0.0 + RescueVault from the Foundry artifacts, opens the
test position (5 WETH collateral, 8,000 USDC debt, LTV 80%), funds the reserve and signs the owner policy (trigger LTV 82%),
then starts the keeper. Later starts reload the chain from <data>/anvil-state.json and the keeper resumes from its journal.

Environment:
  PORT                        status API port (Railway injects it; default 8080)
  FAULTLINE_DATA_DIR          persistent directory: mount the Railway volume here (default /data)
  FAULTLINE_KEEPER_INTERVAL   keeper tick in seconds (default 3)
  FAULTLINE_BLOCK_TIME        Anvil block time in seconds (default 6): confirmations need new blocks
  FAULTLINE_ADMIN_TOKEN       optional; enables POST /admin/shock?usd=<price> (Authorization: Bearer <token>), a SIMULATED
                              price move on the local test feed for demonstrations. Unset = endpoint disabled (404).

Routes (GET, JSON, read-only):
  /healthz                                   200 when the keeper heartbeat is fresh and OK, else 503
  /                                          service description, environment, test vault address
  /api/countermove?action=keeper-status      same schema as the Vercel endpoint
  /api/countermove?action=policy-status      [&vault=0x..] defaults to this service's test vault
  /api/countermove?action=evidence           [&source=store|recorded|all][&limit=..][&since=..]
"""
from __future__ import annotations

import hmac
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defirisk import abi  # noqa: E402
from defirisk.countermove import contracts, devchain  # noqa: E402
from defirisk.countermove import status as cms  # noqa: E402
from defirisk.countermove.chain import RPC, RPCError  # noqa: E402
from defirisk.countermove.signer import import_test_keystore  # noqa: E402

DATA = Path(os.getenv("FAULTLINE_DATA_DIR", "/data"))
KEEPER_DIR, WORLD = DATA / "keeper", DATA / "world.json"
ANVIL_PORT = 8545
USDC, ETH = 10 ** 6, 10 ** 18
ZERO = "0x" + "0" * 40
MP = "(address,address,address,address,uint256)"
POLICY_SIG = "setPolicy((uint8,uint64,uint32,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256))"
DEP, KEEPER, USER, LP = (devchain.ROLE[k] for k in ("deployer", "keeper", "user", "lp"))
ENVIRONMENT_LABEL = "local-test: Anvil chain id 31337 inside this container, test tokens, SIMULATED price feed; not Ethereum mainnet"
STATUS_ACTIONS = {"keeper-status": cms.keeper_status, "policy-status": cms.policy_status, "evidence": cms.evidence}


def log(msg: str) -> None:
    print(f"[railway-keeper] {msg}", flush=True)


def bootstrap(rpc: RPC) -> dict:
    """Deploy the local test world and arm one position (same setup as tests/test_countermove_e2e.py)."""
    d, c = devchain.deploy, devchain.call
    w = {"morpho": d(rpc, DEP, "Morpho", ["address"], [DEP]), "irm": d(rpc, DEP, "IrmMock")}
    w["usdc"] = d(rpc, DEP, "TestToken", ["string", "string", "uint8"], ["USD Coin (local test)", "USDC", 6], "LocalSim")
    w["weth"] = d(rpc, DEP, "TestToken", ["string", "string", "uint8"], ["Wrapped Ether (local test)", "WETH", 18], "LocalSim")
    w["feed"] = d(rpc, DEP, "SimFeed", ["string", "uint8", "int256"], ["ETH / USD", 8, 2000 * 10 ** 8], "LocalSim")
    w["oracle"] = d(rpc, DEP, "SimChainlinkOracle", ["address"] * 4 + ["uint256"], [w["feed"], ZERO, ZERO, ZERO, 10 ** 16],
                    "LocalSim")
    c(rpc, DEP, w["morpho"], "enableIrm(address)", [w["irm"]])
    c(rpc, DEP, w["morpho"], "enableLltv(uint256)", [86 * 10 ** 16])
    params = [w["usdc"], w["weth"], w["oracle"], w["irm"], 86 * 10 ** 16]
    c(rpc, DEP, w["morpho"], f"createMarket({MP})", [params])
    w["market_id"] = abi.market_id({"loan_token": w["usdc"], "collateral_token": w["weth"], "oracle": w["oracle"],
                                    "irm": w["irm"], "lltv_raw": 86 * 10 ** 16})
    c(rpc, DEP, w["usdc"], "mint(address,uint256)", [LP, 1_000_000 * USDC])
    c(rpc, LP, w["usdc"], "approve(address,uint256)", [w["morpho"], 2 ** 256 - 1])
    c(rpc, LP, w["morpho"], f"supply({MP},uint256,uint256,address,bytes)", [params, 1_000_000 * USDC, 0, LP, b""])
    c(rpc, DEP, w["weth"], "mint(address,uint256)", [USER, 10 * ETH])
    c(rpc, USER, w["weth"], "approve(address,uint256)", [w["morpho"], 2 ** 256 - 1])
    c(rpc, USER, w["morpho"], f"supplyCollateral({MP},uint256,address,bytes)", [params, 5 * ETH, USER, b""])
    c(rpc, USER, w["morpho"], f"borrow({MP},uint256,uint256,address,address)", [params, 8_000 * USDC, 0, USER, USER])
    w["vault"] = d(rpc, USER, "RescueVault", ["address", MP, "address", "address"], [w["morpho"], params, USER, KEEPER])
    c(rpc, DEP, w["usdc"], "mint(address,uint256)", [USER, 10_000 * USDC])
    for t in ("usdc", "weth"):
        c(rpc, USER, w[t], "approve(address,uint256)", [w["vault"], 2 ** 256 - 1])
    # the owner's one-time authorization: reserve + policy (REPAY | TOP_UP | FULL_REPAY, trigger LTV 82%, caps)
    c(rpc, USER, w["vault"], "deposit(address,uint256)", [w["usdc"], 3_000 * USDC])
    c(rpc, USER, w["vault"], "deposit(address,uint256)", [w["weth"], ETH // 2])
    now = rpc.block()["timestamp"]
    pol = {"allowed_strategies": 7, "valid_until": now + 30 * 86_400, "cooldown": 3_600, "trigger_ltv": 82 * 10 ** 16,
           "min_ltv_after": 40 * 10 ** 16, "max_repay_per_action": 2_500 * USDC, "max_top_up_per_action": ETH,
           "max_full_repay": 9_000 * USDC, "max_repay_total": 10_000 * USDC, "max_top_up_total": 2 * ETH,
           "min_loan_reserve": 50 * USDC, "min_collateral_reserve": ETH // 100}
    c(rpc, USER, w["vault"], POLICY_SIG, [[pol[k] for k in contracts.POLICY_FIELDS]])
    w["created_at"] = int(time.time())
    return w


def keeper_config(rpc_url: str, w: dict) -> dict:
    return {"rpc_url": rpc_url, "environment": "local-test", "limits": {"receipt_timeout_s": 30},
            "positions": [{"id": "railway-test", "label": "WETH/USDC local test position (hosted keeper)",
                           "rescue_vault": w["vault"], "engine": {"safety_margin": "200", "interest_horizon_s": 86_400},
                           "scenarios": [{"id": "eth10", "label": "ETH / USD -10% follow-on",
                                          "shocks": [{"dependency": "ETH / USD", "drop": 0.10}]}],
                           "retry_after_failed_s": 60, "realert_s": 3_600}]}


def keystore() -> tuple[Path, Path]:
    d = DATA / "keystore"
    ks, pw = d / "anvil-test-1", d / "anvil-test-1.password"
    if ks.is_file() and pw.is_file():
        return ks, pw
    shutil.rmtree(d, ignore_errors=True)
    return import_test_keystore(1, d)


class Service:
    def __init__(self):
        self.anvil: devchain.Anvil | None = None
        self.keeper: subprocess.Popen | None = None
        self.world: dict = {}
        self.stopping = threading.Event()

    def start(self) -> None:
        DATA.mkdir(parents=True, exist_ok=True)
        block_time = os.getenv("FAULTLINE_BLOCK_TIME", "6")
        self.anvil = devchain.Anvil(ANVIL_PORT, log=DATA / "anvil.log",
                                    extra=["--state", str(DATA / "anvil-state.json"), "--state-interval", "15",
                                           "--block-time", block_time]).start()
        rpc = RPC(self.anvil.url)
        world = json.loads(WORLD.read_text()) if WORLD.is_file() else None
        if world and rpc.code(world["vault"]) not in ("0x", "", None):
            log(f"chain state reloaded: vault {world['vault']} present at block {rpc.block()['number']}")
        else:
            if KEEPER_DIR.exists():  # the chain was lost: the old journal describes a chain that no longer exists
                arch = DATA / f"keeper-archived-{int(time.time())}"
                KEEPER_DIR.rename(arch)
                log(f"previous keeper state archived to {arch} (chain state was not recoverable)")
            log("bootstrapping the local test world (Morpho Blue v1.0.0 + RescueVault, test tokens)")
            rpc.call("evm_setAutomine", [True])  # one block per tx while deploying, then back to interval mining
            try:
                world = bootstrap(rpc)
            finally:
                rpc.call("evm_setIntervalMining", [int(block_time)])
            WORLD.write_text(json.dumps(world, indent=1))
            rpc.call("anvil_mine", ["0x1"])
            log(f"armed test position: vault {world['vault']} (owner {USER}, keeper {KEEPER})")
        self.world = world
        cfg = DATA / "keeper.json"
        cfg.write_text(json.dumps(keeper_config(self.anvil.url, world), indent=1))
        ks, pw = keystore()
        KEEPER_DIR.mkdir(parents=True, exist_ok=True)
        os.environ.update({"FAULTLINE_ARM_RPC_URL": self.anvil.url, "FAULTLINE_ARM_ENVIRONMENT": "local-test",
                           "FAULTLINE_KEEPER_HEALTH": str(KEEPER_DIR / "health.json"),
                           "FAULTLINE_EVIDENCE_DB": str(KEEPER_DIR / "evidence.sqlite")})
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "FAULTLINE_KEEPER_KEYSTORE": str(ks),
               "FAULTLINE_KEEPER_PASSWORD_FILE": str(pw)}
        self.keeper = subprocess.Popen(
            [sys.executable, "-m", "defirisk.countermove.service", "--config", str(cfg), "--journal-dir",
             str(KEEPER_DIR / "journal"), "--state-dir", str(KEEPER_DIR), "--environment", "local-test",
             "--confirmations", "2", "--interval", os.getenv("FAULTLINE_KEEPER_INTERVAL", "3")], env=env, cwd=str(ROOT))
        log(f"keeper service started (pid {self.keeper.pid})")

    def dead(self) -> str | None:
        if self.anvil and self.anvil.proc and self.anvil.proc.poll() is not None:
            return f"anvil exited ({self.anvil.proc.returncode})"
        if self.keeper and self.keeper.poll() is not None:
            return f"keeper exited ({self.keeper.returncode})"
        return None

    def stop(self) -> None:
        self.stopping.set()
        if self.keeper and self.keeper.poll() is None:
            self.keeper.send_signal(signal.SIGTERM)  # graceful: the keeper writes status 'stopped' and frees its lock
            try:
                self.keeper.wait(20)
            except subprocess.TimeoutExpired:
                self.keeper.kill()
        if self.anvil:
            self.anvil.stop()


SVC = Service()
_RATE: dict[str, list[float]] = {}
_RATE_LOCK = threading.Lock()


def _allowed(ip: str, limit: int = 120, window: float = 60.0) -> bool:
    now = time.time()
    with _RATE_LOCK:
        hits = [t for t in _RATE.get(ip, []) if now - t < window]
        if len(hits) >= limit:
            _RATE[ip] = hits
            return False
        hits.append(now)
        _RATE[ip] = hits
        if len(_RATE) > 10_000:
            _RATE.clear()
        return True


class Handler(BaseHTTPRequestHandler):
    server_version = "faultline-keeper"

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, allow_nan=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quieter access log: health checks every few seconds
        if not self.path.startswith("/healthz"):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _client(self) -> str:
        return (self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[0].strip()

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items() if v}
        if u.path != "/healthz" and not _allowed(self._client()):
            return self._send(429, {"error": {"code": "rate_limited", "status": 429}})
        try:
            if u.path == "/healthz":
                k = cms.keeper_status({})
                return self._send(200 if k.get("status") == "OK" else 503, k)
            if u.path in ("", "/"):
                return self._send(200, {"service": "FAULTLINE hosted keeper", "environment": ENVIRONMENT_LABEL,
                                        "mainnet": "read-only analysis only; FAULTLINE never transacts on Ethereum mainnet",
                                        "test_vault": SVC.world.get("vault"), "owner": USER, "keeper": KEEPER,
                                        "routes": ["/healthz", "/api/countermove?action=keeper-status",
                                                   "/api/countermove?action=policy-status",
                                                   "/api/countermove?action=evidence"]})
            if u.path.rstrip("/") == "/api/countermove":
                action = q.get("action")
                if action not in STATUS_ACTIONS:
                    return self._send(400, {"error": {"code": "invalid_input", "status": 400, "field": "action",
                                                      "message": "accepted: " + ", ".join(STATUS_ACTIONS)}})
                if action == "policy-status" and not q.get("vault"):
                    q["vault"] = SVC.world.get("vault")
                return self._send(200, STATUS_ACTIONS[action](q))
            return self._send(404, {"error": {"code": "not_found", "status": 404}})
        except (ValueError, KeyError) as e:
            return self._send(400, {"error": {"code": "invalid_input", "status": 400, "message": str(e)[:300]}})
        except Exception as e:  # noqa: BLE001 - generic message, details stay in the service log
            log(f"status request failed: {type(e).__name__}: {e}")
            return self._send(500, {"error": {"code": "internal_error", "status": 500}})

    def do_POST(self):
        u = urlparse(self.path)
        token = os.getenv("FAULTLINE_ADMIN_TOKEN")
        if u.path != "/admin/shock" or not token:
            return self._send(404, {"error": {"code": "not_found", "status": 404}})
        if not _allowed("admin:" + self._client(), limit=10):
            return self._send(429, {"error": {"code": "rate_limited", "status": 429}})
        given = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(given.encode(), token.encode()):
            return self._send(401, {"error": {"code": "unauthorized", "status": 401}})
        q = {k: v[0] for k, v in parse_qs(u.query).items() if v}
        try:
            usd = int(q.get("usd", ""))
            if not 100 <= usd <= 100_000:
                raise ValueError
        except ValueError:
            return self._send(400, {"error": {"code": "invalid_input", "status": 400, "field": "usd",
                                              "message": "usd must be an integer price between 100 and 100000"}})
        rpc = RPC(SVC.anvil.url)
        ts = rpc.block()["timestamp"]
        rc = devchain.call(rpc, DEP, SVC.world["feed"], "set(int256,uint256)", [usd * 10 ** 8, ts])
        log(f"SIMULATED shock: local test feed ETH/USD set to {usd}")
        return self._send(200, {"simulated": True, "environment": ENVIRONMENT_LABEL, "eth_usd": usd,
                                "tx_hash": rc.get("transactionHash")})


def main() -> int:
    port = int(os.getenv("PORT", "8080"))
    try:
        SVC.start()
    except (RPCError, OSError, RuntimeError, TimeoutError) as e:
        log(f"startup failed: {type(e).__name__}: {e}")
        SVC.stop()
        return 1
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    exit_code = [0]

    def supervise():
        while not SVC.stopping.wait(2):
            why = SVC.dead()
            if why:
                log(f"{why}: exiting so the platform restarts the service")
                exit_code[0] = 1
                httpd.shutdown()
                return

    def on_signal(*_):
        log("shutdown requested")
        SVC.stopping.set()
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    threading.Thread(target=supervise, daemon=True).start()
    log(f"status API on 0.0.0.0:{port} ({ENVIRONMENT_LABEL})")
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        SVC.stop()
        log("stopped")
    return exit_code[0]


if __name__ == "__main__":
    raise SystemExit(main())
