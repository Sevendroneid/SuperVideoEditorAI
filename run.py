import uvicorn

from app.main import app


@app.head("/")
def dashboard_head():
    return None


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
