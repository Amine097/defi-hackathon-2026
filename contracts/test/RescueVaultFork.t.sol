// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IMorpho, MarketParams, Id, Position} from "morpho-blue/src/interfaces/IMorpho.sol";
import {IOracle} from "morpho-blue/src/interfaces/IOracle.sol";
import {RescueVault} from "../src/RescueVault.sol";

/// Integration against the REAL Morpho Blue deployment and the REAL cbBTC/USDC market (oracle = Chainlink BTC/USD) on
/// an Ethereum mainnet fork pinned at a block. Test funds come from `deal`; the price move is a SIMULATED shock
/// (`vm.mockCall` on the market oracle). Nothing is sent to mainnet. Run:
///   FORK_RPC_URL=https://... forge test --match-contract Fork
contract RescueVaultForkTest is Test {
    IMorpho internal constant MORPHO = IMorpho(0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb);
    Id internal constant CBBTC_USDC = Id.wrap(0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64);
    uint256 internal constant FORK_BLOCK = 26164248;

    MarketParams internal mp;
    RescueVault internal vault;
    address internal borrower = makeAddr("fork-borrower");
    address internal keeper = makeAddr("fork-keeper");
    uint256 internal price0;
    bool internal enabled;

    function setUp() public {
        string memory url = vm.envOr("FORK_RPC_URL", string(""));
        enabled = bytes(url).length != 0;
        if (!enabled) return;
        vm.createSelectFork(url, FORK_BLOCK);
        mp = MORPHO.idToMarketParams(CBBTC_USDC);
        price0 = IOracle(mp.oracle).price();
        deal(mp.collateralToken, borrower, 1e8); // 1 cbBTC (8 decimals), test funds on the fork
        vm.startPrank(borrower);
        IERC20(mp.collateralToken).approve(address(MORPHO), type(uint256).max);
        MORPHO.supplyCollateral(mp, 1e8, borrower, "");
        uint256 value = 1e8 * price0 / 1e36; // USDC raw
        MORPHO.borrow(mp, value * 80 / 100, 0, borrower, borrower); // LTV 80% (LLTV 86%)
        vault = new RescueVault(MORPHO, mp, borrower, keeper);
        vm.stopPrank();
        deal(mp.loanToken, address(vault), value * 30 / 100);
        deal(mp.collateralToken, address(vault), 0.3e8);
        RescueVault.Policy memory p = RescueVault.Policy({
            allowedStrategies: 7,
            validUntil: uint64(block.timestamp + 7 days),
            cooldown: 10 minutes,
            triggerLtv: 0.82e18,
            minLtvAfter: 0.5e18,
            maxRepayPerAction: value * 25 / 100,
            maxTopUpPerAction: 0.25e8,
            maxFullRepay: value,
            maxRepayTotal: value,
            maxTopUpTotal: 0.3e8,
            minLoanReserve: 10e6,
            minCollateralReserve: 0.001e8
        });
        vm.prank(borrower);
        vault.setPolicy(p);
    }

    function _shock(uint256 bps) internal {
        vm.mockCall(mp.oracle, abi.encodeWithSelector(IOracle.price.selector), abi.encode(price0 * (10_000 - bps) / 10_000));
    }

    function test_fork_realMorpho_repayAndTopUp() public {
        vm.skip(!enabled, "set FORK_RPC_URL to run against the real Morpho Blue market");
        assertEq(mp.lltv, 0.86e18, "real market LLTV");
        uint256 ltvHealthy = vault.positionState().ltv;
        assertApproxEqAbs(ltvHealthy, 0.8e18, 1e15);
        vm.prank(keeper);
        vm.expectPartialRevert(RescueVault.NotAtRisk.selector);
        vault.executeRepay(keccak256("fork-0"), 1e6, 1, 1e18);

        _shock(500); // SIMULATED BTC/USD -5%
        RescueVault.Snapshot memory s0 = vault.positionState();
        assertGe(s0.ltv, 0.82e18);
        uint256 r = s0.debt / 10;
        vm.prank(keeper);
        vault.executeRepay(keccak256("fork-1"), r, 1, 0.80e18);
        RescueVault.Snapshot memory s1 = vault.positionState();
        assertApproxEqAbs(s0.debt - s1.debt, r, 2);
        assertLt(s1.ltv, s0.ltv);

        _shock(1_500); // deeper SIMULATED leg
        vm.warp(block.timestamp + 10 minutes);
        RescueVault.Snapshot memory s2 = vault.positionState();
        assertGe(s2.ltv, 0.82e18);
        vm.prank(keeper);
        vault.executeTopUp(keccak256("fork-2"), 0.2e8, 1, 0.80e18);
        RescueVault.Snapshot memory s3 = vault.positionState();
        assertEq(s3.collateral, s2.collateral + 0.2e8);
        assertEq(s3.borrowShares, s2.borrowShares);
        assertLt(s3.ltv, s2.ltv);
        Position memory pv = MORPHO.position(CBBTC_USDC, address(vault));
        assertEq(pv.supplyShares + pv.borrowShares + pv.collateral, 0);
    }
}
