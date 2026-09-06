import uvicorn
from starlette.responses import Response

from app.main import app


@app.middleware("http")
async def render_head_health(request, call_next):
    if request.method == "HEAD" and request.url.path == "/":
        return Response(status_code=200, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})
    response = await call_next(request)
    if request.url.path in {"/", "/index.html", "/app-free.js", "/app.js"}:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
