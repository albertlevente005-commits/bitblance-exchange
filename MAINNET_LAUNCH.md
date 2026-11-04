# Bitblance – Arc Mainnet indítási jegyzet

Dátum: 2026-11-04 · Branch: `claude/keen-johnson-fjfanp` · Commit: `b510e6b`

## Mi változott

Az app korábban fixen Arc Testnetre volt kötve. Most hálózati konfig van az `index.html`-ben
(`NETWORKS` objektum), **Arc Mainnet az alapértelmezett**, a testnet `?net=testnet`-tel elérhető
(a böngésző megjegyzi). A fejléc badge mutatja és váltja a hálózatot.

| | Arc Mainnet | Arc Testnet |
|---|---|---|
| Chain ID | 5042 (`0x13b2`) | 5042002 (`0x4cef52`) |
| RPC | `https://rpc.mainnet.arc.io` (+ quicknode / drpc / blockdaemon fallback) | `https://rpc.testnet.arc.io` |
| Explorer | `https://explorer.arc.io` | `https://explorer.testnet.arc.io` |
| Gáz | USDC (18 dec natív, 6 dec ERC-20), min. 20 Gwei | ugyanaz |
| USDC | `0x3600000000000000000000000000000000000000` | ugyanaz |
| EURC | `0xbEf5f6d51CB62b58e6A8f77868681825C6fe21c1` | `0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a` |
| USYC | `0x8a5D989Bbb96929F689B0200f435f53dA42bF490` | `0xe9185F0c5F296Ed1797AaE4238D26CCaBEadb86C` |
| cirBTC | `0x171A4217b86A807A64eB94757Db6849fb4bDbAA0` | `0xf0C4a4CE82A5746AbAAd9425360Ab04fbBA432BF` |
| WETH | `0x128cC466B61f542da60c70e3aA11c10e19B84EDB` | `0x2c4047028a72803939b6fb674D01bC059B5C4961` |
| CCTP TokenMessengerV2 | `0x28b5a0e9C621a5BadaA536219b3a228C8168cf5d` | `0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA` |
| CCTP MessageTransmitterV2 | `0x81D40F21F12A8F0E3252Bccb954D722d4c464B64` | `0xE737e5cEBEEBa77EFE34D4aa090756590b1CE275` |
| CCTP domain | 26 | 26 |
| Iris API | `https://iris-api.circle.com` | `https://iris-api-sandbox.circle.com` |
| Bridge célhálózatok | Ethereum (0), Avalanche (1), OP (2), Arbitrum (3), Base (6) | Sepolia / Fuji megfelelők |
| ValtoDEX router | **nincs deployolva** | `0xefa6efae5962fb59b90968f80b50841efdd0a806` |

Forrás: https://docs.arc.io/arc/references/rpc-endpoints és
https://docs.arc.io/arc/references/contract-addresses

Beépített védelmek:
- Minden tranzakció előtt `ensureOnArc()` ellenőrzi, hogy a wallet a kiválasztott Arc chainen van.
- Induláskor `checkDex()` lekéri a router bytecode-ját; ha nincs, a Swap és a Pools szünetel
  figyelmeztetéssel, a Bridge és a balance-olvasás megy.
- Mainneten a Faucet tab helyett Network tab (hálózat hozzáadása, USDC beszerzés).

## Teendők az éles indítás előtt

1. **ValtoDEX AMM deploy Arc Mainnetre** (chain 5042, a deployer walletben legyen USDC gázra,
   `maxFeePerGas` ≥ 20 Gwei). A szerződés forrása nincs ebben a repóban.
2. A kapott router címet beírni az `index.html`-ben: `NETWORKS.mainnet.dex: '0x...'`.
   Gyors teszt újradeploy nélkül: `index.html?dex=0xRouterCím` (törlés: `?dex=reset`).
3. Első USDC/EURC pool seedelése piaci arányban (pl. 10 USDC + 9.2 EURC) – valódi pénz,
   rossz arányt azonnal arbitrálnak.
4. Élesben kis swap + kis CCTP bridge (Arc → pl. Base) végigpróbálása, claim a célhálózaton.
5. Branch merge `main`-be, GitHub Pages / `bitblance.exchange` (CNAME) újratöltése.

## Nem ellenőrzött

A fejlesztői sandboxból az RPC-k nem voltak elérhetők, a címek a docsból származnak, on-chain
nem lettek verifikálva. A böngészős smoke-teszt mindkét hálózaton hibamentesen lefutott.
