from asics_agent.links.trust import rate_website
from asics_agent.models import AccessCheck


def _check(tmp_path, html: str) -> AccessCheck:
    text = tmp_path / "page.txt"
    snapshot = tmp_path / "page.html"
    text.write_text(html)
    snapshot.write_text(html)
    return AccessCheck(
        url="x",
        verification_status="Verified",
        accessibility="Public",
        content_path=str(text),
        snapshot_path=str(snapshot),
    )


def test_directory_sites_are_never_official(tmp_path):
    result = rate_website(
        "https://www.justdial.com/bwssb", _check(tmp_path, "BWSSB"), "BWSSB", "Water Board", []
    )
    assert result.score == 0 and result.band == "Not confirmed"


def test_gov_domain_with_backlinks_is_official(tmp_path):
    pages = [("https://urban.karnataka.gov.in/", "see https://bwssb.karnataka.gov.in/ here")]
    check = _check(tmp_path, "<title>BWSSB</title> Government of Karnataka")
    result = rate_website("https://bwssb.karnataka.gov.in/", check, "BWSSB", "Water Board", pages)
    assert result.band == "Official"
    assert any("Linked from 1" in r for r in result.reasons)


def test_gov_site_with_its_name_that_does_not_open_is_probably_official(tmp_path):
    check = AccessCheck(url="x", verification_status="Not verified", reasons=["HTTP 500."])
    result = rate_website(
        "https://bwssb.karnataka.gov.in/english", check, "BWSSB", "Water Board", []
    )
    assert result.score < 50 and result.band == "Probably official"
    assert any("please open it in your browser" in r for r in result.reasons)


def test_other_site_that_does_not_open_is_not_confirmed(tmp_path):
    check = AccessCheck(url="x", verification_status="Not verified", reasons=["HTTP 500."])
    gov_without_name = rate_website(
        "https://urban.karnataka.gov.in/", check, "BWSSB", "Water Board", []
    )
    named_but_not_gov = rate_website("https://bwssb.org/", check, "BWSSB", "Water Board", [])
    assert gov_without_name.band == named_but_not_gov.band == "Not confirmed"
