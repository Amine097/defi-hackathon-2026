// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {ERC20Mock} from "morpho-blue/src/mocks/ERC20Mock.sol";

/// @dev Takes a 1% fee on every transfer: the receiver gets less than the sender sent (Morpho does not support this).
contract FeeOnTransferToken is ERC20Mock {
    function transfer(address to, uint256 amount) public override returns (bool) {
        require(balanceOf[msg.sender] >= amount, "insufficient balance");
        uint256 fee = amount / 100;
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount - fee;
        totalSupply -= fee;
        emit Transfer(msg.sender, to, amount - fee);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) public override returns (bool) {
        require(allowance[from][msg.sender] >= amount, "insufficient allowance");
        require(balanceOf[from] >= amount, "insufficient balance");
        uint256 fee = amount / 100;
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount - fee;
        totalSupply -= fee;
        emit Transfer(from, to, amount - fee);
        return true;
    }
}

/// @dev Returns false instead of reverting (SafeERC20 must turn this into a revert).
contract FalseReturningToken is ERC20Mock {
    function transfer(address, uint256) public pure override returns (bool) {
        return false;
    }

    function transferFrom(address, address, uint256) public pure override returns (bool) {
        return false;
    }
}

/// @dev Calls back into `target` with `payload` during transferFrom and records how that inner call failed.
contract ReentrantToken is ERC20Mock {
    address public target;
    bytes public payload;
    bytes public lastRevert;
    bool public armed;

    function arm(address target_, bytes calldata payload_) external {
        target = target_;
        payload = payload_;
        armed = true;
    }

    function transferFrom(address from, address to, uint256 amount) public override returns (bool) {
        if (armed) {
            armed = false;
            (bool ok, bytes memory ret) = target.call(payload);
            require(!ok, "reentrant call unexpectedly succeeded");
            lastRevert = ret;
        }
        return super.transferFrom(from, to, amount);
    }
}
