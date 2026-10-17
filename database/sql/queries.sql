-- Analytical and maintenance queries. Every value is a named bind parameter (:name);
-- never build these strings by concatenation.
-- Each block starts with "-- name: <identifier>" so tests and scripts can load them.

-- name: experiment_status_counts_by_dataset
SELECT d.id AS dataset_id, d.name AS dataset_name, e.status, COUNT(*) AS n
FROM experiments e
JOIN datasets d ON d.id = e.dataset_id
WHERE d.id = :dataset_id
GROUP BY d.id, d.name, e.status
ORDER BY e.status;

-- name: expired_datasets
SELECT id, stored_filename
FROM datasets
WHERE expires_at IS NOT NULL AND expires_at < :now
ORDER BY expires_at;

-- name: duplicate_uploads
SELECT sha256, COUNT(*) AS copies, MIN(created_at) AS first_uploaded
FROM datasets
GROUP BY sha256
HAVING COUNT(*) > 1
ORDER BY copies DESC;

-- name: latest_model_per_target
SELECT m.target, m.id AS model_id, m.name, m.created_at
FROM models m
WHERE m.created_at = (SELECT MAX(m2.created_at) FROM models m2 WHERE m2.target = m.target)
ORDER BY m.target;

-- name: prediction_volume_by_model
SELECT p.model_id, m.name, COUNT(*) AS requests, SUM(p.n_records) AS records
FROM prediction_events p
JOIN models m ON m.id = p.model_id
WHERE p.created_at >= :since AND p.created_at < :until
GROUP BY p.model_id, m.name
ORDER BY records DESC;

-- name: audit_trail_for_resource
SELECT occurred_at, actor, action
FROM audit_events
WHERE resource_type = :resource_type AND resource_id = :resource_id
ORDER BY occurred_at, id;

-- name: stuck_experiments
SELECT id, status, started_at
FROM experiments
WHERE status IN ('queued', 'running') AND created_at < :older_than
ORDER BY created_at;
