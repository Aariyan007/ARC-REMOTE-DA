const radar=document.getElementById('radar');
const rctx=radar.getContext('2d');
const CX=95,CY=95,R=85;
const blips=[{a:0.8,r:0.45,l:'OBJ-01'},{a:2.4,r:0.7,l:'OBJ-02'},{a:4.2,r:0.55,l:'OBJ-03'}];
const fade=blips.map(()=>0);
let sw=0;
const TRAIL=Math.PI*0.75,FRAMES=90;
function drawRadar(){
  rctx.clearRect(0,0,190,190);
  // Rings
  [1,0.66,0.33].forEach(f=>{rctx.beginPath();rctx.arc(CX,CY,R*f,0,Math.PI*2);rctx.strokeStyle='rgba(0,212,255,0.12)';rctx.lineWidth=1;rctx.stroke();});
  // Cross
  rctx.strokeStyle='rgba(0,212,255,0.08)';rctx.lineWidth=0.5;
  rctx.beginPath();rctx.moveTo(CX-R,CY);rctx.lineTo(CX+R,CY);rctx.stroke();
  rctx.beginPath();rctx.moveTo(CX,CY-R);rctx.lineTo(CX,CY+R);rctx.stroke();
  // Trail
  for(let i=0;i<40;i++){
    const t=i/40,as=sw-TRAIL*(1-t),ae=sw-TRAIL*(1-t-1/40);
    rctx.beginPath();rctx.moveTo(CX,CY);rctx.arc(CX,CY,R,as,ae);rctx.closePath();
    rctx.fillStyle=`rgba(0,212,255,${t*0.14})`;rctx.fill();
  }
  // Sweep
  rctx.beginPath();rctx.moveTo(CX,CY);rctx.lineTo(CX+Math.cos(sw)*R,CY+Math.sin(sw)*R);
  rctx.strokeStyle='#00d4ff';rctx.lineWidth=1.5;rctx.shadowBlur=8;rctx.shadowColor='#00d4ff';rctx.stroke();rctx.shadowBlur=0;
  // Blips
  blips.forEach((b,i)=>{
    const norm=((b.a-sw)%(Math.PI*2)+Math.PI*2)%(Math.PI*2);
    if(norm<TRAIL)fade[i]=FRAMES;
    if(fade[i]>0){
      const alpha=fade[i]/FRAMES;fade[i]--;
      const bx=CX+Math.cos(b.a)*R*b.r,by=CY+Math.sin(b.a)*R*b.r;
      rctx.beginPath();rctx.arc(bx,by,4,0,Math.PI*2);rctx.fillStyle=`rgba(0,255,136,${alpha})`;rctx.shadowBlur=8;rctx.shadowColor='#00ff88';rctx.fill();rctx.shadowBlur=0;
      rctx.font="7px 'Share Tech Mono'";rctx.fillStyle=`rgba(0,255,136,${alpha*0.7})`;rctx.fillText(b.l,bx+6,by-4);
    }
  });
  // Center
  rctx.beginPath();rctx.arc(CX,CY,3,0,Math.PI*2);rctx.fillStyle='#00d4ff';rctx.shadowBlur=8;rctx.shadowColor='#00d4ff';rctx.fill();rctx.shadowBlur=0;
  sw+=0.03;requestAnimationFrame(drawRadar);
}
drawRadar();