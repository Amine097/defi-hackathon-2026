// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {IMorpho, MarketParams, Id, Position} from "morpho-blue/src/interfaces/IMorpho.sol";
import {ERC20Mock} from "morpho-blue/src/mocks/ERC20Mock.sol";
import {OracleMock} from "morpho-blue/src/mocks/OracleMock.sol";
import {RescueVault} from "../src/RescueVault.sol";
import {RescueVaultBase} from "./RescueVault.t.sol";

/// Random sequences of keeper actions, SIMULATED price moves, time, owner funding / withdrawals / policy resets and
/// attacker calls. Ghost accounting records every token that enters or leaves the vault and where it went.
contract Handler is Test {
    RescueVault internal vault;
    IMorpho internal morpho;
    ERC20Mock internal loan;
    ERC20Mock internal coll;
    OracleMock internal oracle;
    Id internal id;
    address internal owner;
    address internal keeper;
    address internal attacker;
    uint256 internal basePrice;

    uint256 public loanIn;
    uint256 public collIn;
    uint256 public loanToMorpho;
    uint256 public collToMorpho;
    uint256 public loanOut;
    uint256 public collOut;
    uint256 public successes;
    bool public floorViolated;
    bool public breach;
    bool public debtIncreased;
    bool public collateralDecreased;
    uint256 internal seq;
    uint256 internal l0;
    uint256 internal c0;
    uint256 internal ml0;
    uint256 internal mc0;
    uint256 internal bs0;
    uint256 internal col0;

    constructor(RescueVault v, IMorpho m, OracleMock o, Id i, address kp, address att) {
        (vault, morpho, oracle, id, keeper, attacker) = (v, m, o, i, kp, att);
        loan = ERC20Mock(v.LOAN_TOKEN());
        coll = ERC20Mock(v.COLLATERAL_TOKEN());
        owner = v.OWNER();
        basePrice = o.price();
    }

    function _pos() internal view returns (Position memory) {
        return morpho.position(id, owner);
    }

    function _before() internal {
        (l0, c0) = (loan.balanceOf(address(vault)), coll.balanceOf(address(vault)));
        (ml0, mc0) = (loan.balanceOf(address(morpho)), coll.balanceOf(address(morpho)));
        Position memory p = _pos();
        (bs0, col0) = (p.borrowShares, p.collateral);
    }

    function _afterKeeper() internal {
        uint256 dl = l0 - loan.balanceOf(address(vault));
        uint256 dc = c0 - coll.balanceOf(address(vault));
        if (loan.balanceOf(address(morpho)) - ml0 != dl || coll.balanceOf(address(morpho)) - mc0 != dc) breach = true;
        loanToMorpho += dl;
        collToMorpho += dc;
        successes += 1;
        RescueVault.Policy memory p = vault.policy();
        if (dl > 0 && loan.balanceOf(address(vault)) < p.minLoanReserve) floorViolated = true;
        if (dc > 0 && coll.balanceOf(address(vault)) < p.minCollateralReserve) floorViolated = true;
        Position memory p1 = _pos();
        if (p1.borrowShares > bs0) debtIncreased = true;
        if (p1.collateral < col0) collateralDecreased = true;
    }

    function keeperRepay(uint256 assets, uint256 bound_) external {
        assets = bound(assets, 0, 8_000e18);
        bound_ = bound(bound_, 0.3e18, 1.5e18);
        _before();
        uint256 n = vault.policyNonce();
        vm.prank(keeper);
        vault.executeRepay(keccak256(abi.encode("r", ++seq)), assets, n, bound_); // a refused action reverts the whole handler call
        _afterKeeper();
    }

    function keeperTopUp(uint256 assets, uint256 bound_) external {
        assets = bound(assets, 0, 6e18);
        bound_ = bound(bound_, 0.3e18, 1.5e18);
        _before();
        uint256 n = vault.policyNonce();
        vm.prank(keeper);
        vault.executeTopUp(keccak256(abi.encode("t", ++seq)), assets, n, bound_);
        _afterKeeper();
    }

    function keeperFullRepay(uint256 maxAssets) external {
        maxAssets = bound(maxAssets, 0, 40_000e18);
        _before();
        uint256 n = vault.policyNonce();
        vm.prank(keeper);
        vault.executeFullRepay(keccak256(abi.encode("f", ++seq)), maxAssets, n);
        _afterKeeper();
    }

    function movePrice(uint256 bps) external {
        bps = bound(bps, 5_000, 12_000); // SIMULATED oracle between -50% and +20%
        oracle.setPrice(basePrice * bps / 10_000);
    }

    function warp(uint256 s) external {
        vm.warp(block.timestamp + bound(s, 1, 2 hours));
    }

    function ownerDeposit(uint256 amount, bool isLoan) external {
        ERC20Mock t = isLoan ? loan : coll;
        amount = bound(amount, 1, isLoan ? 20_000e18 : 3e18);
        t.setBalance(owner, t.balanceOf(owner) + amount);
        vm.startPrank(owner);
        t.approve(address(vault), amount);
        vault.deposit(address(t), amount);
        vm.stopPrank();
        if (isLoan) loanIn += amount;
        else collIn += amount;
    }

    function ownerWithdraw(uint256 amount, bool isLoan) external {
        ERC20Mock t = isLoan ? loan : coll;
        amount = bound(amount, 0, t.balanceOf(address(vault)));
        uint256 before = t.balanceOf(owner);
        vm.prank(owner);
        vault.withdrawReserve(address(t), amount);
        if (t.balanceOf(owner) - before != amount) breach = true;
        if (isLoan) loanOut += amount;
        else collOut += amount;
    }

    function ownerResetPolicy(uint256 hoursValid) external {
        RescueVault.Policy memory p = vault.policy();
        p.validUntil = uint64(block.timestamp + bound(hoursValid, 1, 720) * 1 hours);
        vm.prank(owner);
        vault.setPolicy(p);
    }

    function attackerTries(uint256 which, bool asKeeper) external {
        address who = asKeeper ? keeper : attacker;
        which = bound(which, 0, 6);
        bytes memory payload;
        if (which == 0) payload = abi.encodeCall(RescueVault.withdrawReserve, (address(loan), 1));
        else if (which == 1) payload = abi.encodeCall(RescueVault.setKeeper, (who));
        else if (which == 2) payload = abi.encodeCall(RescueVault.setPaused, (false));
        else if (which == 3) payload = abi.encodeWithSignature("transfer(address,uint256)", who, 1);
        else if (which == 4) payload = abi.encodeWithSignature("execute(address,bytes)", address(loan), "");
        else if (which == 5) payload = abi.encodeCall(RescueVault.setPolicy, (vault.policy()));
        else payload = abi.encodeCall(RescueVault.deposit, (address(loan), 0));
        vm.prank(who);
        (bool ok,) = address(vault).call(payload);
        if (ok) breach = true;
    }
}

contract RescueVaultInvariantTest is RescueVaultBase {
    Handler internal handler;
    uint256 internal loan0;
    uint256 internal coll0;
    Position internal p0;

    function setUp() public override {
        super.setUp();
        handler = new Handler(vault, morpho, oracle, id, keeper, attacker);
        loan0 = loan.balanceOf(address(vault));
        coll0 = coll.balanceOf(address(vault));
        p0 = morpho.position(id, owner);
        targetContract(address(handler));
    }

    /// Every token that left the vault went to Morpho (for the beneficiary) or back to the owner. Nothing else.
    function invariant_tokenConservation() public view {
        assertEq(loan.balanceOf(address(vault)), loan0 + handler.loanIn() - handler.loanToMorpho() - handler.loanOut());
        assertEq(coll.balanceOf(address(vault)), coll0 + handler.collIn() - handler.collToMorpho() - handler.collOut());
    }

    function invariant_capsNeverExceeded() public view {
        RescueVault.Policy memory p = vault.policy();
        assertLe(vault.repaidTotal(), p.maxRepayTotal);
        assertLe(vault.toppedUpTotal(), p.maxTopUpTotal);
    }

    function invariant_noBorrowNoCollateralWithdrawal() public view {
        Position memory p = morpho.position(id, owner);
        assertLe(p.borrowShares, p0.borrowShares, "debt shares never grow");
        assertGe(p.collateral, p0.collateral, "collateral never shrinks");
        assertFalse(handler.debtIncreased());
        assertFalse(handler.collateralDecreased());
    }

    function invariant_noPrivilegeEscalation() public view {
        assertFalse(handler.breach(), "an unauthorised call succeeded or tokens went elsewhere");
        assertFalse(handler.floorViolated(), "a keeper action left less than the reserve floor");
        assertEq(loan.balanceOf(attacker) + coll.balanceOf(attacker) + loan.balanceOf(keeper) + coll.balanceOf(keeper), 0);
        Position memory pv = morpho.position(id, address(vault));
        assertEq(pv.supplyShares + pv.borrowShares + pv.collateral, 0);
        assertEq(vault.keeper(), keeper);
    }
}
