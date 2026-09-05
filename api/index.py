from fastapi import FastAPI

try:
    from app.main import app
except Exception as exc:  # pragma: no cover - diagnostic bootstrap for serverless imports
    diagnostic_app = FastAPI(title="SuperVideoEditorAI bootstrap diagnostic")

    @diagnostic_app.get("/health")
    def bootstrap_health() -> dict:
        return {
            "status": "bootstrap_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    app = diagnostic_app
