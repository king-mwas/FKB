-- FKB schema for Supabase (Postgres). Generated from db/models.py.
-- Paste into Supabase Dashboard -> SQL Editor -> Run.
-- Safe to run once on a fresh project; re-running errors on existing tables.

CREATE TABLE accounts (
	id SERIAL NOT NULL, 
	broker VARCHAR(16) NOT NULL, 
	mode VARCHAR(16) NOT NULL, 
	label VARCHAR(64) NOT NULL, 
	balance FLOAT NOT NULL, 
	equity FLOAT NOT NULL, 
	margin_used FLOAT NOT NULL, 
	allocated_capital FLOAT NOT NULL, 
	last_synced_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE signals (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	account_id INTEGER NOT NULL, 
	symbol VARCHAR(32) NOT NULL, 
	ltf VARCHAR(8) NOT NULL, 
	htf VARCHAR(8) NOT NULL, 
	track VARCHAR(32) NOT NULL, 
	variant VARCHAR(32) NOT NULL, 
	event_kind VARCHAR(8) NOT NULL, 
	direction INTEGER NOT NULL, 
	bar_time TIMESTAMP WITH TIME ZONE NOT NULL, 
	htf_bias INTEGER NOT NULL, 
	session_ok BOOLEAN NOT NULL, 
	zone_type VARCHAR(8) NOT NULL, 
	zone_top FLOAT NOT NULL, 
	zone_bottom FLOAT NOT NULL, 
	sweep_confirmed BOOLEAN NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	confidence_score INTEGER, 
	confidence_reasoning TEXT, 
	confidence_concerns TEXT, 
	confidence_error TEXT, 
	trade_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_signal_fingerprint UNIQUE (account_id, symbol, ltf, variant, event_kind, bar_time)
);

CREATE TABLE trades (
	id SERIAL NOT NULL, 
	account_id INTEGER NOT NULL, 
	signal_id INTEGER, 
	symbol VARCHAR(32) NOT NULL, 
	direction INTEGER NOT NULL, 
	entry_price FLOAT NOT NULL, 
	sl FLOAT, 
	tp FLOAT, 
	lots_or_qty FLOAT NOT NULL, 
	opened_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	closed_at TIMESTAMP WITH TIME ZONE, 
	exit_price FLOAT, 
	pnl FLOAT, 
	r_multiple FLOAT, 
	broker_order_id VARCHAR(64), 
	status VARCHAR(16) NOT NULL, 
	risk_amount FLOAT, 
	equity_at_entry FLOAT, 
	equity_at_exit FLOAT, 
	PRIMARY KEY (id), 
	UNIQUE (broker_order_id)
);

CREATE TABLE app_settings (
	key VARCHAR(64) NOT NULL, 
	value VARCHAR(500) NOT NULL, 
	PRIMARY KEY (key)
);

CREATE TABLE journal_entries (
	id SERIAL NOT NULL, 
	trade_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	author VARCHAR(64) NOT NULL, 
	title VARCHAR(200), 
	body TEXT NOT NULL, 
	tags VARCHAR(200), 
	PRIMARY KEY (id), 
	FOREIGN KEY(trade_id) REFERENCES trades (id)
);

CREATE TABLE equity_snapshots (
	id SERIAL NOT NULL, 
	timestamp TIMESTAMP WITH TIME ZONE NOT NULL, 
	account_id INTEGER NOT NULL, 
	equity FLOAT NOT NULL, 
	balance FLOAT NOT NULL, 
	open_positions_count INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(account_id) REFERENCES accounts (id)
);

CREATE TABLE p2p_transactions (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	counterparty_name VARCHAR(120) NOT NULL, 
	contact VARCHAR(200), 
	type VARCHAR(16) NOT NULL, 
	currency VARCHAR(16) NOT NULL, 
	amount FLOAT NOT NULL, 
	rate FLOAT, 
	linked_account_id INTEGER, 
	status VARCHAR(16) NOT NULL, 
	notes TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(linked_account_id) REFERENCES accounts (id)
);

CREATE TABLE screenshots (
	id SERIAL NOT NULL, 
	trade_id INTEGER, 
	journal_entry_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	file_path VARCHAR(500) NOT NULL, 
	caption VARCHAR(300), 
	PRIMARY KEY (id), 
	FOREIGN KEY(trade_id) REFERENCES trades (id), 
	FOREIGN KEY(journal_entry_id) REFERENCES journal_entries (id)
);

ALTER TABLE signals ADD FOREIGN KEY(trade_id) REFERENCES trades (id);

ALTER TABLE trades ADD FOREIGN KEY(account_id) REFERENCES accounts (id);

ALTER TABLE signals ADD FOREIGN KEY(account_id) REFERENCES accounts (id);

ALTER TABLE trades ADD FOREIGN KEY(signal_id) REFERENCES signals (id);
