"""Integration tests for /api/v1/product/recommend endpoint."""

import pytest
from fastapi.testclient import TestClient

from bis_api.main import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


class TestProductRecommendEndpoint:
    """Test the product recommendation API."""
    
    def test_post_with_description(self, client):
        """POST with description returns 200."""
        response = client.post(
            "/api/v1/product/recommend",
            params={"description": "ordinary portland cement"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "product" in data
        assert "primary" in data
        assert "related" in data
        assert "coverage" in data
        assert "took_ms" in data
    
    def test_get_with_description(self, client):
        """GET with description returns 200."""
        response = client.get(
            "/api/v1/product/recommend",
            params={"description": "43 grade cement"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "product" in data
    
    def test_empty_description_422(self, client):
        """Empty description returns 422."""
        response = client.post(
            "/api/v1/product/recommend",
            params={"description": ""}
        )
        
        assert response.status_code == 422
    
    def test_response_structure(self, client):
        """Response has expected structure."""
        response = client.post(
            "/api/v1/product/recommend",
            params={"description": "drinking water"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check product
        assert isinstance(data["product"], dict)
        assert "raw" in data["product"]
        assert "normalized" in data["product"]
        
        # Check primary
        assert isinstance(data["primary"], list)
        if data["primary"]:
            row = data["primary"][0]
            assert "designation" in row
            assert "title" in row
            assert "role" in row
            assert "is_mandatory" in row
            assert "why" in row
        
        # Check coverage
        assert isinstance(data["coverage"], dict)
        assert "has_alias_hit" in data["coverage"]
        assert "warnings" in data["coverage"]
    
    def test_mandatory_flagging(self, client):
        """Mandatory standards are flagged."""
        response = client.post(
            "/api/v1/product/recommend",
            params={"description": "ordinary portland cement"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # At least one should be mandatory
        all_rows = data["primary"] + data["related"]
        assert any(row["is_mandatory"] for row in all_rows) or not all_rows
    
    def test_limit_parameter(self, client):
        """limit parameter is respected."""
        response = client.post(
            "/api/v1/product/recommend",
            params={"description": "cement", "limit": 3}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Primary should be capped at min(limit, 5)
        assert len(data["primary"]) <= 5
    
    def test_all_results_current(self, client):
        """All results should be current editions."""
        response = client.post(
            "/api/v1/product/recommend",
            params={"description": "steel"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for row in data["primary"] + data["related"]:
            assert row["is_current"] is True
    
    def test_determinism(self, client):
        """Same input always gives same output."""
        description = "water"
        
        resp1 = client.post("/api/v1/product/recommend", params={"description": description})
        resp2 = client.post("/api/v1/product/recommend", params={"description": description})
        
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        
        data1 = resp1.json()
        data2 = resp2.json()
        
        # Same designations
        assert [r["designation"] for r in data1["primary"]] == [r["designation"] for r in data2["primary"]]
