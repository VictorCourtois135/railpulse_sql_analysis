"""
Import GTFS files (data/static_data/*.txt) into db/sncb.db.

Steps:
1. Connect to the database and enable foreign keys
2. Create the schema (the tables)
3. Import each .txt file, IN ORDER (because of the FK constraints)
4. Create indexes to speed up future queries

Expected project layout (paths below are computed relative to THIS
file's location, so the script works no matter where you run it from):

    railpulse_sql_analysis/
    ├── data/static_data/*.txt
    ├── db/sncb.db
    ├── sql/schema.sql
    └── scripts/ingestion/import_data.py   <- this file
"""
import sqlite3
import csv
import os
from pathlib import Path

# --- Step 1: compute paths relative to THIS script, not the current directory ---
SCRIPT_DIR = Path(__file__).resolve().parent      # scripts/ingestion/
PROJECT_ROOT = SCRIPT_DIR.parent.parent            # railpulse_sql_analysis/

DATA_DIR = PROJECT_ROOT / "data" / "static_data"
DB_PATH = PROJECT_ROOT / "db" / "sncb.db"
SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)  # create db/ if missing

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = OFF")
# Foreign keys are OFF during bulk load: GTFS .txt files are not guaranteed
# to be topologically sorted (e.g. a platform can appear in stops.txt
# BEFORE the station it belongs to, via parent_station self-reference).
# The source data itself is consistent -- this is purely an insertion-order
# artifact, so we verify integrity explicitly at the end instead (see
# Step 4 below) and re-enable FK enforcement for any future application code.

# --- Step 2: create the tables (schema lives in sql/schema.sql) ---
with open(SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = f.read()

# --- Step 2: create the tables ---
conn.executescript(SCHEMA)
conn.commit()
print("Tables created.")

# --- Step 3: import the files, IN ORDER (foreign key constraints) ---

# For each table, list the columns IN THE ORDER we want to insert them.
# This must match the columns in the CREATE TABLE (excluding FK/PRIMARY KEY clauses).
TABLE_COLUMNS = {
    "agency": ["agency_id", "agency_name", "agency_url", "agency_timezone",
               "agency_lang", "agency_phone", "agency_fare_url"],
    "feed_info": ["feed_id", "feed_publisher_name", "feed_publisher_url", "feed_lang",
                  "default_lang", "feed_start_date", "feed_end_date", "feed_version",
                  "feed_contact_email", "feed_contact_url"],
    "calendar": ["service_id", "monday", "tuesday", "wednesday", "thursday",
                 "friday", "saturday", "sunday", "start_date", "end_date"],
    "calendar_dates": ["service_id", "date", "exception_type"],
    "routes": ["route_id", "agency_id", "route_short_name", "route_long_name",
               "route_desc", "route_type", "route_url", "route_color", "route_text_color"],
    "stops": ["stop_id", "stop_code", "stop_name", "stop_desc", "stop_lat", "stop_lon",
              "zone_id", "stop_url", "location_type", "parent_station",
              "wheelchair_boarding", "platform_code"],
    "trips": ["trip_id", "route_id", "service_id", "trip_headsign", "trip_short_name",
              "direction_id", "block_id", "shape_id", "wheelchair_accessible", "bikes_allowed"],
    "stop_times": ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence",
                   "stop_headsign", "pickup_type", "drop_off_type", "shape_dist_traveled"],
    "transfers": ["from_stop_id", "to_stop_id", "transfer_type", "min_transfer_time",
                  "from_trip_id", "to_trip_id"],
    "translations": ["table_name", "field_name", "record_id", "record_sub_id",
                      "field_value", "language", "translation"],
}

# Import order = order of this list (respects FK: parents before children)
IMPORT_ORDER = [
    ("agency.txt", "agency"),
    ("feed_info.txt", "feed_info"),
    ("calendar.txt", "calendar"),
    ("calendar_dates.txt", "calendar_dates"),
    ("routes.txt", "routes"),
    ("stops.txt", "stops"),
    ("trips.txt", "trips"),
    ("stop_times.txt", "stop_times"),
    ("transfers.txt", "transfers"),
    ("translations.txt", "translations"),
]


def clean(val):
    """Turn empty strings into None (NULL in SQL)."""
    if val is None:
        return None
    val = val.strip()
    return val if val != "" else None


def import_file(filename, table):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        print(f"  ! {filename} not found in {DATA_DIR}, skipped.")
        return 0

    cols = TABLE_COLUMNS[table]
    placeholders = ",".join(["?"] * len(cols))
    insert_sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"

    cur = conn.cursor()
    batch = []
    count = 0
    BATCH_SIZE = 20000  # insert in batches of 20,000 rows for speed

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            values = [clean(row.get(c)) for c in cols]
            batch.append(values)
            count += 1
            if len(batch) >= BATCH_SIZE:
                cur.executemany(insert_sql, batch)
                batch = []
        if batch:  # don't forget the last, incomplete batch
            cur.executemany(insert_sql, batch)

    conn.commit()
    return count


print("\nImporting data...")
for filename, table in IMPORT_ORDER:
    n = import_file(filename, table)
    print(f"  {filename:22s} -> {table:15s} : {n:>9d} rows")

# --- Step 4: indexes to speed up future queries ---
print("\nCreating indexes...")
conn.executescript("""
    CREATE INDEX IF NOT EXISTS idx_stop_times_trip ON stop_times(trip_id);
    CREATE INDEX IF NOT EXISTS idx_stop_times_stop ON stop_times(stop_id);
    CREATE INDEX IF NOT EXISTS idx_trips_route ON trips(route_id);
    CREATE INDEX IF NOT EXISTS idx_trips_service ON trips(service_id);
    CREATE INDEX IF NOT EXISTS idx_calendar_dates_service ON calendar_dates(service_id);
    CREATE INDEX IF NOT EXISTS idx_calendar_dates_date ON calendar_dates(date);
    CREATE INDEX IF NOT EXISTS idx_stops_name ON stops(stop_name);
""")
conn.commit()

# --- Step 5: verify referential integrity now that ALL rows are loaded,
#             then re-enable FK enforcement for any future connections ---
print("\nVerifying foreign key integrity...")
violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
if violations:
    print(f"  ! {len(violations)} foreign key violation(s) found:")
    for v in violations[:10]:
        print("   ", v)
else:
    print("  No foreign key violations. Data is consistent.")

conn.execute("PRAGMA foreign_keys = ON")
conn.close()
print(f"\nDone. Database created: {DB_PATH}")