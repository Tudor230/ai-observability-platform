-- Create the platform databases inside the shared Postgres.
CREATE DATABASE aiobs;        -- backend platform data
CREATE DATABASE phoenix;      -- Phoenix trace storage
CREATE DATABASE aiobs_test;   -- backend test suite (drop/recreate per run)