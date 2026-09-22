"""CLI-level tests.

These drive ``main(argv)`` rather than the underlying functions, so the argparse
wiring, exit codes and printed output are covered too. That matters: several
subcommands are only reachable through the parser, and ``cmd_mandatory`` had no
coverage at all until this file existed.

Network-touching subcommands get a fake transport via monkeypatching
``build_client``, so they still execute the real command body.
"""

import json

import pytest

from bis_pipeline import cli
from bis_pipeline.cli import main
from bis_pipeline.http import HttpClient, HttpError, RetryPolicy

from conftest import FakeResponse, FakeSession, NoSleep, fixture

BIS_TABLE_HTML = """
<html><body>
<table>
  <tr><th>Sl. No.</th><th>IS No.</th><th>Title</th><th>Product Category</th></tr>
  <tr><td>1.</td><td>IS 798:2020</td><td>Ortho Phosphoric Acid - Specification</td>
      <td>Ortho Phosphoric Acid</td></tr>
  <tr><td>2.</td><td>IS 10500:2012</td><td>Drinking water - Specification</td>
      <td>Drinking water</td></tr>
</table>
</body></html>
"""


@pytest.fixture
def data_dir(tmp_path):
    """A data dir pre-seeded as if `archive` had already run."""
    from bis_pipeline.archive_scraper import _serialise, parse_item

    archive = tmp_path / "archive"
    (archive / "text").mkdir(parents=True)
    item = parse_item(json.loads(fixture("item_gov_in_is_11367_1985.json")))
    (archive / "items.jsonl").write_text(json.dumps(_serialise(item)) + "\n", encoding="utf-8")
    (archive / "text" / "gov.in.is.11367.1985.txt").write_text(
        fixture("is.11367.1985_djvu.txt"), encoding="utf-8")
    return tmp_path


def fake_client_factory(session):
    """Return a build_client replacement bound to `session`."""
    def build_client(args):
        return HttpClient(session=session, sleep=NoSleep(), min_interval=0.0,
                          policy=RetryPolicy(attempts=2))
    return build_client


class TestMergeIndexQuery:
    def test_merge_then_index_then_query(self, data_dir, capsys):
        assert main(["--data-dir", str(data_dir), "merge"]) == 0
        assert (data_dir / "merged" / "merged_standards.jsonl").exists()

        assert main(["--data-dir", str(data_dir), "index"]) == 0
        assert (data_dir / "index" / "search_index.json").exists()

        assert main(["--data-dir", str(data_dir), "query", "aerospace textile glossary"]) == 0
        out = capsys.readouterr().out
        assert "IS 11367:1985" in out
        assert "archive.org/details/gov.in.is.11367.1985" in out

    def test_merge_reports_when_there_is_nothing_to_merge(self, tmp_path, capsys):
        assert main(["--data-dir", str(tmp_path), "merge"]) == 1
        assert "nothing to merge" in capsys.readouterr().out

    def test_index_without_merge_fails_cleanly(self, tmp_path, capsys):
        assert main(["--data-dir", str(tmp_path), "index"]) == 1
        assert "run `merge` first" in capsys.readouterr().out

    def test_query_without_index_fails_cleanly(self, tmp_path, capsys):
        assert main(["--data-dir", str(tmp_path), "query", "anything"]) == 1
        assert "run `index` first" in capsys.readouterr().out

    def test_merge_picks_up_qco_and_portal_inputs(self, data_dir, capsys):
        (data_dir / "mandatory").mkdir()
        (data_dir / "mandatory" / "mandatory.json").write_text(json.dumps([
            {"designation": "IS 10500:2012", "canonical": "c", "title": "Drinking water",
             "scheme": "Scheme-I", "source_url": "u"},
        ]))
        portal = data_dir / "portal.json"
        portal.write_text(json.dumps([
            {"is_number": "IS 14220:1994", "title": "pump sets old", "status": "withdrawn"},
            {"is_number": "IS 14220:2002", "title": "pump sets", "status": "published"},
        ]))

        assert main(["--data-dir", str(data_dir), "merge",
                     "--portal-json", str(portal)]) == 0

        out = capsys.readouterr().out
        assert "1 QCO-mandated" in out
        rows = [json.loads(l) for l in
                (data_dir / "merged" / "merged_standards.jsonl").read_text().splitlines()]
        by_desig = {r["designation"]: r for r in rows}
        assert by_desig["IS 10500:2012"]["is_compulsory"] is True
        assert by_desig["IS 14220:1994"]["is_current"] is False
        assert by_desig["IS 14220:2002"]["is_current"] is True

    def test_query_suppresses_superseded_unless_asked(self, data_dir, capsys):
        portal = data_dir / "portal.json"
        portal.write_text(json.dumps([
            {"is_number": "IS 14220:1994", "title": "submersible pump old edition"},
            {"is_number": "IS 14220:2002", "title": "submersible pump new edition"},
        ]))
        main(["--data-dir", str(data_dir), "merge", "--portal-json", str(portal)])
        main(["--data-dir", str(data_dir), "index"])

        main(["--data-dir", str(data_dir), "query", "submersible pump"])
        assert "IS 14220:1994" not in capsys.readouterr().out

        main(["--data-dir", str(data_dir), "query", "submersible pump", "--include-superseded"])
        out = capsys.readouterr().out
        assert "IS 14220:1994" in out and "superseded by IS 14220:2002" in out


class TestMandatoryCommand:
    def test_writes_parsed_is_numbers(self, tmp_path, monkeypatch, capsys):
        session = FakeSession({"www.bis.gov.in": FakeResponse(200, BIS_TABLE_HTML.encode())})
        monkeypatch.setattr(cli, "build_client", fake_client_factory(session))

        assert main(["--data-dir", str(tmp_path), "mandatory"]) == 0

        out_path = tmp_path / "mandatory" / "mandatory.json"
        assert out_path.exists()
        rows = json.loads(out_path.read_text())
        assert [r["designation"] for r in rows] == ["IS 798:2020", "IS 10500:2012"]
        assert rows[0]["canonical"] == "IS|798|None|None|2020|None"
        assert "tables_seen" in capsys.readouterr().out

    def test_no_urls_flag_still_uses_bis_defaults(self, tmp_path, monkeypatch):
        """`--urls` defaults to [], which must mean "use BIS's pages".

        Passing the empty list straight through made `mandatory` scrape zero
        URLs and write an empty report while still exiting 0.
        """
        session = FakeSession({"www.bis.gov.in": FakeResponse(200, BIS_TABLE_HTML.encode())})
        monkeypatch.setattr(cli, "build_client", fake_client_factory(session))

        assert main(["--data-dir", str(tmp_path), "mandatory"]) == 0

        assert session.count("www.bis.gov.in") == 1, "must fetch BIS's default page"
        rows = json.loads((tmp_path / "mandatory" / "mandatory.json").read_text())
        assert len(rows) == 2

    def test_warns_when_bis_markup_changes(self, tmp_path, monkeypatch, capsys):
        session = FakeSession({"www.bis.gov.in": FakeResponse(200, b"<html>no tables</html>")})
        monkeypatch.setattr(cli, "build_client", fake_client_factory(session))

        assert main(["--data-dir", str(tmp_path), "mandatory"]) == 0
        assert "may have changed their markup" in capsys.readouterr().out

    def test_unreachable_page_does_not_crash(self, tmp_path, monkeypatch):
        session = FakeSession({}, default=FakeResponse(500, b"boom"))
        monkeypatch.setattr(cli, "build_client", fake_client_factory(session))

        assert main(["--data-dir", str(tmp_path), "mandatory"]) == 0
        assert json.loads((tmp_path / "mandatory" / "mandatory.json").read_text()) == []


class TestArchiveCommand:
    def test_network_failure_is_reported_not_swallowed(self, tmp_path, monkeypatch):
        def exploding_build_client(args):
            raise HttpError("GET https://archive.org/advancedsearch.php failed",
                            status=None, url="https://archive.org/advancedsearch.php")

        monkeypatch.setattr(cli, "build_client", exploding_build_client)
        with pytest.raises(HttpError):
            main(["--data-dir", str(tmp_path), "archive", "--max-items", "1"])

    def test_scrapes_into_the_data_dir(self, tmp_path, monkeypatch, capsys):
        session = FakeSession({
            "advancedsearch": FakeResponse(200, fixture("advancedsearch_page0.json").encode()),
            "metadata/gov.in.is.11367.1985": FakeResponse(
                200, fixture("item_gov_in_is_11367_1985.json").encode()),
            "metadata/gov.in.is.12970.3.2.1992": FakeResponse(500, b""),
            "metadata/gov.in.is.104.1979": FakeResponse(500, b""),
            "_djvu.txt": FakeResponse(200, fixture("is.11367.1985_djvu.txt").encode()),
        })
        monkeypatch.setattr(cli, "build_client", fake_client_factory(session))

        assert main(["--data-dir", str(tmp_path), "archive", "--max-items", "3"]) == 0

        assert (tmp_path / "archive" / "items.jsonl").exists()
        assert (tmp_path / "archive" / "text" / "gov.in.is.11367.1985.txt").exists()
        assert "1 items" in capsys.readouterr().out


class TestParser:
    def test_global_flags_precede_the_subcommand(self):
        parser = cli.build_parser()
        args = parser.parse_args(["--data-dir", "/tmp/x", "--min-interval", "2.5",
                                  "query", "pump", "-k", "3"])
        assert args.data_dir == "/tmp/x" and args.min_interval == 2.5
        assert args.queries == ["pump"] and args.k == 3

    def test_every_subcommand_has_a_handler(self):
        parser = cli.build_parser()
        # `query` and `all` take positionals, so each needs its minimum argv.
        samples = {
            "archive": ["archive"], "mandatory": ["mandatory"], "merge": ["merge"],
            "index": ["index"], "query": ["query", "pump"], "all": ["all"],
        }
        for name, argv in samples.items():
            assert callable(parser.parse_args(argv).func), f"{name} has no handler"

    def test_query_exposes_min_score(self):
        args = cli.build_parser().parse_args(["query", "x", "--min-score", "0.2"])
        assert args.min_score == 0.2
