#!/usr/bin/env python3
"""104 職缺爬蟲：支援搜尋 API 與搜尋頁 HTML 兩種蒐集方式。"""

from __future__ import annotations

import argparse
import csv
import html
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


BASE_URL = "https://www.104.com.tw"
# 文章發表時使用 /jobs/search/list；104 目前的同用途路徑已改為下列網址。
SEARCH_API = f"{BASE_URL}/jobs/search/api/jobs"
SEARCH_PAGE = f"{BASE_URL}/jobs/search/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class CrawlerError(RuntimeError):
    """可預期的爬蟲錯誤。"""


@dataclass
class HttpClient:
    delay_min: float = 1.0
    delay_max: float = 2.0
    timeout: float = 20.0
    retries: int = 2

    def _get(self, url: str, *, params: dict[str, Any] | None = None,
             referer: str) -> bytes:
        if params:
            query = urlencode(params, doseq=True)
            url = f"{url}?{query}"
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": referer,
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            },
        )
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            if attempt or self.delay_max > 0:
                time.sleep(random.uniform(self.delay_min, self.delay_max))
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return response.read()
            except (HTTPError, URLError, TimeoutError) as exc:
                last_error = exc
                if attempt == self.retries:
                    break
                time.sleep(2 ** attempt)
        raise CrawlerError(f"請求失敗：{url} ({last_error})") from last_error

    def get_json(self, url: str, *, params: dict[str, Any] | None = None,
                 referer: str) -> dict[str, Any]:
        raw = self._get(url, params=params, referer=referer)
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CrawlerError(f"伺服器未回傳有效 JSON：{url}") from exc
        if not isinstance(result, dict):
            raise CrawlerError(f"JSON 根節點不是物件：{url}")
        return result

    def get_text(self, url: str, *, params: dict[str, Any] | None = None,
                 referer: str) -> str:
        return self._get(url, params=params, referer=referer).decode(
            "utf-8", errors="replace"
        )


class JobLinkParser(HTMLParser):
    """擷取舊版 104 搜尋頁中的 js-job-link。"""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        href = values.get("href")
        if href and "js-job-link" in classes:
            self.links.append(html.unescape(href))


def extract_job_id(value: str) -> str | None:
    """從 URL 或搜尋結果欄位取出 104 的英數職缺 ID。"""
    match = re.search(r"/job/(?:ajax/content/)?([a-zA-Z0-9]+)", value)
    if match:
        return match.group(1)
    if re.fullmatch(r"[a-zA-Z0-9]+", value):
        return value
    return None


def unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _descriptions(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if isinstance(item, dict):
            value = item.get("description") or item.get("name")
        else:
            value = item
        if value:
            result.append(str(value))
    return result


def parse_detail(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """把明細 API 的巢狀 JSON 整理成適合 CSV/分析的欄位。"""
    data = payload.get("data", payload)
    header = data.get("header") or {}
    detail = data.get("jobDetail") or {}
    condition = data.get("condition") or {}
    company = header.get("custName") or header.get("companyName") or ""
    address = detail.get("addressRegion") or ""
    address_detail = detail.get("addressDetail") or ""
    return {
        "job_id": job_id,
        "職務名稱": header.get("jobName", ""),
        "公司名稱": company,
        "工作內容": detail.get("jobDescription", ""),
        "職務類別": "、".join(_descriptions(detail.get("jobCategory"))),
        "工作地點": f"{address}{address_detail}".strip(),
        "薪資": detail.get("salary", ""),
        "工作性質": detail.get("jobType", ""),
        "學歷要求": condition.get("edu", ""),
        "工作經歷": condition.get("workExp", ""),
        "科系要求": "、".join(_descriptions(condition.get("major"))),
        "語文條件": "、".join(_descriptions(condition.get("language"))),
        "工作技能": "、".join(_descriptions(condition.get("skill"))),
        "擅長工具": "、".join(_descriptions(condition.get("specialty"))),
        "其他條件": condition.get("other", ""),
        "更新日期": header.get("appearDate", ""),
        "職缺網址": f"{BASE_URL}/job/{job_id}",
    }


class Job104Crawler:
    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def search_api(self, keyword: str, pages: int, filters: dict[str, str],
                   order: int = 1, ascending: bool = False) -> list[dict[str, Any]]:
        """文章一：直接呼叫搜尋 JSON（已換成目前的 API 路徑）。"""
        jobs: list[dict[str, Any]] = []
        for page in range(1, pages + 1):
            params: dict[str, Any] = {
                "ro": 0,
                "keyword": keyword,
                "order": order,
                "asc": int(ascending),
                "page": page,
                "pagesize": 20,
                "mode": "s",
                "jobsource": "index_s",
                **filters,
            }
            payload = self.client.get_json(
                SEARCH_API, params=params, referer=SEARCH_PAGE
            )
            data = payload.get("data") or {}
            page_jobs = data.get("list") or []
            if not isinstance(page_jobs, list):
                raise CrawlerError("搜尋 API 的 data.list 格式已改變")
            jobs.extend(item for item in page_jobs if isinstance(item, dict))
            total_page = int(data.get("totalPage") or 0)
            if not page_jobs or (total_page and page >= total_page):
                break
        return jobs

    def search_html(self, keyword: str, pages: int,
                    filters: dict[str, str]) -> list[dict[str, Any]]:
        """文章二：解析搜尋頁 HTML 內的 js-job-link。"""
        results: list[dict[str, Any]] = []
        for page in range(1, pages + 1):
            params = {
                "ro": 0,
                "kwop": 1,
                "keyword": keyword,
                "expansionType": "job",
                "order": 14,
                "asc": 0,
                "page": page,
                "mode": "s",
                "langFlag": 0,
                **filters,
            }
            source = self.client.get_text(
                SEARCH_PAGE, params=params, referer=SEARCH_PAGE
            )
            parser = JobLinkParser()
            parser.feed(source)
            page_ids = unique(
                job_id or "" for job_id in map(extract_job_id, parser.links)
            )
            if not page_ids:
                break
            results.extend({"jobNo": job_id} for job_id in page_ids)
        deduped: dict[str, dict[str, Any]] = {}
        for item in results:
            deduped[str(item["jobNo"])] = item
        return list(deduped.values())

    def get_detail(self, job_id: str) -> dict[str, Any]:
        url = f"{BASE_URL}/job/ajax/content/{job_id}"
        referer = f"{BASE_URL}/job/{job_id}"
        return parse_detail(
            job_id, self.client.get_json(url, referer=referer)
        )

    def crawl(self, keyword: str, *, method: str, pages: int, limit: int,
              details: bool, filters: dict[str, str]) -> list[dict[str, Any]]:
        if method == "api":
            found = self.search_api(keyword, pages, filters)
        else:
            found = self.search_html(keyword, pages, filters)
        found = found[:limit]
        if not details:
            return found
        rows = []
        for index, item in enumerate(found, start=1):
            candidates = (
                item.get("jobNo"), item.get("jobId"), item.get("jobUrl"),
                item.get("link", {}).get("job") if isinstance(item.get("link"), dict) else None,
            )
            job_id = next((extract_job_id(str(value)) for value in candidates if value), None)
            if not job_id:
                print(f"略過第 {index} 筆：找不到職缺 ID", file=sys.stderr)
                continue
            try:
                rows.append(self.get_detail(job_id))
            except CrawlerError as exc:
                print(f"略過 {job_id}：{exc}", file=sys.stderr)
        return rows


def parse_filters(values: list[str]) -> dict[str, str]:
    filters: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise argparse.ArgumentTypeError(f"篩選條件需使用 key=value：{value}")
        key, item = value.split("=", 1)
        if not key or not item:
            raise argparse.ArgumentTypeError(f"篩選條件不可為空：{value}")
        filters[key] = item
    return filters


def write_output(rows: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".json":
        output.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    with output.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="依兩篇文章實作的 104 職缺爬蟲")
    parser.add_argument("keyword", help="搜尋關鍵字，例如：數據分析")
    parser.add_argument("--method", choices=("api", "html"), default="api")
    parser.add_argument("--pages", type=int, default=1, help="最多搜尋頁數")
    parser.add_argument("--limit", type=int, default=20, help="最多輸出職缺數")
    parser.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--no-details", action="store_true", help="只輸出搜尋摘要")
    parser.add_argument("--output", type=Path, default=Path("jobs.csv"))
    parser.add_argument("--delay-min", type=float, default=1.0)
    parser.add_argument("--delay-max", type=float, default=2.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.pages < 1 or args.limit < 1:
        parser.error("--pages 與 --limit 必須大於 0")
    if args.delay_min < 0 or args.delay_max < args.delay_min:
        parser.error("延遲範圍無效")
    try:
        filters = parse_filters(args.filter)
        crawler = Job104Crawler(
            HttpClient(delay_min=args.delay_min, delay_max=args.delay_max)
        )
        rows = crawler.crawl(
            args.keyword,
            method=args.method,
            pages=args.pages,
            limit=args.limit,
            details=not args.no_details,
            filters=filters,
        )
        write_output(rows, args.output)
    except (CrawlerError, OSError, argparse.ArgumentTypeError) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1
    print(f"完成：{len(rows)} 筆，已寫入 {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
