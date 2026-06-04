/* Akıllı Otopark — gerçekçi AVM otopark haritası (Canvas).
   Backend (FastAPI) yalnızca veri verir; tüm çizim/animasyon/trafik burada. */

const C = {
  bg: "#1a1d24", lot: "#23272f", road: "#15171d", roadEdge: "#2e333d",
  slot: "#363c48", paint: "#737b8c", lane: "rgba(214,184,86,0.55)",
  island: "#2f5d3a", islandHi: "#3a724a", tree: "#356b43",
  mall: "#3b3950", glass: "#7fa9c4",
  ev: "#4eb696", disabled: "#4a86ce", suggested: "#f5c846", yourCar: "#f5c846",
  entrance: "#56c07a", exit: "#e08a4a", text: "#e6eaf2", dim: "#8a92a4",
  cross: "#c9cdd6", mallTop: "#494661",
};
const CARS = ["#7b8290","#62708a","#8a6266","#5c7284","#9296a0",
              "#6a707c","#72667c","#627e76","#8c7a62","#6e7a8a"];

const canvas = document.getElementById("lot");
const ctx = canvas.getContext("2d");

let L = null, T = null;
let routes = [];        // aktif yönlendirme rotaları: {pts, car, spotId} (çoklu araç destekli)
// Çoklu atamada her araca ayrı renk (tek araçta ilk renk = sarı kullanılır)
const HERO_COLORS = ["#f5c846","#5ec2f0","#f08a5e","#9d7cf0","#5ef0a8"];
let reservedMap = {};   // spot_id -> true (rezerve, dolu değil)
let anomalySpots = {};  // spot_id -> true (arızalı/çevrimdışı sensör — haritada işaretli)
let heatmapOn = false, heatData = {}, heatMax = 1;   // ısı haritası (kullanım sıklığı)
let vocc = {};          // görsel doluluk (animasyon gecikmeli)
let prevOcc = null;     // bir önceki gerçek doluluk (fark hesaplamak için)
let cars = [];          // gerçek olaylarla tetiklenen hareketli araçlar
let fades = {};         // spot_id -> {dir:+1 beliriş / -1 sönüş, t0} (animasyon slotu doluysa yumuşak geçiş)
let arriving = {};      // spot_id -> true: o yere giden (animasyonu süren) araç var -> üst üste park engellenir
let spotById = {};
let entranceId = null;
let aisleIds = [], entranceIds = [], vexitIds = [];
let last = performance.now();
let CARID = 0;          // araç önceliği (kavşakta geçiş hakkı için sabit id)

/* ---------- yardımcılar ---------- */
function rr(x, y, w, h, r) {
  r = Math.min(r, Math.abs(w) / 2, Math.abs(h) / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
const lerp = (a, b, t) => a + (b - a) * t;
const D = (ax, ay, bx, by) => Math.hypot(bx - ax, by - ay);
function shade(hex, f) {
  const n = parseInt(hex.slice(1), 16);
  return `rgb(${Math.min(255,((n>>16)&255)*f)|0},${Math.min(255,((n>>8)&255)*f)|0},${Math.min(255,(n&255)*f)|0})`;
}
function hashColor(id){let h=0;for(const c of id)h+=c.charCodeAt(0);return CARS[h%CARS.length];}
function S(x, y){ return [T.ox + (x - L.bounds.min_x) * T.scale, T.oy + (y - L.bounds.min_y) * T.scale]; }

/* ---------- transform ---------- */
function computeT(w, h) {
  const pad = 30;
  const ww = L.bounds.max_x - L.bounds.min_x, hh = L.bounds.max_y - L.bounds.min_y;
  const scale = Math.min((w - 2*pad)/ww, (h - 2*pad)/hh);
  T = { scale, ox: pad + (w-2*pad-ww*scale)/2, oy: pad + (h-2*pad-hh*scale)/2 };
}
function resize() {
  const dpr = window.devicePixelRatio||1, r = canvas.getBoundingClientRect();
  canvas.width = r.width*dpr; canvas.height = r.height*dpr;
  ctx.setTransform(dpr,0,0,dpr,0,0);
  if (L) computeT(r.width, r.height);
}
addEventListener("resize", resize);

/* ---------- araç çizimi ---------- */
function drawCar(x, y, ang, color, len, wid) {
  ctx.save(); ctx.translate(x, y); ctx.rotate(ang);
  ctx.fillStyle = "rgba(0,0,0,0.32)"; rr(-len/2+1.5,-wid/2+2.5,len,wid,wid*0.34); ctx.fill();
  const g = ctx.createLinearGradient(0,-wid/2,0,wid/2);
  g.addColorStop(0, shade(color,1.16)); g.addColorStop(1, shade(color,0.8));
  ctx.fillStyle = g; rr(-len/2,-wid/2,len,wid,wid*0.34); ctx.fill();
  ctx.fillStyle = shade(color,0.62); rr(-len*0.16,-wid*0.34,len*0.4,wid*0.68,wid*0.18); ctx.fill();
  ctx.fillStyle = "rgba(196,218,238,0.92)"; rr(len*0.13,-wid*0.3,len*0.13,wid*0.6,2); ctx.fill();
  ctx.fillStyle = "rgba(150,175,200,0.6)"; rr(-len*0.28,-wid*0.26,len*0.1,wid*0.52,2); ctx.fill();
  ctx.fillStyle = "rgba(255,248,205,0.95)";
  ctx.fillRect(len*0.46,-wid*0.34,len*0.05,wid*0.18); ctx.fillRect(len*0.46,wid*0.16,len*0.05,wid*0.18);
  ctx.restore();
}
function arrow(x, y, ang, s, color) {
  ctx.save(); ctx.translate(x,y); ctx.rotate(ang);
  ctx.fillStyle = color; ctx.beginPath();
  ctx.moveTo(s,0); ctx.lineTo(-s*0.5,s*0.6); ctx.lineTo(-s*0.5,-s*0.6); ctx.closePath(); ctx.fill();
  ctx.restore();
}

/* ---------- pathfinding (Dijkstra, yol grafı) ---------- */
function dijkstra(start, goal) {
  const N = L.road_nodes, A = L.road_adj;
  const dst = { [start]: 0 }, prev = {}, vis = {};
  const pq = [[0, start]];
  while (pq.length) {
    let bi = 0; for (let i=1;i<pq.length;i++) if (pq[i][0]<pq[bi][0]) bi=i;
    const [d,u] = pq.splice(bi,1)[0];
    if (vis[u]) continue; vis[u]=1;
    if (u===goal) break;
    for (const v of A[u]||[]) {
      const w = D(N[u][0],N[u][1],N[v][0],N[v][1]);
      if (dst[v]===undefined || d+w<dst[v]) { dst[v]=d+w; prev[v]=u; pq.push([d+w,v]); }
    }
  }
  if (dst[goal]===undefined) return null;
  const p=[]; let c=goal; while(c!==undefined){ p.unshift(L.road_nodes[c]); c=prev[c]; }
  return p;
}
function rand(arr){ return arr[(Math.random()*arr.length)|0]; }

/* ---------- olay tabanlı araçlar (gerçek doluluk değişimleri) ----------
   Bir yer dolunca -> araç girişten gelip park eder; boşalınca -> çıkışa gider.
   Her hareket gerçek bir sensör (MQTT) olayına karşılık gelir. */
class EventCar {
  constructor(pts, onArrive){
    this.pts=pts; this.onArrive=onArrive||null; this._fired=false;
    this.seg=0; this.t=0; this.done=false;
    this.speed=2.4+Math.random()*0.9; this.ang=0;   // gerçekçi, yavaş otopark hızı (takip edilebilir)
    this.color=rand(CARS); this.off=0.4;   // sağ şerit: kesikli çizginin hemen sağı
    this.px=pts[0][0]; this.py=pts[0][1]; this.id=CARID++; this.speedFactor=1;
    this.life=0;   // güvenlik ömrü (sn): çok uzun yolda kalan aracı zorla tamamla
  }
  _finish(){
    this.done=true;
    if(this.onArrive&&!this._fired){ this._fired=true; this.onArrive(); }
  }
  update(dt){
    if(this.done)return;
    this.life+=dt;
    let rem=this.speed*dt*this.speedFactor;   // araç-takibi: öndekine göre yumuşak yavaşla
    while(rem>0 && this.seg<this.pts.length-1){
      const a=this.pts[this.seg], b=this.pts[this.seg+1];
      const d=D(a[0],a[1],b[0],b[1])||1e-4, left=d*(1-this.t);
      if(rem>=left){rem-=left;this.seg++;this.t=0;}else{this.t+=rem/d;rem=0;}
      const aa=this.pts[this.seg], bb=this.pts[Math.min(this.seg+1,this.pts.length-1)];
      this.ang=Math.atan2(bb[1]-aa[1], bb[0]-aa[0]);
    }
    const pa=this.pts[this.seg], pb=this.pts[Math.min(this.seg+1,this.pts.length-1)];
    this.px=lerp(pa[0],pb[0],this.t); this.py=lerp(pa[1],pb[1],this.t);
    // Hedefe vardıysa VEYA güvenlik ömrü dolduysa tamamla -> kalıcı sıkışma/yığılma olmaz
    if(this.seg>=this.pts.length-1 || this.life>16) this._finish();
  }
  draw(len,wid){
    const a=this.pts[this.seg], b=this.pts[Math.min(this.seg+1,this.pts.length-1)];
    let x=lerp(a[0],b[0],this.t), y=lerp(a[1],b[1],this.t);
    const dx=b[0]-a[0], dy=b[1]-a[1], pl=Math.hypot(dx,dy)||1;
    // Sağ şeritte git; park manevrasında (yere giriş/çıkış) merkeze yumuşak geç
    let off=this.off;
    if(this.onArrive){ if(this.seg===this.pts.length-2) off*=(1-this.t); }  // varış: yere girerken merkeze
    else { if(this.seg===0) off*=this.t; }                                  // ayrılış: yerden çıkarken merkezden
    x += (-dy/pl)*off; y += (dx/pl)*off;   // (-dy,dx) = gidiş yönünün sağı
    const [sx,sy]=S(x,y); drawCar(sx,sy,this.ang,this.color,len,wid);
  }
}
// Aynı anda EKRANDA hareket eden araç sınırı (slot) — otopark doluluğuyla İLGİSİ YOK.
// Yüksek tutulur ki HER giriş/çıkış gerçekten sürerek olsun; araç ne pat diye belirir
// ne pat diye silinir. Tüm 240 yer erişilebilir (yol her zaman bulunur), bu yüzden fade
// pratikte hiç tetiklenmez; yalnız teorik bir emniyet sübabıdır. (Deadlock imkânsız:
// applyTraffic min hız 0.15 + life>16 emniyeti; perf: ~100 sprite Canvas için sorunsuz.)
const MAX_CARS = 250;
const FADE_MS = 450;
function fadeIn(id){  vocc[id]=true;  fades[id]={dir:1,  t0:performance.now()}; }  // yumuşak beliriş
function fadeOut(id){ vocc[id]=false; fades[id]={dir:-1, t0:performance.now()}; }  // yumuşak sönüş
// Bir yerin park aracı çizim alfası: fade varsa rampalanır, yoksa doluluk durumu (0/1)
function carAlpha(id, now){
  const f=fades[id];
  if(!f) return vocc[id]?1:0;
  const k=(now-f.t0)/FADE_MS;
  if(k>=1){ delete fades[id]; return vocc[id]?1:0; }
  return f.dir>0 ? k : (1-k);
}
function spawnArrival(spotId){
  // Üst üste park YOK: yer zaten doluysa ya da oraya giden araç varsa yeni varış spawn etme.
  if(vocc[spotId] || arriving[spotId]) return;
  const sp=spotById[spotId];
  // Slot dolu ya da yol yoksa: pat diye belirme yerine yumuşak beliriş (nadir; aşağıda yol her zaman bulunur)
  if(cars.length>MAX_CARS || !sp || !sp.access || !L.road_nodes[sp.access]){ fadeIn(spotId); return; }
  const path=dijkstra(rand(entranceIds), sp.access);
  if(!path){ fadeIn(spotId); return; }
  delete fades[spotId];
  arriving[spotId]=true;
  // Araç yere VARINCA park eder (yer hâlâ "gelen" olarak işaretliyse; yoksa boşalmış demektir)
  cars.push(new EventCar(path.concat([[sp.x,sp.y]]), ()=>{
    if(arriving[spotId]){ delete arriving[spotId]; vocc[spotId]=true; }
  }));
}
function spawnDeparture(spotId){
  delete arriving[spotId];                          // o yere giden araç varsa iptal (yer boşaldı)
  if(!vocc[spotId] && !fades[spotId]) return;       // zaten boş -> çıkacak araç yok (hayalet çıkış engellenir)
  const sp=spotById[spotId];
  // Slot dolu ya da yol yoksa: pat diye silme yerine yumuşak sönüş
  if(cars.length>MAX_CARS || !sp || !sp.access || !L.road_nodes[sp.access]){ fadeOut(spotId); return; }
  const path=dijkstra(sp.access, rand(vexitIds));
  if(path){ delete fades[spotId]; vocc[spotId]=false; cars.push(new EventCar([[sp.x,sp.y]].concat(path), null)); }
  else fadeOut(spotId);
}

/* ---------- yönlendirilen araç ---------- */
class Hero {
  constructor(pts, color){ this.pts=pts; this.seg=0; this.t=0; this.done=pts.length<2; this.speed=3.4; this.ang=0; this.off=0.4; this.x=pts[0][0]; this.y=pts[0][1]; this.px=this.x; this.py=this.y; this.id=CARID++; this.speedFactor=1; this.color=color||C.yourCar; }
  update(dt){
    if(this.done)return;
    let rem=this.speed*dt*this.speedFactor;
    while(rem>0 && this.seg<this.pts.length-1){
      const a=this.pts[this.seg], b=this.pts[this.seg+1];
      const d=D(a[0],a[1],b[0],b[1])||1e-4, left=d*(1-this.t);
      if(rem>=left){rem-=left;this.seg++;this.t=0;}else{this.t+=rem/d;rem=0;}
      const aa=this.pts[this.seg],bb=this.pts[Math.min(this.seg+1,this.pts.length-1)];
      this.ang=Math.atan2(bb[1]-aa[1],bb[0]-aa[0]);
    }
    if(this.seg>=this.pts.length-1){this.done=true;this.seg=this.pts.length-1;this.t=1;}
    const a=this.pts[this.seg],b=this.pts[Math.min(this.seg+1,this.pts.length-1)];
    this.x=lerp(a[0],b[0],this.t); this.y=lerp(a[1],b[1],this.t);
    this.px=this.x; this.py=this.y;
  }
  draw(len,wid){
    const a=this.pts[this.seg], b=this.pts[Math.min(this.seg+1,this.pts.length-1)];
    const dx=b[0]-a[0], dy=b[1]-a[1], pl=Math.hypot(dx,dy)||1;
    let off=this.off;
    if(this.seg>=this.pts.length-2) off*=(1-this.t);   // son segment: yere girerken merkeze
    const [sx,sy]=S(this.x+(-dy/pl)*off, this.y+(dx/pl)*off);
    ctx.beginPath(); ctx.arc(sx,sy,len*0.8,0,7); ctx.fillStyle="rgba(245,200,70,0.18)"; ctx.fill();
    drawCar(sx,sy,this.ang,this.color,len*1.14,wid*1.14);
  }
}

/* ---------- sahne çizimi ---------- */
function drawMall() {
  const m = L.mall;
  const [x0,y0]=S(m.x0,m.y0), [x1,y1]=S(m.x1,m.y1);
  const w=x1-x0, h=y1-y0;
  ctx.fillStyle=C.mall; rr(x0,y0,w,h,12); ctx.fill();
  ctx.fillStyle=C.mallTop; rr(x0,y0,w,h*0.26,12); ctx.fill();
  // vitrinler
  ctx.fillStyle=C.glass;
  const n=Math.max(8,(w/46)|0), gw=(w-30)/n;
  for(let i=0;i<n;i++){ rr(x0+15+i*gw, y0+h*0.36, gw-7, h*0.4, 3); ctx.fill(); }
  // etiket
  ctx.fillStyle=C.text; ctx.textAlign="center";
  ctx.font=`700 ${Math.max(h*0.2,14)}px "Segoe UI",system-ui,sans-serif`;
  ctx.fillText("ALIŞVERİŞ MERKEZİ", (x0+x1)/2, y0+h*0.26);
  // yaya kapıları + kanopi + zebra
  ctx.font=`600 ${Math.max(T.scale*0.5,10)}px "Segoe UI",sans-serif`;
  for(const d of L.doors){
    const [dx,dy]=S(d.x,m.y1);
    ctx.fillStyle="#2b2f3a"; rr(dx-T.scale*1.4,dy-7,T.scale*2.8,16,4); ctx.fill();
    ctx.fillStyle=C.glass; rr(dx-T.scale*1.2,dy-3,T.scale*2.4,9,3); ctx.fill();
    ctx.fillStyle=C.dim; ctx.fillText("AVM", dx, dy+24);
    // zebra geçit (kapıdan aşağı)
    const [zx,zy]=S(d.x, 0.2);
    ctx.fillStyle=C.cross;
    for(let i=0;i<5;i++) ctx.fillRect(dx-T.scale*0.9+i*T.scale*0.38, dy+18, T.scale*0.22, zy-dy-18);
  }
}
function drawRoads() {
  const hw = Math.max(T.scale*2.7, 14);   // geniş yatay sürüş yolları
  ctx.lineCap="round";
  // dikey + kapı yolları (geniş)
  ctx.strokeStyle=C.road; ctx.lineWidth=Math.max(T.scale*2.0,11);
  for(const s of L.roads.v.concat(L.roads.gates)){ const[a,b]=[S(s[0],s[1]),S(s[2],s[3])];
    ctx.beginPath(); ctx.moveTo(a[0],a[1]); ctx.lineTo(b[0],b[1]); ctx.stroke(); }
  // yatay yollar
  ctx.lineWidth=hw;
  for(const s of L.roads.h){ const[a,b]=[S(s[0],s[1]),S(s[2],s[3])];
    ctx.beginPath(); ctx.moveTo(a[0],a[1]); ctx.lineTo(b[0],b[1]); ctx.stroke(); }
  // sarı kesikli orta şerit + yön okları (hem yatay hem dikey yollarda)
  ctx.strokeStyle=C.lane; ctx.lineWidth=1.5; ctx.setLineDash([10,13]);
  L.roads.h.forEach((s,idx)=>{ const[a,b]=[S(s[0],s[1]),S(s[2],s[3])];
    ctx.beginPath(); ctx.moveTo(a[0],a[1]); ctx.lineTo(b[0],b[1]); ctx.stroke();
    const dir = idx%2? Math.PI:0, ya=(a[1]+b[1])/2;
    for(let k=1;k<=4;k++){ const x=lerp(a[0],b[0],k/5); arrow(x,ya,dir,6,"rgba(180,188,205,0.5)"); }
  });
  L.roads.v.forEach((s,idx)=>{ const[a,b]=[S(s[0],s[1]),S(s[2],s[3])];
    ctx.beginPath(); ctx.moveTo(a[0],a[1]); ctx.lineTo(b[0],b[1]); ctx.stroke();
    const dir = idx%2? -Math.PI/2:Math.PI/2, xa=(a[0]+b[0])/2;
    for(let k=1;k<=4;k++){ const y=lerp(a[1],b[1],k/5); arrow(xa,y,dir,6,"rgba(180,188,205,0.45)"); }
  });
  ctx.setLineDash([]);
}
function drawSections() {
  // Yalnızca çok hafif bölüm çerçevesi (spotların altında kalır, sorun değil).
  for(const sec of L.sections){
    const [x0,y0]=S(sec.x0,sec.y0), [x1,y1]=S(sec.x1,sec.y1);
    ctx.strokeStyle="rgba(255,255,255,0.04)"; ctx.lineWidth=1; rr(x0,y0,x1-x0,y1-y0,6); ctx.stroke();
  }
}
// Bölüm harfleri (A–E): spotların ÜSTÜNE, her bandın SOLUNDAKİ boşluğa, küçük + şeffaf.
// Böylece park yerlerini kapatmadan hangi blokta olduğun net görünür.
function drawSectionLabels() {
  ctx.textAlign="center"; ctx.textBaseline="middle";
  ctx.font=`700 ${Math.max(T.scale*1.7,15)}px "Segoe UI",sans-serif`;
  for(const sec of L.sections){
    const mx=(L.bounds.min_x + sec.x0)/2;           // sol kenar boşluğunun ortası
    const [lx,ly]=S(mx, (sec.y0+sec.y1)/2);
    ctx.fillStyle="rgba(214,222,236,0.38)";          // şeffaf, dikkat dağıtmaz
    ctx.fillText(sec.label, lx, ly);
  }
  ctx.textBaseline="alphabetic";
}
function drawIslands() {
  for(const il of L.islands){
    const [x,y]=S(il.x,il.y), w=Math.max(T.scale*0.7,5), h=Math.max(T.scale*3.0,16);
    ctx.fillStyle=C.island; rr(x-w/2,y-h/2,w,h,5); ctx.fill();
    ctx.fillStyle=C.tree; ctx.beginPath(); ctx.arc(x,y-h*0.28,w*0.7,0,7); ctx.fill();
    ctx.beginPath(); ctx.arc(x,y+h*0.28,w*0.7,0,7); ctx.fill();
  }
}
function bolt(cx,cy,s){ ctx.fillStyle=C.suggested; ctx.beginPath();
  ctx.moveTo(cx+s*0.15,cy-s);ctx.lineTo(cx-s*0.45,cy+s*0.15);ctx.lineTo(cx-s*0.02,cy+s*0.15);
  ctx.lineTo(cx-s*0.15,cy+s);ctx.lineTo(cx+s*0.45,cy-s*0.15);ctx.lineTo(cx+s*0.02,cy-s*0.15);ctx.closePath();ctx.fill(); }
function wheelchair(cx,cy,s){ ctx.strokeStyle="#cdddf2";ctx.fillStyle="#cdddf2";ctx.lineWidth=1.5;
  ctx.beginPath();ctx.arc(cx,cy-s*0.85,s*0.28,0,7);ctx.fill();
  ctx.beginPath();ctx.arc(cx,cy+s*0.35,s*0.8,0,7);ctx.stroke(); }

function drawSpots(now){
  const sw=Math.max(T.scale*0.84,5), sh=Math.max(T.scale*1.4,9);
  const cl=Math.max(T.scale*0.91,8), cw=Math.max(T.scale*0.42,5);   // 0.70x küçültülmüş
  const pulse=0.5+0.5*Math.sin(now/240);
  for(const s of L.spots){
    const [cx,cy]=S(s.x,s.y), x=cx-sw/2, y=cy-sh/2, upper=s.face==="up";
    // Isı haritası modu: TÜM yerler kullanım sıklığına göre boyanır (araç gizlenir -> saf ısı haritası)
    if(heatmapOn){
      const used=heatData[s.id]||0;
      ctx.fillStyle = used>0 ? heatColor(used) : "rgba(74,84,104,0.5)";
      rr(x,y,sw,sh,2); ctx.fill();
      if(routes.some(r=>r.spotId===s.id)){ ctx.strokeStyle=`rgba(245,200,70,${0.5+0.5*pulse})`; ctx.lineWidth=3; rr(x-4,y-4,sw+8,sh+8,5); ctx.stroke(); }
      continue;
    }
    ctx.fillStyle = C.slot;
    rr(x,y,sw,sh,2); ctx.fill();
    ctx.strokeStyle=C.paint; ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(x,y);ctx.lineTo(x,y+sh); ctx.moveTo(x+sw,y);ctx.lineTo(x+sw,y+sh);
    const by=upper?y+sh:y; ctx.moveTo(x,by);ctx.lineTo(x+sw,by); ctx.stroke();
    const a=carAlpha(s.id, now);
    if(a>0){ ctx.globalAlpha=a; drawCar(cx,cy,upper?-Math.PI/2:Math.PI/2,hashColor(s.id),cl,cw); ctx.globalAlpha=1; }
    else if(s.type==="ev_charging"){ ctx.strokeStyle=C.ev;ctx.lineWidth=2;rr(x+1,y+1,sw-2,sh-2,2);ctx.stroke(); bolt(cx,cy,Math.min(sw,sh)*0.32); }
    else if(s.type==="disabled"){ ctx.strokeStyle=C.disabled;ctx.lineWidth=2;rr(x+1,y+1,sw-2,sh-2,2);ctx.stroke(); wheelchair(cx,cy,Math.min(sw,sh)*0.3); }
    // Rezerve (dolu değil): turuncu kesikli çerçeve + R
    if(reservedMap[s.id] && !vocc[s.id]){
      ctx.setLineDash([4,3]); ctx.strokeStyle=C.exit; ctx.lineWidth=2;
      rr(x-1,y-1,sw+2,sh+2,3); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle=C.exit; ctx.font=`700 ${Math.max(sh*0.5,8)}px sans-serif`; ctx.textAlign="center";
      ctx.fillText("R", cx, cy+sh*0.18);
    }
    // Anomali (arızalı/çevrimdışı sensör): kırmızı uyarı halkası
    if(anomalySpots[s.id]){ ctx.strokeStyle="rgba(239,138,142,0.95)"; ctx.lineWidth=2;
      ctx.beginPath(); ctx.arc(cx,cy,Math.max(sw,sh)*0.62,0,7); ctx.stroke(); }
    if(routes.some(r=>r.spotId===s.id)){ ctx.strokeStyle=`rgba(245,200,70,${0.5+0.5*pulse})`;ctx.lineWidth=3;rr(x-4,y-4,sw+8,sh+8,5);ctx.stroke(); }
  }
}

// Isı haritası rengi — çok-duraklı geçiş: az(soğuk mavi) -> çok(sıcak kırmızı)
const HEAT_STOPS=[[46,58,82],[42,118,176],[70,190,140],[245,200,70],[226,96,80]];
function heatColor(v){
  const t = Math.min(1, heatMax ? v/heatMax : 0);
  const f = t*(HEAT_STOPS.length-1), i = Math.min(HEAT_STOPS.length-2, Math.floor(f)), k = f-i;
  const a=HEAT_STOPS[i], b=HEAT_STOPS[i+1], ch=j=>Math.round(a[j]+(b[j]-a[j])*k);
  return `rgb(${ch(0)},${ch(1)},${ch(2)})`;
}
function drawGates(){
  ctx.textAlign="center"; ctx.font=`700 ${Math.max(T.scale*0.6,11)}px "Segoe UI",sans-serif`;
  const dmap={up:-Math.PI/2,down:Math.PI/2,left:Math.PI,right:0};
  for(const e of L.entrances){ const [x,y]=S(e.x,e.y);
    ctx.fillStyle=C.entrance; rr(x-T.scale*1.5,y-T.scale*0.85,T.scale*3,T.scale*1.7,6); ctx.fill();
    arrow(x,y,dmap[e.dir]||0,T.scale*0.5,"#15211a");
    ctx.fillStyle="#dff7e6"; ctx.fillText("GİRİŞ", x, y - T.scale*1.1); }
  for(const e of L.vexits){ const [x,y]=S(e.x,e.y);
    ctx.fillStyle=C.exit; rr(x-T.scale*1.5,y-T.scale*0.85,T.scale*3,T.scale*1.7,6); ctx.fill();
    arrow(x,y,dmap[e.dir]||0,T.scale*0.5,"#231405");
    ctx.fillStyle="#fbeede"; ctx.fillText("ÇIKIŞ", x, y - T.scale*1.1); }
}
function drawRoute(){
  for(const r of routes){
    const pts=r.pts.map(p=>S(p[0],p[1]));
    const col=(r.car&&r.car.color)||C.suggested;
    ctx.strokeStyle=col; ctx.globalAlpha=0.85; ctx.lineWidth=3; ctx.lineJoin="round"; ctx.lineCap="round";
    ctx.beginPath(); pts.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1])); ctx.stroke();
    ctx.globalAlpha=1;
  }
}

// Trafik modeli (yalnızca yumuşak araç-takibi):
//  - Aynı yöndeki öndeki araç = LİDER -> mesafeye göre yumuşakça yavaşla (asla 0'a
//    inmez; bir konvoyun en önündeki aracın lideri yoktur -> daima ilerler -> konvoy akar).
//  Not: Eski "kavşakta sert dur (f=0)" kuralı zincirleme KİLİTLENMEYE yol açıyordu;
//  kaldırıldı. Kavşakta hafif görsel örtüşme kabul edilebilir; donma riski yok.
function applyTraffic(list){
  const LOOK=1.7, LANE=0.55, MIN=0.85, SAFE=1.7;
  for(const A of list){
    let f=1;
    const ca=Math.cos(A.ang), sa=Math.sin(A.ang);
    for(const B of list){ if(B===A) continue;
      const dx=B.px-A.px, dy=B.py-A.py;
      const fwd=dx*ca+dy*sa, lat=-dx*sa+dy*ca;
      if(fwd<=0.02 || fwd>LOOK || Math.abs(lat)>LANE) continue;   // önümde ve şeridimde değil
      const sameDir=(ca*Math.cos(B.ang)+sa*Math.sin(B.ang)) > 0.4;
      if(sameDir) f=Math.min(f, Math.max(0.15,(fwd-MIN)/(SAFE-MIN)));  // lideri yumuşakça takip et (min 0.15)
    }
    A.speedFactor=f;
  }
}

function frame(now){
  const dt=Math.min((now-last)/1000,0.05); last=now;
  if(!L||!T){ requestAnimationFrame(frame); return; }
  const tl=Math.max(T.scale*0.95,8), tw=Math.max(T.scale*0.42,5);   // 0.70x küçültülmüş
  const heroCars = routes.map(r=>r.car).filter(Boolean);
  const moving = heroCars.length ? cars.concat(heroCars) : cars;
  applyTraffic(moving);                       // hız faktörlerini hesapla (takip + öncelik)
  for(const c of cars) c.update(dt);
  for(const c of heroCars) c.update(dt);
  if(cars.length) cars = cars.filter(c=>!c.done);

  ctx.fillStyle=C.bg; ctx.fillRect(0,0,canvas.width,canvas.height);
  // lot zemini (yollar bölgesi)
  const m=L.mall, [lx,ly]=S(L.bounds.min_x, m.y1-0.5), [lx2,ly2]=S(L.bounds.max_x, L.bounds.max_y);
  ctx.fillStyle=C.lot; rr(lx,ly,lx2-lx,ly2-ly,14); ctx.fill();

  drawRoads();
  drawSections();
  drawIslands();
  drawSpots(now);
  drawSectionLabels();           // bölüm harfleri spotların üstüne (sol boşlukta)
  for(const c of cars) c.draw(tl,tw);
  drawRoute();
  drawGates();
  drawMall();
  for(const c of heroCars) c.draw(tl,tw);
  requestAnimationFrame(frame);
}

/* ---------- veri & UI ---------- */
async function loadLayout(){
  L = await (await fetch("/api/layout")).json();
  aisleIds = Object.keys(L.road_nodes).filter(n=>n.startsWith("AISLE"));
  entranceIds = L.entrances.map(e=>e.id);
  vexitIds = L.vexits.map(e=>e.id);
  spotById = Object.fromEntries(L.spots.map(s=>[s.id, s]));
  resize();
  buildLegend(); buildEntranceSel();
}
function applyState(d, animate){
  stTotal.textContent=d.counts.total; stOcc.textContent=d.counts.occupied; stEmp.textContent=d.counts.empty;
  if(d.sim && clockEl){ const h=Math.floor(d.sim.hour), m=Math.floor((d.sim.hour-h)*60);
    clockEl.textContent=`${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}  ·  Yoğunluk: ${d.sim.busy}`; }
  reservedMap = d.reserved || {};
  updateSysRow(d);
  if(!animate || prevOcc===null){ vocc={...d.occupancy}; prevOcc=d.occupancy; return; }  // baz kare: animasyonsuz
  for(const id in d.occupancy){
    const now=d.occupancy[id], was=prevOcc[id];
    if(now && !was) spawnArrival(id);        // yeni doldu -> araç gelir
    else if(!now && was) spawnDeparture(id); // boşaldı -> araç gider
  }
  prevOcc=d.occupancy;
}
// Açılışta anlık durumu bir kez çek -> sayılar/doluluk hemen boyanır (ilk WS'i bekleme)
async function primeState(){
  try{ applyState(await (await fetch("/api/state")).json(), false); }catch(e){}
}
function connectWS(){
  const proto=location.protocol==="https:"?"wss":"ws";
  const ws=new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage=(ev)=>applyState(JSON.parse(ev.data), true);
  // Bağlantı koparsa baz kareyi sıfırla: yeniden bağlanınca tüm doluluk farkı BİRDEN
  // spawn olmasın (aksi halde onlarca araç aynı anda belirir). İlk mesaj animasyonsuz baz olur.
  ws.onclose=()=>{ prevOcc=null; setTimeout(connectWS,1500); };
}
function buildLegend(){
  const items=[[C.slot,"Boş"],[CARS[0],"Dolu"],[C.ev,"Şarjlı"],[C.disabled,"Engelli"],[C.exit,"Rezerve"],[C.suggested,"Önerilen"],[C.yourCar,"Sizin aracınız"]];
  document.getElementById("legend").innerHTML=items.map(([c,t])=>`<span class="item"><span class="sw" style="background:${c}"></span>${t}</span>`).join("");
}
function buildEntranceSel(){
  const labels=["Alt sol","Alt sağ","Yan"];
  const seg=document.getElementById("seg"); seg.innerHTML="";
  L.entrances.forEach((e,i)=>{ const b=document.createElement("button");
    b.textContent=labels[i]||("G"+(i+1));
    b.onclick=()=>{ entranceId=e.id; [...seg.children].forEach(c=>c.classList.remove("active")); b.classList.add("active"); };
    if(i===0){ b.classList.add("active"); entranceId=e.id; } seg.appendChild(b); });
}

const chatEl=document.getElementById("chat");
const stTotal=document.getElementById("stat-total"), stOcc=document.getElementById("stat-occ"), stEmp=document.getElementById("stat-emp");
const clockEl=document.getElementById("clock");
function bubble(role,text,meta){ const d=document.createElement("div"); d.className=`bubble ${role}`; d.textContent=text;
  if(meta){const m=document.createElement("span");m.className="meta";m.textContent=meta;d.appendChild(m);}
  chatEl.appendChild(d); chatEl.scrollTop=chatEl.scrollHeight; return d; }
bubble("info","Merhaba! Nasıl bir park yeri istediğinizi yazın.");
bubble("info",'Örn: "Elektrikli arabam var, çıkışa yakın bir yer istiyorum"');

const form=document.getElementById("composer"), input=document.getElementById("msg"), sendBtn=document.getElementById("send");
const multiBtn=document.getElementById("multi");
if(multiBtn) multiBtn.addEventListener("click", requestMulti);
form.addEventListener("submit", async (e)=>{
  e.preventDefault(); const text=input.value.trim(); if(!text)return;
  input.value=""; sendBtn.disabled=true; input.disabled=true;
  const eg=L.entrances.find(x=>x.id===entranceId), idx=L.entrances.indexOf(eg);
  bubble("user", `${text}  (${["Alt sol","Alt sağ","Yan"][idx]||"giriş"})`);
  const think=bubble("system thinking","Düşünüyor...");
  try{
    const r=await fetch("/api/request",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text,entrance:entranceId})});
    const data=await r.json(); think.remove();
    bubble("system", data.reply, `kaynak: ${data.source}`);
    if(data.result&&data.result.path_points){
      routes=[{pts:data.result.path_points, spotId:data.result.spot_id, car:new Hero(data.result.path_points)}];
      addReserveButton(data.result.spot_id);     // "Yeri ayırt" seçeneği
    }
    else { routes=[]; }
  }catch(err){ think.remove(); bubble("system","Bağlantı hatası: "+err.message); }
  finally{ sendBtn.disabled=false; input.disabled=false; input.focus(); }
});

/* ---------- Rezervasyon ---------- */
function addReserveButton(spotId){
  const b=document.createElement("button");
  b.className="reserve-btn"; b.textContent=`🅿 ${spotId} yerini ayırt`;
  b.onclick=async ()=>{
    b.disabled=true;
    try{
      const r=await fetch("/api/reserve",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({spot_id:spotId})});
      const d=await r.json();
      if(d.ok){ b.textContent=`✓ ${spotId} ayrıldı (${d.timeout_sec|0}sn)`;
        bubble("info",`${spotId} sizin için rezerve edildi. ${d.timeout_sec|0} sn içinde gelmezseniz serbest bırakılır.`); }
      else { b.disabled=false; bubble("info","Ayrılamadı: "+d.reason); }
    }catch(e){ b.disabled=false; bubble("system","Rezervasyon hatası: "+e.message); }
  };
  chatEl.appendChild(b); chatEl.scrollTop=chatEl.scrollHeight;
}

/* ---------- IoT sistem durumu (ağ geçidi + sensör filosu + anomali) ---------- */
const gatewayEl=document.getElementById("gateway"), sensorsEl=document.getElementById("sensors");
const edgeEl=document.getElementById("edge");
const anomalyBadge=document.getElementById("anomaly-badge"), anomalyCount=document.getElementById("anomaly-count");
const anomalyListEl=document.getElementById("anomaly-list");
function updateSysRow(d){
  if(d.gateway){ gatewayEl.classList.toggle("online", d.gateway.online); gatewayEl.classList.toggle("offline", !d.gateway.online);
    gatewayEl.lastChild.textContent = d.gateway.online ? " Ağ geçidi ✓" : " Ağ geçidi ✕"; }
  if(d.sensors){ sensorsEl.textContent = `📡 ${d.sensors.online}/${d.sensors.total} · %${d.sensors.avg_battery}`; }
  if(d.edge && edgeEl){ edgeEl.textContent = `🛡 Edge: ${d.edge.filtered} gürültü`; }
  if(d.anomalies){ const t=d.anomalies.error+d.anomalies.warning;
    anomalyBadge.hidden = t===0; anomalyCount.textContent = t; }
}

/* ---------- Tahmin (öngörücü zekâ) ---------- */
const predictBtn=document.getElementById("predict-btn");
if(predictBtn) predictBtn.onclick=async ()=>{
  predictBtn.disabled=true;
  try{
    const p=await (await fetch("/api/predict?horizon_min=15")).json();
    const arrow = p.trend==="rising" ? "📈" : (p.trend==="falling" ? "📉" : "➖");
    bubble("system", `${arrow} ${p.advice}`,
      `şimdi %${Math.round(p.now_ratio*100)} → ~%${Math.round(p.predicted_ratio*100)} (15 dk)`);
  }catch(e){ bubble("system","Tahmin alınamadı: "+e.message); }
  finally{ predictBtn.disabled=false; }
};
anomalyBadge.onclick=async ()=>{
  if(!anomalyListEl.hidden){ anomalyListEl.hidden=true; anomalySpots={}; return; }
  try{
    const d=await (await fetch("/api/anomalies")).json();
    anomalySpots={}; d.items.forEach(a=>anomalySpots[a.spot_id]=true);
    anomalyListEl.innerHTML = d.items.length
      ? d.items.map(a=>`<div class="a-item" data-spot="${a.spot_id}"><span class="a-tag ${a.severity}">${a.severity==="error"?"HATA":"UYARI"}</span>${a.message}</div>`).join("")
      : '<div class="a-item">Şu an anomali yok ✓</div>';
    anomalyListEl.hidden=false;
  }catch(e){ bubble("system","Anomali alınamadı: "+e.message); }
};

/* ---------- Analitik paneli ---------- */
const overlay=document.getElementById("analytics");
document.getElementById("analytics-btn").onclick=openAnalytics;
document.getElementById("analytics-close").onclick=()=>overlay.hidden=true;
async function openAnalytics(){
  overlay.hidden=false;
  try{
    const a=await (await fetch("/api/analytics")).json();
    const ts=a.timeseries||[];
    const last=ts.length?ts[ts.length-1]:{occupied:0,total:240};
    const total=last.total||240;
    const nowPct=total?Math.round(last.occupied/total*100):0;
    const peakPct=ts.length?Math.round(Math.max(...ts.map(p=>p.occupied))/total*100):0;
    const busiest=(a.sections||[]).slice().sort((x,y)=>y.rate-x.rate)[0];
    const moves=Object.values(a.heatmap||{}).reduce((s,v)=>s+v,0);
    const M=[
      ["🚗", nowPct+"%", "Şu anki doluluk", "#6cb8ee"],
      ["⏱️", a.avg_stay_minutes+" dk", "Ort. kalış (simüle)", "#62c8a8"],
      ["📈", peakPct+"%", "Zirve doluluk", "#f5c846"],
      ["🔥", busiest?(busiest.section+" · %"+Math.round(busiest.rate*100)):"—", "En yoğun bölge", "#e2685a"],
      ["🅿️", moves.toLocaleString("tr-TR"), "Toplam park hareketi", "#9a8cf0"],
    ];
    document.getElementById("analytics-metrics").innerHTML = M.map(([ic,v,l,col])=>
      `<div class="metric" style="border-left-color:${col}"><span class="mv"><span class="mi">${ic}</span>${v}</span><span class="ml">${l}</span></div>`).join("");
    drawTimeChart(ts);
    drawSectionChart(a.sections);
  }catch(e){ document.getElementById("analytics-metrics").innerHTML = "Analitik alınamadı: "+e.message; }
}
function _fit(cv, cssH){ const r=cv.getBoundingClientRect(), dpr=window.devicePixelRatio||1;
  cv.width=Math.max(1,r.width)*dpr; cv.height=cssH*dpr; cv.style.height=cssH+"px";
  const c=cv.getContext("2d"); c.setTransform(dpr,0,0,dpr,0,0); return [c, r.width||cv.width/dpr, cssH]; }
function _grid(c, x0, x1, y0, y1){          // %0–100 yatay ızgara + sol eksen etiketleri
  c.font="10px 'Segoe UI',sans-serif"; c.textAlign="right"; c.textBaseline="middle";
  for(let g=0; g<=4; g++){
    const yy=y1-(y1-y0)*(g/4);
    c.strokeStyle="rgba(255,255,255,0.06)"; c.lineWidth=1;
    c.beginPath(); c.moveTo(x0,yy); c.lineTo(x1,yy); c.stroke();
    c.fillStyle="rgba(170,178,196,0.7)"; c.fillText((g*25)+"%", x0-6, yy);
  }
}
function drawTimeChart(ts){
  const cv=document.getElementById("chart-time"); const [c,W,H]=_fit(cv,160);
  c.clearRect(0,0,W,H);
  const x0=36, x1=W-12, y0=14, y1=H-18;
  _grid(c, x0, x1, y0, y1);
  if(!ts.length) return;
  const total=ts[0].total||1, n=ts.length;
  const px=i=>x0+(x1-x0)*i/Math.max(1,n-1);
  const py=v=>y1-(y1-y0)*Math.min(1, v/total);
  // gradyan alan dolgusu
  const grad=c.createLinearGradient(0,y0,0,y1);
  grad.addColorStop(0,"rgba(108,184,238,0.42)"); grad.addColorStop(1,"rgba(108,184,238,0.02)");
  c.beginPath(); c.moveTo(px(0),y1);
  ts.forEach((p,i)=>c.lineTo(px(i),py(p.occupied)));
  c.lineTo(px(n-1),y1); c.closePath(); c.fillStyle=grad; c.fill();
  // çizgi
  c.beginPath(); ts.forEach((p,i)=>{ const X=px(i),Y=py(p.occupied); i?c.lineTo(X,Y):c.moveTo(X,Y); });
  c.strokeStyle="#6cb8ee"; c.lineWidth=2; c.lineJoin="round"; c.stroke();
  // son nokta + değer balonu
  const last=ts[n-1], lx=px(n-1), ly=py(last.occupied);
  c.fillStyle="#6cb8ee"; c.beginPath(); c.arc(lx,ly,3.5,0,7); c.fill();
  c.fillStyle="#e6eaf2"; c.font="700 11px 'Segoe UI',sans-serif"; c.textAlign="right"; c.textBaseline="bottom";
  c.fillText(Math.round(last.occupied/total*100)+"% ("+last.occupied+")", lx-3, ly-5);
  // x ekseni: eski -> şimdi
  c.fillStyle="rgba(170,178,196,0.6)"; c.font="10px 'Segoe UI',sans-serif"; c.textBaseline="top";
  c.textAlign="left"; c.fillText("← eski", x0, y1+4);
  c.textAlign="right"; c.fillText("şimdi", x1, y1+4);
}
function levelColor(rate){ return rate>=0.7 ? "#e2685a" : (rate>=0.4 ? "#f5c846" : "#6cd08a"); }
function drawSectionChart(secs){
  const cv=document.getElementById("chart-sections"); const [c,W,H]=_fit(cv,160);
  c.clearRect(0,0,W,H); if(!secs||!secs.length) return;
  const x0=36, x1=W-12, y0=16, y1=H-28;
  _grid(c, x0, x1, y0, y1);
  const gap=(x1-x0)/secs.length, bw=gap*0.5;
  secs.forEach((s,i)=>{
    const bx=x0+gap*i+(gap-bw)/2, h=(y1-y0)*s.rate, by=y1-h;
    c.fillStyle=levelColor(s.rate); rrc(c,bx,by,bw,Math.max(h,2),3); c.fill();
    c.fillStyle="#e6eaf2"; c.font="700 11px 'Segoe UI',sans-serif"; c.textAlign="center"; c.textBaseline="bottom";
    c.fillText(Math.round(s.rate*100)+"%", bx+bw/2, by-3);
    c.fillStyle="rgba(214,222,236,0.9)"; c.font="700 12px 'Segoe UI',sans-serif"; c.textBaseline="top";
    c.fillText(s.section, bx+bw/2, y1+5);
    c.fillStyle="rgba(170,178,196,0.7)"; c.font="10px 'Segoe UI',sans-serif";
    c.fillText(s.occupied+"/"+s.total, bx+bw/2, y1+19);
  });
}
function rrc(c,x,y,w,h,r){ r=Math.min(r,w/2,h/2); c.beginPath();
  c.moveTo(x+r,y); c.arcTo(x+w,y,x+w,y+h,r); c.arcTo(x+w,y+h,x,y+h,r);
  c.arcTo(x,y+h,x,y,r); c.arcTo(x,y,x+w,y,r); c.closePath(); }

/* ---------- Isı haritası ---------- */
const heatBtn=document.getElementById("heatmap-btn");
const heatLegend=document.getElementById("heat-legend"), heatMaxEl=document.getElementById("hl-max");
heatBtn.onclick=async ()=>{
  heatmapOn=!heatmapOn; heatBtn.classList.toggle("on", heatmapOn);
  if(heatmapOn){
    try{ const a=await (await fetch("/api/analytics")).json();
      heatData=a.heatmap||{}; heatMax=Math.max(1, ...Object.values(heatData));
      if(heatMaxEl) heatMaxEl.textContent=`çok (${heatMax}×)`;
      if(heatLegend) heatLegend.hidden=false;
    }
    catch(e){ heatmapOn=false; heatBtn.classList.remove("on"); }
  } else if(heatLegend){ heatLegend.hidden=true; }
};

/* ---------- Sesli giriş (Web Speech API) ---------- */
const micBtn=document.getElementById("mic");
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if(SR){
  const rec=new SR(); rec.lang="tr-TR"; rec.interimResults=false; rec.maxAlternatives=1;
  micBtn.onclick=()=>{ try{ rec.start(); micBtn.classList.add("rec"); }catch(e){} };
  rec.onresult=(e)=>{ input.value=e.results[0][0].transcript; };
  rec.onend=()=>{ micBtn.classList.remove("rec"); if(input.value.trim()) form.requestSubmit(); };
  rec.onerror=()=>micBtn.classList.remove("rec");
} else {
  micBtn.title="Tarayıcınız sesli girişi desteklemiyor"; micBtn.disabled=true;
}

/* ---------- Çoklu araç optimal atama (G2.4 / Hungarian) ---------- */
// Aynı anda gelen birden çok aracı sunucudaki allocate_multiple ile optimal atar;
// her araca ayrı renkte rota + animasyon. "İki araç asla aynı yere gitmez."
const MULTI_DEMO = [
  {label:"Normal", text:"normal araç",                         vehicle_type:"normal",   entrance:"ENTRANCE-0"},
  {label:"Elektrikli", text:"elektrikli, şarj lazım",          vehicle_type:"ev", needs_charging:true, entrance:"ENTRANCE-1"},
  {label:"Engelli", text:"engelli araç",                       vehicle_type:"disabled", entrance:"ENTRANCE-2"},
];
async function requestMulti(){
  multiBtn.disabled=true;
  bubble("user","🚗🚗🚗 Aynı anda 3 araç geldi (optimal atama)");
  const think=bubble("system thinking","Optimal atama hesaplanıyor...");
  try{
    const r=await fetch("/api/request_multi",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({requests:MULTI_DEMO})});
    const data=await r.json(); think.remove();
    routes=[];
    let lines=[];
    data.results.forEach((res,i)=>{
      const col=HERO_COLORS[i%HERO_COLORS.length];
      if(res && res.path_points){
        routes.push({pts:res.path_points, spotId:res.spot_id, car:new Hero(res.path_points, col)});
        lines.push(`${MULTI_DEMO[i].label} → ${res.spot_id} (${res.spot_type}, ${res.distance} br)`);
      } else {
        lines.push(`${MULTI_DEMO[i].label} → yer bulunamadı`);
      }
    });
    bubble("system", "Optimal atama (çakışmasız):\n"+lines.join("\n"),
           `kaynak: Hungarian · toplam ${data.total_distance} br`);
  }catch(err){ think.remove(); bubble("system","Bağlantı hatası: "+err.message); }
  finally{ multiBtn.disabled=false; }
}

(async function(){ await loadLayout(); await primeState(); connectWS(); requestAnimationFrame(frame); })();
