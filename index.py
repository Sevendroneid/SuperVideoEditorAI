from fastapi import FastAPI
import importlib

app = FastAPI(title="SuperVideoEditorAI import probe")


@app.get("/health")
def health() -> dict:
    modules = [
        "app.ai",
        "app.config",
        "app.director",
        "app.jobs",
        "app.models",
        "app.main",
    ]
    results = {}
    for module_name in modules:
        try:
            importlib.import_module(module_name)
            results[module_name] = "ok"
        except BaseException as exc:
            results[module_name] = {
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            break
    return {"status": "import_probe", "results": results}
