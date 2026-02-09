-- NaviSound PostgreSQL + PostGIS schema

CREATE EXTENSION IF NOT EXISTS postgis;

-- Active and historical navigation sessions
CREATE TABLE IF NOT EXISTS navigation_sessions (
    id              SERIAL PRIMARY KEY,
    session_id      VARCHAR(64) UNIQUE NOT NULL,
    user_id         VARCHAR(64),
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    total_frames    INTEGER DEFAULT 0,
    total_hazards   INTEGER DEFAULT 0
);

CREATE INDEX idx_sessions_user ON navigation_sessions(user_id);

-- Scene snapshots captured per frame
CREATE TABLE IF NOT EXISTS scene_snapshots (
    id                      SERIAL PRIMARY KEY,
    session_id              VARCHAR(64) NOT NULL REFERENCES navigation_sessions(session_id),
    captured_at             TIMESTAMPTZ DEFAULT NOW(),
    scene_json              JSONB,
    confidence              REAL DEFAULT 0.0,
    clear_path_direction    VARCHAR(32),
    clear_path_distance_ft  REAL
);

CREATE INDEX idx_snapshots_session ON scene_snapshots(session_id);

-- Hazard events detected by HazardAgent
CREATE TABLE IF NOT EXISTS hazard_events (
    id              SERIAL PRIMARY KEY,
    session_id      VARCHAR(64) NOT NULL REFERENCES navigation_sessions(session_id),
    detected_at     TIMESTAMPTZ DEFAULT NOW(),
    hazard_type     VARCHAR(64) NOT NULL,
    direction       VARCHAR(32),
    distance_feet   REAL,
    urgency         VARCHAR(16) NOT NULL,
    was_avoided     BOOLEAN
);

CREATE INDEX idx_hazards_session ON hazard_events(session_id);

-- User testing results
CREATE TABLE IF NOT EXISTS test_results (
    id                  SERIAL PRIMARY KEY,
    participant_id      VARCHAR(64) NOT NULL,
    testing_date        TIMESTAMPTZ DEFAULT NOW(),
    task_1_completion   BOOLEAN DEFAULT FALSE,
    task_1_time_sec     REAL,
    task_1_collisions   INTEGER DEFAULT 0,
    task_2_completion   BOOLEAN DEFAULT FALSE,
    task_2_time_sec     REAL,
    task_2_collisions   INTEGER DEFAULT 0,
    sus_score           INTEGER,
    nps_score           INTEGER,
    feedback            TEXT
);
