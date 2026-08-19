#!/usr/bin/env python3
"""Lightweight streaming normalizer for provenance, keys and archive joins.

Unlike a dataframe workflow this uses csv + SQLite, so the 5GB summary file is
never loaded into memory. Inputs are read-only; all output goes to --output.
"""
import argparse, csv, datetime as dt, hashlib, re, sqlite3
from pathlib import Path

ID_RE = re.compile(r"(?:-|/)(\d{7,})(?:[/?#]|$)")
def clean_url(v):
    v=(v or '').strip().split('#',1)[0].split('?',1)[0].rstrip('/')
    if '://' in v:
        s,r=v.split('://',1); h,*p=r.split('/',1); v=s.lower()+'://'+h.lower()+('/'+p[0] if p else '')
    return v
def key(url, fallback=''):
    u=clean_url(url); m=ID_RE.search(u)
    return 'linkedin:'+m.group(1) if m else ('url:'+hashlib.sha1(u.encode()).hexdigest() if u else 'row:'+fallback)
def iso(v):
    v=(v or '').strip()
    if not v: return ''
    try:
        n=float(v); n=n/1000 if n>10_000_000_000 else n
        return dt.datetime.fromtimestamp(n,dt.timezone.utc).isoformat()
    except Exception:
        try:
            x=dt.datetime.fromisoformat(v.replace('Z','+00:00')); x=x.replace(tzinfo=dt.timezone.utc) if x.tzinfo is None else x
            return x.astimezone(dt.timezone.utc).isoformat()
        except Exception: return v
def boolean(v):
    x=(v or '').strip().lower(); return '1' if x in {'1','true','t','yes','y'} else ('0' if x in {'0','false','f','no','n'} else '')
def txt(v): return re.sub(r'\s+',' ',(v or '').replace('\ufeff','')).strip()
def rd(p): return csv.DictReader(Path(p).open(encoding='utf-8-sig',newline='',errors='replace'))
def emit(path, fields, rows):
    with Path(path).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)

def postings(src,out,n=0):
    r=rd(src); base=r.fieldnames or []; fields=['job_key','source_dataset','snapshot_date','source_url']+[x for x in base if x not in {'job_key','source_dataset','snapshot_date','source_url'}]+['listed_at_utc','original_listed_at_utc','expiry_at_utc','closed_at_utc']; seen=set(); rows=[]
    for i,x in enumerate(r,1):
        if n and i>n: break
        u=clean_url(x.get('job_posting_url')); k=key(u,x.get('job_id',str(i)))
        if k in seen: continue
        seen.add(k); x={a:txt(b) for a,b in x.items()}; x.update(job_key=k,source_dataset='postings',source_url=u,snapshot_date=iso(x.get('listed_time'))[:10],listed_at_utc=iso(x.get('listed_time')),original_listed_at_utc=iso(x.get('original_listed_time')),expiry_at_utc=iso(x.get('expiry')),closed_at_utc=iso(x.get('closed_time')))
        for b in ('remote_allowed','sponsored'):
            if b in x:x[b]=boolean(x[b])
        rows.append(x)
    emit(Path(out)/'postings_normalized.csv',fields,rows); return len(rows)

def archive(src,out,n=0,joined=False):
    out=Path(out); db=sqlite3.connect(out/'archive_join.sqlite'); c=db.cursor(); c.executescript('CREATE TABLE IF NOT EXISTS master(k TEXT PRIMARY KEY,u TEXT,snap TEXT,data TEXT); CREATE TABLE IF NOT EXISTS skills(u TEXT PRIMARY KEY,v TEXT); CREATE TABLE IF NOT EXISTS summaries(u TEXT PRIMARY KEY,v TEXT)')
    mr=rd(Path(src)/'linkedin_job_postings.csv'); base=mr.fieldnames or []; fields=['job_key','source_dataset','snapshot_date','source_url']+[x for x in base if x not in {'job_key','source_dataset','snapshot_date','source_url'}]; rows=[]; seen=set()
    for i,x in enumerate(mr,1):
        if n and i>n: break
        u=clean_url(x.get('job_link')); k=key(u,str(i))
        if u in seen: continue
        seen.add(u); x={a:txt(b) for a,b in x.items()}; x.update(job_key=k,source_dataset='archive',source_url=u,snapshot_date=iso(x.get('first_seen'))[:10]);
        for b in ('got_summary','got_ner','is_being_worked'):
            if b in x:x[b]=boolean(x[b])
        rows.append(x); c.execute('INSERT OR REPLACE INTO master VALUES (?,?,?,?)',(k,u,x['snapshot_date'],'\x1f'.join(x.get(f,'') for f in fields)))
    emit(out/'archive_master_normalized.csv',fields,rows); db.commit()
    # For a joined preview, scan the auxiliary files until EOF but retain only
    # the selected master keys.  Limiting each file to its first N rows can
    # produce an apparently empty description column because the files are
    # independently ordered.
    selected_urls = {x['source_url'] for x in rows} if (n and joined) else None
    for fn,table,col in [('job_skills.csv','skills','job_skills'),('job_summary.csv','summaries','job_summary')]:
        rr=rd(Path(src)/fn)
        for i,x in enumerate(rr,1):
            u=clean_url(x.get('job_link'))
            if not u or (selected_urls is not None and u not in selected_urls):
                if n and not joined and i>=n: break
                continue
            c.execute(f'INSERT OR REPLACE INTO {table} VALUES (?,?)',(u,txt(x.get(col))))
            if n and not joined and i>=n: break
        db.commit()
    if joined:
        with (out/'archive_joined_sample_or_full.csv').open('w',encoding='utf-8',newline='') as f:
            w=csv.writer(f); w.writerow(fields+['job_skills','job_summary'])
            for x in rows:
                s=c.execute('SELECT v FROM skills WHERE u=?',(x['source_url'],)).fetchone(); z=c.execute('SELECT v FROM summaries WHERE u=?',(x['source_url'],)).fetchone(); w.writerow([x.get(a,'') for a in fields]+[s[0] if s else '',z[0] if z else ''])
    db.close(); return len(rows)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--postings',type=Path); p.add_argument('--archive',type=Path); p.add_argument('--output',type=Path,required=True); p.add_argument('--sample',type=int,default=0); p.add_argument('--join',action='store_true'); a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=True)
    if a.postings: print('postings:',postings(a.postings,a.output,a.sample))
    if a.archive: print('archive master:',archive(a.archive,a.output,a.sample,a.join))
if __name__=='__main__': main()
