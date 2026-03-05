export function startWaveform(){

const bars = document.querySelectorAll(".wave span")

setInterval(()=>{

bars.forEach(bar=>{
bar.style.height = (20 + Math.random()*50) + "px"
})

},100)

}