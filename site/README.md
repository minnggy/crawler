# Job Radar 職缺市場分析儀表板

Job Radar 使用公開 LinkedIn 職缺資料，呈現職務、技能、公司、地點、薪資、
經驗層級、技能組合與應徵競爭度。選擇技能後，各分析區塊會同步更新。

## Prerequisites

- Node.js `>=22.13.0`

## 本機開啟

```bash
npm install
npm run dev
```

啟動後依終端顯示的網址開啟首頁。也可直接開啟
`public/job-radar-p0-final.html`，不需要後端服務。

## GitHub Pages

專案已包含 `.github/workflows/pages.yml`，會把 `site/public` 當成靜態網站發布。

1. 將功能分支合併到 `main`。
2. 到 GitHub repository 的 **Settings → Pages**。
3. 在 **Build and deployment → Source** 選擇 **GitHub Actions**。
4. 到 **Actions** 查看 `Deploy Job Radar to GitHub Pages` 是否完成。
5. 網站網址通常為：

```text
https://minnggy.github.io/crawler/job-radar-p0-final.html
```

如果希望 repository 首頁直接顯示儀表板，可再將
`job-radar-p0-final.html` 複製或改名為 `index.html`。

## 主要檔案

- `public/job-radar-p0-final.html`：互動式儀表板
- `public/job-dashboard-data.js`：職務、公司、地點與技能資料
- `public/competition-synthetic-data.js`：應徵競爭補充資料
- `tests/rendered-html.test.mjs`：網站輸出測試

## 驗證

```bash
npm test
```
