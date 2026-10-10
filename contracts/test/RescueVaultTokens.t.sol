// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {MarketParams, Id, Position} from "morpho-blue/src/interfaces/IMorpho.sol";
import {MarketParamsLib} from "morpho-blue/src/libraries/MarketParamsLib.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ERC20Mock} from "morpho-blue/src/mocks/ERC20Mock.sol";
import {OracleMock} from "morpho-blue/src/mocks/OracleMock.sol";
import {RescueVault} from "../src/RescueVault.sol";
import {RescueVaultBase} from "./RescueVault.t.sol";
import {FeeOnTransferToken, FalseReturningToken, ReentrantToken} from "./helpers/WeirdTokens.sol";

/// Unexpected token behaviour and unit scaling (decimals / oracle scale) on the real Morpho Blue code.
contract RescueVaultTokensTest is RescueVaultBase {
    using MarketParamsLib for MarketParams;

    function _market(address loanToken, address collToken, address oracle_) internal returns (MarketParams memory mp) {
        mp = MarketParams(loanToken, collToken, oracle_, address(irm), LLTV);
        morpho.createMarket(mp);
        ERC20Mock(loanToken).setBalance(lp, 1_000_000e18);
        vm.startPrank(lp);
        ERC20Mock(loanToken).approve(address(morpho), type(uint256).max);
        morpho.supply(mp, 1_000_000e18, 0, lp, "");
        vm.stopPrank();
    }

    function test_feeOnTransferCollateral_isRefused() public {
        FeeOnTransferToken fot = new FeeOnTransferToken();
        MarketParams memory mp = _market(address(loan), address(fot), address(oracle));
        fot.setBalance(owner, 20e18);
        vm.startPrank(owner);
        fot.approve(address(morpho), type(uint256).max);
        morpho.supplyCollateral(mp, 10e18, owner, "");
        morpho.borrow(mp, 16_000e18, 0, owner, owner);
        RescueVault v = new RescueVault(morpho, mp, owner, keeper);
        fot.approve(address(v), type(uint256).max);
        vm.expectRevert(RescueVault.UnexpectedTokenMovement.selector); // deposit sees 0.99 instead of 1
        v.deposit(address(fot), 1e18);
        fot.transfer(address(v), 3e18); // plain transfer still funds it (2.97 received)
        v.setPolicy(_policy());
        vm.stopPrank();
        _shock(500);
        uint256 b0 = fot.balanceOf(address(v));
        vm.prank(keeper);
        vm.expectRevert(RescueVault.UnexpectedTokenMovement.selector); // Morpho would receive 0.99 for 1 credited
        v.executeTopUp(keccak256("fot"), 1e18, 1, 1e18);
        assertEq(fot.balanceOf(address(v)), b0);
    }

    function test_falseReturningToken_isRefused() public {
        FalseReturningToken bad = new FalseReturningToken();
        bad.setBalance(address(vault), 1e18);
        vm.prank(owner);
        vm.expectPartialRevert(SafeERC20.SafeERC20FailedOperation.selector);
        vault.withdrawReserve(address(bad), 1e18);
    }

    function test_reentrancyThroughTokenHook_isBlocked() public {
        ReentrantToken rt = new ReentrantToken();
        MarketParams memory mp = _market(address(rt), address(coll), address(oracle));
        coll.setBalance(owner, 10e18);
        vm.startPrank(owner);
        coll.approve(address(morpho), type(uint256).max);
        morpho.supplyCollateral(mp, 10e18, owner, "");
        morpho.borrow(mp, 16_000e18, 0, owner, owner);
        RescueVault v = new RescueVault(morpho, mp, owner, keeper);
        rt.setBalance(owner, rt.balanceOf(owner) + 5_000e18);
        rt.approve(address(v), type(uint256).max);
        v.deposit(address(rt), 5_000e18);
        v.setPolicy(_policy());
        vm.stopPrank();
        _shock(500);
        // during Morpho's transferFrom(vault -> Morpho) the token re-enters the vault to spend again
        rt.arm(address(v), abi.encodeCall(RescueVault.executeRepay, (keccak256("inner"), 1_000e18, 1, 1e18)));
        vm.prank(keeper);
        v.executeRepay(keccak256("outer"), 1_000e18, 1, 1e18);
        assertEq(bytes4(rt.lastRevert()), ReentrancyGuard.ReentrancyGuardReentrantCall.selector);
        assertEq(v.repaidTotal(), 1_000e18, "only the outer action spent");
        assertFalse(v.actionUsed(keccak256("inner")));
    }

    /// USDC-like 6-decimal loan token, WBTC/cbBTC-like 8-decimal collateral, BTC at 80,000: 1e8 raw collateral is worth
    /// 80,000e6 raw loan units, so the Morpho oracle price is 80,000e6 * 1e36 / 1e8 = 8e38.
    function test_decimals_6_loan_8_collateral() public {
        ERC20Mock usdc = new ERC20Mock();
        ERC20Mock btc = new ERC20Mock();
        OracleMock o = new OracleMock();
        o.setPrice(80_000e6 * 1e36 / 1e8);
        MarketParams memory mp = _market(address(usdc), address(btc), address(o));
        btc.setBalance(owner, 2e8);
        vm.startPrank(owner);
        btc.approve(address(morpho), type(uint256).max);
        morpho.supplyCollateral(mp, 1e8, owner, "");
        morpho.borrow(mp, 64_000e6, 0, owner, owner); // LTV 80%
        RescueVault v = new RescueVault(morpho, mp, owner, keeper);
        usdc.setBalance(owner, usdc.balanceOf(owner) + 20_000e6);
        usdc.approve(address(v), type(uint256).max);
        btc.approve(address(v), type(uint256).max);
        v.deposit(address(usdc), 20_000e6);
        v.deposit(address(btc), 0.5e8);
        RescueVault.Policy memory p = _policy();
        p.maxRepayPerAction = 15_000e6;
        p.maxRepayTotal = 20_000e6;
        p.maxFullRepay = 20_000e6;
        p.maxTopUpPerAction = 0.3e8;
        p.maxTopUpTotal = 0.4e8;
        p.minLoanReserve = 100e6;
        p.minCollateralReserve = 0.01e8;
        v.setPolicy(p);
        vm.stopPrank();
        o.setPrice(76_000e6 * 1e36 / 1e8); // SIMULATED -5%
        RescueVault.Snapshot memory s0 = v.positionState();
        assertApproxEqAbs(s0.ltv, uint256(64_000e6) * 1e18 / 76_000e6, 1e6);
        vm.prank(keeper);
        v.executeRepay(keccak256("r6"), 10_000e6, 1, 0.75e18);
        RescueVault.Snapshot memory s1 = v.positionState();
        assertApproxEqAbs(s1.ltv, uint256(54_000e6) * 1e18 / 76_000e6, 1e6); // 71.05%
        o.setPrice(64_000e6 * 1e36 / 1e8); // SIMULATED second leg: 54,000 / 64,000 = 84.4% >= trigger
        vm.warp(block.timestamp + 1 hours);
        vm.prank(keeper);
        v.executeTopUp(keccak256("t8"), 0.1e8, 1, 0.80e18);
        RescueVault.Snapshot memory s2 = v.positionState();
        assertEq(s2.collateral, 1.1e8);
        assertApproxEqAbs(s2.ltv, uint256(54_000e6) * 1e18 / 70_400e6, 1e6); // 76.7%
    }
}
