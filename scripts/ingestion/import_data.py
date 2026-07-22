"""
Import GTFS files (static_data/*.txt) into sncb.db.

Steps:
1. Connect to the database and enable foreign keys
2. Create the schema (the tables)
3. Import each .txt file, IN ORDER (because of the FK constraints)
4. Create indexes to speed up future queries
"""
import sqlite3
import csv
import os

# --- Step 1: folder where your .txt files live ---
DATA_DIR = "static_data"   # adjust the path if needed (relative to this script)
DB_PATH = "sncb.db"

conn = sqlite3.connect(DB_PATH)

SCHEMA = """
CREATE TABLE IF NOT EXISTS agency (
    agency_id           TEXT PRIMARY KEY,
    agency_name         TEXT NOT NULL,
    agency_url          TEXT NOT NULL,
    agency_timezone     TEXT NOT NULL,
    agency_lang         TEXT,
    agency_phone        TEXT,
    agency_fare_url     TEXT
);

CREATE TABLE IF NOT EXISTS feed_info (
    feed_id                 TEXT,
    feed_publisher_name     TEXT NOT NULL,
    feed_publisher_url      TEXT NOT NULL,
    feed_lang               TEXT NOT NULL,
    default_lang            TEXT,
    feed_start_date         TEXT,
    feed_end_date           TEXT,
    feed_version            TEXT,
    feed_contact_email      TEXT,
    feed_contact_url        TEXT
);

CREATE TABLE IF NOT EXISTS calendar (
    service_id  TEXT PRIMARY KEY,
    monday      INTEGER NOT NULL,
    tuesday     INTEGER NOT NULL,
    wednesday   INTEGER NOT NULL,
    thursday    INTEGER NOT NULL,
    friday      INTEGER NOT NULL,
    saturday    INTEGER NOT NULL,
    sunday      INTEGER NOT NULL,
    start_date  TEXT NOT NULL,
    end_date    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calendar_dates (
    service_id      TEXT NOT NULL,
    date            TEXT NOT NULL,
    exception_type  INTEGER NOT NULL,
    PRIMARY KEY (service_id, date),
    FOREIGN KEY (service_id) REFERENCES calendar(service_id)
);

CREATE TABLE IF NOT EXISTS routes (
    route_id            TEXT PRIMARY KEY,
    agency_id           TEXT,
    route_short_name    TEXT,
    route_long_name     TEXT,
    route_desc          TEXT,
    route_type          INTEGER NOT NULL,
    route_url           TEXT,
    route_color         TEXT,
    route_text_color    TEXT,
    FOREIGN KEY (agency_id) REFERENCES agency(agency_id)
);

CREATE TABLE IF NOT EXISTS stops (
    stop_id                 TEXT PRIMARY KEY,
    stop_code               TEXT,
    stop_name               TEXT,
    stop_desc               TEXT,
    stop_lat                REAL,
    stop_lon                REAL,
    zone_id                 TEXT,
    stop_url                TEXT,
    location_type           INTEGER,
    parent_station          TEXT,
    wheelchair_boarding     TEXT,
    platform_code           TEXT,
    FOREIGN KEY (parent_station) REFERENCES stops(stop_id)
);

CREATE TABLE IF NOT EXISTS trips (
    trip_id                 TEXT PRIMARY KEY,
    route_id                TEXT NOT NULL,
    service_id              TEXT NOT NULL,
    trip_headsign           TEXT,
    trip_short_name         TEXT,
    direction_id            INTEGER,
    block_id                TEXT,
    shape_id                TEXT,
    wheelchair_accessible   TEXT,
    bikes_allowed           TEXT,
    FOREIGN KEY (route_id) REFERENCES routes(route_id),
    FOREIGN KEY (service_id) REFERENCES calendar(service_id)
);

CREATE TABLE IF NOT EXISTS stop_times (
    trip_id                 TEXT NOT NULL,
    arrival_time            TEXT,
    departure_time          TEXT,
    stop_id                 TEXT,
    stop_sequence           INTEGER NOT NULL,
    stop_headsign           TEXT,
    pickup_type             INTEGER,
    drop_off_type           INTEGER,
    shape_dist_traveled     REAL,
    PRIMARY KEY (trip_id, stop_sequence),
    FOREIGN KEY (trip_id) REFERENCES trips(trip_id),
    FOREIGN KEY (stop_id) REFERENCES stops(stop_id)
);

CREATE TABLE IF NOT EXISTS transfers (
    from_stop_id         TEXT,
    to_stop_id           TEXT,
    transfer_type        INTEGER,
    min_transfer_time    INTEGER,
    from_trip_id         TEXT,
    to_trip_id           TEXT,
    FOREIGN KEY (from_stop_id) REFERENCES stops(stop_id),
    FOREIGN KEY (to_stop_id) REFERENCES stops(stop_id),
    FOREIGN KEY (from_trip_id) REFERENCES trips(trip_id),
    FOREIGN KEY (to_trip_id) REFERENCES trips(trip_id)
);

CREATE TABLE IF NOT EXISTS translations (
    table_name      TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    record_id       TEXT,
    record_sub_id   TEXT,
    field_value     TEXT,
    language        TEXT NOT NULL,
    translation     TEXT NOT NULL
);
"""

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

conn.close()
print(f"\nDone. Database created: {DB_PATH}")