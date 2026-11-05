# Bitblance Exchange

Native stablecoin DEX interface for **Arc** (Circle's stablecoin-native L1) — swap, bridge and automate stablecoin FX with sub-second finality.

**Live app:** single-file build, no framework, no build step. Just open `index.html`.

## Also in this repo

- [`eredmenyek/`](eredmenyek/) — **Eredménytábla**, a Flashscore-style live scores page for Hungarian and European football, ice hockey, handball, basketball and tennis (single-file, no build step). Served at `/eredmenyek/` on GitHub Pages.
- [`screener/`](screener/) — data-driven crypto project screener.

## Networks

The app runs on **Arc Mainnet by default**. Arc Testnet stays available for QA:

| | Arc Mainnet (default) | Arc Testnet |
|---|---|---|
| Select with | `?net=mainnet` | `?net=testnet` (remembered in the browser) |
| Chain ID | 5042 (`0x13b2`) | 5042002 (`0x4cef52`) |
| RPC | `https://rpc.mainnet.arc.io` (+ QuickNode, dRPC, Blockdaemon fallbacks) | `https://rpc.testnet.arc.io` |
| Gas token | USDC | USDC |
| Explorer | `https://explorer.arc.io` | `https://explorer.testnet.arc.io` |
| Faucet | — (bridge USDC in via CCTP) | `https://faucet.circle.com` |
| USDC | `0x3600000000000000000000000000000000000000` | `0x3600000000000000000000000000000000000000` |
| EURC | `0xbEf5f6d51CB62b58e6A8f77868681825C6fe21c1` | `0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a` |
| USYC | `0x8a5D989Bbb96929F689B0200f435f53dA42bF490` | `0xe9185F0c5F296Ed1797AaE4238D26CCaBEadb86C` |
| CCTP TokenMessengerV2 | `0x28b5a0e9C621a5BadaA536219b3a228C8168cf5d` | `0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA` |
| CCTP MessageTransmitterV2 | `0x81D40F21F12A8F0E3252Bccb954D722d4c464B64` | `0xE737e5cEBEEBa77EFE34D4aa090756590b1CE275` |
| CCTP domain | 26 | 26 |
| Iris attestation API | `https://iris-api.circle.com` | `https://iris-api-sandbox.circle.com` |
| ValtoDEX AMM router | **not deployed yet** (see below) | `0xefa6efae5962fb59b90968f80b50841efdd0a806` |

All addresses come from the official Arc docs: [RPC endpoints](https://docs.arc.io/arc/references/rpc-endpoints) and [Contract addresses](https://docs.arc.io/arc/references/contract-addresses).

The header badge shows the active network and lets you switch. Every transaction is guarded: the wallet must be on the selected Arc chain ID before anything is sent.

## Features

- **Swap** — real on-chain swaps via the ValtoDEX AMM (0.30% fee); the preview shows the real pool quote, price impact and min-received (0.5% slippage)
- **Pools** — create ValtoDEX pairs and add liquidity straight from the UI (approve + addLiquidity flows)
- **Bridge** — Circle CCTP V2 burn-and-mint from Arc to Ethereum, Base, Arbitrum, Avalanche and OP Mainnet (Sepolia / Fuji equivalents on testnet), with attestation polling and one-click claim on the destination. Circle's transfer fee is quoted live from the Iris API and passed as `maxFee` before the burn
- **Recurring orders** — DCA-style scheduled swaps (daily / weekly / biweekly / monthly), stored locally (preview only, not executed automatically yet)
- **Profile** — live on-chain balances read directly from the Arc RPC
- **Blance AI** — built-in copilot for rates, bridging, USYC and Arc gas questions
- **Network** (mainnet) / **Faucet** (testnet) — one-click "Add Arc to wallet", network details, how to get USDC
- **BitBlance Points** — loyalty program teaser with waitlist

## Mainnet launch checklist

1. **Deploy the ValtoDEX AMM to Arc Mainnet** (chain ID 5042, deployer needs USDC for gas; set `maxFeePerGas` ≥ 20 Gwei). Source, tests and deploy script: [`contracts/`](contracts/README.md). ⚠️ The contract is **not audited yet**: get it audited before it holds real funds.
2. Put the deployed router address into `NETWORKS.mainnet.dex` in `index.html`. Until then the UI pauses Swap and Pools with a notice; Bridge, balances and wallet features already work on mainnet.
   - Quick test without redeploying the site: open `index.html?dex=0xYourRouter` (stored in the browser for mainnet; `?dex=reset` clears it).
3. Seed the first USDC/EURC pool at a market-like ratio — the first deposit sets the price and off-market ratios get arbitraged with real funds.
4. Open the site, confirm the header says **Arc Mainnet**, and do a small swap and a small CCTP bridge end to end.

## Transaction safety

- **Network check before every transaction**: nothing is sent unless the wallet is on the selected Arc network (and on the destination chain when claiming a bridge transfer).
- **Exact approvals only**: swaps, pool deposits and CCTP burns approve exactly the amount being spent, never an unlimited allowance.
- **Slippage limit**: user-selectable max. slippage (0.1% / 0.5% / 1% / custom, hard-capped at 5%), applied as `minOut` to the on-chain swap.
- **Pool price check**: if a pool quotes more than 2% worse than the reference rate (or a new pool's first deposit is priced more than 2% off), the user must confirm explicitly.
- **Approval manager**: the Profile tab lists open approvals to ValtoDEX and CCTP, with one-click revoke.

## Smart contract

The ValtoDEX AMM source, Foundry tests and deploy script are in [`contracts/`](contracts/README.md).
It uses the same function selectors as the original testnet router, so the front-end works with it
unchanged. **Not audited yet.**

## Crypto project screener platform

The `screener/` directory holds a separate, data-driven crypto project screening and monitoring
platform (Python + SQLite + FastAPI): DefiLlama / CoinGecko / GitHub data, a weighted scoring model
with red flags, daily ranking, early-project watchlist, Telegram alerts, a JSON feed for the OKX DCA
bot and a web dashboard. See [`screener/README.md`](screener/README.md) (Hungarian).

## Run locally

Open `index.html` in any modern browser. A wallet extension (MetaMask, Rabby, Coinbase Wallet, Rainbow) is needed for the connected features.

## Deploy

Works on any static host: GitHub Pages, Cloudflare Pages, Netlify, Vercel. Upload the file, point your domain, done.

## Status & disclaimer

Wallet connection, network switching, balance reads, swaps, liquidity management and CCTP bridging run live on-chain. On Arc Mainnet these move real USDC / EURC — double-check amounts and addresses. Nothing here is financial advice.
