// Metadata pagination never truncates the archive. FITS are opened on demand.
export class ArchiveBrowser {
  constructor(container,onOpen){
    this.rows=[];this.page=0;this.pageSize=50;this.onOpen=onOpen;
    container.innerHTML='<div class="card-heading"><span class="eyebrow">ARQUIVO DA REGIÃO</span><h3>Todas as imagens disponíveis</h3></div><p class="help" id="catalogue-scope">Uma busca ao arquivo lista todos os detectores e as duas coleções selecionadas.</p><div class="catalogue-controls"><label>Detector<select id="catalogue-detector"><option value="all">Todos os seis detectores</option>'+[1,2,3,4,5,6].map(n=>`<option value="SPHEREx-D${n}">D${n}</option>`).join('')+'</select></label><label>Filtrar por data, ID ou coleção<input id="catalogue-search" placeholder="Ex.: 2026-04 ou spherex_qr3"></label></div><p id="catalogue-count" class="help" aria-live="polite"></p><div class="catalogue-table"><table><thead><tr><th>Data UTC</th><th>Detector</th><th>Coleção</th><th>Exposição</th><th>Abrir</th></tr></thead><tbody id="catalogue-body"></tbody></table></div><div class="catalogue-controls"><button id="catalogue-prev">← Anterior</button><span id="catalogue-page"></span><button id="catalogue-next">Próxima →</button><button id="catalogue-export">↓ Lista completa CSV</button></div>';
    this.el=id=>container.querySelector('#'+id);
    for(const id of ['catalogue-detector','catalogue-search'])this.el(id).addEventListener(id.endsWith('search')?'input':'change',()=>{this.page=0;this.render();});
    this.el('catalogue-prev').onclick=()=>{this.page--;this.render();};this.el('catalogue-next').onclick=()=>{this.page++;this.render();};
    this.el('catalogue-export').onclick=()=>{const fields=['date','energy_bandpassname','collection','obs_id','access_url'];const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"';const content=fields.join(',')+'\n'+this.rows.map(r=>fields.map(f=>quote(r[f])).join(',')).join('\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([content],{type:'text/csv'}));a.download='spherex-all-images.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
  }
  setRows(rows,scope){
    this.rows=[...new Map(rows.map(r=>[r.access_url,r])).values()].map(r=>({...r,date:r.date||new Date((Number(r.t_min)-40587)*864e5).toISOString()})).sort((a,b)=>a.date.localeCompare(b.date));this.page=0;this.el('catalogue-scope').textContent=scope;this.render();
  }
  render(){
    const filter=this.el('catalogue-detector').value,q=this.el('catalogue-search').value.toLowerCase();
    const rows=this.rows.filter(r=>(filter==='all'||r.energy_bandpassname===filter)&&[r.date,r.obs_id,r.collection].join(' ').toLowerCase().includes(q));
    const pages=Math.max(1,Math.ceil(rows.length/this.pageSize));this.page=Math.max(0,Math.min(pages-1,this.page));
    this.el('catalogue-count').textContent=`${rows.length} imagens neste filtro · ${this.rows.length} arquivos listados. Versões de coleções diferentes permanecem acessíveis.`;
    this.el('catalogue-page').textContent=`Página ${this.page+1} de ${pages}`;this.el('catalogue-prev').disabled=this.page===0;this.el('catalogue-next').disabled=this.page>=pages-1;
    const body=this.el('catalogue-body');body.replaceChildren();
    for(const row of rows.slice(this.page*this.pageSize,(this.page+1)*this.pageSize)){
      const tr=document.createElement('tr');for(const v of [row.date.replace('T',' ').slice(0,19),row.energy_bandpassname,row.collection,row.obs_id]){const td=document.createElement('td');td.textContent=v;tr.append(td);}
      const td=document.createElement('td'),b=document.createElement('button'),a=document.createElement('a');b.textContent='Ver';b.onclick=async()=>{b.disabled=true;try{await this.onOpen(row);}finally{b.disabled=false;}};a.textContent='FITS ↗';a.href=row.access_url;a.target='_blank';a.rel='noopener';td.append(b,a);tr.append(td);body.append(tr);
    }
  }
}
