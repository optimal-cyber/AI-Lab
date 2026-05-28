-- Seed data for the lab POA&M store (read-only MCP, ADR-005).
-- Build the db:  sqlite3 data/poams.db < data/seed_poams.sql
-- All data is fictional lab content — no client/CUI data.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS poams (
    id                        INTEGER PRIMARY KEY,
    control_id                TEXT    NOT NULL,
    weakness_description      TEXT    NOT NULL,
    severity                  TEXT    NOT NULL CHECK (severity IN ('low','moderate','high','critical')),
    status                    TEXT    NOT NULL CHECK (status IN ('open','in_progress','completed','risk_accepted')),
    scheduled_completion_date TEXT,
    milestones_json           TEXT    NOT NULL DEFAULT '[]',
    created_at                TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at                TEXT    NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO poams
  (id, control_id, weakness_description, severity, status, scheduled_completion_date, milestones_json, created_at, updated_at)
VALUES
  (1, 'AU-6',
   'Audit log review is manual and ad hoc; no scheduled review cadence or alerting on anomalous events.',
   'moderate', 'in_progress', '2026-08-15',
   '[{"milestone":"Stand up CloudWatch metric filters + alarms","due":"2026-06-30","done":true},{"milestone":"Define weekly review SOP","due":"2026-08-15","done":false}]',
   '2026-03-01 14:02:00', '2026-05-20 09:30:00'),

  (2, 'RA-5',
   'No recurring authenticated vulnerability scanning of the gateway host; scans are on-demand only.',
   'high', 'open', '2026-09-30',
   '[{"milestone":"Select scanner + cadence","due":"2026-07-15","done":false},{"milestone":"Remediate criticals within 15 days SLA","due":"2026-09-30","done":false}]',
   '2026-03-05 10:15:00', '2026-05-18 16:45:00'),

  (3, 'IA-5',
   'Service account authenticator rotation not yet automated; rotation is performed manually.',
   'moderate', 'open', '2026-10-31',
   '[{"milestone":"Inventory service accounts","due":"2026-08-01","done":false}]',
   '2026-03-10 08:00:00', '2026-04-22 11:10:00'),

  (4, 'SC-7',
   'Egress allowlist maintained manually; no automated drift detection on the proxy allowlist.',
   'low', 'risk_accepted', NULL,
   '[{"milestone":"Documented compensating control: IaC-managed allowlist + change review","due":"2026-05-01","done":true}]',
   '2026-02-20 13:30:00', '2026-05-01 17:00:00'),

  (5, 'SI-2',
   'Container base images are not yet on an automated patch/rebuild pipeline; updates are manual.',
   'high', 'completed', '2026-05-10',
   '[{"milestone":"Add weekly image rebuild + scan job","due":"2026-05-10","done":true},{"milestone":"Verify pinned digests","due":"2026-05-10","done":true}]',
   '2026-01-15 09:00:00', '2026-05-10 15:20:00');
