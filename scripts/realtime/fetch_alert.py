"""
Fetch the SNCB GTFS-Realtime Alert feed and store it in sncb.db.

New tables:
  - realtime_alert_snapshots : one row per API fetch
  - realtime_alerts          : one row per alert (id, cause, effect)
  - realtime_alert_texts     : header/description/url text, per language
  - realtime_alert_entities  : which agency/route/stop/trip is affected
  - realtime_alert_periods   : validity windows (activePeriod), if any

GTFS-RT enums (for reference, see google's gtfs-realtime.proto):
  cause:  1=unknown, 2=other, 3=technical_problem, 4=strike, 5=demonstration,
          6=accident, 7=holiday, 8=weather, 9=maintenance, 10=construction,
          11=police_activity, 12=medical_emergency
  effect: 1=no_service, 2=reduced_service, 3=significant_delays, 4=detour,
          5=additional_service, 6=modified_service, 7=other_effect,
          8=unknown_effect, 9=stop_moved, 10=no_effect, 11=accessibility_issue

Run this script repeatedly to build up a history of service alerts.
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
API_URL = "https://api-management-opendata-production.azure-api.net/api/gtfs/feed/nmbssncb/rt/alert/"
API_HEADERS = {
    'Cache-Control': 'no-cache',
    'bmc-partner-key': os.environ["SNCB_API_KEY"],  # set this env var before running
}


# ---------------------------------------------------------------------
# Step 1: create the new tables (only runs once, IF NOT EXISTS)
# ---------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS realtime_alert_snapshots (
    snapshot_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at      TEXT NOT NULL,
    feed_timestamp  INTEGER
);

CREATE TABLE IF NOT EXISTS realtime_alerts (
    snapshot_id     INTEGER NOT NULL,
    alert_id        TEXT NOT NULL,
    cause           INTEGER,
    effect          INTEGER,
    PRIMARY KEY (snapshot_id, alert_id),
    FOREIGN KEY (snapshot_id) REFERENCES realtime_alert_snapshots(snapshot_id)
);

CREATE TABLE IF NOT EXISTS realtime_alert_texts (
    snapshot_id     INTEGER NOT NULL,
    alert_id        TEXT NOT NULL,
    field_name      TEXT NOT NULL,   -- 'header', 'description', or 'url'
    language        TEXT,
    text_value      TEXT,
    FOREIGN KEY (snapshot_id, alert_id) REFERENCES realtime_alerts(snapshot_id, alert_id)
);

CREATE TABLE IF NOT EXISTS realtime_alert_entities (
    snapshot_id     INTEGER NOT NULL,
    alert_id        TEXT NOT NULL,
    agency_id       TEXT,
    route_id        TEXT,           -- matches routes.route_id, when present
    stop_id         TEXT,           -- matches stops.stop_id, when present
    trip_id         TEXT,           -- matches trips.trip_id, when present
    FOREIGN KEY (snapshot_id, alert_id) REFERENCES realtime_alerts(snapshot_id, alert_id)
);

CREATE TABLE IF NOT EXISTS realtime_alert_periods (
    snapshot_id     INTEGER NOT NULL,
    alert_id        TEXT NOT NULL,
    start_time      INTEGER,        -- unix epoch, NULL if open-ended
    end_time        INTEGER,        -- unix epoch, NULL if open-ended
    FOREIGN KEY (snapshot_id, alert_id) REFERENCES realtime_alerts(snapshot_id, alert_id)
);

CREATE INDEX IF NOT EXISTS idx_alert_texts_lookup ON realtime_alert_texts(alert_id, field_name, language);
CREATE INDEX IF NOT EXISTS idx_alert_entities_route ON realtime_alert_entities(route_id);
CREATE INDEX IF NOT EXISTS idx_alert_entities_stop ON realtime_alert_entities(stop_id);
"""


def fetch_feed():
    """Call the SNCB alert API and return the parsed JSON."""
    req = urllib.request.Request(API_URL, headers=API_HEADERS)
    req.get_method = lambda: 'GET'
    with urllib.request.urlopen(req) as response:
        raw = response.read()
    return json.loads(raw)


def store_feed(conn, feed_json):
    """Insert one snapshot + all its alerts into the database."""
    cur = conn.cursor()

    header = feed_json.get("header", {})
    feed_ts = header.get("timestamp")
    entities = feed_json.get("entity", [])

    fetched_at = datetime.now(timezone.utc).isoformat()
    cur.execute(
        "INSERT INTO realtime_alert_snapshots (fetched_at, feed_timestamp) VALUES (?, ?)",
        (fetched_at, feed_ts)
    )
    snapshot_id = cur.lastrowid

    alert_rows = []
    text_rows = []
    entity_rows = []
    period_rows = []

    for entity in entities:
        alert_id = entity.get("id")
        alert = entity.get("alert", {})
        cause = alert.get("cause")
        effect = alert.get("effect")

        alert_rows.append((snapshot_id, alert_id, cause, effect))

        # --- texts: header, description, url, each with several languages ---
        for field_name in ("headerText", "descriptionText", "url"):
            field = alert.get(field_name, {})
            short_name = {"headerText": "header", "descriptionText": "description", "url": "url"}[field_name]
            for translation in field.get("translation", []):
                text_rows.append((
                    snapshot_id, alert_id, short_name,
                    translation.get("language"), translation.get("text")
                ))

        # --- informed entities: agency/route/stop/trip affected ---
        for informed in alert.get("informedEntity", []):
            trip_info = informed.get("trip", {})
            entity_rows.append((
                snapshot_id, alert_id,
                informed.get("agencyId"),
                informed.get("routeId"),
                informed.get("stopId"),
                trip_info.get("tripId") if trip_info else None,
            ))

        # --- active periods (often empty for these alerts) ---
        for period in alert.get("activePeriod", []):
            period_rows.append((
                snapshot_id, alert_id,
                period.get("start"), period.get("end")
            ))

    cur.executemany(
        "INSERT INTO realtime_alerts (snapshot_id, alert_id, cause, effect) VALUES (?, ?, ?, ?)",
        alert_rows
    )
    cur.executemany(
        "INSERT INTO realtime_alert_texts (snapshot_id, alert_id, field_name, language, text_value) VALUES (?, ?, ?, ?, ?)",
        text_rows
    )
    cur.executemany(
        "INSERT INTO realtime_alert_entities (snapshot_id, alert_id, agency_id, route_id, stop_id, trip_id) VALUES (?, ?, ?, ?, ?, ?)",
        entity_rows
    )
    cur.executemany(
        "INSERT INTO realtime_alert_periods (snapshot_id, alert_id, start_time, end_time) VALUES (?, ?, ?, ?)",
        period_rows
    )

    conn.commit()
    return snapshot_id, len(alert_rows)


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()

    print("Fetching alert feed...")
    feed_json = fetch_feed()

    snapshot_id, nb_alerts = store_feed(conn, feed_json)
    print(f"Snapshot #{snapshot_id} stored: {nb_alerts} alerts.")

    conn.close()


if __name__ == "__main__":
    main()