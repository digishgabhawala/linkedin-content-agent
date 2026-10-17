-- Postgres shape of the LinkedIn tables before multi-user (origin/main e84f762),
-- generated from that commit's models. Used by test_postgres_migration.py.
CREATE TABLE characters (
	character_id VARCHAR NOT NULL, 
	owner_id VARCHAR, 
	display_name VARCHAR, 
	personality TEXT, 
	card_json TEXT, 
	hero_asset_id VARCHAR, 
	hero_version INTEGER NOT NULL, 
	hero_image_url VARCHAR, 
	hero_candidate_id VARCHAR, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (character_id)
);
CREATE TABLE scene_asset_versions (
	id VARCHAR NOT NULL, 
	scene_asset_name VARCHAR NOT NULL, 
	version INTEGER NOT NULL, 
	detail_text TEXT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_scene_asset_version UNIQUE (scene_asset_name, version)
);
CREATE TABLE scene_assets (
	id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	display_name VARCHAR, 
	detail_text TEXT NOT NULL, 
	current_version INTEGER NOT NULL, 
	archived_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);
CREATE TABLE hero_generation_runs (
	id VARCHAR NOT NULL, 
	character_id VARCHAR NOT NULL, 
	card_json TEXT NOT NULL, 
	profile VARCHAR NOT NULL, 
	base_seed INTEGER NOT NULL, 
	requested_candidates INTEGER NOT NULL, 
	status VARCHAR NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(character_id) REFERENCES characters (character_id)
);
CREATE TABLE posts (
	id VARCHAR NOT NULL, 
	character_id VARCHAR NOT NULL, 
	brief TEXT NOT NULL, 
	clarify_transcript TEXT, 
	status VARCHAR NOT NULL, 
	post_text TEXT, 
	draft_version INTEGER NOT NULL, 
	category VARCHAR, 
	gate_scores TEXT, 
	pillar_scores TEXT, 
	weighted_score FLOAT, 
	recalibration_count INTEGER NOT NULL, 
	escalation_reason TEXT, 
	scene_instruction TEXT, 
	scene_asset_name VARCHAR, 
	scene_asset_version_id VARCHAR, 
	seed INTEGER, 
	final_image_path VARCHAR, 
	image_job_error TEXT, 
	image_task_id VARCHAR, 
	image_profile VARCHAR, 
	active_step TEXT, 
	step_context TEXT, 
	step_error TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	image_started_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(scene_asset_version_id) REFERENCES scene_asset_versions (id)
);
CREATE TABLE feedback (
	id VARCHAR NOT NULL, 
	post_id VARCHAR NOT NULL, 
	stage VARCHAR NOT NULL, 
	post_text_snippet TEXT, 
	user_note TEXT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(post_id) REFERENCES posts (id)
);
CREATE TABLE hero_candidates (
	id VARCHAR NOT NULL, 
	run_id VARCHAR NOT NULL, 
	task_id VARCHAR, 
	seed INTEGER NOT NULL, 
	status VARCHAR NOT NULL, 
	queue_artifact_id VARCHAR, 
	asset_id VARCHAR, 
	storage_path VARCHAR, 
	image_url VARCHAR, 
	metadata_json TEXT, 
	error TEXT, 
	selected_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_hero_candidate_run_seed UNIQUE (run_id, seed), 
	FOREIGN KEY(run_id) REFERENCES hero_generation_runs (id), 
	UNIQUE (task_id)
);
CREATE TABLE post_drafts (
	id VARCHAR NOT NULL, 
	post_id VARCHAR NOT NULL, 
	version INTEGER NOT NULL, 
	post_text TEXT NOT NULL, 
	generated_by VARCHAR NOT NULL, 
	user_instruction TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(post_id) REFERENCES posts (id)
);
