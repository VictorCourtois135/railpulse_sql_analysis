# 🚄 RailPulse — SNCB/NMBS Transit Analytics

**RailPulse** is a transit data engineering project built for RailwayPulse's Sprint 1: ingesting, normalizing, and analyzing the Belgian National Railway (SNCB/NMBS) network using both **static (GTFS)** and **real-time (GTFS-RT)** data sources.

## Project Description

The Belgian National Railway wants a clear overview of operational performance and delay patterns to optimize winter scheduling. This project builds a normalized SQLite database from SNCB's open data, combining:

- **Static schedule data** (GTFS): stations, routes, trips, stop-level timetables, calendars
- **Real-time data** (GTFS-Realtime): live trip delays, cancellations, and service alerts

...into a single relational database, queried using pure SQL (JOINs, CTEs, window functions, CASE WHEN) to answer key operational questions about peak hours, platform bottlenecks, service frequency, and accessibility.

**Data source:** [data.belgianmobility.io](https://data.belgianmobility.io/en/data.html) — SNCB/NMBS open data portal (Static Data API + Real-time Data API).

## Architecture

```
┌─────────────────────┐        ┌──────────────────────┐
│   GTFS Static Feed   │        │  GTFS-Realtime Feeds  │
│  (agency, routes,    │        │  (trip updates,       │
│   stops, trips,      │        │   service alerts)     │
│   stop_times, ...)   │        │                        │
└──────────┬───────────┘        └───────────┬────────────┘
           │ one-time import                │ polled periodically
           ▼                                 ▼
┌─────────────────────────────────────────────────────────┐
│                       sncb.db (SQLite)                    │
│   10 static tables  +  9 real-time snapshot/detail tables  │
│           normalized with strict PK / FK constraints       │
└─────────────────────────────────────────────────────────┘
                             │
                             ▼
                  SQL analysis (schema.sql, queries.sql)
```

## Entity Relationship Diagram

View the full interactive diagram on drawdb: **[RailPulse ERD](https://www.drawdb.app/share/z-o8cGVxjWpdwUFzyQFme12W)**

Key relationships:
- `trips.route_id → routes.route_id`
- `trips.service_id → calendar.service_id`
- `stop_times.trip_id → trips.trip_id`
- `stop_times.stop_id → stops.stop_id`
- `stops.parent_station → stops.stop_id` (station ↔ platform hierarchy)
- `calendar_dates.service_id → calendar.service_id`
- `realtime_stop_updates.trip_id/stop_id → trips/stops` (real-time ↔ static link)

## Repository Structure

```
railpulse_sql_analysis/
├── data/
│   └── static_data/           # Raw GTFS .txt files downloaded from the SNCB portal
├── db/
│   └── sncb.db                 # Generated database (not committed to git)
├── sql/
│   ├── schema.sql              # All table definitions (static + real-time), PK/FK, indexes
│   └── queries.sql             # The 5 key analytical queries (answers to the mission brief)
├── scripts/
│   ├── ingestion/
│   │   └── import_data.py      # One-time ingestion: static GTFS .txt files -> db/sncb.db
│   └── realtime/
│       ├── fetch_realtime.py   # Polls the GTFS-RT TripUpdate feed, appends to db/sncb.db
│       └── fetch_alerts.py     # Polls the GTFS-RT Alert feed, appends to db/sncb.db
├── docs/
│   └── erd.png                 # (optional) static export of the ERD, as backup for the drawdb link
└── README.md
```

All scripts compute their paths relative to their own file location (`Path(__file__)`), so they
work correctly regardless of which directory you run them from.

> **Note on `db/sncb.db`:** the generated database is **not committed to this repository**
> (~600 MB+ once fully imported — well over GitHub's file size limits). It is excluded via
> `.gitignore` and regenerated locally by running `scripts/ingestion/import_data.py` (step 4
> below). This has been tested end-to-end from a clean clone: running the steps in this README,
> in order, reproduces the exact same database and query results documented here.

> **Note:** `fetch_realtime.py` and `fetch_alerts.py` were run manually to build up the real-time
> history used in this analysis. A scheduling/cron mechanism to automate this (nice-to-have) was
> not implemented in this sprint — planned for Sprint 2, where the SNCB brief itself notes this is
> optional at this stage ("No worries if not, we will do it in the next sprint!").

## Database Creation

The database (`db/sncb.db`) is **not stored in this repo** (too large for git — see note below). To (re)create it locally:

```bash
# 1. Install dependencies
pip install python-dotenv

# 2. Set up your API key (see step 2 in Setup & Usage below for details)
cp .env.example .env
# edit .env with your real SNCB_API_KEY

# 3. Place the static GTFS .txt files in data/static_data/
#    (download from https://data.belgianmobility.io/en/data.html)

# 4. Build the database from the static files (creates db/sncb.db)
python scripts/ingestion/import_data.py

# 5. (optional) Append real-time snapshots on top of the static schedule
python scripts/realtime/fetch_realtime.py
python scripts/realtime/fetch_alerts.py
```

Step 4 alone is enough to get a fully queryable database — steps 5 are only needed if you want
the real-time delay/alert tables populated too. This whole sequence has been tested end-to-end
from a clean clone and reproduces the exact database and results documented in this README.

## Setup & Usage

1. **Create a free account** on the [SNCB developer portal](https://data.belgianmobility.io/en/data.html) and get an API key for the real-time feeds.
2. **Set your API key** by copying the template and filling in your real key:
   ```bash
   cp .env.example .env
   # then edit .env and replace "your-real-key-here" with your actual SNCB API key
   ```
   `.env` is git-ignored — your key never gets committed. Install the loader once:
   ```bash
   pip install python-dotenv
   ```
3. **Download the static GTFS feed** and place the `.txt` files in `data/static_data/`.
4. **Build the database:**
   ```bash
   python scripts/ingestion/import_data.py
   ```
5. **Poll real-time data** (run manually, or repeatedly to build history):
   ```bash
   python scripts/realtime/fetch_realtime.py   # one trip-update snapshot
   python scripts/realtime/fetch_alerts.py     # one alert snapshot
   ```
6. **Run the analytical queries:**
   ```bash
   sqlite3 db/sncb.db < sql/queries.sql
   ```

## Key Analytical Questions & Findings

| # | Question | Answer |
|---|---|---|
| 1 | Peak hour (network-wide departures) | **10:00** is the busiest hour (139,071 scheduled departures), with a plateau from 9:00–13:00 |
| 2 | Busiest platforms at Brussels-Central | Platform 3 (11,982 events), Platform 4 (10,515), Platform 2 (7,473) |
| 3 | Busiest morning destinations (before 12:00) | Anvers-Central (3,930 trips), Bruxelles-Midi (3,145), Louvain (2,505) |
| 4 | Service frequency breakdown | Low Frequency/Special: 50.85% · Medium: 33.11% · High: 16.04% (derived from `calendar_dates`, since this feed defines services via exceptions rather than weekly patterns) |
| 5 | Accessibility audit (wheelchair/bikes) | `wheelchair_accessible` is never populated in this feed (0% filled); the metric is effectively driven by `bikes_allowed`. Several replacement BUS routes score 0%. |

Full SQL for each answer is in [`queries.sql`](./sql/queries.sql).

## Query Results

Raw output from running `sql/queries.sql` against the production database.

**Q1 — Peak Hour Problem** (top 5 busiest hours, all departures network-wide)
```
10:00  ->  139,071 departures
09:00  ->  135,851 departures
11:00  ->  135,156 departures
12:00  ->  131,354 departures
13:00  ->  129,093 departures
```

**Q2 — Platform Bottlenecks** (top 3 busiest platforms, Brussels-Central)
```
Platform 3  ->  11,982 scheduled stop-events
Platform 4  ->  10,515 scheduled stop-events
Platform 2  ->   7,473 scheduled stop-events
```

**Q3 — Busiest Morning Destinations** (top 3 trip_headsign, departures before 12:00:00)
```
Anvers-Central   -> 3,930 trips
Bruxelles-Midi   -> 3,145 trips
Louvain          -> 2,505 trips
```

**Q4 — Service Frequency Classification** (% of all 51,593 service_ids)
```
Low Frequency/Special     26,234 services  (50.85%)
Medium Frequency          17,083 services  (33.11%)
High Frequency             8,276 services  (16.04%)
```

**Q5 — Accessibility Audit** (10 routes with the LOWEST accessible/bike-friendly ratio)
```
[BUS] Bruges -- Gand-Saint-Pierre             0/82   trips (0.0%)
[BUS] Bruges -- Ostende                       0/119  trips (0.0%)
[BUS] Liège-Guillemins -- Waremme              0/14   trips (0.0%)
[BUS] Louvain -- Waremme                       0/34   trips (0.0%)
[BUS] Menin -- Poperinge                       0/40   trips (0.0%)
[BUS] Audenarde -- Zottegem                    0/38   trips (0.0%)
[BUS] Welkenraedt -- Eupen                     0/70   trips (0.0%)
[BUS] Liège-Guillemins -- Verviers-Central      0/73   trips (0.0%)
[BUS] Louvain -- Liège-Guillemins              0/13   trips (0.0%)
[BUS] Landen -- Liège-Guillemins               0/71   trips (0.0%)
```
*(All 10 lowest-scoring routes are BUS replacement services; see the "Data Quality Notes"
below for why this reflects missing `bikes_allowed` data rather than true inaccessibility.)*

## Data Quality Notes

A few real quirks discovered while building this project, worth knowing before querying the data yourself:

- **`calendar.txt` is entirely zeroed out** (all weekday flags = 0 for all 51,593 services). This SNCB feed defines service days exclusively through `calendar_dates.txt` exceptions — a common pattern for national rail operators. Any frequency analysis must use `calendar_dates`, not `calendar`.
- **`wheelchair_accessible` is never filled** in `trips.txt` — SNCB does not currently publish this field.
- Real-time `trip_id`/`stop_id` formats match the static feed exactly (`gt:nmbssncb:...` / `gs:nmbssncb:...`), enabling direct joins between real-time and static tables without any transformation.

## Contributors

**Victor Courtois**

- GitHub: https://github.com/VictorCourtois135
- LinkedIn: www.linkedin.com/in/victor-courtois-303690274

## Timeline

- **Sprint 1** (current): Local database infrastructure, static + real-time ingestion, relational modeling, SQL analysis — *[20/07/2026 - 24/07/2026]*
- Sprint 2: Cloud migration (Azure SQL/PostgreSQL), serverless ingestion — *planned*
- Sprint 3: Power BI dashboard — *planned*
- Sprint 4: Text-to-SQL conversational assistant — *planned*

## Personal Situation

*This project was completed in 5 days as part of the BeCode AI/Data Science bootcamp.*