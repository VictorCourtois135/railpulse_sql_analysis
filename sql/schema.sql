-- ============================================================
-- RailPulse — SNCB/NMBS Database Schema
-- ============================================================
-- Source: GTFS static feed (data.belgianmobility.io) +
--         GTFS-Realtime feeds (trip updates & service alerts)
--
-- Run with: sqlite3 sncb.db < schema.sql
-- ============================================================


-- ============================================================
-- STATIC GTFS TABLES
-- ============================================================

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
    route_type          INTEGER NOT NULL,  -- 2 = rail, 3 = bus, etc.
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
    location_type           INTEGER,   -- 0=stop/platform, 1=station, ...
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

-- ============================================================
-- REAL-TIME TABLES — Trip Updates (GTFS-RT TripUpdate feed)
-- ============================================================

CREATE TABLE IF NOT EXISTS realtime_snapshots (
    snapshot_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at      TEXT NOT NULL,
    feed_timestamp  INTEGER
);

CREATE TABLE IF NOT EXISTS realtime_stop_updates (
    snapshot_id             INTEGER NOT NULL,
    trip_id                 TEXT NOT NULL,
    trip_start_time         TEXT,
    trip_start_date         TEXT,
    stop_id                 TEXT,
    stop_sequence           INTEGER,
    schedule_relationship   INTEGER,  -- 0=scheduled, 1=added, 2=skipped
    arrival_time            INTEGER,
    arrival_delay           INTEGER,
    departure_time          INTEGER,
    departure_delay         INTEGER,
    FOREIGN KEY (snapshot_id) REFERENCES realtime_snapshots(snapshot_id),
    FOREIGN KEY (trip_id) REFERENCES trips(trip_id),
    FOREIGN KEY (stop_id) REFERENCES stops(stop_id)
);

-- ============================================================
-- REAL-TIME TABLES — Service Alerts (GTFS-RT Alert feed)
-- ============================================================

CREATE TABLE IF NOT EXISTS realtime_alert_snapshots (
    snapshot_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at      TEXT NOT NULL,
    feed_timestamp  INTEGER
);

CREATE TABLE IF NOT EXISTS realtime_alerts (
    snapshot_id     INTEGER NOT NULL,
    alert_id        TEXT NOT NULL,
    cause           INTEGER,  -- 1=unknown,...,9=maintenance,10=construction,...
    effect          INTEGER,  -- 1=no_service,...,6=modified_service,...
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
    route_id        TEXT,
    stop_id         TEXT,
    trip_id         TEXT,
    FOREIGN KEY (snapshot_id, alert_id) REFERENCES realtime_alerts(snapshot_id, alert_id)
);

CREATE TABLE IF NOT EXISTS realtime_alert_periods (
    snapshot_id     INTEGER NOT NULL,
    alert_id        TEXT NOT NULL,
    start_time      INTEGER,
    end_time        INTEGER,
    FOREIGN KEY (snapshot_id, alert_id) REFERENCES realtime_alerts(snapshot_id, alert_id)
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_stop_times_trip ON stop_times(trip_id);
CREATE INDEX IF NOT EXISTS idx_stop_times_stop ON stop_times(stop_id);
CREATE INDEX IF NOT EXISTS idx_trips_route ON trips(route_id);
CREATE INDEX IF NOT EXISTS idx_trips_service ON trips(service_id);
CREATE INDEX IF NOT EXISTS idx_calendar_dates_service ON calendar_dates(service_id);
CREATE INDEX IF NOT EXISTS idx_calendar_dates_date ON calendar_dates(date);
CREATE INDEX IF NOT EXISTS idx_stops_name ON stops(stop_name);

CREATE INDEX IF NOT EXISTS idx_rt_stop_updates_trip ON realtime_stop_updates(trip_id);
CREATE INDEX IF NOT EXISTS idx_rt_stop_updates_stop ON realtime_stop_updates(stop_id);
CREATE INDEX IF NOT EXISTS idx_rt_stop_updates_snapshot ON realtime_stop_updates(snapshot_id);

CREATE INDEX IF NOT EXISTS idx_alert_texts_lookup ON realtime_alert_texts(alert_id, field_name, language);
CREATE INDEX IF NOT EXISTS idx_alert_entities_route ON realtime_alert_entities(route_id);
CREATE INDEX IF NOT EXISTS idx_alert_entities_stop ON realtime_alert_entities(stop_id);