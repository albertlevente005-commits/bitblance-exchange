# Bitblance Exchange

Native stablecoin DEX interface for **Arc** (Circle's stablecoin-native chain) — swap, bridge and automate stablecoin FX with sub-second finality.

**Live app:** single-file build, no framework, no build step. Just open `index.html`.

The app runs on **Arc Mainnet by default**. Append `?net=testnet` to the URL (or use the footer link) to use Arc Testnet in the current tab.

## Features

- **Swap** — on-chain swaps via the ValtoDEX AMM (0.30% fee) with a live pool quote, price impact and min-received (0.5% slippage)
- **Pools** — create ValtoDEX pairs and add liquidity straight from the UI (approve + addLiquidity flows)
- **Bridge** — Circle CCTP V2 from Arc to Ethereum, Base, Arbitrum, Avalanche and OP (Sepolia / Fuji equivalents on testnet). Circle's transfer fee is quoted live from the Iris API before the burn.
- **Recurring orders** — DCA-style scheduled swaps (daily / weekly / biweekly / monthly). Preview only: stored locally, not executed automatically yet.
- **Profile** — live on-chain balances read directly from the Arc RPC
- **Blance AI** — built-in copilot for rates, bridging, USYC and Arc gas questions
- **Get started / Faucet** — one-click "Add Arc to wallet"; on testnet, Circle faucet shortcuts
- **BitBlance Points** — loyalty program teaser with waitlist

## Network details

| | Mainnet | Testnet |
|---|---|---|
| Chain ID | 5042 (`0x13b2`) | 5042002 (`0x4cef52`) |
| RPC | `https://rpc.mainnet.arc.io` | `https://rpc.testnet.arc.io` |
| Gas token | USDC (18 decimals natively, shown as USDC) | USDC |
| Explorer | `https://explorer.arc.io` | `https://explorer.testnet.arc.io` |
| Faucet | — | `https://faucet.circle.com` |
| CCTP domain | 26 | 26 |

Token contracts (from [docs.arc.io](https://docs.arc.io/arc/references/contract-addresses)):

| Token | Mainnet | Testnet |
|---|---|---|
| USDC | `0x3600000000000000000000000000000000000000` | `0x3600000000000000000000000000000000000000` |
| EURC | `0xbEf5f6d51CB62b58e6A8f77868681825C6fe21c1` | `0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a` |
| USYC | `0x8a5D989Bbb96929F689B0200f435f53dA42bF490` | `0xe9185F0c5F296Ed1797AaE4238D26CCaBEadb86C` |

CCTP V2 contracts:

| Contract | Mainnet | Testnet |
|---|---|---|
| TokenMessengerV2 | `0x28b5a0e9C621a5BadaA536219b3a228C8168cf5d` | `0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA` |
| MessageTransmitterV2 | `0x81D40F21F12A8F0E3252Bccb954D722d4c464B64` | `0xE737e5cEBEEBa77EFE34D4aa090756590b1CE275` |
| Iris API | `https://iris-api.circle.com` | `https://iris-api-sandbox.circle.com` |

## ValtoDEX AMM

| | Address |
|---|---|
| Testnet | `0xefa6efae5962fb59b90968f80b50841efdd0a806` |
| Mainnet | **not deployed yet** |

Until the AMM is deployed on Arc Mainnet, the Swap and Pools tabs show a notice and stay disabled on mainnet; bridging works. To go live:

1. Deploy the ValtoDEX AMM contract on Arc Mainnet (chain ID 5042, gas paid in USDC).
2. Put the deployed address into `NETWORKS.mainnet.dex` near the top of the `<script>` in `index.html`.
3. Create the USDC/EURC pool and seed it from the Pools tab.

The app checks `eth_getCode` on the configured address at startup and only enables swaps when the contract is actually there.

## Run locally

Open `index.html` in any modern browser. A wallet extension (MetaMask, Rabby) is needed for the connected features.

## Deploy

Works on any static host: GitHub Pages, Cloudflare Pages, Netlify, Vercel. Upload the file, point your domain, done.

## Status & disclaimer

Mainnet handles real funds. Wallet connection, network switching, balance reads and CCTP bridging run live on-chain; swaps and liquidity management run live wherever the ValtoDEX AMM is deployed. Recurring orders are a local preview. Nothing here is financial advice — use at your own risk.
