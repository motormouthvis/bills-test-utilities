"""
wikipediaApiV9.py
=================

Purpose
-------
Fetch a **small number** of Wikipedia article sections quickly for read-aloud or
preview scenarios. Compared to scraping the whole article or iterating every TOC
entry (see wikipediaApiV8), this module:

    * Makes **one** `parse` + `sections` request to learn all section IDs.
    * Makes **one** `parse` + `text` request for the **introduction** (section ``0``)
      plus **one** such request **per configured topic keyword** matched from the TOC
      (typically introduction + History + Geography).
    * Optionally truncates each section to the first N sentences via NLTK.
    * Reuses one HTTP Session (keep-alive) across calls.

Design notes
------------
English Wikipedia APIs require a descriptive User-Agent string; Wikimedia commonly
issues HTTP 403 to generic/default clients. Headers are centralized in
`WIKIPEDIA_REQUEST_HEADERS`.

MediaWiki TOC entries expose a numeric **section index** (string) distinct from the
printed outline number (“1”, “2.1”, …). API calls **must use that index**, not the
outline number—this script reads `sections[].index` from the TOC response.

The article **introduction** (lead text before the first heading) is requested with
section index ``"0"``; it is not resolved via the TOC.

`section_topics` lists **substring** patterns matched case-insensitively against TOC
titles. The **first** match wins for each topic in list order (“History” beats
“The Florida Highwaymen” if you mistakenly put a generic keyword).

Dependencies
-----------
    requests, bs4/lxml (BeautifulSoup backend), nltk (+ punkt tokenizer data).

Sentence clipping uses ``nltk.tokenize.sent_tokenize``. If NLTK warns about punkt:
    >>> import nltk; nltk.download("punkt_tab")

This mirrors other Motormouth wiki utilities that depend on Punkt-like models.
"""

# ---------------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------------
import re
import sys
import unicodedata

# ---------------------------------------------------------------------------
# Third party
# ---------------------------------------------------------------------------
import requests  # synchronous HTTP client; Session used for TCP reuse below
from bs4 import BeautifulSoup  # parses HTML-ish section bodies from the parse API

# NLTK tokenizer: statistically aware sentence splitting (preferred over naive
# "split on period" hacks that break on "St.", "Dr.", "approx.", decimals, …).
from nltk.tokenize import sent_tokenize

# ---------------------------------------------------------------------------
# UTF-8 stdio on Windows (console code pages often mismatched otherwise)
# ---------------------------------------------------------------------------
sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# HTTP compliance: Wikimedia User-Agent requirement
#
# Wikimedia forbids unidentified scripts; descriptive UA + etiquette link reduces
# 403 surprises. Keep this aligned with sibling modules (wikipediaApiV7/V8).
# ---------------------------------------------------------------------------
WIKIPEDIA_REQUEST_HEADERS = {
    "User-Agent": (
        "MotormouthLocalWiki/1.0 "
        "(Wikipedia/MediaWiki script; Python; +https://www.mediawiki.org/wiki/API:Etiquette)"
    ),
}

# ---------------------------------------------------------------------------
# Post-processing: regex pairs [pattern, replacement]
#
# Wikipedia HTML plain-text still carries artifacts (IPA, metric parentheticals,
# "[edit]" junk, pronunciation guides). These patterns strip or normalize text so
# TTS / VUI output is smoother. Mirrors the list pattern used in wikipediaApiV8 /
# GetWikipediaInfo in V7; keep edits in sync if you change pronunciation policy.
#
# Order matters slightly: heavier “delete rest of page” patterns should stay where
# they won’t shred legitimate prose (see Preview-of-references line).
# ---------------------------------------------------------------------------
replacement_character_strings = [
    [r"\(\w{1}\)", ""],
    [r"\(.{1,12}km\)", ""],
    [r"\(\d{1,4}.{1,7}\sm\)", ""],
    [r"\[edit\]", ""],
    [r"\sel\.", " elevation"],
    [r"\(.{1,12}km2\)", ""],
    [r"\[\d{0,3}\]", ""],
    [r"\(\d{0,2}\)", ""],
    [r"\d{1,3}°.{0,80}-\d{1,3}\.\d{1,7}.{1}", ""],
    [r"Preview of references(.|\n)*", ""],
    [r"\(.{1,8}°C\)", ""],
    [r"\(.{1,12}mm\)", ""],
    [r"\s,", ","],
    [r"(\s|\n){2,200}", " "],
    [r"\(CDP\)\s", " "],
    [r"\(.*\(listen\).*\)\s", ""],
    [r"\(.*[A-Z]+[-]{1}[a-z]+.*\)\s", ""],
]


def replace_char_strings(text_to_scan, rules):
    """
    Apply a list of (regex, replacement_string) tuples in sequence.

    Args:
        text_to_scan: raw string pulled from markup (paragraph or whole section).
        rules: iterable of two-element sequences; typical source is the module-level
            ``replacement_character_strings`` list above.

    Returns:
        The same string conceptually; each rule mutates sequentially.
    """
    for pattern, repl in rules:
        text_to_scan = re.sub(pattern, repl, text_to_scan)
    return text_to_scan


def fetch_toc_list(wiki_page_name, session=None):
    """
    Retrieve structured table-of-contents rows for ``wiki_page_name``.

    Hits:
        GET https://en.wikipedia.org/w/api.php
        action=parse&prop=sections&format=json&page=<title>

    Args:
        wiki_page_name: article title exactly as Wikipedia expects in API calls,
            e.g. ``"Fort_Pierce,_Florida"`` with underscores—not the pretty URL slug
            variant that omits commas unless the API accepts it (underscore form is safest).
        session: optional ``requests.Session`` for connection reuse with section fetches;
            ``None`` falls back to the ``requests`` module top-level helpers.

    Returns:
        Tuple ``(toc_list, status_code-ish)``.
        * On success: ``toc_list`` is a list of dicts with keys ``LineNum`` (outline
          number string), ``Descrip`` (TOC line text), ``index`` (MediaWiki section id),
          ``toclevel`` (nesting depth, 1 = top-level §).
        * On failure: ``[]`` plus the HTTP status or ``400`` for JSON/parse failures.
          Callers distinguish success with ``toc_code == 200`` convention used in main.

    Important:
        The ``index`` strings are opaque to this script—we pass them verbatim into
        ``get_wikipedia_section_plain_text``. Do **not** substitute ``LineNum``.
    """
    params = {
        "action": "parse",
        "prop": "sections",
        "format": "json",
        "page": wiki_page_name,
    }
    url = "https://en.wikipedia.org/w/api.php"

    # Use session if caller provided one so TLS + TCP handshakes amortize across calls.
    req = session if session is not None else requests
    try:
        r = req.get(url, params=params, headers=WIKIPEDIA_REQUEST_HEADERS, timeout=30)

        # Non-200: surface status; empty list implies caller should abort TOC-driven work.
        if r.status_code != 200:
            return [], r.status_code

        data = r.json()
        sections = data["parse"]["sections"]

        toc_list = []
        for s in sections:
            # Normalize field names slightly for downstream Python code (camel-ish keys).
            toc_list.append(
                {
                    "LineNum": s["number"],  # e.g. "1", "3.2" — display only here
                    "Descrip": s["line"],  # TOC label; substring match targets this
                    "index": s["index"],  # **API section parameter** lives here
                    "toclevel": s["toclevel"],
                }
            )
        return toc_list, 200
    except Exception:
        # Network loss, malformed JSON, missing keys, etc.: treat uniformly as TOC failure.
        return [], 400


def get_wikipedia_section_plain_text(
    wiki_page_name, index, verbose=False, session=None
):
    """
    Retrieve one section body as plaintext-ish HTML soup text with cleanup regexes.

    Hits:
        GET https://en.wikipedia.org/w/api.php
        action=parse&prop=text&format=json&page=<title>&section=<index>
        &contentformat=text/plain

    Wikipedia still returns markup fragments in practice; BeautifulSoup collapses tags
    to strings. Paragraphs accumulate in preference order (`<p>` nodes); sections that
    are pure lists/templates may lack `<p>`—then we grab `soup.get_text()` wholesale.

    Args:
        wiki_page_name: same title encoding rules as TOC fetch (underscores typical).
        index: TOC ``index`` string from fetch_toc_list, **not** the outline LineNum.
        verbose: echo resolved request URL when True—handy debugging rate limits /
            malformed parameters.
        session: shared ``requests.Session`` or ``None``.

    Returns:
        Quadruple::
            (section_final_text,
             section_para_list,  # paragraphs collected (callers ignore in V9 main)
             api_response_code,  # 200 success, else HTTP code or 400 on parse fail
             no_paragraph_found_flag)  # True when only fallback get_text() path ran

    Error contract:
        On HTTP errors or JSON issues, first element is a short human error string;
        call sites should not run sentence tokenizers on that path.
    """
    section_final_text = ""
    section_para_list = []
    no_paragraph_found_flag = True

    # MediaWiki boolean-like parameters: empty string often means "true" for flags;
    # keep sectionpreview/preview empty as in production V7/V8 calls.
    params = {
        "action": "parse",
        "prop": "text",
        "format": "json",
        "page": wiki_page_name,
        "section": index,
        "contentformat": "text/plain",
        "sectionpreview": "",
        "preview": "",
    }
    url = "https://en.wikipedia.org/w/api.php"
    req = session if session is not None else requests
    api_response = req.get(
        url, params=params, headers=WIKIPEDIA_REQUEST_HEADERS, timeout=30
    )
    api_response_code = api_response.status_code

    if verbose:
        print(api_response.url)

    if api_response_code != 200:
        return (
            "No Wikipedia data is available for this topic",
            section_para_list,
            api_response_code,
            True,
        )

    try:
        # Star key is literal per MediaWiki JSON shape: {"parse":{"text":{"*":"..."}}}
        result = api_response.json()["parse"]["text"]["*"]
        soup = BeautifulSoup(result, features="lxml")

        # Primary path: concatenate visible paragraph text in document order.
        for paragraph in soup.find_all("p"):
            soup_text = paragraph.text
            clean_text = replace_char_strings(
                soup_text, replacement_character_strings
            )
            clean_text = unicodedata.normalize("NFKD", clean_text)
            section_para_list.append(clean_text)
            section_final_text += clean_text
            no_paragraph_found_flag = False

        if no_paragraph_found_flag:
            # Fallback: infobox-only / list-heavy sections may have no <p>.
            text = soup.get_text()
            clean_text = replace_char_strings(text, replacement_character_strings)
            clean_text = unicodedata.normalize("NFKD", clean_text)
            section_final_text = clean_text
            section_para_list.append(clean_text)

        return section_final_text, section_para_list, 200, no_paragraph_found_flag
    except Exception:
        return "No Wikipedia data is available for this topic", section_para_list, 400, True


def first_toc_match(toc_list, keyword):
    """
    Walk TOC rows in order; return the first section whose title contains ``keyword``.

    Matching is **substring**, case-insensitive: ``"geo"`` matches ``"Geography"``.
    Be intentional with ``section_topics``—overly short tokens may false-positive
    (rare for "history" / "economy" but possible for "art").

    Args:
        toc_list: list of dicts from ``fetch_toc_list`` (skips non-dict entries defensively).
        keyword: user-configured topic token from ``section_topics`` in main.

    Returns:
        ``(section_index, display_title)`` or ``(None, None)`` if no row matches.
    """
    kw = keyword.lower()
    for item in toc_list:
        if not isinstance(item, dict):
            # Defensive: error-handling paths elsewhere may stuff strings into lists;
            # keep robust if this helper is reused outside the happy path.
            continue
        if kw in item["Descrip"].lower():
            return item["index"], item["Descrip"]
    return None, None


def clip_to_max_sentences(text, max_sentences):
    """
    Limit ``text`` to the first ``max_sentences`` NLTK tokenized sentences.

    Args:
        text: full section body after cleanup (should not be an error placeholder string).
        max_sentences: positive int applies cap; **0 or negative** disables clipping and
            returns the original string whole—useful for debugging long sections.

    Returns:
        Space-joined sentence string. If fewer sentences exist than the cap, returns
        all of them without padding.

    Note:
        ``sent_tokenize`` incurs small CPU cost but avoids naive period-splitting bugs.
    """
    if not text or not str(text).strip():
        return text
    if max_sentences <= 0:
        return text
    sentences = sent_tokenize(text.strip())
    if len(sentences) <= max_sentences:
        return " ".join(sentences)
    return " ".join(sentences[:max_sentences])


# ---------------------------------------------------------------------------
# Script entry point: wire configuration, drive I/O, print human-readable blocks
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # --- Article selection ---------------------------------------------------
    # Title string as accepted by the English Wikipedia API (underscores for spaces
    # in compound names is the conventional stable form in this codebase).
    wikipedia_page_name = "Fort_Pierce,_Florida"

    # --- Output shaping ------------------------------------------------------
    # Cap printed sentences per block (introduction, then each TOC topic). Set to 0
    # (or any non-positive) to dump the entire cleaned body without NLTK truncation.
    max_sentences_to_display = 5

    # --- Which sections to pull (after introduction) -------------------------
    # Introduction uses MediaWiki section index "0" (lead before first heading).
    # Each keyword here is matched as a substring against TOC titles, top-down.
    # One keyword == one parse+text request after the intro fetch.
    section_topics = ["history", "geography"]

    # --- HTTP session --------------------------------------------------------
    # Single Session shares cookies/connection pool; headers copied so every request
    # gets the compliant User-Agent without repeating the dict literal at call sites.
    http = requests.Session()
    http.headers.update(WIKIPEDIA_REQUEST_HEADERS)

    # --- Phase 1: discover section indices -----------------------------------
    toc_list, toc_code = fetch_toc_list(wikipedia_page_name, session=http)
    if toc_code != 200:
        # Without a TOC we cannot map friendly names to hidden section ids—fail fast.
        print("Wikipedia TOC request failed; cannot resolve section indices.")
        sys.exit(1)

    # --- Phase 2: introduction (section 0) + TOC-driven sections -----------
    fetch_plan = [("0", "Introduction", None)]
    for keyword in section_topics:
        sec_index, title = first_toc_match(toc_list, keyword)
        fetch_plan.append((sec_index, title or keyword.upper(), keyword))

    for sec_index, heading, keyword in fetch_plan:
        bar = "=" * 72
        print(f"\n{bar}\n{heading}\n{bar}")

        if sec_index is None:
            print(f'(No TOC section matching "{keyword}")')
            continue

        body, _paras, sec_code, _no_para = get_wikipedia_section_plain_text(
            wikipedia_page_name, sec_index, session=http
        )

        if sec_code == 200 and body and str(body).strip():
            print(clip_to_max_sentences(body, max_sentences_to_display))
        elif sec_code == 200:
            print("(empty section)")
        else:
            print(body)
