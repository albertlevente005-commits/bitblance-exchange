# Bitblance Exchange

Native stablecoin DEX interface for **Arc** (Testnet, with a read-only Mainnet mode) — swap, bridge and automate stablecoin FX with sub-second finality.

**Live app:** single-file build, no framework, no build step. Just open `index.html`.

## Features

- **Swap** — real on-chain swaps via our deployed ValtoDEX AMM (0.30% fee), with live quotes, price impact and min-received display
- **Pools** — create ValtoDEX pairs and add liquidity straight from the UI (approve + addLiquidity flows)
- **Bridge** — real Circle CCTP V2 flow (burn → attestation → claim) from Arc to Ethereum Sepolia, Base Sepolia, Arbitrum Sepolia, Avalanche Fuji, OP Sepolia, with selectable source and destination networks
- **Recurring orders** — DCA-style scheduled swaps (daily / weekly / biweekly / monthly), stored locally
- **Profile** — live on-chain balances read directly from Arc Testnet RPC
- **Blance AI** — built-in copilot for rates, bridging, USYC and Arc gas questions
- **Faucet** — Circle faucet shortcuts plus one-click "Add Arc Testnet to wallet"
- **BitBlance Points** — loyalty program teaser with waitlist

## Network details

Switch networks with the network button in the header (or open the site with `?net=mainnet` / `?net=testnet`). The choice is remembered in the browser.

| | Testnet | Mainnet |
|---|---|---|
| Chain ID | 5042002 (`0x4cef52`) | 5042 (`0x13b2`) |
| RPC | `https://rpc.testnet.arc.network` | `https://rpc.mainnet.arc.io` |
| Gas token | USDC | USDC |
| Explorer | `https://testnet.arcscan.app` | `https://explorer.arc.io` |
| Faucet | `https://faucet.circle.com` | — |
| USDC | `0x3600000000000000000000000000000000000000` | `0x3600000000000000000000000000000000000000` |
| EURC | `0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a` | `0xbEf5f6d51CB62b58e6A8f77868681825C6fe21c1` |
| USYC | `0xe9185F0c5F296Ed1797AaE4238D26CCaBEadb86C` | `0x8a5D989Bbb96929F689B0200f435f53dA42bF490` |
| CCTP TokenMessengerV2 | `0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA` | `0x28b5a0e9C621a5BadaA536219b3a228C8168cf5d` |
| ValtoDEX AMM | `0xefa6efae5962fb59b90968f80b50841efdd0a806` | not deployed yet |

Addresses are from the official Arc docs (docs.arc.io → Contract addresses).

### Mainnet mode

Mainnet is **read-only** for now: wallet connection, network switching and live balances work, but swaps, pools and bridging are disabled. To enable trading, deploy and audit ValtoDEX on mainnet, then set `NETWORKS.mainnet.dex` in `index.html` and lift the `READ_ONLY` guard.

## Transaction safety

- **Network check before every transaction** — the app refuses to send anything unless the wallet is on the selected Arc network (and on the destination chain when claiming a bridge transfer).
- **Exact approvals only** — swaps, pool deposits and CCTP burns approve exactly the amount being spent, never an unlimited allowance.
- **Slippage limit** — user-selectable max. slippage (0.1% / 0.5% / 1% / custom, hard-capped at 5%), applied as `minOut` to the on-chain swap.
- **Pool price check** — if a pool quotes more than 2% worse than the reference rate (or a new pool's first deposit is priced more than 2% off), the user must confirm explicitly.
- **Approval manager** — the Profile tab lists open approvals to ValtoDEX and CCTP, with one-click revoke.

## Run locally

Open `index.html` in any modern browser. A wallet extension (MetaMask, Rabby) is needed for the connected features.

## Deploy

Works on any static host: GitHub Pages, Cloudflare Pages, Netlify, Vercel. Upload the file, point your domain, done.

## Status & disclaimer

On Testnet, wallet connection, balance reads, swaps, liquidity management and CCTP bridging (Arc → other testnets) run live on-chain. Mainnet mode is read-only. Displayed market prices are still static placeholders. Nothing here is financial advice.
