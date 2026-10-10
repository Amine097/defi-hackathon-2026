// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/// @title ShockFeed - LOCAL FORK SIMULATION TOOL ONLY (never deploy to a real network)
/// @notice Replaces the code of a real Chainlink-style feed on an Anvil fork (anvil_setCode) to apply a controlled,
/// clearly labelled price shock: answer = baseAnswer x (10_000 - shockBps) / 10_000. Every oracle that reads the feed
/// (exactly like in a real crisis of that dependency) sees the shocked value. `description()` says it is simulated.
/// Storage is written with anvil_setStorageAt: slot 0 baseAnswer, 1 shockBps, 2 decimals, 3 roundId, 4 timestampMode
/// (0 = report updatedAt 0 like an exchange-rate adapter, 1 = report the current block time).
contract ShockFeed {
    int256 public baseAnswer;
    uint256 public shockBps;
    uint8 public decimals;
    uint256 public roundId;
    uint256 public timestampMode;

    function description() external pure returns (string memory) {
        return "FAULTLINE SIMULATED SHOCK (local fork only)";
    }

    function version() external pure returns (uint256) {
        return 4;
    }

    function latestAnswer() public view returns (int256) {
        return baseAnswer * int256(10_000 - shockBps) / 10_000;
    }

    function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80) {
        uint256 t = timestampMode == 1 ? block.timestamp : 0;
        return (uint80(roundId), latestAnswer(), t, t, uint80(roundId));
    }
}
