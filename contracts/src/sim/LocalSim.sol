// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @notice LOCAL TEST TOKEN ONLY: anyone can mint. Used by the plain-Anvil end-to-end tests, never on a real network.
contract TestToken is ERC20 {
    uint8 private immutable _decimals;

    constructor(string memory name_, string memory symbol_, uint8 decimals_) ERC20(name_, symbol_) {
        _decimals = decimals_;
    }

    function decimals() public view override returns (uint8) {
        return _decimals;
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

/// @notice LOCAL TEST FEED ONLY: a Chainlink-style feed whose answer and update time are set by the test.
contract SimFeed {
    string public description;
    uint8 public immutable decimals;
    int256 public answer;
    uint256 public updatedAt;
    uint80 public roundId;

    constructor(string memory description_, uint8 decimals_, int256 answer_) {
        description = description_;
        decimals = decimals_;
        set(answer_, block.timestamp);
    }

    function set(int256 answer_, uint256 updatedAt_) public {
        answer = answer_;
        updatedAt = updatedAt_;
        roundId += 1;
    }

    function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80) {
        return (roundId, answer, updatedAt, updatedAt, roundId);
    }
}

interface IFeed {
    function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80);
}

/// @notice LOCAL TEST ORACLE ONLY, same getters and formula as Morpho's MorphoChainlinkOracleV2 (without vaults):
/// price = SCALE_FACTOR x BASE_FEED_1 x BASE_FEED_2 / (QUOTE_FEED_1 x QUOTE_FEED_2), zero-address feeds count as 1.
contract SimChainlinkOracle {
    address public immutable BASE_VAULT = address(0);
    address public immutable QUOTE_VAULT = address(0);
    address public immutable BASE_FEED_1;
    address public immutable BASE_FEED_2;
    address public immutable QUOTE_FEED_1;
    address public immutable QUOTE_FEED_2;
    uint256 public immutable SCALE_FACTOR;

    constructor(address baseFeed1, address baseFeed2, address quoteFeed1, address quoteFeed2, uint256 scaleFactor) {
        BASE_FEED_1 = baseFeed1;
        BASE_FEED_2 = baseFeed2;
        QUOTE_FEED_1 = quoteFeed1;
        QUOTE_FEED_2 = quoteFeed2;
        SCALE_FACTOR = scaleFactor;
    }

    function _get(address feed) internal view returns (uint256) {
        if (feed == address(0)) return 1;
        (, int256 a,,,) = IFeed(feed).latestRoundData();
        require(a >= 0, "negative answer");
        return uint256(a);
    }

    function price() external view returns (uint256) {
        return SCALE_FACTOR * _get(BASE_FEED_1) * _get(BASE_FEED_2) / (_get(QUOTE_FEED_1) * _get(QUOTE_FEED_2));
    }
}
