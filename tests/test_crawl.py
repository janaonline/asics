"""The same-site crawl: link extraction, ranking and the completeness note. No network."""

from asics_agent import source_requirements as sr
from asics_agent.links import crawl
from asics_agent.models import Parastatal, Source

HOME = "https://www.sample-board.in/"
PAGE = """
<html><body>
<header><nav class="main-menu"><ul>
  <li><a href="/about">About Us</a></li>
  <li><a href="budget.php?id=3">Budget</a></li>
  <li><a href="https://www.sample-board.in/reports/annual-report-2024.pdf">Annual Report</a></li>
  <li><a href="/about#top">About Us again</a></li>
  <li><a href="/gallery">Photo Gallery</a></li>
  <li><a href="https://other.gov.in/page">State portal</a></li>
  <li><a href="mailto:info@sample-board.in">Mail</a></li>
  <li><a href="javascript:void(0)">Menu toggle</a></li>
  <li><a href="/?lang=hi">हिंदी</a></li>
  <li><a href="/logo.png">Logo</a></li>
  <li><a href="/">Home</a></li>
  <li><a href="/login">Login</a></li>
</ul></nav></header>
<main><p>News</p><a href="/news/1">A news item in the body</a></main>
<footer><a href="/rti">RTI</a></footer>
</body></html>
"""


def urls(links):
    return [link.url for link in links]


def test_extract_links_keeps_same_site_pages_and_pdfs_only():
    links = crawl.extract_links(PAGE, HOME)
    assert urls(links) == [
        "https://www.sample-board.in/about",
        "https://www.sample-board.in/budget.php?id=3",
        "https://www.sample-board.in/reports/annual-report-2024.pdf",
        "https://www.sample-board.in/gallery",
        "https://www.sample-board.in/news/1",
        "https://www.sample-board.in/rti",
    ]
    # the fragment duplicate, other site, mailto, javascript, language switch, image, home and
    # login links are all dropped


def test_menu_links_are_the_ones_inside_navigation_blocks():
    flags = {link.url.rsplit("/", 1)[-1]: link.in_menu for link in crawl.extract_links(PAGE, HOME)}
    assert flags["about"] and flags["gallery"] and flags["rti"]  # header nav and footer
    assert not flags["1"]  # a link in the body is not a menu link


def test_a_complete_crawl_fits_the_cap_and_captures_every_menu_link():
    plan = crawl.plan_crawl(PAGE, HOME, cap=15)
    assert plan.menu_links == 5 and plan.possible
    assert len(plan.selected) == 5
    note = crawl.crawl_note(plan, captured=5)
    assert note == "SITE-CRAWL: complete, 5 of 5 menu links captured."


def test_links_are_ranked_by_topic_first_so_a_cut_keeps_the_relevant_pages():
    plan = crawl.plan_crawl(PAGE, HOME, cap=3)
    assert not plan.possible and "5 menu links found, more than the cap of 3" in plan.reason
    kept = urls(plan.selected)
    assert "https://www.sample-board.in/gallery" not in kept  # no topic word: cut first
    assert "https://www.sample-board.in/budget.php?id=3" in kept
    assert crawl.crawl_note(plan, captured=3).startswith("SITE-CRAWL: incomplete")


def test_a_javascript_menu_gives_an_incomplete_crawl():
    plan = crawl.plan_crawl("<html><body><div id='app'></div></body></html>", HOME, cap=15)
    assert plan.menu_links == 0 and "no menu links" in plan.reason
    assert "incomplete" in crawl.crawl_note(plan, captured=0)


def test_a_link_that_did_not_open_makes_the_crawl_incomplete():
    plan = crawl.plan_crawl(PAGE, HOME, cap=15)
    note = crawl.crawl_note(plan, captured=4, failed=["https://www.sample-board.in/rti"])
    assert "incomplete" in note and "did not open" in note and "/rti" in note


def test_the_note_is_what_the_gate_reads():
    agency = Parastatal(
        id="AAA", name="Sample Board", type="other", official_website="https://www.sample-board.in/"
    )
    home = Source(
        parastatal_id="AAA", title="Website", url=HOME, source_type="Official website", notes=""
    )
    assert sr.crawl_status(agency, [home])[0] == "none"
    plan = crawl.plan_crawl(PAGE, HOME, cap=15)
    home.notes = "Opened. " + crawl.crawl_note(plan, captured=5) + " More."
    assert sr.crawl_status(agency, [home])[0] == "complete"
    home.notes = crawl.crawl_note(crawl.plan_crawl(PAGE, HOME, cap=3), captured=3)
    assert sr.crawl_status(agency, [home])[0] == "incomplete"


def test_lenient_note_names_the_dead_links_it_ignored_and_stays_parseable():
    plan = crawl.plan_crawl(PAGE, HOME, cap=15)
    note = crawl.crawl_note(
        plan, captured=4, failed=[], ignored=["https://www.sample-board.in/gallery"]
    )
    assert note == (
        "SITE-CRAWL: complete, 4 of 5 menu links captured (lenient: 1 dead link(s) without a "
        "topic word ignored)."
    )
    agency = Parastatal(
        id="AAA", name="Sample Board", type="other", official_website="https://www.sample-board.in/"
    )
    home = Source(parastatal_id="AAA", title="Website", url=HOME, notes=note)
    assert sr.crawl_status(agency, [home])[0] == "complete"
    # a dead link that was not ignored still makes it incomplete; nothing captured is never complete
    assert "incomplete" in crawl.crawl_note(plan, captured=4, failed=["https://x/rti"], ignored=[])
    assert "incomplete" in crawl.crawl_note(
        plan, captured=0, failed=[], ignored=["a", "b", "c", "d", "e"]
    )
