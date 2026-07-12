"""
================================================================================
 COLLEGE WEBSITE SCRAPER  —  built on Crawl4AI
================================================================================

WHAT THIS SCRIPT DOES (in plain English)
------------------------------------------
1. You give it the homepage URL of a college website (e.g. an Indian private
   engineering college site).
2. It "deep crawls" the whole site — meaning it starts at the homepage,
   finds every link on that page, follows those links, finds more links,
   and keeps going (breadth-first) until it has visited every page it can
   reach on that domain (or hits a safety limit you set).
3. For every normal HTML page it visits, it:
      - Strips out the junk that repeats on every page (header, footer, nav
        menu, cookie banners, <script>/<style> tags, etc.)
      - Converts what's left into clean Markdown text (perfect food for a
        RAG pipeline / vector database).
      - Saves that Markdown to its own .txt/.md file on disk.
4. Crawl4AI (as of the version documented at docs.crawl4ai.com) CAN read
   PDFs directly (see the "PDFCrawlerStrategy" / "PDFContentScrapingStrategy"
   classes), BUT it can only do that if you feed it the PDF's own URL as a
   crawl target. A "deep crawl" of an HTML site does NOT open PDFs as pages
   for you automatically — it just sees a link that points to a .pdf file.
   So instead of letting Crawl4AI try (and possibly choke on) every PDF,
   this script:
      - Never tries to render a PDF as if it were a webpage.
      - Instead, every time it sees a link ending in .pdf (or .docx/.xlsx/
        .pptx — other common "document" files Indian college sites dump
        online), it records that URL in a JSON file.
   That JSON file is exactly the input you said you'll later feed into
   Docling (`pip install docling`) to turn those PDFs into clean text.
   Docling is a much better PDF parser than Crawl4AI's built-in one for
   messy scanned notices, tables, admission brochures, etc. — so this is
   the right division of labour.
5. Because Indian college websites are famously unreliable (broken SSL
   certificates, random 500 errors, infinite calendar pages, pages that
   never finish loading, servers that fall over under load), this script
   also:
      - Ignores SSL certificate errors (many .edu.in sites have expired
        or self-signed certificates).
      - Saves its crawl progress to disk after every single page, so if
        the script crashes or you Ctrl+C it, you can re-run it and it will
        pick up exactly where it left off instead of starting over.
      - Limits how many pages it will visit and how deep it will go, so a
        site with an infinite "next month" calendar link can't trap it
        forever.
      - Politely limits how many pages it fetches at the same time, so it
        doesn't hammer a cheap shared-hosting server into the ground.


HOW TO RUN THIS SCRIPT
------------------------------------------
Step 1 — install the two things you need (only once):

    pip install -U crawl4ai
    crawl4ai-setup

`crawl4ai-setup` downloads the actual browser (Playwright/Chromium) that
Crawl4AI drives under the hood. Without this step the script will fail.

Step 2 — run it, pointing at the college's homepage:

    python college_scraper.py --url "https://www.somecollege.edu.in" \
        --output "./somecollege_data" \
        --max-pages 400 \
        --max-depth 6

Step 3 — look inside the output folder. You'll find:

    somecollege_data/
        markdown/                  <- one clean .md file per HTML page
        pdf_and_document_urls.json <- every PDF/DOCX/XLSX/PPTX link found
        failed_urls.json           <- pages that errored out (for review)
        crawl_state.json           <- internal checkpoint (for resuming)

If the script stops for any reason, just run the exact same command again.
It will detect crawl_state.json and resume instead of starting from zero.


WHAT YOU'LL WIRE UP LATER WITH DOCLING
------------------------------------------
Once you're ready, `pdf_and_document_urls.json` looks like this:

    [
      {"url": "https://college.edu.in/notices/timetable.pdf",
       "found_on_page": "https://college.edu.in/academics/"},
      ...
    ]

Later, you'll loop over that list and do something like:

    from docling.document_converter import DocumentConverter
    converter = DocumentConverter()
    result = converter.convert("https://college.edu.in/notices/timetable.pdf")
    clean_text = result.document.export_to_markdown()

This script even includes a ready-made (but OFF by default) helper function
called `run_docling_pass()` near the bottom that does exactly this loop for
you, downloading and converting every discovered document. Turn it on with
the `--with-docling` flag once you `pip install docling`.

================================================================================
"""

# ------------------------------------------------------------------------
# IMPORTS
# ------------------------------------------------------------------------
# argparse -> lets us accept command-line options like --url and --output,
#             so this ONE script can be reused for ANY college's website
#             instead of hard-coding a single URL.
# asyncio   -> Crawl4AI is built "async" (it can do many things concurrently
#             without blocking), so our whole script has to run inside an
#             asyncio event loop.
# json      -> for reading/writing our checkpoint and URL-list files.
# os / re / sys -> basic filesystem and text-cleanup helpers.
# pathlib   -> a nicer, modern way to build file paths than string-concat.
# urllib.parse -> for pulling the domain name out of a URL, and for
#             checking whether a link ends in .pdf etc.
# datetime  -> just used to stamp files/logs with the current time.
# ------------------------------------------------------------------------
import argparse
import asyncio
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen

# ------------------------------------------------------------------------
# CRAWL4AI IMPORTS
# ------------------------------------------------------------------------
# AsyncWebCrawler   -> the main "browser driver" object. You open one of
#                      these (like opening a browser window) and reuse it
#                      for every page you visit.
# BrowserConfig     -> settings for the underlying browser itself (headless
#                      or not, ignore SSL errors, custom user-agent, etc).
# CrawlerRunConfig  -> settings for ONE crawl "run" (which strategy to use,
#                      what to exclude, how markdown should be generated,
#                      timeouts, etc). You can reuse the same one for every
#                      page in a run.
# CacheMode         -> Crawl4AI can cache pages it already fetched. Since we
#                      want fresh data for a RAG chatbot, we tell it to
#                      always bypass the cache and fetch live.
# BFSDeepCrawlStrategy -> "Breadth First Search" deep crawl: visit the start
#                      page, then all pages ONE link away, then all pages
#                      TWO links away, and so on. This gives good, even
#                      coverage of a whole site instead of tunnelling deep
#                      down one random menu first (which is what Depth
#                      First Search / DFS would do).
# DomainFilter      -> a rule object that only allows the crawler to follow
#                      links that stay on the college's own domain (so it
#                      doesn't wander off into Facebook, YouTube, etc).
# ContentTypeFilter -> a rule object that only lets the crawler treat a URL
#                      as a "page to crawl" if the server says it's actual
#                      HTML. This is what keeps PDFs/images/zips from being
#                      accidentally opened as if they were webpages.
# FilterChain       -> bundles multiple filter rules together; a link only
#                      gets followed if it passes ALL of them.
# LXMLWebScrapingStrategy -> the actual HTML-cleaning engine Crawl4AI uses.
#                      It's the fast, modern default — we set it explicitly
#                      so behaviour doesn't silently change between
#                      Crawl4AI versions.
# DefaultMarkdownGenerator -> turns cleaned HTML into Markdown text.
# PruningContentFilter -> a smart "junk remover" that looks at each block of
#                      text on the page and scores it by how "link-heavy"
#                      or "boilerplate-like" it looks (menus, footers,
#                      cookie notices, etc.) and throws away the low-scoring
#                      blocks. This catches repeated junk EVEN IF it isn't
#                      wrapped in a proper <nav>/<footer> tag — which is
#                      extremely common on the kind of hand-built, messy
#                      HTML you find on Indian college websites.
# ------------------------------------------------------------------------
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
)
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.filters import FilterChain, DomainFilter, ContentTypeFilter
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter


# ------------------------------------------------------------------------
# FILE EXTENSIONS WE TREAT AS "DOCUMENTS FOR DOCLING" RATHER THAN "PAGES"
# ------------------------------------------------------------------------
# Indian college sites LOVE dumping information as PDFs (timetables, fee
# structures, admission brochures, results, circulars). Some also use
# .docx / .xlsx / .pptx. Docling can read ALL of these formats, so we
# collect all of them into the same "please run Docling on these" list,
# instead of only looking for .pdf.
DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt")

# Link "schemes" that are not real web pages and should never be crawled
# or logged as documents (e.g. <a href="mailto:office@college.edu.in">).
NON_HTTP_SCHEMES = ("mailto:", "tel:", "javascript:", "#")


def is_document_url(url: str) -> bool:
    """
    Returns True if this URL POINTS AT a downloadable document (PDF, Word,
    Excel, PowerPoint) rather than an HTML page.

    We strip off anything after a "?" (query string) or "#" (page anchor)
    first, because a real-world link often looks like:
        https://college.edu.in/files/result.pdf?download=1
    and we still want that recognised as a PDF.
    """
    clean_url = url.split("?")[0].split("#")[0].lower()
    return clean_url.endswith(DOCUMENT_EXTENSIONS)


def is_crawlable_http_link(url: str) -> bool:
    """
    Returns True only for links that are worth even looking at — i.e. they
    start with http:// or https:// and are not mailto:/tel:/javascript:
    pseudo-links. This keeps our document-collector and our crawl targets
    clean of junk that isn't really a URL at all.
    """
    if not url:
        return False
    lowered = url.strip().lower()
    if lowered.startswith(NON_HTTP_SCHEMES):
        return False
    return lowered.startswith("http://") or lowered.startswith("https://")


# ------------------------------------------------------------------------
# SITEMAP.XML DISCOVERY  (new)
# ------------------------------------------------------------------------
# You told this crawler to only trust what it can reach by following
# <a href> links from the homepage, up to --max-depth clicks deep. On real
# sites that under-counts badly — pages get orphaned from nav menus, JS
# renders links this crawler's static link-scan never sees, deep archive
# pages fall outside your depth limit, etc.
#
# Most CMSs (and every site run through a sitemap generator, which is what
# produced JIIT's) publish an explicit, authoritative URL list at
# sitemap.xml. We fetch that BEFORE the crawl starts and use it two ways:
#   1. Document URLs (.pdf/.docx/etc) in the sitemap go straight into
#      documents_found — no need to "discover" a link Docling will use later.
#   2. HTML page URLs in the sitemap that the BFS crawl didn't already
#      reach get swept up in a second pass after the main crawl finishes.
#
# We treat the sitemap as ANOTHER SOURCE, not ground truth — it's often
# third-party generated (see the XML comment JIIT's own sitemap contains:
# "created with Free Online Sitemap Generator www.xml-sitemaps.com") and
# can itself be stale. That's why we still run the full link-based crawl
# too, instead of just trusting the sitemap alone.
SITEMAP_XML_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def fetch_url_text(url: str, timeout: int = 20) -> str | None:
    """
    Fetch the raw text of a URL with plain urllib (no browser needed for a
    static XML/text file). SSL verification is disabled here for the same
    reason it's disabled on the browser side in BrowserConfig — a lot of
    .edu.in sites have expired or self-signed certificates, and refusing to
    talk to them means missing sitemap.xml/robots.txt entirely.
    """
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; CollegeScraperBot/1.0)"})
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - any fetch failure just means "no sitemap here"
        print(f"[sitemap] Could not fetch {url}: {exc}")
        return None


def discover_sitemap_candidate_urls(start_url: str) -> list:
    """
    Works out which URL(s) to even TRY as a sitemap, in priority order:
      1. Whatever robots.txt explicitly declares via "Sitemap:" lines —
         this is the standards-compliant way a site announces its sitemap,
         and can point anywhere (not necessarily /sitemap.xml).
      2. The conventional guesses (/sitemap.xml, /sitemap_index.xml) as a
         fallback for sites whose robots.txt doesn't mention one.
    """
    parsed = urlparse(start_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    candidates = []

    robots_text = fetch_url_text(f"{root}/robots.txt")
    if robots_text:
        for line in robots_text.splitlines():
            if line.strip().lower().startswith("sitemap:"):
                candidates.append(line.split(":", 1)[1].strip())

    for guess in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml"):
        guess_url = root + guess
        if guess_url not in candidates:
            candidates.append(guess_url)

    return candidates


def parse_sitemap_xml(xml_text: str):
    """
    Parses ONE sitemap XML document. The sitemap spec allows two shapes:
      - <urlset><url><loc>...</loc></url>...</urlset>
            -> this IS the list of real page/document URLs.
      - <sitemapindex><sitemap><loc>...</loc></sitemap>...</sitemapindex>
            -> this is a list of OTHER sitemaps to go fetch (common on
               large sites that split their sitemap into chunks).
    Returns (page_urls, nested_sitemap_urls) — exactly one of the two
    lists will be non-empty depending on which shape this document was.
    """
    page_urls, nested_sitemaps = [], []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        print(f"[sitemap] Not valid XML, skipping: {exc}")
        return page_urls, nested_sitemaps

    root_tag = root.tag.lower()
    if root_tag.endswith("urlset"):
        for url_el in root:
            loc_el = url_el.find(f"{SITEMAP_XML_NS}loc")
            if loc_el is None:
                loc_el = url_el.find("loc")  # tolerate sitemaps with no/odd namespace
            if loc_el is not None and loc_el.text:
                page_urls.append(loc_el.text.strip())
    elif root_tag.endswith("sitemapindex"):
        for sitemap_el in root:
            loc_el = sitemap_el.find(f"{SITEMAP_XML_NS}loc")
            if loc_el is None:
                loc_el = sitemap_el.find("loc")
            if loc_el is not None and loc_el.text:
                nested_sitemaps.append(loc_el.text.strip())

    return page_urls, nested_sitemaps


def get_all_sitemap_urls(start_url: str, max_sitemap_files: int = 25) -> list:
    """
    Full pipeline: find the site's sitemap(s), follow sitemap-index nesting
    (a sitemap of sitemaps), and return the flat, de-duplicated list of
    every URL any of them list. max_sitemap_files caps how many individual
    sitemap XML files we'll fetch, as a safety net against a pathological
    or malicious index that nests forever.
    """
    seen_sitemaps = set()
    to_fetch = discover_sitemap_candidate_urls(start_url)
    all_page_urls = []

    while to_fetch and len(seen_sitemaps) < max_sitemap_files:
        sitemap_url = to_fetch.pop(0)
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)

        xml_text = fetch_url_text(sitemap_url)
        if not xml_text or "<" not in xml_text:
            continue  # 404 / HTML error page / not actually XML - skip silently

        pages, nested = parse_sitemap_xml(xml_text)
        if pages or nested:
            extra = f" (+{len(nested)} nested sitemaps)" if nested else ""
            print(f"[sitemap] {sitemap_url} -> {len(pages)} URLs{extra}")
        all_page_urls.extend(pages)
        to_fetch.extend(nested)

    return list(dict.fromkeys(all_page_urls))  # de-dup, keep first-seen order


def slugify_url_to_filename(url: str) -> str:
    """
    Turns a URL into a safe filename for saving to disk.

    Example:
        https://www.college.edu.in/admissions/btech-fees/  ->
        www.college.edu.in__admissions_btech-fees.md

    We can't just use the URL as a filename because URLs contain characters
    (like "/" and ":") that aren't allowed in filenames. We also cap the
    length, because very long URLs (common on WordPress calendar/search
    pages) would otherwise create filenames the filesystem rejects.
    """
    parsed = urlparse(url)
    # netloc = the domain, e.g. "www.college.edu.in"
    # path   = everything after the domain, e.g. "/admissions/btech-fees/"
    path = parsed.path.strip("/")
    if not path:
        path = "home"
    # Replace anything that isn't a letter/number/dash/underscore with "_"
    safe_path = re.sub(r"[^a-zA-Z0-9]+", "_", path)
    safe_domain = re.sub(r"[^a-zA-Z0-9]+", "_", parsed.netloc)
    filename = f"{safe_domain}__{safe_path}"
    # Cap length so we never hit filesystem filename limits.
    filename = filename[:150]
    return filename + ".md"


def load_json_file(path: Path, default):
    """Small helper: read a JSON file if it exists, otherwise return `default`."""
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # File got corrupted (e.g. we crashed mid-write last time).
            # Better to start fresh than to crash the whole script.
            return default
    return default


def save_json_file(path: Path, data):
    """Small helper: write `data` to disk as nicely-formatted JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------------
# THE MAIN CRAWL FUNCTION
# ------------------------------------------------------------------------
def process_crawl_result(
    result,
    markdown_dir: Path,
    visited_url_to_file: dict,
    visited_map_file: Path,
    documents_found: list,
    documents_seen_urls: set,
    documents_file: Path,
) -> bool:
    """
    Everything that needs to happen for ONE successfully-crawled page:
    save its cleaned markdown to disk, and scan its links for any PDF/
    DOCX/XLSX/PPTX documents. Pulled out into its own function because
    BOTH the main homepage deep-crawl loop AND the sitemap sweep-pass
    (for pages the deep-crawl never reached) need to do exactly this.

    Returns True if markdown was saved, False if the page had nothing
    left after cleanup.
    """
    depth = result.metadata.get("depth", 0) if result.metadata else 0

    # --- Save the cleaned Markdown for this page -------------------------
    md_object = result.markdown
    fit_markdown = getattr(md_object, "fit_markdown", None)
    raw_markdown = getattr(md_object, "raw_markdown", str(md_object))
    body_text = fit_markdown if fit_markdown and fit_markdown.strip() else raw_markdown

    saved = False
    if body_text and body_text.strip():
        filename = slugify_url_to_filename(result.url)
        file_path = markdown_dir / filename

        page_title = (result.metadata or {}).get("title", "")
        frontmatter = (
            "---\n"
            f"source_url: {result.url}\n"
            f"title: {page_title}\n"
            f"crawl_depth: {depth}\n"
            f"scraped_at: {datetime.now(timezone.utc).isoformat()}\n"
            "---\n\n"
        )
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(frontmatter + body_text)

        visited_url_to_file[result.url] = filename
        save_json_file(visited_map_file, visited_url_to_file)
        saved = True
        print(f"[saved depth={depth}] {result.url}  ->  markdown/{filename}")
    else:
        print(f"[empty]  {result.url}  (nothing left after cleanup — skipped)")

    # --- Look for PDF/Word/Excel/PowerPoint links on this page -----------
    all_links_on_page = (result.links or {}).get("internal", []) + (
        result.links or {}
    ).get("external", [])

    for link in all_links_on_page:
        href = link.get("href", "")
        if not href:
            continue
        absolute_href = urljoin(result.url, href)

        if not is_crawlable_http_link(absolute_href):
            continue
        if not is_document_url(absolute_href):
            continue
        if absolute_href in documents_seen_urls:
            continue

        documents_seen_urls.add(absolute_href)
        documents_found.append(
            {
                "url": absolute_href,
                "found_on_page": result.url,
                "link_text": (link.get("text") or "").strip(),
            }
        )

    save_json_file(documents_file, documents_found)
    return saved


async def crawl_college_site(
    start_url: str,
    output_dir: Path,
    max_pages: int,
    max_depth: int,
    concurrency: int,
    sitemap_html_urls: list = None,
):
    """
    This is the heart of the script. It configures Crawl4AI and runs a
    deep crawl starting from `start_url`, saving results as it goes.

    sitemap_html_urls: HTML page URLs pulled from the site's sitemap.xml
    (see get_all_sitemap_urls) that we ALSO want covered. Any of these not
    already reached by the homepage's link-following deep crawl get swept
    up in a second pass at the end.
    """
    sitemap_html_urls = sitemap_html_urls or []

    # --- Prepare our output folders -------------------------------------
    markdown_dir = output_dir / "markdown"
    markdown_dir.mkdir(parents=True, exist_ok=True)

    state_file = output_dir / "crawl_state.json"
    documents_file = output_dir / "pdf_and_document_urls.json"
    failed_file = output_dir / "failed_urls.json"
    visited_map_file = output_dir / "visited_url_to_file.json"

    # These dictionaries/lists are our "memory" for this run. We reload
    # them from disk if a previous run already created them, so re-running
    # the script never loses earlier progress.
    documents_found = load_json_file(documents_file, default=[])
    documents_seen_urls = {doc["url"] for doc in documents_found}
    failed_urls = load_json_file(failed_file, default=[])
    visited_url_to_file = load_json_file(visited_map_file, default={})

    # If a previous run left a checkpoint, we resume from it instead of
    # starting the crawl over from page 1. This is the "crash recovery"
    # feature Crawl4AI's BFSDeepCrawlStrategy supports natively.
    resume_state = load_json_file(state_file, default=None)
    if resume_state:
        print(
            f"[resume] Found a previous checkpoint — it had already "
            f"crawled {resume_state.get('pages_crawled', 0)} pages. "
            f"Continuing from there instead of starting over."
        )

    # --- Work out which domain we are allowed to stay on ----------------
    start_domain = urlparse(start_url).netloc  # e.g. "www.college.edu.in"

    # --- Set up the "which links are we even allowed to follow" rules ---
    # DomainFilter        -> never leave the college's own domain.
    # ContentTypeFilter   -> only follow links whose SERVER RESPONSE says
    #                        "this is an HTML page". This is what stops the
    #                        deep crawler from trying to open a PDF, a JPG,
    #                        or a ZIP file as if it were a webpage. It does
    #                        NOT stop us from noticing the link exists —
    #                        we still collect it below via result.links.
    filter_chain = FilterChain(
        [
            DomainFilter(allowed_domains=[start_domain]),
            ContentTypeFilter(allowed_types=["text/html"]),
        ]
    )

    # --- The callback Crawl4AI calls after EVERY single page, so we can
    #     save a checkpoint to disk. This is what makes the crawl resumable
    #     if the script crashes or you stop it halfway through. -----------
    async def save_checkpoint(state: dict):
        save_json_file(state_file, state)

    deep_crawl_strategy = BFSDeepCrawlStrategy(
        max_depth=max_depth,          # how many "clicks" away from the homepage to go
        include_external=False,       # never follow links off the college's domain
        max_pages=max_pages,          # hard safety cap on total pages visited
        filter_chain=filter_chain,
        resume_state=resume_state,    # None on a first run, or a loaded checkpoint
        on_state_change=save_checkpoint,
    )

    # --- Set up how "junk" gets removed from each page's text -----------
    # excluded_tags: these whole HTML tags get deleted before we even look
    # at the text. This is the FIRST line of defense against repeated
    # header/footer/nav/cookie-banner content that every single page on
    # the site shares.
    excluded_tags = ["nav", "header", "footer", "form", "aside", "script", "style", "noscript"]

    # PruningContentFilter is the SECOND line of defense. Lots of Indian
    # college sites build their nav menu or sidebar out of plain <div>s and
    # <table>s instead of proper <nav>/<aside> tags, so excluded_tags alone
    # won't catch everything. PruningContentFilter scores every remaining
    # block of text by how "real" it looks (link density, word count,
    # structure) and throws out the low-scoring, boilerplate-looking bits.
    #   threshold_type="dynamic" -> it adapts the cutoff per-page instead of
    #                               using one fixed number for every page,
    #                               which matters because a "Contact Us"
    #                               page and a long "About the College"
    #                               page have very different natural
    #                               lengths.
    #   min_word_threshold=5     -> ignore text blocks shorter than 5 words
    #                               (these are almost always menu labels,
    #                               "Read More" buttons, etc).
    content_filter = PruningContentFilter(
        threshold=0.45,
        threshold_type="dynamic",
        min_word_threshold=5,
    )

    markdown_generator = DefaultMarkdownGenerator(
        content_filter=content_filter,
        options={
            "ignore_links": True,   # drop inline hyperlinks from the markdown text
            "ignore_images": True,  # drop image references from the markdown text
            "escape_html": False,   # keep special characters (like &, %) readable
            "body_width": 0,        # 0 = don't hard-wrap lines at N characters
        },
    )

    # --- The full "how to crawl every page" configuration ----------------
    run_config = CrawlerRunConfig(
        deep_crawl_strategy=deep_crawl_strategy,
        scraping_strategy=LXMLWebScrapingStrategy(),
        markdown_generator=markdown_generator,
        excluded_tags=excluded_tags,
        word_count_threshold=8,          # skip whole blocks shorter than 8 words
        exclude_social_media_links=True, # drop Facebook/Twitter/Instagram footer links
        exclude_external_images=True,    # skip images hosted on other domains (ad/CDN junk)
        process_iframes=False,            # pull in content that's embedded via <iframe>
        remove_overlay_elements=True,    # try to auto-remove popups/modals
        remove_consent_popups=True,      # try to auto-remove cookie-consent banners
        wait_until="domcontentloaded",   # don't wait forever for slow trackers/ads to load
        delay_before_return_html=1.5,    # small grace period for lazy-loaded content
        page_timeout=60000,              # give slow Indian shared-hosting servers 60s
        semaphore_count=concurrency,     # how many pages to fetch AT THE SAME TIME
        check_robots_txt=True,           # be a polite, respectful crawler
        stream=True,                     # hand us results one-by-one as they finish,
                                          # instead of making us wait for the ENTIRE
                                          # site before we see anything (also uses less
                                          # memory on a big site)
        verbose=True,
        cache_mode=CacheMode.BYPASS,     # always fetch fresh — we want current data
    )

    # --- The actual browser settings -------------------------------------
    browser_config = BrowserConfig(
        headless=True,          # run without a visible window (faster, works on servers)
        # A LOT of Indian college websites run on old shared hosting with
        # misconfigured, expired, or self-signed SSL certificates. Without
        # this, the crawler would refuse to even open the homepage.
        ignore_https_errors=True,
        # Some cheap hosting setups / basic firewalls block requests that
        # "look like a bot". A normal desktop-browser user-agent avoids
        # tripping that up for no good reason.
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        verbose=True,
    )

    pages_crawled_this_run = 0
    pages_saved_this_run = 0

    print(f"\n[start] Crawling {start_url}")
    print(f"[start] Staying on domain: {start_domain}")
    print(f"[start] Limits: max_depth={max_depth}, max_pages={max_pages}, concurrency={concurrency}\n")

    # `async with AsyncWebCrawler(...) as crawler:` starts up the underlying
    # browser once, and automatically shuts it down cleanly when we're done
    # (even if an error happens inside the `with` block).
    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            # Because run_config.stream=True, crawler.arun() gives us back
            # something we can loop over with `async for`, receiving one
            # finished page at a time instead of waiting for the whole
            # crawl to finish before we see anything.
            async for result in await crawler.arun(start_url, config=run_config):
                pages_crawled_this_run += 1

                if not result.success:
                    # The page failed (404, timeout, server error, etc).
                    # We log it and move on — one broken page on a college
                    # site should never stop the whole crawl.
                    print(f"[FAILED] {result.url}  ->  {result.error_message}")
                    failed_urls.append(
                        {"url": result.url, "error": str(result.error_message)}
                    )
                    save_json_file(failed_file, failed_urls)
                    continue

                if process_crawl_result(
                    result,
                    markdown_dir,
                    visited_url_to_file,
                    visited_map_file,
                    documents_found,
                    documents_seen_urls,
                    documents_file,
                ):
                    pages_saved_this_run += 1

        except KeyboardInterrupt:
            print("\n[stopped] You pressed Ctrl+C. Progress up to this point is saved.")
            print("          Run the exact same command again to resume.")
        except Exception as exc:  # noqa: BLE001 - we want to survive ANY crawl error
            print(f"\n[error] The crawl stopped early because of: {exc}")
            print("        Your progress so far is saved. Run the same command again to resume.")

        # --- SITEMAP SWEEP PASS -------------------------------------------
        # The homepage deep-crawl above only ever reaches pages connected
        # by <a href> links within max_depth clicks. Anything sitemap.xml
        # listed that we DIDN'T just visit — orphaned pages, JS-rendered
        # nav items, pages buried deeper than max_depth — gets fetched
        # directly here, one URL at a time (no further link-following,
        # since these are exact URLs, not a discovery problem).
        sitemap_pending = [
            u for u in sitemap_html_urls
            if u not in visited_url_to_file and len(visited_url_to_file) < max_pages
        ]
        if sitemap_pending:
            print(f"\n[sitemap sweep] {len(sitemap_pending)} sitemap URLs weren't reached "
                  f"by the deep crawl — fetching them directly now.")
            single_page_config = CrawlerRunConfig(
                scraping_strategy=LXMLWebScrapingStrategy(),
                markdown_generator=markdown_generator,
                excluded_tags=excluded_tags,
                word_count_threshold=8,
                exclude_social_media_links=True,
                exclude_external_images=True,
                process_iframes=False,
                remove_overlay_elements=True,
                remove_consent_popups=True,
                wait_until="domcontentloaded",
                delay_before_return_html=1.5,
                page_timeout=60000,
                check_robots_txt=True,
                verbose=False,
                cache_mode=CacheMode.BYPASS,
            )
            for sitemap_url in sitemap_pending:
                if len(visited_url_to_file) >= max_pages:
                    print(f"[sitemap sweep] Hit max_pages={max_pages} cap, stopping sweep early.")
                    break
                try:
                    result = await crawler.arun(sitemap_url, config=single_page_config)
                    if isinstance(result, list):  # some crawl4ai versions return a list of 1
                        result = result[0] if result else None
                    if result is None:
                        continue
                    if not result.success:
                        print(f"[FAILED, sweep] {sitemap_url}  ->  {result.error_message}")
                        failed_urls.append({"url": sitemap_url, "error": str(result.error_message)})
                        save_json_file(failed_file, failed_urls)
                        continue
                    if process_crawl_result(
                        result,
                        markdown_dir,
                        visited_url_to_file,
                        visited_map_file,
                        documents_found,
                        documents_seen_urls,
                        documents_file,
                    ):
                        pages_saved_this_run += 1
                except Exception as exc:  # noqa: BLE001 - one bad sweep URL shouldn't kill the rest
                    print(f"[FAILED, sweep] {sitemap_url}  ->  {exc}")
                    failed_urls.append({"url": sitemap_url, "error": str(exc)})
                    save_json_file(failed_file, failed_urls)

    # --- Reconcile against the sitemap, so you know exactly what's still
    #     missing even after the sweep pass above (e.g. pages that 404'd,
    #     or documents the sitemap knew about that no page ever linked to).
    still_missing_file = output_dir / "still_missing_after_sitemap.json"
    if sitemap_html_urls:
        still_missing = [u for u in sitemap_html_urls if u not in visited_url_to_file]
        save_json_file(still_missing_file, still_missing)


    # --- Final summary ----------------------------------------------------
    print("\n" + "=" * 70)
    print("CRAWL SUMMARY")
    print("=" * 70)
    print(f"Pages processed this run : {pages_crawled_this_run}")
    print(f"Markdown files saved     : {pages_saved_this_run}")
    print(f"Total markdown files ever: {len(visited_url_to_file)}")
    print(f"PDF/DOCX/XLSX/PPTX found : {len(documents_found)}  -> {documents_file}")
    print(f"Failed pages             : {len(failed_urls)}  -> {failed_file}")
    if sitemap_html_urls:
        still_missing_count = len([u for u in sitemap_html_urls if u not in visited_url_to_file])
        print(f"Sitemap HTML URLs        : {len(sitemap_html_urls)}")
        print(f"Still missing vs sitemap : {still_missing_count}  -> {still_missing_file}")
    print(f"Output folder            : {output_dir.resolve()}")
    print("=" * 70)


# ------------------------------------------------------------------------
# OPTIONAL DOCLING PASS (off by default — turn on with --with-docling)
# ------------------------------------------------------------------------
# This is where the "Indian private college PDFs are messy" problem gets
# handled. In practice these documents fall into roughly three buckets:
#   1. Genuine digital PDFs (application forms, circulars) — Docling's
#      normal text-layer extraction handles these fine and fast.
#   2. Scanned/photocopied documents — sometimes a clean single scan,
#      sometimes a phone photo of a notice board, sometimes a scan with a
#      garbled OCR text layer already baked in by whatever scanner/printer
#      produced it. These need real OCR, and force_full_page_ocr to ignore
#      that garbled pre-existing layer.
#   3. Legacy binary Office files (.doc/.ppt/.xls, NOT .docx/.pptx/.xlsx).
#      Docling only understands the modern XML-based Office formats — it
#      has no support at all for the old binary ones — so these need to be
#      converted to a modern format first (via LibreOffice) before Docling
#      can touch them.
#
# Strategy: download the raw bytes ourselves (so we can verify the file is
# actually what its extension claims — Indian college servers frequently
# serve an HTML error/redirect page at a URL that LOOKS like a .pdf link),
# bridge legacy Office formats through LibreOffice if needed, then run a
# FAST Docling pass first. If that pass fails outright OR produces
# suspiciously thin/low-confidence text (using Docling's built-in
# confidence grades, backed by a blunt char-density check as a safety net),
# escalate to a slower, more aggressive OCR pass. Anything still bad after
# BOTH passes gets saved anyway (partial text beats no text) but flagged
# needs_manual_review so it doesn't silently poison your RAG index.
# ------------------------------------------------------------------------

LEGACY_TO_MODERN_OFFICE_EXT = {"doc": "docx", "ppt": "pptx", "xls": "xlsx"}

# Below this average characters-per-page, a "successful" conversion is
# almost certainly garbled or near-empty and should be escalated to OCR.
MIN_CHARS_PER_PAGE_THRESHOLD = 40
# A document producing less text than this, period, is functionally empty
# regardless of how many pages it claims to have.
MIN_ABSOLUTE_CHARS_THRESHOLD = 20


def find_libreoffice_binary():
    """LibreOffice ships as either 'soffice' or 'libreoffice' depending on
    the OS/package — check both before giving up."""
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    return None


def download_document_bytes(url: str, timeout: int = 60):
    """
    Download a document's raw bytes ourselves rather than handing Docling
    the URL directly. This lets us verify what we actually got BEFORE
    spending OCR time on it — Indian college servers routinely serve an
    HTML error/login/redirect page at a URL that ends in .pdf.
    """
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; CollegeScraperBot/1.0)"})
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001
        print(f"[docling] Download failed for {url}: {exc}")
        return None


def sniff_actual_format(raw_bytes: bytes) -> str:
    """
    Identify a document's REAL format from its magic bytes, ignoring
    whatever the URL's extension claims. Returns one of:
    'pdf', 'docx', 'pptx', 'xlsx', 'ole_legacy_office' (old binary
    .doc/.ppt/.xls — magic bytes alone can't tell which), 'html_error_page'
    (server returned a webpage, not a document), 'empty', or 'unknown'.
    """
    if not raw_bytes:
        return "empty"

    head = raw_bytes[:8]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"):
        return "ole_legacy_office"
    if head.startswith(b"PK\x03\x04"):
        # Modern Office formats are ZIP archives with a distinctive internal
        # folder layout — that's the only reliable way to tell them apart.
        try:
            with zipfile.ZipFile(BytesIO(raw_bytes)) as zf:
                names = zf.namelist()
                if any(n.startswith("word/") for n in names):
                    return "docx"
                if any(n.startswith("ppt/") for n in names):
                    return "pptx"
                if any(n.startswith("xl/") for n in names):
                    return "xlsx"
        except zipfile.BadZipFile:
            pass
        return "zip_unknown"

    stripped_lower = raw_bytes[:200].lstrip().lower()
    if stripped_lower.startswith(b"<!doctype") or stripped_lower.startswith(b"<html"):
        return "html_error_page"

    return "unknown"


def convert_legacy_office_with_libreoffice(raw_bytes: bytes, legacy_ext: str, tmp_dir: Path):
    """
    Bridges old binary Office formats to modern ones via LibreOffice
    headless conversion, since Docling has no support for .doc/.ppt/.xls
    at all (only the XML-based .docx/.pptx/.xlsx). Returns the converted
    bytes, or None if LibreOffice isn't installed or the conversion failed.
    """
    soffice_path = find_libreoffice_binary()
    if not soffice_path:
        return None

    target_ext = LEGACY_TO_MODERN_OFFICE_EXT.get(legacy_ext)
    if not target_ext:
        return None

    input_path = tmp_dir / f"legacy_input.{legacy_ext}"
    input_path.write_bytes(raw_bytes)

    try:
        subprocess.run(
            [
                soffice_path, "--headless", "--norestore",
                "--convert-to", target_ext, "--outdir", str(tmp_dir),
                str(input_path),
            ],
            check=True, timeout=120, capture_output=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"[docling] LibreOffice conversion of .{legacy_ext} failed: {exc}")
        return None

    converted_path = tmp_dir / f"legacy_input.{target_ext}"
    return converted_path.read_bytes() if converted_path.exists() else None


def build_docling_converters():
    """
    Builds the two conversion pipelines used for every document. Built
    ONCE and reused across all documents — constructing a DocumentConverter
    loads/initializes the underlying AI models, which is expensive to redo
    per-document.
    """
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        EasyOcrOptions,
        PdfPipelineOptions,
        TableFormerMode,
        TableStructureOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    accelerator_options = AcceleratorOptions(
        num_threads=max(os.cpu_count() or 4, 4),
        device=AcceleratorDevice.AUTO,
    )

    # --- TIER 1: fast pass ------------------------------------------------
    # do_ocr=True WITHOUT force_full_page_ocr means Docling only runs OCR
    # on pages/regions that actually lack a text layer — most admin PDFs
    # (fee structures, circulars, application forms) are real digital PDFs,
    # so this tier handles the majority of documents quickly.
    fast_pdf_options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        table_structure_options=TableStructureOptions(
            do_cell_matching=True, mode=TableFormerMode.ACCURATE
        ),
        ocr_options=EasyOcrOptions(confidence_threshold=0.5),
        accelerator_options=accelerator_options,
        document_timeout=180,
    )
    fast_converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=fast_pdf_options)}
    )

    # --- TIER 2: OCR-heavy escalation pass ---------------------------------
    # For the actually messy stuff: scanned admission brochures, photocopied
    # notices, forms that are just a photograph of paper. force_full_page_ocr
    # throws away any garbled pre-existing text layer and re-reads the
    # ENTIRE rendered page image. images_scale=2.5 renders at higher
    # resolution before OCR, which matters for low-quality photocopies
    # where small print would otherwise be unreadable. The confidence
    # threshold is lowered so OCR doesn't discard marginal-but-real text
    # on bad scans.
    ocr_heavy_pdf_options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        table_structure_options=TableStructureOptions(
            do_cell_matching=True, mode=TableFormerMode.ACCURATE
        ),
        ocr_options=EasyOcrOptions(force_full_page_ocr=True, confidence_threshold=0.3),
        images_scale=2.5,
        accelerator_options=accelerator_options,
        document_timeout=300,
    )
    ocr_heavy_converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=ocr_heavy_pdf_options)}
    )

    return fast_converter, ocr_heavy_converter


def _grade_name(grade) -> str:
    return getattr(grade, "name", str(grade)) if grade is not None else "UNKNOWN"


def _markdown_quality_is_poor(result) -> bool:
    """
    Primary signal: Docling's own confidence grades (mean_grade/low_grade -
    POOR/FAIR/GOOD/EXCELLENT, v2.34+). Backed by a blunt text-density
    heuristic as a safety net, since confidence scoring is relatively new
    and we'd rather over-escalate to the slower OCR pass than silently
    accept a page of near-empty garbage.
    """
    confidence = getattr(result, "confidence", None)
    if confidence is not None:
        if _grade_name(getattr(confidence, "mean_grade", None)) == "POOR":
            return True
        if _grade_name(getattr(confidence, "low_grade", None)) == "POOR":
            return True

    try:
        markdown_text = result.document.export_to_markdown()
    except Exception:  # noqa: BLE001
        return True

    char_count = len(markdown_text.strip())
    page_count = len(getattr(result, "pages", None) or []) or 1

    if char_count < MIN_ABSOLUTE_CHARS_THRESHOLD:
        return True
    if (char_count / page_count) < MIN_CHARS_PER_PAGE_THRESHOLD:
        return True
    return False


def convert_one_document(
    doc_entry: dict,
    docs_output_dir: Path,
    fast_converter,
    ocr_heavy_converter,
    tmp_dir: Path,
) -> dict:
    """
    Full pipeline for ONE document: download -> verify actual format ->
    bridge legacy Office formats if needed -> fast Docling pass -> escalate
    to OCR-heavy pass if the fast pass failed or looks low-quality -> save
    whatever's best, flagged for manual review if it's still poor.
    """
    from docling.datamodel.base_models import ConversionStatus, DocumentStream

    url = doc_entry["url"]
    report = {
        "url": url,
        "found_on_page": doc_entry.get("found_on_page", ""),
        "status": "failed",
        "engine_used": None,
        "grade": None,
        "char_count": 0,
        "page_count": 0,
        "needs_manual_review": False,
        "error": None,
        "saved_file": None,
    }

    raw_bytes = download_document_bytes(url)
    if not raw_bytes:
        report["error"] = "download_failed"
        return report

    detected_format = sniff_actual_format(raw_bytes)

    if detected_format == "html_error_page":
        report["error"] = "url_returned_html_not_a_document (broken link / redirect / login wall)"
        return report
    if detected_format == "empty":
        report["error"] = "downloaded_zero_bytes"
        return report

    url_path = url.split("?")[0].split("#")[0]
    url_ext = url_path.rsplit(".", 1)[-1].lower() if "." in url_path else ""
    stream_name = slugify_url_to_filename(url).replace(".md", "")

    # --- Bridge legacy binary Office formats (.doc/.ppt/.xls) -------------
    if detected_format == "ole_legacy_office" or url_ext in LEGACY_TO_MODERN_OFFICE_EXT:
        legacy_ext = url_ext if url_ext in LEGACY_TO_MODERN_OFFICE_EXT else "doc"
        converted_bytes = convert_legacy_office_with_libreoffice(raw_bytes, legacy_ext, tmp_dir)
        if converted_bytes is None:
            report["error"] = (
                f"legacy_.{legacy_ext}_format_unsupported — Docling can't read old binary "
                f"Office formats and LibreOffice isn't available to convert it first "
                f"(install with: sudo apt-get install libreoffice)"
            )
            return report
        raw_bytes = converted_bytes
        stream_name = f"{stream_name}.{LEGACY_TO_MODERN_OFFICE_EXT[legacy_ext]}"
        pdf_like = False
    elif detected_format == "pdf":
        stream_name = f"{stream_name}.pdf"
        pdf_like = True
    elif "." not in stream_name and url_ext:
        stream_name = f"{stream_name}.{url_ext}"
        pdf_like = False
    else:
        pdf_like = False

    source = DocumentStream(name=stream_name, stream=BytesIO(raw_bytes))

    # --- Tier 1: fast pass --------------------------------------------------
    result = None
    engine_used = "fast"
    try:
        result = fast_converter.convert(source, raises_on_error=False)
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"fast_pass_exception: {exc}"

    needs_escalation = (
        result is None
        or result.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS)
        or _markdown_quality_is_poor(result)
    )

    # --- Tier 2: OCR-heavy escalation - only worth it for PDFs. A DOCX/
    # XLSX/PPTX that failed the fast pass has no text-layer/scan distinction
    # for OCR to fix.
    if needs_escalation and pdf_like:
        try:
            source.stream.seek(0)
            retried = ocr_heavy_converter.convert(source, raises_on_error=False)
            if retried is not None:
                result = retried
                engine_used = "ocr_heavy"
        except Exception as exc:  # noqa: BLE001
            if result is None:
                report["error"] = f"ocr_heavy_pass_exception: {exc}"

    if result is None:
        return report

    try:
        markdown_text = result.document.export_to_markdown()
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"markdown_export_failed: {exc}"
        return report

    char_count = len(markdown_text.strip())
    if char_count == 0:
        report["error"] = "empty_after_conversion"
        return report

    confidence = getattr(result, "confidence", None)
    grade = _grade_name(getattr(confidence, "mean_grade", None)) if confidence is not None else None
    page_count = len(getattr(result, "pages", None) or [])
    still_poor = _markdown_quality_is_poor(result)

    filename = slugify_url_to_filename(url).replace(".md", "") + ".md"
    file_path = docs_output_dir / filename
    frontmatter = (
        "---\n"
        f"source_url: {url}\n"
        f"found_on_page: {doc_entry.get('found_on_page', '')}\n"
        f"converted_at: {datetime.now(timezone.utc).isoformat()}\n"
        f"conversion_engine: {engine_used}\n"
        f"confidence_grade: {grade}\n"
        f"page_count: {page_count}\n"
        f"needs_manual_review: {str(still_poor).lower()}\n"
        "---\n\n"
    )
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(frontmatter + markdown_text)

    report.update(
        {
            "status": "needs_review" if still_poor else "ok",
            "engine_used": engine_used,
            "grade": grade,
            "char_count": char_count,
            "page_count": page_count,
            "needs_manual_review": still_poor,
            "saved_file": filename,
            "error": None,
        }
    )
    return report


def run_docling_pass(output_dir: Path):
    try:
        import docling  # noqa: F401 - import check only
    except ImportError:
        print(
            "\n[docling] The 'docling' package isn't installed yet.\n"
            "          Install it with:  pip install docling\n"
            "          Then re-run this script with --with-docling.\n"
        )
        return

    documents_file = output_dir / "pdf_and_document_urls.json"
    documents = load_json_file(documents_file, default=[])
    if not documents:
        print("[docling] No documents found in pdf_and_document_urls.json — nothing to do.")
        return

    docs_output_dir = output_dir / "documents_markdown"
    docs_output_dir.mkdir(parents=True, exist_ok=True)

    report_file = output_dir / "docling_conversion_report.json"
    review_file = output_dir / "documents_needing_review.json"

    # Resumable, same philosophy as the crawl: reload whatever already
    # converted cleanly so re-running --with-docling doesn't redo
    # (potentially slow, OCR-heavy) work on documents already handled.
    existing_report = load_json_file(report_file, default=[])
    report_by_url = {r["url"]: r for r in existing_report}
    already_ok_urls = {url for url, r in report_by_url.items() if r.get("status") == "ok"}

    pending = [d for d in documents if d["url"] not in already_ok_urls]
    print(
        f"\n[docling] {len(documents)} documents total, "
        f"{len(already_ok_urls)} already converted OK, {len(pending)} to process now."
    )
    if not pending:
        print("[docling] Nothing to do.")
        return

    if find_libreoffice_binary() is None:
        print(
            "[docling] NOTE: LibreOffice not found on PATH — any legacy .doc/.ppt/.xls "
            "files will be skipped and flagged for manual review. Install it with "
            "'sudo apt-get install libreoffice' (Linux) or 'brew install libreoffice' (Mac) "
            "if you need those converted too.\n"
        )

    print("[docling] Building conversion pipelines (downloads OCR models on first run)...")
    fast_converter, ocr_heavy_converter = build_docling_converters()

    with tempfile.TemporaryDirectory(prefix="docling_scratch_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        for i, doc_entry in enumerate(pending, start=1):
            url = doc_entry["url"]
            report = convert_one_document(
                doc_entry, docs_output_dir, fast_converter, ocr_heavy_converter, tmp_dir
            )
            report_by_url[url] = report
            save_json_file(report_file, list(report_by_url.values()))

            status_label = {"ok": "OK", "needs_review": "REVIEW", "failed": "FAIL"}.get(
                report["status"], report["status"].upper()
            )
            engine_note = f" [{report['engine_used']}]" if report.get("engine_used") else ""
            error_note = f"  -> {report['error']}" if report.get("error") else ""
            print(f"[docling {i}/{len(pending)}] {status_label}{engine_note} {url}{error_note}")

    all_reports = list(report_by_url.values())
    ok_count = sum(1 for r in all_reports if r["status"] == "ok")
    review_count = sum(1 for r in all_reports if r["status"] == "needs_review")
    failed_count = sum(1 for r in all_reports if r["status"] == "failed")
    ocr_heavy_count = sum(1 for r in all_reports if r.get("engine_used") == "ocr_heavy")

    needing_review = [r for r in all_reports if r["status"] in ("needs_review", "failed")]
    save_json_file(review_file, needing_review)

    print("\n" + "=" * 70)
    print("DOCLING CONVERSION SUMMARY")
    print("=" * 70)
    print(f"Converted cleanly       : {ok_count}")
    print(f"Converted, needs review : {review_count}  (low confidence / thin text — check these)")
    print(f"Failed entirely         : {failed_count}")
    print(f"Needed OCR escalation   : {ocr_heavy_count}  (fast pass wasn't good enough)")
    print(f"Full report             : {report_file}")
    print(f"Needs-attention list    : {review_file}")
    print("=" * 70)


# ------------------------------------------------------------------------
# COMMAND-LINE ENTRY POINT
# ------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Deep-crawl a college website into clean Markdown for a RAG chatbot."
    )
    parser.add_argument(
        "--url", required=True, help="Homepage URL of the college website, e.g. https://www.college.edu.in"
    )
    parser.add_argument(
        "--output", default="./scraped_data", help="Folder to save results into (default: ./scraped_data)"
    )
    parser.add_argument(
        "--max-pages", type=int, default=500, help="Safety cap on total pages to crawl (default: 500)"
    )
    parser.add_argument(
        "--max-depth", type=int, default=6, help="How many 'clicks' deep from the homepage to go (default: 6)"
    )
    parser.add_argument(
        "--concurrency", type=int, default=5, help="How many pages to fetch at once (default: 5, be polite!)"
    )
    parser.add_argument(
        "--with-docling",
        action="store_true",
        help="After crawling, also run Docling on every discovered PDF/DOCX/XLSX/PPTX (requires: pip install docling).",
    )
    parser.add_argument(
        "--no-sitemap",
        action="store_true",
        help="Skip sitemap.xml discovery entirely and rely only on link-following (old behaviour).",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    sitemap_html_urls = []
    if not args.no_sitemap:
        print(f"\n[sitemap] Looking for a sitemap at {urlparse(args.url).netloc} ...")
        sitemap_urls = get_all_sitemap_urls(args.url)
        if sitemap_urls:
            sitemap_docs = [u for u in sitemap_urls if is_document_url(u)]
            sitemap_html_urls = [u for u in sitemap_urls if not is_document_url(u)]
            print(f"[sitemap] {len(sitemap_urls)} total URLs -> "
                  f"{len(sitemap_html_urls)} pages, {len(sitemap_docs)} documents")

            # Merge sitemap-discovered documents straight into
            # pdf_and_document_urls.json now, before the crawl even starts —
            # no need to "discover" a document link Docling will use later.
            documents_file = output_dir / "pdf_and_document_urls.json"
            documents_found = load_json_file(documents_file, default=[])
            documents_seen_urls = {doc["url"] for doc in documents_found}
            added = 0
            for doc_url in sitemap_docs:
                if doc_url not in documents_seen_urls:
                    documents_seen_urls.add(doc_url)
                    documents_found.append(
                        {"url": doc_url, "found_on_page": "sitemap.xml", "link_text": ""}
                    )
                    added += 1
            if added:
                save_json_file(documents_file, documents_found)
                print(f"[sitemap] Added {added} new document URLs from the sitemap.")
        else:
            print("[sitemap] No sitemap.xml found (or it was empty) — relying on link-following only.")

    asyncio.run(
        crawl_college_site(
            start_url=args.url,
            output_dir=output_dir,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            concurrency=args.concurrency,
            sitemap_html_urls=sitemap_html_urls,
        )
    )

    if args.with_docling:
        run_docling_pass(output_dir)


if __name__ == "__main__":
    main()