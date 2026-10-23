#!/usr/bin/env python3
"""
 Scraper Dashboard — aggregates configured domain scraper outputs into one view.
Generates a JSON snapshot + console report with alerts, new items, and trends.

Outputs:
    - data/briefings/scraper_dashboard.json (machine-readable snapshot)
    - Console report with all alerts across scrapers

Usage:
    python3 scraper_dashboard.py
    python3 scraper_dashboard.py --json-only
    python3 scraper_dashboard.py --section jobs,finance
    python3 scraper_dashboard.py --format text
"""

import argparse
import csv
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[1]
    load_dotenv(_root / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[1]
BRIEFINGS_DIR = ROOT / "data" / "briefings"


# ─── Scraper Data Sources ─────────────────────────────────────────────
SCRAPER_SOURCES = {
    "crypto": {
        "name": "Crypto Prices",
        "latest": ROOT / "data" / "exported" / "crypto_prices.csv",
        "history": ROOT / "data" / "exported" / "crypto_history.csv",
        "alert_field": "change_24h_pct",
        "alert_threshold": 5.0,
        "icon": "📈",
    },
    "exchange_rates": {
        "name": "Exchange Rates",
        "latest": ROOT / "data" / "exported" / "exchange_rates.csv",
        "history": ROOT / "data" / "exported" / "exchange_history.csv",
        "alert_field": "change_pct",
        "alert_threshold": 0.5,
        "icon": "💱",
    },
    "github_trending": {
        "name": "GitHub Trending",
        "latest": ROOT / "data" / "exported" / "github_trending.csv",
        "history": ROOT / "data" / "exported" / "github_trending_history.csv",
        "alert_field": None,
        "alert_threshold": 0,
        "icon": "🐙",
    },
    "property": {
        "name": "Property Listings",
        "latest": ROOT / "data" / "exported" / "property_listings.csv",
        "history": ROOT / "data" / "exported" / "property_history.csv",
        "alert_field": "price_thb",
        "alert_threshold": 10.0,
        "icon": "🏠",
    },
    "seo": {
        "name": "SEO Rankings",
        "latest": ROOT / "domains" / "book-marketing" / "data" / "seo_rankings.csv",
        "history": ROOT / "domains" / "book-marketing" / "data" / "seo_rankings_history.csv",
        "alert_field": "rank",
        "alert_threshold": 5,
        "icon": "🔍",
    },
    "jobs": {
        "name": "Job Postings",
        "latest": ROOT / "data" / "job_postings.csv",
        "history": ROOT / "data" / "job_postings_history.csv",
        "matched": ROOT / "data" / "matched_jobs.csv",
        "alert_field": None,
        "alert_threshold": 0,
        "icon": "💼",
    },
    "marketplace": {
        "name": "Kaidee Classifieds",
        "latest": ROOT / "data" / "exported" / "kaidee_classifieds.csv",
        "history": ROOT / "data" / "exported" / "kaidee_classifieds_history.csv",
        "alert_field": None,
        "alert_threshold": 0,
        "icon": "🛒",
    },
    "restaurants": {
        "name": "Wongnai Bangkok",
        "latest": ROOT / "data" / "exported" / "wongnai_bangkok.csv",
        "history": ROOT / "data" / "exported" / "wongnai_bangkok_history.csv",
        "alert_field": None,
        "alert_threshold": 0,
        "icon": "🍜",
    },
    "restaurants_upcountry": {
        "name": "Wongnai Upcountry",
        "latest": ROOT / "data" / "exported" / "wongnai_upcountry.csv",
        "history": ROOT / "data" / "exported" / "wongnai_upcountry_history.csv",
        "alert_field": None,
        "alert_threshold": 0,
        "icon": "🗺️",
    },
    "news": {
        "name": "Matichon News",
        "latest": ROOT / "data" / "exported" / "matichon_news.csv",
        "history": ROOT / "data" / "exported" / "matichon_news_history.csv",
        "alert_field": None,
        "alert_threshold": 0,
        "icon": "📰",
    },
    "business_news": {
        "name": "Bangkok Post Business",
        "latest": ROOT / "data" / "exported" / "thai_business_news.csv",
        "history": ROOT / "data" / "exported" / "thai_business_news_history.csv",
        "alert_field": None,
        "alert_threshold": 0,
        "icon": "💼",
    },
    "tech_news": {
        "name": "Blognone Technology",
        "latest": ROOT / "data" / "exported" / "thai_tech_news.csv",
        "history": ROOT / "data" / "exported" / "thai_tech_news_history.csv",
        "alert_field": None,
        "alert_threshold": 0,
        "icon": "💻",
    },
    "stocks": {
        "name": "Stock Prices",
        "latest": ROOT / "data" / "exported" / "stock_prices.csv",
        "history": ROOT / "data" / "exported" / "stock_history.csv",
        "alert_field": "change_pct",
        "alert_threshold": 3.0,
        "icon": "📊",
    },
    "ai_tools": {
        "name": "AI Tools",
        "latest": ROOT / "data" / "exported" / "ai_tools.csv",
        "history": ROOT / "data" / "exported" / "ai_tools_history.csv",
        "alert_field": None,
        "alert_threshold": 0,
        "icon": "🤖",
    },
    "defi": {
        "name": "DeFi Yields",
        "latest": ROOT / "data" / "exported" / "defi_yields.csv",
        "history": ROOT / "data" / "exported" / "defi_yields_history.csv",
        "alert_field": "apy",
        "alert_threshold": 20.0,
        "icon": "🏦",
    },
}


def load_csv(filepath: Path, max_rows: int = 500) -> list:
    """Load CSV file, return list of dicts. Empty list if file missing."""
    if not filepath.exists():
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)[:max_rows]
        return rows
    except Exception:
        return []


def get_file_age(filepath: Path) -> str:
    """Get human-readable file age."""
    if not filepath.exists():
        return "never"
    mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
    age = datetime.now() - mtime
    if age < timedelta(hours=1):
        return f"{int(age.total_seconds() / 60)}m ago"
    elif age < timedelta(days=1):
        return f"{int(age.total_seconds() / 3600)}h ago"
    else:
        return f"{age.days}d ago"


def count_rows(filepath: Path) -> int:
    """Count data rows in CSV (excluding header)."""
    if not filepath.exists():
        return 0
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return sum(1 for _ in f) - 1  # minus header
    except Exception:
        return 0


def detect_alerts(source_key: str, source: dict, data: list) -> list:
    """Detect alerts based on source-specific thresholds."""
    alerts = []
    threshold = source["alert_threshold"]
    alert_field = source["alert_field"]

    if not alert_field or not data:
        return alerts

    for row in data:
        try:
            val = float(row.get(alert_field, 0))
            if abs(val) >= threshold:
                label = ""
                if source_key == "crypto":
                    label = f"{row.get('coin_id', '?').upper()} {row.get('currency', '').upper()}: {val:+.2f}% ({row.get('price', '?')})"
                elif source_key == "exchange_rates":
                    label = f"{row.get('base', '?')}->{row.get('currency', '?')}: {val:+.3f}% ({row.get('rate', '?')})"
                elif source_key == "stocks":
                    label = f"{row.get('symbol', '?')}: {val:+.2f}% (${row.get('price', '?')})"
                elif source_key == "defi":
                    label = f"{row.get('project', '?')}/{row.get('symbol', '?')}: APY {val:.1f}% (TVL ${float(row.get('tvl_usd', 0)):,.0f})"
                elif source_key == "property":
                    label = f"{row.get('title', '?')[:30]}: ฿{val:,.0f}"
                elif source_key == "seo":
                    label = f"{row.get('keyword', '?')}: rank {int(val)}"
                else:
                    label = f"{val}"

                direction = "🔺" if val > 0 else "🔻" if val < 0 else "⚡"
                alerts.append({
                    "source": source["name"],
                    "icon": source["icon"],
                    "direction": direction,
                    "value": val,
                    "label": label,
                })
        except (ValueError, TypeError):
            continue

    return alerts


def count_new_items(source_key: str, source: dict) -> dict:
    """Count new items by comparing latest vs history."""
    latest = load_csv(source["latest"], max_rows=1000) if source.get("latest") else []
    history = load_csv(source["history"], max_rows=5000) if source.get("history") else []

    if not latest:
        return {"total": 0, "new": 0, "status": "no_data"}

    # For sources with URL dedup
    url_field = None
    for field in ["url", "repo_url", "listing_url"]:
        if field in (latest[0] if latest else {}):
            url_field = field
            break

    if not url_field:
        return {"total": len(latest), "new": len(latest), "status": "ok"}

    latest_urls = {row.get(url_field, "") for row in latest if row.get(url_field)}

    if not history:
        return {"total": len(latest), "new": len(latest), "status": "first_run"}

    history_urls = {row.get(url_field, "") for row in history if row.get(url_field)}
    new_count = len(latest_urls - history_urls)

    return {"total": len(latest), "new": new_count, "status": "ok"}


def get_matched_jobs_summary() -> dict:
    """Get job match summary from matched_jobs.csv."""
    matched_path = SCRAPER_SOURCES["jobs"].get("matched")
    if not matched_path or not matched_path.exists():
        return {"total": 0, "hot": 0, "strong": 0, "top_jobs": []}

    data = load_csv(matched_path, max_rows=100)
    hot = [r for r in data if int(r.get("score", 0)) >= 20]
    strong = [r for r in data if 10 <= int(r.get("score", 0)) < 20]

    top_jobs = []
    for r in data[:5]:
        top_jobs.append({
            "title": r.get("title", "")[:50],
            "company": r.get("company", ""),
            "score": int(r.get("score", 0)),
            "salary": r.get("salary", "N/A"),
            "url": r.get("url", ""),
        })

    return {
        "total": len(data),
        "hot": len(hot),
        "strong": len(strong),
        "top_jobs": top_jobs,
    }


def get_top_defi_pools() -> list:
    """Get top DeFi yield pools."""
    data = load_csv(SCRAPER_SOURCES["defi"]["latest"], max_rows=100)
    if not data:
        return []
    # Sort by APY descending
    try:
        sorted_pools = sorted(data, key=lambda x: float(x.get("apy", 0)), reverse=True)
    except (ValueError, TypeError):
        sorted_pools = data
    top = []
    for p in sorted_pools[:5]:
        tvl = float(p.get("tvl_usd", 0))
        top.append({
            "pool": f"{p.get('project', '?')}/{p.get('symbol', '?')}"[:30],
            "chain": p.get("chain", ""),
            "apy": f"{float(p.get('apy', 0)):.1f}",
            "tvl": f"${tvl:,.0f}" if tvl else "$0",
        })
    return top


def get_stock_summary() -> list:
    """Get stock portfolio summary."""
    data = load_csv(SCRAPER_SOURCES["stocks"]["latest"], max_rows=50)
    if not data:
        return []
    summary = []
    for s in data[:10]:
        summary.append({
            "symbol": s.get("symbol", ""),
            "price": s.get("price", ""),
            "change_pct": s.get("change_pct", ""),
        })
    return summary


def generate_dashboard(sections: list = None) -> dict:
    """Generate the full dashboard data."""
    dashboard = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sources": {},
        "alerts": [],
        "summary": {},
    }

    all_alerts = []

    for key, source in SCRAPER_SOURCES.items():
        if sections and key not in sections:
            continue

        data = load_csv(source["latest"]) if source.get("latest") else []
        age = get_file_age(source["latest"]) if source.get("latest") else "never"
        row_count = count_rows(source["latest"]) if source.get("latest") else 0
        source_info = {
            "name": source["name"],
            "icon": source["icon"],
            "rows": row_count,
            "last_updated": age,
            "status": "active" if row_count > 0 else "no_data",
        }

        # Alerts
        alerts = detect_alerts(key, source, data)
        all_alerts.extend(alerts)

        # New items count
        new_items = count_new_items(key, source)
        source_info["new_items"] = new_items["new"]

        dashboard["sources"][key] = source_info

    dashboard["alerts"] = all_alerts

    # Specialized summaries
    dashboard["summary"]["matched_jobs"] = get_matched_jobs_summary()
    dashboard["summary"]["top_defi_pools"] = get_top_defi_pools()
    dashboard["summary"]["stock_portfolio"] = get_stock_summary()

    # Overall stats
    total_sources = len(dashboard["sources"])
    active_sources = sum(1 for s in dashboard["sources"].values() if s["status"] == "active")
    total_alerts = len(all_alerts)
    total_rows = sum(s["rows"] for s in dashboard["sources"].values())

    dashboard["stats"] = {
        "total_sources": total_sources,
        "active_sources": active_sources,
        "total_alerts": total_alerts,
        "total_data_points": total_rows,
    }

    return dashboard


def format_text_report(dashboard: dict) -> str:
    """Format dashboard as human-readable text report."""
    lines = []
    lines.append("=" * 70)
    lines.append("  🖥️  SCRAPER DASHBOARD")
    lines.append(f"  Generated: {dashboard['generated_at']}")
    lines.append("=" * 70)
    lines.append("")

    stats = dashboard["stats"]
    lines.append(f"  Sources: {stats['active_sources']}/{stats['total_sources']} active | "
                 f"Data points: {stats['total_data_points']:,} | "
                 f"Alerts: {stats['total_alerts']}")
    lines.append("")

    # Source overview table
    lines.append("  ── SOURCES ──────────────────────────────────────────────")
    lines.append(f"  {'Icon':<4} {'Source':<20} {'Rows':>8} {'New':>6} {'Updated':>10} {'Status':>8}")
    lines.append(f"  {'─'*4} {'─'*20} {'─'*8} {'─'*6} {'─'*10} {'─'*8}")
    for key, src in dashboard["sources"].items():
        lines.append(f"  {src['icon']:<4} {src['name']:<20} {src['rows']:>8,} {src['new_items']:>6} {src['last_updated']:>10} {src['status']:>8}")
    lines.append("")

    # Alerts
    alerts = dashboard["alerts"]
    if alerts:
        lines.append(f"  ── ALERTS ({len(alerts)}) ─────────────────────────────────────────")
        for alert in alerts[:20]:
            lines.append(f"  {alert['icon']} {alert['direction']} {alert['label']}")
        if len(alerts) > 20:
            lines.append(f"  ... and {len(alerts) - 20} more")
        lines.append("")

    # Job matches
    jobs = dashboard["summary"].get("matched_jobs", {})
    if jobs.get("total", 0) > 0:
        lines.append(f"  ── 🔥 JOB MATCHES ────────────────────────────────────────")
        lines.append(f"  Total: {jobs['total']} | Hot (20+): {jobs['hot']} | Strong (10-19): {jobs['strong']}")
        for j in jobs.get("top_jobs", []):
            lines.append(f"    [{j['score']:>2}] {j['title'][:40]:<40} | {j['company'][:15]:<15} | {j['salary']}")
        lines.append("")

    # Top DeFi pools
    defi = dashboard["summary"].get("top_defi_pools", [])
    if defi:
        lines.append(f"  ── 🏦 TOP DEFI YIELDS ───────────────────────────────────")
        for p in defi:
            lines.append(f"    {p['pool'][:25]:<25} | {p['chain']:<12} | APY: {p['apy']}% | TVL: {p['tvl']}")
        lines.append("")

    # Stock portfolio
    stocks = dashboard["summary"].get("stock_portfolio", [])
    if stocks:
        lines.append(f"  ── 📊 STOCK PORTFOLIO ──────────────────────────────────")
        for s in stocks:
            chg = s.get("change_pct", "0")
            try:
                chg_f = float(chg)
                indicator = "🟢" if chg_f > 0 else "🔴" if chg_f < 0 else "⚪"
            except (ValueError, TypeError):
                indicator = "⚪"
            lines.append(f"    {indicator} {s['symbol']:<8} ${s['price']:<12} {chg}%")
        lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


def format_html_report(dashboard: dict) -> str:
    """Format dashboard as self-contained HTML page."""
    stats = dashboard["stats"]
    sources = dashboard["sources"]
    alerts = dashboard["alerts"]
    summary = dashboard["summary"]

    # Build source cards
    source_cards = []
    for key, src in sources.items():
        status_color = "#22c55e" if src["status"] == "active" else "#94a3b8"
        source_cards.append(f"""
        <div class="card source-card">
          <div class="card-header">
            <span class="icon">{src['icon']}</span>
            <h3>{src['name']}</h3>
            <span class="status-dot" style="background:{status_color}"></span>
          </div>
          <div class="card-body">
            <div class="stat-row">
              <span class="stat-label">Rows</span>
              <span class="stat-value">{src['rows']:,}</span>
            </div>
            <div class="stat-row">
              <span class="stat-label">New</span>
              <span class="stat-value highlight">{src['new_items']}</span>
            </div>
            <div class="stat-row">
              <span class="stat-label">Updated</span>
              <span class="stat-value">{src['last_updated']}</span>
            </div>
          </div>
        </div>""")

    # Build alert rows
    alert_rows = []
    for alert in alerts[:30]:
        alert_rows.append(f"""
        <tr>
          <td>{alert['icon']}</td>
          <td>{alert['source']}</td>
          <td>{alert['direction']}</td>
          <td>{alert['label']}</td>
        </tr>""")

    # Job matches section
    jobs = summary.get("matched_jobs", {})
    job_cards = []
    for j in jobs.get("top_jobs", []):
        job_cards.append(f"""
        <div class="opp-item">
          <span class="opp-score" style="background:{'#22c55e' if j['score'] >= 20 else '#f59e0b' if j['score'] >= 10 else '#94a3b8'}">{j['score']}</span>
          <div class="opp-details">
            <a href="{j.get('url', '#')}" target="_blank">{j['title'][:50]}</a>
            <span class="opp-meta">{j['company']} · {j['salary']}</span>
          </div>
        </div>""")

    # DeFi pools section
    defi = summary.get("top_defi_pools", [])
    defi_cards = []
    for p in defi:
        defi_cards.append(f"""
        <div class="defi-item">
          <span class="defi-pool">{p['pool']}</span>
          <span class="defi-chain">{p['chain']}</span>
          <span class="defi-apy">{p['apy']}% APY</span>
          <span class="defi-tvl">{p['tvl']}</span>
        </div>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Scraper Dashboard</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 0.5rem; }}
  .subtitle {{ color: #94a3b8; margin-bottom: 2rem; }}
  .stats-bar {{ display: flex; gap: 2rem; margin-bottom: 2rem; flex-wrap: wrap; }}
  .stat {{ background: #1e293b; padding: 1rem 1.5rem; border-radius: 0.75rem; }}
  .stat-number {{ font-size: 1.5rem; font-weight: 700; color: #38bdf8; }}
  .stat-label {{ font-size: 0.85rem; color: #94a3b8; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
  .card {{ background: #1e293b; border-radius: 0.75rem; padding: 1rem; }}
  .card-header {{ display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }}
  .card-header h3 {{ font-size: 0.95rem; flex: 1; }}
  .icon {{ font-size: 1.2rem; }}
  .status-dot {{ width: 8px; height: 8px; border-radius: 50%; }}
  .stat-row {{ display: flex; justify-content: space-between; margin-bottom: 0.25rem; font-size: 0.85rem; }}
  .stat-value {{ font-weight: 600; }}
  .highlight {{ color: #22c55e; }}
  .section {{ background: #1e293b; border-radius: 0.75rem; padding: 1.5rem; margin-bottom: 2rem; }}
  .section h2 {{ font-size: 1.2rem; margin-bottom: 1rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th {{ text-align: left; padding: 0.5rem; border-bottom: 1px solid #334155; color: #94a3b8; }}
  td {{ padding: 0.5rem; border-bottom: 1px solid #1e293b; }}
  tr:hover {{ background: #334155; }}
  .opp-item {{ display: flex; align-items: center; gap: 1rem; padding: 0.75rem; border-bottom: 1px solid #334155; }}
  .opp-item:last-child {{ border-bottom: none; }}
  .opp-score {{ background: #94a3b8; color: #0f172a; font-weight: 700; padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.85rem; min-width: 2.5rem; text-align: center; }}
  .opp-details {{ flex: 1; }}
  .opp-details a {{ color: #38bdf8; text-decoration: none; font-size: 0.9rem; }}
  .opp-details a:hover {{ text-decoration: underline; }}
  .opp-meta {{ display: block; font-size: 0.75rem; color: #94a3b8; margin-top: 0.25rem; }}
  .defi-item {{ display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; border-bottom: 1px solid #334155; font-size: 0.85rem; }}
  .defi-pool {{ font-weight: 600; flex: 1; }}
  .defi-chain {{ color: #94a3b8; width: 80px; }}
  .defi-apy {{ color: #22c55e; font-weight: 600; width: 80px; text-align: right; }}
  .defi-tvl {{ color: #94a3b8; width: 100px; text-align: right; }}
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
  @media (max-width: 768px) {{ .two-col {{ grid-template-columns: 1fr; }} .grid {{ grid-template-columns: repeat(2, 1fr); }} }}
</style>
</head>
<body>
<div class="container">
  <h1>🖥️ Scraper Dashboard</h1>
  <p class="subtitle">Generated: {dashboard['generated_at']}</p>

  <div class="stats-bar">
    <div class="stat">
      <div class="stat-number">{stats['active_sources']}/{stats['total_sources']}</div>
      <div class="stat-label">Active Sources</div>
    </div>
    <div class="stat">
      <div class="stat-number">{stats['total_alerts']}</div>
      <div class="stat-label">Alerts</div>
    </div>
    <div class="stat">
      <div class="stat-number">{stats['total_data_points']:,}</div>
      <div class="stat-label">Data Points</div>
    </div>
  </div>

  <h2 style="margin-bottom: 1rem;">📡 Sources</h2>
  <div class="grid">
    {"".join(source_cards)}
  </div>

  {"<h2 style='margin-bottom: 1rem;'>⚠️ Alerts</h2><div class='section'><table><thead><tr><th></th><th>Source</th><th></th><th>Detail</th></tr></thead><tbody>" + "".join(alert_rows) + "</tbody></table></div>" if alert_rows else ""}

  <div class="two-col">
    <div class="section">
      <h2>💼 Job Matches</h2>
      <p style="color:#94a3b8; font-size:0.85rem; margin-bottom:1rem;">Total: {jobs.get('total', 0)} | Hot: {jobs.get('hot', 0)}</p>
      {"".join(job_cards) if job_cards else "<p style='color:#94a3b8'>No matches</p>"}
    </div>
  </div>

  <div class="section">
    <h2>🏦 Top DeFi Yields</h2>
    {"".join(defi_cards) if defi_cards else "<p style='color:#94a3b8'>No yield data</p>"}
  </div>
</div>
</body>
</html>"""
    return html


class ScraperDashboard:
    """Wrapper class for scheduler compatibility."""
    def __init__(self, format="both", output=None, section=None, **kwargs):
        self.format = format
        self.output = output or str(BRIEFINGS_DIR / "scraper_dashboard.json")
        self.section = section

    async def run(self, **kwargs):
        main(format=self.format, output=self.output, section=self.section)
        return [{"source": "dashboard", "count": 0}]


def main(format="both", output=None, section=None, json_only=False):
    output_path = Path(output or str(BRIEFINGS_DIR / "scraper_dashboard.json"))

    sections = None
    if section:
        sections = [s.strip() for s in section.split(",")]

    dashboard = generate_dashboard(sections)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, indent=2, ensure_ascii=False)

    if json_only:
        print(json.dumps(dashboard, ensure_ascii=False))
        return dashboard

    if format in ("json", "both"):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Dashboard saved to {output_path}")

    if not json_only and format in ("text", "both"):
        report = format_text_report(dashboard)
        print(report)

    # Generate HTML dashboard
    html_path = BRIEFINGS_DIR / "scraper_dashboard.html"
    html_report = format_html_report(dashboard)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_report)
    print(f"  HTML dashboard saved to {html_path}")

    stats = dashboard["stats"]
    print(f"  Sources: {stats['active_sources']}/{stats['total_sources']} | "
          f"Alerts: {stats['total_alerts']} | "
          f"Data: {stats['total_data_points']:,} rows")
    print("  Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate the scraper dashboard")
    parser.add_argument("--json-only", action="store_true", help="Write JSON only to stdout")
    parser.add_argument("--format", choices=["text", "json", "both"], default="both")
    parser.add_argument("--output", help="JSON output path")
    parser.add_argument("--section", help="Comma-separated dashboard sections")
    args = parser.parse_args()
    main(
        format=args.format,
        output=args.output,
        section=args.section,
        json_only=args.json_only,
    )
