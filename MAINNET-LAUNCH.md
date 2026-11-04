# Arc Mainnet indítási jegyzet

Állapot: 2026-11-04. Az app alapból **Arc Mainnet**-en fut, a testnet `?net=testnet`-tel (vagy a lábléc linkjével) érhető el az adott böngészőfülben.

## Mi készült el

- Hálózati konfig mainnetre (`index.html`, `NETWORKS` objektum a `<script>` elején):
  chain ID 5042, RPC `https://rpc.mainnet.arc.io`, explorer `https://explorer.arc.io`.
- Mainnet token címek (docs.arc.io): USDC `0x3600000000000000000000000000000000000000`,
  EURC `0xbEf5f6d51CB62b58e6A8f77868681825C6fe21c1`, USYC `0x8a5D989Bbb96929F689B0200f435f53dA42bF490`,
  cirBTC `0x171A4217b86A807A64eB94757Db6849fb4bDbAA0`.
- CCTP V2 mainnet: TokenMessengerV2 `0x28b5a0e9C621a5BadaA536219b3a228C8168cf5d`,
  MessageTransmitterV2 `0x81D40F21F12A8F0E3252Bccb954D722d4c464B64`, Iris `https://iris-api.circle.com`,
  Arc domain 26. Célhálózatok: Ethereum (0), Avalanche (1), OP Mainnet (2), Arbitrum One (3), Base (6).
- A Circle átutalási díját élőben kérdezi le (`/v2/burn/USDC/fees/26/{dest}`) és `maxFee`-ként adja át
  a `depositForBurn`-nek. Túl kis összegnél (díj >= összeg) hibát ad.
- Indításkor `eth_getCode`-dal ellenőrzi, hogy a ValtoDEX AMM létezik-e. Ha nincs, a Swap és Pools
  fül figyelmeztetést mutat és le van tiltva, a bridge működik.
- Swap előnézet a valódi pool-árajánlatból (price impact, min. received 0,5% slippage).
  EURC referenciaár az ECB EUR/USD árfolyamából (frankfurter.app), fallback 1,083.
- Minden tranzakció előtt ellenőrzi, hogy a tárca az Arc hálózaton van-e; ha nem, átváltást kér.
- Mainneten a Faucet fül helyett "Get started" fül (hálózat hozzáadása, USDC szerzés).
- Kikerültek a kitalált TVL / volumen / %-változás számok. A Recurring fül jelzi, hogy csak
  helyi előnézet, nem hajt végre tranzakciót.
- Testnet hostok frissítve: `rpc.testnet.arc.io`, `explorer.testnet.arc.io`.

## Teendő az éles indulás előtt

1. **ValtoDEX AMM telepítése Arc Mainnetre.** Jelenleg csak testneten van
   (`0xefa6efae5962fb59b90968f80b50841efdd0a806`). A forráskód nincs a repóban, a telepítéshez
   a deployer kulcs és a kontrakt forrása kell. Gáz USDC-ben, chain ID 5042.
2. A telepített címet beírni az `index.html`-ben: `NETWORKS.mainnet.dex: '0x...'` (egy sor).
3. Pools fülön létrehozni és feltölteni a USDC/EURC poolt (kb. piaci arány, pl. 10 USDC + 9,2 EURC).
4. Kis összegű (pl. 2 USDC) éles bridge próba Arc → Base irányban valódi tárcával.
   A sandboxból az RPC és a Circle API nem volt elérhető, az on-chain rész mockolt válaszokkal
   lett tesztelve, a címek a hivatalos dokumentációból származnak.
5. Az ágat a `main`-re merge-elni (a GitHub Pages / `bitblance.exchange` a `main`-t szolgálja ki).

## Hasznos linkek

- Hálózati adatok: https://docs.arc.io/arc/references/rpc-endpoints
- Kontrakt címek: https://docs.arc.io/arc/references/contract-addresses
- Tárca beállítás: https://docs.arc.io/arc/references/connect-to-arc
- Gas tracker: https://explorer.arc.io/gas-tracker
- Hálózat státusz: https://status.arc.io

## Ág

A munka a `claude/wizardly-brown-zxlneq` ágon van (commit `a8455f7` és ez a jegyzet).
