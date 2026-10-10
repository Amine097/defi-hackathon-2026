// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {IMorpho, MarketParams, Id, Position} from "morpho-blue/src/interfaces/IMorpho.sol";
import {MarketParamsLib} from "morpho-blue/src/libraries/MarketParamsLib.sol";
import {MathLib} from "morpho-blue/src/libraries/MathLib.sol";
import {SharesMathLib} from "morpho-blue/src/libraries/SharesMathLib.sol";
import {ORACLE_PRICE_SCALE} from "morpho-blue/src/libraries/ConstantsLib.sol";
import {ERC20Mock} from "morpho-blue/src/mocks/ERC20Mock.sol";
import {OracleMock} from "morpho-blue/src/mocks/OracleMock.sol";
import {IrmMock} from "morpho-blue/src/mocks/IrmMock.sol";
import {RescueVault} from "../src/RescueVault.sol";

/// Shared fixture: the REAL Morpho Blue v1.0.0 code (deployed from the pinned sources), a mock oracle / IRM / tokens,
/// one borrower at 80% LTV (LLTV 86%) and a funded RescueVault with a conservative policy.
abstract contract RescueVaultBase is Test {
    using MarketParamsLib for MarketParams;
    using MathLib for uint256;
    using SharesMathLib for uint256;

    IMorpho internal morpho;
    ERC20Mock internal loan;
    ERC20Mock internal coll;
    OracleMock internal oracle;
    IrmMock internal irm;
    MarketParams internal params;
    Id internal id;
    RescueVault internal vault;
    uint256 internal policyNonceMirror; // tracked locally: an external read inside call args would consume vm.prank

    address internal owner = makeAddr("owner"); // protected borrower, vault owner and beneficiary
    address internal keeper = makeAddr("keeper");
    address internal attacker = makeAddr("attacker");
    address internal lp = makeAddr("lp");

    uint256 internal constant LLTV = 0.86e18;
    uint256 internal constant PRICE = 2000e36; // 1e18 collateral raw = 2,000e18 loan raw
    uint256 internal constant TRIGGER = 0.82e18;

    function setUp() public virtual {
        morpho = IMorpho(deployCode("Morpho.sol:Morpho", abi.encode(address(this))));
        loan = new ERC20Mock();
        coll = new ERC20Mock();
        oracle = new OracleMock();
        irm = new IrmMock();
        oracle.setPrice(PRICE);
        morpho.enableIrm(address(irm));
        morpho.enableLltv(LLTV);
        params = MarketParams(address(loan), address(coll), address(oracle), address(irm), LLTV);
        morpho.createMarket(params);
        id = params.id();

        loan.setBalance(lp, 1_000_000e18);
        vm.startPrank(lp);
        loan.approve(address(morpho), type(uint256).max);
        morpho.supply(params, 1_000_000e18, 0, lp, "");
        vm.stopPrank();

        coll.setBalance(owner, 15e18);
        vm.startPrank(owner);
        coll.approve(address(morpho), type(uint256).max);
        morpho.supplyCollateral(params, 10e18, owner, ""); // 10 x 2,000 = 20,000 of collateral value
        morpho.borrow(params, 16_000e18, 0, owner, owner); // LTV 80%
        vault = new RescueVault(morpho, params, owner, keeper);
        loan.setBalance(owner, loan.balanceOf(owner) + 5_000e18);
        loan.approve(address(vault), type(uint256).max);
        coll.approve(address(vault), type(uint256).max);
        vault.deposit(address(loan), 5_000e18);
        vault.deposit(address(coll), 5e18);
        vault.setPolicy(_policy());
        vm.stopPrank();
        policyNonceMirror = 1;
    }

    function _policy() internal view returns (RescueVault.Policy memory) {
        return RescueVault.Policy({
            allowedStrategies: 7,
            validUntil: uint64(block.timestamp + 30 days),
            cooldown: 1 hours,
            triggerLtv: TRIGGER,
            minLtvAfter: 0.5e18,
            maxRepayPerAction: 3_000e18,
            maxTopUpPerAction: 3e18,
            maxFullRepay: 20_000e18,
            maxRepayTotal: 20_000e18,
            maxTopUpTotal: 4e18,
            minLoanReserve: 100e18,
            minCollateralReserve: 0.1e18
        });
    }

    function _setPolicy(RescueVault.Policy memory p) internal {
        vm.prank(owner);
        vault.setPolicy(p);
        policyNonceMirror += 1;
        assertEq(vault.policyNonce(), policyNonceMirror);
    }

    function _shock(uint256 bps) internal {
        oracle.setPrice(PRICE * (10_000 - bps) / 10_000);
    }

    function _nonce() internal view returns (uint256) {
        return policyNonceMirror;
    }

    function _ltv() internal view returns (uint256) {
        return vault.positionState().ltv;
    }

    function _healthy() internal view returns (bool) {
        Position memory p = morpho.position(id, owner);
        (,, uint128 tba, uint128 tbs,,) = _market();
        uint256 debt = uint256(p.borrowShares).toAssetsUp(tba, tbs);
        uint256 maxBorrow = uint256(p.collateral).mulDivDown(oracle.price(), ORACLE_PRICE_SCALE).wMulDown(LLTV);
        return maxBorrow >= debt;
    }

    function _market() internal view returns (uint128, uint128, uint128, uint128, uint128, uint128) {
        (bool ok, bytes memory ret) = address(morpho).staticcall(abi.encodeWithSignature("market(bytes32)", id));
        require(ok, "market read");
        return abi.decode(ret, (uint128, uint128, uint128, uint128, uint128, uint128));
    }
}

contract RescueVaultTest is RescueVaultBase {
    event RescueExecuted(
        bytes32 indexed actionId,
        uint8 indexed strategy,
        uint256 assets,
        uint256 debtBefore,
        uint256 debtAfter,
        uint256 collateralBefore,
        uint256 collateralAfter,
        uint256 ltvBefore,
        uint256 ltvAfter,
        uint256 policyNonce
    );

    // ---- the three mandatory outcomes ------------------------------------------------------------------------

    function test_autoRepay_reducesDebt_improvesLtv() public {
        _shock(500); // SIMULATED -5% oracle move: LTV 16,000 / 19,000 = 84.2% >= trigger 82%
        RescueVault.Snapshot memory s0 = vault.positionState();
        assertGe(s0.ltv, TRIGGER);
        uint256 bal0 = loan.balanceOf(address(vault));
        vm.expectEmit(true, true, false, false, address(vault));
        emit RescueExecuted(keccak256("repay-1"), 1, 0, 0, 0, 0, 0, 0, 0, 0);
        vm.prank(keeper);
        vault.executeRepay(keccak256("repay-1"), 2_000e18, _nonce(), 0.75e18);
        RescueVault.Snapshot memory s1 = vault.positionState();
        assertApproxEqAbs(s0.debt - s1.debt, 2_000e18, 2, "debt reduced by the repaid amount");
        assertEq(s1.collateral, s0.collateral, "collateral untouched");
        assertLt(s1.ltv, s0.ltv);
        assertApproxEqAbs(s1.ltv, uint256(14_000e18) * 1e18 / 19_000e18, 1e10);
        assertEq(bal0 - loan.balanceOf(address(vault)), 2_000e18, "exactly the planned amount left the reserve");
        assertEq(vault.repaidTotal(), 2_000e18);
        assertTrue(vault.actionUsed(keccak256("repay-1")));
        assertEq(vault.actionCount(), 1);
        assertTrue(_healthy());
    }

    function test_autoTopUp_addsCollateral_debtUnchanged() public {
        _shock(500);
        RescueVault.Snapshot memory s0 = vault.positionState();
        uint256 bal0 = coll.balanceOf(address(vault));
        vm.prank(keeper);
        vault.executeTopUp(keccak256("topup-1"), 1e18, _nonce(), 0.80e18);
        RescueVault.Snapshot memory s1 = vault.positionState();
        assertEq(s1.collateral, s0.collateral + 1e18, "collateral added");
        assertEq(s1.borrowShares, s0.borrowShares, "debt unchanged");
        assertEq(s1.debt, s0.debt);
        assertApproxEqAbs(s1.ltv, uint256(16_000e18) * 1e18 / 20_900e18, 1e10); // 16,000 / (11 x 1,900)
        assertEq(bal0 - coll.balanceOf(address(vault)), 1e18);
        assertEq(vault.toppedUpTotal(), 1e18);
    }

    function test_hold_whenNotAtRisk_noTokenMoves() public {
        uint256 l0 = loan.balanceOf(address(vault));
        vm.prank(keeper);
        vm.expectPartialRevert(RescueVault.NotAtRisk.selector);
        vault.executeRepay(keccak256("x"), 1_000e18, _nonce(), 1e18);
        assertEq(loan.balanceOf(address(vault)), l0);
    }

    function test_emergencyFullRepay_closesDebt_keepsCollateral() public {
        vm.prank(owner);
        vault.deposit(address(loan), 12_000e18);
        _shock(500);
        RescueVault.Snapshot memory s0 = vault.positionState();
        vm.prank(keeper);
        vault.executeFullRepay(keccak256("full-1"), s0.debt + 1e18, _nonce());
        RescueVault.Snapshot memory s1 = vault.positionState();
        assertEq(s1.borrowShares, 0, "no debt left");
        assertEq(s1.debt, 0);
        assertEq(s1.ltv, 0);
        assertEq(s1.collateral, s0.collateral, "collateral is NOT withdrawn or sold");
        assertEq(vault.repaidTotal(), s0.debt);
    }

    // ---- permissions -----------------------------------------------------------------------------------------

    function test_onlyKeeperCanExecute() public {
        _shock(500);
        address[3] memory who = [owner, attacker, address(this)];
        for (uint256 i; i < who.length; i++) {
            vm.startPrank(who[i]);
            vm.expectRevert(RescueVault.NotKeeper.selector);
            vault.executeRepay(keccak256("a"), 1_000e18, 1, 1e18);
            vm.expectRevert(RescueVault.NotKeeper.selector);
            vault.executeTopUp(keccak256("a"), 1e18, 1, 1e18);
            vm.expectRevert(RescueVault.NotKeeper.selector);
            vault.executeFullRepay(keccak256("a"), 1e30, 1);
            vm.stopPrank();
        }
    }

    function test_onlyOwnerAdministers() public {
        address[2] memory who = [keeper, attacker];
        for (uint256 i; i < who.length; i++) {
            vm.startPrank(who[i]);
            vm.expectRevert(RescueVault.NotOwner.selector);
            vault.setPolicy(_policy());
            vm.expectRevert(RescueVault.NotOwner.selector);
            vault.setKeeper(who[i]);
            vm.expectRevert(RescueVault.NotOwner.selector);
            vault.setPaused(false);
            vm.expectRevert(RescueVault.NotOwner.selector);
            vault.revoke();
            vm.expectRevert(RescueVault.NotOwner.selector);
            vault.withdrawReserve(address(loan), 1);
            vm.expectRevert(RescueVault.NotOwner.selector);
            vault.deposit(address(loan), 1);
            vm.stopPrank();
        }
    }

    function test_noArbitraryCallsNoEth() public {
        bytes[] memory payloads = new bytes[](6);
        payloads[0] = abi.encodeWithSignature("transfer(address,uint256)", attacker, 1_000e18);
        payloads[1] = abi.encodeWithSignature("approve(address,uint256)", attacker, type(uint256).max);
        payloads[2] = abi.encodeWithSignature(
            "execute(address,bytes)", address(loan), abi.encodeWithSignature("transfer(address,uint256)", attacker, 1)
        );
        payloads[3] = abi.encodeWithSignature("multicall(bytes[])", new bytes[](0));
        payloads[4] = abi.encodeWithSignature("borrow(uint256,address)", 1_000e18, attacker);
        payloads[5] = abi.encodeWithSignature("withdrawCollateral(uint256,address)", 1e18, attacker);
        for (uint256 i; i < payloads.length; i++) {
            vm.prank(keeper);
            (bool ok,) = address(vault).call(payloads[i]);
            assertFalse(ok);
        }
        vm.deal(keeper, 1 ether);
        vm.prank(keeper);
        (bool sent,) = address(vault).call{value: 1 ether}("");
        assertFalse(sent, "no receive / fallback");
    }

    /// A keeper key compromised mid-crisis tries every lever. Nothing leaves the policy envelope.
    function test_maliciousKeeper_cannotSpendOutsidePolicy() public {
        vm.prank(owner);
        morpho.setAuthorization(address(vault), true); // worst case: the borrower even authorized the vault on Morpho
        uint256 l0 = loan.balanceOf(address(vault));
        uint256 c0 = coll.balanceOf(address(vault));
        Position memory p0 = morpho.position(id, owner);
        uint256 n = _nonce();

        vm.startPrank(keeper);
        // the position is healthy: no spending allowed at all
        vm.expectPartialRevert(RescueVault.NotAtRisk.selector);
        vault.executeRepay(keccak256("m1"), 1_000e18, n, 1e18);
        vm.stopPrank();

        _shock(500); // now at risk
        vm.startPrank(keeper);
        vm.expectPartialRevert(RescueVault.ExceedsPerActionCap.selector);
        vault.executeRepay(keccak256("m2"), 3_000e18 + 1, n, 1e18);
        vm.expectPartialRevert(RescueVault.ExceedsPerActionCap.selector);
        vault.executeTopUp(keccak256("m3"), 3e18 + 1, n, 1e18);
        vm.expectPartialRevert(RescueVault.StalePolicy.selector);
        vault.executeRepay(keccak256("m4"), 1_000e18, n + 1, 1e18);
        vm.expectPartialRevert(RescueVault.ReserveFloor.selector); // try to drain the reserve with a "full repay"
        vault.executeFullRepay(keccak256("m5"), type(uint256).max, n);
        vm.expectRevert(RescueVault.NotOwner.selector);
        vault.withdrawReserve(address(loan), l0);
        vm.expectRevert(RescueVault.NotOwner.selector);
        vault.setPolicy(_policy());
        vm.expectRevert(RescueVault.NotOwner.selector);
        vault.setKeeper(attacker);
        (bool ok,) = address(vault).call(abi.encodeWithSignature("transfer(address,uint256)", keeper, l0));
        assertFalse(ok);
        vm.stopPrank();

        // a legitimate-looking action passes once, then replay / cooldown / trigger stop any repetition
        vm.prank(keeper);
        vault.executeRepay(keccak256("ok"), 1_000e18, n, 1e18);
        vm.startPrank(keeper);
        vm.expectPartialRevert(RescueVault.ActionAlreadyExecuted.selector);
        vault.executeRepay(keccak256("ok"), 1_000e18, n, 1e18);
        vm.expectPartialRevert(RescueVault.CooldownActive.selector);
        vault.executeRepay(keccak256("again"), 1_000e18, n, 1e18);
        vm.warp(block.timestamp + 1 hours);
        vm.expectPartialRevert(RescueVault.NotAtRisk.selector); // LTV 15,000 / 19,000 = 78.9% < trigger
        vault.executeRepay(keccak256("again"), 1_000e18, n, 1e18);
        vm.stopPrank();

        assertEq(l0 - loan.balanceOf(address(vault)), 1_000e18, "only the one in-policy action spent");
        assertEq(coll.balanceOf(address(vault)), c0);
        assertEq(loan.balanceOf(keeper) + coll.balanceOf(keeper) + loan.balanceOf(attacker), 0, "keeper gained nothing");
        Position memory p1 = morpho.position(id, owner);
        assertLe(p1.borrowShares, p0.borrowShares, "debt never increased (no borrow path)");
        assertGe(p1.collateral, p0.collateral, "collateral never decreased (no withdraw path)");
        Position memory pv = morpho.position(id, address(vault));
        assertEq(pv.supplyShares + pv.borrowShares + pv.collateral, 0, "vault holds no Morpho position of its own");
    }

    // ---- policy limits ---------------------------------------------------------------------------------------

    function test_cumulativeCap_acrossActions() public {
        RescueVault.Policy memory p = _policy();
        p.maxRepayTotal = 4_000e18;
        p.maxFullRepay = 4_000e18;
        _setPolicy(p);
        _shock(500);
        vm.prank(keeper);
        vault.executeRepay(keccak256("c1"), 3_000e18, _nonce(), 1e18);
        _shock(2_500); // a second, deeper SIMULATED leg: 13,000 / 15,000 = 86.7%
        vm.warp(block.timestamp + 1 hours);
        vm.prank(keeper);
        vm.expectPartialRevert(RescueVault.ExceedsTotalCap.selector);
        vault.executeRepay(keccak256("c2"), 1_500e18, _nonce(), 1e18);
        vm.prank(keeper);
        vault.executeRepay(keccak256("c3"), 1_000e18, _nonce(), 1e18); // exactly up to the cap
        assertEq(vault.repaidTotal(), 4_000e18);
    }

    function test_reserveFloor() public {
        RescueVault.Policy memory p = _policy();
        p.minLoanReserve = 4_500e18;
        _setPolicy(p);
        _shock(500);
        vm.prank(keeper);
        vm.expectPartialRevert(RescueVault.ReserveFloor.selector);
        vault.executeRepay(keccak256("f"), 600e18, _nonce(), 1e18);
        vm.prank(keeper);
        vault.executeRepay(keccak256("f2"), 500e18, _nonce(), 1e18); // leaves exactly the floor
        assertEq(loan.balanceOf(address(vault)), 4_500e18);
    }

    function test_insufficientReserve() public {
        RescueVault.Policy memory p = _policy();
        p.maxRepayPerAction = 10_000e18;
        p.minLoanReserve = 0;
        _setPolicy(p);
        _shock(500);
        vm.prank(keeper);
        vm.expectPartialRevert(RescueVault.ReserveFloor.selector);
        vault.executeRepay(keccak256("i"), 5_000e18 + 1, _nonce(), 1e18);
    }

    function test_expiry_pause_strategy() public {
        _shock(500);
        RescueVault.Policy memory p = _policy();
        p.allowedStrategies = 1; // REPAY only
        _setPolicy(p);
        uint256 n = _nonce();
        vm.prank(keeper);
        vm.expectRevert(abi.encodeWithSelector(RescueVault.StrategyNotAllowed.selector, uint8(2)));
        vault.executeTopUp(keccak256("s"), 1e18, n, 1e18);
        vm.prank(owner);
        vault.setPaused(true);
        vm.prank(keeper);
        vm.expectRevert(RescueVault.IsPaused.selector);
        vault.executeRepay(keccak256("s"), 1_000e18, n, 1e18);
        vm.prank(owner);
        vault.setPaused(false);
        vm.warp(block.timestamp + 31 days);
        vm.prank(keeper);
        vm.expectPartialRevert(RescueVault.PolicyExpired.selector);
        vault.executeRepay(keccak256("s"), 1_000e18, n, 1e18);
    }

    function test_noPolicy_noAction() public {
        RescueVault fresh = new RescueVault(morpho, params, owner, keeper);
        _shock(500);
        vm.prank(keeper);
        vm.expectPartialRevert(RescueVault.PolicyExpired.selector); // validUntil = 0 until the owner sets a policy
        fresh.executeRepay(keccak256("n"), 1, 0, 1e18);
    }

    function test_policyChange_invalidatesPendingPlan_andResetsBudget() public {
        _shock(500);
        uint256 planned = _nonce();
        vm.prank(keeper);
        vault.executeRepay(keccak256("p1"), 500e18, planned, 1e18);
        assertEq(vault.repaidTotal(), 500e18);
        _setPolicy(_policy()); // owner edits the policy while the keeper holds an old plan
        vm.warp(block.timestamp + 1 hours);
        vm.prank(keeper);
        vm.expectRevert(abi.encodeWithSelector(RescueVault.StalePolicy.selector, planned, planned + 1));
        vault.executeRepay(keccak256("p2"), 500e18, planned, 1e18);
        assertEq(vault.repaidTotal(), 0, "a new policy is a new budget");
    }

    function test_revoke_isIrreversible_ownerStillRecoversReserves() public {
        _shock(500);
        vm.startPrank(owner);
        vault.revoke();
        vm.expectRevert(RescueVault.IsRevoked.selector);
        vault.setKeeper(keeper);
        vm.expectRevert(RescueVault.IsRevoked.selector);
        vault.setPaused(false);
        vm.stopPrank();
        vm.prank(keeper);
        vm.expectRevert(RescueVault.NotKeeper.selector);
        vault.executeRepay(keccak256("r"), 1_000e18, _nonce(), 1e18);
        uint256 before = loan.balanceOf(owner);
        vm.prank(owner);
        vault.withdrawReserve(address(loan), 5_000e18);
        assertEq(loan.balanceOf(owner) - before, 5_000e18, "reserves go back to the owner only");
        assertEq(loan.balanceOf(address(vault)), 0);
    }

    function test_ltvFloor_and_keeperBound() public {
        RescueVault.Policy memory p = _policy();
        p.minLtvAfter = 0.79e18;
        _setPolicy(p);
        _shock(500);
        vm.prank(keeper);
        vm.expectPartialRevert(RescueVault.LtvBelowFloor.selector); // 14,000 / 19,000 = 73.7% < 79%
        vault.executeRepay(keccak256("l"), 2_000e18, _nonce(), 1e18);
        vm.prank(keeper);
        vm.expectPartialRevert(RescueVault.LtvAboveBound.selector); // plan promised <= 79.5%, reality 81.1%
        vault.executeRepay(keccak256("l2"), 600e18, _nonce(), 0.795e18);
    }

    function test_partialRepay_cannotExceedDebt_fullRepayBounds() public {
        RescueVault.Policy memory p = _policy();
        p.maxRepayPerAction = 20_000e18;
        p.minLtvAfter = 0;
        _setPolicy(p);
        vm.prank(owner);
        vault.deposit(address(loan), 15_000e18);
        _shock(500);
        RescueVault.Snapshot memory s0 = vault.positionState();
        vm.startPrank(keeper);
        vm.expectPartialRevert(RescueVault.ExceedsDebt.selector);
        vault.executeRepay(keccak256("d"), s0.debt, _nonce(), 1e18);
        vm.expectPartialRevert(RescueVault.ExceedsKeeperBound.selector);
        vault.executeFullRepay(keccak256("d2"), s0.debt - 1, _nonce());
        vm.stopPrank();
        RescueVault.Policy memory q = _policy();
        q.maxFullRepay = 10_000e18;
        _setPolicy(q);
        vm.prank(keeper);
        vm.expectPartialRevert(RescueVault.ExceedsPerActionCap.selector);
        vault.executeFullRepay(keccak256("d3"), 1e30, _nonce());
    }

    function test_interestAccrued_isIncludedOnChain() public {
        RescueVault.Policy memory p = _policy();
        p.validUntil = uint64(block.timestamp + 400 days);
        _setPolicy(p);
        vm.prank(owner);
        vault.deposit(address(loan), 15_000e18);
        vm.warp(block.timestamp + 365 days); // interest accrues (IRM mock ~1.6% APR at this utilisation)
        _shock(500);
        RescueVault.Snapshot memory stale = vault.positionState(); // last accrual: one year ago
        vm.prank(keeper);
        vault.executeFullRepay(keccak256("y"), 17_000e18, _nonce());
        uint256 repaid = vault.repaidTotal();
        assertGt(repaid, stale.debt, "the full repay paid the interest accrued in the last year");
        assertEq(vault.positionState().borrowShares, 0);
    }

    function test_invalidPolicies() public {
        RescueVault.Policy memory p;
        string[6] memory fields = ["strategies", "triggerLtv", "minLtvAfter", "validUntil", "repayCaps", "topUpCaps"];
        for (uint256 i; i < fields.length; i++) {
            p = _policy();
            if (i == 0) p.allowedStrategies = 8;
            if (i == 1) p.triggerLtv = LLTV;
            if (i == 2) p.minLtvAfter = p.triggerLtv;
            if (i == 3) p.validUntil = uint64(block.timestamp);
            if (i == 4) p.maxRepayPerAction = p.maxRepayTotal + 1;
            if (i == 5) p.maxTopUpPerAction = p.maxTopUpTotal + 1;
            vm.prank(owner);
            vm.expectRevert(abi.encodeWithSelector(RescueVault.InvalidPolicy.selector, fields[i]));
            vault.setPolicy(p);
        }
    }

    function test_constructor_rejectsUnknownMarket() public {
        MarketParams memory wrong = params;
        wrong.lltv = 0.5e18;
        vm.expectRevert(RescueVault.MarketMismatch.selector);
        new RescueVault(morpho, wrong, owner, keeper);
        vm.expectRevert(RescueVault.ZeroAddress.selector);
        new RescueVault(morpho, params, address(0), keeper);
    }

    function test_depositOnlyMarketTokens() public {
        ERC20Mock other = new ERC20Mock();
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(RescueVault.UnsupportedToken.selector, address(other)));
        vault.deposit(address(other), 1);
    }

    // ---- fuzzing ---------------------------------------------------------------------------------------------

    /// Any amount, any (bounded) SIMULATED shock: either the action respects every bound, or nothing moves.
    function testFuzz_repay_respectsPolicyOrRevertsCleanly(uint256 assets, uint256 shockBps, uint256 bound_) public {
        shockBps = bound(shockBps, 0, 3_000);
        assets = bound(assets, 0, 12_000e18);
        bound_ = bound(bound_, 0.3e18, 1.2e18);
        _shock(shockBps);
        RescueVault.Snapshot memory s0 = vault.positionState();
        uint256 b0 = loan.balanceOf(address(vault));
        vm.prank(keeper);
        try vault.executeRepay(keccak256(abi.encode(assets, shockBps)), assets, 1, bound_) {
            RescueVault.Snapshot memory s1 = vault.positionState();
            assertGe(s0.ltv, TRIGGER, "acted only at risk");
            assertTrue(assets > 0 && assets <= 3_000e18 && assets < s0.debt);
            assertEq(b0 - loan.balanceOf(address(vault)), assets);
            assertGe(loan.balanceOf(address(vault)), 100e18, "reserve floor kept");
            assertLt(s1.ltv, s0.ltv);
            assertLe(s1.ltv, bound_);
            assertGe(s1.ltv, 0.5e18);
        } catch {
            assertEq(loan.balanceOf(address(vault)), b0, "a refused action moves nothing");
            assertEq(vault.positionState().borrowShares, s0.borrowShares);
        }
    }

    function testFuzz_topUp_respectsPolicyOrRevertsCleanly(uint256 assets, uint256 shockBps) public {
        shockBps = bound(shockBps, 0, 3_000);
        assets = bound(assets, 0, 6e18);
        _shock(shockBps);
        RescueVault.Snapshot memory s0 = vault.positionState();
        uint256 b0 = coll.balanceOf(address(vault));
        vm.prank(keeper);
        try vault.executeTopUp(keccak256(abi.encode(assets, shockBps)), assets, 1, 1e18) {
            RescueVault.Snapshot memory s1 = vault.positionState();
            assertGe(s0.ltv, TRIGGER);
            assertTrue(assets > 0 && assets <= 3e18);
            assertEq(s1.collateral, s0.collateral + assets);
            assertEq(s1.borrowShares, s0.borrowShares);
            assertGe(coll.balanceOf(address(vault)), 0.1e18);
        } catch {
            assertEq(coll.balanceOf(address(vault)), b0);
            assertEq(vault.positionState().collateral, s0.collateral);
        }
    }

    /// The vault's LTV agrees with Morpho Blue's own health check (liquidatable <=> LTV > LLTV), up to rounding.
    function testFuzz_ltvAgreesWithMorphoHealth(uint256 shockBps) public {
        shockBps = bound(shockBps, 0, 9_000);
        _shock(shockBps);
        uint256 ltv = _ltv();
        if (ltv + 1e9 < LLTV) assertTrue(_healthy());
        if (ltv > LLTV + 1e9) assertFalse(_healthy());
    }
}
