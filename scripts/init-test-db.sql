-- Runs once, the first time the PostgreSQL container initialises its data
-- directory. Creates the throwaway database the test suite writes to, so the
-- development data is never touched by a test run.
CREATE DATABASE urlshortener_test;
