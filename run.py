import uvicorn
from starlette.responses import Response

from app.main import app


@app.middleware("http")
async def render_head_health(request, call_next):
    if request.method == "HEAD" and request.url.path == "/":
        return Response(status_code=200)
    return await call_next(request)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
