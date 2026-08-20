export default function Home() {
  return (
    <main className="dashboard-host">
      <iframe
        className="dashboard-frame"
        src="/job-radar-p0-final.html"
        title="Job Radar 職缺雷達"
      />
      <noscript>
        <p>
          請啟用 JavaScript，或直接開啟
          <a href="/job-radar-p0-final.html">Job Radar 職缺雷達</a>。
        </p>
      </noscript>
    </main>
  );
}
