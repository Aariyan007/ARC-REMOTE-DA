// J.A.R.V.I.S APP.JS

// ── CLOCK ──
function updateClock(){
  const n=new Date(),pad=v=>String(v).padStart(2,'0');
  const days=['SUN','MON','TUE','WED','THU','FRI','SAT'];
  const mons=['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
  document.getElementById('clock').textContent=`${pad(n.getHours())}:${pad(n.getMinutes())}:${pad(n.getSeconds())}`;
  document.getElementById('datedisp').textContent=`${days[n.getDay()]} ${pad(n.getDate())} ${mons[n.getMonth()]} ${n.getFullYear()}`;
  const h=n.getHours();
  const tod=h<6?'NIGHT':h<12?'MORNING':h<17?'AFTERNOON':h<21?'EVENING':'NIGHT';
  const te=document.getElementById('e-tod');if(te)te.textContent=tod;
}
setInterval(updateClock,1000);updateClock();

// ── UPTIME ──
const T0=Date.now();
function updateUptime(){
  const s=Math.floor((Date.now()-T0)/1000);
  const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60;
  const pad=v=>String(v).padStart(2,'0');
  const str=`${pad(h)}:${pad(m)}:${pad(sec)}`;
  const u=document.getElementById('uptime');if(u)u.textContent=str;
  const st=document.getElementById('session-t');if(st)st.textContent=str;
  const as=document.getElementById('a-sess');if(as)as.textContent=str;
}
setInterval(updateUptime,1000);

// ── SENSORS ──
async function getSensors(){
  try{
    const r=await fetch('/sensor-data');const d=await r.json();
    if(d.heart>0){document.getElementById('heart').textContent=d.heart;}
    if(d.temp>0){document.getElementById('temp').textContent=d.temp;}
  }catch(e){}
}
setInterval(getSensors,1000);

// ── SYSTEM STATS ──
function updateStats(){
  const s={cpu:40+Math.random()*40,mem:35+Math.random()*20,net:60+Math.random()*30,gpu:20+Math.random()*40,tmp:52+Math.random()*12,bat:85+Math.random()*4};
  Object.entries(s).forEach(([k,v])=>{
    const b=document.getElementById(k+'-b'),t=document.getElementById(k+'-v');
    if(b)b.style.width=v.toFixed(0)+'%';
    if(t)t.textContent=k==='tmp'?v.toFixed(0)+'°C':v.toFixed(0)+'%';
    if(b&&k!=='tmp'&&k!=='bat'){b.style.background=v>80?'linear-gradient(90deg,#cc0000,#ff3c3c)':v>65?'linear-gradient(90deg,#aa6600,#ffaa00)':'linear-gradient(90deg,#0088cc,#00d4ff)';}
  });
}
setInterval(updateStats,1800);updateStats();

// ── VOICE WAVEFORM ──
const vwc=document.getElementById('voicewave'),vwx=vwc?vwc.getContext('2d'):null;
let vwp=0;
function drawVoice(){
  if(!vwx)return;
  const W=vwc.width,H=vwc.height;
  vwx.clearRect(0,0,W,H);
  vwx.beginPath();
  for(let i=0;i<W;i++){
    const t=i/W*Math.PI*6+vwp;
    const y=H/2+Math.sin(t)*9+Math.sin(t*2.4)*4+Math.sin(t*0.5)*2;
    i===0?vwx.moveTo(i,y):vwx.lineTo(i,y);
  }
  vwx.strokeStyle='#00d4ff';vwx.lineWidth=1.5;vwx.shadowBlur=6;vwx.shadowColor='#00d4ff';vwx.stroke();vwx.shadowBlur=0;
  vwx.beginPath();vwx.moveTo(0,H/2);vwx.lineTo(W,H/2);vwx.strokeStyle='rgba(0,212,255,0.1)';vwx.lineWidth=0.5;vwx.stroke();
  vwp+=0.05;requestAnimationFrame(drawVoice);
}
drawVoice();

let vm=90+Math.random()*7;
setInterval(()=>{
  vm+=(Math.random()-0.5)*2;vm=Math.max(82,Math.min(99,vm));
  const e=document.getElementById('v-match');if(e)e.textContent=vm.toFixed(1)+'%';
  const n=new Date(),pad=v=>String(v).padStart(2,'0');
  const e2=document.getElementById('v-last');
  if(e2)e2.textContent=`${pad(n.getHours())}:${pad(n.getMinutes())}:${pad(n.getSeconds())}`;
},3000);

// ── ECG ──
const ecgC=document.getElementById('ecg'),ecgX=ecgC?ecgC.getContext('2d'):null;
let ecgP=0;
function drawECG(){
  if(!ecgX)return;
  ecgX.clearRect(0,0,110,28);
  ecgX.beginPath();ecgX.strokeStyle='#00ff88';ecgX.lineWidth=1.2;ecgX.shadowBlur=4;ecgX.shadowColor='#00ff88';
  for(let x=0;x<110;x++){
    const t=(x/110)*Math.PI*4+ecgP;
    const mod=t%(Math.PI*2);
    let y=14;
    if(mod>2.5&&mod<2.65)y=1;
    else if(mod>2.65&&mod<2.8)y=27;
    else if(mod>2.8&&mod<2.95)y=9;
    else y=14+Math.sin(t*0.5)*2;
    x===0?ecgX.moveTo(x,y):ecgX.lineTo(x,y);
  }
  ecgX.stroke();ecgX.shadowBlur=0;
  ecgP+=0.09;requestAnimationFrame(drawECG);
}
drawECG();

// ── SLEEP RING ──
const slC=document.getElementById('sleep-ring'),slX=slC?slC.getContext('2d'):null;
function drawSleepRing(){
  if(!slX)return;
  slX.clearRect(0,0,70,70);
  slX.beginPath();slX.arc(35,35,28,0,Math.PI*2);slX.strokeStyle='rgba(0,212,255,0.1)';slX.lineWidth=5;slX.stroke();
  slX.beginPath();slX.arc(35,35,28,-Math.PI/2,-Math.PI/2+Math.PI*2*0.84);slX.strokeStyle='#00d4ff';slX.lineWidth=5;slX.shadowBlur=8;slX.shadowColor='#00d4ff';slX.lineCap='round';slX.stroke();slX.shadowBlur=0;
  slX.beginPath();slX.arc(35,35,19,-Math.PI/2,-Math.PI/2+Math.PI*2*0.28);slX.strokeStyle='#00ff88';slX.lineWidth=3;slX.stroke();
}
drawSleepRing();

// ── FOCUS TIMER ──
const fStart=Date.now();
function updateFocus(){
  const s=Math.floor((Date.now()-fStart)/1000);
  const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60;
  const pad=v=>String(v).padStart(2,'0');
  const e=document.getElementById('focus-timer');if(e)e.textContent=`${pad(h)}:${pad(m)}:${pad(sec)}`;
  const mins=Math.floor(s/60),pomRem=25-(mins%25);
  const w=document.getElementById('focus-warn');
  if(w)w.textContent=pomRem<=5?`⚠ BREAK NOW!`:`NEXT BREAK IN ${pomRem} MIN`;
}
setInterval(updateFocus,1000);

// ── CMD LOG ──
const logEl=document.getElementById('cmd-log');
const logMsgs=[
  ['le-info','[AI] Listening for wake word...'],['le-ok','[CMD] Voice received'],
  ['le-ok','[AUTH] Owner voice verified'],['le-sys','[SYS] Memory nominal'],
  ['le-warn','[ESP] Sensor heartbeat delayed'],['le-ok','[ESP] Sensor reconnected'],
  ['le-info','[AI] Gemini standby — no fallback'],['le-ok','[CMD] Intent: open_safari → executed'],
  ['le-sys','[SYS] CPU throttle OFF'],['le-info','[CAM] Face tracking active'],
  ['le-ok','[CMD] tell_time → executed'],['le-warn','[NET] Gemini latency spike 340ms'],
  ['le-ok','[CMD] search_google → executed'],['le-sys','[SYS] All diagnostics green'],
];
let logIdx=0,cmdTotal=0;
function addLog(){
  if(!logEl)return;
  const[cls,msg]=logMsgs[logIdx%logMsgs.length];logIdx++;cmdTotal++;
  const n=new Date(),pad=v=>String(v).padStart(2,'0');
  const ts=`${pad(n.getHours())}:${pad(n.getMinutes())}:${pad(n.getSeconds())}`;
  const d=document.createElement('div');d.className=`le ${cls}`;d.textContent=`${ts} ${msg}`;
  logEl.appendChild(d);
  while(logEl.children.length>20)logEl.removeChild(logEl.firstChild);
  logEl.scrollTop=logEl.scrollHeight;
  const bc=document.getElementById('b-cmds');if(bc)bc.textContent=cmdTotal;
  const ac=document.getElementById('a-cmds');if(ac)ac.textContent=cmdTotal;
}
setInterval(addLog,3000+Math.random()*2000);

// ── CONVERSATION ──
const convos=[
  {y:'FRIEND open safari',j:'Opening Safari now.',c:'97.2%'},
  {y:'what time is it',j:`It's ${new Date().toLocaleTimeString()}.`,c:'99.1%'},
  {y:'search python loops',j:'Searching Google...',c:'95.8%'},
  {y:'FRIEND lock screen',j:'Locking your screen.',c:'98.3%'},
];
let cvIdx=0;
function updateConvo(){
  const c=convos[cvIdx%convos.length];cvIdx++;
  const cy=document.getElementById('cv-you'),cj=document.getElementById('cv-jar'),cc=document.getElementById('cv-conf');
  if(cy)cy.textContent=c.y;if(cj)cj.textContent=c.j;if(cc)cc.textContent=c.c;
}
setInterval(updateConvo,7000);

// ── HEALTH ──
let eyeMin=20;
setInterval(()=>{
  eyeMin--;if(eyeMin<=0)eyeMin=20;
  const e=document.getElementById('h-eye');
  if(e){e.textContent=eyeMin+'m';e.className=eyeMin<=5?'red':eyeMin<=10?'amber':'cyan';}
},60000);