from fastapi import FastAPI

app = FastAPI(title="SuperVideoEditorAI Vercel probe")


@app.get("/health")
def health() -> dict:
    return {"status": "probe_ok"}
