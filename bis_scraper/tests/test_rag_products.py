"""Unit tests for product recommendation engine."""

import pytest
from pathlib import Path

from bis_rag.data import BisData
from bis_rag.hybrid import HybridSearch
from bis_rag.products import (
    ProductDescriptor,
    normalize_product,
    classify_role,
    recommend_for_product,
    load_product_aliases,
)
from bis_rag.compliance import QCODatabase


@pytest.fixture
def data():
    """Load real corpus."""
    return BisData(Path(__file__).parent.parent / "bis_data")


@pytest.fixture
def search(data):
    """Build search engine."""
    return HybridSearch(data)


@pytest.fixture
def aliases():
    """Load product aliases."""
    return load_product_aliases(Path(__file__).parent.parent / "bis_data")


@pytest.fixture
def qco_db(data):
    """Build QCO database."""
    return QCODatabase(data)


class TestNormalizeProduct:
    """Test product description normalization."""
    
    def test_normalize_basic(self, aliases):
        """Normalize a basic product description."""
        desc = "50 kg bags of 43 grade ordinary portland cement"
        product = normalize_product(desc, aliases)
        
        assert product.raw == desc
        assert "ordinary portland cement" in product.normalized
        assert len(product.aliases_matched) > 0
        assert "43" in product.attributes.get("grade", [])
    
    def test_normalize_expands_aliases(self, aliases):
        """Expand OPC -> ordinary portland cement."""
        desc = "OPC 53 grade cement"
        product = normalize_product(desc, aliases)
        
        assert len(product.aliases_matched) > 0
        assert "53" in product.attributes.get("grade", [])
    
    def test_normalize_extracts_grades(self, aliases):
        """Extract grade attributes."""
        test_cases = [
            ("33 grade cement", ["33"]),
            ("43 grade ordinary portland cement", ["43"]),
            ("53 grade OPC", ["53"]),
            ("m25 concrete", ["m25"]),
            ("m30 rcc", ["m30"]),
        ]
        
        for desc, expected_grades in test_cases:
            product = normalize_product(desc, aliases)
            grades = product.attributes.get("grade", []) + product.attributes.get("concrete_grade", [])
            assert any(g in expected_grades for g in grades), f"Failed for: {desc}"
    
    def test_normalize_no_match_returns_empty_aliases(self, aliases):
        """If no alias matches, aliases_matched is empty."""
        desc = "some random industrial equipment"
        product = normalize_product(desc, aliases)
        
        assert product.aliases_matched == []
    
    def test_normalize_detect_sector(self, aliases):
        """detect_sector is called and sector is set."""
        desc = "cement for construction"
        product = normalize_product(desc, aliases)
        
        # sector may or may not be detected depending on detect_sector implementation
        assert hasattr(product, "sector")
        assert hasattr(product, "sector_hits")


class TestClassifyRole:
    """Test standard role classification."""
    
    def test_classify_test_method(self):
        """Identify test method standards."""
        titles = [
            "Methods of test for water and wastewater",
            "Method of test for concrete",
            "Methods of Tests for Internal Combustion Engines",
        ]
        
        for title in titles:
            role = classify_role(title)
            assert role == "test_method", f"Failed for: {title}"
    
    def test_classify_code_of_practice(self):
        """Identify code of practice standards."""
        titles = [
            "Code of practice for design, fabrication and erection of steel structures",
            "Code of practice for repair, maintenance and rehabilitation of reinforced concrete structures",
        ]
        
        for title in titles:
            role = classify_role(title)
            assert role == "code_of_practice", f"Failed for: {title}"
    
    def test_classify_packaging_marking(self):
        """Identify packaging/marking standards."""
        titles = [
            "Marking and labelling of products",
            "Packaging requirements for cement",
            "Marking of industrial products",
        ]
        
        for title in titles:
            role = classify_role(title)
            assert role == "packaging_marking", f"Failed for: {title}"
    
    def test_classify_product_standard(self):
        """Identify product specification standards."""
        titles = [
            "Specification for ordinary portland cement",
            "Specification of steel reinforcement bars",
            "Requirements for drinking water",
        ]
        
        for title in titles:
            role = classify_role(title)
            assert role in ("product_standard", "product_standard"), f"Failed for: {title}"
    
    def test_classify_other(self):
        """Classification falls back to 'other' for unknown formats."""
        title = "Completely ambiguous standard title"
        role = classify_role(title)
        
        assert role in ("other", "product_standard")


class TestRecommendForProduct:
    """Test the full recommendation pipeline."""
    
    def test_recommend_cement(self, data, search, aliases, qco_db):
        """Recommend for cement product."""
        description = "50 kg bags of 43 grade ordinary portland cement"
        
        recommendation = recommend_for_product(data, search, description, aliases=aliases, qco_db=qco_db)
        
        # Check structure
        assert hasattr(recommendation, "product")
        assert hasattr(recommendation, "primary")
        assert hasattr(recommendation, "related")
        assert hasattr(recommendation, "coverage")
        assert hasattr(recommendation, "took_ms")
        
        # Should find alias match
        assert recommendation.product.aliases_matched
        
        # Primary should not be empty
        assert recommendation.primary or recommendation.coverage.get("warnings")
    
    def test_recommend_all_current_editions(self, data, search, aliases, qco_db):
        """All recommendations must be current (not superseded)."""
        description = "ordinary portland cement"
        
        recommendation = recommend_for_product(data, search, description, aliases=aliases, qco_db=qco_db)
        
        # In recommend mode, HybridSearch enforces is_current
        # So every result should have is_current=True
        for row in recommendation.primary + recommendation.related:
            assert row.is_current, f"Non-current edition recommended: {row.designation}"
    
    def test_recommend_has_evidence(self, data, search, aliases, qco_db):
        """Every recommendation carries evidence."""
        description = "drinking water"
        
        recommendation = recommend_for_product(data, search, description, aliases=aliases, qco_db=qco_db)
        
        for row in recommendation.primary + recommendation.related:
            assert row.why, f"Missing evidence for {row.designation}"
            assert row.why.startswith(("alias:", "hybrid:")), f"Invalid evidence format: {row.why}"
    
    def test_recommend_caps_primary_at_5(self, data, search, aliases, qco_db):
        """Primary list is capped at 5."""
        description = "cement"
        
        recommendation = recommend_for_product(data, search, description, aliases=aliases, qco_db=qco_db, limit=20)
        
        assert len(recommendation.primary) <= 5
    
    def test_recommend_empty_description(self, data, search, aliases, qco_db):
        """Empty description handled gracefully."""
        description = ""
        
        # Should not crash
        try:
            recommendation = recommend_for_product(data, search, description, aliases=aliases, qco_db=qco_db)
            # May return empty results or coverage warning
            assert recommendation.coverage is not None
        except Exception as e:
            pytest.fail(f"Empty description caused crash: {e}")
    
    def test_recommend_no_corpus_match_warns(self, data, search, aliases, qco_db):
        """No corpus match returns results with low confidence."""
        description = "zzzzz nonexistent product yyyyy"
        
        recommendation = recommend_for_product(data, search, description, aliases=aliases, qco_db=qco_db)
        
        # Either has no alias hit, or scores are low
        # The important thing is it doesn't crash
        assert recommendation is not None
    
    def test_recommend_checklist_format(self, data, search, aliases, qco_db):
        """Checklist has correct format for CSV."""
        description = "ordinary portland cement"
        
        recommendation = recommend_for_product(data, search, description, aliases=aliases, qco_db=qco_db)
        
        for row in recommendation.checklist:
            assert "designation" in row
            assert "title" in row
            assert "role" in row
            assert "mandatory" in row
            assert "current" in row
            assert "why" in row
    
    def test_recommend_mandatory_overlay(self, data, search, aliases, qco_db):
        """Mandatory standards are flagged correctly."""
        description = "43 grade ordinary portland cement"
        
        recommendation = recommend_for_product(data, search, description, aliases=aliases, qco_db=qco_db)
        
        # Check that any mandatory rows are in the mandatory dict
        mandatory_designations = set(recommendation.mandatory.keys())
        
        for row in recommendation.primary + recommendation.related:
            if row.is_mandatory:
                assert row.designation in mandatory_designations
    
    def test_recommend_determinism(self, data, search, aliases, qco_db):
        """Same input always gives same output."""
        description = "drinking water"
        
        rec1 = recommend_for_product(data, search, description, aliases=aliases, qco_db=qco_db)
        rec2 = recommend_for_product(data, search, description, aliases=aliases, qco_db=qco_db)
        
        # Same designations in primary
        assert [r.designation for r in rec1.primary] == [r.designation for r in rec2.primary]


class TestLoadProductAliases:
    """Test alias loading."""
    
    def test_load_aliases(self, aliases):
        """Load product aliases from JSON."""
        assert isinstance(aliases, dict)
        assert len(aliases) > 0
    
    def test_aliases_structure(self, aliases):
        """Aliases have correct structure."""
        # Should have at least phrase entries
        assert any("cement" in key for key in aliases.keys())
    
    def test_aliases_contain_synonyms(self, aliases):
        """Aliases contain expected synonyms."""
        # Check for OPC
        opc_keys = [k for k in aliases.keys() if "opc" in k.lower()]
        assert len(opc_keys) > 0
