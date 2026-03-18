const canvas=document.getElementById('hud-canvas');
const ctx=canvas.getContext('2d');
function resize(){canvas.width=window.innerWidth;canvas.height=window.innerHeight;}
window.addEventListener('resize',resize);resize();
let faceData=null,angle=0,scanAngle=0;
async function fetchFace(){try{const r=await fetch('/face');faceData=await r.json();}catch(e){faceData=null;}}
setInterval(fetchFace,80);
function arc(cx,cy,r,s,e,w,col,sh){ctx.beginPath();ctx.arc(cx,cy,r,s,e);ctx.lineWidth=w;ctx.strokeStyle=col;ctx.shadowBlur=sh;ctx.shadowColor=col;ctx.stroke();ctx.shadowBlur=0;}
function ln(x1,y1,x2,y2,col,w,a){ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.strokeStyle=col;ctx.lineWidth=w;ctx.globalAlpha=a||1;ctx.stroke();ctx.globalAlpha=1;}
function ticks(cx,cy,r,n,rot,len,col){for(let i=0;i<n;i++){const a=(i/n)*Math.PI*2+rot;ln(cx+Math.cos(a)*r,cy+Math.sin(a)*r,cx+Math.cos(a)*(r+len),cy+Math.sin(a)*(r+len),col,i%4===0?1.5:0.8,i%4===0?0.8:0.2);}}
function dot(cx,cy,r,col){ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.fillStyle=col;ctx.shadowBlur=12;ctx.shadowColor=col;ctx.fill();ctx.shadowBlur=0;}
function bracket(x,y,w,h,s,col){
  ctx.strokeStyle=col;ctx.lineWidth=2;ctx.shadowBlur=10;ctx.shadowColor=col;
  ctx.beginPath();ctx.moveTo(x,y+s);ctx.lineTo(x,y);ctx.lineTo(x+s,y);ctx.stroke();
  ctx.beginPath();ctx.moveTo(x+w-s,y);ctx.lineTo(x+w,y);ctx.lineTo(x+w,y+s);ctx.stroke();
  ctx.beginPath();ctx.moveTo(x,y+h-s);ctx.lineTo(x,y+h);ctx.lineTo(x+s,y+h);ctx.stroke();
  ctx.beginPath();ctx.moveTo(x+w-s,y+h);ctx.lineTo(x+w,y+h);ctx.lineTo(x+w,y+h-s);ctx.stroke();
  ctx.shadowBlur=0;
}
function dataTag(x,y,label,val,dir){
  const C='#00d4ff',dx=dir==='r'?1:-1,len=55;
  ctx.strokeStyle=C;ctx.lineWidth=1;ctx.globalAlpha=0.6;
  ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x+dx*len,y);ctx.lineTo(x+dx*(len+18),y-14);ctx.stroke();
  ctx.globalAlpha=1;dot(x+dx*len,y,2,C);
  ctx.font="8px 'Share Tech Mono'";ctx.fillStyle='rgba(0,212,255,0.4)';
  const lw=ctx.measureText(label).width;
  ctx.fillText(label,x+dx*(len+22)-(dir==='l'?lw:0),y-16);
  ctx.font="bold 10px 'Rajdhani'";ctx.fillStyle='rgba(255,255,255,0.75)';
  const vw=ctx.measureText(val).width;
  ctx.fillText(val,x+dx*(len+22)-(dir==='l'?vw:0),y-4);
}
function drawAmbient(){
  const cx=canvas.width/2,cy=canvas.height/2;
  arc(cx,cy,160,angle*0.3,angle*0.3+0.8,1,'rgba(0,212,255,0.12)',0);
  arc(cx,cy,160,angle*0.3+Math.PI,angle*0.3+Math.PI+0.8,1,'rgba(0,212,255,0.12)',0);
  ln(cx-22,cy,cx+22,cy,'rgba(0,212,255,0.08)',1);ln(cx,cy-22,cx,cy+22,'rgba(0,212,255,0.08)',1);
  ctx.font="9px 'Share Tech Mono'";ctx.fillStyle='rgba(0,212,255,0.2)';ctx.textAlign='center';
  ctx.fillText('SCANNING FOR TARGET...',cx,cy+220);ctx.textAlign='left';
}
function drawFaceHUD(fd){
  const cx=fd.x+fd.w/2,cy=fd.y+fd.h/2,C='#00d4ff',Y='#ffcc00';
  ctx.beginPath();ctx.arc(cx,cy,230,scanAngle,scanAngle+0.5);ctx.lineWidth=18;ctx.strokeStyle='rgba(0,212,255,0.06)';ctx.stroke();
  ctx.beginPath();ctx.arc(cx,cy,230,scanAngle,scanAngle+0.13);ctx.lineWidth=18;ctx.strokeStyle='rgba(0,212,255,0.28)';ctx.shadowBlur=16;ctx.shadowColor=C;ctx.stroke();ctx.shadowBlur=0;
  arc(cx,cy,250,angle,angle+1.2,1.5,'rgba(0,212,255,0.5)',5);
  arc(cx,cy,250,angle+2.1,angle+3.0,1.5,'rgba(0,212,255,0.3)',3);
  ticks(cx,cy,210,64,-angle,7,'rgba(0,212,255,0.3)');
  ticks(cx,cy,195,12,angle*0.5,14,C);
  arc(cx,cy,172,-angle,Math.PI*1.5-angle,1.5,'rgba(0,212,255,0.4)',5);
  arc(cx,cy,155,angle,angle+2.3,1.5,'rgba(0,180,255,0.3)',3);
  bracket(fd.x-8,fd.y-8,fd.w+16,fd.h+16,24,Y);
  ln(cx-75,cy,cx-12,cy,C,1,0.55);ln(cx+12,cy,cx+75,cy,C,1,0.55);
  ln(cx,cy-75,cx,cy-12,C,1,0.55);ln(cx,cy+12,cx,cy+75,C,1,0.55);
  [[1,1],[1,-1],[-1,1],[-1,-1]].forEach(([dx,dy])=>{ln(cx+dx*12,cy+dy*12,cx+dx*22,cy+dy*22,C,1,0.35);});
  dot(cx,cy,4,C);
  dataTag(cx+fd.w/2+12,cy-28,'IDENTITY','UNVERIFIED','r');
  dataTag(cx+fd.w/2+12,cy+18,'THREAT','NONE','r');
  dataTag(cx-fd.w/2-12,cy-28,'DIST','~1.2m','l');
  dataTag(cx-fd.w/2-12,cy+18,'CONF','94.7%','l');
  const fs=document.getElementById('face-status');if(fs)fs.textContent='LOCKED — TRACKING';
  const id=document.getElementById('identity');if(id){id.textContent='OWNER DETECTED';id.className='bbv green';}
}
const parts=Array.from({length:22},()=>({x:Math.random()*window.innerWidth,y:Math.random()*window.innerHeight,r:Math.random()*1.2+0.2,vx:(Math.random()-0.5)*0.2,vy:(Math.random()-0.5)*0.2,a:Math.random()*0.2+0.04}));
function drawParts(){parts.forEach(p=>{p.x+=p.vx;p.y+=p.vy;if(p.x<0)p.x=canvas.width;if(p.x>canvas.width)p.x=0;if(p.y<0)p.y=canvas.height;if(p.y>canvas.height)p.y=0;ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fillStyle=`rgba(0,212,255,${p.a})`;ctx.fill();});}
function draw(){ctx.clearRect(0,0,canvas.width,canvas.height);drawParts();if(faceData&&faceData.face)drawFaceHUD(faceData);else drawAmbient();angle+=0.011;scanAngle+=0.022;requestAnimationFrame(draw);}
draw();