const msgs=['[ OK ] Kernel modules loaded','[ OK ] Neural core v4.2 initialized','[ OK ] SpeechBrain ECAPA-TDNN: READY','[ OK ] Porcupine wake engine: ACTIVE','[ OK ] Whisper STT: LOADED','[ OK ] OpenCV face detection: ONLINE','[ OK ] MediaPipe pipeline: READY','[ OK ] ESP32 sensor bridge: CONNECTED','[ OK ] Gemini AI fallback: STANDBY','[ OK ] Voice profile STARK,T.: VERIFIED','[ OK ] FastAPI server: STARTING','[ OK ] All systems nominal — FRIEND READY'];
const bl=document.getElementById('bootLog');let idx=0;
function nl(){
  if(idx>=msgs.length){
    setTimeout(()=>{
      const bs=document.getElementById('boot-screen');
      bs.classList.add('out');
      setTimeout(()=>{bs.classList.add('gone');document.getElementById('hud').classList.replace('hud-hidden','hud-visible');},900);
    },400);
    return;
  }
  const d=document.createElement('div');d.textContent=msgs[idx++];bl.appendChild(d);bl.scrollTop=bl.scrollHeight;
  setTimeout(nl,185+Math.random()*155);
}
setTimeout(nl,500);