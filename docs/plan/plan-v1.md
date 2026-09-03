# Piano — Casa Radar V1

> Prima stesura, 3 settembre 2026, prima di qualsiasi riga di codice. Stessa forma dei piani
> di Food Plan Maker e Wallet: descrive le **intenzioni**; quando il codice esisterà, le regole
> staranno in `CLAUDE.md` e gli scostamenti si registrano qui.

## Context

Cerchi casa a Torino: 3–4 locali, da 80 mq, salone e una stanza in più per una futura
cameretta, fino a 250.000 €, in San Paolo, Santa Rita, Cit Turin, Cenisia, Crocetta, San
Donato, Campidoglio. Ascensore e balcone/terrazzo irrinunciabili; "privato o agenzia" e "box
compreso o no" vanno **segnati**, non filtrati.

Oggi questa ricerca vuol dire aprire tre siti ogni giorno, riscorrere annunci già visti e
rileggere descrizioni per capire se il taglio va bene. L'app deve fare quel giro al posto tuo,
una o due volte al giorno: raccoglie gli annunci di vendita, scarta quelli che non passano i
criteri rigidi, fa leggere gli altri a un LLM che assegna un punteggio e tira fuori i fatti che
contano, e ti mostra tutto in una **dashboard pubblica** dove flaggi ogni casa come
interessante / media / scartata così che sparisca dalle "nuove".

Vincolo assoluto, ereditato: **tutto gratuito**. Neon, Vercel Hobby, GitHub Actions, Gemini
free tier.

### Cosa hanno detto le prove fatte oggi (prima del piano)

| Sito | Pagina HTML | API interna | Verdetto |
|---|---|---|---|
| **Subito** | 200 | `hades.subito.it/v1/search/items` **aperta**: prezzo, mq, locali, piano, ascensore, balcone, classe energetica, stato, riscaldamento, `nosalesman` (privato), foto, testo | **Fonte primaria.** Torino = `r=2`, `ci=6`, `to=001272`, con le zone (`hasZone: true`) |
| **Immobiliare** | 403 **DataDome** | `api-next/search-list/listings/` risponde **senza cookie** al riquadro di coordinate della mappa, con filtri lato server (prezzo, mq, locali) e ordinamento per data | **Fonte secondaria, risolta a M0** — vedi lo scostamento sotto |
| **Idealista** | 403 DataDome | — | **Fuori dalla V1**, deciso |

Il numero di telefono: **nessuno dei tre siti lo espone negli elenchi** (Subito manda
`phone: "0"`, la rivelazione richiede login o app). Si estrae **quando compare** nel testo
dell'annuncio o nei dati dell'inserzionista (agenzie su Immobiliare), e la dashboard dice
"non disponibile" negli altri casi. Non è una promessa del prodotto.

## Decisioni prese

| Questione | Decisione |
|---|---|
| Nome di lavoro | **Casa Radar** (si cambia in un commit, è solo testo) |
| Fonti V1 | Subito + Immobiliare. Idealista no |
| Dove gira lo scraper | **GitHub Actions**, workflow schedulato **2 volte al giorno** (07:30 e 19:30 ora italiana). È un processo Python vero, senza il limite di 10–60 s di Vercel |
| Accesso | **Nessuno.** Dashboard pubblica, scritture (flag) aperte a chi ha l'URL. Niente magic link, niente `app_user`, niente Brevo |
| LLM | **Gemini** via chiave AI Studio, chiamate REST. Cascata sui 429: `gemini-2.5-flash` → `gemini-2.5-flash-lite` → `gemma-3-27b-it`. Dinamica per esecuzione, e ogni valutazione ricorda quale modello l'ha prodotta |
| Cosa valuta l'LLM | **Solo gli annunci che passano il filtro rigido.** Il filtro è codice deterministico e testato; l'LLM giudica ciò che il codice non sa leggere (salone, cameretta, stato reale, contesto) e non spende quota su case fuori budget |
| Criteri di ricerca | Costanti in `domain/criteria.py`. Un utente solo: cambiarli è un commit, non un form |
| Stack | Identico ai due progetti precedenti: React + TS + Vite + Tailwind 4 / FastAPI + SQLAlchemy 2 + Alembic / Postgres su Neon / Vercel Hobby. **Scheletro rispecchiato da food-plan-maker**, non riscritto |
| Interfaccia | Il design arriva da te in seguito; il frontend è l'**ultima** milestone. Fino ad allora `/_stato` e i token segnaposto |
| Ordine di lavoro | Prove sulle fonti **prima di tutto** (è il tuo dubbio), poi persistenza, poi LLM, poi API, poi dashboard |

## I criteri

`backend/app/domain/criteria.py`, puro e testato. Due livelli, e la distinzione è il cuore
del prodotto:

**Rigido — scarta senza chiedere all'LLM**

- prezzo ≤ 250.000 €
- superficie ≥ 80 mq
- locali ≥ 3
- zona ∈ {San Paolo, Santa Rita, Cit Turin, Cenisia, Crocetta, San Donato, Campidoglio}
- ascensore: scartato **solo se il sito dice esplicitamente "no"**; sconosciuto passa
- balcone/terrazzo: stessa regola

⚠️ **"Sconosciuto" non è "no".** Gli annunci sono compilati male e un campo vuoto è la norma:
scartare per un dato mancante butterebbe metà delle case buone. Il dubbio va all'LLM, che
legge la descrizione, e se nemmeno lì c'è scritto lo segnala come "da verificare".

⚠️ **La zona si legge dal dato strutturato del sito quando c'è**, e dal testo solo come
ripiego. Subito ha le zone di Torino nella sua API; Immobiliare ha i quartieri. La mappa
"nome della zona sul sito → zona dei criteri" sta in `criteria.py` per ogni fonte, perché
"Cit Turin" su un sito può essere "San Donato / Cit Turin" sull'altro.

**Morbido — lo giudica l'LLM, entra nel punteggio**

- c'è un salone (e quanto è grande)
- c'è una stanza in più per una cameretta futura
- stato dell'immobile (da ristrutturare / abitabile / ristrutturato)
- piano e luminosità
- prezzo al mq rispetto alla **mediana della zona calcolata sui nostri stessi annunci**
- classe energetica, riscaldamento, spese condominiali se scritte

**Da segnare, non da giudicare**

- asta giudiziaria (deciso a M0: si segnala, non si scarta)
- privato o agenzia (Subito: `nosalesman`; Immobiliare: tipo di inserzionista)
- box/posto auto compreso, a parte, o assente
- telefono, se compare

## Struttura del repository

```
backend/
  app/
    main.py, config.py, db.py       ← rispecchiati da food-plan-maker
    models/     listing.py, evaluation.py, review.py, scrape_run.py
    schemas/    listing.py, review.py, health.py
    api/        health.py, listings.py, reviews.py, runs.py
    domain/     ← puro: zero FastAPI, zero SQLAlchemy, zero HTTP
      listing.py      il dataclass Listing normalizzato, comune a tutte le fonti
      criteria.py     criteri rigidi, mappa delle zone, filtro
      pricing.py      prezzo/mq e mediana per zona
      evaluation.py   forma del verdetto dell'LLM, parsing e validazione della risposta
      vocabulary.py   enum chiusi: fonte, stato di revisione, condizione, ecc.
    sources/    ← un modulo per sito: fa HTTP, restituisce Listing
      base.py         protocollo Source, politeness (pause, UA, retry)
      subito.py
      immobiliare.py
    llm/        ← l'unico posto che parla con Gemini
      client.py       REST, cascata dei modelli, conteggio
      prompts/evaluate_v1.md   il prompt, versionato come file
  migrations/
  scripts/      scrape.py (il runner), backup.py, doctor.py, reset.py
  tests/        domain/ e llm/parsing, niente rete
frontend/src/
  api/          client.ts + cache.ts (rispecchiato)
  features/     listings/ (elenco, filtri, dettaglio), shell/, debug/
  lib/          validation.ts, online.ts, format.ts (euro, mq, date relative)
  styles/       tokens.css — segnaposto fino al design
api/index.py            entrypoint Vercel (copiato)
.github/workflows/scrape.yml   il cron
vercel.json, requirements.txt, requirements-dev.txt, package.json (copiati e adattati)
```

**La regola che tiene**: `domain/` non importa nulla di FastAPI, SQLAlchemy, né `curl_cffi`.
`sources/` fa rete e restituisce `Listing`; `llm/` fa rete e restituisce testo; `domain/`
decide. È ciò che rende testabili senza rete e senza database le tre cose che possono
sbagliare: la normalizzazione, il filtro, il parsing del verdetto.

⚠️ I tre documenti oggi nella cartella (`CLAUDE.md` e `README.md` di Food Plan Maker,
`docs/plan/plan-v1.md` di Wallet) **sono riferimenti, non il progetto**: a M0 vengono
sostituiti dai documenti di questo, e il piano di Wallet si toglie.

## Modello dati

```
listing               id, source (subito|immobiliare), source_id, url,
                      title, description, price_eur (int), size_sqm, rooms, bathrooms,
                      floor, total_floors, elevator, balcony, garage (incluso|a_parte|no|null),
                      condition, energy_class, heating, year_built, condo_fees_eur,
                      zone (dei criteri), zone_raw (del sito), address, lat, lng,
                      is_private, advertiser_name, phone, images (JSON),
                      published_at, first_seen_at, last_seen_at, is_active,
                      passes_hard_filter, raw (JSON)
                      UNIQUE (source, source_id)

price_history         listing_id, price_eur, seen_at

evaluation            listing_id, model, prompt_version, score (0–100), summary,
                      pros (JSON), cons (JSON), facts (JSON: salone, cameretta,
                      stato, privato, box, telefono, da_verificare[]),
                      created_at

review                listing_id (UNIQUE), status (nuova|interessante|media|scartata),
                      note, updated_at

scrape_run            id, source, started_at, finished_at, status, fetched, new,
                      updated, deactivated, evaluated, model_used, error
```

Le scelte che contano:

- **`raw` si conserva.** È il JSON del sito così com'è arrivato: se cambio il prompt o la
  normalizzazione, si rivaluta tutto senza rifare lo scraping — che è la parte fragile.
- **`price_history` è una tabella, non una colonna.** Un ribasso di prezzo è il segnale più
  utile che esista in una ricerca lunga, e la dashboard lo mostra ("−15.000 € dal 12/08").
- **`is_active`**: un annuncio che non compare più in due giri consecutivi è venduto o
  ritirato. Non si cancella — è storico, e serve alla mediana di zona — ma sparisce dalla
  lista di default.
- **`evaluation` è append-only**, una riga per modello/versione del prompt: la dashboard
  mostra l'ultima, ma cambiare prompt non riscrive i giudizi vecchi.
- **`review` è separata dal listing** e nasce solo al primo flag: "nuova" è l'assenza di una
  riga. Un ri-scraping non la tocca mai.
- **Prezzi in euro interi**, non in centesimi: gli annunci non hanno decimali e la lezione
  di Wallet sui centesimi vale per gli importi che si sommano, non per quelli che si leggono.
- **Nessuna tabella utenti, sessioni, token.** Non c'è accesso.
- Non c'è dedup fra siti in V1: la stessa casa su Subito e Immobiliare sono due righe.
  Un'euristica (stessa zona + stessi mq + stesso prezzo → "possibile doppione") è V1.5,
  quando ci saranno dati veri per tararla.

## Lo scraper

`python -m scripts.scrape [--source subito|immobiliare] [--no-llm] [--dry-run]`, lanciato
dal workflow. Un giro per fonte:

1. Scorre l'elenco di Torino ordinato per data, **le sole pagine necessarie**: si ferma
   quando una pagina intera è fatta di annunci già visti nel giro precedente.
2. Per ogni annuncio: normalizza → `Listing` → upsert su `(source, source_id)`;
   `last_seen_at = now`; se il prezzo è cambiato, riga in `price_history`.
3. Applica il filtro rigido; chi passa ed è **senza valutazione** va all'LLM.
4. Chi non è comparso in questo giro né nel precedente → `is_active = false`.
5. Scrive `scrape_run` con i contatori. Un errore su una fonte **non ferma l'altra**.

**Politeness, che è anche autodifesa**: due giri al giorno, pause di 1–3 s fra le
richieste, un solo User-Agent realistico e stabile, `Accept-Language: it-IT`, nessuna
parallelizzazione, mai il dettaglio di un annuncio che l'elenco già descrive. Un 403 o un
429 chiude il giro di quella fonte con `status = blocked` e lo dice: **non si riprova in
loop**, che è esattamente il comportamento che fa alzare il muro.

⚠️ **Il primo giro è diverso**: non c'è un "già visto", quindi scorre tutto Torino per i
criteri (poche centinaia di annunci) e valuta solo quelli che passano. Va lanciato a mano,
con `--dry-run` prima.

**GitHub Actions**: `.github/workflows/scrape.yml`, `schedule` con due cron UTC, più
`workflow_dispatch` per lanciarlo a mano. Segreti: `DATABASE_URL`, `GEMINI_API_KEY`.
Runner `ubuntu-latest`, Python 3.12, `pip install -r requirements.txt`. Un giro dura pochi
minuti: il piano gratuito ne concede 2.000 al mese, ne useremo ~100.

⚠️ **Immobiliare, il piano B già deciso.** Se in M0 l'`api-next` richiede un cookie
DataDome anche da IP di datacenter, la fonte resta nel codice ma **disattivata** (`enabled =
false` in `config.py`), la dashboard dice "solo Subito", e si riapre come V1.5 con
Playwright dal tuo PC. Non si blocca la V1 per una fonte.

## L'LLM

`backend/app/llm/client.py`: REST puro contro
`generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, nessun SDK.

- **Cascata**: `GEMINI_MODELS=gemini-2.5-flash,gemini-2.5-flash-lite,gemma-3-27b-it`. Un
  429 (`RESOURCE_EXHAUSTED`) sposta **il resto del giro** sul modello successivo; la
  valutazione registra `model`. Finiti tutti, gli annunci restano senza valutazione e li
  riprende il giro dopo — la dashboard li mostra come "in attesa di valutazione", non li
  nasconde.
- **Il prompt è un file**, `prompts/evaluate_v1.md`, con i criteri scritti in chiaro e
  la rubrica del punteggio. Riceve i campi strutturati **e** il testo dell'annuncio **e** il
  prezzo/mq contro la mediana di zona (calcolato da `domain/pricing.py`, non dal modello:
  l'aritmetica la fa il codice).
- **Risposta JSON con schema** dove il modello lo supporta (i Gemini), parsing tollerante
  dove no (Gemma): estrae il primo oggetto JSON dal testo, poi **Pydantic valida**
  (`score` 0–100, campi noti). Se non valida, la valutazione non si scrive e si riprova al
  giro dopo. Mai un punteggio inventato da un default.
- **La chiave sta solo nell'ambiente** di GitHub Actions e in `backend/.env`. Vercel non
  la vede: la function non chiama mai l'LLM.
- Quote free tier (settembre 2026, da riverificare): Flash ~250 richieste/giorno, Flash-Lite
  ~1.000, Gemma ~14.000. Con il filtro rigido a monte, un giro ne chiede decine, non
  centinaia: la cascata è una rete di sicurezza, non il percorso normale.

## L'API

Tutta pubblica, nessun `deps.py` di sessione.

| Rotta | Cosa fa |
|---|---|
| `GET /api/health` | come negli altri progetti, `redact_dsn` da Wallet |
| `GET /api/listings` | elenco con filtri: `status`, `source`, `zone[]`, `price_max`, `size_min`, `rooms_min`, `score_min`, `private_only`, `garage`, `active_only`, `sort` (score, prezzo, data, ribasso). Porta l'ultima valutazione, la review e il delta prezzo |
| `GET /api/listings/{id}` | dettaglio: tutto + storico prezzi + tutte le valutazioni |
| `PUT /api/listings/{id}/review` | `{status, note}` — upsert |
| `GET /api/runs/latest` | ultimo giro per fonte: la dashboard scrive "aggiornata alle 07:31 · Subito ok · Immobiliare bloccato" |

⚠️ **Il filtro sta in SQL, non in Python.** Al contrario di Wallet: qui l'elenco cresce di
decine di righe al giorno per mesi e la dashboard chiede sempre una fetta. Le regole di
*cosa* mostrare sono `WHERE`, non giudizi di dominio.

## La dashboard

Ultima milestone, sul design che fornirai. Quello che deve esserci, indipendentemente dal
design:

- **Vista di default = "Nuove"**: attive, passano il filtro, valutate, senza review, per
  punteggio. È la schermata del mattino.
- **Tre bottoni per riga**: interessante / media / scartata. Un tocco, ottimistico come la
  lista della spesa di Food Plan Maker (`api/cache.ts` + una funzione di trasformazione
  locale), con rollback dichiarato se fallisce.
- **Filtri** in chip (`ChipRow` rispecchiato): stato, fonte, zona, solo privati, con box,
  prezzo/mq/locali/score come intervalli.
- **Riga**: foto, titolo, zona, prezzo (+ ribasso se c'è), mq · locali · piano, badge
  privato/agenzia e box, punteggio, prima riga del verdetto.
- **Dettaglio**: il verdetto intero con pro/contro e "da verificare", i fatti estratti, il
  telefono se c'è, lo storico prezzi, le foto, il link al sito.
- **Testata**: "aggiornata alle …" da `/api/runs/latest`, in rosso se una fonte è bloccata.
- Mobile-first, desktop a tabella. Copy italiano, sentence case, `·` come separatore,
  `1.234 €` e `85 mq`.
- Nessuna PWA in V1: si apre dal browser, e non c'è offline da gestire.

## Milestone

**M0 — Le fonti, e lo scheletro.** Prima le fonti, perché è il dubbio che decide la forma di
tutto il resto:

1. `sources/subito.py` + `domain/listing.py` + `domain/criteria.py`: `python -m
   scripts.scrape --source subito --dry-run --no-llm` stampa gli annunci di Torino
   normalizzati e dice quali passano il filtro e perché no gli altri. Test sulla
   normalizzazione con JSON reali salvati in `tests/fixtures/`.
2. `sources/immobiliare.py` ✅. **Scostamento**: non servono né cookie né id geografici.
   La richiesta della mappa catturata dal browser ha rivelato il riquadro di coordinate
   (`minLat/maxLat/minLng/maxLng`), che l'endpoint `listings` accetta al posto della
   geografia; `prezzoMassimo`, `superficieMinima`, `localiMinimo` filtrano lato server.
   Nessun piano B necessario. ⚠️ Di conseguenza da questa fonte entrano solo annunci già
   dentro i criteri numerici: la mediana di zona sarà una mediana di case comparabili.
3. Lo scheletro rispecchiato: `main.py`, `config.py`, `db.py`, `api/index.py`,
   `vercel.json`, `requirements*.txt`, `package.json`, `/_stato`, Alembic a vuoto. Deploy
   su Vercel, `/_stato` verde. Riscrittura di `CLAUDE.md` e `README.md` per questo
   progetto.

**M1 — Persistenza e cron.** Modelli, prima migrazione, `scripts/scrape.py` completo
(upsert, storico prezzi, disattivazione, `scrape_run`), primo giro a mano su Neon,
`.github/workflows/scrape.yml` con i due orari, `backup.py`.

**M2 — Valutazione.** `llm/client.py` con la cascata, `prompts/evaluate_v1.md`,
`domain/evaluation.py` e `domain/pricing.py`, tabella `evaluation`, test sul parsing (JSON
pulito, JSON dentro testo, JSON rotto, score fuori scala). Lettura a mano di venti verdetti
per tarare il prompt prima di fidarsi del punteggio.

**M3 — API.** Le cinque rotte, filtri in SQL, indici (`listing (is_active,
passes_hard_filter, first_seen_at DESC)`, `review (listing_id)` unico), `doctor.py`
(migrazione applicata, annunci attivi senza valutazione, run falliti di fila).

**M4 — Dashboard.** Sul tuo design. Token, shell, elenco, filtri, flag ottimistici,
dettaglio, testata con lo stato dei giri.

**V1.5, già in vista**: Idealista con Playwright dal PC; dedup fra siti; notifica (email via
Brevo o Telegram) quando un annuncio supera un punteggio; criteri modificabili dalla
dashboard invece che nel codice.

## Test

pytest su `domain/` e `llm/` con fixture, mai rete:

- ⚠️ **Il test intoccabile**: nessun annuncio sopra 250.000 €, sotto 80 mq, sotto 3 locali o
  fuori zona passa il filtro rigido, e nessuno con ascensore/balcone `None` viene scartato
  per quello. Se cade questo, la dashboard è rumore o è cieca.
- Normalizzazione da JSON reale di Subito e di Immobiliare: prezzo "250.000 €" → `250000`,
  "85 mq" → `85`, "Sì"/"No"/assente → `True`/`False`/`None`, piano "Rialzato"/"3"/"Ultimo".
- Mappa delle zone: ogni nome di zona del sito usato nei fixture mappa su una zona dei
  criteri o su `None`, mai su una stringa nuova.
- Parsing del verdetto: JSON pulito, JSON avvolto in testo, JSON rotto, `score` a 140 →
  rifiutato, campo mancante → rifiutato.
- Cascata: 429 sul primo modello → il secondo riceve la stessa richiesta; 429 su tutti →
  nessuna valutazione scritta, nessuna eccezione fuori dal runner.
- Mediana di zona con 0, 1 e N annunci; il prezzo/mq non si calcola con mq mancanti.
- Disattivazione: assente in un giro → ancora attivo; assente in due → inattivo; ricompare
  → attivo di nuovo, senza perdere review né valutazioni.

## Verifica

1. `python -m scripts.scrape --source subito --dry-run --no-llm` stampa annunci veri di
   Torino con il verdetto del filtro rigido (M0)
2. Lo stesso per Immobiliare, o il piano B dichiarato (M0)
3. `/_stato` verde su Vercel (M0)
4. `alembic upgrade head` su Neon; primo giro reale; `select count(*) from listing` torna
   con numeri sensati; secondo giro senza duplicati (M1)
5. Il workflow gira da `workflow_dispatch` con successo e poi da solo al primo orario (M1)
6. `pytest` verde, test intoccabile compreso (M2)
7. Venti verdetti letti a mano: il punteggio è difendibile, i fatti estratti sono veri (M2)
8. `curl /api/listings?status=nuova&sort=score` risponde con l'elenco filtrato (M3)
9. Dal telefono: apri la dashboard, flagga tre case, ricarica, sono sparite dalle nuove e
   stanno nel loro filtro; la testata dice quando ha girato lo scraper (M4)

## Dipendenze

**Backend runtime** (le legge Vercel): `fastapi`, `pydantic`, `pydantic-settings`,
`sqlalchemy`, `psycopg[binary]`, `alembic` — stessi pin di food-plan-maker (cp314).
**Nuova, approvata a M0**: **`curl_cffi`**, solo per lo scraper (fonti + Gemini), in un
`requirements-scraper.txt` che Vercel non legge: la function non fa scraping. ⚠️ Il piano
diceva `httpx`, ed è stato smentito il giorno stesso: Subito sta dietro Akamai, che
riconosce **la firma TLS** dello stack SSL di Python e risponde "Access Denied" con gli
stessi identici header che a curl accetta. Provati `urllib`, httpx con contesti SSL
diversi, cifrari personalizzati: 403 tutti. `curl_cffi` imita l'handshake di Chrome e
passa. Alternative scartate: chiamare il `curl` di sistema (dipende dalla build SSL di
ogni macchina). Nessun SDK Google: è REST, e un SDK porterebbe `grpc` e mezzo mondo per una
`POST`.
**Dev**: `uvicorn`, `pytest`, `httpx2`.
**Frontend**: `react`, `react-dom`, `react-router`, `vite`, `typescript`, `tailwindcss`.
Nessuna libreria di grafici, di fetching, di form.

Non entrano senza chiedere: Playwright (V1.5), BeautifulSoup (le fonti sono JSON, non
HTML), SDK Gemini.

## Punti aperti da decidere in corsa

1. **Tolleranza sul budget**: 250.000 € secchi, o +5 % perché si tratta? Deciderlo dopo
   aver visto quante case stanno fra 250 e 262.
2. **Rubrica del punteggio**: pesi fra prezzo/mq, taglio, stato e piano. Si tara a M2
   leggendo i verdetti, non prima.
3. **Nome del prodotto**: "Casa Radar" è di lavoro.
4. **Quanti giri senza comparire prima di "inattivo"**: due è la proposta; con Immobiliare
   che può bloccarsi un giorno, forse tre.
5. **Notifiche**: quando un annuncio ≥ 80 arriva, vuoi saperlo senza aprire la dashboard?
   È V1.5, ma il canale (email Brevo o Telegram bot, entrambi gratis) si può decidere prima.
