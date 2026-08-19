#!/usr/bin/env python3
"""Stream-process archive master + skills only; never opens job_summary.csv."""
import argparse, csv, hashlib, json, re, sqlite3
from pathlib import Path

ID_RE = re.compile(r"(?:-|/)(\d{7,})(?:[/?#]|$)")
def clean(v): return re.sub(r"\s+", " ", (v or "").replace("\ufeff", "")).strip()
def url(v): return clean(v).split("#",1)[0].split("?",1)[0].rstrip("/")
def key(u):
    m=ID_RE.search(u)
    return "linkedin:"+m.group(1) if m else "url:"+hashlib.sha1(u.encode()).hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--archive',type=Path,required=True); ap.add_argument('--output',type=Path,required=True); ap.add_argument('--chunksize',type=int,default=50000); a=ap.parse_args(); a.output.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(a.output/'archive_skills_join.sqlite'); db.execute('CREATE TABLE IF NOT EXISTS jobs (job_link TEXT PRIMARY KEY, job_key TEXT, snapshot_date TEXT, job_title TEXT, company TEXT, job_location TEXT)'); db.execute('CREATE TABLE IF NOT EXISTS skills (job_link TEXT PRIMARY KEY, job_skills TEXT)')
    master_out=a.output/'linkedin_job_postings_normalized.csv'; skill_out=a.output/'job_skills_normalized.csv'; master_rows=skill_rows=dup_master=dup_skill=0
    with (a.archive/'linkedin_job_postings.csv').open(encoding='utf-8-sig',newline='',errors='replace') as src, master_out.open('w',encoding='utf-8',newline='') as dst:
        rd=csv.DictReader(src); fields=['job_key','source_dataset','snapshot_date','source_url']+[x for x in (rd.fieldnames or []) if x not in {'job_key','source_dataset','snapshot_date','source_url'}]; w=csv.DictWriter(dst,fieldnames=fields); w.writeheader(); seen=set()
        for r in rd:
            u=url(r.get('job_link'));
            if not u or u in seen: dup_master+=1; continue
            seen.add(u); k=key(u); cleanr={c:clean(v) for c,v in r.items()}; cleanr.update(job_key=k,source_dataset='archive',source_url=u,snapshot_date=cleanr.get('first_seen','')[:10]); w.writerow({c:cleanr.get(c,'') for c in fields}); db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?)',(u,k,cleanr.get('first_seen','')[:10],cleanr.get('job_title',''),cleanr.get('company',''),cleanr.get('job_location',''))); master_rows+=1
    db.commit()
    with (a.archive/'job_skills.csv').open(encoding='utf-8-sig',newline='',errors='replace') as src, skill_out.open('w',encoding='utf-8',newline='') as dst:
        rd=csv.DictReader(src); w=csv.DictWriter(dst,fieldnames=['job_key','source_dataset','job_link','job_skills','has_skills']); w.writeheader(); seen=set()
        for r in rd:
            u=url(r.get('job_link'))
            if not u or u in seen: dup_skill+=1; continue
            seen.add(u); s=clean(r.get('job_skills')); k=key(u); w.writerow({'job_key':k,'source_dataset':'archive','job_link':u,'job_skills':s,'has_skills':bool(s)}); db.execute('INSERT OR REPLACE INTO skills VALUES (?,?)',(u,s)); skill_rows+=1
    db.commit(); covered=db.execute('SELECT COUNT(*) FROM skills s JOIN jobs j ON s.job_link=j.job_link').fetchone()[0]; missing=db.execute('SELECT COUNT(*) FROM jobs j LEFT JOIN skills s ON s.job_link=j.job_link WHERE s.job_link IS NULL').fetchone()[0]; db.close()
    report={'master_rows':master_rows,'skills_rows':skill_rows,'master_duplicate_urls':dup_master,'skills_duplicate_urls':dup_skill,'skills_matching_master':covered,'master_without_skills':missing,'skills_coverage_of_master':covered/master_rows if master_rows else 0,'summary_processed':False}
    (a.output/'data_quality_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)); print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__': main()
