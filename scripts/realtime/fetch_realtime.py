"""
Fetch the SNCB GTFS-Realtime TripUpdate feed and store it in sncb.db.

New tables:
  - realtime_snapshots     : one row per API fetch (when we polled)
  - realtime_stop_updates  : one row per stop-time update within that fetch

Run this script repeatedly (e.g. every 1-2 minutes via a scheduler/cron)
to build up a real-time history you can compare against the static schedule.
"""
import urllib.request
import json
import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent      # scripts/realtime/
PROJECT_ROOT = SCRIPT_DIR.parent.parent            # railpulse_sql_analysis/
DB_PATH = PROJECT_ROOT / "db" / "sncb.db"
API_URL = "https://api-management-opendata-production.azure-api.net/api/gtfs/feed/nmbssncb/rt/trip-update/"
API_HEADERS = {
    'Cache-Control': 'no-cache',
    'bmc-partner-key': os.environ["SNCB_API_KEY"],  # set this env var before running
}


# ---------------------------------------------------------------------
# Step 1: create the new tables (only runs once, IF NOT EXISTS)
# ---------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS realtime_snapshots (
    snapshot_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at      TEXT NOT NULL,   -- when WE fetched it (ISO datetime, UTC)
    feed_timestamp  INTEGER          -- the feed's own "timestamp.low" field (unix epoch)
);

CREATE TABLE IF NOT EXISTS realtime_stop_updates (
    snapshot_id             INTEGER NOT NULL,
    trip_id                 TEXT NOT NULL,      -- matches trips.trip_id
    trip_start_time         TEXT,
    trip_start_date         TEXT,
    stop_id                 TEXT,                -- matches stops.stop_id
    stop_sequence           INTEGER,
    schedule_relationship   INTEGER,             -- 0=scheduled, 1=added, 2=skipped/cancelled
    arrival_time            INTEGER,             -- unix epoch, NULL if not provided
    arrival_delay           INTEGER,             -- seconds, NULL if not provided
    departure_time          INTEGER,
    departure_delay         INTEGER,
    FOREIGN KEY (snapshot_id) REFERENCES realtime_snapshots(snapshot_id),
    FOREIGN KEY (trip_id) REFERENCES trips(trip_id),
    FOREIGN KEY (stop_id) REFERENCES stops(stop_id)
);

CREATE INDEX IF NOT EXISTS idx_rt_stop_updates_trip ON realtime_stop_updates(trip_id);
CREATE INDEX IF NOT EXISTS idx_rt_stop_updates_stop ON realtime_stop_updates(stop_id);
CREATE INDEX IF NOT EXISTS idx_rt_stop_updates_snapshot ON realtime_stop_updates(snapshot_id);
"""


def fetch_feed():
    """Call the SNCB real-time API and return the parsed JSON."""
    req = urllib.request.Request(API_URL, headers=API_HEADERS)
    req.get_method = lambda: 'GET'
    with urllib.request.urlopen(req) as response:
        raw = response.read()
    return json.loads(raw)


def store_feed(conn, feed_json):
    """Insert one snapshot + all its stop-time updates into the database."""
    cur = conn.cursor()

    # --- one row for this fetch ---
    entities = feed_json.get("entity", feed_json.get("entities", []))
    # some feed dumps wrap everything under "entity"; adjust if the key differs
    if not entities and isinstance(feed_json, dict):
        # fallback: maybe the top-level IS already the list of entities
        entities = feed_json.get("entity") or []

    feed_ts = None
    if entities:
        feed_ts = entities[0].get("tripUpdate", {}).get("timestamp", {}).get("low")

    fetched_at = datetime.now(timezone.utc).isoformat()
    cur.execute(
        "INSERT INTO realtime_snapshots (fetched_at, feed_timestamp) VALUES (?, ?)",
        (fetched_at, feed_ts)
    )
    snapshot_id = cur.lastrowid

    # --- one row per stop_time_update, across every entity/trip in the feed ---
    rows = []
    for entity in entities:
        trip_update = entity.get("tripUpdate", {})
        trip = trip_update.get("trip", {})
        trip_id = trip.get("tripId")
        start_time = trip.get("startTime")
        start_date = trip.get("startDate")

        for stu in trip_update.get("stopTimeUpdate", []):
            arrival = stu.get("arrival", {})
            departure = stu.get("departure", {})
            rows.append((
                snapshot_id,
                trip_id,
                start_time,
                start_date,
                stu.get("stopId"),
                stu.get("stopSequence"),
                stu.get("scheduleRelationship"),
                arrival.get("time"),
                arrival.get("delay"),
                departure.get("time"),
                departure.get("delay"),
            ))

    cur.executemany("""
        INSERT INTO realtime_stop_updates (
            snapshot_id, trip_id, trip_start_time, trip_start_date,
            stop_id, stop_sequence, schedule_relationship,
            arrival_time, arrival_delay, departure_time, departure_delay
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    conn.commit()
    return snapshot_id, len(rows)


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()

    print("Fetching real-time feed...")
    feed_json = fetch_feed()

    snapshot_id, nb_rows = store_feed(conn, feed_json)
    print(f"Snapshot #{snapshot_id} stored: {nb_rows} stop-time updates.")

    conn.close()


if __name__ == "__main__":
    main()