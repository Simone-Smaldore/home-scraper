# CLAUDE.md

> Stato: **M1 completa in locale** — fonti, persistenza, giri completo/incrementale, cron
> su GitHub Actions, `backup`. Da fare a mano: `alembic upgrade head` su Neon, primo giro,
> segreti su GitHub, deploy su Vercel.
>
> Questo file è la fonte di verità operativa: raccoglie le decisioni prese e **i motivi
> per cui sono state prese così**. Il piano di progetto in
> [`docs/plan/plan-v1.md`](docs/plan/plan-v1.md) è il documento originale, con gli
> scostamenti registrati man mano; dove i due divergono ha ragione questo. Se trovi una
> divergenza, segnalamela.

## Cos'è questo progetto

**Casa Radar** (nome di lavoro) — raccoglie ogni giorno gli annunci di appartamenti in
vendita a Torino dai portali immobiliari, scarta quelli che non passano i criteri
rigidi, fa leggere gli altri a un LLM che assegna un punteggio e ne estrae i fatti utili,
e li mostra in una **dashboard pubblica** dove ogni casa si flagga come interessante,
media o scartata così che sparisca dalle "nuove".

Progetto personale, un solo utente. Nasce dallo stesso stampo di Food Plan Maker e
Wallet (le cartelle accanto a questa): stesso stack, stesse convenzioni, stesso modo di
documentare. Quando una cosa è identica a là, qui non è rispiegata.

**Vincolo assoluto: tutto gratuito.** Neon free, Vercel Hobby, GitHub Actions, Gemini
free tier.

## Decisioni prese

| Questione | Decisione | Perché |
|---|---|---|
| Fonti V1 | **Subito** e **Immobiliare**, entrambe via API JSON | Idealista sta dietro DataDome e non passa nemmeno con l'impersonazione di Chrome; non vale la V1 |
| Dove gira lo scraper | **GitHub Actions**, 2 volte al giorno | Processo Python vero, senza il limite di 10–60 s di una function Vercel. Il free tier concede 2.000 minuti al mese, ne useremo ~100 |
| Accesso | **Nessuno.** Lettura e flag aperti a chi ha l'URL | Scelta esplicita: un solo utente, niente da proteggere che valga un login |
| LLM | Gemini via chiave AI Studio, REST puro, cascata `2.5-flash → 2.5-flash-lite → gemma-3-27b-it` sui 429 | Gratis; la cascata è rete di sicurezza, non percorso normale |
| Chi valuta cosa | **Il filtro rigido è codice**, l'LLM giudica solo chi lo passa | Deterministico e testato dove si può; l'LLM non spende quota su case fuori budget |
| Criteri | Costanti in `domain/criteria.py` | Un utente: cambiarli è un commit, non un form |
| HTTP nello scraper | **`curl_cffi`** con `impersonate="chrome"`, non httpx/urllib | Vedi "Le fonti": è la firma TLS |
| Interfaccia | Design da produrre; frontend è l'**ultima** milestone | Fino ad allora `/_stato` e token segnaposto |

## Comandi

Verificati a M0. Il frontend è un **npm workspace**: `npm` si lancia dalla radice.

```bash
# installazione (una tantum)
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
npm install

# lo scraper — scrive su DATABASE_URL
cd backend && python -m scripts.scrape                  # incrementale: si ferma alla prima pagina di annunci noti
cd backend && python -m scripts.scrape --full           # completo: tutte le pagine, segna chi è sparito
cd backend && python -m scripts.scrape --source subito  # una fonte sola
cd backend && python -m scripts.backup [--no-raw]       # esporta tutto in JSON

# lo scraper in prova a vuoto — niente database, stampa e basta
cd backend && python -m scripts.scrape --dry-run --no-llm --source subito            # 2 pagine
cd backend && python -m scripts.scrape --dry-run --no-llm --source subito --all      # tutto Torino
cd backend && python -m scripts.scrape --dry-run --no-llm --source immobiliare --show-rejected

# dev server backend — http://127.0.0.1:8000, docs su /api/docs
cd backend && uvicorn app.main:app --reload

# dev server frontend — http://localhost:5173, proxy /api verso uvicorn
npm run dev

# build frontend (produce frontend/dist)
npm run build

# test
cd backend && pytest

# typecheck frontend
npm run typecheck

# migrazioni DB — a mano dalla tua macchina contro Neon, mai in fase di deploy
cd backend && alembic upgrade head
cd backend && alembic revision --autogenerate -m "descrizione in inglese"
```

Su Windows, se i caratteri non ASCII escono rotti sul terminale: `set PYTHONUTF8=1`.

Non lanciare comandi che non sono elencati qui senza chiedere prima.

## Struttura del repository

```
backend/app/
  config.py, db.py, main.py    rispecchiati da food-plan-maker
  models/                      SQLAlchemy: listing + price_history, review, scrape_run
  schemas/                     Pydantic, input e output delle API
  api/                         router HTTP: health (M0), listings/reviews/runs (M3)
  store/                       ← scrive sul database: l'upsert e il ciclo di vita
  domain/                      ← puro: zero FastAPI, zero SQLAlchemy, zero HTTP
    vocabulary.py                enum chiusi: fonte, zona, box, stato, review
    listing.py                   il Listing normalizzato, comune a tutte le fonti
    criteria.py                  i criteri e il filtro rigido
    auction.py                   riconosce le aste dal testo
    format.py                    "250.000 €", "85 mq"
  sources/                     ← una per sito: fa HTTP, restituisce Listing
    base.py                      PoliteClient (curl_cffi), Blocked, protocollo
    subito.py
    immobiliare.py
  llm/                         (M2) l'unico posto che parla con Gemini
backend/scripts/               scrape.py (il runner), backup.py, _common.py
backend/tests/                 pytest; fixtures/ con JSON veri dei siti
backend/migrations/            Alembic
frontend/src/                  React + Vite + Tailwind 4; a M0 solo /_stato
.github/workflows/scrape.yml   il cron: due giri al giorno
api/index.py                   entrypoint Vercel, monta l'app FastAPI
requirements.txt               runtime dell'API — la legge Vercel, sta in root
requirements-scraper.txt       API + curl_cffi — GitHub Actions e la tua macchina
requirements-dev.txt           tutto + uvicorn, pytest
docs/plan/plan-v1.md           il piano di progetto
```

## Le fonti

Stanno in `backend/app/sources/`, una per sito. Fanno rete e restituiscono `Listing`;
non toccano il database — il runner dice loro quali id conosce già tramite una callback,
ed è tutto ciò che serve per sapere quando smettere di sfogliare.

⚠️ **Il client HTTP è `curl_cffi` che impersona Chrome, e non è una preferenza.** Subito
sta dietro Akamai, che riconosce **la firma TLS** dell'handshake: `urllib`, httpx con
qualsiasi contesto SSL e cifrari personalizzati prendono "Access Denied" con gli stessi
identici header che a curl passano. Misurato il 3 settembre 2026, non supposto. Per lo
stesso motivo **non si scrive uno User-Agent a mano**: l'impersonazione ne manda uno
coerente con l'handshake, e uno UA da browser sopra un handshake non da browser è esso
stesso un segnale da bot.

⚠️ **Un 403 o 429 chiude il giro di quella fonte e non si riprova.** `Blocked` sale fino
al runner, che lo registra e passa alla fonte successiva. Martellare un sito che ha appena
detto no è esattamente il comportamento che alza il muro per sempre. Le buone maniere sono
anche autodifesa: due giri al giorno, pausa di 1–3 s fra le richieste, nessun
parallelismo, mai una pagina di dettaglio quando l'elenco già dice tutto.
⚠️ **Subito manda il limite di frequenza come un 500** con dentro `[429 Too Many
Requests]`: successo il primo giorno, dopo una giornata di sondaggi. `PoliteClient` lo
riconosce e lo tratta da `Blocked`. Se ti capita in sviluppo, smetti per un'ora: non è un
bug da riprovare.

**Subito** — `hades.subito.it/v1/search/items`, la stessa API JSON del sito. Nessun
cookie né token. Cento annunci a richiesta con tutti i campi strutturati, il testo
intero, le foto, l'inserzionista. Torino è `r=2` (Piemonte), `ci=6` (provincia),
`to=001272` (comune), ordinati per data; le 14 zone sono le chiavi `001272-N` mappate in
`subito.ZONES`. Circa un annuncio su cinque **non ha zona**: passa con l'avviso "zona non
indicata" invece di essere scartato per un dato mancante.
⚠️ **Privato o agenzia si legge da `advertiser.company`**, non da `/nosalesman`: quella è
la casella "non contattatemi, agenzie", e la spunta anche un terzo delle agenzie. ⚠️ Il
telefono non c'è mai nell'elenco (`phone: "0"`): si estrae quando compare nel testo.

**Immobiliare** — le pagine HTML sono dietro DataDome (403 anche impersonando Chrome), ma
l'API interna `api-next/search-list/listings/` **risponde senza alcun cookie**. Non le si
passano id geografici — quelli veri (`fkRegione`, `idProvincia`, `idComune`) sono
indocumentati — ma **il riquadro di coordinate** che usa la mappa del sito
(`minLat/maxLat/minLng/maxLng`), più `path` e `paramsCount` che senza danno 500. Filtra
**lato server** (`prezzoMassimo`, `superficieMinima`, `localiMinimo`) e ordina per data di
modifica, 25 a pagina.
⚠️ **Il riquadro è quello delle quattro zone cercate, non tutta Torino** (`TARGET_BBOX`,
misurato sui dati veri). Il primo giro completo da GitHub ha chiesto tutta la città, 109
pagine, e alla 65ª Immobiliare ha risposto **418 "I'm a teapot"**: conta le richieste. Il
riquadro stretto costa ~45 pagine (1.100 annunci), la pausa per Immobiliare è 2–5 s (`scrape.PAUSES`), e
il 418 è un `Blocked` come gli altri. Quel che il riquadro prende dai bordi — altre zone,
Grugliasco — lo scartano il filtro (zona) e `parse_result` (`city`). ⚠️ Le agenzie hanno
**il telefono in chiaro** (`advertiser.agency.phones`); "senza `agency`" è un privato.
`elevator` è `True` o assente, mai `False`; balcone e terrazzo stanno in `ga4features`;
il piano è una sigla (`T`, `R`, `S`, o `S, 2` per i multilivello).

⚠️ **Le macrozone di Immobiliare non coincidono con le 14 di Subito** ("Lingotto, Nizza
Millefonti" ne cavalca due): la mappa in `immobiliare.MICROZONES` guarda prima la
microzona, `MACROZONES` è il ripiego. Una zona non mappata finisce nel log come warning e
il listing passa con "zona non indicata".

⚠️ **Da Immobiliare il database vede solo annunci già dentro budget, mq e locali**, perché
il filtro è del server. La mediana di zona di `domain/pricing.py` sarà una mediana di
case *comparabili*, non del mercato intero. Va bene per il lavoro che deve fare.

**Le aste si segnalano, non si scartano** (`is_auction`, da `domain/auction.py`, che
riconosce "all'asta", "asta giudiziaria", "tribunale di" — non la parola "asta" da sola,
che sta anche in "fantastica").

## Il runner e i due giri

`scripts/scrape.py`. Ogni fonte ha la sua riga in `scrape_run` e il suo `try`: un blocco su
un sito non costa il giro all'altro. Ogni 50 annunci un commit, così un blocco a metà
tiene quello che è arrivato prima. Un giro non `ok` fa uscire con codice 1: su GitHub
Actions il run diventa rosso e la mail arriva — **quello è l'allarme**.

⚠️ **Due tipi di giro, e la differenza non è cosmetica.** L'incrementale legge dal più
recente e si ferma alla prima pagina fatta solo di id già noti, quindi *non può sapere*
cosa è sparito più in là. Il completo (`--full`) legge tutto ed è **l'unico autorizzato a
dichiarare un annuncio sparito**: chi non compare prende `missed_runs += 1`, a 2 diventa
`is_active = false`. Mai cancellato — è storico, e la mediana di zona lo usa. Ricompare →
torna attivo e il contatore si azzera. Il cron del mattino è completo, quello della sera
incrementale. ⚠️ Un giro bloccato o fallito **non** disattiva nessuno, anche se era
`--full`: un annuncio che non hai potuto vedere non è un annuncio sparito.

⚠️ **Una query per pagina, non per annuncio.** Il runner gira negli USA e Neon sta a
Francoforte: ~100 ms a query, e il primo giro con una `SELECT` per annuncio ha impiegato
11 minuti. `fetch_existing` carica le righe di un lotto di 50 in un colpo e `upsert` le
riceve già in mano.

**L'upsert sta in `store/listings.py`** ed è l'unico posto che scrive `listing`: nuova riga
alla prima vista con il primo prezzo in `price_history`; a ogni vista `last_seen_at` si
muove, i campi si aggiornano, un prezzo cambiato aggiunge una riga a `price_history`. Il
verdetto del filtro viaggia con l'annuncio (`passes_hard_filter`, `filter_rejections`,
`filter_unknowns`) e si riaggiorna a ogni vista. **`review` non viene mai toccata** da un
ri-scraping.

**GitHub Actions** (`.github/workflows/scrape.yml`): `30 5 * * *` completo, `30 17 * * *`
incrementale, UTC — l'ora italiana scivola di uno fra estate e inverno, e non vale una
correzione. `workflow_dispatch` con la casella "giro completo". `concurrency: scrape`
perché due giri insieme farebbero a gara sulle stesse righe. Segreti: `DATABASE_URL`,
`GEMINI_API_KEY`. Installa `requirements-scraper.txt`, non `requirements.txt`.

## Il vocabolario delle zone

`Zone` in `domain/vocabulary.py` è la partizione di Torino **come la fa Subito**, 14 aree.
È il vocabolario condiviso: Subito lo definisce nativamente, Immobiliare userà quartieri
più fini che si ripiegano su questi. Le zone cercate sono quattro (`TARGET_ZONES` in
`criteria.py`): Cenisia / San Paolo · Cit Turin / San Donato / Campidoglio ·
Crocetta / San Secondo · Lingotto / Santa Rita. ⚠️ L'ultima contiene anche Lingotto, che
non è nella ricerca: è l'LLM che raffina dall'indirizzo, non il filtro.

## I criteri e il filtro rigido

`domain/criteria.py`. Due livelli, e la distinzione è il cuore del prodotto:

- **Rigido, codice, prima dell'LLM**: prezzo ≤ 250.000 € (e ≥ 20.000 €: sotto è un
  affitto nella categoria sbagliata, visto davvero), superficie ≥ 80 mq, locali ≥ 3,
  zona fra le quattro, ascensore e balcone **solo se il sito dice esplicitamente "no"**.
- **Morbido, LLM, nel punteggio**: salone, stanza per una cameretta futura, stato,
  piano, prezzo/mq contro la mediana di zona.
- **Da segnare, non da giudicare**: privato/agenzia, box compreso, telefono.

⚠️ **"Sconosciuto" non è "no".** Un campo vuoto passa e finisce in `Verdict.unknowns`
("ascensore non indicato"), così l'LLM legge la descrizione e la dashboard dice "da
verificare". Scartare per un dato mancante butterebbe metà delle case buone. È il test
intoccabile di `test_domain_criteria.py`, insieme al suo gemello: nessun annuncio fuori
budget, mq, locali o zona passa mai.

Le ragioni di scarto e gli avvisi sono **stringhe italiane**, perché finiscono a schermo.

## Convenzioni di lavoro e di codice

Identiche a Food Plan Maker: pianificare prima, commit piccoli con messaggi in inglese
all'imperativo, niente commit automatici, niente dipendenze nuove senza chiedere, non
riscrivere codice fuori dal task, chiedere se è ambiguo.

`domain/` non importa **nulla** di FastAPI, SQLAlchemy né `curl_cffi`: riceve `Listing`
e restituisce oggetti semplici. `sources/` fa rete e restituisce `Listing`; `llm/` farà
rete e restituirà testo; `domain/` decide. È ciò che rende testabili senza rete e senza
database le tre cose che possono sbagliare: la normalizzazione, il filtro, il parsing del
verdetto.

Python `snake_case`, moduli al singolare; React `PascalCase`; tabelle al singolare
(`listing`, `price_history`), chiavi esterne `<tabella>_id`. Codice e commenti in inglese,
testi per l'utente in italiano, sentence case, `·` come separatore, `1.234 €`, `85 mq`.

⚠️ **Prezzi in euro interi**, non in centesimi: gli annunci non hanno decimali, e la
regola dei centesimi di Wallet vale per gli importi che si sommano, non per quelli che si
leggono.

**Test.** Su `domain/` e sulla normalizzazione delle fonti, con JSON veri salvati in
`tests/fixtures/` — mai rete. Non si testano i CRUD né i componenti React.

**Errori.** `Blocked` e `SourceError` in `sources/base.py`; un annuncio malformato viene
saltato **con un warning nel log**, mai in silenzio, e non ferma il giro.

## Manutenzione del database

`backend/scripts/`, `python -m scripts.<nome>`. Dicono a quale database parlano prima di
fare qualsiasi cosa (`_common.announce`). `backup` esporta annunci, storico prezzi, review
e giri in JSON — `--no-raw` per un file piccolo senza i payload dei siti. Le review sono
la cosa irrecuperabile. ⚠️ `backup-*.json` è in `.gitignore`.

⚠️ `get_engine` passa `connect_timeout` **solo a Postgres**: lo scraper si prova
end-to-end su un SQLite temporaneo (`DATABASE_URL=sqlite:///C:/…/x.db`, poi `alembic
upgrade head`), e SQLite quell'argomento lo rifiuta.

## Variabili d'ambiente

| Nome | A cosa serve |
|---|---|
| `DATABASE_URL` | Neon, **host pooled** (con `-pooler`) |
| `ENVIRONMENT` | `development` o `production` |
| `GEMINI_API_KEY` | solo lo scraper; vuota → valutazione saltata, e il giro lo dice |
| `GEMINI_MODELS` | la cascata, separata da virgola |

⚠️ **La chiave Gemini non arriva mai su Vercel**: la function non chiama il modello. Sta
in GitHub Actions e in `backend/.env`.

## Cose da non fare

- Non committare `.env`, chiavi, dump di database
- Non modificare la configurazione di build/deploy senza chiedere
- Non introdurre servizi a pagamento: l'hosting deve restare interamente gratuito
- Non mettere logica di dominio nei router, nelle fonti o nei componenti React
- Non riprovare una richiesta dopo un 403/429, e non aggiungere parallelismo allo scraper
- Non fissare uno User-Agent a mano nel client HTTP
