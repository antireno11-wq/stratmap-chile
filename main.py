from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

# Monta la UI (debe ir al final)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
