-- ============================================================
-- RailPulse — Key Analytical Queries
-- ============================================================
-- Run with: sqlite3 db/sncb.db < sql/queries.sql
-- Or copy individual queries into any SQLite client.
-- ============================================================


-- ------------------------------------------------------------
-- Q1. THE PEAK HOUR PROBLEM
-- What hour of the day experiences the highest volume of
-- scheduled train departures across the entire network?
-- ------------------------------------------------------------
-- departure_time can exceed "24:00:00" in GTFS for after-midnight
-- trips. The modulo "% 24" folds these back into a real 0-23 hour.
SELECT
    CAST(substr(departure_time, 1, 2) AS INTEGER) % 24 AS hour_of_day,
    COUNT(*) AS nb_departures
FROM stop_times
WHERE departure_time IS NOT NULL
GROUP BY hour_of_day
ORDER BY nb_departures DESC
LIMIT 5;


-- ------------------------------------------------------------
-- Q2. PLATFORM BOTTLENECKS
-- Identify the top 3 busiest platforms in Brussels-Central.
-- ------------------------------------------------------------
SELECT
    s.platform_code,
    COUNT(*) AS nb_events
FROM stop_times st
JOIN stops s ON s.stop_id = st.stop_id
WHERE s.stop_name LIKE '%Bruxelles-Central%'
   OR s.stop_name LIKE '%Brussel-Centraal%'
GROUP BY s.platform_code
ORDER BY nb_events DESC
LIMIT 3;


-- ------------------------------------------------------------
-- Q3. BUSIEST MORNING DESTINATIONS
-- Top 3 most frequent terminal destinations (trip_headsign)
-- for all morning trips departing before 12:00:00.
-- ------------------------------------------------------------
-- stop_sequence = 1 isolates each trip's ORIGIN departure, so
-- each trip is only counted once (not once per intermediate stop).
SELECT
    t.trip_headsign,
    COUNT(*) AS nb_trips
FROM trips t
JOIN stop_times st ON st.trip_id = t.trip_id AND st.stop_sequence = 1
WHERE st.departure_time < '12:00:00'
  AND t.trip_headsign IS NOT NULL
GROUP BY t.trip_headsign
ORDER BY nb_trips DESC
LIMIT 3;


-- ------------------------------------------------------------
-- Q4. SERVICE FREQUENCY CLASSIFICATION
-- Classify each active service_id into a weekly frequency
-- category. Show the percentage of services in each category.
-- ------------------------------------------------------------
-- NOTE: for this SNCB feed, calendar.txt's weekday flags are ALL
-- ZERO for every service_id (this feed defines service entirely
-- through calendar_dates.txt exceptions, a common pattern for
-- national rail operators). So the frequency is derived from
-- calendar_dates instead: for each service_id, count active dates
-- and divide by the number of weeks they span.
WITH iso_dates AS (
    SELECT
        service_id,
        substr(date,1,4) || '-' || substr(date,5,2) || '-' || substr(date,7,2) AS iso_date
    FROM calendar_dates
    WHERE exception_type = 1   -- only dates where service was actually added
),
service_stats AS (
    SELECT
        service_id,
        COUNT(*) AS active_days,
        JULIANDAY(MAX(iso_date)) - JULIANDAY(MIN(iso_date)) + 1 AS span_days
    FROM iso_dates
    GROUP BY service_id
),
classified AS (
    SELECT
        service_id,
        active_days,
        active_days / (span_days / 7.0) AS avg_days_per_week,
        CASE
            WHEN active_days / (span_days / 7.0) >= 5 THEN 'High Frequency'
            WHEN active_days / (span_days / 7.0) >= 2 THEN 'Medium Frequency'
            ELSE 'Low Frequency/Special'
        END AS frequency_category
    FROM service_stats
)
SELECT
    frequency_category,
    COUNT(*) AS nb_services,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_total
FROM classified
GROUP BY frequency_category
ORDER BY nb_services DESC;


-- ------------------------------------------------------------
-- Q5. THE ACCESSIBILITY AUDIT
-- Ratio/percentage of scheduled trips per route that guarantee
-- wheelchair accessibility OR bicycle storage. Which routes
-- score lowest?
-- ------------------------------------------------------------
-- NOTE: in this feed, trips.wheelchair_accessible is NEVER filled
-- (100% NULL) — SNCB does not publish this info in GTFS. So this
-- metric is effectively driven entirely by bikes_allowed = '1'.
SELECT
    r.route_short_name,
    r.route_long_name,
    COUNT(*) AS total_trips,
    SUM(
        CASE WHEN t.wheelchair_accessible = '1' OR t.bikes_allowed = '1'
             THEN 1 ELSE 0 END
    ) AS accessible_trips,
    ROUND(
        100.0 * SUM(
            CASE WHEN t.wheelchair_accessible = '1' OR t.bikes_allowed = '1'
                 THEN 1 ELSE 0 END
        ) / COUNT(*),
        2
    ) AS pct_accessible
FROM trips t
JOIN routes r ON r.route_id = t.route_id
GROUP BY r.route_id
HAVING total_trips >= 10          -- ignore near-empty routes that would skew the ranking
ORDER BY pct_accessible ASC
LIMIT 10;