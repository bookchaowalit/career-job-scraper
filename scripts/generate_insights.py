#!/usr/bin/env python3
"""
Insight Extraction Engine — transforms raw scraper data into actionable insights.

Reads all 11 scraper data sources, compares latest vs history, detects trends,
anomalies, and opportunities. Outputs structured insights per niche for content
generation (infographics, storytelling pages, newsletters).

Output:
    - data/briefings/insights.json (structured insights)
    - data/briefings/insights.md (human-readable summary)

Usage:
    python3 scripts (book-job-scraping)/scripts/generate_insights.py
    python3 scripts (book-job-scraping)/scripts/generate_insights.py --niche finance,dev
    python3 scripts (book-job-scraping)/scripts/generate_insights.py --min-score 70
"""

import argparse
import csv
import json
import math
import os
from datetime import datetime, timedelta
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


# Reuse paths from scraper_dashboard
SCRAPER_PATHS = {
    "crypto": {
        "latest": ROOT / "data" / "exported" / "crypto_prices.csv",
        "history": ROOT / "data" / "exported" / "crypto_history.csv",
    },
    "exchange_rates": {
        "latest": ROOT / "data" / "exported" / "exchange_rates.csv",
        "history": ROOT / "data" / "exported" / "exchange_history.csv",
    },
    "marketplace": {
        "latest": ROOT / "data" / "exported" / "kaidee_classifieds.csv",
        "history": ROOT / "data" / "exported" / "kaidee_classifieds_history.csv",
    },
    "restaurants": {
        "latest": ROOT / "data" / "exported" / "wongnai_bangkok.csv",
        "history": ROOT / "data" / "exported" / "wongnai_bangkok_history.csv",
    },
    "restaurants_upcountry": {
        "latest": ROOT / "data" / "exported" / "wongnai_upcountry.csv",
        "history": ROOT / "data" / "exported" / "wongnai_upcountry_history.csv",
    },
    "news": {
        "latest": ROOT / "data" / "exported" / "matichon_news.csv",
        "history": ROOT / "data" / "exported" / "matichon_news_history.csv",
    },
    "business_news": {
        "latest": ROOT / "data" / "exported" / "thai_business_news.csv",
        "history": ROOT / "data" / "exported" / "thai_business_news_history.csv",
    },
    "tech_news": {
        "latest": ROOT / "data" / "exported" / "thai_tech_news.csv",
        "history": ROOT / "data" / "exported" / "thai_tech_news_history.csv",
    },
    "stocks": {
        "latest": ROOT / "data" / "exported" / "stock_prices.csv",
        "history": ROOT / "data" / "exported" / "stock_history.csv",
    },
    "defi": {
        "latest": ROOT / "data" / "exported" / "defi_yields.csv",
        "history": ROOT / "data" / "exported" / "defi_yields_history.csv",
    },
    "github_trending": {
        "latest": ROOT / "data" / "exported" / "github_trending.csv",
        "history": ROOT / "data" / "exported" / "github_trending_history.csv",
    },
    "jobs": {
        "latest": ROOT / "data" / "job_postings.csv",
        "history": ROOT / "data" / "job_postings_history.csv",
    },
    "property": {
        "latest": ROOT / "data" / "exported" / "property_listings.csv",
        "history": ROOT / "data" / "exported" / "property_history.csv",
    },
    "seo": {
        "latest": ROOT / "domains" / "book-marketing" / "data" / "seo_rankings.csv",
        "history": ROOT / "domains" / "book-marketing" / "data" / "seo_rankings_history.csv",
    },
    "ai_tools": {
        "latest": ROOT / "data" / "exported" / "ai_tools.csv",
        "history": ROOT / "data" / "exported" / "ai_tools_history.csv",
    },
}

NICHE_NAMES = {
    "crypto": "Crypto Markets",
    "exchange_rates": "Exchange Rates",
    "marketplace": "Marketplace Listings",
    "restaurants": "Wongnai Bangkok Restaurants",
    "restaurants_upcountry": "Wongnai Upcountry Restaurants",
    "news": "Matichon News",
    "business_news": "Bangkok Post Business",
    "tech_news": "Blognone Technology",
    "stocks": "Stock Portfolio",
    "defi": "DeFi Yields",
    "github_trending": "GitHub Trending",
    "jobs": "Job Market",
    "property": "Real Estate",
    "seo": "SEO Rankings",
    "ai_tools": "AI Tools",
}


def load_csv(filepath: Path, max_rows: int = 10000) -> list:
    """Load CSV file, return list of dicts."""
    if not filepath.exists():
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)[:max_rows]
        return rows
    except Exception:
        return []


def parse_date(date_str: str) -> datetime | None:
    """Parse various date formats."""
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"]:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


# ─── Insight Extractors ────────────────────────────────────────────────

def extract_crypto_insights(latest: list, history: list) -> list:
    """Extract crypto market insights."""
    insights = []
    if not latest:
        return insights

    # Prefer one comparable quote currency when a source emits multiple pairs.
    usd_latest = [row for row in latest if str(row.get("currency", "")).lower() == "usd"]
    comparable_rows = usd_latest or latest

    # Biggest movers (24h)
    movers = []
    for row in comparable_rows:
        try:
            change = float(row.get("change_24h_pct", 0))
            movers.append({
                "coin": row.get("coin_id", row.get("coin", "?")).upper(),
                "currency": str(row.get("currency", "USD")).upper(),
                "price": float(row.get("price", 0)),
                "change_pct": change,
            })
        except (ValueError, TypeError):
            continue

    if movers:
        movers.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
        top_mover = movers[0]
        direction = "surged" if top_mover["change_pct"] > 0 else "dropped"
        insights.append({
            "type": "price_movement",
            "title": f"{top_mover['coin']} {direction} {abs(top_mover['change_pct']):.1f}% in 24h",
            "narrative": f"{top_mover['coin']} is now at {top_mover['currency']} {top_mover['price']:,.2f}, "
                        f"{'gaining' if top_mover['change_pct'] > 0 else 'losing'} "
                        f"{abs(top_mover['change_pct']):.1f}% in the last 24 hours.",
            "data_points": {
                "coin": top_mover["coin"],
                "price": top_mover["price"],
                "change_pct": top_mover["change_pct"],
            },
            "actionability": min(100, int(abs(top_mover["change_pct"]) * 10)),
            "content_hook": f"📈 {top_mover['coin']} moves {abs(top_mover['change_pct']):.1f}% — here's what it means",
        })

        # Top 3 movers summary
        top3 = movers[:3]
        gainers = [m for m in top3 if m["change_pct"] > 0]
        losers = [m for m in top3 if m["change_pct"] < 0]
        if gainers and losers:
            # Joined outside the f-string: nested same-quote f-strings need Python 3.12.
            top_gainers = ", ".join(f"{m['coin']} (+{m['change_pct']:.1f}%)" for m in gainers[:2])
            top_losers = ", ".join(f"{m['coin']} ({m['change_pct']:.1f}%)" for m in losers[:2])
            insights.append({
                "type": "market_summary",
                "title": "Mixed crypto market — winners and losers",
                "narrative": f"Top gainers: {top_gainers}. "
                            f"Top losers: {top_losers}.",
                "data_points": {"gainers": gainers[:2], "losers": losers[:2]},
                "actionability": 50,
                "content_hook": "📊 Crypto market update — who's up, who's down",
            })

    # Trend from history (7-day direction)
    if history and len(history) >= 7:
        recent = history[-7:]
        btc_prices = []
        for row in recent:
            if row.get("coin_id") == "bitcoin":
                try:
                    btc_prices.append(float(row.get("price", 0)))
                except (ValueError, TypeError):
                    pass
        if len(btc_prices) >= 2:
            week_change = ((btc_prices[-1] - btc_prices[0]) / btc_prices[0]) * 100
            direction = "up" if week_change > 0 else "down"
            insights.append({
                "type": "trend",
                "title": f"Bitcoin {direction} {abs(week_change):.1f}% over 7 days",
                "narrative": f"BTC moved from ${btc_prices[0]:,.0f} to ${btc_prices[-1]:,.0f} this week, "
                            f"a {direction} trend of {abs(week_change):.1f}%.",
                "data_points": {"start_price": btc_prices[0], "end_price": btc_prices[-1], "week_change_pct": week_change},
                "actionability": 60,
                "content_hook": f"₿ Bitcoin weekly trend: {direction} {abs(week_change):.1f}%",
            })

    return insights


def extract_stock_insights(latest: list, history: list) -> list:
    """Extract stock portfolio insights."""
    insights = []
    if not latest:
        return insights

    # Portfolio performance
    performers = []
    for row in latest:
        try:
            change_pct = float(row.get("change_pct", 0))
            performers.append({
                "symbol": row.get("symbol", "?"),
                "price": float(row.get("price", 0)),
                "change_pct": change_pct,
            })
        except (ValueError, TypeError):
            continue

    if performers:
        performers.sort(key=lambda x: x["change_pct"], reverse=True)
        best = performers[0]
        worst = performers[-1]

        insights.append({
            "type": "portfolio_highlight",
            "title": f"{best['symbol']} leads portfolio with +{best['change_pct']:.1f}%",
            "narrative": f"Best performer: {best['symbol']} at ${best['price']:,.2f} (+{best['change_pct']:.1f}%). "
                        f"Worst: {worst['symbol']} at ${worst['price']:,.2f} ({worst['change_pct']:.1f}%).",
            "data_points": {"best": best, "worst": worst, "total_stocks": len(performers)},
            "actionability": 40,
            "content_hook": f"📊 Portfolio update: {best['symbol']} outperforms at +{best['change_pct']:.1f}%",
        })

        # All green?
        all_positive = all(p["change_pct"] > 0 for p in performers)
        if all_positive and len(performers) >= 3:
            insights.append({
                "type": "market_event",
                "title": "All portfolio stocks in the green",
                "narrative": f"All {len(performers)} tracked stocks are up today — rare broad-based rally.",
                "data_points": {"count": len(performers)},
                "actionability": 70,
                "content_hook": "🟢 Everything's up — what's driving the rally?",
            })

    return insights


def extract_defi_insights(latest: list, history: list) -> list:
    """Extract DeFi yield insights."""
    insights = []
    if not latest:
        return insights

    # Top yield pools
    pools = []
    for row in latest:
        try:
            apy = float(row.get("apy", 0))
            tvl = float(row.get("tvl_usd", 0))
            if apy > 0 and tvl > 1000000:  # Filter noise
                pools.append({
                    "pool": f"{row.get('project', '?')}/{row.get('symbol', '?')}",
                    "chain": row.get("chain", "?"),
                    "apy": apy,
                    "tvl_usd": tvl,
                })
        except (ValueError, TypeError):
            continue

    if pools:
        pools.sort(key=lambda x: x["apy"], reverse=True)
        top = pools[0]
        insights.append({
            "type": "yield_opportunity",
            "title": f"Top DeFi yield: {top['pool']} at {top['apy']:.1f}% APY",
            "narrative": f"Highest yield with >$1M TVL: {top['pool']} on {top['chain']} "
                        f"offering {top['apy']:.1f}% APY with ${top['tvl_usd']:,.0f} TVL.",
            "data_points": {"top_pools": pools[:5]},
            "actionability": min(100, int(top["apy"])),
            "content_hook": f"🏦 DeFi alert: {top['apy']:.0f}% APY on {top['chain']} — is it safe?",
        })

        # High-yield chains
        chain_avg = {}
        for p in pools:
            chain_avg.setdefault(p["chain"], []).append(p["apy"])
        chain_rank = [(c, sum(aps)/len(aps)) for c, aps in chain_avg.items()]
        chain_rank.sort(key=lambda x: x[1], reverse=True)
        if chain_rank:
            best_chain = chain_rank[0]
            insights.append({
                "type": "chain_comparison",
                "title": f"{best_chain[0]} leads with {best_chain[1]:.1f}% average APY",
                "narrative": f"Average yields by chain: {', '.join(f'{c} ({avg:.1f}%)' for c, avg in chain_rank[:3])}.",
                "data_points": {"chain_averages": chain_rank[:5]},
                "actionability": 55,
                "content_hook": f"🔗 Best chain for yields: {best_chain[0]} at {best_chain[1]:.0f}% avg",
            })

    return insights


def extract_github_insights(latest: list, history: list) -> list:
    """Extract GitHub trending insights."""
    insights = []
    if not latest:
        return insights

    # Top repos by stars
    repos = []
    for row in latest:
        try:
            repos.append({
                "name": row.get("name", "?"),
                "stars": int(row.get("stars", 0)),
                "language": row.get("language", "?"),
                "description": (row.get("description", "") or "")[:100],
                "url": row.get("url", ""),
            })
        except (ValueError, TypeError):
            continue

    if repos:
        repos.sort(key=lambda x: x["stars"], reverse=True)
        top = repos[0]
        insights.append({
            "type": "trending_repo",
            "title": f"Top trending: {top['name']} with {top['stars']:,} stars",
            "narrative": f"{top['name']} ({top['language']}) is the hottest repo right now with "
                        f"{top['stars']:,} stars. {top['description'][:80]}.",
            "data_points": {"top_repos": repos[:5]},
            "actionability": 65,
            "content_hook": f"🔥 {top['name']} is blowing up — {top['stars']:,} stars and counting",
        })

        # Language distribution
        lang_count = {}
        for r in repos:
            lang_count[r["language"]] = lang_count.get(r["language"], 0) + 1
        if lang_count:
            top_lang = max(lang_count, key=lang_count.get)
            insights.append({
                "type": "language_trend",
                "title": f"{top_lang.title()} dominates trending with {lang_count[top_lang]} repos",
                "narrative": f"Language breakdown: {', '.join(f'{l} ({c})' for l, c in sorted(lang_count.items(), key=lambda x: -x[1])[:4])}.",
                "data_points": {"languages": lang_count},
                "actionability": 50,
                "content_hook": f"💻 {top_lang.title()} is the language of the week",
            })

    # Growth detection from history
    if history and len(history) >= 2:
        # Find repos that appeared recently with high stars
        recent_names = {r.get("name") for r in repos if r.get("name")}
        history_names = set()
        for row in history[:-len(repos)] if len(history) > len(repos) else history[:100]:
            history_names.add(row.get("name"))
        new_hot = [r for r in repos if r.get("name") not in history_names and r["stars"] >= 100]
        if new_hot:
            insights.append({
                "type": "new_opportunity",
                "title": f"{len(new_hot)} new hot repos appeared this week",
                "narrative": f"New repos with 100+ stars: {', '.join(r['name'] for r in new_hot[:3])}.",
                "data_points": {"new_repos": new_hot[:5]},
                "actionability": 75,
                "content_hook": f"🆕 {len(new_hot)} new repos hit trending — early mover opportunity",
            })

    return insights


def extract_job_insights(latest: list, history: list) -> list:
    """Extract job market insights."""
    insights = []
    if not latest:
        return insights

    # High-paying jobs
    high_pay = []
    for row in latest:
        salary = row.get("salary", "")
        if salary and "$" in salary:
            # Extract max salary
            import re
            nums = re.findall(r'\$(\d+)[kK]?', salary)
            if nums:
                max_sal = max(int(n) for n in nums)
                if "k" in salary.lower() or max_sal < 1000:
                    max_sal *= 1000
                high_pay.append({
                    "title": row.get("title", "?")[:50],
                    "company": row.get("company", "?"),
                    "salary": salary,
                    "salary_num": max_sal,
                    "url": row.get("url", ""),
                })

    if high_pay:
        high_pay.sort(key=lambda x: x["salary_num"], reverse=True)
        top = high_pay[0]
        insights.append({
            "type": "high_paying_job",
            "title": f"Top job: {top['title']} at {top['company']} — {top['salary']}",
            "narrative": f"Highest-paying role right now: {top['title']} at {top['company']} "
                        f"offering {top['salary']}.",
            "data_points": {"top_jobs": high_pay[:5]},
            "actionability": 80,
            "content_hook": f"💰 {top['company']} is paying {top['salary']} for {top['title']}",
        })

    # Source distribution (which boards are active)
    sources = {}
    for row in latest:
        src = row.get("source", "?")
        sources[src] = sources.get(src, 0) + 1
    if sources:
        top_source = max(sources, key=sources.get)
        insights.append({
            "type": "market_activity",
            "title": f"{top_source} is most active board with {sources[top_source]} listings",
            "narrative": f"Job board activity: {', '.join(f'{s} ({c})' for s, c in sorted(sources.items(), key=lambda x: -x[1])[:4])}.",
            "data_points": {"sources": sources},
            "actionability": 30,
            "content_hook": f"📋 Where the jobs are: {top_source} leads with {sources[top_source]} listings",
        })

    # Keyword demand
    keywords = {}
    for row in latest:
        kw = row.get("keyword", "")
        if kw:
            keywords[kw] = keywords.get(kw, 0) + 1
    if keywords:
        top_kw = max(keywords, key=keywords.get)
        insights.append({
            "type": "skill_demand",
            "title": f"'{top_kw}' is most in-demand skill with {keywords[top_kw]} jobs",
            "narrative": f"Top skills by job count: {', '.join(f'{k} ({c})' for k, c in sorted(keywords.items(), key=lambda x: -x[1])[:5])}.",
            "data_points": {"keywords": keywords},
            "actionability": 70,
            "content_hook": f"🎯 Hottest skill: {top_kw} — {keywords[top_kw]} open roles",
        })

    return insights


def extract_exchange_rate_insights(latest: list, history: list) -> list:
    """Extract exchange rate insights."""
    insights = []
    if not latest:
        return insights

    # Find THB rates
    thb_rates = []
    for row in latest:
        if row.get("base") == "THB" or row.get("symbol", "").startswith("THB"):
            try:
                rate = float(row.get("rate", 0))
                currency = row.get("currency", row.get("symbol", "?").replace("THB", ""))
                thb_rates.append({"currency": currency, "rate": rate})
            except (ValueError, TypeError):
                continue

    if thb_rates:
        rates_text = ", ".join(f"{r['currency']}={r['rate']:.4f}" for r in thb_rates[:5])
        insights.append({
            "type": "rate_snapshot",
            "title": f"THB exchange rates: {len(thb_rates)} currencies tracked",
            "narrative": f"Current THB rates: {rates_text}.",
            "data_points": {"rates": thb_rates},
            "actionability": 40,
            "content_hook": f"💱 THB update: {thb_rates[0]['currency']} at {thb_rates[0]['rate']:.4f}",
        })

    return insights


def extract_marketplace_insights(latest: list, history: list) -> list:
    """Extract a bounded Kaidee marketplace snapshot."""
    if not latest:
        return []

    categories: dict[str, int] = {}
    priced: list[dict[str, Any]] = []
    for row in latest:
        category = str(row.get("category") or "ไม่ระบุ").strip()
        categories[category] = categories.get(category, 0) + 1
        try:
            price = float(row.get("price_thb", 0))
        except (TypeError, ValueError):
            continue
        if math.isfinite(price) and price > 0:
            priced.append({
                "listing_id": row.get("listing_id", ""),
                "title": str(row.get("title") or "")[:80],
                "price_thb": price,
                "category": category,
                "url": row.get("url", ""),
            })

    if not priced:
        return []
    priced.sort(key=lambda item: item["price_thb"])
    top_categories = sorted(categories.items(), key=lambda item: (-item[1], item[0]))[:5]
    cheapest = priced[0]
    return [{
        "type": "marketplace_snapshot",
        "title": f"Kaidee tracks {len(priced)} priced listings across {len(categories)} categories",
        "narrative": (
            f"The latest Kaidee capture contains {len(priced)} priced listings. "
            f"Most common categories: {', '.join(f'{name} ({count})' for name, count in top_categories)}. "
            f"Lowest captured price is ฿{cheapest['price_thb']:,.0f} for {cheapest['title'] or cheapest['listing_id']}."
        ),
        "data_points": {
            "total_listings": len(priced),
            "categories": dict(top_categories),
            "lowest_price": cheapest,
        },
        "actionability": 35,
        "content_hook": f"🛒 Kaidee snapshot: {len(priced)} priced listings tracked",
    }]


def extract_restaurant_insights(latest: list, history: list) -> list:
    """Extract a bounded Wongnai restaurant snapshot."""
    if not latest:
        return []
    categories: dict[str, int] = {}
    districts: dict[str, int] = {}
    locations = sorted({str(row.get("location") or "").strip() for row in latest if row.get("location")})
    is_bangkok = locations == ["bangkok"]
    scope_label = "Bangkok" if is_bangkok else "upcountry"
    for row in latest:
        for category in str(row.get("categories") or "").split(","):
            category = category.strip()
            if category:
                categories[category] = categories.get(category, 0) + 1
        district = str(row.get("district") or "ไม่ระบุ").strip()
        districts[district] = districts.get(district, 0) + 1
    top_categories = sorted(categories.items(), key=lambda item: (-item[1], item[0]))[:5]
    top_districts = sorted(districts.items(), key=lambda item: (-item[1], item[0]))[:5]
    return [{
        "type": "restaurant_snapshot",
        "title": f"Wongnai captured {len(latest)} {scope_label} restaurants",
        "narrative": (
            f"The latest Wongnai HTML capture contains {len(latest)} location-validated {scope_label} restaurants "
            f"across {len(districts)} district(s) and {len(locations)} configured location matcher(s)."
        ),
        "data_points": {
            "total_restaurants": len(latest),
            "locations": locations,
            "top_categories": dict(top_categories),
            "top_districts": dict(top_districts),
        },
        "actionability": 40,
        "content_hook": f"🍜 Wongnai {scope_label} snapshot: {len(latest)} restaurants captured",
    }]


def extract_news_insights(latest: list, history: list) -> list:
    """Extract a bounded Matichon RSS snapshot."""
    if not latest:
        return []

    topics: dict[str, int] = {}
    for row in latest:
        categories = str(row.get("categories") or "").split(",")
        for category in categories:
            category = category.strip()
            if category:
                topics[category] = topics.get(category, 0) + 1
    top_topics = sorted(topics.items(), key=lambda item: (-item[1], item[0]))[:5]
    topic_text = ", ".join(f"{name} ({count})" for name, count in top_topics) or "ไม่มีหมวดหมู่"
    return [{
        "type": "news_snapshot",
        "title": f"Matichon captured {len(latest)} attributed articles",
        "narrative": f"The latest Matichon RSS capture contains {len(latest)} articles. Top topics: {topic_text}.",
        "data_points": {"total_articles": len(latest), "top_topics": dict(top_topics)},
        "actionability": 35,
        "content_hook": f"📰 Matichon update: {len(latest)} articles across current topics",
    }]


def extract_business_news_insights(latest: list, history: list) -> list:
    """Extract a bounded Bangkok Post Business snapshot."""
    if not latest:
        return []
    sections = {}
    for row in latest:
        section = str(row.get("section") or "business").strip()
        sections[section] = sections.get(section, 0) + 1
    return [{
        "type": "business_news_snapshot",
        "title": f"Bangkok Post Business captured {len(latest)} articles",
        "narrative": (
            f"The latest Bangkok Post Business RSS capture contains {len(latest)} attributed articles "
            f"across {len(sections)} section(s)."
        ),
        "data_points": {"total_articles": len(latest), "sections": sections},
        "actionability": 40,
        "content_hook": f"💼 Business news update: {len(latest)} articles captured",
    }]


def extract_tech_news_insights(latest: list, history: list) -> list:
    """Extract a bounded Blognone technology snapshot."""
    if not latest:
        return []
    topics = {}
    for row in latest:
        for topic in str(row.get("topics") or "").split(","):
            topic = topic.strip()
            if topic:
                topics[topic] = topics.get(topic, 0) + 1
    top_topics = sorted(topics.items(), key=lambda item: (-item[1], item[0]))[:5]
    topic_text = ", ".join(f"{name} ({count})" for name, count in top_topics) or "ไม่มี topic metadata"
    return [{
        "type": "technology_news_snapshot",
        "title": f"Blognone captured {len(latest)} technology articles",
        "narrative": f"The latest Blognone feed capture contains {len(latest)} attributed technology articles. Topics: {topic_text}.",
        "data_points": {"total_articles": len(latest), "top_topics": dict(top_topics)},
        "actionability": 40,
        "content_hook": f"💻 Tech news update: {len(latest)} Blognone articles captured",
    }]


def extract_property_insights(latest: list, history: list) -> list:
    """Extract real estate insights."""
    insights = []
    if not latest:
        return insights

    # Count by type
    types = {}
    for row in latest:
        ptype = row.get("type", "?")
        types[ptype] = types.get(ptype, 0) + 1

    if types:
        top_type = max(types, key=types.get)
        insights.append({
            "type": "market_snapshot",
            "title": f"{len(latest)} property listings — {top_type} most common",
            "narrative": f"Listing types: {', '.join(f'{t} ({c})' for t, c in sorted(types.items(), key=lambda x: -x[1])[:4])}.",
            "data_points": {"types": types, "total": len(latest)},
            "actionability": 35,
            "content_hook": f"🏠 Bangkok property market: {len(latest)} listings tracked",
        })

    return insights


def extract_seo_insights(latest: list, history: list) -> list:
    """Extract SEO ranking insights."""
    insights = []
    if not latest:
        return insights

    insights.append({
        "type": "seo_snapshot",
        "title": f"Tracking {len(latest)} keywords for SEO",
        "narrative": f"Monitoring {len(latest)} keywords across search engines.",
        "data_points": {"keywords_tracked": len(latest)},
        "actionability": 25,
        "content_hook": f"🔍 SEO tracker: {len(latest)} keywords monitored",
    })

    return insights


def extract_ai_tools_insights(latest: list, history: list) -> list:
    """Extract AI tools insights."""
    insights = []
    if not latest:
        return insights

    # Category breakdown
    cats = {}
    for row in latest:
        values = str(row.get("categories") or row.get("category") or row.get("source_category") or "?").split(",")
        for value in values:
            cat = value.strip() or "?"
            cats[cat] = cats.get(cat, 0) + 1

    if cats:
        insights.append({
            "type": "ai_landscape",
            "title": f"{len(latest)} AI tools tracked across {len(cats)} categories",
            "narrative": f"AI tool categories: {', '.join(f'{c} ({n})' for c, n in sorted(cats.items(), key=lambda x: -x[1])[:5])}.",
            "data_points": {"categories": cats, "total": len(latest)},
            "actionability": 50,
            "content_hook": f"🤖 AI tools landscape: {len(latest)} tools in {len(cats)} categories",
        })

    return insights


# ─── Main Engine ────────────────────────────────────────────────────────

EXTRACTORS = {
    "crypto": extract_crypto_insights,
    "stocks": extract_stock_insights,
    "defi": extract_defi_insights,
    "github_trending": extract_github_insights,
    "jobs": extract_job_insights,
    "exchange_rates": extract_exchange_rate_insights,
    "marketplace": extract_marketplace_insights,
    "restaurants": extract_restaurant_insights,
    "restaurants_upcountry": extract_restaurant_insights,
    "news": extract_news_insights,
    "business_news": extract_business_news_insights,
    "tech_news": extract_tech_news_insights,
    "property": extract_property_insights,
    "seo": extract_seo_insights,
    "ai_tools": extract_ai_tools_insights,
}


def generate_insights(niches: list = None, min_score: int = 0) -> dict:
    """Generate insights for all (or specified) niches."""
    all_insights = {}
    total_insights = 0

    target_niches = niches or list(SCRAPER_PATHS.keys())

    for niche in target_niches:
        if niche not in SCRAPER_PATHS:
            continue

        paths = SCRAPER_PATHS[niche]
        latest = load_csv(paths["latest"]) if paths.get("latest") else []
        history = (
            load_csv(paths["history"], max_rows=5000)
            if paths.get("history")
            else []
        )

        extractor = EXTRACTORS.get(niche)
        if not extractor:
            continue

        insights = extractor(latest, history)

        # Filter by min score
        if min_score > 0:
            insights = [i for i in insights if i.get("actionability", 0) >= min_score]

        if insights:
            all_insights[niche] = {
                "niche_name": NICHE_NAMES.get(niche, niche),
                "data_rows": len(latest),
                "insights": insights,
                "top_insight": max(insights, key=lambda x: x.get("actionability", 0)) if insights else None,
            }
            total_insights += len(insights)

    # Summary
    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "niches_analyzed": len(all_insights),
        "total_insights": total_insights,
        "top_insights_across_all": [],
    }

    # Collect top insights across all niches
    all_top = []
    for niche, data in all_insights.items():
        for insight in data["insights"]:
            insight["niche"] = niche
            insight["niche_name"] = data["niche_name"]
            all_top.append(insight)

    all_top.sort(key=lambda x: x.get("actionability", 0), reverse=True)
    summary["top_insights_across_all"] = all_top[:10]

    return {
        "summary": summary,
        "by_niche": all_insights,
    }


def generate_markdown(result: dict) -> str:
    """Generate human-readable markdown summary."""
    lines = []
    summary = result["summary"]
    lines.append(f"# 🧠 Insight Report — {summary['generated_at']}")
    lines.append(f"\n**{summary['niches_analyzed']} niches** analyzed → **{summary['total_insights']} insights** extracted\n")

    # Top 10 across all
    lines.append("## 🔥 Top 10 Insights (All Niches)\n")
    for i, insight in enumerate(summary["top_insights_across_all"][:10], 1):
        score = insight.get("actionability", 0)
        bar = "█" * (score // 10) + "░" * (10 - score // 10)
        lines.append(f"{i}. **{insight['title']}**")
        lines.append(f"   - Niche: {insight.get('niche_name', '?')} | Actionability: {bar} {score}/100")
        lines.append(f"   - {insight.get('narrative', '')}")
        lines.append(f"   - 💡 {insight.get('content_hook', '')}")
        lines.append("")

    # Per-niche breakdown
    lines.append("## 📊 By Niche\n")
    for niche, data in result["by_niche"].items():
        lines.append(f"### {data['niche_name']} ({data['data_rows']} data rows, {len(data['insights'])} insights)\n")
        for insight in data["insights"]:
            score = insight.get("actionability", 0)
            lines.append(f"- **{insight['title']}** (actionability: {score}/100)")
            lines.append(f"  - {insight.get('narrative', '')}")
            lines.append(f"  - 💡 `{insight.get('content_hook', '')}`")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate insights from scraper data")
    parser.add_argument("--niches", default=None, help="Comma-separated niches to analyze (default: all)")
    parser.add_argument("--min-score", type=int, default=0, help="Minimum actionability score (0-100)")
    parser.add_argument("--json-only", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    niches = [n.strip() for n in args.niches.split(",")] if args.niches else None

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Insight Extraction Engine")
    print(f"  Analyzing {len(niches) if niches else 'all'} niches...")

    result = generate_insights(niches=niches, min_score=args.min_score)

    # Save JSON
    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = BRIEFINGS_DIR / "insights.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"  Saved insights JSON to {json_path}")

    # Save Markdown
    md_path = BRIEFINGS_DIR / "insights.md"
    md_content = generate_markdown(result)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"  Saved insights report to {md_path}")

    # Print summary
    s = result["summary"]
    print(f"\n  Results: {s['niches_analyzed']} niches → {s['total_insights']} insights")
    print(f"\n  Top 5 insights:")
    for i, insight in enumerate(s["top_insights_across_all"][:5], 1):
        print(f"    {i}. [{insight.get('actionability', 0):3d}/100] {insight['title']}")

    print("\n  Done.")


if __name__ == "__main__":
    main()
