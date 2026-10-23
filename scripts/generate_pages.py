"""
Content Generation Engine — transforms insights into storytelling HTML pages.

Reads structured insights from insights.json and generates beautiful, niche-specific
HTML pages with data visualizations, infographics, and storytelling elements.

Output:
    - data/pages/index.html (overview dashboard)
    - data/pages/{niche}.html (one page per niche)

Usage:
    python3 scripts (book-job-scraping)/scripts/generate_pages.py
    python3 scripts (book-job-scraping)/scripts/generate_pages.py --niche defi,jobs
    python3 scripts (book-job-scraping)/scripts/generate_pages.py --min-score 70
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[1]
    load_dotenv(_root / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[1]
BRIEFINGS_DIR = ROOT / "data" / "briefings"
PAGES_DIR = ROOT / "data" / "pages"

# Niche metadata with icons and colors
NICHE_META = {
    "crypto": {"icon": "₿", "color": "#f7931a", "label": "Crypto Markets"},
    "exchange_rates": {"icon": "💱", "color": "#10b981", "label": "Exchange Rates"},
    "stocks": {"icon": "📈", "color": "#3b82f6", "label": "Stock Portfolio"},
    "defi": {"icon": "🏦", "color": "#8b5cf6", "label": "DeFi Yields"},
    "github_trending": {"icon": "🔥", "color": "#181717", "label": "GitHub Trending"},
    "jobs": {"icon": "💼", "color": "#06b6d4", "label": "Job Market"},
    "opportunities": {"icon": "💰", "color": "#10b981", "label": "Money Opportunities"},
    "property": {"icon": "🏠", "color": "#ef4444", "label": "Real Estate"},
    "seo": {"icon": "🔍", "color": "#6366f1", "label": "SEO Rankings"},
    "ai_tools": {"icon": "🤖", "color": "#8b5cf6", "label": "AI Tools"},
}


def load_insights() -> dict:
    """Load insights.json."""
    json_path = BRIEFINGS_DIR / "insights.json"
    if not json_path.exists():
        print(f"ERROR: {json_path} not found. Run generate_insights.py first.")
        sys.exit(1)
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_css() -> str:
    """Generate shared CSS for all pages."""
    return """
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0f172a;--card:#1e293b;--border:#334155;--text:#e2e8f0;--muted:#94a3b8;--accent:#3b82f6;--green:#10b981;--red:#ef4444;--yellow:#f59e0b;--purple:#8b5cf6}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;line-height:1.6}
.header{background:linear-gradient(135deg,var(--card) 0%,#0f172a 100%);border-bottom:1px solid var(--border);padding:2rem;display:flex;align-items:center;justify-content:space-between}
.header h1{font-size:2rem;font-weight:800;display:flex;align-items:center;gap:.75rem}
.header .meta{font-size:.875rem;color:var(--muted);display:flex;gap:1.5rem}
.container{max-width:1400px;margin:0 auto;padding:2rem}
.grid{display:grid;gap:1.5rem}
.grid-4{grid-template-columns:repeat(auto-fit,minmax(250px,1fr))}
.grid-3{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.grid-2{grid-template-columns:repeat(auto-fit,minmax(400px,1fr))}
.card{background:var(--card);border:1px solid var(--border);border-radius:1rem;padding:1.5rem;transition:transform .2s,box-shadow .2s}
.card:hover{transform:translateY(-2px);box-shadow:0 10px 25px rgba(0,0,0,.3)}
.card h3{font-size:1rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:1rem;display:flex;align-items:center;gap:.5rem}
.stat-card{text-align:center;position:relative;overflow:hidden}
.stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:4px;background:var(--accent)}
.stat-card .value{font-size:3rem;font-weight:800;line-height:1;margin:.5rem 0}
.stat-card .label{font-size:.875rem;color:var(--muted)}
.insight-card{position:relative;padding-left:1rem;border-left:4px solid var(--accent)}
.insight-card.high{border-left-color:var(--green)}
.insight-card.medium{border-left-color:var(--yellow)}
.insight-card.low{border-left-color:var(--muted)}
.insight-title{font-size:1.125rem;font-weight:700;margin-bottom:.5rem}
.insight-narrative{color:var(--muted);font-size:.9375rem;margin-bottom:1rem;line-height:1.7}
.insight-hook{background:rgba(59,130,246,.1);border:1px solid rgba(59,130,246,.2);border-radius:.5rem;padding:.75rem 1rem;font-size:.875rem;margin-bottom:1rem}
.actionability{display:inline-flex;align-items:center;gap:.5rem;font-size:.875rem;font-weight:600}
.actionability-bar{width:100px;height:8px;background:var(--border);border-radius:4px;overflow:hidden}
.actionability-fill{height:100%;border-radius:4px;transition:width .3s}
.data-point{background:rgba(255,255,255,.05);border-radius:.5rem;padding:1rem;margin-top:1rem}
.data-point h4{font-size:.875rem;color:var(--muted);margin-bottom:.75rem}
.data-table{width:100%;border-collapse:collapse;font-size:.875rem}
.data-table th{text-align:left;padding:.5rem .75rem;color:var(--muted);font-weight:500;border-bottom:1px solid var(--border)}
.data-table td{padding:.5rem .75rem;border-bottom:1px solid rgba(51,65,85,.3)}
.data-table tr:hover td{background:rgba(51,65,85,.2)}
.chart-container{position:relative;height:300px;margin-top:1rem}
.badge{display:inline-block;padding:.25rem .75rem;border-radius:9999px;font-size:.75rem;font-weight:600}
.badge-high{background:rgba(16,185,129,.2);color:#34d399}
.badge-medium{background:rgba(245,158,11,.2);color:#fbbf24}
.badge-low{background:rgba(100,116,139,.2);color:#94a3b8}
.nav-links{display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:2rem}
.nav-link{padding:.5rem 1rem;background:var(--card);border:1px solid var(--border);border-radius:.5rem;text-decoration:none;color:var(--text);font-size:.875rem;transition:all .15s}
.nav-link:hover{border-color:var(--accent);background:rgba(59,130,246,.1)}
.nav-link.active{background:var(--accent);border-color:var(--accent);color:#fff}
.footer{text-align:center;padding:2rem;color:var(--muted);font-size:.875rem;border-top:1px solid var(--border);margin-top:3rem}
@media(max-width:768px){.container{padding:1rem}.grid-2,.grid-3{grid-template-columns:1fr}.header h1{font-size:1.5rem}}
</style>
"""


def generate_header(title: str, subtitle: str = "") -> str:
    """Generate page header."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""
<div class="header">
  <div>
    <h1>{title}</h1>
    {f'<p style="color:var(--muted);margin-top:.5rem">{subtitle}</p>' if subtitle else ''}
  </div>
  <div class="meta">
    <span>Generated: {now}</span>
    <a href="index.html" style="color:var(--accent);text-decoration:none">← Back to Overview</a>
  </div>
</div>
"""


def generate_index_page(data: dict) -> str:
    """Generate overview/index page."""
    summary = data["summary"]
    by_niche = data["by_niche"]
    
    # Calculate stats
    total_insights = summary["total_insights"]
    niches_analyzed = summary["niches_analyzed"]
    high_actionability = sum(1 for i in summary["top_insights_across_all"] if i.get("actionability", 0) >= 70)
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Solo Empire Insights — Overview</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
{generate_css()}
</head>
<body>
{generate_header("📊 Solo Empire Insights", f"{niches_analyzed} niches • {total_insights} insights • Actionable intelligence")}

<div class="container">
  <!-- Summary Stats -->
  <div class="grid grid-4" style="margin-bottom:2rem">
    <div class="card stat-card">
      <div class="value" style="color:var(--accent)">{niches_analyzed}</div>
      <div class="label">Niches Analyzed</div>
    </div>
    <div class="card stat-card">
      <div class="value" style="color:var(--green)">{total_insights}</div>
      <div class="label">Total Insights</div>
    </div>
    <div class="card stat-card">
      <div class="value" style="color:var(--yellow)">{high_actionability}</div>
      <div class="label">High Actionability</div>
    </div>
    <div class="card stat-card">
      <div class="value" style="color:var(--purple)">{len(summary.get('top_insights_across_all', []))}</div>
      <div class="label">Top Insights</div>
    </div>
  </div>

  <!-- Top Insights Across All Niches -->
  <div class="card" style="margin-bottom:2rem">
    <h3>🔥 Top Insights Across All Niches</h3>
    <div style="display:flex;flex-direction:column;gap:1rem">
"""
    
    for insight in summary.get("top_insights_across_all", [])[:10]:
        score = insight.get("actionability", 0)
        score_class = "high" if score >= 70 else "medium" if score >= 40 else "low"
        niche = insight.get("niche", "")
        meta = NICHE_META.get(niche, {"icon": "📌", "color": "var(--accent)"})
        
        html += f"""
      <div class="insight-card {score_class}">
        <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:.5rem">
          <div class="insight-title">{meta['icon']} {insight['title']}</div>
          <div class="actionability">
            <span>{score}/100</span>
            <div class="actionability-bar">
              <div class="actionability-fill" style="width:{score}%;background:{meta['color']}"></div>
            </div>
          </div>
        </div>
        <div class="insight-narrative">{insight.get('narrative', '')}</div>
        <div class="insight-hook">{insight.get('content_hook', '')}</div>
      </div>
"""
    
    html += """
    </div>
  </div>

  <!-- Niche Overview Grid -->
  <div class="grid grid-3">
"""
    
    for niche_key, niche_data in by_niche.items():
        meta = NICHE_META.get(niche_key, {"icon": "📌", "color": "var(--accent)", "label": niche_key})
        insights = niche_data.get("insights", [])
        top_insight = niche_data.get("top_insight", {})
        insight_count = len(insights)
        avg_score = sum(i.get("actionability", 0) for i in insights) / max(insight_count, 1)
        
        html += f"""
    <a href="{niche_key}.html" class="card" style="text-decoration:none;color:inherit">
      <h3 style="color:{meta['color']}">{meta['icon']} {meta['label']}</h3>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
        <div>
          <div style="font-size:2rem;font-weight:800">{insight_count}</div>
          <div style="font-size:.75rem;color:var(--muted)">insights</div>
        </div>
        <div>
          <div style="font-size:1.5rem;font-weight:700;color:{meta['color']}">{avg_score:.0f}</div>
          <div style="font-size:.75rem;color:var(--muted)">avg score</div>
        </div>
      </div>
      <div style="font-size:.875rem;color:var(--muted);line-height:1.5">
        {top_insight.get('title', 'No insights yet')[:100]}{'...' if len(top_insight.get('title', '')) > 100 else ''}
      </div>
    </a>
"""
    
    html += """
  </div>

  <!-- Chart: Insights by Niche -->
  <div class="card" style="margin-top:2rem">
    <h3>📊 Insights Distribution by Niche</h3>
    <div class="chart-container">
      <canvas id="niche-chart"></canvas>
    </div>
  </div>
</div>

<div class="footer">
  Solo Empire Insights Engine • Layer 2: Content Generation
</div>

<script>
const ctx = document.getElementById('niche-chart');
new Chart(ctx, {
  type: 'bar',
  data: {
    labels: [""" + ", ".join(f"'{NICHE_META.get(k, {'label': k})['label']}'" for k in by_niche.keys()) + """],
    datasets: [{
      label: 'Insights',
      data: [""" + ", ".join(str(len(by_niche[k].get("insights", []))) for k in by_niche.keys()) + """],
      backgroundColor: [""" + ", ".join(f"'{NICHE_META.get(k, {'color': 'var(--accent)'})['color']}'" for k in by_niche.keys()) + """],
      borderRadius: 8
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      y: { beginAtZero: true, ticks: { color: '#94a3b8' }, grid: { color: 'rgba(51,65,85,.3)' } },
      x: { ticks: { color: '#94a3b8' }, grid: { display: false } }
    }
  }
});
</script>
</body>
</html>
"""
    return html


def generate_niche_page(niche_key: str, niche_data: dict) -> str:
    """Generate a page for a specific niche."""
    meta = NICHE_META.get(niche_key, {"icon": "📌", "color": "var(--accent)", "label": niche_key})
    insights = niche_data.get("insights", [])
    data_rows = niche_data.get("data_rows", 0)
    
    # Calculate stats
    avg_score = sum(i.get("actionability", 0) for i in insights) / max(len(insights), 1)
    high_count = sum(1 for i in insights if i.get("actionability", 0) >= 70)
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{meta['label']} — Solo Empire Insights</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
{generate_css()}
</head>
<body>
{generate_header(f"{meta['icon']} {meta['label']}", f"{len(insights)} insights • {data_rows} data points • Avg score: {avg_score:.0f}/100")}

<div class="container">
  <!-- Navigation -->
  <div class="nav-links">
    <a href="index.html" class="nav-link">← Overview</a>
"""
    
    for nk in NICHE_META.keys():
        if nk != niche_key:
            nmeta = NICHE_META[nk]
            html += f'    <a href="{nk}.html" class="nav-link">{nmeta["icon"]} {nmeta["label"]}</a>\n'
    
    html += f"""
  </div>

  <!-- Stats -->
  <div class="grid grid-4" style="margin-bottom:2rem">
    <div class="card stat-card">
      <div class="value" style="color:{meta['color']}">{len(insights)}</div>
      <div class="label">Insights</div>
    </div>
    <div class="card stat-card">
      <div class="value" style="color:var(--green)">{high_count}</div>
      <div class="label">High Actionability</div>
    </div>
    <div class="card stat-card">
      <div class="value" style="color:var(--yellow)">{avg_score:.0f}</div>
      <div class="label">Avg Score</div>
    </div>
    <div class="card stat-card">
      <div class="value" style="color:var(--accent)">{data_rows}</div>
      <div class="label">Data Points</div>
    </div>
  </div>

  <!-- Insights List -->
  <div style="display:flex;flex-direction:column;gap:1.5rem">
"""
    
    for insight in insights:
        score = insight.get("actionability", 0)
        score_class = "high" if score >= 70 else "medium" if score >= 40 else "low"
        
        html += f"""
    <div class="card insight-card {score_class}">
      <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:1rem">
        <div class="insight-title">{insight.get('title', 'Untitled Insight')}</div>
        <div class="actionability">
          <span>{score}/100</span>
          <div class="actionability-bar">
            <div class="actionability-fill" style="width:{score}%;background:{meta['color']}"></div>
          </div>
        </div>
      </div>
      <div class="insight-narrative">{insight.get('narrative', '')}</div>
      <div class="insight-hook">{insight.get('content_hook', '')}</div>
"""
        
        # Render data points
        data_points = insight.get("data_points", {})
        if data_points:
            html += render_data_points(data_points, niche_key)
        
        html += """
    </div>
"""
    
    html += """
  </div>

  <!-- Data Visualization -->
  <div class="card" style="margin-top:2rem">
    <h3>📊 Actionability Scores</h3>
    <div class="chart-container">
      <canvas id="score-chart"></canvas>
    </div>
  </div>
</div>

<div class="footer">
  """ + meta['label'] + """ • Solo Empire Insights Engine
</div>

<script>
const ctx = document.getElementById('score-chart');
new Chart(ctx, {
  type: 'bar',
  data: {
    labels: [""" + ", ".join(f"'{i.get('title', '')[:30]}'" for i in insights) + """],
    datasets: [{
      label: 'Actionability Score',
      data: [""" + ", ".join(str(i.get("actionability", 0)) for i in insights) + """],
      backgroundColor: '""" + meta['color'] + """',
      borderRadius: 8
    }]
  },
  options: {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { beginAtZero: true, max: 100, ticks: { color: '#94a3b8' }, grid: { color: 'rgba(51,65,85,.3)' } },
      y: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { display: false } }
    }
  }
});
</script>
</body>
</html>
"""
    return html


def render_data_points(data_points: dict, niche_key: str) -> str:
    """Render data points as tables or visualizations."""
    html = '<div class="data-point"><h4>📊 Key Data</h4>'
    
    # Handle different data point types
    if "top_pools" in data_points:  # DeFi pools
        pools = data_points["top_pools"]
        html += '<table class="data-table"><thead><tr><th>Pool</th><th>Chain</th><th>APY</th><th>TVL</th></tr></thead><tbody>'
        for pool in pools[:5]:
            html += f'<tr><td>{pool.get("pool", "?")}</td><td>{pool.get("chain", "?")}</td><td style="color:var(--green);font-weight:600">{pool.get("apy", 0):.1f}%</td><td>${pool.get("tvl_usd", 0):,.0f}</td></tr>'
        html += '</tbody></table>'
    
    elif "top_jobs" in data_points:  # Job listings
        jobs = data_points["top_jobs"]
        html += '<table class="data-table"><thead><tr><th>Position</th><th>Company</th><th>Salary</th></tr></thead><tbody>'
        for job in jobs[:5]:
            html += f'<tr><td>{job.get("title", "?")}</td><td>{job.get("company", "?")}</td><td style="color:var(--green);font-weight:600">{job.get("salary", "?")}</td></tr>'
        html += '</tbody></table>'
    
    elif "top_repos" in data_points or "new_repos" in data_points:  # GitHub repos
        repos = data_points.get("top_repos", data_points.get("new_repos", []))
        html += '<table class="data-table"><thead><tr><th>Repository</th><th>Stars</th><th>Language</th></tr></thead><tbody>'
        for repo in repos[:5]:
            html += f'<tr><td><a href="{repo.get("url", "#")}" style="color:var(--accent);text-decoration:none">{repo.get("name", "?")}</a></td><td>⭐ {repo.get("stars", 0):,}</td><td>{repo.get("language", "?")}</td></tr>'
        html += '</tbody></table>'
    
    elif "rates" in data_points:  # Exchange rates
        rates = data_points["rates"]
        html += '<table class="data-table"><thead><tr><th>Currency</th><th>Rate</th></tr></thead><tbody>'
        for rate in rates[:10]:
            html += f'<tr><td>{rate.get("currency", "?")}</td><td style="color:var(--accent);font-weight:600">{rate.get("rate", 0):.4f}</td></tr>'
        html += '</tbody></table>'
    
    elif "keywords" in data_points:  # Job skills
        keywords = data_points["keywords"]
        html += '<table class="data-table"><thead><tr><th>Skill</th><th>Job Count</th></tr></thead><tbody>'
        for skill, count in sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:10]:
            html += f'<tr><td>{skill}</td><td style="color:var(--accent);font-weight:600">{count}</td></tr>'
        html += '</tbody></table>'
    
    elif "top_opportunities" in data_points:  # Money opportunities
        opps = data_points["top_opportunities"]
        html += '<table class="data-table"><thead><tr><th>Opportunity</th><th>Category</th><th>Score</th></tr></thead><tbody>'
        for opp in opps[:5]:
            html += f'<tr><td><a href="{opp.get("url", "#")}" style="color:var(--accent);text-decoration:none">{opp.get("title", "?")[:50]}</a></td><td>{opp.get("category", "?")}</td><td style="color:var(--green);font-weight:600">{opp.get("score", 0)}/100</td></tr>'
        html += '</tbody></table>'
    
    elif "chain_averages" in data_points:  # DeFi chain comparison
        chains = data_points["chain_averages"]
        html += '<table class="data-table"><thead><tr><th>Chain</th><th>Avg APY</th></tr></thead><tbody>'
        for chain in chains[:10]:
            html += f'<tr><td>{chain[0]}</td><td style="color:var(--green);font-weight:600">{chain[1]:.1f}%</td></tr>'
        html += '</tbody></table>'
    
    elif "categories" in data_points:  # Category breakdown
        categories = data_points["categories"]
        html += '<table class="data-table"><thead><tr><th>Category</th><th>Count</th></tr></thead><tbody>'
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            html += f'<tr><td>{cat}</td><td style="color:var(--accent);font-weight:600">{count}</td></tr>'
        html += '</tbody></table>'
    
    elif "types" in data_points:  # Property types
        types = data_points["types"]
        html += '<table class="data-table"><thead><tr><th>Type</th><th>Listings</th></tr></thead><tbody>'
        for ptype, count in sorted(types.items(), key=lambda x: x[1], reverse=True):
            html += f'<tr><td>{ptype}</td><td style="color:var(--accent);font-weight:600">{count}</td></tr>'
        html += '</tbody></table>'
    
    else:
        # Generic key-value display
        for key, value in data_points.items():
            if isinstance(value, (str, int, float)):
                html += f'<div style="margin-bottom:.5rem"><strong>{key}:</strong> {value}</div>'
    
    html += '</div>'
    return html


def generate_pages(niches: list = None, min_score: int = 0):
    """Generate all HTML pages."""
    data = load_insights()
    
    # Filter niches if specified
    by_niche = data.get("by_niche", {})
    if niches:
        by_niche = {k: v for k, v in by_niche.items() if k in niches}
    
    # Filter by min score
    if min_score > 0:
        for niche_key in by_niche:
            by_niche[niche_key]["insights"] = [
                i for i in by_niche[niche_key]["insights"]
                if i.get("actionability", 0) >= min_score
            ]
    
    # Create output directory
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate index page
    index_html = generate_index_page(data)
    index_path = PAGES_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"  Generated index page: {index_path}")
    
    # Generate niche pages
    for niche_key, niche_data in by_niche.items():
        niche_html = generate_niche_page(niche_key, niche_data)
        niche_path = PAGES_DIR / f"{niche_key}.html"
        with open(niche_path, "w", encoding="utf-8") as f:
            f.write(niche_html)
        print(f"  Generated {niche_key} page: {niche_path}")
    
    return len(by_niche) + 1  # +1 for index


def main():
    parser = argparse.ArgumentParser(description="Generate HTML pages from insights")
    parser.add_argument("--niches", type=str, help="Comma-separated list of niches to generate")
    parser.add_argument("--min-score", type=int, default=0, help="Minimum actionability score (0-100)")
    args = parser.parse_args()
    
    niches = [n.strip() for n in args.niches.split(",")] if args.niches else None
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Content Generation Engine")
    print(f"  Generating pages for {len(niches) if niches else 'all'} niches...")
    
    page_count = generate_pages(niches=niches, min_score=args.min_score)
    
    print(f"\n  Generated {page_count} pages in {PAGES_DIR}")
    print(f"  Open: file://{PAGES_DIR / 'index.html'}")
    print("\n  Done.")


if __name__ == "__main__":
    main()
