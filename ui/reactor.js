const rc=document.getElementById('reactor-canvas');
const rcc=rc.getContext('2d');
const RX=65,RY=65;
let ra=0;
function drawReactor(){
  rcc.clearRect(0,0,130,130);
  const p=0.6+Math.sin(ra*2)*0.1;
  const g=rcc.createRadialGradient(RX,RY,8,RX,RY,58);
  g.addColorStop(0,`rgba(0,212,255,${p*0.22})`);g.addColorStop(0.5,`rgba(0,100,180,${p*0.08})`);g.addColorStop(1,'transparent');
  rcc.beginPath();rcc.arc(RX,RY,58,0,Math.PI*2);rcc.fillStyle=g;rcc.fill();
  rcc.beginPath();rcc.arc(RX,RY,55,0,Math.PI*2);rcc.strokeStyle=`rgba(0,212,255,${0.25+Math.sin(ra)*0.08})`;rcc.lineWidth=1;rcc.stroke();
  // Segments
  for(let i=0;i<6;i++){
    const a1=(i/6)*Math.PI*2+ra,a2=((i+0.68)/6)*Math.PI*2+ra;
    rcc.beginPath();rcc.moveTo(RX,RY);rcc.arc(RX,RY,46,a1,a2);rcc.closePath();
    rcc.fillStyle=`rgba(0,100,200,${0.13+(i%2)*0.09})`;rcc.strokeStyle='rgba(0,212,255,0.4)';rcc.lineWidth=0.5;rcc.fill();rcc.stroke();
  }
  for(let i=0;i<6;i++){
    const a1=(i/6)*Math.PI*2-ra*1.4,a2=((i+0.45)/6)*Math.PI*2-ra*1.4;
    rcc.beginPath();rcc.arc(RX,RY,32,a1,a2);rcc.strokeStyle='rgba(0,212,255,0.55)';rcc.lineWidth=2;rcc.shadowBlur=4;rcc.shadowColor='#00d4ff';rcc.stroke();rcc.shadowBlur=0;
  }
  // Core glow
  rcc.beginPath();rcc.arc(RX,RY,22,0,Math.PI*2);
  const ig=rcc.createRadialGradient(RX,RY,0,RX,RY,22);
  ig.addColorStop(0,`rgba(255,255,255,${p*0.9})`);ig.addColorStop(0.4,`rgba(100,220,255,${p*0.8})`);ig.addColorStop(1,`rgba(0,100,200,${p*0.25})`);
  rcc.fillStyle=ig;rcc.shadowBlur=18;rcc.shadowColor='#00d4ff';rcc.fill();rcc.shadowBlur=0;
  rcc.beginPath();rcc.arc(RX,RY,8,0,Math.PI*2);rcc.fillStyle='rgba(255,255,255,0.9)';rcc.shadowBlur=14;rcc.shadowColor='#fff';rcc.fill();rcc.shadowBlur=0;
  // Ticks
  for(let i=0;i<24;i++){
    const a=(i/24)*Math.PI*2;const r1=50,r2=i%4===0?57:53;
    rcc.beginPath();rcc.moveTo(RX+Math.cos(a)*r1,RY+Math.sin(a)*r1);rcc.lineTo(RX+Math.cos(a)*r2,RY+Math.sin(a)*r2);
    rcc.strokeStyle=`rgba(0,212,255,${i%4===0?0.7:0.25})`;rcc.lineWidth=i%4===0?1.5:0.8;rcc.stroke();
  }
  ra+=0.018;requestAnimationFrame(drawReactor);
}
drawReactor();