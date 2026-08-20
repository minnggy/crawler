import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const projectRoot = new URL("../", import.meta.url);

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    {
      ASSETS: {
        fetch: async (request) => {
          const url = new URL(request.url);
          if (url.pathname === "/job-radar-p0-final.html") {
            return new Response(
              await readFile(
                new URL("../public/job-radar-p0-final.html", import.meta.url),
              ),
              { headers: { "content-type": "text/html; charset=utf-8" } },
            );
          }
          return new Response("Not found", { status: 404 });
        },
      },
    },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("publishes the Job Radar dashboard at the site root", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>職缺雷達｜技能需求與市場洞察<\/title>/i);
  assert.match(html, /src="\/job-radar-p0-final\.html"/i);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/i);
});

test("keeps the latest self-contained dashboard available as a public asset", async () => {
  const dashboard = await readFile(
    new URL("../public/job-radar-p0-final.html", import.meta.url),
    "utf8",
  );

  assert.match(dashboard, /所選技能重點摘要/);
  assert.match(dashboard, /技能組合分析/);
  assert.match(dashboard, /每份職缺有多少人應徵？/);
  assert.match(dashboard, /薪資市場概況/);
  assert.match(dashboard, /地點分布/);
  assert.match(dashboard, /公司職缺量/);
  assert.match(dashboard, /window\.CANONICAL_SKILL_DATA/);
  assert.match(dashboard, /competition-synthetic-data\.js/);
  assert.match(dashboard, /renderCompanyTreemap/);
  assert.match(dashboard, /renderSkillOrbit/);
  assert.match(dashboard, /renderExperienceHeatmap/);
  assert.match(dashboard, /renderCompetitionDistribution/);
  assert.match(dashboard, /Fira Code/);
  assert.match(dashboard, /--color-primary:#1e40af/);
  assert.match(dashboard, /chip\.is-active/);
  assert.match(dashboard, /prefers-reduced-motion:reduce/);
  assert.match(dashboard, /class="skip-link" href="#dashboard-content"/);
  assert.match(dashboard, /aria-pressed="false"/);

  const competitionSource = await readFile(
    new URL("../public/competition-synthetic-data.js", import.meta.url),
    "utf8",
  );
  assert.match(competitionSource, /window\.SYNTHETIC_COMPETITION_DATA/);
  assert.match(competitionSource, /"usesSynthetic":true/);

  await assert.rejects(access(new URL("../app/_sites-preview", import.meta.url)));
  await assert.rejects(access(new URL("../public/index.html", projectRoot)));
});
