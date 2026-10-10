// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

import {IMorpho, Id, MarketParams, Market, Position} from "morpho-blue/src/interfaces/IMorpho.sol";
import {IOracle} from "morpho-blue/src/interfaces/IOracle.sol";
import {MarketParamsLib} from "morpho-blue/src/libraries/MarketParamsLib.sol";
import {SharesMathLib} from "morpho-blue/src/libraries/SharesMathLib.sol";
import {MathLib} from "morpho-blue/src/libraries/MathLib.sol";
import {ORACLE_PRICE_SCALE} from "morpho-blue/src/libraries/ConstantsLib.sol";

/// @title RescueVault - FAULTLINE Autonomous Countermove (Phase 2 hackathon prototype)
/// @notice A pre-funded, narrowly permissioned rescue reserve protecting ONE Morpho Blue borrower position.
/// Before a crisis the owner deposits loan tokens and/or the market's collateral token and sets a policy (allowed
/// strategies, per-action and cumulative caps, reserve floors, trigger LTV, expiry, cooldown). During a crisis a keeper
/// may ask the vault to (a) repay part of the debt, (b) supply collateral, or (c) repay the whole debt, ALWAYS on behalf
/// of the fixed beneficiary and ONLY through Morpho Blue `repay` / `supplyCollateral`, which need no Morpho
/// authorization. The keeper cannot move tokens anywhere else, borrow, withdraw collateral, change the beneficiary,
/// change the policy, bypass a cap or run arbitrary calldata: none of those code paths exist. Every constraint that can
/// be checked on-chain (risk trigger from Morpho's own oracle and accrued debt, caps, floors, expiry, nonce, replay,
/// cooldown, exact token movement, strict improvement of the position) is checked here, not trusted from the keeper.
/// @dev NOT AUDITED. Built and tested for a local Ethereum fork only; never deploy with real funds.
contract RescueVault is ReentrancyGuard {
    using SafeERC20 for IERC20;
    using MarketParamsLib for MarketParams;
    using SharesMathLib for uint256;
    using MathLib for uint256;

    uint8 public constant STRATEGY_REPAY = 1;
    uint8 public constant STRATEGY_TOP_UP = 2;
    uint8 public constant STRATEGY_FULL_REPAY = 4;
    uint8 internal constant ALL_STRATEGIES = 7;

    /// @notice Owner policy. LTVs are WAD (1e18 = 100%), amounts are raw token units.
    struct Policy {
        uint8 allowedStrategies; // bitmask of STRATEGY_*
        uint64 validUntil; // no keeper action after this timestamp
        uint32 cooldown; // minimum seconds between two keeper actions
        uint256 triggerLtv; // the keeper may act only if the on-chain LTV >= triggerLtv (< LLTV)
        uint256 minLtvAfter; // a partial action may not push the LTV below this floor (no over-spending)
        uint256 maxRepayPerAction; // loan tokens, partial repay
        uint256 maxTopUpPerAction; // collateral tokens
        uint256 maxFullRepay; // loan tokens, full debt close (0 = disabled)
        uint256 maxRepayTotal; // cumulative loan tokens spent under this policy (partial + full)
        uint256 maxTopUpTotal; // cumulative collateral locked under this policy
        uint256 minLoanReserve; // loan tokens that must stay in the vault after an action
        uint256 minCollateralReserve; // collateral tokens that must stay in the vault after an action
    }

    /// @notice Position read at one point of the transaction (debt includes interest accrued to this block).
    struct Snapshot {
        uint256 collateral;
        uint256 borrowShares;
        uint256 debt;
        uint256 price;
        uint256 collateralValue;
        uint256 ltv;
    }

    IMorpho public immutable MORPHO;
    address public immutable OWNER; // funds the reserve, sets the policy, receives withdrawn reserves
    address public immutable BENEFICIARY; // the protected Morpho borrower (onBehalf of every rescue)
    address public immutable LOAN_TOKEN;
    address public immutable COLLATERAL_TOKEN;
    address public immutable ORACLE;
    address public immutable IRM;
    uint256 public immutable LLTV;
    Id public immutable MARKET_ID;

    address public keeper;
    bool public paused;
    bool public revoked; // irreversible kill switch for automation (the owner can still withdraw)
    Policy internal _policy;
    uint256 public policyNonce; // bumped by every setPolicy: a plan made under an older policy cannot execute
    uint256 public repaidTotal; // under the current policy
    uint256 public toppedUpTotal; // under the current policy
    uint256 public lastActionAt;
    uint256 public actionCount;
    mapping(bytes32 actionId => bool) public actionUsed;

    event PolicySet(uint256 indexed nonce, Policy policy);
    event KeeperSet(address indexed keeper);
    event PausedSet(bool paused);
    event RevokedForever();
    event Deposited(address indexed token, uint256 amount);
    event ReserveWithdrawn(address indexed token, uint256 amount, address indexed to);
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

    error ZeroAddress();
    error MarketMismatch();
    error NotOwner();
    error NotKeeper();
    error IsPaused();
    error IsRevoked();
    error InvalidPolicy(string field);
    error StalePolicy(uint256 expected, uint256 current);
    error PolicyExpired(uint256 validUntil);
    error StrategyNotAllowed(uint8 strategy);
    error ActionAlreadyExecuted(bytes32 actionId);
    error CooldownActive(uint256 readyAt);
    error NoDebt();
    error NotAtRisk(uint256 ltv, uint256 triggerLtv);
    error ZeroAmount();
    error ExceedsPerActionCap(uint256 assets, uint256 cap);
    error ExceedsTotalCap(uint256 spentAfter, uint256 cap);
    error ExceedsDebt(uint256 assets, uint256 debt);
    error ExceedsKeeperBound(uint256 assets, uint256 bound);
    error ReserveFloor(uint256 balance, uint256 assets, uint256 floor);
    error UnsupportedToken(address token);
    error UnexpectedTokenMovement();
    error UnexpectedPositionChange();
    error NoImprovement(uint256 ltvBefore, uint256 ltvAfter);
    error LtvAboveBound(uint256 ltvAfter, uint256 bound);
    error LtvBelowFloor(uint256 ltvAfter, uint256 floor);

    modifier onlyOwner() {
        if (msg.sender != OWNER) revert NotOwner();
        _;
    }

    /// @param morpho Morpho Blue singleton.
    /// @param params The protected market; checked against Morpho's own registry (must exist, must match).
    /// @param beneficiary The borrower whose position is protected (fixed forever).
    /// @param keeper_ Initial keeper (may be zero: automation off until the owner sets one).
    constructor(IMorpho morpho, MarketParams memory params, address beneficiary, address keeper_) {
        if (address(morpho) == address(0) || beneficiary == address(0)) revert ZeroAddress();
        if (params.loanToken == address(0) || params.collateralToken == address(0)) revert ZeroAddress();
        Id id = params.id();
        MarketParams memory onchain = morpho.idToMarketParams(id);
        if (
            morpho.market(id).lastUpdate == 0 || onchain.loanToken != params.loanToken
                || onchain.collateralToken != params.collateralToken || onchain.oracle != params.oracle
                || onchain.irm != params.irm || onchain.lltv != params.lltv
        ) revert MarketMismatch();
        MORPHO = morpho;
        OWNER = msg.sender;
        BENEFICIARY = beneficiary;
        LOAN_TOKEN = params.loanToken;
        COLLATERAL_TOKEN = params.collateralToken;
        ORACLE = params.oracle;
        IRM = params.irm;
        LLTV = params.lltv;
        MARKET_ID = id;
        keeper = keeper_;
        emit KeeperSet(keeper_);
    }

    // ---- owner -------------------------------------------------------------------------------------------------

    function setPolicy(Policy calldata p) external onlyOwner {
        if (p.allowedStrategies == 0 || p.allowedStrategies & ~ALL_STRATEGIES != 0) revert InvalidPolicy("strategies");
        if (p.triggerLtv == 0 || p.triggerLtv >= LLTV) revert InvalidPolicy("triggerLtv");
        if (p.minLtvAfter >= p.triggerLtv) revert InvalidPolicy("minLtvAfter");
        if (p.validUntil <= block.timestamp) revert InvalidPolicy("validUntil");
        if (p.maxRepayPerAction > p.maxRepayTotal || p.maxFullRepay > p.maxRepayTotal) revert InvalidPolicy("repayCaps");
        if (p.maxTopUpPerAction > p.maxTopUpTotal) revert InvalidPolicy("topUpCaps");
        _policy = p;
        policyNonce += 1;
        repaidTotal = 0;
        toppedUpTotal = 0;
        emit PolicySet(policyNonce, p);
    }

    function setKeeper(address newKeeper) external onlyOwner {
        if (revoked) revert IsRevoked();
        keeper = newKeeper;
        emit KeeperSet(newKeeper);
    }

    function setPaused(bool newPaused) external onlyOwner {
        if (revoked && !newPaused) revert IsRevoked();
        paused = newPaused;
        emit PausedSet(newPaused);
    }

    /// @notice Irreversibly disables automation. Reserves stay withdrawable by the owner.
    function revoke() external onlyOwner {
        revoked = true;
        paused = true;
        keeper = address(0);
        emit KeeperSet(address(0));
        emit PausedSet(true);
        emit RevokedForever();
    }

    /// @notice Funds the reserve with the market's loan or collateral token (plain transfers work too).
    function deposit(address token, uint256 amount) external nonReentrant onlyOwner {
        if (token != LOAN_TOKEN && token != COLLATERAL_TOKEN) revert UnsupportedToken(token);
        uint256 before = IERC20(token).balanceOf(address(this));
        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);
        if (IERC20(token).balanceOf(address(this)) != before + amount) revert UnexpectedTokenMovement();
        emit Deposited(token, amount);
    }

    /// @notice Returns uncommitted reserves (any token) to the owner, and only to the owner, at any time.
    function withdrawReserve(address token, uint256 amount) external nonReentrant onlyOwner {
        IERC20(token).safeTransfer(OWNER, amount);
        emit ReserveWithdrawn(token, amount, OWNER);
    }

    // ---- keeper ------------------------------------------------------------------------------------------------

    /// @notice Repays `assets` of the beneficiary's debt from the reserve (partial: assets < accrued debt).
    /// @param maxLtvAfter The keeper's own bound: revert if the action no longer reaches the planned LTV.
    function executeRepay(bytes32 actionId, uint256 assets, uint256 expectedPolicyNonce, uint256 maxLtvAfter)
        external
        nonReentrant
    {
        Snapshot memory s0 = _preflight(STRATEGY_REPAY, actionId, expectedPolicyNonce);
        Policy memory p = _policy;
        if (assets == 0) revert ZeroAmount();
        if (assets > p.maxRepayPerAction) revert ExceedsPerActionCap(assets, p.maxRepayPerAction);
        if (repaidTotal + assets > p.maxRepayTotal) revert ExceedsTotalCap(repaidTotal + assets, p.maxRepayTotal);
        if (assets >= s0.debt) revert ExceedsDebt(assets, s0.debt);
        repaidTotal += assets;

        _pull(LOAN_TOKEN, assets, p.minLoanReserve, STRATEGY_REPAY, 0);

        Snapshot memory s1 = _snapshot();
        if (s1.collateral != s0.collateral || s1.debt >= s0.debt) revert UnexpectedPositionChange();
        _checkPartialOutcome(s0, s1, maxLtvAfter, p.minLtvAfter);
        _record(actionId, STRATEGY_REPAY, assets, s0, s1);
    }

    /// @notice Supplies `assets` of the market's collateral token from the reserve to the beneficiary's position.
    function executeTopUp(bytes32 actionId, uint256 assets, uint256 expectedPolicyNonce, uint256 maxLtvAfter)
        external
        nonReentrant
    {
        Snapshot memory s0 = _preflight(STRATEGY_TOP_UP, actionId, expectedPolicyNonce);
        Policy memory p = _policy;
        if (assets == 0) revert ZeroAmount();
        if (assets > p.maxTopUpPerAction) revert ExceedsPerActionCap(assets, p.maxTopUpPerAction);
        if (toppedUpTotal + assets > p.maxTopUpTotal) revert ExceedsTotalCap(toppedUpTotal + assets, p.maxTopUpTotal);
        toppedUpTotal += assets;

        _pull(COLLATERAL_TOKEN, assets, p.minCollateralReserve, STRATEGY_TOP_UP, 0);

        Snapshot memory s1 = _snapshot();
        if (s1.collateral != s0.collateral + assets || s1.borrowShares != s0.borrowShares) {
            revert UnexpectedPositionChange();
        }
        _checkPartialOutcome(s0, s1, maxLtvAfter, p.minLtvAfter);
        _record(actionId, STRATEGY_TOP_UP, assets, s0, s1);
    }

    /// @notice Repays ALL of the beneficiary's borrow shares (debt incl. interest accrued to this block). Collateral
    /// stays in the position: this removes borrowing liquidation risk, it does not sell or withdraw collateral.
    /// @param maxAssets The keeper's bound on the loan tokens this may take (interest / plan drift guard).
    function executeFullRepay(bytes32 actionId, uint256 maxAssets, uint256 expectedPolicyNonce) external nonReentrant {
        Snapshot memory s0 = _preflight(STRATEGY_FULL_REPAY, actionId, expectedPolicyNonce);
        Policy memory p = _policy;
        uint256 needed = s0.debt; // = toAssetsUp(borrowShares) on totals accrued in this block: what repay(shares) pulls
        if (needed > maxAssets) revert ExceedsKeeperBound(needed, maxAssets);
        if (needed > p.maxFullRepay) revert ExceedsPerActionCap(needed, p.maxFullRepay);
        if (repaidTotal + needed > p.maxRepayTotal) revert ExceedsTotalCap(repaidTotal + needed, p.maxRepayTotal);
        repaidTotal += needed;

        _pull(LOAN_TOKEN, needed, p.minLoanReserve, STRATEGY_FULL_REPAY, s0.borrowShares);

        Snapshot memory s1 = _snapshot();
        if (s1.borrowShares != 0 || s1.collateral != s0.collateral) revert UnexpectedPositionChange();
        _record(actionId, STRATEGY_FULL_REPAY, needed, s0, s1);
    }

    // ---- views -------------------------------------------------------------------------------------------------

    function policy() external view returns (Policy memory) {
        return _policy;
    }

    function marketParams() public view returns (MarketParams memory) {
        return MarketParams(LOAN_TOKEN, COLLATERAL_TOKEN, ORACLE, IRM, LLTV);
    }

    /// @notice Position at the last Morpho interest accrual (off-chain readers accrue interest themselves).
    function positionState() external view returns (Snapshot memory) {
        return _snapshot();
    }

    // ---- internals ---------------------------------------------------------------------------------------------

    function _preflight(uint8 strategy, bytes32 actionId, uint256 expectedPolicyNonce)
        internal
        returns (Snapshot memory s)
    {
        if (msg.sender != keeper || msg.sender == address(0)) revert NotKeeper();
        if (revoked) revert IsRevoked();
        if (paused) revert IsPaused();
        if (expectedPolicyNonce != policyNonce) revert StalePolicy(expectedPolicyNonce, policyNonce);
        Policy memory p = _policy;
        if (block.timestamp > p.validUntil) revert PolicyExpired(p.validUntil);
        if (p.allowedStrategies & strategy == 0) revert StrategyNotAllowed(strategy);
        if (actionUsed[actionId]) revert ActionAlreadyExecuted(actionId);
        if (lastActionAt != 0 && block.timestamp < lastActionAt + p.cooldown) {
            revert CooldownActive(lastActionAt + p.cooldown);
        }
        actionUsed[actionId] = true; // rolled back with the whole call if anything below reverts

        MORPHO.accrueInterest(marketParams()); // debt read below includes interest up to this block
        s = _snapshot();
        if (s.borrowShares == 0) revert NoDebt();
        if (s.ltv < p.triggerLtv) revert NotAtRisk(s.ltv, p.triggerLtv);
    }

    /// @dev Moves exactly `assets` of `token` from this vault into Morpho for the beneficiary and checks both balances,
    /// so fee-on-transfer / rebasing surprises revert instead of silently mis-accounting. Allowance is reset to 0.
    function _pull(address token, uint256 assets, uint256 floor, uint8 strategy, uint256 shares) internal {
        uint256 vaultBefore = IERC20(token).balanceOf(address(this));
        if (vaultBefore < assets + floor) revert ReserveFloor(vaultBefore, assets, floor);
        uint256 morphoBefore = IERC20(token).balanceOf(address(MORPHO));

        IERC20(token).forceApprove(address(MORPHO), assets);
        if (strategy == STRATEGY_TOP_UP) {
            MORPHO.supplyCollateral(marketParams(), assets, BENEFICIARY, "");
        } else if (strategy == STRATEGY_REPAY) {
            (uint256 repaid,) = MORPHO.repay(marketParams(), assets, 0, BENEFICIARY, "");
            if (repaid != assets) revert UnexpectedTokenMovement();
        } else {
            (uint256 repaid, uint256 repaidShares) = MORPHO.repay(marketParams(), 0, shares, BENEFICIARY, "");
            if (repaid != assets || repaidShares != shares) revert UnexpectedTokenMovement();
        }
        IERC20(token).forceApprove(address(MORPHO), 0);

        if (IERC20(token).balanceOf(address(this)) + assets != vaultBefore) revert UnexpectedTokenMovement();
        if (IERC20(token).balanceOf(address(MORPHO)) != morphoBefore + assets) revert UnexpectedTokenMovement();
    }

    function _checkPartialOutcome(Snapshot memory s0, Snapshot memory s1, uint256 maxLtvAfter, uint256 floor)
        internal
        pure
    {
        if (s1.ltv >= s0.ltv) revert NoImprovement(s0.ltv, s1.ltv);
        if (s1.ltv > maxLtvAfter) revert LtvAboveBound(s1.ltv, maxLtvAfter);
        if (s1.ltv < floor) revert LtvBelowFloor(s1.ltv, floor);
    }

    function _record(bytes32 actionId, uint8 strategy, uint256 assets, Snapshot memory s0, Snapshot memory s1)
        internal
    {
        lastActionAt = block.timestamp;
        actionCount += 1;
        emit RescueExecuted(
            actionId, strategy, assets, s0.debt, s1.debt, s0.collateral, s1.collateral, s0.ltv, s1.ltv, policyNonce
        );
    }

    function _snapshot() internal view returns (Snapshot memory s) {
        Position memory pos = MORPHO.position(MARKET_ID, BENEFICIARY);
        Market memory m = MORPHO.market(MARKET_ID);
        s.collateral = pos.collateral;
        s.borrowShares = pos.borrowShares;
        s.debt = s.borrowShares.toAssetsUp(m.totalBorrowAssets, m.totalBorrowShares);
        s.price = IOracle(ORACLE).price();
        s.collateralValue = s.collateral.mulDivDown(s.price, ORACLE_PRICE_SCALE);
        if (s.debt == 0) s.ltv = 0;
        else if (s.collateralValue == 0) s.ltv = type(uint256).max;
        else s.ltv = s.debt.wDivUp(s.collateralValue);
    }
}
