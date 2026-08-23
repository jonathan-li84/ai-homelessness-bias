#!/usr/bin/env python3
"""Collect homelessness-related headlines from public GDELT GAL files.

This is a project-integrated, restartable version of the supplied collector.
It discovers headline matches only; it does not infer locations or assign CoCs.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "https://storage.googleapis.com/data.gdeltproject.org/gdeltv3/gal"
DEFAULT_TERMS = (
    "homeless",
    "homelessness",
    "unhoused",
    "people experiencing homelessness",
    "homeless population",
    "homeless residents",
)
OUTPUT_COLUMNS = (
    "article_id",
    "date",
    "url",
    "normalized_url",
    "domain",
    "publisher",
    "title",
    "language",
    "author",
    "description",
    "matching_terms",
    "source_dataset",
    "source_file",
    "retrieved_at_utc",
)
TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}


class CollectionError(RuntimeError):
    """Raised when a minute cannot be checked without risking silent data loss."""


@dataclass(frozen=True)
class FetchResult:
    status: str
    source_url: str
    matches: list[dict[str, Any]]
    malformed_records: int = 0


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("dates must use YYYY-MM-DD") from exc


def normalize_url(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    if parts.port and not (
        (parts.scheme.lower() == "http" and parts.port == 80)
        or (parts.scheme.lower() == "https" and parts.port == 443)
    ):
        host = f"{host}:{parts.port}"
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
    ]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), host, path, urlencode(query), ""))


def article_id(url: str) -> str:
    return "gdelt_gal_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def compile_headline_patterns(terms: Sequence[str]) -> list[tuple[str, re.Pattern[str]]]:
    patterns = []
    for raw_term in terms:
        term = " ".join(str(raw_term).split())
        if not term:
            continue
        words = [re.escape(word) for word in term.split()]
        patterns.append((term, re.compile(r"\b" + r"\s+".join(words) + r"\b", re.I)))
    if not patterns:
        raise ValueError("At least one non-empty search term is required.")
    return patterns


def minute_url(base_url: str, timestamp: datetime) -> str:
    filename = timestamp.strftime("%Y%m%d%H%M00.gal.json.gz")
    return f"{base_url.rstrip('/')}/{filename}"


def parse_gal_payload(
    payload: bytes,
    patterns: Sequence[tuple[str, re.Pattern[str]]],
    english_only: bool,
    source_url: str,
) -> tuple[list[dict[str, Any]], int]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as compressed:
            text = compressed.read().decode("utf-8", errors="replace")
    except (OSError, EOFError) as exc:
        raise CollectionError(f"Could not decompress {source_url}: {exc}") from exc

    matches: list[dict[str, Any]] = []
    malformed = 0
    retrieved_at = utc_now()
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        title = record.get("title")
        url = str(record.get("url") or "").strip()
        if not isinstance(title, str) or not url:
            continue
        title = " ".join(title.split())
        matching_terms = [term for term, pattern in patterns if pattern.search(title)]
        if not matching_terms:
            continue
        language = str(record.get("lang") or "").strip()
        if english_only and language.casefold() not in {"en", "eng", "english"}:
            continue
        normalized = normalize_url(url)
        if not normalized:
            continue
        matches.append(
            {
                "article_id": article_id(normalized),
                "date": record.get("date"),
                "url": url,
                "normalized_url": normalized,
                "domain": record.get("domain"),
                "publisher": record.get("outletName"),
                "title": title,
                "language": language,
                "author": record.get("author"),
                "description": record.get("desc"),
                "matching_terms": " | ".join(matching_terms),
                "source_dataset": "GDELT Article List (GAL)",
                "source_file": source_url,
                "retrieved_at_utc": retrieved_at,
            }
        )
    return matches, malformed


def fetch_gal_file(
    session: requests.Session,
    base_url: str,
    timestamp: datetime,
    patterns: Sequence[tuple[str, re.Pattern[str]]],
    english_only: bool,
    max_retries: int,
    timeout_seconds: float,
    maximum_download_bytes: int,
) -> FetchResult:
    url = minute_url(base_url, timestamp)
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            response = session.get(url, timeout=timeout_seconds)
            if response.status_code == 404:
                return FetchResult("missing", url, [])
            if response.status_code == 429 or 500 <= response.status_code < 600:
                wait_seconds = min(60.0, float(2**attempt))
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait_seconds = min(60.0, max(wait_seconds, float(retry_after)))
                print(f"Temporary HTTP {response.status_code}; retrying in {wait_seconds:g}s")
                time.sleep(wait_seconds)
                continue
            response.raise_for_status()
            declared_size = int(response.headers.get("Content-Length") or 0)
            if declared_size > maximum_download_bytes or len(response.content) > maximum_download_bytes:
                raise CollectionError(
                    f"Refusing {url}: file exceeds {maximum_download_bytes:,} bytes."
                )
            matches, malformed = parse_gal_payload(
                response.content, patterns, english_only, url
            )
            return FetchResult("success", url, matches, malformed)
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt + 1 < max_retries:
                wait_seconds = min(60.0, float(2**attempt))
                print(f"Connection problem; retrying in {wait_seconds:g}s: {url}")
                time.sleep(wait_seconds)
        except requests.RequestException as exc:
            raise CollectionError(f"Request failed for {url}: {exc}") from exc
    raise CollectionError(f"Could not retrieve {url} after {max_retries} attempts: {last_error}")


def config_fingerprint(args: argparse.Namespace, terms: Sequence[str]) -> str:
    values = {
        "start_date": args.start_date.strftime("%Y-%m-%d"),
        "end_date": args.end_date.strftime("%Y-%m-%d"),
        "terms": list(terms),
        "english_only": not args.all_languages,
        "base_url": args.base_url,
    }
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()


def atomic_write_json(value: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def append_jsonl(rows: Iterable[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise CollectionError(f"Invalid checkpoint data at {path}:{line_number}") from exc
    return rows


def save_output(rows: list[dict[str, Any]], output_path: Path) -> tuple[int, int]:
    frame = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    before = len(frame)
    if not frame.empty:
        frame = frame.dropna(subset=["title", "url"])
        frame = frame.drop_duplicates(subset=["article_id"], keep="first")
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce", utc=True)
        frame = frame.sort_values(["date", "article_id"], na_position="last").reset_index(drop=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8")
    os.replace(temporary, output_path)
    return len(frame), before - len(frame)


def default_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    label = f"{args.start_date:%Y%m%d}_{args.end_date:%Y%m%d}"
    output = Path(args.output) if args.output else Path(f"data/processed/gdelt_homelessness_headlines_{label}.csv")
    output = output if output.is_absolute() else ROOT / output
    checkpoint = output.with_suffix(".checkpoint.json")
    spool = output.with_suffix(".records.jsonl")
    return output, checkpoint, spool


def collect(args: argparse.Namespace) -> int:
    if args.end_date < args.start_date:
        raise CollectionError("End date must be on or after start date.")
    terms = tuple(dict.fromkeys(" ".join(term.split()) for term in args.terms if term.strip()))
    patterns = compile_headline_patterns(terms)
    output, checkpoint, spool = default_paths(args)
    fingerprint = config_fingerprint(args, terms)

    if args.restart:
        for path in (output, checkpoint, spool):
            if path.exists():
                path.unlink()

    start = args.start_date
    end = args.end_date + timedelta(hours=23, minutes=59)
    current = start
    state: dict[str, Any] = {}
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
        if state.get("config_fingerprint") != fingerprint:
            raise CollectionError(
                f"Checkpoint settings do not match this run: {checkpoint}. "
                "Use the original settings, choose another --output, or pass --restart."
            )
        if state.get("complete") and output.exists():
            print(f"Collection already complete: {output}")
            return 0
        if state.get("last_checked_utc_minute"):
            current = datetime.strptime(state["last_checked_utc_minute"], "%Y-%m-%d %H:%M") + timedelta(minutes=1)
            print(f"Resuming from {current:%Y-%m-%d %H:%M} UTC")

    session = requests.Session()
    session.headers.update({"User-Agent": args.user_agent})
    checked_this_run = 0
    found_this_run = 0
    matches_this_run = 0
    malformed_this_run = 0
    last_day = None

    print("GDELT GAL homelessness-headline collection")
    print(f"UTC date range: {args.start_date:%Y-%m-%d} through {args.end_date:%Y-%m-%d}")
    print(f"Terms: {', '.join(terms)}")
    print(f"Output: {output}")
    while current <= end and (args.max_minutes is None or checked_this_run < args.max_minutes):
        if current.date() != last_day:
            last_day = current.date()
            print(f"Checking {current.date()} UTC...")
        result = fetch_gal_file(
            session=session,
            base_url=args.base_url,
            timestamp=current,
            patterns=patterns,
            english_only=not args.all_languages,
            max_retries=args.max_retries,
            timeout_seconds=args.timeout_seconds,
            maximum_download_bytes=args.maximum_download_bytes,
        )
        checked_this_run += 1
        malformed_this_run += result.malformed_records
        if result.status == "success":
            found_this_run += 1
        if result.matches:
            append_jsonl(result.matches, spool)
            matches_this_run += len(result.matches)
            print(f"  {current:%H:%M}: {len(result.matches)} matches")
        state = {
            "config_fingerprint": fingerprint,
            "last_checked_utc_minute": current.strftime("%Y-%m-%d %H:%M"),
            "complete": False,
            "updated_at_utc": utc_now(),
        }
        atomic_write_json(state, checkpoint)
        current += timedelta(minutes=1)
        if args.request_delay:
            time.sleep(args.request_delay)

    rows = load_jsonl(spool)
    final_count, duplicates_removed = save_output(rows, output)
    complete = current > end
    state.update(
        {
            "complete": complete,
            "updated_at_utc": utc_now(),
            "output": str(output),
            "unique_articles": final_count,
        }
    )
    atomic_write_json(state, checkpoint)
    print("Collection complete." if complete else "Collection paused; rerun the same command to resume.")
    print(f"Minutes checked this run: {checked_this_run:,}")
    print(f"GAL files found this run: {found_this_run:,}")
    print(f"Headline records this run: {matches_this_run:,}")
    print(f"Malformed GAL records this run: {malformed_this_run:,}")
    print(f"Duplicate URLs removed from accumulated results: {duplicates_removed:,}")
    print(f"Unique articles currently saved: {final_count:,}")
    print(f"CSV: {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect homelessness-related English headlines captured by the public "
            "GDELT Article List. This is headline discovery, not CoC assignment."
        )
    )
    parser.add_argument("--start-date", type=parse_date, default=parse_date("2024-01-01"))
    parser.add_argument("--end-date", type=parse_date, default=parse_date("2024-01-31"))
    parser.add_argument("--terms", nargs="+", default=list(DEFAULT_TERMS))
    parser.add_argument("--all-languages", action="store_true")
    parser.add_argument("--output", help="CSV path relative to the project root or absolute.")
    parser.add_argument("--max-minutes", type=int, help="Pause after this many minutes (for testing).")
    parser.add_argument("--restart", action="store_true", help="Discard this output's prior checkpoint and restart.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--user-agent", default="CA-CoC-Homelessness-Research/1.0")
    parser.add_argument("--request-delay", type=float, default=0.05)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--maximum-download-bytes", type=int, default=20_000_000)
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.max_minutes is not None and args.max_minutes <= 0:
        raise CollectionError("--max-minutes must be positive.")
    if args.max_retries <= 0:
        raise CollectionError("--max-retries must be positive.")
    if args.request_delay < 0 or args.timeout_seconds <= 0:
        raise CollectionError("Request delay cannot be negative and timeout must be positive.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        validate_args(args)
        return collect(args)
    except (CollectionError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
