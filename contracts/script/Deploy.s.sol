// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Script, console2} from "forge-std/Script.sol";
import {ValtoDEX} from "../src/ValtoDEX.sol";

/// Deploys ValtoDEX. The signer comes from the command line (--ledger, --trezor or
/// --interactive); never put a private key in a file or environment variable.
///
///   forge script script/Deploy.s.sol --rpc-url arc_testnet --broadcast --interactive
///   forge script script/Deploy.s.sol --rpc-url arc_mainnet --broadcast --ledger
contract Deploy is Script {
    function run() external returns (ValtoDEX dex) {
        uint256 chainId = block.chainid;
        require(chainId == 5042 || chainId == 5042002 || chainId == 31337, "not an Arc network");
        vm.startBroadcast();
        dex = new ValtoDEX();
        vm.stopBroadcast();
        console2.log("ValtoDEX deployed at", address(dex));
        console2.log("chain id", chainId);
        console2.log("Next: set NETWORKS.%s.dex in index.html to this address", chainId == 5042 ? "mainnet" : "testnet");
    }
}
