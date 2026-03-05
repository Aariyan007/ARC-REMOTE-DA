export function startScanner(){

const line = document.querySelector(".scan-line")

let pos = 0

setInterval(()=>{

pos += 2

if(pos > 200){
pos = 0
}

line.style.top = pos + "px"

},30)

}