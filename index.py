from fastapi import FastAPI

try:
    from app.main import app
except Exception as exc:  # pragma: no cover - temporary startup diagnostic
    diagnostic_app = FastAPI(title="SuperVideoEditorAI startup diagnostic")

    @diagnostic_app.get("/health")
    def health() -> dict:
        return {
            "status": "startup_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    app = diagnostic_app
