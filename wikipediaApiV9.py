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

Production plumbing can be: latitude/longitude → **Wikidata entity id** (e.g. from a
commercial place DB) → ``enwiki_underscore_title_from_wikidata_id`` → English
``action=parse`` calls below. The ``__main__`` batch list is ``(Q-id, display name)``
pairs for tests only—the display name is for logs; the API path always uses the
sitelink title resolved from the Q-id.

All ``action=parse`` requests pass ``redirects=1`` so a title like
``Denver,_Colorado`` (a redirect) resolves to the canonical article (``Denver``);
otherwise ``prop=sections`` can return **zero** rows and History/Geography lookups
silently fail even though the destination article has those sections.

MediaWiki TOC entries expose a numeric **section index** (string) distinct from the
printed outline number (“1”, “2.1”, …). API calls **must use that index**, not the
outline number—this script reads `sections[].index` from the TOC response.

The article **introduction** (lead text before the first heading) is requested with
section index ``"0"``; it is not resolved via the TOC.

`section_topics` lists **keywords** matched **exactly** to a TOC title first, then
as a **non-embedded** substring (so ``history`` does not match **Prehistory**).
The **first** qualifying row wins in document order.

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
import random
import re
import sys
import time
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
        "redirects": 1,
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
        &contentformat=text/plain&redirects=1

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
        "redirects": 1,
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
    Walk TOC rows in order and map ``keyword`` to a section index.

    Matching order:

    1. **Exact** title (case-insensitive, stripped), e.g. ``"history"`` → ``"History"``.
    2. **Substring** occurrences of ``keyword`` in the title, **skipping** matches
       glued inside a longer word. That avoids ``"history"`` matching **Prehistory**
       before **History**, which produced sparse HTML and nonsense sentence clips.

    Prefix matches still work: ``"geo"`` can match ``"Geography"`` (no letter before
    ``"geo"``).

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
        desc_strip = item["Descrip"].strip().lower()
        if desc_strip == kw:
            return item["index"], item["Descrip"]

    for item in toc_list:
        if not isinstance(item, dict):
            continue
        desc = item["Descrip"]
        dl = desc.lower()
        start = 0
        while True:
            i = dl.find(kw, start)
            if i == -1:
                break
            embedded_left = i > 0 and dl[i - 1].isalpha()
            if not embedded_left:
                return item["index"], item["Descrip"]
            start = i + 1
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
        Whitespace is collapsed first so stray newlines do not confuse the tokenizer.
        Sentences with no letters (pure punctuation) are skipped when applying the cap.
    """
    if not text or not str(text).strip():
        return text
    if max_sentences <= 0:
        return text
    collapsed = re.sub(r"\s+", " ", str(text).strip())
    sentences = sent_tokenize(collapsed)
    sentences = [s for s in sentences if any(ch.isalpha() for ch in s)]
    if not sentences:
        return collapsed
    if len(sentences) <= max_sentences:
        return " ".join(sentences)
    return " ".join(sentences[:max_sentences])


def enwiki_underscore_title_from_wikidata_id(wikidata_id, session=None):
    """
    Resolve a Wikidata Q-id to the English Wikipedia article title (underscore form).

    Intended flow: lat/lon → Wikidata id (e.g. from a simplemaps-style DB) → this
    helper → ``fetch_toc_list`` / ``get_wikipedia_section_plain_text``.
    """
    raw = str(wikidata_id).strip()
    m = re.match(r"^Q?(\d+)$", raw, re.I)
    if not m:
        return None
    qid = "Q" + m.group(1)
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "format": "json",
        "props": "sitelinks",
    }
    url = "https://www.wikidata.org/w/api.php"
    req = session if session is not None else requests
    try:
        r = req.get(url, params=params, headers=WIKIPEDIA_REQUEST_HEADERS, timeout=30)
        if r.status_code != 200:
            return None
        ent = r.json().get("entities", {}).get(qid)
        if not ent or ent.get("missing"):
            return None
        title = ent.get("sitelinks", {}).get("enwiki", {}).get("title")
        if not title:
            return None
        return title.replace(" ", "_")
    except Exception:
        return None


def preview_wikipedia_article(
    wiki_page_name,
    session,
    section_topics,
    max_sentences_to_display,
    *,
    verbose=True,
):
    """
    Fetch the article introduction (section ``0``) plus each ``section_topics`` TOC
    match; optionally print blocks. Returns a small status dict for batch runs.

    Returns:
        dict with keys: ``page``, ``ok`` (bool), ``notes`` (list of str).
    """
    notes = []
    toc_list, toc_code = fetch_toc_list(wiki_page_name, session=session)
    if toc_code != 200:
        msg = f"TOC request failed (HTTP {toc_code})"
        if verbose:
            print(msg)
        return {"page": wiki_page_name, "ok": False, "notes": [msg]}

    fetch_plan = [("0", "Introduction", None)]
    for keyword in section_topics:
        sec_index, title = first_toc_match(toc_list, keyword)
        fetch_plan.append((sec_index, title or keyword.upper(), keyword))

    intro_ok = False
    section_http_error = False

    for sec_index, heading, keyword in fetch_plan:
        if verbose:
            bar = "=" * 72
            print(f"\n{bar}\n{heading}\n{bar}")

        if sec_index is None:
            notes.append(f'missing section match for {keyword!r}')
            if verbose:
                print(f'(No TOC section matching "{keyword}")')
            continue

        body, _paras, sec_code, _no_para = get_wikipedia_section_plain_text(
            wiki_page_name, sec_index, session=session
        )

        if sec_code == 200 and body and str(body).strip():
            clipped = clip_to_max_sentences(body, max_sentences_to_display)
            if verbose:
                print(clipped)
            if heading == "Introduction" and any(ch.isalpha() for ch in clipped):
                intro_ok = True
        elif sec_code == 200:
            notes.append(f"{heading}: empty")
            if verbose:
                print("(empty section)")
        else:
            section_http_error = True
            notes.append(f"{heading}: fetch failed ({body!s:.120})")
            if verbose:
                print(body)

    ok = intro_ok and not section_http_error
    if not intro_ok:
        notes.append("introduction: no usable text after clip")

    return {"page": wiki_page_name, "ok": ok, "notes": notes}


# ---------------------------------------------------------------------------
# Script entry point: wire configuration, drive I/O, print human-readable blocks
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    WIKIDATA_TEST_CITIES = [
        ('Q60', 'New York City'),
        ('Q65', 'Los Angeles'),
        ('Q1297', 'Chicago'),
        ('Q16555', 'Houston'),
        ('Q16556', 'Phoenix, Arizona'),
        ('Q1345', 'Philadelphia'),
        ('Q975', 'San Antonio'),
        ('Q16552', 'San Diego'),
        ('Q16557', 'Dallas'),
        ('Q16568', 'Jacksonville, Florida'),
        ('Q16558', 'Fort Worth, Texas'),
        ('Q16553', 'San Jose, California'),
        ('Q16559', 'Austin, Texas'),
        ('Q16565', 'Charlotte, North Carolina'),
        ('Q16567', 'Columbus, Ohio'),
        ('Q6346', 'Indianapolis'),
        ('Q62', 'San Francisco'),
        ('Q5083', 'Seattle'),
        ('Q16554', 'Denver'),
        ('Q34863', 'Oklahoma City'),
        ('Q23197', 'Nashville, Tennessee'),
        ('Q61', 'Washington, D.C.'),
        ('Q16562', 'El Paso, Texas'),
        ('Q23768', 'Las Vegas'),
        ('Q100', 'Boston'),
        ('Q12439', 'Detroit'),
        ('Q43668', 'Louisville, Kentucky'),
        ('Q6106', 'Portland, Oregon'),
        ('Q16563', 'Memphis, Tennessee'),
        ('Q5092', 'Baltimore'),
        ('Q37836', 'Milwaukee'),
        ('Q34804', 'Albuquerque, New Mexico'),
        ('Q18575', 'Tucson, Arizona'),
        ('Q43301', 'Fresno, California'),
        ('Q18013', 'Sacramento, California'),
        ('Q23556', 'Atlanta'),
        ('Q49261', 'Mesa, Arizona'),
        ('Q41819', 'Kansas City, Missouri'),
        ('Q41087', 'Raleigh, North Carolina'),
        ('Q49258', 'Colorado Springs, Colorado'),
        ('Q43199', 'Omaha, Nebraska'),
        ('Q8652', 'Miami'),
        ('Q49259', 'Virginia Beach, Virginia'),
        ('Q16739', 'Long Beach, California'),
        ('Q17042', 'Oakland, California'),
        ('Q36091', 'Minneapolis'),
        ('Q49256', 'Bakersfield, California'),
        ('Q44989', 'Tulsa, Oklahoma'),
        ('Q49255', 'Tampa, Florida'),
        ('Q17943', 'Arlington, Texas'),
        ('Q49246', 'Aurora, Colorado'),
        ('Q49266', 'Wichita, Kansas'),
        ('Q37320', 'Cleveland'),
        ('Q34404', 'New Orleans'),
        ('Q49267', 'Henderson, Nevada'),
        ('Q18094', 'Honolulu'),
        ('Q49247', 'Anaheim, California'),
        ('Q49233', 'Orlando, Florida'),
        ('Q49241', 'Lexington, Kentucky'),
        ('Q49240', 'Stockton, California'),
        ('Q49243', 'Riverside, California'),
        ('Q49219', 'Irvine, California'),
        ('Q49242', 'Corpus Christi, Texas'),
        ('Q25395', 'Newark, New Jersey'),
        ('Q49244', 'Santa Ana, California'),
        ('Q43196', 'Cincinnati'),
        ('Q1342', 'Pittsburgh'),
        ('Q28848', 'Saint Paul, Minnesota'),
        ('Q49238', 'Greensboro, North Carolina'),
        ('Q26339', 'Jersey City, New Jersey'),
        ('Q49229', 'Durham, North Carolina'),
        ('Q28260', 'Lincoln, Nebraska'),
        ('Q143782', 'North Las Vegas, Nevada'),
        ('Q51689', 'Plano, Texas'),
        ('Q39450', 'Anchorage, Alaska'),
        ('Q51684', 'Gilbert, Arizona'),
        ('Q43788', 'Madison, Wisconsin'),
        ('Q49225', 'Reno, Nevada'),
        ('Q49272', 'Chandler, Arizona'),
        ('Q38022', 'St. Louis'),
        ('Q49270', 'Chula Vista, California'),
        ('Q40435', 'Buffalo, New York'),
        ('Q49268', 'Fort Wayne, Indiana'),
        ('Q49273', 'Lubbock, Texas'),
        ('Q49236', 'St. Petersburg, Florida'),
        ('Q49239', 'Toledo, Ohio'),
        ('Q16868', 'Laredo, Texas'),
        ('Q667749', 'Port St. Lucie, Florida'),
        ('Q51682', 'Glendale, Arizona'),
        ('Q51690', 'Irving, Texas'),
        ('Q49227', 'Winston-Salem, North Carolina'),
        ('Q49222', 'Chesapeake, Virginia'),
        ('Q49274', 'Garland, Texas'),
        ('Q49221', 'Scottsdale, Arizona'),
        ('Q35775', 'Boise, Idaho'),
        ('Q49276', 'Hialeah, Florida'),
        ('Q128269', 'Frisco, Texas'),
        ('Q43421', 'Richmond, Virginia'),
        ('Q462789', 'Cape Coral, Florida'),
        ('Q49231', 'Norfolk, Virginia'),
        ('Q187805', 'Spokane, Washington'),
        ('Q79860', 'Huntsville, Alabama'),
        ('Q491132', 'Santa Clarita, California'),
        ('Q199797', 'Tacoma, Washington'),
        ('Q49220', 'Fremont, California'),
        ('Q51697', 'McKinney, Texas'),
        ('Q486168', 'San Bernardino, California'),
        ('Q28218', 'Baton Rouge, Louisiana'),
        ('Q204561', 'Modesto, California'),
        ('Q491128', 'Fontana, California'),
        ('Q23337', 'Salt Lake City'),
        ('Q494720', 'Moreno Valley, California'),
        ('Q39709', 'Des Moines, Iowa'),
        ('Q49179', 'Worcester, Massachusetts'),
        ('Q128114', 'Yonkers, New York'),
        ('Q331104', 'Fayetteville, North Carolina'),
        ('Q131335', 'Sioux Falls, South Dakota'),
        ('Q51694', 'Grand Prairie, Texas'),
        ('Q49218', 'Rochester, New York'),
        ('Q37043', 'Tallahassee, Florida'),
        ('Q33405', 'Little Rock, Arkansas'),
        ('Q51691', 'Amarillo, Texas'),
        ('Q500481', 'Overland Park, Kansas'),
        ('Q239870', 'Columbus, Georgia'),
        ('Q181962', 'Augusta, Georgia'),
        ('Q79875', 'Mobile, Alabama'),
        ('Q209338', 'Oxnard, California'),
        ('Q184587', 'Grand Rapids, Michigan'),
        ('Q51686', 'Peoria, Arizona'),
        ('Q234053', 'Vancouver, Washington'),
        ('Q185582', 'Knoxville, Tennessee'),
        ('Q79867', 'Birmingham, Alabama'),
        ('Q29364', 'Montgomery, Alabama'),
        ('Q18383', 'Providence, Rhode Island'),
        ('Q5917', 'Huntington Beach, California'),
        ('Q51693', 'Brownsville, Texas'),
        ('Q186702', 'Chattanooga, Tennessee'),
        ('Q165972', 'Fort Lauderdale, Florida'),
        ('Q51685', 'Tempe, Arizona'),
        ('Q163132', 'Akron, Ohio'),
        ('Q485716', 'Glendale, California'),
        ('Q328941', 'Clarksville, Tennessee'),
        ('Q488134', 'Ontario, California'),
        ('Q335017', 'Newport News, Virginia'),
        ('Q671314', 'Elk Grove, California'),
        ('Q852665', 'Cary, North Carolina'),
        ('Q22595', 'Aurora, Illinois'),
        ('Q43919', 'Salem, Oregon'),
        ('Q370972', 'Pembroke Pines, Florida'),
        ('Q171224', 'Eugene, Oregon'),
        ('Q212991', 'Santa Rosa, California'),
        ('Q495365', 'Rancho Cucamonga, California'),
        ('Q80517', 'Shreveport, Louisiana'),
        ('Q50054', 'Garden Grove, California'),
        ('Q488924', 'Oceanside, California'),
        ('Q490732', 'Fort Collins, Colorado'),
        ('Q135615', 'Springfield, Missouri'),
        ('Q501766', 'Murfreesboro, Tennessee'),
        ('Q51687', 'Surprise, Arizona'),
        ('Q494711', 'Lancaster, California'),
        ('Q128306', 'Denton, Texas'),
        ('Q491340', 'Roseville, California'),
        ('Q488940', 'Palmdale, California'),
        ('Q494707', 'Corona, California'),
        ('Q488125', 'Salinas, California'),
        ('Q128228', 'Killeen, Texas'),
        ('Q138391', 'Paterson, New Jersey'),
        ('Q88', 'Alexandria, Virginia'),
        ('Q234453', 'Hollywood, Florida'),
        ('Q491114', 'Hayward, California'),
        ('Q47716', 'Charleston, South Carolina'),
        ('Q219656', 'Macon, Georgia'),
        ('Q462804', 'Lakewood, Colorado'),
        ('Q208459', 'Sunnyvale, California'),
        ('Q486472', 'Kansas City, Kansas'),
        ('Q49158', 'Springfield, Massachusetts'),
        ('Q214164', 'Bellevue, Washington'),
        ('Q243007', 'Naperville, Illinois'),
        ('Q40345', 'Joliet, Illinois'),
        ('Q49174', 'Bridgeport, Connecticut'),
        ('Q51696', 'Mesquite, Texas'),
        ('Q51695', 'Pasadena, Texas'),
        ('Q593022', 'Olathe, Kansas'),
        ('Q372454', 'Escondido, California'),
        ('Q83813', 'Savannah, Georgia'),
        ('Q51698', 'McAllen, Texas'),
        ('Q487999', 'Gainesville, Florida'),
        ('Q486868', 'Pomona, California'),
        ('Q233892', 'Rockford, Illinois'),
        ('Q579761', 'Thornton, Colorado'),
        ('Q128244', 'Waco, Texas'),
        ('Q495373', 'Visalia, California'),
        ('Q128069', 'Syracuse, New York'),
        ('Q38453', 'Columbia, South Carolina'),
        ('Q128321', 'Midland, Texas'),
        ('Q745168', 'Miramar, Florida'),
        ('Q816809', 'Palm Bay, Florida'),
        ('Q1088792', 'Lakewood Township, New Jersey'),
        ('Q28198', 'Jackson, Mississippi'),
        ('Q505557', 'Coral Springs, Florida'),
        ('Q495353', 'Victorville, California'),
        ('Q138311', 'Elizabeth, New Jersey'),
        ('Q494723', 'Fullerton, California'),
        ('Q1085274', 'Meridian, Idaho'),
        ('Q489197', 'Torrance, California'),
        ('Q49169', 'Stamford, Connecticut'),
        ('Q52465', 'West Valley City, Utah'),
        ('Q491350', 'Orange, California'),
        ('Q486439', 'Cedar Rapids, Iowa'),
        ('Q499401', 'Warren, Michigan'),
        ('Q342043', 'Hampton, Virginia'),
        ('Q49145', 'New Haven, Connecticut'),
        ('Q485176', 'Pasadena, California'),
        ('Q844008', 'Kent, Washington'),
        ('Q34739', 'Dayton, Ohio'),
        ('Q34109', 'Fargo, North Dakota'),
        ('Q26495', 'Lewisville, Texas'),
        ('Q128261', 'Carrollton, Texas'),
        ('Q128334', 'Round Rock, Texas'),
        ('Q927243', 'Sterling Heights, Michigan'),
        ('Q159260', 'Santa Clara, California'),
        ('Q40347', 'Norman, Oklahoma'),
        ('Q59670', 'Columbia, Missouri'),
        ('Q128295', 'Abilene, Texas'),
        ('Q982550', 'Pearland, Texas'),
        ('Q203263', 'Athens, Georgia'),
        ('Q695511', 'College Station, Texas'),
        ('Q303794', 'Clovis, California'),
        ('Q163749', 'West Palm Beach, Florida'),
        ('Q142811', 'Allentown, Pennsylvania'),
        ('Q847538', 'North Charleston, South Carolina'),
        ('Q323414', 'Simi Valley, California'),
        ('Q41057', 'Topeka, Kansas'),
        ('Q659400', 'Wilmington, North Carolina'),
        ('Q639452', 'Lakeland, Florida'),
        ('Q208447', 'Thousand Oaks, California'),
        ('Q490441', 'Concord, California'),
        ('Q486479', 'Rochester, Minnesota'),
        ('Q208445', 'Vallejo, California'),
        ('Q485172', 'Ann Arbor, Michigan'),
        ('Q835810', 'Broken Arrow, Oklahoma'),
        ('Q323432', 'Fairfield, California'),
        ('Q128891', 'Lafayette, Louisiana'),
        ('Q33486', 'Hartford, Connecticut'),
        ('Q590849', 'Arvada, Colorado'),
        ('Q484678', 'Berkeley, California'),
        ('Q24603', 'Independence, Missouri'),
        ('Q166304', 'Billings, Montana'),
        ('Q49111', 'Cambridge, Massachusetts'),
        ('Q49162', 'Lowell, Massachusetts'),
    ]

    max_sentences_to_display = 5

    section_topics = ["history", "geography"]

    # ``"errors_only"`` → one status line per city; details only on FAIL.
    # ``"full"`` → print Introduction / History / Geography for every city.
    BATCH_SHOW = "errors_only"

    # Subset after optional shuffle: slice(None) | slice(0, 250) | slice(0, 9, 3), etc.
    CITY_TEST_SLICE = slice(0, 250)

    BATCH_SHUFFLE_SEED = None
    BATCH_DELAY_SECONDS = 0.2

    # Debug one entity: e.g. ("Q16554", "Denver")
    SINGLE_WIKIDATA_FIXTURE = None

    city_slice = CITY_TEST_SLICE
    if len(sys.argv) >= 2:
        parts = []
        for a in sys.argv[1:4]:
            try:
                parts.append(int(a))
            except ValueError:
                print(
                    "Usage: wikipediaApiV9.py [stop] | "
                    "wikipediaApiV9.py start stop [step]",
                    file=sys.stderr,
                )
                sys.exit(2)
        if len(parts) == 1:
            n = parts[0]
            city_slice = slice(None) if n <= 0 else slice(0, n)
        elif len(parts) == 2:
            city_slice = slice(parts[0], parts[1])
        else:
            city_slice = slice(parts[0], parts[1], parts[2])

    http = requests.Session()
    http.headers.update(WIKIPEDIA_REQUEST_HEADERS)
    show_full_sections = BATCH_SHOW == "full"

    def _row_label(qid_, name_):
        return f"{name_} ({qid_})"

    if SINGLE_WIKIDATA_FIXTURE is not None:
        _q, _name = SINGLE_WIKIDATA_FIXTURE
        _page = enwiki_underscore_title_from_wikidata_id(_q, session=http)
        if not _page:
            print(f"No en.wikipedia.org sitelink for {_q} ({_name})", file=sys.stderr)
            sys.exit(1)
        preview_wikipedia_article(
            _page,
            http,
            section_topics,
            max_sentences_to_display,
            verbose=show_full_sections,
        )
    else:
        rows = list(WIKIDATA_TEST_CITIES)
        if BATCH_SHUFFLE_SEED is not None:
            random.Random(BATCH_SHUFFLE_SEED).shuffle(rows)
        rows_run = rows[city_slice]
        if not rows_run:
            print("No cities selected (empty slice).", file=sys.stderr)
            sys.exit(1)

        if len(rows_run) == 1:
            _q, _name = rows_run[0]
            _page = enwiki_underscore_title_from_wikidata_id(_q, session=http)
            if not _page:
                print(f"No en.wikipedia.org sitelink for {_q} ({_name})", file=sys.stderr)
                sys.exit(1)
            preview_wikipedia_article(
                _page,
                http,
                section_topics,
                max_sentences_to_display,
                verbose=show_full_sections,
            )
        else:
            print(
                f"Batch: {len(rows_run)} cities | slice {city_slice} | "
                f"show={BATCH_SHOW!r} | delay={BATCH_DELAY_SECONDS}s\n"
            )
            results = []
            for i, (_q, _name) in enumerate(rows_run, start=1):
                label = _row_label(_q, _name)
                _page = enwiki_underscore_title_from_wikidata_id(_q, session=http)
                if not _page:
                    print(
                        f"[{i}/{len(rows_run)}] {label} ... FAIL\n"
                        f"         · no en.wikipedia.org sitelink for {_q}",
                        flush=True,
                    )
                    results.append(
                        {"page": _q, "ok": False, "notes": ["no enwiki sitelink"]}
                    )
                    time.sleep(BATCH_DELAY_SECONDS)
                    continue
                if show_full_sections:
                    bar = "#" * 72
                    print(f"\n{bar}\n[{i}/{len(rows_run)}] {label}\n{bar}")
                else:
                    print(f"[{i}/{len(rows_run)}] {label} ... ", end="", flush=True)
                r = preview_wikipedia_article(
                    _page,
                    http,
                    section_topics,
                    max_sentences_to_display,
                    verbose=show_full_sections,
                )
                r["wikidata_id"] = _q
                r["label"] = _name
                results.append(r)
                if show_full_sections:
                    st = "OK" if r["ok"] else "FAIL"
                    print(f"\n——— [{i}/{len(rows_run)}] {label}: {st} ———\n")
                else:
                    print("OK" if r["ok"] else "FAIL")
                    if not r["ok"]:
                        for note in r["notes"]:
                            print(f"         · {note}")
                time.sleep(BATCH_DELAY_SECONDS)

            ok_n = sum(1 for r in results if r["ok"])
            print(f"\n--- summary: {ok_n}/{len(results)} passed ---")
            failed = [
                f"{r.get('label', '?')} ({r.get('wikidata_id', '?')})"
                for r in results
                if not r["ok"]
            ]
            if failed:
                print("Failed:", "; ".join(failed))
