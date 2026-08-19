import tempfile
import unittest
from pathlib import Path

from job104_crawler import (
    Job104Crawler,
    JobLinkParser,
    extract_job_id,
    parse_detail,
    parse_filters,
    write_output,
)


class FakeClient:
    def get_json(self, url, *, params=None, referer):
        if "/ajax/content/" in url:
            return DETAIL
        return {
            "data": {
                "totalPage": 1,
                "list": [{"jobNo": "abc123", "jobName": "資料分析師"}],
            }
        }

    def get_text(self, url, *, params=None, referer):
        return '''
        <a class="job-name js-job-link" href="//www.104.com.tw/job/abc123?jobsource=x">A</a>
        <a class="js-job-link" href="https://www.104.com.tw/job/def456">B</a>
        <a href="https://www.104.com.tw/job/ignored">C</a>
        '''


DETAIL = {
    "data": {
        "header": {
            "jobName": "資料分析師",
            "custName": "範例公司",
            "appearDate": "2026/08/17",
        },
        "jobDetail": {
            "jobDescription": "分析資料",
            "jobCategory": [{"description": "市場調查／分析人員"}],
            "addressRegion": "台北市",
            "addressDetail": "信義區",
            "salary": "月薪 50,000 元",
            "jobType": "全職",
        },
        "condition": {
            "edu": "大學以上",
            "workExp": "1年以上",
            "major": [{"description": "統計學相關"}],
            "language": [],
            "skill": [{"description": "數據分析"}],
            "specialty": [{"description": "Python"}, {"description": "SQL"}],
            "other": "主動積極",
        },
    }
}


class ParserTests(unittest.TestCase):
    def test_link_parser_and_id(self):
        parser = JobLinkParser()
        parser.feed(FakeClient().get_text("", referer=""))
        self.assertEqual(len(parser.links), 2)
        self.assertEqual(extract_job_id(parser.links[0]), "abc123")

    def test_parse_detail(self):
        row = parse_detail("abc123", DETAIL)
        self.assertEqual(row["職務名稱"], "資料分析師")
        self.assertEqual(row["擅長工具"], "Python、SQL")
        self.assertEqual(row["工作地點"], "台北市信義區")

    def test_two_search_methods(self):
        crawler = Job104Crawler(FakeClient())
        api = crawler.crawl(
            "數據分析", method="api", pages=1, limit=10,
            details=True, filters={}
        )
        html_rows = crawler.crawl(
            "數據分析", method="html", pages=1, limit=10,
            details=False, filters={}
        )
        self.assertEqual(api[0]["公司名稱"], "範例公司")
        self.assertEqual([x["jobNo"] for x in html_rows], ["abc123", "def456"])

    def test_filters_and_outputs(self):
        self.assertEqual(parse_filters(["area=6001001000"]), {"area": "6001001000"})
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "jobs.csv"
            json_path = Path(directory) / "jobs.json"
            rows = [parse_detail("abc123", DETAIL)]
            write_output(rows, csv_path)
            write_output(rows, json_path)
            self.assertIn("資料分析師", csv_path.read_text(encoding="utf-8-sig"))
            self.assertIn("資料分析師", json_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
