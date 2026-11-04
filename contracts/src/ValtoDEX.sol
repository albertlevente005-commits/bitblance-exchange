// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title ValtoDEX - constant-product AMM for stablecoin pairs on Arc
/// @notice Interface-compatible with the Bitblance front-end (same selectors as the original
///         testnet deployment): poolCount, pools, getQuote, swap, createPool, addLiquidity.
///         Adds removeLiquidity, LP shares, reentrancy protection and balance-delta accounting.
/// @dev    No owner, no admin keys, no upgradeability, no protocol fee: the 0.30% swap fee stays
///         in the pool for liquidity providers. NOT AUDITED - do not use with real funds before an audit.
contract ValtoDEX {
    uint256 public constant FEE_BPS = 30; // 0.30%
    uint256 public constant BPS = 10_000;
    /// @notice Shares burned on the first deposit of every pool (blocks share-inflation attacks).
    uint256 public constant MINIMUM_LIQUIDITY = 1_000;

    struct Pool {
        address tokenA;
        address tokenB;
        uint256 reserveA;
        uint256 reserveB;
        uint256 totalShares;
    }

    /// @notice Public getter returns (tokenA, tokenB, reserveA, reserveB, totalShares) - the
    ///         front-end reads the first four words.
    Pool[] public pools;
    /// @notice LP shares: poolId => provider => shares
    mapping(uint256 => mapping(address => uint256)) public shares;
    /// @dev keccak(sorted pair) => poolId + 1 (0 = no pool)
    mapping(bytes32 => uint256) private _poolIdPlusOne;

    uint256 private _lock = 1;

    event PoolCreated(uint256 indexed poolId, address indexed tokenA, address indexed tokenB);
    event LiquidityAdded(uint256 indexed poolId, address indexed provider, uint256 amountA, uint256 amountB, uint256 sharesMinted);
    event LiquidityRemoved(uint256 indexed poolId, address indexed provider, uint256 amountA, uint256 amountB, uint256 sharesBurned);
    event Swap(uint256 indexed poolId, address indexed trader, address indexed tokenIn, uint256 amountIn, uint256 amountOut);

    error Reentrancy();
    error IdenticalTokens();
    error ZeroAddress();
    error PoolExists(uint256 poolId);
    error UnknownPool();
    error InvalidToken();
    error ZeroAmount();
    error InsufficientLiquidity();
    error InsufficientShares();
    error SlippageExceeded();
    error TransferFailed();

    modifier nonReentrant() {
        if (_lock != 1) revert Reentrancy();
        _lock = 2;
        _;
        _lock = 1;
    }

    // ------------------------------------------------------------------ views

    function poolCount() external view returns (uint256) {
        return pools.length;
    }

    /// @notice Pool id for a pair (any order). exists=false if the pair has no pool.
    function getPoolId(address tokenX, address tokenY) external view returns (bool exists, uint256 poolId) {
        uint256 p = _poolIdPlusOne[_pairKey(tokenX, tokenY)];
        return (p != 0, p == 0 ? 0 : p - 1);
    }

    /// @notice Output amount for swapping `amountIn` of `tokenIn` in pool `poolId` (fee included).
    function getQuote(uint256 poolId, address tokenIn, uint256 amountIn) public view returns (uint256) {
        Pool storage p = _pool(poolId);
        (uint256 rIn, uint256 rOut) = _reservesFor(p, tokenIn);
        return _amountOut(amountIn, rIn, rOut);
    }

    // ------------------------------------------------------------------ pools

    function createPool(address tokenA, address tokenB) external returns (uint256 poolId) {
        if (tokenA == tokenB) revert IdenticalTokens();
        if (tokenA == address(0) || tokenB == address(0)) revert ZeroAddress();
        bytes32 key = _pairKey(tokenA, tokenB);
        uint256 existing = _poolIdPlusOne[key];
        if (existing != 0) revert PoolExists(existing - 1);
        // Both addresses must answer balanceOf like an ERC-20 (Arc's USDC lives at a precompile
        // address, so a code-size check would wrongly reject it).
        _balanceOf(tokenA);
        _balanceOf(tokenB);

        poolId = pools.length;
        pools.push(Pool(tokenA, tokenB, 0, 0, 0));
        _poolIdPlusOne[key] = poolId + 1;
        emit PoolCreated(poolId, tokenA, tokenB);
    }

    /// @notice Front-end compatible add: deposits up to (amountA, amountB) in the pool's current
    ///         ratio; only the amounts actually needed are pulled. Amounts are in pool order.
    function addLiquidity(uint256 poolId, uint256 amountA, uint256 amountB) external returns (uint256) {
        return _addLiquidity(poolId, amountA, amountB, 0);
    }

    /// @notice Same as above with a minimum-shares guard against ratio changes before inclusion.
    function addLiquidity(uint256 poolId, uint256 amountA, uint256 amountB, uint256 minShares) external returns (uint256) {
        return _addLiquidity(poolId, amountA, amountB, minShares);
    }

    function removeLiquidity(uint256 poolId, uint256 shareAmount, uint256 minA, uint256 minB)
        external
        nonReentrant
        returns (uint256 amountA, uint256 amountB)
    {
        Pool storage p = _pool(poolId);
        if (shareAmount == 0) revert ZeroAmount();
        if (shares[poolId][msg.sender] < shareAmount) revert InsufficientShares();

        uint256 ts = p.totalShares;
        amountA = shareAmount * p.reserveA / ts;
        amountB = shareAmount * p.reserveB / ts;
        if (amountA == 0 && amountB == 0) revert InsufficientLiquidity();
        if (amountA < minA || amountB < minB) revert SlippageExceeded();

        shares[poolId][msg.sender] -= shareAmount;
        p.totalShares = ts - shareAmount;
        p.reserveA -= amountA;
        p.reserveB -= amountB;

        _transferOut(p.tokenA, msg.sender, amountA);
        _transferOut(p.tokenB, msg.sender, amountB);
        emit LiquidityRemoved(poolId, msg.sender, amountA, amountB, shareAmount);
    }

    // ------------------------------------------------------------------ swap

    /// @notice Swap `amountIn` of `tokenIn`; reverts unless at least `minOut` comes out.
    function swap(uint256 poolId, address tokenIn, uint256 amountIn, uint256 minOut)
        external
        nonReentrant
        returns (uint256 amountOut)
    {
        Pool storage p = _pool(poolId);
        if (amountIn == 0) revert ZeroAmount();
        bool aIn = tokenIn == p.tokenA;
        if (!aIn && tokenIn != p.tokenB) revert InvalidToken();
        if (p.reserveA == 0 || p.reserveB == 0) revert InsufficientLiquidity();

        uint256 received = _transferIn(tokenIn, msg.sender, amountIn);
        (uint256 rIn, uint256 rOut) = aIn ? (p.reserveA, p.reserveB) : (p.reserveB, p.reserveA);
        amountOut = _amountOut(received, rIn, rOut);
        if (amountOut == 0) revert InsufficientLiquidity();
        if (amountOut < minOut) revert SlippageExceeded();

        if (aIn) {
            p.reserveA = rIn + received;
            p.reserveB = rOut - amountOut;
        } else {
            p.reserveB = rIn + received;
            p.reserveA = rOut - amountOut;
        }
        _transferOut(aIn ? p.tokenB : p.tokenA, msg.sender, amountOut);
        emit Swap(poolId, msg.sender, tokenIn, received, amountOut);
    }

    // ------------------------------------------------------------------ internals

    function _addLiquidity(uint256 poolId, uint256 amountA, uint256 amountB, uint256 minShares)
        private
        nonReentrant
        returns (uint256 minted)
    {
        Pool storage p = _pool(poolId);
        if (amountA == 0 || amountB == 0) revert ZeroAmount();

        uint256 rA = p.reserveA;
        uint256 rB = p.reserveB;
        uint256 ts = p.totalShares;

        if (ts != 0) {
            // keep the pool ratio: pull only what matches the smaller side
            uint256 bOptimal = amountA * rB / rA;
            if (bOptimal <= amountB) {
                amountB = bOptimal;
            } else {
                amountA = amountB * rA / rB;
            }
            if (amountA == 0 || amountB == 0) revert ZeroAmount();
        }

        uint256 inA = _transferIn(p.tokenA, msg.sender, amountA);
        uint256 inB = _transferIn(p.tokenB, msg.sender, amountB);

        if (ts == 0) {
            uint256 root = _sqrt(inA * inB);
            if (root <= MINIMUM_LIQUIDITY) revert InsufficientLiquidity();
            minted = root - MINIMUM_LIQUIDITY;
            shares[poolId][address(0)] = MINIMUM_LIQUIDITY; // permanently locked
            ts = MINIMUM_LIQUIDITY;
        } else {
            uint256 sA = inA * ts / rA;
            uint256 sB = inB * ts / rB;
            minted = sA < sB ? sA : sB;
        }
        if (minted == 0) revert InsufficientLiquidity();
        if (minted < minShares) revert SlippageExceeded();

        shares[poolId][msg.sender] += minted;
        p.totalShares = ts + minted;
        p.reserveA = rA + inA;
        p.reserveB = rB + inB;
        emit LiquidityAdded(poolId, msg.sender, inA, inB, minted);
    }

    function _pool(uint256 poolId) private view returns (Pool storage) {
        if (poolId >= pools.length) revert UnknownPool();
        return pools[poolId];
    }

    function _reservesFor(Pool storage p, address tokenIn) private view returns (uint256, uint256) {
        if (tokenIn == p.tokenA) return (p.reserveA, p.reserveB);
        if (tokenIn == p.tokenB) return (p.reserveB, p.reserveA);
        revert InvalidToken();
    }

    function _amountOut(uint256 amountIn, uint256 rIn, uint256 rOut) private pure returns (uint256) {
        if (amountIn == 0 || rIn == 0 || rOut == 0) return 0;
        uint256 inWithFee = amountIn * (BPS - FEE_BPS);
        return inWithFee * rOut / (rIn * BPS + inWithFee);
    }

    function _pairKey(address x, address y) private pure returns (bytes32) {
        return x < y ? keccak256(abi.encodePacked(x, y)) : keccak256(abi.encodePacked(y, x));
    }

    /// @dev balanceOf that reverts on non-ERC-20 addresses (empty returndata).
    function _balanceOf(address token) private view returns (uint256) {
        (bool ok, bytes memory data) = token.staticcall(abi.encodeWithSelector(0x70a08231, address(this)));
        if (!ok || data.length < 32) revert InvalidToken();
        return abi.decode(data, (uint256));
    }

    /// @dev Pulls tokens and returns what actually arrived (safe with fee-on-transfer tokens and
    ///      tokens that return no bool).
    function _transferIn(address token, address from, uint256 amount) private returns (uint256) {
        uint256 before = _balanceOf(token);
        (bool ok, bytes memory data) = token.call(abi.encodeWithSelector(0x23b872dd, from, address(this), amount));
        if (!ok || (data.length != 0 && !abi.decode(data, (bool)))) revert TransferFailed();
        uint256 received = _balanceOf(token) - before;
        if (received == 0) revert TransferFailed();
        return received;
    }

    /// @dev Sends tokens and checks the pool balance really dropped by `amount`.
    function _transferOut(address token, address to, uint256 amount) private {
        if (amount == 0) return;
        uint256 before = _balanceOf(token);
        (bool ok, bytes memory data) = token.call(abi.encodeWithSelector(0xa9059cbb, to, amount));
        if (!ok || (data.length != 0 && !abi.decode(data, (bool)))) revert TransferFailed();
        if (before - _balanceOf(token) != amount) revert TransferFailed();
    }

    function _sqrt(uint256 y) private pure returns (uint256 z) {
        if (y > 3) {
            z = y;
            uint256 x = y / 2 + 1;
            while (x < z) {
                z = x;
                x = (y / x + x) / 2;
            }
        } else if (y != 0) {
            z = 1;
        }
    }
}
