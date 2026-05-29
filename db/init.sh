#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE todos (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    due_date DATE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
);
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set "appuser=$APP_DB_USER" \
    --set "apppass=$APP_DB_PASSWORD" \
    --set "appdb=$POSTGRES_DB" <<-'EOSQL'
CREATE USER :"appuser" WITH PASSWORD :'apppass';
GRANT CONNECT ON DATABASE :"appdb" TO :"appuser";
GRANT USAGE ON SCHEMA public TO :"appuser";
GRANT SELECT, INSERT, UPDATE, DELETE ON users, todos TO :"appuser";
GRANT USAGE, SELECT ON SEQUENCE users_id_seq, todos_id_seq TO :"appuser";
EOSQL
