# 104 職缺爬蟲（兩種文章做法）

本專案依兩篇文章實作兩種蒐集方式，僅使用 Python 標準函式庫，無須安裝額外套件。

## 兩種做法

| 方法 | 流程 | 優點 | 限制 |
|---|---|---|---|
| `api`（預設） | 呼叫搜尋 JSON 取得清單，再呼叫 `/job/ajax/content/{id}` | 快、資料結構化、容易分頁與篩選 | 非公開 API，端點或欄位可能改版 |
| `html` | 下載搜尋結果頁，解析 `.js-job-link`，再呼叫明細 JSON | 能示範 BeautifulSoup 類型的頁面解析思路 | 高度依賴 HTML class；動態渲染或改版後可能抓不到 |

兩篇文章其實都使用明細 JSON；主要差別在「如何取得職缺清單」。第二篇雖用 BeautifulSoup 解析明細回應，但真正取值仍是 `response.json()`。

第一篇的舊路徑 `/jobs/search/list` 已改版；程式使用目前對應的
`/jobs/search/api/jobs`，其餘流程仍遵循文章做法。2026 年實站另有
Cloudflare 保護，純 HTTP 程式可能收到 `403`；本專案不嘗試繞過網站的
存取控制，若遇到此狀況請停止執行，改以網站正常介面或取得官方授權。

## 使用方式

```bash
python3 job104_crawler.py "數據分析" --pages 2 --limit 30 --output jobs.csv
```

使用 HTML 搜尋頁做法：

```bash
python3 job104_crawler.py "數據分析" --method html --pages 2 --limit 30 --output jobs.json
```

加入文章列出的篩選條件（可重複使用 `--filter`）：

```bash
python3 job104_crawler.py python \
  --filter area=6001001000 \
  --filter isnew=7 \
  --filter jobexp=1,3 \
  --limit 20
```

只保留搜尋結果摘要、不逐筆抓明細：

```bash
python3 job104_crawler.py python --no-details --output jobs.json
```

常見區域代碼：台北市 `6001001000`、新北市 `6001002000`、桃園市 `6001005000`、台中市 `6001008000`、台南市 `6001014000`、高雄市 `6001016000`。

## 測試

測試不會連線到 104：

```bash
python3 -m unittest discover -s tests -v
```

## Kaggle 職缺資料前處理

針對 `postings.csv` 與 `archive/` 的第 1–9 項前處理分成兩層：

1. `normalize_sources.py`：來源／快照、欄位型態、canonical `job_key`，以及 archive 主表與 skills/summary 的串流合併。
2. `preprocessing_normalize.py`：薪資、地理、工作型態、經驗層級、職務家族、文字與技能清理。
3. `preprocess_jobs.py`：分批品質檢查、缺失統計、覆蓋率與儀表板彙總。支援 `--dry-run`；若環境沒有 `pyarrow`，會以串流 CSV 輸出，安裝 `pyarrow` 後則輸出 Parquet。

先以小批量確認欄位與權限：

```bash
python3 normalize_sources.py \
  --postings /Users/wangmingfang/Downloads/postings.csv \
  --archive /Users/wangmingfang/Downloads/archive \
  --output normalized_sample --sample 100

python3 preprocess_jobs.py \
  --postings /Users/wangmingfang/Downloads/postings.csv \
  --archive /Users/wangmingfang/Downloads/archive \
  --output processed_sample --chunksize 1000 --dry-run
```

確認輸出正常後，再移除 `--dry-run` 執行完整分批處理。完整處理會產生清理資料、分類彙總及 `data_quality_report.json/csv`；不會修改 Downloads 中的原始檔。

若只處理 archive 的主表與技能資料、不讀取大型 summary，可使用：

```bash
python3 process_archive_skills.py \
  --archive /Users/wangmingfang/Downloads/archive \
  --output archive_skills_processed
```

此流程只會讀取 `linkedin_job_postings.csv` 與 `job_skills.csv`。

## 使用注意

- 預設每次請求等待 1–2 秒，請維持低頻率並設定合理的 `--limit`。
- 網站端點、HTML 與使用規範可能變更；正式或大量使用前，請重新確認 104 的 robots.txt、服務條款與資料使用限制。
- 請勿蒐集、散布聯絡人或其他個人資料，也不要繞過驗證或存取控制。

## 參考文章

- [Python 網路爬蟲實例－104 人力銀行職缺爬蟲](https://blog.jiatool.com/posts/job104_spider/)
- [Python 爬蟲實例－104 上的職缺分析](https://medium.com/@SCU.Datascientist/%E4%BD%BF%E7%94%A8%E6%95%B8%E6%93%9A%E5%88%86%E6%9E%90%E5%88%86%E6%9E%90-104%E4%BA%BA%E5%8A%9B%E9%8A%80%E8%A1%8C%E4%B8%8A%E7%9A%84-%E6%95%B8%E6%93%9A%E5%88%86%E6%9E%90%E8%81%B7%E7%BC%BA-9e76ad7da3eb)
