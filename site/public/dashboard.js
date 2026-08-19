(() => {
  const data = window.JOB_DATA || {};
  const fmt = n => new Intl.NumberFormat('en-US').format(n || 0);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const max = arr => Math.max(...arr.map(x => x[1]), 1);
  const base = {titles:data.titles||[], locations:data.locations||[], companies:data.companies||[]};
  function bars(id, items, coral=false) {
    const el=document.getElementById(id); if(!items?.length){el.innerHTML='<div class="empty">目前沒有可顯示資料</div>';return}
    const m=max(items); el.innerHTML=items.map(([name,n])=>`<div class="bar-row"><span title="${esc(name)}">${esc(name)}</span><div class="bar-bg"><div class="bar ${coral?'coral':''}" style="width:${Math.max(3,n/m*100)}%"></div></div><b>${fmt(n)}</b></div>`).join('');
  }
  function render() {
    const skillRows = data.skillCoverage ?? data.skillSampleRows ?? 0;
    document.getElementById('totalJobs').textContent=fmt(data.totalJobs);
    document.getElementById('coverage').textContent=Math.round(skillRows/(data.totalJobs||1)*100)+'%';
    const skillRowsEl=document.getElementById('skillRows'); if(skillRowsEl) skillRowsEl.textContent=fmt(skillRows);
    const companyCountEl=document.getElementById('companyCount'); if(companyCountEl) companyCountEl.textContent=fmt((data.companies||[]).length)+'+';
    const locationCountEl=document.getElementById('locationCount'); if(locationCountEl) locationCountEl.textContent=fmt((data.locations||[]).length)+'+';
    document.getElementById('companyCount').textContent=fmt((data.companies||[]).length)+'+';
    document.getElementById('locationCount').textContent=fmt((data.locations||[]).length)+'+';
    bars('titles', data.titles); bars('locations', data.locations, true); bars('companies', data.companies);
    const chips=document.getElementById('skills'); chips.innerHTML=(data.skills||[]).map(([s,n])=>`<button class="chip" data-skill="${esc(s)}">${esc(s)} <span>${fmt(n)}</span></button>`).join('');
    chips.querySelectorAll('[data-skill]').forEach(b=>b.addEventListener('click',()=>{
      document.getElementById('search').value=b.dataset.skill;
      applyFilter(b.dataset.skill);
      document.getElementById('search').focus();
    }));
    document.getElementById('sampleNote').textContent=`技能排行以 ${fmt(data.skillSampleRows)} 筆已處理技能資料計算；選定技能後的職務、地點與公司分布為互動預覽。`;
  }
  function applyFilter(value) {
    const q=(value||'').trim().toLowerCase();
    const profile=(data.skillProfiles||{})[q];
    if(profile){bars('titles',profile.titles);bars('locations',profile.locations,true);bars('companies',profile.companies);}
    else {bars('titles',base.titles);bars('locations',base.locations,true);bars('companies',base.companies);document.querySelectorAll('.bar-row').forEach(r=>r.style.display=!q||r.textContent.toLowerCase().includes(q)?'grid':'none');}
    document.querySelectorAll('.chip').forEach(r=>r.style.opacity=(!q||r.textContent.toLowerCase().includes(q))?'1':'.28');
  }
  document.getElementById('reset').addEventListener('click',()=>{document.getElementById('search').value='';document.getElementById('scope').value='all';applyFilter('');});
  document.getElementById('search').addEventListener('input',e=>applyFilter(e.target.value));
  render();
})();
