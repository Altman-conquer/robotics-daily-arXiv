#!/usr/bin/env python3
"""Fetch historical arXiv metadata and write daily JSONL files."""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence


DATE_FORMAT = "%Y-%m-%d"
ARXIV_ID_VERSION = re.compile(r"v\d+$")


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r}; expected YYYY-MM-DD"
        ) from exc


def parse_categories(value: str) -> list[str]:
    categories = list(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))
    if not categories:
        raise argparse.ArgumentTypeError("at least one arXiv category is required")
    return categories


def validate_range(start_date: date, end_date: date, max_days: int) -> None:
    if end_date < start_date:
        raise ValueError("end date must be on or after start date")
    day_count = (end_date - start_date).days + 1
    if day_count > max_days:
        raise ValueError(f"date range is {day_count} days; maximum is {max_days}")


def build_query(categories: Sequence[str], start_date: date, end_date: date) -> str:
    category_query = " OR ".join(f"cat:{category}" for category in categories)
    start = start_date.strftime("%Y%m%d") + "0000"
    end = end_date.strftime("%Y%m%d") + "2359"
    return f"({category_query}) AND submittedDate:[{start} TO {end}]"


def build_chunks(start_date: date, end_date: date, chunk_days: int) -> list[dict[str, str]]:
    if chunk_days < 1:
        raise ValueError("chunk days must be at least 1")

    chunks = []
    current = start_date
    while current <= end_date:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end_date)
        chunks.append(
            {
                "start": current.isoformat(),
                "end": chunk_end.isoformat(),
            }
        )
        current = chunk_end + timedelta(days=1)
    return chunks


def normalize_arxiv_id(value: str) -> str:
    short_id = value.rstrip("/").rsplit("/", 1)[-1]
    return ARXIV_ID_VERSION.sub("", short_id)


def clean_text(value: str | None) -> str:
    return " ".join((value or "").split())


def paper_to_item(paper) -> dict:
    paper_id = normalize_arxiv_id(paper.entry_id)
    return {
        "id": paper_id,
        "pdf": f"https://arxiv.org/pdf/{paper_id}",
        "abs": f"https://arxiv.org/abs/{paper_id}",
        "authors": [clean_text(author.name) for author in paper.authors],
        "title": clean_text(paper.title),
        "categories": list(paper.categories),
        "comment": clean_text(paper.comment),
        "summary": clean_text(paper.summary),
    }


def load_ids(directory: Path | None) -> set[str]:
    if directory is None or not directory.exists():
        return set()

    paper_ids: set[str] = set()
    for path in sorted(directory.glob("*.jsonl")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    if item.get("id"):
                        paper_ids.add(normalize_arxiv_id(str(item["id"])))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Warning: could not read IDs from {path}: {exc}", file=sys.stderr)
    return paper_ids


def load_completed_dates(directory: Path | None, language: str) -> set[date]:
    if directory is None or not directory.exists():
        return set()

    suffix = f"_AI_enhanced_{language}.jsonl"
    completed = set()
    for path in directory.glob(f"*{suffix}"):
        try:
            completed.add(parse_date(path.name.removesuffix(suffix)))
        except argparse.ArgumentTypeError:
            continue
    return completed


def write_daily_files(
    papers: Iterable,
    output_dir: Path,
    start_date: date,
    end_date: date,
    excluded_ids: set[str],
    completed_dates: set[date],
) -> tuple[dict[date, int], int, int]:
    by_date: dict[date, list[tuple[datetime, dict]]] = defaultdict(list)
    seen_ids = set(excluded_ids)
    excluded_count = 0
    duplicate_count = 0

    for paper in papers:
        published_date = paper.published.date()
        if published_date < start_date or published_date > end_date:
            continue
        if published_date in completed_dates:
            excluded_count += 1
            continue

        item = paper_to_item(paper)
        if item["id"] in seen_ids:
            duplicate_count += 1
            continue
        seen_ids.add(item["id"])
        by_date[published_date].append((paper.published, item))

    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for published_date, dated_papers in sorted(by_date.items()):
        path = output_dir / f"{published_date.isoformat()}.jsonl"
        dated_papers.sort(key=lambda entry: entry[0], reverse=True)
        with path.open("w", encoding="utf-8") as handle:
            for _, item in dated_papers:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        counts[published_date] = len(dated_papers)

    return counts, excluded_count, duplicate_count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True, type=parse_date)
    parser.add_argument("--end-date", required=True, type=parse_date)
    parser.add_argument(
        "--categories",
        default=os.environ.get("CATEGORIES", "cs.RO,cs.AI,cs.LG,cs.CV"),
        type=parse_categories,
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--exclude-dir", type=Path)
    parser.add_argument("--skip-completed-dir", type=Path)
    parser.add_argument("--language", default=os.environ.get("LANGUAGE", "Chinese"))
    parser.add_argument("--max-results", type=int, default=20_000)
    parser.add_argument("--max-days", type=int, default=31)
    parser.add_argument("--chunk-days", type=int, default=5)
    parser.add_argument("--print-matrix", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        validate_range(args.start_date, args.end_date, args.max_days)
        chunks = build_chunks(args.start_date, args.end_date, args.chunk_days)
    except ValueError as exc:
        print(f"Invalid backfill configuration: {exc}", file=sys.stderr)
        return 2

    if args.print_matrix:
        print(json.dumps({"include": chunks}, separators=(",", ":")))
        return 0

    import arxiv

    excluded_ids = load_ids(args.exclude_dir)
    completed_dates = load_completed_dates(args.skip_completed_dir, args.language)
    query = build_query(args.categories, args.start_date, args.end_date)
    print(f"arXiv query: {query}", file=sys.stderr)
    print(
        f"Existing IDs: {len(excluded_ids)}; completed dates in range: "
        f"{sum(args.start_date <= day <= args.end_date for day in completed_dates)}",
        file=sys.stderr,
    )

    search = arxiv.Search(
        query=query,
        max_results=args.max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )
    client = arxiv.Client(page_size=100, delay_seconds=3, num_retries=5)
    try:
        counts, excluded_count, duplicate_count = write_daily_files(
            client.results(search),
            args.output_dir,
            args.start_date,
            args.end_date,
            excluded_ids,
            completed_dates,
        )
    except Exception as exc:
        print(f"Historical arXiv fetch failed: {exc}", file=sys.stderr)
        return 1

    total = sum(counts.values())
    for day, count in counts.items():
        print(f"{day.isoformat()}: {count} candidates")
    print(
        f"Historical fetch complete: {total} candidates across {len(counts)} days; "
        f"skipped {excluded_count} completed/existing and {duplicate_count} duplicate papers"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
