# Kripto projekt-szűrő és -figyelő platform

Adatvezérelt döntéstámogató rendszer: nem a hype, hanem mérhető adatok alapján rangsorolja a
kripto projekteket, figyeli őket, és Telegramon riaszt. Python + SQLite, REST API-val és
beépített webes dashboarddal, Dockerrel telepíthető.

> **Fontos korlát:** a szűrő a kockázatot csökkenti, a nyereséget nem garantálja. Ez nem pénzügyi
> tanács. A rendszer döntéstámogatás, nem automata vásárlási jel. Új, kis kapitalizációjú
> projekteknél mindig számolj a teljes elvesztés lehetőségével.

## Mit csinál

| Lépés | Mi történik |
|---|---|
| **Adatgyűjtés** | DefiLlama (TVL, díjbevétel, bevétel, aktív felhasználók, token-unlockok, hackek, pool-hozamok), CoinGecko (ár, forgalom, kapitalizáció, kínálat, tőzsdeszám, spread, repók), GitHub (commitok, aktív kontribútorok, release-ek, utolsó push), Snapshot (governance-javaslatok, szavazók, követők), Token Terminal (szabványosított díj, bevétel, DAU/MAU, tranzakciók, holderek), DeFiSafety (Process Quality Review pontszám), Dune (saját mentett lekérdezések: valós használat és bevétel). Minden napi pillanatkép SQLite-ba kerül, így a saját történet is gyűlik. |
| **Pontozás** | 5 kategória, mindegyik 0–100: valós használat, tokenomika, csapat és fejlesztés, likviditás, piros zászlók. Súlyozott összpontszám 0–100. |
| **Rangsor** | Napi rangsor pontszám szerint, kategória/zászló/keresés szűrővel. |
| **Figyelőlista** | Friss (alapból 60 napon belül listázott) projektek, kritikus zászló nélkül. |
| **Riasztások** | Telegramra: nagy unlock közeleg, TVL zuhan, fejlesztés leáll, új ígéretes projekt, nagy pontszám-változás. Minden riasztás csak egyszer megy ki (kulcs szerinti deduplikáció). |
| **DCA-export** | `out/dca_candidates.json` és `/api/dca-candidates`: csak a teljes szűrőn átment érmék, az OKX DCA bot ebből olvashat. |
| **Platform** | REST API + dashboard (`screener serve`), a napi kört a beépített ütemező futtatja. |

## Gyors indítás

```bash
cd screener
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-web.txt
cp .env.example .env          # Telegram token + chat id, opcionális API-kulcsok
python -m screener init
python -m screener run-daily --no-send   # első kör: lekérés, pontozás, riasztások, exportok
python -m screener rank --top 25
python -m screener serve --port 8080     # dashboard: http://localhost:8080
```

Docker:

```bash
cd screener
cp .env.example .env
docker compose up -d --build
```

Az adatbázis és a kimenetek a `screener-data` köteten maradnak meg. A konténer indulásakor a
beépített ütemező a `config.toml` `[web] run_at` időpontjában (alapból 06:00) futtatja a napi kört.

## Parancsok

| Parancs | Leírás |
|---|---|
| `init` | Adatbázis és kimeneti mappa létrehozása |
| `fetch [--skip-github] [--skip-details]` | Adatok lekérése a mai pillanatképbe |
| `score` | Pontozás a mai pillanatképből |
| `rank [--top N] [--category X] [--json]` | Rangsor |
| `watchlist [--min-score N]` | Korai projektek figyelőlistája |
| `alerts [--send]` | Riasztások generálása, `--send` esetén Telegramra küldés |
| `export-dca [--out f]` | DCA-jelöltek JSON-ba |
| `report [--out f]` | Statikus HTML-jelentés |
| `run-daily [--no-send]` | Teljes napi kör egyben |
| `daemon --at HH:MM` | Blokkoló ütemező (szerver nélkül) |
| `serve [--port 8080] [--no-scheduler]` | Webes platform (API + dashboard + ütemező) |
| `telegram-test` | Tesztüzenet a Telegram-kapcsolat ellenőrzésére |

Cron alternatíva a beépített ütemező helyett:

```
0 6 * * * cd /path/to/screener && .venv/bin/python -m screener run-daily >> out/cron.log 2>&1
```

## REST API

| Végpont | Mit ad |
|---|---|
| `GET /api/health` | Állapot, legutóbbi értékelés napja, ütemező státusz |
| `GET /api/ranking?day&top&category&min_score&q&flag` | Rangsor |
| `GET /api/projects/{slug}` | Projektprofil: pontszám, részmutatók, pillanatkép-történet, GitHub, hackek, riasztások |
| `GET /api/watchlist?min_score` | Korai projektek |
| `GET /api/dca-candidates` | A DCA-bot bemenete |
| `GET /api/alerts?limit&kind` | Riasztásnapló |
| `GET /api/categories`, `GET /api/days`, `GET /api/config` | Szűrőkhöz |
| `POST /api/run` | Napi kör azonnali indítása. `X-Admin-Token` fejléc kell, értéke a `SCREENER_ADMIN_TOKEN` env változó. Ha nincs beállítva, a végpont le van tiltva. |
| `GET /report` | Statikus HTML-jelentés |
| `GET /docs` | OpenAPI dokumentáció |

## Pontozási modell

Minden kategória az elérhető mutatók súlyozott átlaga. A hiányzó adat nem büntet, de csökkenti a
**lefedettséget** (coverage); 40% alatt a pontszám a középértékhez húz és `low_data_coverage`
zászlót kap, hogy ne tűnjön magabiztosnak.

| Kategória (súly) | Mutatók |
|---|---|
| **Valós használat** (30) | TVL-trend 30 nap és 7 nap, díjbevétel 30 nap (abszolút és trend), díj/TVL éves hozam, napi felhasználók (DefiLlama, Token Terminal DAU-átlag vagy Dune), felhasználói trend 30 nap, bevétel 30 nap (DefiLlama, Token Terminal vagy Dune), **fundamentum vs. ár** (ha az ár nő, de a díj és a TVL nem, büntet) |
| **Tokenomika** (20) | forgó/teljes kínálat aránya, következő unlock mérete a kapitalizációhoz képest és távolsága, éves inflációs ütem az unlock-ütemezésből, van-e kínálati plafon |
| **Csapat és fejlesztés** (20) | commitok 90 nap, aktív kontribútorok 90 nap, utolsó push frissessége, release-ek, auditok száma, DeFiSafety PQR-pontszám, governance-javaslatok 90 nap és átlagos szavazószám (Snapshot) |
| **Likviditás** (15) | 24h forgalom / kapitalizáció, abszolút forgalom, kapitalizáció, tőzsdék száma, átlagos spread |
| **Piros zászlók** (15) | 100 pontból levonás: nincs audit (−30), korábbi exploit (−25/−35 ha egy éven belül), nagy unlock 30 napon belül (−20), kevés forgó kínálat (−15), fejlesztés leállt (−20), extrém hozam >100% APY (−15/−25), gyanús forgalom (−10), TVL-zuhanás (−15), DeFiSafety FAIL, azaz 70% alatti PQR (−15, 50% alatt −25), névtelen csapat (−20), koncentrált tulajdon (−20), mikro kapitalizáció (−10) |

Ha a piros-zászló pontszám 30 alá esik, az összpontszám 45-ben van maximálva, bármilyen jók is a
többi mutatók.

A súlyok és a küszöbök a `config.toml`-ban módosíthatók. A névtelen csapat és a koncentrált
tulajdon automatikusan nem mérhető megbízhatóan, ezért kézi felülírásként adható meg:

```toml
[overrides.valami-protokoll]
anonymous_team = true
concentrated_ownership = true
audited = true      # ha tudod, hogy auditált, de a DefiLlama nem jelöli
exclude = false
notes = "saját megjegyzés"
```

## Adatforrások és korlátok

| Forrás | Kulcs | Megjegyzés |
|---|---|---|
| DefiLlama | nem kell | `/protocols`, `/overview/fees`, `/activeUsers`, `/emissions`, `/hacks`, `/protocol/{slug}`, `yields.llama.fi/pools` |
| CoinGecko | opcionális demo kulcs (`COINGECKO_API_KEY`) | Kulcs nélkül szigorú limit; a részletlekérések száma futásonként korlátozott (`coingecko_details_limit`), és projektenként csak 7 naponta frissül |
| GitHub | opcionális token (`GITHUB_TOKEN`) | Token nélkül 60 kérés/óra, ezért alapból csak 30 projekt/futás |
| Snapshot | nem kell | `hub.snapshot.org/graphql`. A space-t a DefiLlama `governanceID` mezőjéből, ennek híján tippekből (`slug.eth`, `slugdao.eth`, `gov.slug.eth` ...) oldjuk fel és cache-eljük; kézzel: `[overrides.slug] snapshot_space = "x.eth"`. Futásonként `projects_limit` projekt, 7 naponta frissül. |
| Token Terminal | `TOKENTERMINAL_API_KEY` (fizetős csomag) | `api.tokenterminal.com/v2`, Bearer-auth. Projekt-illesztés CoinGecko-id, slug, név vagy egyedi szimbólum alapján (cache-elve; kézzel: `[tokenterminal.project_ids]` vagy `[overrides.slug] tokenterminal_id`). `bulk` mód: metrikánként egy hívás az összes projektre; `per_project` mód: projektenként egy hívás. A metrika-azonosítókat a `/v2/metrics` listával ellenőrzi, a hiányzókra figyelmeztet; `[tokenterminal.metrics]` alatt átnevezhetők vagy `false`-szal kikapcsolhatók. |
| DeFiSafety | nem kell | Nincs dokumentált nyilvános JSON API. Először a webapp lista-végpontját próbálja (`api_url`), név szerint illeszt (verzió- és zárójel-független, a legfrissebb review számít). Ha a lista nem elérhető, a `[defisafety.ids]` slug → riport-id térkép alapján a riportoldalakat értelmezi (végső pontszám, PASS/FAIL, dátum, folyamatverzió). Kézi pontszám: `[overrides.slug] defisafety_score = 85`. |
| Dune | `DUNE_API_KEY` (ingyenes csomag is van) | Nincs általános protokoll-végpont: a `config.toml` `[[dune.queries]]` blokkjaiban adsz meg mentett lekérdezéseket. Az eredmény lekérése olcsó, az újrafuttatás (`execute_if_stale`) kreditet fogyaszt. |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Bot: @BotFather; chat id: írj a botnak, majd `https://api.telegram.org/bot<TOKEN>/getUpdates` |

A figyelt kör: DefiLlama-protokollok legalább `min_tvl_usd` TVL-lel (alapból 2M USD), a legnagyobb
`top_n_by_tvl` (300), kizárva a `exclude_categories` kategóriákat, plusz a friss listázások
kisebb küszöbbel, plusz az `always_include` lista.

### Dune-lekérdezés bekötése

Egy lekérdezés eredménytáblájának egy oszlopa azonosítja a projektet (`match_by`: `slug`, `symbol`,
`gecko_id` vagy `name`, a DefiLlama-adatokhoz illesztve), a többi oszlopot mutatókra képezed:

```toml
[dune]
enabled = true
max_age_hours = 36
execute_if_stale = false

[[dune.queries]]
id = 1234567
match_by = "slug"
match_column = "protocol"
metrics = { users_30d = "active_users_30d", revenue_30d = "revenue_usd_30d", txs_30d = "tx_count_30d" }
```

A szabványos mutatónevek (`users_24h`, `users_30d`, `revenue_30d`, `fees_30d`, `txs_30d`,
`volume_30d`, `holders`) beépülnek a pontozásba, ha a DefiLlama-nál hiányzik az adat; bármilyen más
név csak a projekt oldalán jelenik meg. Több `[[dune.queries]]` blokk is megadható.

### Token Terminal

```toml
[tokenterminal]
enabled = true
mode = "bulk"          # vagy "per_project"
window_days = 30

[tokenterminal.metrics]
# users_daily = "user_dau"   # ha a Token Terminal másképp nevezi; false = kikapcsolás
```

Gyűjtött mutatók a 30 napos ablakra és az előző ablakhoz képesti változás: díj, bevétel, earnings,
tranzakciók (összeg), DAU (átlag), MAU, holderek, TVL, aktív fejlesztők (utolsó érték). Ahol a
DefiLlama-nál hiányzik a díj, bevétel vagy felhasználószám, ezek pótolják; a DAU-trend külön
mutatóként épül a használat-pontszámba. A pontos metrika-azonosítók a csomagodtól függhetnek: az
első futás logja megmondja, melyik nem létezik, és hasonló neveket ajánl.

Még nincs bekötve (tervezett): X / Telegram / Discord hangulat (ez a leggyengébb jel, csak
kiegészítésnek).

## OKX DCA bot összekötése

A `out/dca_candidates.json` (vagy a `/api/dca-candidates` végpont) tartalma:

```json
{
  "day": "2026-11-04",
  "filter": {"min_score": 70, "min_liquidity_score": 50, "min_red_flag_score": 60, "min_mcap_usd": 20000000},
  "candidates": [{"symbol": "XYZ", "name": "...", "gecko_id": "...", "score": 78.2, "mcap": 410000000, "flags": []}]
}
```

A DCA bot ebből olvassa a vásárolható szimbólumokat. A lista csak szűrő: a bot a saját
kockázatkezelésével (összeg, gyakoriság, stop) dolgozzon tovább, és soha ne vegyen olyat, ami
épp kiesett a listáról.

## Fejlesztés és tesztek

```bash
pip install -r requirements-dev.txt -r requirements-web.txt
python -m pytest
```

A tesztek hálózat nélkül futnak: rögzített DefiLlama/CoinGecko/GitHub válaszokkal
(`tests/conftest.py`) a teljes pipeline-t, a pontozást, a riasztásokat, a Telegram-küldést és az
API-t ellenőrzik.

## Könyvtárszerkezet

```
screener/
  config.toml            súlyok, küszöbök, figyelt kör, kézi felülírások
  .env.example           titkok sablonja
  screener/
    cli.py               parancssor
    config.py            config.toml + .env betöltés
    http.py              rate limit, újrapróbálás
    db.py                SQLite séma
    sources/             defillama.py, coingecko.py, github.py, snapshot.py, dune.py, tokenterminal.py, defisafety.py
    pipeline.py          lekérés -> DB -> pontozás
    scoring.py           pontozási modell
    alerts.py            riasztási szabályok
    telegram.py          Telegram-küldés
    export.py            rangsor, figyelőlista, DCA-export, HTML-jelentés
    scheduler.py         napi kör + háttér-ütemező
    web.py               FastAPI REST API + dashboard kiszolgálás
    static/index.html    dashboard
  tests/                 offline tesztek
  Dockerfile, docker-compose.yml
```
