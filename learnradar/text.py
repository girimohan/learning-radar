from __future__ import annotations

import datetime as dt
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def strip_html(s: str | None) -> str:
    s = _TAG.sub(" ", s or "")
    return _SPACE.sub(" ", html.unescape(s)).strip()


def clip(s: str, n: int = 220) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:-") + "…"


def pick_lang(d: dict | None, *order: str) -> str:
    """First non-empty value of a {"en": ..., "fi": ...} dict, in the given language order."""
    d = d or {}
    for k in order or ("en", "fi", "sv"):
        v = (d.get(k) or "").strip()
        if v:
            return v
    return next((v.strip() for v in d.values() if isinstance(v, str) and v.strip()), "")


_WORD = r"[0-9a-zåäöüßéè+#.]"


def keyword_pattern(k: str) -> re.Pattern:
    """Whole-word match; a trailing * matches any word starting with the keyword."""
    k = k.lower().strip()
    prefix = k.endswith("*")
    body = re.escape(k.rstrip("*"))
    tail = rf"{_WORD}*" if prefix else rf"(?!{_WORD})"
    return re.compile(rf"(?<!{_WORD}){body}{tail}")


_PAT_CACHE: dict[str, re.Pattern] = {}


def has_keyword(text: str, k: str) -> bool:
    p = _PAT_CACHE.get(k)
    if p is None:
        p = _PAT_CACHE[k] = keyword_pattern(k)
    return p.search(text) is not None


def clean_url(url: str) -> str:
    """Drop tracking parameters (utm_*, WT.mc_id)."""
    try:
        p = urlsplit(url)
    except ValueError:
        return url
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not k.lower().startswith("utm_") and k != "WT.mc_id"]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), p.fragment))


_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                        "september", "october", "november", "december"], 1)}
_DATE_TEXT = re.compile(r"(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|"
                        r"november|december)\s+(\d{4})", re.I)


def parse_text_date(s: str | None) -> str:
    """'Register by 31 October 2026 + 1 more' -> '2026-10-31'. ISO dates pass through. '' when none."""
    s = s or ""
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", s)
    if m:
        return m.group(0)
    m = _DATE_TEXT.search(s)
    if not m:
        return ""
    try:
        return dt.date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
    except ValueError:
        return ""


def norm_title(s: str) -> str:
    return re.sub(r"[^0-9a-zåäö]+", " ", s.lower()).strip()
