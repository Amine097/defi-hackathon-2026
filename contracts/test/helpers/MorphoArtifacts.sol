// SPDX-License-Identifier: MIT
pragma solidity 0.8.19;

// Compiles the official Morpho Blue v1.0.0 sources (exact pragma 0.8.19) so tests can deploy the REAL protocol code
// locally with `deployCode("Morpho.sol:Morpho", ...)` instead of a hand-written mock.
import {Morpho} from "morpho-blue/src/Morpho.sol";
