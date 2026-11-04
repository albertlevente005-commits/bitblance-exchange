// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// Plain ERC-20 (6 decimals, like USDC/EURC)
contract MockERC20 {
    string public name;
    string public symbol;
    uint8 public constant decimals = 6;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    constructor(string memory n, string memory s) { name = n; symbol = s; }

    function mint(address to, uint256 a) external { balanceOf[to] += a; totalSupply += a; }
    function approve(address s, uint256 a) external returns (bool) { allowance[msg.sender][s] = a; return true; }
    function transfer(address to, uint256 a) external virtual returns (bool) { _move(msg.sender, to, a); return true; }
    function transferFrom(address f, address to, uint256 a) external virtual returns (bool) {
        allowance[f][msg.sender] -= a; _move(f, to, a); return true;
    }
    function _move(address f, address to, uint256 a) internal virtual { balanceOf[f] -= a; balanceOf[to] += a; }
}

/// Takes a 1% fee on every transfer
contract FeeToken is MockERC20 {
    constructor() MockERC20("Fee", "FEE") {}
    function _move(address f, address to, uint256 a) internal override {
        uint256 fee = a / 100; balanceOf[f] -= a; balanceOf[to] += a - fee; totalSupply -= fee;
    }
}

/// USDT-style: transfer/transferFrom return nothing
contract NoReturnToken {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    function mint(address to, uint256 a) external { balanceOf[to] += a; }
    function approve(address s, uint256 a) external { allowance[msg.sender][s] = a; }
    function transfer(address to, uint256 a) external { balanceOf[msg.sender] -= a; balanceOf[to] += a; }
    function transferFrom(address f, address to, uint256 a) external {
        allowance[f][msg.sender] -= a; balanceOf[f] -= a; balanceOf[to] += a;
    }
}

/// Reports success but moves nothing
contract LyingToken is MockERC20 {
    constructor() MockERC20("Lie", "LIE") {}
    function transfer(address, uint256) external pure override returns (bool) { return true; }
    function transferFrom(address, address, uint256) external pure override returns (bool) { return true; }
}

interface IReenterTarget { function swap(uint256, address, uint256, uint256) external returns (uint256); }

/// Calls back into the DEX during transfer (reentrancy attempt)
contract ReentrantToken is MockERC20 {
    address public target; bool public armed; bytes public lastRevert;
    constructor() MockERC20("Re", "RE") {}
    function arm(address t) external { target = t; armed = true; }
    function _move(address f, address to, uint256 a) internal override {
        super._move(f, to, a);
        if (armed) {
            armed = false;
            (bool ok, bytes memory err) = target.call(abi.encodeCall(IReenterTarget.swap, (0, address(this), 1, 0)));
            require(!ok, "reentry succeeded");
            lastRevert = err;
        }
    }
}
