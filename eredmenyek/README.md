# Eredménytábla — élő foci és jégkorong eredmények

Eredmenyek.com / Flashscore-stílusú élő eredmény oldal valós adatokkal (TheSportsDB). Egyetlen `index.html`, nincs build lépés, nincs backend. Nyisd meg a fájlt, vagy a GitHub Pages-en: `https://bitblance.exchange/eredmenyek/`.

## Mi van benne

- **Két sportág:** ⚽ Foci és 🏒 Jégkorong (a `SPORTS` / `LEAGUES` tömb bővítésével új sportág vagy bajnokság adható hozzá).
- **Foci (12 bajnokság):** NB I, NB II, Bajnokok Ligája, Európa-liga, Konferencia-liga, Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Eredivisie, Primeira Liga.
- **Jégkorong (10 bajnokság):** Erste Liga, ICE Hockey League (Fehérvár AV19), Champions Hockey League, KHL, SHL, Liiga, DEL, cseh Extraliga, svájci National League, szlovák Tipos Extraliga.
- **Napi nézet** dátumsávval (±3 nap, naptár), szűrők: Összes / ÉLŐ / Befejezett / Következő / Kedvencek.
- **Élő állapot:** percszám, 45+/90+ hosszabbítás, szünet, harmadok játékidővel, hosszabbítás és büntetők jégkorongban, 5 másodpercenkénti frissítés, gólnál villanó sor és toast értesítés a kedvenc meccseken.
- **Mérkőzés részletek:** összefoglaló (gólok, 11-esek, öngólok, lapok, kiállítások, asszisztok), statisztika, keretek, tabella, H2H.
- **Bajnokság oldal:** Eredmények / Menetrend / Tabella (forma, kiemelt zónák: bajnok, nemzetközi kupa, kiesés, rájátszás).
- **Kedvencek:** bajnokság, csapat és mérkőzés szintjén, `localStorage`-ban tárolva.
- **Sötét / világos téma**, mobilbarát elrendezés (bal menü és részletek overlayként).

## Adatforrás

Az oldal **valós adatokat** a [TheSportsDB](https://www.thesportsdb.com/) nyilvános v1 API-jából tölt, közvetlenül a böngészőből (nincs backend, nincs API-kulcs: az ingyenes „3” tesztkulcsot használja). Lekért végpontok:

| Mire | Végpont | Frissítés |
|---|---|---|
| Liga-azonosítók feloldása név/ország alapján | `search_all_leagues.php?s=Soccer` / `?s=Ice_Hockey` | 24 óra (localStorage) |
| Napi meccslista, állás, státusz | `eventsday.php?d=ÉÉÉÉ-HH-NN&s=…` (két UTC napot kér, helyi dátumra szűr) | ma: 60 mp, múlt: 6 óra, jövő: 30 perc |
| Tabella | `lookuptable.php?l=ID&s=2026-2027` | 10 perc |
| Liga oldal (eredmények / menetrend / H2H) | `eventsseason.php?id=ID&s=…`, tartalék: `eventspastleague` + `eventsnextleague` | 10 perc |
| Mérkőzés események / statisztika / összeállítás | `lookuptimeline.php`, `lookupeventstats.php`, `lookuplineup.php` | élő: 60 mp, befejezett: 24 óra |

A lekérések cache-elve vannak, hogy az ingyenes kulcs (kb. 30 kérés/perc) alatt maradjon a forgalom: a napi nézet percenként 2 kérés, a tabella 10 percenként 1.

**Státuszok:** a szolgáltató státuszkódjai (`1H`, `HT`, `2H`, `ET`, `P`, `FT`, `AET`, `PEN`, hokinál `P1`–`P3`, `OT`, `PT`, valamint `PST`/`CANC`/`ABD`) magyar címkékre fordulnak. Ha a szolgáltató a kezdés után még nem ad élő státuszt, a percszám a kezdési időből **becsült** (`~31'`), és így is jelöli.

**Tartalék:** amelyik bajnokságot a TheSportsDB nem fedi (pl. Erste Liga), vagy ha az API nem érhető el, az oldal automatikusan a determinisztikus szezon-szimulációra vált, és ezt egyértelműen jelzi („szim.” jelvény a liga neve mellett, illetve figyelmeztető sáv a lista tetején; a fejléc színes pöttye zöld = valós, piros = nem elérhető, sárga = kapcsolódás). A ⚙ beállításokban kézzel is átkapcsolható (`?data=sim` URL-paraméterrel is), és saját TheSportsDB (Patreon) kulcs adható meg: azzal több adat jön (eseménylista, statisztika, összeállítások).

## Demo óra

A szimulált bajnokságokhoz a ⚙ beállításokban átállítható a nap virtuális időpontja (pl. 20:30), vagy URL paraméterrel: `index.html?t=20:30`. A valós adatokra ez nem hat (csak a becsült percszámra). További paraméterek: `?sport=hoki`, `?d=2026-11-07`, `?data=sim`.
