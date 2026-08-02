from fastapi import FastAPI

app = FastAPI(
    title="Support Agent API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)


@app.get("/", include_in_schema=False)
async def service_info() -> dict[str, str]:
    return {
        "service": "support-agent-api",
        "status": "scaffold-ready",
    }
