#!/usr/bin/env python3
"""Fetch and publish only the reviewed Scout public schema-v1 payload."""

import json
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

SOURCE = "https://project-hub-view.pages.dev/api/scout/current"
MAX_BYTES = 1_000_000
ROOT = {"schemaVersion", "status", "publisher", "scoutVersion", "generatedUtc", "searches", "project", "receivedUtc"}
SEARCH_REQUIRED = {"id", "name", "query", "checkedUtc", "resultCount", "pricing"}
SEARCH_OPTIONAL = {"minimumPrice", "maximumPrice", "bestResult"}
BEST_REQUIRED = {"title", "price", "condition", "source", "url", "buying", "lastSeenUtc"}
BEST_OPTIONAL = {"shipping", "deliveredPrice"}
PRICING = {"calculatorVersion", "target", "freshReferenceSources", "currentConfidence", "coverage30", "validDays30", "coverage90", "validDays90", "trend"}
BLOCKED_KEY = re.compile(r"user(name)?|home|profile|postal|zip|store|cookie|session|auth|token|secret|password|credential|email|ebay|project.?hub|machine|network|host(name)?|ip.?address|mac.?address", re.I)
BLOCKED_VALUE = re.compile(r"(?<![A-Za-z])[a-z]:[\\/]|\\\\|/Users/|/home/|%USERPROFILE%|\b(?:bearer|basic)\s+[A-Za-z0-9+/._=-]+|\b(?:token|password|secret|cookie|session|api.?key|authorization)\s*[:=]|\b(?:zip|postal|store|browser profile|username|home directory|project hub)\b|\b[A-Fa-f0-9]{2}(?::[A-Fa-f0-9]{2}){5}\b|\b(?:\d{1,3}\.){3}\d{1,3}\b|\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
REVIEWED_RESULT_HOSTS = {"www.ebay.com", "www.walmart.com", "www.newegg.com"}
BEST_BUY_HOST = "www.bestbuy.com"
BEST_BUY_PRODUCT_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
BEST_BUY_LEGACY_PRODUCT_PATH = re.compile(rf"^/site/{BEST_BUY_PRODUCT_SLUG}/(\d+)\.p$")
BEST_BUY_CURRENT_PRODUCT_PATH = re.compile(rf"^/product/{BEST_BUY_PRODUCT_SLUG}/[A-Z0-9]{{10}}$")


def pairs_unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def keys(value, required, optional=frozenset()):
    if not isinstance(value, dict):
        raise ValueError("expected object")
    missing = required - value.keys()
    extra = value.keys() - required - optional
    if missing or extra:
        raise ValueError(f"schema mismatch: missing={sorted(missing)}, extra={sorted(extra)}")


def string(value, max_length=1000):
    if not isinstance(value, str) or not value or len(value) > max_length or BLOCKED_VALUE.search(value):
        raise ValueError("unsafe or invalid text value")
    if any(ord(char) < 32 for char in value):
        raise ValueError("control character in text")


def number(value):
    if type(value) not in (int, float) or value < 0 or value > 1_000_000_000:
        raise ValueError("invalid nonnegative number")


def timestamp(value):
    string(value, 40)
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)", value):
        raise ValueError("invalid UTC timestamp")


def scan(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if BLOCKED_KEY.search(key) and key not in {"source"}:
                raise ValueError(f"sensitive key: {key}")
            scan(child)
    elif isinstance(value, list):
        for child in value:
            scan(child)
    elif isinstance(value, str):
        string(value)


def result_url(value):
    url = urlsplit(value)
    if url.hostname == BEST_BUY_HOST:
        if url.scheme != "https":
            raise ValueError("unreviewed Best Buy result URL scheme")
        if url.username is not None or url.password is not None:
            raise ValueError("unreviewed Best Buy result URL credentials")
        try:
            port = url.port
        except ValueError as error:
            raise ValueError("unreviewed Best Buy result URL port") from error
        if port is not None:
            raise ValueError("unreviewed Best Buy result URL port")
        if "#" in value:
            raise ValueError("unreviewed Best Buy result URL fragment")

        legacy_match = BEST_BUY_LEGACY_PRODUCT_PATH.fullmatch(url.path)
        current_match = BEST_BUY_CURRENT_PRODUCT_PATH.fullmatch(url.path)
        if not legacy_match and not current_match:
            raise ValueError("unreviewed Best Buy result URL shape")

        if "?" in value:
            query_match = re.fullmatch(r"skuId=(\d+)", url.query)
            if not legacy_match or not query_match:
                raise ValueError("unreviewed Best Buy query parameters")
            if query_match.group(1) != legacy_match.group(1):
                raise ValueError("unreviewed Best Buy result URL shape")
        return

    if url.scheme != "https" or url.hostname not in REVIEWED_RESULT_HOSTS or url.username or url.password or url.query or url.fragment:
        host = url.hostname or "<missing>"
        raise ValueError(f"unreviewed result URL host or structure: {host}")


def validate(payload):
    keys(payload, ROOT)
    if type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1:
        raise ValueError("unexpected schema version")
    for field in ("status", "publisher", "scoutVersion", "project"):
        string(payload[field], 100)
    if payload["publisher"] != "Scout" or payload["project"] != "Scout" or payload["status"] not in {"online", "offline"}:
        raise ValueError("unexpected feed identity/status")
    for field in ("generatedUtc", "receivedUtc"):
        timestamp(payload[field])
    if not isinstance(payload["searches"], list) or len(payload["searches"]) > 1000:
        raise ValueError("invalid searches")
    for search in payload["searches"]:
        keys(search, SEARCH_REQUIRED, SEARCH_OPTIONAL)
        for field in ("id", "name", "query"):
            string(search[field], 500)
        timestamp(search["checkedUtc"])
        number(search["resultCount"])
        for field in ("minimumPrice", "maximumPrice"):
            if field in search:
                number(search[field])
        pricing = search["pricing"]
        keys(pricing, PRICING)
        for field in ("calculatorVersion", "target", "freshReferenceSources", "validDays30", "validDays90"):
            number(pricing[field])
        for field in ("currentConfidence", "coverage30", "coverage90", "trend"):
            string(pricing[field], 100)
        if "bestResult" in search:
            best = search["bestResult"]
            keys(best, BEST_REQUIRED, BEST_OPTIONAL)
            for field in ("title", "condition", "source", "buying"):
                string(best[field])
            for field in ("price", "shipping", "deliveredPrice"):
                if field in best:
                    number(best[field])
            timestamp(best["lastSeenUtc"])
            string(best["url"])
            result_url(best["url"])
    scan(payload)
    return payload


def decode(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError("response too large")
    return validate(json.loads(raw.decode("utf-8"), object_pairs_hook=pairs_unique, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x))))


def fetch():
    request = urllib.request.Request(SOURCE, headers={"User-Agent": "scout-public-feed-mirror/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        raw = response.read(MAX_BYTES + 1)
    return raw


def update(path, fetcher=fetch):
    payload = decode(fetcher())
    content = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if path.exists() and path.read_bytes() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=".scout-", suffix=".tmp", delete=False) as temp:
            temp_name = temp.name
            temp.write(content)
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return True


if __name__ == "__main__":
    try:
        changed = update(Path(__file__).resolve().parent / "scout-current.json")
        print("Scout feed updated" if changed else "Scout feed unchanged")
    except Exception as error:
        print(f"Scout mirror failed: {error}", file=sys.stderr)
        sys.exit(1)
