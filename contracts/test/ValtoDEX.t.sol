// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test} from "forge-std/Test.sol";
import {ValtoDEX} from "../src/ValtoDEX.sol";
import {MockERC20, FeeToken, NoReturnToken, LyingToken, ReentrantToken} from "./mocks/Tokens.sol";

contract ValtoDEXTest is Test {
    ValtoDEX dex;
    MockERC20 usdc;
    MockERC20 eurc;
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");

    function setUp() public {
        dex = new ValtoDEX();
        usdc = new MockERC20("USD Coin", "USDC");
        eurc = new MockERC20("Euro Coin", "EURC");
        for (uint256 i; i < 2; i++) {
            address u = i == 0 ? alice : bob;
            usdc.mint(u, 1e15);
            eurc.mint(u, 1e15);
            vm.startPrank(u);
            usdc.approve(address(dex), type(uint256).max);
            eurc.approve(address(dex), type(uint256).max);
            vm.stopPrank();
        }
    }

    function _seed(uint256 a, uint256 b) internal returns (uint256 id) {
        id = dex.createPool(address(usdc), address(eurc));
        vm.prank(alice);
        dex.addLiquidity(id, a, b);
    }

    function _pool(uint256 id) internal view returns (address tA, address tB, uint256 rA, uint256 rB, uint256 ts) {
        return dex.pools(id);
    }

    // ---------------------------------------------------------------- front-end compatibility

    function test_SelectorsMatchFrontend() public pure {
        assertEq(bytes4(keccak256("poolCount()")), bytes4(0xf525cb68));
        assertEq(bytes4(keccak256("pools(uint256)")), bytes4(0xac4afa38));
        assertEq(bytes4(keccak256("getQuote(uint256,address,uint256)")), bytes4(0x9c8e3085));
        assertEq(bytes4(keccak256("swap(uint256,address,uint256,uint256)")), bytes4(0xb33daea9));
        assertEq(bytes4(keccak256("createPool(address,address)")), bytes4(0xe3433615));
        assertEq(bytes4(keccak256("addLiquidity(uint256,uint256,uint256)")), bytes4(0x422f1043));
        assertEq(ValtoDEX.poolCount.selector, bytes4(0xf525cb68));
        assertEq(ValtoDEX.getQuote.selector, bytes4(0x9c8e3085));
        assertEq(ValtoDEX.swap.selector, bytes4(0xb33daea9));
        assertEq(ValtoDEX.createPool.selector, bytes4(0xe3433615));
    }

    /// The front-end reads pools(i) as raw words: [tokenA, tokenB, reserveA, reserveB]
    function test_PoolsGetterWordLayout() public {
        uint256 id = _seed(10e6, 9.2e6);
        (bool ok, bytes memory raw) = address(dex).staticcall(abi.encodeWithSelector(0xac4afa38, id));
        assertTrue(ok);
        (address a, address b, uint256 rA, uint256 rB) = abi.decode(raw, (address, address, uint256, uint256));
        assertEq(a, address(usdc));
        assertEq(b, address(eurc));
        assertEq(rA, 10e6);
        assertEq(rB, 9.2e6);
    }

    // ---------------------------------------------------------------- createPool

    function test_CreatePool() public {
        assertEq(dex.poolCount(), 0);
        uint256 id = dex.createPool(address(usdc), address(eurc));
        assertEq(id, 0);
        assertEq(dex.poolCount(), 1);
        (bool exists, uint256 pid) = dex.getPoolId(address(eurc), address(usdc));
        assertTrue(exists);
        assertEq(pid, 0);
    }

    function test_RevertWhen_DuplicatePairEitherOrder() public {
        dex.createPool(address(usdc), address(eurc));
        vm.expectRevert(abi.encodeWithSelector(ValtoDEX.PoolExists.selector, 0));
        dex.createPool(address(eurc), address(usdc));
    }

    function test_RevertWhen_BadTokens() public {
        vm.expectRevert(ValtoDEX.IdenticalTokens.selector);
        dex.createPool(address(usdc), address(usdc));
        vm.expectRevert(ValtoDEX.ZeroAddress.selector);
        dex.createPool(address(0), address(usdc));
        vm.expectRevert(ValtoDEX.InvalidToken.selector);
        dex.createPool(address(usdc), makeAddr("not-a-token"));
    }

    // ---------------------------------------------------------------- liquidity

    function test_FirstDepositLocksMinimumLiquidity() public {
        uint256 id = _seed(10e6, 9.2e6);
        uint256 root = 9591663; // floor(sqrt(10e6 * 9.2e6))
        assertEq(dex.shares(id, alice), root - 1000);
        assertEq(dex.shares(id, address(0)), 1000);
        (,,,, uint256 ts) = _pool(id);
        assertEq(ts, root);
    }

    function test_AddLiquidityPullsOnlyRatioAmounts() public {
        uint256 id = _seed(10e6, 5e6); // 2:1
        uint256 bobUsdc = usdc.balanceOf(bob);
        uint256 bobEurc = eurc.balanceOf(bob);
        vm.prank(bob);
        dex.addLiquidity(id, 4e6, 10e6); // too much EURC offered
        assertEq(bobUsdc - usdc.balanceOf(bob), 4e6);
        assertEq(bobEurc - eurc.balanceOf(bob), 2e6); // only what matches the ratio
        (,, uint256 rA, uint256 rB,) = _pool(id);
        assertEq(rA, 14e6);
        assertEq(rB, 7e6);
    }

    function test_RevertWhen_MinSharesNotMet() public {
        uint256 id = _seed(10e6, 10e6);
        vm.prank(bob);
        vm.expectRevert(ValtoDEX.SlippageExceeded.selector);
        dex.addLiquidity(id, 1e6, 1e6, 2e6);
    }

    function test_RemoveLiquidityReturnsProportional() public {
        uint256 id = _seed(10e6, 10e6);
        vm.prank(bob);
        uint256 s = dex.addLiquidity(id, 5e6, 5e6);
        uint256 u0 = usdc.balanceOf(bob);
        uint256 e0 = eurc.balanceOf(bob);
        vm.prank(bob);
        (uint256 a, uint256 b) = dex.removeLiquidity(id, s, 0, 0);
        assertApproxEqAbs(a, 5e6, 1);
        assertApproxEqAbs(b, 5e6, 1);
        assertEq(usdc.balanceOf(bob) - u0, a);
        assertEq(eurc.balanceOf(bob) - e0, b);
        assertEq(dex.shares(id, bob), 0);
    }

    function test_RevertWhen_RemoveMoreThanOwned() public {
        uint256 id = _seed(10e6, 10e6);
        vm.prank(bob);
        vm.expectRevert(ValtoDEX.InsufficientShares.selector);
        dex.removeLiquidity(id, 1, 0, 0);
    }

    function test_RevertWhen_RemoveBelowMinimums() public {
        uint256 id = _seed(10e6, 10e6);
        uint256 s = dex.shares(id, alice);
        vm.prank(alice);
        vm.expectRevert(ValtoDEX.SlippageExceeded.selector);
        dex.removeLiquidity(id, s, 10e6, 0);
    }

    function test_LpEarnsSwapFees() public {
        uint256 id = _seed(100e6, 100e6);
        for (uint256 i; i < 10; i++) {
            vm.startPrank(bob);
            dex.swap(id, address(usdc), 10e6, 0);
            dex.swap(id, address(eurc), dex.getQuote(id, address(usdc), 10e6), 0);
            vm.stopPrank();
        }
        uint256 s = dex.shares(id, alice);
        vm.prank(alice);
        (uint256 a, uint256 b) = dex.removeLiquidity(id, s, 0, 0);
        assertGt(a + b, 200e6 - 2000); // more than deposited minus locked dust
    }

    // ---------------------------------------------------------------- swap

    function test_SwapMatchesQuote() public {
        uint256 id = _seed(1_000e6, 920e6);
        uint256 q = dex.getQuote(id, address(usdc), 10e6);
        uint256 e0 = eurc.balanceOf(bob);
        vm.prank(bob);
        uint256 out = dex.swap(id, address(usdc), 10e6, q);
        assertEq(out, q);
        assertEq(eurc.balanceOf(bob) - e0, q);
        // x*y=k with 0.30% fee: 10 * 0.997 * 920 / (1000 + 9.97)
        assertEq(q, 9_081_853);
    }

    function test_RevertWhen_SlippageExceeded() public {
        uint256 id = _seed(1_000e6, 920e6);
        uint256 q = dex.getQuote(id, address(usdc), 10e6);
        vm.prank(bob);
        vm.expectRevert(ValtoDEX.SlippageExceeded.selector);
        dex.swap(id, address(usdc), 10e6, q + 1);
    }

    function test_RevertWhen_FrontRunMovesPrice() public {
        uint256 id = _seed(1_000e6, 1_000e6);
        uint256 q = dex.getQuote(id, address(usdc), 10e6);
        uint256 minOut = q * 9950 / 10000; // 0.5% slippage, as the front-end computes it
        vm.prank(alice);
        dex.swap(id, address(usdc), 50e6, 0); // attacker moves the price first
        vm.prank(bob);
        vm.expectRevert(ValtoDEX.SlippageExceeded.selector);
        dex.swap(id, address(usdc), 10e6, minOut);
    }

    function test_RevertWhen_WrongTokenOrEmptyPool() public {
        uint256 id = dex.createPool(address(usdc), address(eurc));
        vm.prank(bob);
        vm.expectRevert(ValtoDEX.InsufficientLiquidity.selector);
        dex.swap(id, address(usdc), 1e6, 0);
        MockERC20 other = new MockERC20("X", "X");
        vm.prank(alice);
        dex.addLiquidity(id, 10e6, 10e6);
        vm.expectRevert(ValtoDEX.InvalidToken.selector);
        dex.swap(id, address(other), 1e6, 0);
        vm.expectRevert(ValtoDEX.UnknownPool.selector);
        dex.swap(7, address(usdc), 1e6, 0);
    }

    function test_DonationDoesNotMovePrice() public {
        uint256 id = _seed(100e6, 100e6);
        uint256 q0 = dex.getQuote(id, address(usdc), 1e6);
        vm.prank(alice);
        eurc.transfer(address(dex), 50e6); // direct donation
        assertEq(dex.getQuote(id, address(usdc), 1e6), q0);
    }

    // ---------------------------------------------------------------- hostile tokens

    function test_FeeOnTransferTokenAccountsActualAmounts() public {
        FeeToken fee = new FeeToken();
        fee.mint(alice, 1e12);
        fee.mint(bob, 1e12);
        vm.prank(alice); fee.approve(address(dex), type(uint256).max);
        vm.prank(bob); fee.approve(address(dex), type(uint256).max);
        uint256 id = dex.createPool(address(usdc), address(fee));
        vm.prank(alice);
        dex.addLiquidity(id, 100e6, 100e6);
        (,, uint256 rA, uint256 rB,) = _pool(id);
        assertEq(rA, 100e6);
        assertEq(rB, 99e6); // 1% fee never counted as reserves
        assertEq(fee.balanceOf(address(dex)), rB);
        vm.prank(bob);
        dex.swap(id, address(fee), 10e6, 0);
        (,, rA, rB,) = _pool(id);
        assertEq(fee.balanceOf(address(dex)), rB);
        assertEq(usdc.balanceOf(address(dex)), rA);
    }

    function test_NoReturnTokenWorks() public {
        NoReturnToken nr = new NoReturnToken();
        nr.mint(alice, 1e12);
        vm.prank(alice); nr.approve(address(dex), type(uint256).max);
        uint256 id = dex.createPool(address(nr), address(usdc));
        vm.prank(alice);
        dex.addLiquidity(id, 10e6, 10e6);
        vm.prank(alice);
        dex.swap(id, address(usdc), 1e6, 1);
    }

    function test_RevertWhen_TokenLiesAboutTransfer() public {
        LyingToken lie = new LyingToken();
        uint256 id = dex.createPool(address(lie), address(usdc));
        vm.prank(alice);
        vm.expectRevert(ValtoDEX.TransferFailed.selector);
        dex.addLiquidity(id, 10e6, 10e6);
    }

    function test_ReentrancyBlocked() public {
        ReentrantToken re = new ReentrantToken();
        re.mint(alice, 1e12);
        vm.prank(alice); re.approve(address(dex), type(uint256).max);
        uint256 id = dex.createPool(address(re), address(usdc));
        vm.prank(alice);
        dex.addLiquidity(id, 10e6, 10e6);
        re.arm(address(dex));
        vm.prank(alice);
        dex.swap(id, address(re), 1e6, 0); // token re-enters swap() during transferFrom
        assertEq(re.lastRevert(), abi.encodeWithSelector(ValtoDEX.Reentrancy.selector));
    }

    // ---------------------------------------------------------------- fuzz

    function testFuzz_SwapKeepsInvariantAndSolvency(uint96 rA, uint96 rB, uint96 amt, bool dir) public {
        rA = uint96(bound(rA, 1e4, 1e14));
        rB = uint96(bound(rB, 1e4, 1e14));
        amt = uint96(bound(amt, 1, 1e14));
        uint256 id = _seed(rA, rB);
        (,, uint256 a0, uint256 b0,) = _pool(id);
        address tin = dir ? address(usdc) : address(eurc);
        uint256 q = dex.getQuote(id, tin, amt);
        vm.prank(bob);
        if (q == 0) {
            vm.expectRevert(ValtoDEX.InsufficientLiquidity.selector);
            dex.swap(id, tin, amt, 0);
            return;
        }
        dex.swap(id, tin, amt, q);
        (,, uint256 a1, uint256 b1,) = _pool(id);
        assertGe(a1 * b1, a0 * b0); // k never decreases
        assertGt(a1, 0);
        assertGt(b1, 0);
        assertEq(usdc.balanceOf(address(dex)), a1);
        assertEq(eurc.balanceOf(address(dex)), b1);
    }

    function testFuzz_AddRemoveNeverProfits(uint96 a, uint96 b, uint96 add) public {
        a = uint96(bound(a, 1e6, 1e14));
        b = uint96(bound(b, 1e6, 1e14));
        add = uint96(bound(add, 1e3, 1e14));
        uint256 id = _seed(a, b);
        uint256 u0 = usdc.balanceOf(bob);
        uint256 e0 = eurc.balanceOf(bob);
        vm.startPrank(bob);
        try dex.addLiquidity(id, add, add) returns (uint256 s) {
            dex.removeLiquidity(id, s, 0, 0);
        } catch {}
        vm.stopPrank();
        assertLe(usdc.balanceOf(bob), u0);
        assertLe(eurc.balanceOf(bob), e0);
    }
}
