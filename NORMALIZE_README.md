normalize_sources.py

Streaming provenance/key normalizer for postings.csv and archive/*.csv. It writes only to --output and uses SQLite for archive side tables, so job_summary.csv is never loaded into memory.

Sample smoke test:
python3 normalize_sources.py --postings /path/postings.csv --archive /path/archive --output /tmp/jobs_norm --sample 100 --join

Full normalization (no --join to avoid writing a huge denormalized CSV):
python3 normalize_sources.py --postings ... --archive ... --output processed_jobs

Outputs: postings_normalized.csv, archive_master_normalized.csv, archive_join.sqlite. Add --join only when a denormalized archive CSV is explicitly required.
