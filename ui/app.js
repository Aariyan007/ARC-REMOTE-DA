function updateStats(){

document.getElementById("cpu").style.width =
Math.random()*100 + "%"

document.getElementById("ram").style.width =
Math.random()*100 + "%"

document.getElementById("net").style.width =
Math.random()*100 + "%"

}

setInterval(updateStats,2000)

function log(msg){

let box = document.getElementById("log")

let p = document.createElement("p")

p.innerText = msg

box.appendChild(p)

}

log("System boot complete")
log("Voice recognition ready")
log("Face recognition ready")

setInterval(()=>{

log("Scanning environment...")
log("Monitoring network traffic")

},5000)