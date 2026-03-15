from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()

# Serve /static/* from the "static" folder
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main HTML page."""
    index_path = BASE_DIR / "index.html"
    return index_path.read_text(encoding="utf-8")

