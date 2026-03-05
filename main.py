from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

# serve static files from the ui folder
app.mount("/ui", StaticFiles(directory="ui"), name="ui")

@app.get("/")
def home():
    return FileResponse("ui/index.html")