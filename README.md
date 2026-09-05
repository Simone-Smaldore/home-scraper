# Casa Radar

Raccoglie ogni giorno gli annunci di appartamenti in vendita a Torino, scarta quelli che
non passano i criteri, fa valutare gli altri a un LLM e li mostra in una dashboard dove
ogni casa si flagga come interessante, media o scartata.

- Piano di progetto: [`docs/plan/plan-v1.md`](docs/plan/plan-v1.md)
- Convenzioni per lavorarci: [`CLAUDE.md`](CLAUDE.md)

**Stato: M1.** Le due fonti (Subito, Immobiliare) raccolgono e salvano gli annunci su Neon,
con storico dei prezzi e ciclo di vita; il cron su GitHub Actions gira due volte al giorno.
Valutazione LLM, API della dashboard e dashboard arrivano con M2–M4.

## Prerequisiti

Python 3.11+, Node 20+, un account Neon e un account Vercel (entrambi free tier), una
chiave Gemini di AI Studio (gratuita).

## Setup locale

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements-dev.txt
npm install
cp .env.example backend/.env    # poi compila DATABASE_URL (host -pooler) e GEMINI_API_KEY
```

### Provare lo scraper senza database

```bash
cd backend
python -m scripts.scrape --source subito --dry-run --no-llm
python -m scripts.scrape --source immobiliare --dry-run --no-llm
```

Legge due pagine di annunci veri, stampa quali passano il filtro e perché gli altri no.
`--all` per tutta Torino, `--show-rejected` per vedere anche gli scartati. Non scrive
niente da nessuna parte.

### Il primo giro vero

```bash
cd backend
alembic upgrade head                 # crea le tabelle su Neon (una volta)
python -m scripts.scrape --full      # tutto Torino, qualche minuto
python -m scripts.backup --no-raw    # il paracadute
```

Poi ogni giorno ci pensa GitHub Actions (vedi sotto). A mano: `python -m scripts.scrape`
è il giro incrementale, `--full` quello completo che segna anche gli annunci spariti.

### Backend e frontend

```bash
cd backend && uvicorn app.main:app --reload    # http://127.0.0.1:8000, docs su /api/docs
npm run dev                                    # http://localhost:5173, proxy /api → uvicorn
```

Apri **http://localhost:5173/_stato**: tre righe, frontend, API, database. Senza
`DATABASE_URL` la terza è rossa e dice perché.

```bash
cd backend && pytest
npm run typecheck
```

## Il cron su GitHub Actions

Il workflow `.github/workflows/scrape.yml` gira alle 05:30 UTC (completo) e alle 17:30 UTC
(incrementale). Su GitHub: **Settings → Secrets and variables → Actions → New repository
secret**, due volte: `DATABASE_URL` (la stringa pooled di Neon) e `GEMINI_API_KEY`. Poi
**Actions → scrape → Run workflow** per lanciarlo a mano la prima volta; se una fonte è
bloccata il run diventa rosso e GitHub manda la mail.

## Deploy su Vercel

1. Pusha il repository su GitHub.
2. Su Vercel: **Add New → Project**, importa il repository e **non toccare** le
   impostazioni di build: le legge da `vercel.json`.
3. In **Settings → Environment Variables**: `DATABASE_URL` (pooled) e
   `ENVIRONMENT=production`. **Non** la chiave Gemini: la function non la usa.
4. Deploy, poi apri `https://<dominio>/_stato`.
5. **Le migrazioni non girano al deploy**: `cd backend && alembic upgrade head` dalla tua
   macchina, contro lo stesso Neon.

Le versioni in `requirements.txt` non sono decorative: Vercel compila su CPython 3.14 e
ogni pacchetto nativo deve avere un wheel `cp314`. Prima di abbassare un pin, controlla
*Download files* su PyPI.

## Come sta insieme

```
api/index.py               entrypoint Vercel: espone l'app FastAPI come serverless function
backend/app/               API, dominio, fonti
backend/scripts/scrape.py  lo scraper — gira su GitHub Actions, non su Vercel
frontend/                  React + Vite, build statica servita da Vercel
requirements.txt           solo l'API (Vercel); requirements-scraper.txt aggiunge curl_cffi
```
