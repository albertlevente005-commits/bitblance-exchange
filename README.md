# Bitblance Exchange

Native stablecoin DEX interface for the **Arc Testnet** — swap, bridge and automate stablecoin FX with sub-second finality.

**Live app:** single-file build, no framework, no build step. Just open `index.html`.

## Features

- **Swap** — real on-chain swaps via our deployed ValtoDEX AMM (0.30% fee), with live quotes, price impact and min-received display
- **Pools** — create ValtoDEX pairs and add liquidity straight from the UI (approve + addLiquidity flows)
- **Bridge** — Circle CCTP V2 flow between Arc and Ethereum Sepolia, Base Sepolia, Arbitrum Sepolia, Avalanche Fuji, OP Sepolia, with selectable source and destination networks
- **Recurring orders** — DCA-style scheduled swaps (daily / weekly / biweekly / monthly), stored locally
- **Profile** — live on-chain balances read directly from Arc Testnet RPC
- **Blance AI** — built-in copilot for rates, bridging, USYC and Arc gas questions
- **Faucet** — Circle faucet shortcuts plus one-click "Add Arc Testnet to wallet"
- **BitBlance Points** — loyalty program teaser with waitlist

## Network details

| | |
|---|---|
| Chain | Arc Testnet |
| Chain ID | 5042002 (`0x4cef52`) |
| RPC | `https://rpc.testnet.arc.network` |
| Gas token | USDC |
| Explorer | `https://testnet.arcscan.app` |
| Faucet | `https://faucet.circle.com` |

Token contracts (Arc Testnet): USDC `0x3600000000000000000000000000000000000000` · EURC `0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a` · USYC `0xe9185F0c5F296Ed1797AaE4238D26CCaBEadb86C`

## Run locally

Open `index.html` in any modern browser. A wallet extension (MetaMask, Rabby) is needed for the connected features.

## Deploy

Works on any static host: GitHub Pages, Cloudflare Pages, Netlify, Vercel. Upload the file, point your domain, done.

## Status & disclaimer

Testnet demo. Wallet connection, network switching, balance reads, swaps and liquidity management run live on-chain against our deployed ValtoDEX AMM (0xefa6efae5962fb59b90968f80b50841efdd0a806). Bridge execution is still simulated. Test tokens only — nothing here has real value and nothing is financial advice.
