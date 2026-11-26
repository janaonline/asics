# Categories

One settings file per ASICS category. A city is assessed in each category: first choose the
city, then the category. There are two:

- **ULG** (Urban Local Government): its own set of questions. Each ULG question is answered
  once per city.
- **Parastatal**: each applicable question is answered separately for every parastatal in the
  city. The parastatals differ between cities; the question set and question codes are the same.

UPD, SC and DPG are **sections** inside a category's question bank. They are not categories.

Every category runs the same steps:

1. **Find sources**: the units to assess, their official websites, the Citation Sheet.
2. **Answer questions**: from the reviewed Citation Sheet only.
3. **Score**: from each Step 2 answer and its citation.

What differs is set here: the question bank, what is assessed (`unit`: `parastatal` or `ulg`),
which agent does each job in each step, the shared rules, where its city folders go, and its
scoring workbook (`scoring_code` names its files and sheets). See the main README, "Adding a
new ASICS category".

**`required_sources`** (`on` or `off`, default `off`; Parastatal sets `on`): when on, a score of 0
is allowed only if every source the question requires is in the agency's Citation Sheet and was
read. The table of required sources is `data/question_source_requirements.yaml`. With it off, a 0 is
judged as before.

**`crawl_max_pages`** (default 15 for Parastatal, 0 = off): Step 1 opens the menu links of each
agency's confirmed home page, one level deep. **`crawl_incomplete_on_dead_link`** (`strict` by
default, or `lenient`): strict makes any menu link that did not open an incomplete crawl; lenient
ignores a dead link whose text and address name no topic word. To switch, edit the word in the
category file, save, and restart the app.

**`staged_fetch`** (`on` or `off`, default `on`): a link the plain check cannot open is tried again
(its http/https and www forms), then in a headless Chromium browser (pages drawn by JavaScript;
a certificate that cannot be verified is bypassed only for the agency's own site and `.gov.in` /
`.nic.in`), then in the Wayback Machine (for a 404, a 5xx or a site that cannot be reached). The
Citation Sheet's last column, **Copy Type**, says how each copy was obtained (plain HTTP,
browser-rendered, certificate not verified, ARCHIVED <date>, stale archive, saved by team). An
archived copy can support a positive finding but never a zero, a required source or a complete
crawl; one older than **`archive_max_age_days`** (default 365) is not used. **`failure_cache_hours`**
(default 24): a link that failed every stage is not tried again for that long. **`fetch_time_cap_minutes`**
(default 20): after it, links in that run get the plain check only and Needs Attention lists them as
"not retried this run". `off` gives exactly the earlier plain check. **`fetch_cache_max_age_days`** (default 30):
a page opened in one city or step is reused from `outputs/_cache` for that long. **`scan_reading_budget_usd`**
(default 3.00; 5.00 for Parastatal): the most one run spends on Claude reading scanned PDFs, legal texts
and required sources first; a document that does not fit is skipped whole. **`scan_batch_wait_minutes`**
(default 20): how long Step 1 waits for a scan-reading batch before it finishes and collects it later.
Scan-reading copies carry their own marks: *read by Claude (scan)* (a PDF with no text layer),
*read by Claude (page images)* (a damaged file whose pages were rendered to pictures), *repaired* (a
damaged PDF the app rewrote and then read as text), *partial scan* (some pages did not come back; only
those are read again next time), *check transcription* (section numbers skip or repeat, so text may have
been dropped) and *scan reading in progress* (a batch Step 1 did not wait for). A partial scan, a
copy to check and one in progress, like an archived copy, cannot support a zero, a required source or a
complete crawl. PDFs up to 100 MB are downloaded in full.
