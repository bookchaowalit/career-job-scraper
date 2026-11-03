"""RemoteOK, HN Who is hiring and PeoplePerHour return usable postings.

Found 2026-11-03 from the jobs Gold marts: RemoteOK had sent nothing since
2026-08-18, HN_WhoIsHiring rows had no URL and its newest posting was from
2020, and PeoplePerHour's posted date never parsed.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import scrape_job_postings as scraper  # noqa: E402

NOW = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, payload=None, text=""):
        self._payload = payload
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


REMOTEOK_FEED = [
    {"legal": "API terms"},
    {"position": "Senior Python Engineer", "company": "Acme", "url": "https://remoteok.com/remote-jobs/1",
     "date": "2026-11-02T10:00:00+00:00", "tags": ["python", "backend"], "location": ""},
    {"position": "React Developer", "company": "Beta", "url": "https://remoteok.com/remote-jobs/2",
     "date": "2026-11-01T10:00:00+00:00", "tags": ["react", "javascript"], "location": "Worldwide"},
    {"position": "Sales Manager", "company": "Gamma", "url": "https://remoteok.com/remote-jobs/3",
     "date": "2026-11-01T09:00:00+00:00", "tags": ["sales"], "location": ""},
]


class RemoteOKTests(unittest.TestCase):
    def setUp(self):
        scraper._REMOTEOK_CACHE = None

    def test_multi_word_keywords_filter_one_feed_locally(self):
        # RemoteOK returns 0 jobs for tag="python contract"; fetch the feed once, filter here.
        calls = []

        def fake_get(url, **kwargs):
            calls.append(url)
            return FakeResponse(REMOTEOK_FEED)

        with mock.patch.object(scraper._http, "get", side_effect=fake_get):
            python_jobs = scraper.fetch_remoteok_api("python contract")
            react_jobs = scraper.fetch_remoteok_api("react freelance")
        self.assertEqual([job["title"] for job in python_jobs], ["Senior Python Engineer"])
        self.assertEqual([job["title"] for job in react_jobs], ["React Developer"])
        self.assertEqual(len(calls), 1)
        self.assertNotIn("tag=", calls[0])
        self.assertEqual(python_jobs[0]["posted"], "2026-11-02")
        self.assertEqual(python_jobs[0]["source"], "RemoteOK")
        self.assertEqual(python_jobs[0]["location"], "Remote")


WWR_RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Acme: Senior Python Developer</title><region>Anywhere in the World</region>
 <skills>Python, Django</skills><category>Back-End Programming</category>
 <pubDate>Mon, 02 Nov 2026 18:18:39 +0000</pubDate><link>https://weworkremotely.com/remote-jobs/acme-python</link></item>
<item><title>Beta: Marketing Manager</title><region>USA Only</region><skills></skills><category>Sales and Marketing</category>
 <pubDate>Sun, 01 Nov 2026 10:00:00 +0000</pubDate><link>https://weworkremotely.com/remote-jobs/beta-marketing</link></item>
</channel></rss>"""

JOBICY_FEED = {"success": True, "jobs": [
    {"jobTitle": "React Engineer", "companyName": "Gamma", "jobGeo": "Anywhere", "url": "https://jobicy.com/jobs/1",
     "pubDate": "2026-11-03 08:00:00", "jobIndustry": ["Engineering"], "jobType": ["contract"]},
    {"jobTitle": "Account Executive", "companyName": "Delta", "jobGeo": "USA", "url": "https://jobicy.com/jobs/2",
     "pubDate": "2026-11-02 08:00:00", "jobIndustry": ["Sales"], "jobType": ["full-time"]},
]}

ARC_HTML = (
    '<script id="__NEXT_DATA__" type="application/json">'
    '{"props":{"pageProps":{"arcJobs":[{"title":"Senior Python Engineer","categories":[{"name":"Backend"}],'
    '"tags":["python"],"company":{"name":"Epsilon"},"urlString":"epsilon-python","postedAt":1793616312}],"externalJobs":[]}}}'
    "</script>"
)


class FeedSourcesTests(unittest.TestCase):
    def setUp(self):
        scraper.reset_run_caches()

    def tearDown(self):
        scraper.reset_run_caches()

    def test_weworkremotely_reads_the_rss_feed_once_and_filters_locally(self):
        calls = []

        def fake_get(url, **kwargs):
            calls.append(url)
            return FakeResponse(text=WWR_RSS)

        with mock.patch.object(scraper._http, "get", side_effect=fake_get):
            python_jobs = scraper.fetch_weworkremotely("python contract")
            scraper.fetch_weworkremotely("react freelance")
        self.assertEqual(calls, ["https://weworkremotely.com/remote-jobs.rss"])
        self.assertEqual(len(python_jobs), 1)
        job = python_jobs[0]
        self.assertEqual((job["company"], job["title"]), ("Acme", "Senior Python Developer"))
        self.assertEqual((job["posted"], job["location"], job["source"]), ("2026-11-02", "Anywhere in the World", "WeWorkRemotely"))
        self.assertEqual(job["url"], "https://weworkremotely.com/remote-jobs/acme-python")

    def test_jobicy_fetches_one_feed_without_a_phrase_tag(self):
        # tag="AI automation contract" answered 400 and tag="python contract" nothing.
        calls = []

        def fake_get(url, **kwargs):
            calls.append(url)
            return FakeResponse(JOBICY_FEED)

        with mock.patch.object(scraper._http, "get", side_effect=fake_get):
            react = scraper.fetch_jobicy("react freelance")
            scraper.fetch_jobicy("AI automation contract")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("tag=", calls[0])
        self.assertEqual([j["title"] for j in react], ["React Engineer"])
        self.assertEqual(react[0]["posted"], "2026-11-03")

    def test_arc_matches_keyword_words_not_the_whole_phrase(self):
        calls = []

        def fake_get(url, **kwargs):
            calls.append(url)
            return FakeResponse(text=ARC_HTML)

        with mock.patch.object(scraper._http, "get", side_effect=fake_get):
            jobs = scraper.fetch_arc("python contract")
            scraper.fetch_arc("react freelance")
        self.assertEqual([j["title"] for j in jobs], ["Senior Python Engineer"])
        self.assertEqual(jobs[0]["posted"], "2026-11-02")  # postedAt is Unix seconds
        self.assertEqual(len(calls), 1)


class RunCacheTests(unittest.TestCase):
    def tearDown(self):
        scraper._REMOTEOK_CACHE = None
        scraper._PEOPLEPERHOUR_CACHE = None

    def test_each_scraper_run_fetches_fresh_feeds(self):
        # A long-lived scheduler process calls main() every 6 h; module caches
        # must not carry the first run's feed into later runs.
        scraper._REMOTEOK_CACHE = [{"position": "Stale Python Job", "url": "https://remoteok.com/old", "tags": []}]
        scraper._PEOPLEPERHOUR_CACHE = [{"title": "stale", "url": "u", "context": ""}]
        with mock.patch.object(scraper._http, "get", return_value=FakeResponse(REMOTEOK_FEED)), \
                mock.patch.object(scraper, "save_jobs"), \
                mock.patch.object(scraper, "load_previous_urls", return_value=set()), \
                mock.patch.object(scraper, "append_history"), \
                mock.patch.object(scraper, "archive_old_jobs", return_value=0):
            stats = scraper.main(boards=["remoteok-api"], keywords=["python contract"])
        self.assertEqual(stats["per_board"], {"remoteok-api": 1})
        self.assertNotIn("Stale", str(scraper._REMOTEOK_CACHE))
        self.assertIsNone(scraper._PEOPLEPERHOUR_CACHE)


HN_STORIES = {"hits": [
    {"title": "Ask HN: Who wants to be hired? (November 2026)", "objectID": "50338726"},
    {"title": "Ask HN: Who is hiring? (November 2026)", "objectID": "50338728"},
]}
HN_COMMENTS = {"hits": [
    {"objectID": "111", "created_at": "2026-11-02T16:00:00Z",
     "comment_text": "Acme | Remote | Python<p>We build things. Apply: <a href=\"https:&#x2F;&#x2F;acme.example&#x2F;jobs\">x</a>"},
    {"objectID": "222", "created_at": "2026-11-02T17:00:00Z",
     "comment_text": "Beta Corp | Remote (US) | Full-time<p>Email us at jobs at beta dot com"},
]}


class HNWhoIsHiringTests(unittest.TestCase):
    def test_uses_the_newest_who_is_hiring_thread_by_date(self):
        calls = []

        def fake_get(url, params=None, **kwargs):
            calls.append((url, params))
            return FakeResponse(HN_STORIES if "story" in (params or {}).get("tags", "") and "author" in params["tags"] else HN_COMMENTS)

        with mock.patch.object(scraper._http, "get", side_effect=fake_get):
            jobs = scraper.fetch_hn_who_is_hiring("python")
        self.assertIn("search_by_date", calls[0][0])
        self.assertIn("author_whoishiring", calls[0][1]["tags"])
        self.assertIn("story_50338728", calls[1][1]["tags"])  # "Who is hiring", not "Who wants to be hired"
        self.assertEqual(len(jobs), 2)

    def test_every_posting_has_a_url(self):
        def fake_get(url, params=None, **kwargs):
            return FakeResponse(HN_STORIES if "author_whoishiring" in (params or {}).get("tags", "") else HN_COMMENTS)

        with mock.patch.object(scraper._http, "get", side_effect=fake_get):
            jobs = scraper.fetch_hn_who_is_hiring("python")
        self.assertEqual(jobs[0]["url"], "https://acme.example/jobs")
        # No link in the comment: the HN comment itself is the posting.
        self.assertEqual(jobs[1]["url"], "https://news.ycombinator.com/item?id=222")
        self.assertEqual(jobs[1]["company"], "Beta Corp")
        self.assertEqual(jobs[1]["posted"], "2026-11-02")


PPH_HTML = """<html><body>
<div class="item__container"><a href="/freelance-jobs/technology-programming/web/build-a-python-api-4528600">Build a Python API for us</a>
 by Jane D. $500 Python Django work 3 days ago</div>
<div class="item__container"><a href="/freelance-jobs/technology-programming/web/fix-my-react-site-4528601">Fix my React site please</a>
 by Joe B. $200 React work</div>
<script>window.__STATE__={"jobs":[
 {"id":4528600,"url":"https:\\u002F\\u002Fwww.peopleperhour.com\\u002Ffreelance-jobs\\u002Ftechnology-programming\\u002Fweb\\u002Fbuild-a-python-api-4528600","item_type":"job","posted_dt":"2026-10-28 02:07:37"},
 {"id":4528601,"url":"https:\\u002F\\u002Fwww.peopleperhour.com\\u002Ffreelance-jobs\\u002Ftechnology-programming\\u002Fweb\\u002Ffix-my-react-site-4528601","item_type":"job","posted_dt":"2026-11-01 09:00:00"}
]}</script></body></html>"""


class PeoplePerHourPageTests(unittest.TestCase):
    def setUp(self):
        scraper._PEOPLEPERHOUR_CACHE = None

    def tearDown(self):
        scraper._PEOPLEPERHOUR_CACHE = None

    def test_posted_date_comes_from_the_page_json(self):
        with mock.patch.object(scraper._http, "get", return_value=FakeResponse(text=PPH_HTML)):
            cards = scraper._load_peopleperhour_cards()
        posted = {card["url"].rsplit("-", 1)[-1]: card["posted"] for card in cards}
        self.assertEqual(posted, {"4528600": "2026-10-28", "4528601": "2026-11-01"})


class PeoplePerHourDateTests(unittest.TestCase):
    def test_relative_posted_text_becomes_an_iso_date(self):
        cases = {
            "3 days ago": "2026-10-31",
            "posted 5 hours ago": "2026-11-03",
            "10 hours ago": "2026-11-02",
            "minutes ago": "2026-11-03",
            "1 day ago": "2026-11-02",
            "": "",
            "yesterday-ish": "",
        }
        for text, expected in cases.items():
            self.assertEqual(scraper.relative_posted_date(text, now=NOW), expected, text)


if __name__ == "__main__":
    unittest.main()
