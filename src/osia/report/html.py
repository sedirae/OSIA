from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg

from ..exchange.dump import dump_investigation
from ..store.repo import Repo

REPORT_FORMAT = "osia-report"
REPORT_VERSION = "1.0"

_CSS = """
:root{--bg:#F5F7FA;--surface:#ffffff;--text:#172033;--accent:#2458C6;--muted:#5b6b85;--line:#d8e0ec;--warn:#9a3b1e;--ok:#1e7a3c;}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;line-height:1.45;}
header{background:var(--surface);border-bottom:1px solid var(--line);padding:14px 20px;position:sticky;top:0;z-index:5;}
header h1{font-size:1.15rem;margin:0 0 4px;}
.banner{background:#fdf3e7;border:1px solid #e8c9a8;color:var(--warn);padding:8px 12px;border-radius:6px;margin:8px 20px;font-size:.85rem;}
nav{display:flex;gap:6px;flex-wrap:wrap;padding:0 20px 10px;background:var(--surface);border-bottom:1px solid var(--line);position:sticky;top:64px;z-index:5;}
nav button{border:1px solid var(--line);background:var(--surface);color:var(--text);border-radius:6px;padding:6px 12px;cursor:pointer;font-size:.85rem;}
nav button[aria-selected="true"]{background:var(--accent);color:#fff;border-color:var(--accent);}
nav button:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid var(--accent);outline-offset:2px;}
main{padding:16px 20px;max-width:1200px;margin:0 auto;}
.panel{display:none;}
.panel.active{display:block;}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px;}
.toolbar input,.toolbar select{border:1px solid var(--line);border-radius:6px;padding:6px 10px;font-size:.85rem;background:var(--surface);color:var(--text);}
#graph-wrap{background:var(--surface);border:1px solid var(--line);border-radius:8px;overflow:hidden;}
svg#graph{width:100%;height:560px;display:block;cursor:grab;}
.legend{font-size:.78rem;color:var(--muted);padding:6px 10px;}
.card{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin-bottom:12px;}
.card h3{margin:0 0 6px;font-size:.95rem;}
.tag{display:inline-block;border-radius:10px;padding:1px 8px;font-size:.72rem;margin-right:4px;border:1px solid var(--line);background:var(--bg);}
.tag.confirmed{color:var(--ok);border-color:var(--ok);}
.tag.hypothesis{color:var(--muted);}
.tag.contradicted{color:var(--warn);border-color:var(--warn);}
.tag.validated{color:var(--ok);border-color:var(--ok);}
.tag.rejected{color:var(--warn);border-color:var(--warn);}
table{border-collapse:collapse;width:100%;font-size:.82rem;}
th,td{border:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top;}
th{background:var(--bg);}
ul.tree{list-style:none;padding-left:14px;border-left:2px solid var(--line);}
.muted{color:var(--muted);font-size:.8rem;}
a{color:var(--accent);}
.kv{font-size:.85rem;}
.kv b{display:inline-block;min-width:140px;color:var(--muted);font-weight:600;}
"""

_JS = """
const DATA = JSON.parse(document.getElementById('osia-data').textContent);
const $ = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => Array.from(r.querySelectorAll(s));
function esc(s){return String(s==null?'':s);}
function tag(cls, txt){return '<span class="tag '+cls+'">'+esc(txt)+'</span>';}
const SUPPORT_TAG = {documente:['confirmed','documenté'],corrobore:['confirmed','corroboré'],a_confirmer:['hypothesis','à confirmer'],contradictoire:['contradicted','contradictoire'],non_etabli:['hypothesis','non établi']};
function supportTag(s){const t=SUPPORT_TAG[s]||['hypothesis',s];return tag(t[0],t[1]);}
const DEC_TAG = {validated:['validated','validé'],rejected:['rejected','rejeté'],unexamined:['hypothesis','non examiné']};
function decTag(d){const t=DEC_TAG[d]||['hypothesis',d];return tag(t[0],t[1]);}

$$('nav button').forEach(b => b.addEventListener('click', () => {
  $$('nav button').forEach(x => x.setAttribute('aria-selected', x===b ? 'true':'false'));
  $$('.panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + b.dataset.tab));
}));

function renderSynthese(){
  const inv = DATA.investigation || {};
  $('#panel-synthese').innerHTML =
    '<div class="card"><h3>'+esc(inv.title)+'</h3>' +
    '<div class="kv"><b>Objectif</b> '+esc(inv.objective||'—')+'</div>' +
    '<div class="kv"><b>État</b> '+esc(inv.state)+(inv.stop_reason?' ('+esc(inv.stop_reason)+')':'')+'</div>' +
    '<div class="kv"><b>Profil</b> '+esc(inv.profile_id)+'</div>' +
    '<div class="kv"><b>Indices</b> '+esc((inv.hints||[]).join(', ')||'—')+'</div>' +
    '<div class="kv"><b>Exporté le</b> '+esc(DATA.meta.generated_at)+'</div></div>' +
    (DATA.objectif ? '<div class="card"><h3>Objectif suffisamment étayé</h3><div class="kv"><b>Décision moteur</b> '+esc(DATA.objectif.etaye?'OUI':'NON')+'</div><div class="kv"><b>Motif</b> '+esc(DATA.objectif.motif||'')+'</div></div>' : '') +
    (DATA.etayage && DATA.etayage.length ? '<div class="card"><h3>Étayage des assertions décisives</h3>' + DATA.etayage.map(e => '<div class="kv"><b>'+esc(e.assertion_id||'')+'</b> '+supportTag(e.support_level||'')+' '+esc(e.detail||'')+'</div>').join('') + '</div>' : '') +
    (DATA.meta.warnings.length ? '<div class="card"><h3>Avertissements</h3><ul>'+DATA.meta.warnings.map(w=>'<li>'+esc(w)+'</li>').join('')+'</ul></div>' : '');
}

function renderArbre(){
  const brs = DATA.branches||[];
  const byParent = {};
  brs.forEach(b => {const k = b.parent_branch_id||'root';(byParent[k]=byParent[k]||[]).push(b);});
  function node(b){return '<li><b>'+esc(b.objective)+'</b> <span class="muted">'+esc(b.id)+' — '+esc(b.state)+(b.stop_reason?' ('+esc(b.stop_reason)+')':'')+' prof. '+esc(b.depth)+'</span><ul class="tree">'+(byParent[b.id]||[]).map(node).join('')+'</ul></li>';}
  $('#panel-arbre').innerHTML = '<div class="card"><ul class="tree">'+(byParent['root']||[]).map(node).join('')+'</ul></div>';
}

let nodes=[], links=[], scale=1, panX=0, panY=0;
function renderGraphe(){
  const ents = DATA.entities||[], rels = DATA.relations||[];
  const kinds = [...new Set(ents.map(e=>e.kind))];
  const R = 260, cx = 400, cy = 300;
  const pos = {};
  ents.forEach((e,i)=>{const k = kinds.indexOf(e.kind);const n = ents.filter(x=>x.kind===e.kind).length;const idx = ents.filter(x=>x.kind===e.kind).indexOf(e);const a = (2*Math.PI*idx/Math.max(n,1)) + k*0.7;pos[e.id]={x:cx+R*Math.cos(a),y:cy+R*Math.sin(a),e};});
  const svg = $('#graph');svg.innerHTML='';
  const NS='http://www.w3.org/2000/svg';
  function line(x1,y1,x2,y2,cls,label){const l=document.createElementNS(NS,'line');l.setAttribute('x1',x1);l.setAttribute('y1',y1);l.setAttribute('x2',x2);l.setAttribute('y2',y2);l.setAttribute('stroke',cls==='contradicted'?'#9a3b1e':cls==='confirmed'?'#1e7a3c':'#5b6b85');l.setAttribute('stroke-width',cls==='contradicted'?2.4:1.6);if(cls==='hypothesis')l.setAttribute('stroke-dasharray','5 4');svg.appendChild(l);if(label&&cls==='contradicted'){const t=document.createElementNS(NS,'text');t.setAttribute('x',(x1+x2)/2);t.setAttribute('y',(y1+y2)/2);t.setAttribute('fill','#9a3b1e');t.setAttribute('font-size','10');t.textContent=label;svg.appendChild(t);}}
  rels.forEach(r=>{const a=pos[r.src_id],b=pos[r.dst_id];if(a&&b)line(a.x,a.y,b.x,b.y,r.status==='contradicted'?'contradicted':r.status==='confirmed'?'confirmed':'hypothesis',r.status==='contradicted'?r.type:'');});
  ents.forEach(e=>{const p=pos[e.id];if(!p)return;const g=document.createElementNS(NS,'g');g.setAttribute('transform','translate('+p.x+','+p.y+')');g.style.cursor='pointer';const c=document.createElementNS(NS,'circle');c.setAttribute('r',14);c.setAttribute('fill',e.merged_into?'#c9d4e8':'#2458C6');svg.appendChild(g);g.appendChild(c);const t=document.createElementNS(NS,'text');t.setAttribute('y',26);t.setAttribute('text-anchor','middle');t.setAttribute('font-size','10');t.setAttribute('fill','#172033');t.textContent=(e.data&&(e.data.nom||e.data.name||e.data.label))||e.kind;g.appendChild(t);g.addEventListener('click',()=>showEntity(e.id));});
  nodes = ents; window._pos = pos;
}
function applyGraphFilter(){
  const kind = $('#f-kind').value, sup = $('#f-support').value;
  $$('#graph g').forEach(g=>{g.style.display='';});
  const ents = DATA.entities||[];
  ents.forEach(e=>{if(kind && e.kind!==kind){} });
  renderGraphe();
}
function showEntity(id){
  const e = (DATA.entities||[]).find(x=>x.id===id);if(!e)return;
  const ids = (DATA.identifiers||[]).filter(i=>i.entity_id===id);
  const out = (DATA.relations||[]).filter(r=>r.src_id===id);
  const inc = (DATA.relations||[]).filter(r=>r.dst_id===id);
  $('#panel-entites').innerHTML = '<div class="card"><h3>'+esc((e.data&&(e.data.nom||e.data.name||e.data.label))||e.id)+' <span class="muted">'+esc(e.kind)+'</span></h3>'+
   '<div class="kv"><b>Identifiants</b> '+esc(ids.map(i=>i.scheme+': '+i.value_normalisee).join(', ')||'—')+'</div>'+
   '<div class="kv"><b>Données</b> <code>'+esc(JSON.stringify(e.data))+'</code></div>'+
   '<div class="kv"><b>Fusionnée dans</b> '+esc(e.merged_into||'—')+'</div>'+
   '<h4>Relations sortantes</h4><ul>'+out.map(r=>'<li>'+esc(r.type)+' → '+esc(r.dst_id)+' '+supportTag(r.support_level)+' '+decTag(r.human_decision)+'</li>').join('')+'</ul>'+
   '<h4>Relations entrantes</h4><ul>'+inc.map(r=>'<li>'+esc(r.src_id)+' → '+esc(r.type)+' '+supportTag(r.support_level)+' '+decTag(r.human_decision)+'</li>').join('')+'</ul></div>';
  $$('nav button').forEach(x => x.setAttribute('aria-selected', x.dataset.tab==='entites'?'true':'false'));
  $$('.panel').forEach(p => p.classList.toggle('active', p.id==='panel-entites'));
}
function renderEntites(){
  const q = ($('#q-entites').value||'').toLowerCase();
  const rows = (DATA.entities||[]).filter(e=>!q || JSON.stringify(e).toLowerCase().includes(q));
  $('#panel-entites').innerHTML = '<div class="toolbar"><input id="q-entites" placeholder="Rechercher une entité…" value="'+esc($('#q-entites')?$('#q-entites').value:'')+'" aria-label="Rechercher une entité"></div>'+
   rows.map(e=>'<div class="card"><h3><a href="#" data-ent="'+esc(e.id)+'">'+esc((e.data&&(e.data.nom||e.data.name||e.data.label))||e.id)+'</a> <span class="muted">'+esc(e.kind)+'</span></h3><div class="muted">'+esc(JSON.stringify(e.data)).slice(0,300)+'</div></div>').join('');
  $$('#panel-entites a[data-ent]').forEach(a=>a.addEventListener('click',ev=>{ev.preventDefault();showEntity(a.dataset.ent);}));
  const qi = $('#q-entites'); if(qi) qi.addEventListener('input', renderEntites);
}
function renderAssertions(){
  const q = ($('#q-assert').value||'').toLowerCase();
  const rows = (DATA.assertions||[]).filter(a=>!q || a.statement.toLowerCase().includes(q));
  $('#panel-assertions').innerHTML = '<div class="toolbar"><input id="q-assert" placeholder="Rechercher une assertion…" value="" aria-label="Rechercher une assertion"></div>'+
   rows.map(a=>'<div class="card"><h3>'+esc(a.statement)+'</h3><div>'+supportTag(a.support_level)+' '+decTag(a.human_decision)+' <span class="tag">'+esc(a.nature)+'</span>'+(a.decisive?' <span class="tag confirmed">décisive</span>':'')+(a.contradicted_by&&a.contradicted_by.length?' <span class="tag contradicted">contradictions: '+esc(a.contradicted_by.join(', '))+'</span>':'')+'</div><div class="muted">preuves: '+esc((a.proof_ids||[]).join(', ')||'—')+' — branche '+esc(a.branch_id||'—')+'</div></div>').join('');
  const qi=$('#q-assert'); if(qi) qi.addEventListener('input', renderAssertions);
}
function renderChrono(){
  const rows = (DATA.events||[]).slice().sort((a,b)=>String(a.created_at).localeCompare(String(b.created_at)));
  $('#panel-chrono').innerHTML = '<div class="card"><table><tr><th>Date</th><th>Événement</th><th>Détail</th></tr>'+
   rows.map(e=>'<tr><td>'+esc(e.created_at)+'</td><td>'+esc(e.type)+'</td><td><code>'+esc(JSON.stringify(e.payload)).slice(0,200)+'</code></td></tr>').join('')+'</table></div>';
}
function renderDecisions(){
  const rows = DATA.decisions||[];
  $('#panel-decisions').innerHTML = '<div class="card"><table><tr><th>Date</th><th>Action</th><th>Cible</th><th>Détail</th></tr>'+
   rows.map(d=>'<tr><td>'+esc(d.created_at)+'</td><td>'+esc(d.action)+'</td><td>'+esc(d.target_type)+' '+esc(d.target_id||'')+'</td><td><code>'+esc(JSON.stringify(d.payload)).slice(0,200)+'</code></td></tr>').join('')+'</table></div>';
}
function renderSources(){
  const rows = DATA.proofs||[];
  $('#panel-sources').innerHTML = '<div class="card"><p class="muted">Les contenus binaires des preuves ne sont pas embarqués dans ce rapport (lecture seule, aucun contenu actif des sources). Les originaux figurent dans l\'archive .osia.</p><table><tr><th>Date</th><th>Source</th><th>Type</th><th>SHA-256</th><th>Taille</th></tr>'+
   rows.map(p=>'<tr><td>'+esc(p.fetched_at)+'</td><td>'+esc(p.source_url||'—')+'</td><td>'+esc(p.media_type||'—')+'</td><td><code>'+esc(p.proof_sha256)+'</code></td><td>'+esc(p.size_bytes)+'</td></tr>').join('')+'</table></div>';
}
function renderGraphToolbar(){
  const kinds = [...new Set((DATA.entities||[]).map(e=>e.kind))];
  $('#f-kind').innerHTML = '<option value="">Tous types</option>'+kinds.map(k=>'<option>'+esc(k)+'</option>').join('');
}
renderSynthese();renderArbre();renderGraphe();renderGraphToolbar();renderEntites();renderAssertions();renderChrono();renderDecisions();renderSources();
const gwrap = $('#graph');
let dragging=false,sx=0,sy=0,vb=null;
function setView(){const svg=$('#graph');const w=800,h=600;svg.setAttribute('viewBox',(panX)+' '+(panY)+' '+(w/scale)+' '+(h/scale));}
gwrap.addEventListener('mousedown',e=>{dragging=true;sx=e.clientX;sy=e.clientY;});
window.addEventListener('mousemove',e=>{if(!dragging)return;const r=gwrap.getBoundingClientRect();panX-= (e.clientX-sx)* (800/scale)/r.width;panY-=(e.clientY-sy)*(600/scale)/r.height;sx=e.clientX;sy=e.clientY;setView();});
window.addEventListener('mouseup',()=>{dragging=false;});
gwrap.addEventListener('wheel',e=>{e.preventDefault();scale=Math.min(8,Math.max(0.25,scale*(e.deltaY<0?1.1:0.9)));setView();},{passive:false});
$('#f-kind').addEventListener('change',()=>{});
setView();
"""

_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ — Rapport OSIA</title>
<style>__CSS__</style>
</head>
<body>
<header><h1>__TITLE__</h1><div class="muted">Rapport OSIA autonome — photographie en lecture seule de l'investigation au moment de l'export (__GENERATED__).</div></header>
<div class="banner" role="note">Ce fichier HTML n'est pas chiffré : il est lisible par toute personne possédant ce fichier. Aucune ressource externe n'est chargée à l'ouverture ; aucun contenu actif provenant des sources collectées n'est exécuté.</div>
<nav role="tablist">
<button data-tab="synthese" aria-selected="true">Synthèse</button>
<button data-tab="graphe" aria-selected="false">Graphe</button>
<button data-tab="arbre" aria-selected="false">Arbre des recherches</button>
<button data-tab="entites" aria-selected="false">Entités</button>
<button data-tab="assertions" aria-selected="false">Assertions</button>
<button data-tab="chrono" aria-selected="false">Chronologie</button>
<button data-tab="decisions" aria-selected="false">Décisions</button>
<button data-tab="sources" aria-selected="false">Sources &amp; preuves</button>
</nav>
<main>
<section class="panel active" id="panel-synthese" role="tabpanel"></section>
<section class="panel" id="panel-graphe" role="tabpanel">
  <div class="toolbar">
    <label for="f-kind">Type d'entité</label><select id="f-kind"></select>
    <span class="legend">Traits pleins = confirmés, pointillés = hypothèses, libellé rouge = contradiction (charte V1.6). Glissez pour déplacer, molette pour zoomer.</span>
  </div>
  <div id="graph-wrap"><svg id="graph" viewBox="0 0 800 600" role="img" aria-label="Graphe de connaissances"></svg></div>
</section>
<section class="panel" id="panel-arbre" role="tabpanel"></section>
<section class="panel" id="panel-entites" role="tabpanel"></section>
<section class="panel" id="panel-assertions" role="tabpanel"></section>
<section class="panel" id="panel-chrono" role="tabpanel"></section>
<section class="panel" id="panel-decisions" role="tabpanel"></section>
<section class="panel" id="panel-sources" role="tabpanel"></section>
</main>
<script type="application/json" id="osia-data">__DATA__</script>
<script>__JS__</script>
</body>
</html>
"""


def _embed_json(data: dict[str, Any]) -> str:
    raw = json.dumps(data, ensure_ascii=False, default=str)
    return raw.replace("</", "<\\/")


def _strip_proofs(obj: Any) -> Any:
    """Retire récursivement les métadonnées de preuves (source_url, empreintes) d'une structure :
    une donnée exclue ne doit pas figurer dans le fichier produit (REC-D5-04)."""
    if isinstance(obj, dict):
        return {
            k: ([] if k in ("proofs", "preuves", "sources") else _strip_proofs(v))
            for k, v in obj.items()
            if k not in ("proof_sha256", "source_url")
        }
    if isinstance(obj, list):
        return [_strip_proofs(v) for v in obj]
    return obj


class ReportService:
    """Rapport HTML autonome et interactif, consultable hors ligne (T7.5, D5.7.1B, V1.6).

    Un seul fichier : donnees embarquees en JSON, script embarque vanilla, aucun appel
    reseau, aucun contenu actif des sources. Les donnees exclues ne figurent pas dans le
    fichier produit (REC-D5-04)."""

    def __init__(self, pool: asyncpg.Pool, repo: Repo, graph: Any = None):
        self.pool = pool
        self.repo = repo
        self.graph = graph

    async def build(
        self,
        investigation_id: str,
        *,
        branch_ids: Optional[list[str]] = None,
        exclusions: Optional[set[str]] = None,
        include_proofs_meta: bool = True,
    ) -> str:
        exclusions = set(exclusions or set())
        payload = await dump_investigation(self.pool, investigation_id, branch_ids=branch_ids, exclusions=exclusions)
        inv = payload["investigations"][0]
        etayage: list[dict] = []
        objectif: Optional[dict] = None
        if self.graph is not None:
            etayage = await self.graph.etayage(investigation_id)
            objectif = await self.graph.objective_etaye(investigation_id)
        if not include_proofs_meta:
            etayage = _strip_proofs(etayage)
        warnings: list[str] = []
        if exclusions:
            warnings.append("Export partiel : exclusions=" + ", ".join(sorted(exclusions)))
        proof_ids_used = {p for rows in (payload.get("assertions", []), payload.get("relations", [])) for r in rows for p in (r.get("proof_ids") or [])}
        proof_ids_have = {r["id"] for r in payload.get("proof_refs", [])}
        for pid in sorted(proof_ids_used - proof_ids_have):
            warnings.append(f"chaîne de preuve rompue : la preuve {pid} est référencée mais absente de l'export (T7.4)")
        data = {
            "meta": {
                "format": REPORT_FORMAT,
                "version": REPORT_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "partial": bool(exclusions or branch_ids),
                "exclusions": sorted(exclusions),
                "warnings": warnings,
                "include_proofs_meta": include_proofs_meta,
            },
            "investigation": inv,
            "branches": payload.get("branches", []),
            "entities": payload.get("entities", []),
            "identifiers": payload.get("entity_identifiers", []),
            "relations": payload.get("relations", []),
            "assertions": payload.get("assertions", []),
            "matches": payload.get("match_proposals", []),
            "decisions": payload.get("decisions", []),
            "proofs": payload.get("proof_refs", []) if include_proofs_meta else [],
            "events": payload.get("events", []),
            "etayage": etayage,
            "objectif": objectif,
        }
        title = html.escape(str(inv.get("title") or investigation_id))
        return (
            _HTML
            .replace("__TITLE__", title)
            .replace("__GENERATED__", html.escape(data["meta"]["generated_at"]))
            .replace("__CSS__", _CSS)
            .replace("__DATA__", _embed_json(data))
            .replace("__JS__", _JS)
        )
