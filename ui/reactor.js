const canvas = document.getElementById("reactorCanvas")
const ctx = canvas.getContext("2d")

canvas.width = 400
canvas.height = 400

let angle = 0

function draw(){

ctx.clearRect(0,0,400,400)

ctx.strokeStyle="#00e1ff"
ctx.lineWidth=2

ctx.beginPath()
ctx.arc(200,200,150,0,Math.PI*2)
ctx.stroke()

ctx.beginPath()
ctx.arc(200,200,110,0,Math.PI*2)
ctx.stroke()

ctx.beginPath()
ctx.arc(200,200,70,0,Math.PI*2)
ctx.stroke()

ctx.save()

ctx.translate(200,200)
ctx.rotate(angle)

ctx.beginPath()
ctx.moveTo(0,0)
ctx.lineTo(150,0)

ctx.strokeStyle="rgba(0,225,255,0.6)"
ctx.lineWidth=4
ctx.stroke()

ctx.restore()

ctx.beginPath()
ctx.arc(200,200,20,0,Math.PI*2)
ctx.fillStyle="#00e1ff"
ctx.fill()

angle += 0.01

requestAnimationFrame(draw)

}

draw()