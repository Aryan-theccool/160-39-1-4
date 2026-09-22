import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, "bis_scraper/src")

from fastapi.testclient import TestClient
from bis_api.config import Settings
from bis_api.main import create_app


def test_api_with_and_without_groq():
    # 1. Test with Groq
    settings_with_groq = Settings(
        data_dir=Path("."),
        store_dir=Path("vector_store"),
        embedder="st:BAAI/bge-base-en-v1.5",
        llm="groq",
    )
    app_groq = create_app(settings_with_groq)
    with TestClient(app_groq) as client:
        health_resp = client.get("/api/v1/health").json()
        print("--- HEALTH WITH GROQ ---")
        print("STATUS:", health_resp.get("status"))
        print("LLM:", health_resp.get("llm"))

        rec_resp = client.post(
            "/api/v1/recommend",
            json={"query": "What Indian Standards are relevant for outdoor LED street lighting?", "top_k": 4},
        )
        print("\n--- RECOMMEND WITH GROQ ---")
        print("STATUS CODE:", rec_resp.status_code)
        body = rec_resp.json()
        print("MODE:", body.get("mode"))
        print("GENERATOR:", body.get("generator"))
        print("GROUNDED:", body.get("grounded"))
        print("HAS_REPORT:", body.get("report") is not None)
        print("CITATIONS_COUNT:", len(body.get("citations", [])))
        print("WARNINGS:", body.get("warnings"))
        assert rec_resp.status_code == 200
        if body.get("mode") == "llm":
            assert "groq" in body.get("generator", "").lower()
            assert body.get("report") is not None
        else:
            assert body.get("mode") == "extractive"

    # 2. Test Fallback (No Groq)
    settings_no_llm = Settings(
        data_dir=Path("."),
        store_dir=Path("vector_store"),
        embedder="st:BAAI/bge-base-en-v1.5",
        llm="extractive",
    )
    app_no_llm = create_app(settings_no_llm)
    with TestClient(app_no_llm) as client:
        health_fallback = client.get("/api/v1/health").json()
        print("\n--- HEALTH FALLBACK ---")
        print("STATUS:", health_fallback.get("status"))
        print("LLM:", health_fallback.get("llm"))

        rec_fallback = client.post(
            "/api/v1/recommend",
            json={"query": "What Indian Standards are relevant for outdoor LED street lighting?", "top_k": 4},
        )
        print("\n--- RECOMMEND FALLBACK ---")
        print("STATUS CODE:", rec_fallback.status_code)
        fallback_body = rec_fallback.json()
        print("MODE:", fallback_body.get("mode"))
        print("GENERATOR:", fallback_body.get("generator"))
        print("GROUNDED:", fallback_body.get("grounded"))
        print("HAS_REPORT:", fallback_body.get("report") is not None)
        assert rec_fallback.status_code == 200
        assert fallback_body.get("mode") == "extractive"


if __name__ == "__main__":
    test_api_with_and_without_groq()
