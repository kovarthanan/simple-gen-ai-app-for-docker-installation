"""Interactive knowledge-graph view: a small self-contained force layout in SVG.

No CDN or extra package needed. Drag nodes, drag the background to pan, scroll to zoom,
hover a node to highlight its neighbours, click it to pin its details.
"""
from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from config import COLORS

_TEMPLATE = r"""
<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
  html,body{margin:0;height:100%;background:#FBFCFE;font-family:'Instrument Sans',system-ui,sans-serif;overflow:hidden}
  svg{width:100%;height:100%;cursor:grab;display:block} svg.dragging{cursor:grabbing}
  .edge{stroke:#C3CAD7;stroke-width:1.3} .edge.hl{stroke:__SAFFRON__;stroke-width:2.4}
  .elabel{font-size:10px;fill:#9A5C05;font-weight:600;opacity:0;pointer-events:none} .elabel.hl{opacity:1}
  .node circle{stroke:#fff;stroke-width:2;cursor:pointer} .node text{font-size:11px;fill:#1A2233;pointer-events:none;font-weight:600}
  .faded{opacity:.15}
  #info{position:absolute;right:12px;top:12px;max-width:280px;background:#fff;border:1px solid #D9DEE8;border-radius:12px;
        padding:10px 12px;font-size:12.5px;color:#1A2233;display:none;box-shadow:0 6px 18px rgba(26,34,51,.08)}
  #info h4{margin:0 0 2px;font-size:14px} #info .lbl{color:#5B6578;margin-bottom:6px} #info li{margin:2px 0}
  #info ul{padding-left:16px;margin:0} #info .p{color:#9A5C05;font-weight:600}
  #hint{position:absolute;left:12px;bottom:10px;font-size:11.5px;color:#5B6578}
  #empty{position:absolute;inset:0;display:grid;place-items:center;color:#5B6578;font-size:14px;text-align:center}
</style></head><body>
<svg id="svg"><g id="vp"><g id="edges"></g><g id="nodes"></g></g></svg>
<div id="info"></div>
<div id="hint">Drag to move, scroll to zoom, click a node for details</div>
<script>
const DATA = __DATA__, COLORS = __COLORS__;
const svg = document.getElementById('svg'), vp = document.getElementById('vp');
const NS = 'http://www.w3.org/2000/svg';
if (!DATA.nodes.length) { document.body.insertAdjacentHTML('beforeend',
  '<div id="empty"><div><b style="color:#1A2233;font-size:16px">No relationships to show yet</b><br>Add documents or approve items in the review queue.</div></div>'); }
const W = () => svg.clientWidth || 800, H = () => svg.clientHeight || 600;
const byId = {}; DATA.nodes.forEach((n,i) => { byId[n.id]=n; n.deg=0; const a=2*Math.PI*i/DATA.nodes.length;
  n.x = W()/2 + Math.cos(a)*Math.min(W(),H())*0.3; n.y = H()/2 + Math.sin(a)*Math.min(W(),H())*0.3; n.vx=0; n.vy=0; });
const edges = DATA.edges.filter(e => byId[e.source] && byId[e.target]);
edges.forEach(e => { byId[e.source].deg++; byId[e.target].deg++; });
const nbr = {}; edges.forEach(e => { (nbr[e.source] ||= new Set()).add(e.target); (nbr[e.target] ||= new Set()).add(e.source); });

function tick(alpha){
  const ns = DATA.nodes, k = 90;
  for (let i=0;i<ns.length;i++) for (let j=i+1;j<ns.length;j++){
    const a=ns[i], b=ns[j]; let dx=a.x-b.x, dy=a.y-b.y, d2=dx*dx+dy*dy||0.01, d=Math.sqrt(d2);
    const f = k*k/d2*alpha; dx/=d; dy/=d; a.vx+=dx*f; a.vy+=dy*f; b.vx-=dx*f; b.vy-=dy*f; }
  edges.forEach(e => { const a=byId[e.source], b=byId[e.target]; let dx=b.x-a.x, dy=b.y-a.y, d=Math.sqrt(dx*dx+dy*dy)||0.01;
    const f=(d-k)*0.05*alpha; dx/=d; dy/=d; a.vx+=dx*f; a.vy+=dy*f; b.vx-=dx*f; b.vy-=dy*f; });
  ns.forEach(n => { n.vx += (W()/2-n.x)*0.004*alpha; n.vy += (H()/2-n.y)*0.004*alpha;
    if (!n.fixed){ n.x+=Math.max(-25,Math.min(25,n.vx)); n.y+=Math.max(-25,Math.min(25,n.vy)); } n.vx*=0.55; n.vy*=0.55; });
}
for (let i=0;i<350;i++) tick(1 - i/400);

const edgeEls = edges.map(e => { const l=document.createElementNS(NS,'line'); l.setAttribute('class','edge');
  const t=document.createElementNS(NS,'text'); t.setAttribute('class','elabel'); t.setAttribute('text-anchor','middle');
  t.textContent = e.type.replace(/_/g,' ').toLowerCase();
  document.getElementById('edges').append(l,t); return {e,l,t}; });
const nodeEls = DATA.nodes.map(n => { const g=document.createElementNS(NS,'g'); g.setAttribute('class','node');
  const r = 6 + Math.sqrt(n.deg)*3; const c=document.createElementNS(NS,'circle'); c.setAttribute('r',r);
  c.setAttribute('fill', COLORS[n.label||'Other'] || '#4B5A73'); const t=document.createElementNS(NS,'text');
  t.setAttribute('x', r+4); t.setAttribute('y', 4); t.textContent = n.name.length>28 ? n.name.slice(0,27)+'…' : n.name;
  if (DATA.nodes.length>60 && n.deg<2) t.style.display='none';
  const title=document.createElementNS(NS,'title'); title.textContent = n.name + (n.label ? ' ('+n.label+')' : '');
  g.append(c,t,title); document.getElementById('nodes').append(g); return {n,g}; });

function draw(){
  edgeEls.forEach(({e,l,t}) => { const a=byId[e.source], b=byId[e.target];
    l.setAttribute('x1',a.x); l.setAttribute('y1',a.y); l.setAttribute('x2',b.x); l.setAttribute('y2',b.y);
    t.setAttribute('x',(a.x+b.x)/2); t.setAttribute('y',(a.y+b.y)/2-4); });
  nodeEls.forEach(({n,g}) => g.setAttribute('transform', `translate(${n.x},${n.y})`));
}
draw();

let view = {x:0,y:0,s:1}; const applyView = () => vp.setAttribute('transform', `translate(${view.x},${view.y}) scale(${view.s})`);
function highlight(id){
  nodeEls.forEach(({n,g}) => g.classList.toggle('faded', !!id && n.id!==id && !(nbr[id]&&nbr[id].has(n.id))));
  edgeEls.forEach(({e,l,t}) => { const on = !!id && (e.source===id || e.target===id);
    l.classList.toggle('hl', on); t.classList.toggle('hl', on); l.classList.toggle('faded', !!id && !on); });
}
const info = document.getElementById('info'); let pinned = null;
function showInfo(n){
  const out = edges.filter(e=>e.source===n.id).map(e=>`<li>${esc(n.name)} <span class="p">${esc(e.type.replace(/_/g,' ').toLowerCase())}</span> ${esc(byId[e.target].name)}</li>`);
  const inc = edges.filter(e=>e.target===n.id).map(e=>`<li>${esc(byId[e.source].name)} <span class="p">${esc(e.type.replace(/_/g,' ').toLowerCase())}</span> ${esc(n.name)}</li>`);
  info.innerHTML = `<h4>${esc(n.name)}</h4><div class="lbl">${esc(n.label||'Other')}, ${n.deg} connection${n.deg===1?'':'s'}</div><ul>${out.concat(inc).slice(0,12).join('')}</ul>`;
  info.style.display='block';
}
function esc(s){ return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

let drag=null, pan=null;
nodeEls.forEach(({n,g}) => {
  g.addEventListener('mouseenter', () => { if(!pinned) highlight(n.id); });
  g.addEventListener('mouseleave', () => { if(!pinned) highlight(null); });
  g.addEventListener('mousedown', ev => { ev.stopPropagation(); drag={n, moved:false}; n.fixed=true; });
  g.addEventListener('click', ev => { ev.stopPropagation(); if (drag && drag.moved) return;
    pinned = pinned===n.id ? null : n.id; highlight(pinned); pinned ? showInfo(n) : (info.style.display='none'); });
});
svg.addEventListener('mousedown', ev => { pan={x:ev.clientX-view.x, y:ev.clientY-view.y}; svg.classList.add('dragging'); });
window.addEventListener('mousemove', ev => {
  if (drag){ drag.moved=true; const r=svg.getBoundingClientRect(); drag.n.x=(ev.clientX-r.left-view.x)/view.s; drag.n.y=(ev.clientY-r.top-view.y)/view.s; draw(); }
  else if (pan){ view.x=ev.clientX-pan.x; view.y=ev.clientY-pan.y; applyView(); } });
window.addEventListener('mouseup', () => { if (drag) setTimeout(()=>{drag=null},0); pan=null; svg.classList.remove('dragging'); });
svg.addEventListener('click', () => { pinned=null; highlight(null); info.style.display='none'; });
svg.addEventListener('wheel', ev => { ev.preventDefault(); const r=svg.getBoundingClientRect(), mx=ev.clientX-r.left, my=ev.clientY-r.top;
  const s = Math.max(0.3, Math.min(3, view.s * (ev.deltaY<0 ? 1.1 : 0.9)));
  view.x = mx-(mx-view.x)*s/view.s; view.y = my-(my-view.y)*s/view.s; view.s=s; applyView(); }, {passive:false});
</script></body></html>
"""


def _safe_json(value) -> str:
    # entity names come from documents/LLM output: never let them close the <script> tag
    return json.dumps(value).replace("</", "<\\/").replace("<!--", "<\\!--")


def render_graph(subgraph: dict, label_colors: dict[str, str], height: int = 620) -> None:
    html = (_TEMPLATE.replace("__DATA__", _safe_json(subgraph))
            .replace("__COLORS__", _safe_json(label_colors))
            .replace("__SAFFRON__", COLORS["saffron"]))
    if hasattr(st, "iframe"):  # Streamlit >= 1.5x
        st.iframe(html, height=height)
    else:
        components.html(html, height=height, scrolling=False)
