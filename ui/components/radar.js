export function startRadar(){

const radar = document.querySelector(".outer")

let angle = 0

setInterval(()=>{

angle += 1
radar.style.transform = "rotate(" + angle + "deg)"

},20)

}