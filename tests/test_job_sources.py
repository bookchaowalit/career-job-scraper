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
