import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from preprocess_jobs import process_archive, process_postings, write_quality


def test_streaming_quality_outputs(tmp_path):
    postings = tmp_path / "postings.csv"
    pd.DataFrame({
        "job_posting_url": ["https://www.linkedin.com/jobs/view/1", "https://www.linkedin.com/jobs/view/2"],
        "title": [" Analyst ", "Engineer"], "listed_time": [1710000000000, 1710000001000],
        "normalized_salary": [50000, -1], "formatted_work_type": ["Full-time", None],
    }).to_csv(postings, index=False)
    archive = tmp_path / "archive"; archive.mkdir()
    pd.DataFrame({"job_link": ["https://www.linkedin.com/jobs/view/3"], "job_title": ["Nurse"], "first_seen": ["2024-01-01"], "last_processed_time": ["2024-01-02"], "job_type": ["Onsite"], "job_level": ["Mid senior"], "search_country": ["US"]}).to_csv(archive / "linkedin_job_postings.csv", index=False)
    pd.DataFrame({"job_link": ["https://www.linkedin.com/jobs/view/3"], "job_skills": ["Python"]}).to_csv(archive / "job_skills.csv", index=False)
    pd.DataFrame({"job_link": ["https://www.linkedin.com/jobs/view/3"], "job_summary": ["Summary"]}).to_csv(archive / "job_summary.csv", index=False)
    out = tmp_path / "out"; out.mkdir()
    p = process_postings(postings, out, 1); ar = process_archive(archive, out, 1)
    write_quality({"postings": p, "archive": ar}, out)
    assert p["rows"] == 2 and p["invalid_salary"] == 1
    assert ar["rows"] == 1 and ar["job_skills_covered"] == 1
    assert (out / "data_quality_report.csv").exists()
