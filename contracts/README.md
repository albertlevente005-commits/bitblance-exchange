# ValtoDEX contracts

Constant-product AMM (x·y=k, 0.30% fee) for stablecoin pairs on Arc. It has the same
function selectors as the original testnet ValtoDEX, so the Bitblance front-end
(`../index.html`) works with it **without code changes**.

> ⚠️ **Not audited.** Do not deploy to Arc Mainnet or put real funds in it before an
> independent security audit.

## What changed versus the original

| | Original (testnet) | This version |
|---|---|---|
| Front-end interface (`poolCount`, `pools`, `getQuote`, `swap`, `createPool`, `addLiquidity`) | ✓ | ✓ same selectors |
| Remove liquidity | — | `removeLiquidity(poolId, shares, minA, minB)` |
| LP share accounting | ? | `shares(poolId, address)`, 1,000 shares locked on first deposit (blocks share-inflation attacks) |
| Reentrancy guard | ? | on every state-changing function |
| Duplicate pools | ? | rejected (`getPoolId(tokenX, tokenY)`) |
| Proportional deposits | ? | pulls only the amounts matching the pool ratio; optional `minShares` overload |
| Token transfers | ? | balance-delta checks (safe with fee-on-transfer, no-return and lying tokens) |
| Donations | ? | ignored; prices use tracked reserves only |
| Admin / owner keys | ? | none: no owner, no upgrade, no pause, no protocol fee |

## Interface

```solidity
function poolCount() view returns (uint256)
function pools(uint256) view returns (address tokenA, address tokenB, uint256 reserveA, uint256 reserveB, uint256 totalShares)
function getPoolId(address, address) view returns (bool exists, uint256 poolId)
function getQuote(uint256 poolId, address tokenIn, uint256 amountIn) view returns (uint256 amountOut)
function createPool(address tokenA, address tokenB) returns (uint256 poolId)
function addLiquidity(uint256 poolId, uint256 amountA, uint256 amountB) returns (uint256 shares)
function addLiquidity(uint256 poolId, uint256 amountA, uint256 amountB, uint256 minShares) returns (uint256 shares)
function removeLiquidity(uint256 poolId, uint256 shares, uint256 minA, uint256 minB) returns (uint256 amountA, uint256 amountB)
function swap(uint256 poolId, address tokenIn, uint256 amountIn, uint256 minOut) returns (uint256 amountOut)
function shares(uint256 poolId, address provider) view returns (uint256)
```

## Build & test

Requires [Foundry](https://book.getfoundry.sh/getting-started/installation).

```sh
git submodule update --init --recursive   # fetches forge-std
cd contracts
forge test -vv
```

23 tests: front-end selector/layout compatibility, pools, liquidity add/remove,
slippage, front-running, fee accrual, donations, fee-on-transfer / no-return / lying
tokens, reentrancy, plus fuzz tests (k never decreases, pool stays solvent, add+remove
never profits).

## Deploy

The signer is chosen on the command line. **Never put a private key in a file, in `.env`,
or in a chat.** Prefer a hardware wallet (`--ledger` / `--trezor`); `--interactive`
asks for the key in the terminal without storing it.

```sh
cd contracts

# 1. Testnet first
forge script script/Deploy.s.sol --rpc-url arc_testnet --broadcast --interactive

# 2. Mainnet - only after the audit
forge script script/Deploy.s.sol --rpc-url arc_mainnet --broadcast --ledger
```

The deployer needs a little USDC for gas. The script refuses to run on anything other
than Arc (chain 5042 / 5042002) or a local node.

After deploying, put the printed address into `index.html`:

```js
const NETWORKS = {
  ...
  mainnet: {
    ...
    dex: '0xYOUR_DEPLOYED_ADDRESS',
```

Mainnet trading in the front-end also stays disabled until the `READ_ONLY` guard
(`const READ_ONLY = NET.mainnet;`) is lifted, which should happen only after the audit.

Optional: verify the source on the explorer so users can read it
(`forge verify-contract <address> src/ValtoDEX.sol:ValtoDEX --chain-id 5042 ...`, see the
Arc docs for the explorer's verifier URL).
