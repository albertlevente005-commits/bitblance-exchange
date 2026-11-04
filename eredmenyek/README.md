# Eredménytábla — élő foci és jégkorong eredmények

Eredmenyek.com / Flashscore-stílusú élő eredmény oldal. Egyetlen `index.html`, nincs build lépés és nincs külső függőség (a betűtípuson kívül). Nyisd meg a fájlt, vagy a GitHub Pages-en: `https://bitblance.exchange/eredmenyek/`.

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

A jelenlegi verzió **determinisztikus szezon-szimulációt** használ: minden bajnoksághoz valós csapatnevekkel (2025/26-os kiírások) körmérkőzéses menetrend készül, az eredmények és események (gólszerző, perc, lapok) a mérkőzés azonosítójából seedelt véletlenből származnak, és a valós órához képest „játszódnak le”. Ebből következnek a tabellák is, így minden nézet konzisztens.

Ez azt jelenti, hogy nincs API-kulcs és nincs hálózati kérés. Egy valós adatszolgáltató (pl. API-Football, SportMonks, TheSportsDB) bekötéséhez a `season()`, `result()` és `phase()` függvényeket kell adatforrásra cserélni; a renderelő réteg változatlanul használható.

## Demo óra

Hogy napközben is lássál élő mérkőzést, a ⚙ beállításokban átállítható a nap virtuális időpontja (pl. 20:30), vagy URL paraméterrel: `index.html?t=20:30`. További paraméterek: `?sport=hoki`, `?d=2026-11-07`.
