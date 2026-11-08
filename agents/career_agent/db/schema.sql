-- Shared schema: common to all agents
CREATE SCHEMA IF NOT EXISTS shared;

CREATE TABLE IF NOT EXISTS shared.users (
    user_id    TEXT PRIMARY KEY,
    name       TEXT,
    email      TEXT,
    created_at TIMESTAMP DEFAULT now()
);

-- Career Agent schema
CREATE SCHEMA IF NOT EXISTS career;

CREATE TABLE IF NOT EXISTS career.cvs (
    cv_id          SERIAL PRIMARY KEY,
    user_id        TEXT REFERENCES shared.users(user_id),
    file_path      TEXT,
    extracted_text TEXT,
    skills         JSONB,
    uploaded_at    TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS career.job_postings (
    job_posting_id SERIAL PRIMARY KEY,
    title          TEXT NOT NULL,
    company        TEXT NOT NULL,
    type           TEXT,
    url            TEXT,
    description    TEXT,
    skills         JSONB,
    deadline       DATE,
    UNIQUE (title, company)
);

CREATE TABLE IF NOT EXISTS career.matches (
    user_id        TEXT REFERENCES shared.users(user_id),
    job_posting_id INT  REFERENCES career.job_postings(job_posting_id),
    score          REAL,
    missing_skills JSONB,
    PRIMARY KEY (user_id, job_posting_id)
);

CREATE TABLE IF NOT EXISTS career.applications (
    application_id SERIAL PRIMARY KEY,
    user_id        TEXT REFERENCES shared.users(user_id),
    job_posting_id INT  REFERENCES career.job_postings(job_posting_id),
    status         TEXT DEFAULT 'planned',
    deadline       DATE,
    applied_at     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS career.cover_letters (
    cover_letter_id SERIAL PRIMARY KEY,
    application_id  INT REFERENCES career.applications(application_id),
    text            TEXT,
    version         INT DEFAULT 1,
    approved        BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS career.esco_cache (
    key  TEXT PRIMARY KEY,
    data JSONB
);
-- Tracker columns (added later; IF NOT EXISTS keeps re-runs safe)
ALTER TABLE career.applications ADD COLUMN IF NOT EXISTS interview_invited BOOLEAN DEFAULT FALSE;
ALTER TABLE career.applications ADD COLUMN IF NOT EXISTS accepted TEXT DEFAULT 'pending';
ALTER TABLE career.applications ADD COLUMN IF NOT EXISTS interview_date DATE;