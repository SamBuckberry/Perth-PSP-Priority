-- Perth PSP-Priority Cycling Router — PostGIS Schema
-- All geometries stored in EPSG:7850 (GDA2020 / MGA Zone 50) for metric operations
-- Convert to EPSG:4326 at API boundary for routing engine and frontend

CREATE EXTENSION IF NOT EXISTS postgis;

-- Facility class enum
CREATE TYPE facility_class AS ENUM (
    'PSP',
    'OFFROAD_SHARED_PATH_HQ',
    'OFFROAD_SHARED_PATH',
    'CYCLE_TRACK_PROTECTED',
    'CYCLE_LANE_PAINTED',
    'QUIET_STREET',
    'BUSY_ROAD_NO_INFRA'
);

-- PSP source tracking
CREATE TYPE psp_source AS ENUM (
    'osm_only',
    'ltcn_primary',
    'mrwa_psp_nodes',
    'manual'
);

-- Edge table: the core routable network
CREATE TABLE edge (
    edge_id BIGSERIAL PRIMARY KEY,
    geom GEOMETRY(LINESTRING, 7850) NOT NULL,
    osm_way_id BIGINT,
    length_m DOUBLE PRECISION NOT NULL,
    facility_class facility_class NOT NULL DEFAULT 'BUSY_ROAD_NO_INFRA',
    psp_flag BOOLEAN NOT NULL DEFAULT FALSE,
    psp_source psp_source,
    road_speed_kmh SMALLINT,
    road_hierarchy TEXT,
    crash_risk DOUBLE PRECISION DEFAULT 0.0 CHECK (crash_risk >= 0 AND crash_risk <= 1),
    surface TEXT,
    smoothness TEXT,
    lit BOOLEAN,
    crossing_type TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_edge_geom ON edge USING GIST (geom);
CREATE INDEX idx_edge_facility ON edge (facility_class);
CREATE INDEX idx_edge_psp ON edge (psp_flag) WHERE psp_flag = TRUE;
CREATE INDEX idx_edge_osm_way ON edge (osm_way_id);

-- Node table
CREATE TABLE node (
    node_id BIGSERIAL PRIMARY KEY,
    geom GEOMETRY(POINT, 7850) NOT NULL,
    osm_node_id BIGINT,
    is_psp_node_mrwa BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_node_geom ON node USING GIST (geom);
CREATE INDEX idx_node_osm ON node (osm_node_id);

-- Edge-node topology
CREATE TABLE edge_node (
    edge_id BIGINT NOT NULL REFERENCES edge(edge_id),
    start_node_id BIGINT NOT NULL REFERENCES node(node_id),
    end_node_id BIGINT NOT NULL REFERENCES node(node_id),
    PRIMARY KEY (edge_id)
);

-- Closure events (roadworks, incidents)
CREATE TABLE closure_event (
    event_id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    geom GEOMETRY(GEOMETRY, 7850),
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    description TEXT,
    raw_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_closure_geom ON closure_event USING GIST (geom);
CREATE INDEX idx_closure_time ON closure_event (start_time, end_time);

-- Route request log (minimal, privacy-preserving)
CREATE TABLE route_request_log (
    request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    origin_hash TEXT,
    destination_hash TEXT,
    profile TEXT,
    result_metrics JSONB
);

-- LTCN overlay staging (for ETL)
CREATE TABLE ltcn_overlay (
    id BIGSERIAL PRIMARY KEY,
    geom GEOMETRY(MULTILINESTRING, 7850),
    hierarchy TEXT,
    route_id TEXT,
    ltcn_name TEXT,
    lga_name TEXT,
    endorsed TEXT,
    date_endorsed DATE
);

CREATE INDEX idx_ltcn_geom ON ltcn_overlay USING GIST (geom);

-- MRWA road assets staging
CREATE TABLE mrwa_road_asset (
    id BIGSERIAL PRIMARY KEY,
    geom GEOMETRY(MULTILINESTRING, 7850),
    network_type TEXT,
    start_node_no TEXT,
    end_node_no TEXT,
    road_name TEXT,
    raw_data JSONB
);

CREATE INDEX idx_mrwa_road_geom ON mrwa_road_asset USING GIST (geom);

-- MRWA intersection/node staging
CREATE TABLE mrwa_intersection (
    id BIGSERIAL PRIMARY KEY,
    geom GEOMETRY(POINT, 7850),
    node_type TEXT,
    node_no TEXT,
    node_name TEXT,
    raw_data JSONB
);

CREATE INDEX idx_mrwa_int_geom ON mrwa_intersection USING GIST (geom);

-- MRWA crash data staging
CREATE TABLE mrwa_crash (
    id BIGSERIAL PRIMARY KEY,
    geom GEOMETRY(POINT, 7850),
    severity TEXT,
    accident_type TEXT,
    crash_date DATE,
    total_bike_involved INTEGER,
    raw_data JSONB
);

CREATE INDEX idx_mrwa_crash_geom ON mrwa_crash USING GIST (geom);
