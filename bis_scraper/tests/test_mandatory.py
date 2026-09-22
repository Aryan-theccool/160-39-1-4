"""Tests for the BIS compulsory-certification table parser."""

from bis_pipeline.mandatory import parse_tables

SCHEME_I_HTML = """
<html><body>
<table>
  <tr><th>Sl. No.</th><th>IS No.</th><th>Title</th><th>Product Category</th><th>Notification</th></tr>
  <tr><td>1.</td><td>IS 14286 IS/IEC 61730-1 IS/IEC 61730-2</td>
      <td>Crystalline Silicon Terrestrial Photovoltaic (PV) modules</td>
      <td>Crystalline Silicon PV modules</td><td>S.O. 2920(E) dated 30 August 2017</td></tr>
  <tr><td>2.</td><td>IS 798:2020</td><td>Ortho Phosphoric Acid - Specification</td>
      <td>Ortho Phosphoric Acid</td><td>S.O. 2335 (E) dated 15.06.2021</td></tr>
  <tr><td>3.</td><td>IS 17439:2020</td><td>Polyphosphoric Acid - Specification</td>
      <td>Polyphosphoric Acid</td><td>S.O. 5388(E)</td></tr>
</table>
</body></html>
"""

SCHEME_II_HTML = """
<table>
  <tr><th>Sl. No.</th><th>IS No.</th><th>Title</th><th>Product Category</th><th>Notification</th></tr>
  <tr><td>45.</td><td>IS 16103 Part 1: 2012</td><td>Standalone LED Modules</td>
      <td>LED Modules for General Lighting</td><td>CRO IV</td></tr>
  <tr><td>55.</td><td>IS 616: 2017</td><td>Television other than Plasma/LCD/LED</td>
      <td>Television</td><td>CRO IV</td></tr>
</table>
"""


class TestParseTables:
    def test_extracts_is_numbers_from_scheme_i(self):
        report = parse_tables(SCHEME_I_HTML, scheme="Scheme-I", source_url="u")

        designations = [s.designation.format() for s in report.standards]
        assert "IS 14286" in designations
        assert "IS/IEC 61730 (Part 1)" in designations
        assert "IS 798:2020" in designations
        assert "IS 17439:2020" in designations
        assert report.tables_seen == 1
        assert report.rows_with_is == 3

    def test_multiple_codes_in_one_cell_are_all_kept(self):
        report = parse_tables(SCHEME_I_HTML)
        first_row = [s for s in report.standards if s.designation.number == 14286]
        assert len(first_row) == 1
        assert first_row[0].raw_row.count("IS/IEC 61730") == 2, "row context preserved"

    def test_title_comes_from_the_prose_column(self):
        report = parse_tables(SCHEME_I_HTML)
        by_number = {s.designation.number: s.title for s in report.standards}
        assert "Ortho Phosphoric Acid" in by_number[798]

    def test_handles_part_in_title_column(self):
        report = parse_tables(SCHEME_II_HTML, scheme="Scheme-II")
        assert [s.designation.format() for s in report.standards] == [
            "IS 16103 (Part 1):2012", "IS 616:2017",
        ]
        assert report.standards[0].scheme == "Scheme-II"

    def test_sp_codes_are_ignored(self):
        html = "<table><tr><th>Sl</th><th>IS No.</th></tr><tr><td>1</td><td>SP 7:2026</td></tr></table>"
        report = parse_tables(html)
        assert report.standards == [], "SP handbooks are not product standards"

    def test_empty_and_headerless_input(self):
        assert parse_tables("").standards == []
        assert parse_tables("<html><body>no tables</body></html>").standards == []
        assert parse_tables("<table><tr><td>only one cell</td></tr></table>").standards == []

    def test_unheaded_table_still_yields_codes(self):
        html = "<table><tr><td>1</td><td>IS 456:2000</td><td>Plain and reinforced concrete</td></tr></table>"
        report = parse_tables(html)
        assert [s.designation.format() for s in report.standards] == ["IS 456:2000"]
