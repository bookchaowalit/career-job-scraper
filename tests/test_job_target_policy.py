from __future__ import annotations

import csv
import asyncio
import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from filter_job_matches import JobMatchFilter, main as filter_matches  # noqa: E402
from auto_promote_jobs import promote_jobs  # noqa: E402
from classify_jobs import classify_country, classify_job_type  # noqa: E402
from cron_scheduler import get_daily_commands  # noqa: E402
from match_jobs import score_job as score_legacy_job  # noqa: E402
from scrape_job_postings import fetch_peopleperhour  # noqa: E402
from job_target_policy import (  # noqa: E402
    APPROVED,
    PASS,
    REJECT,
    VERIFY,
    is_approved_for_submission,
    qualify_job,
)
from job_role_relevance import contains_term, evidence_tags, is_relevant_role  # noqa: E402


class JobTargetPolicyTests(unittest.TestCase):
    def test_short_skill_aliases_do_not_match_inside_unrelated_words(self):
        self.assertFalse(contains_term("copywriter", "py"))
        self.assertFalse(contains_term("restoration", "rest"))
        self.assertTrue(contains_term("Python + React.js", "python"))
        self.assertTrue(contains_term("REST API", "rest"))

    def test_search_keyword_is_not_employment_or_skill_evidence(self):
        job = {
            "title": "Senior Python Engineer",
            "location": "Remote",
            "source": "RemoteOK",
            "keyword": "python contract",
            "tags": "python contract",
        }
        self.assertEqual(evidence_tags(job), "")
        self.assertEqual(qualify_job(job)["employment_type"], "Unknown")
        clean_job = {**job, "keyword": "", "tags": ""}
        self.assertEqual(score_legacy_job(job)[0], score_legacy_job(clean_job)[0])

    def test_role_gate_rejects_writers_and_accepts_target_roles(self):
        self.assertFalse(is_relevant_role({"title": "Freelance Copywriter", "tags": "REST"}))
        self.assertTrue(is_relevant_role({"title": "Contract Senior Web Engineer"}))
        self.assertFalse(is_relevant_role({"title": "Inside Sales Contractor", "tags": "financial services"}))
        self.assertTrue(is_relevant_role({"title": "Business Development Manager", "tags": "SaaS, API"}))
        self.assertTrue(
            is_relevant_role(
                {
                    "title": "Open Source Contributor",
                    "tags": "Open-Source-Developer,Open-Source-Engineer",
                }
            )
        )
        self.assertTrue(
            is_relevant_role(
                {
                    "title": "Community & Advocacy Fellowship",
                    "tags": "eBPF, open-source",
                    "description": "Technical tutorials and contributor mentorship.",
                }
            )
        )

    def test_worldwide_freelance_is_pass_but_not_submission_approval(self):
        result = qualify_job(
            {
                "title": "Freelance Python Developer",
                "location": "Worldwide",
                "source": "PeoplePerHour",
                "tags": "python,freelance",
            }
        )
        self.assertEqual(result["qualification_status"], PASS)
        self.assertEqual(result["employment_type"], "Freelance")
        self.assertEqual(result["application_readiness"], "REVIEW_REQUIRED")
        self.assertFalse(is_approved_for_submission(result))

    def test_explicit_approval_only_counts_after_pass(self):
        result = qualify_job(
            {
                "title": "Independent Contractor - FastAPI",
                "location": "Thailand / Remote",
                "source": "Direct",
                "notes": "Flexible hours",
                "application_readiness": APPROVED,
            }
        )
        self.assertEqual(result["qualification_status"], PASS)
        self.assertTrue(is_approved_for_submission(result))

    def test_thai_full_time_is_rejected(self):
        result = qualify_job(
            {
                "title": "Full-time Software Engineer",
                "location": "Bangkok, Thailand",
                "source": "JobThai",
            }
        )
        self.assertEqual(result["qualification_status"], REJECT)
        self.assertIn("thai_full_time_not_targeted", result["qualification_reasons"])

    def test_foreign_full_time_is_verify(self):
        result = qualify_job(
            {
                "title": "Full-time Backend Engineer",
                "location": "Worldwide",
                "source": "RemoteOK",
            }
        )
        self.assertEqual(result["qualification_status"], VERIFY)
        self.assertIn("foreign_full_time_requires_review", result["qualification_reasons"])

    def test_unknown_remote_type_is_verify(self):
        result = qualify_job(
            {"title": "Python Developer", "location": "Remote", "source": "RemoteOK"}
        )
        self.assertEqual(result["qualification_status"], VERIFY)
        self.assertEqual(result["employment_type"], "Unknown")

    def test_human_evidence_can_promote_remote_contract_from_verify_to_pass(self):
        result = qualify_job(
            {
                "title": "Contract Browser Automation Engineer",
                "location": "Remote",
                "source": "Arc.dev",
                "verified_employment_type": "contract",
                "verified_thailand_eligibility": "YES",
                "verified_work_arrangement": "remote",
                "verified_concurrent_employment": "COMPATIBLE",
                "verified_engagement_boundary": "CONTRACTOR",
            }
        )
        self.assertEqual(result["qualification_status"], PASS)
        self.assertEqual(result["employment_type"], "Contract")

    def test_bounded_volunteer_is_review_only_and_never_submission_ready(self):
        result = qualify_job(
            {
                "title": "Volunteer Python Developer",
                "location": "Worldwide",
                "source": "Catchafire",
                "description": "Build a scoped website over 6 weeks with a mentor.",
            }
        )
        self.assertEqual(result["employment_type"], "Volunteer")
        self.assertEqual(result["qualification_status"], VERIFY)
        self.assertEqual(result["application_readiness"], "REVIEW_REQUIRED")
        self.assertIn("unpaid_bridge_review_only_no_guaranteed_hire", result["qualification_reasons"])
        self.assertFalse(is_approved_for_submission(result))

    def test_bridge_rejects_upfront_fee_or_indefinite_unpaid_production_work(self):
        fee = qualify_job(
            {
                "title": "Volunteer Web Developer",
                "location": "Worldwide",
                "source": "Example",
                "description": "Pay an upfront fee to participate in this unpaid full-time role.",
            }
        )
        self.assertEqual(fee["employment_type"], "Volunteer")
        self.assertEqual(fee["qualification_status"], REJECT)
        self.assertIn("upfront_fee_or_income_share_not_accepted", fee["qualification_reasons"])
        self.assertIn("unpaid_indefinite_or_production_work_not_accepted", fee["qualification_reasons"])

    def test_bridge_does_not_reject_explicitly_free_program(self):
        result = qualify_job(
            {
                "title": "Volunteer Python Developer",
                "location": "Worldwide",
                "source": "Example",
                "description": "A bounded 6-week project with a mentor; no application fee and tuition-free.",
            }
        )
        self.assertEqual(result["qualification_status"], VERIFY)
        self.assertNotIn("upfront_fee_or_income_share_not_accepted", result["qualification_reasons"])

    def test_paid_bridge_can_pass_only_after_human_evidence_is_complete(self):
        result = qualify_job(
            {
                "title": "Open Source Fellowship Developer",
                "location": "Worldwide",
                "source": "Example",
                "verified_employment_type": "fellowship",
                "verified_thailand_eligibility": "YES",
                "verified_work_arrangement": "remote",
                "verified_concurrent_employment": "COMPATIBLE",
                "verified_engagement_boundary": "CONTRACTOR",
                "verified_bridge_compensation": "YES",
                "verified_scope_duration": "YES",
                "verified_mentor": "YES",
                "verified_conversion_path": "YES",
                "description": "12-week part-time program with a $500 stipend, mentor, and path to hire; asynchronous work.",
            }
        )
        self.assertEqual(result["employment_type"], "Fellowship")
        self.assertEqual(result["qualification_status"], PASS)
        self.assertIn("paid_bridge_with_verified_scope_and_conversion_path", result["qualification_reasons"])

    def test_contract_to_hire_without_scope_or_mentor_stays_verify(self):
        result = qualify_job(
            {
                "title": "Contract-to-hire Backend Engineer",
                "location": "Worldwide",
                "source": "RemoteOK",
                "description": "Paid 3-month contract-to-hire with flexible asynchronous hours.",
            }
        )
        self.assertEqual(result["employment_type"], "Contract-to-hire")
        self.assertEqual(result["qualification_status"], VERIFY)
        self.assertIn("verify_scope_duration_and_mentor", result["qualification_reasons"])

    def test_country_restriction_is_rejected(self):
        result = qualify_job(
            {
                "title": "Contract React Developer",
                "location": "United States",
                "source": "RemoteOK",
            }
        )
        self.assertEqual(result["qualification_status"], REJECT)
        self.assertEqual(result["thailand_eligibility"], "NO")

        country_codes = qualify_job(
            {
                "title": "Contract React Developer",
                "location": "CA, US",
                "source": "Arc.dev",
            }
        )
        self.assertEqual(country_codes["qualification_status"], REJECT)

    def test_onsite_and_exclusivity_are_rejected(self):
        onsite = qualify_job(
            {
                "title": "Contract Python Developer",
                "location": "Bangkok, Thailand - onsite",
            }
        )
        exclusive = qualify_job(
            {
                "title": "Freelance Developer",
                "location": "Worldwide",
                "notes": "Exclusive engagement; no outside employment",
            }
        )
        self.assertEqual(onsite["qualification_status"], REJECT)
        self.assertEqual(exclusive["qualification_status"], REJECT)

    def test_filter_excludes_rejects_and_orders_pass_before_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "jobs.csv"
            output_path = root / "matches.csv"
            fields = [
                "title", "company", "location", "salary", "url", "source",
                "keyword", "posted", "tags", "verified_thailand_eligibility",
                "verification_notes",
            ]
            rows = [
                {
                    "title": "Full-time Python Engineer",
                    "company": "Thai Co",
                    "location": "Bangkok, Thailand",
                    "url": "https://example.test/thai",
                    "source": "JobThai",
                    "keyword": "python",
                    "tags": "python",
                },
                {
                    "title": "Python Engineer",
                    "company": "Unknown Co",
                    "location": "Remote",
                    "url": "https://example.test/verify",
                    "source": "RemoteOK",
                    "keyword": "python",
                    "tags": "python",
                },
                {
                    "title": "Freelance Python Engineer",
                    "company": "Global Co",
                    "location": "Worldwide",
                    "url": "https://example.test/pass",
                    "source": "PeoplePerHour",
                    "keyword": "python",
                    "tags": "python,freelance",
                    "verified_thailand_eligibility": "YES",
                    "verification_notes": "Marketplace terms checked by reviewer",
                },
            ]
            with input_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

            count = filter_matches(
                min_score=5,
                top=5,
                input=str(input_path),
                output=str(output_path),
            )
            with output_path.open(encoding="utf-8") as handle:
                matches = list(csv.DictReader(handle))

            self.assertEqual(count, 2)
            self.assertEqual([row["qualification_status"] for row in matches], [PASS, VERIFY])
            self.assertEqual(matches[0]["verified_thailand_eligibility"], "YES")
            self.assertEqual(matches[0]["verification_notes"], "Marketplace terms checked by reviewer")
            self.assertNotIn("https://example.test/thai", {row["url"] for row in matches})

    def test_enriched_full_time_hours_downgrade_contract_to_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "jobs.csv"
            description_path = root / "descriptions.csv"
            output_path = root / "matches.csv"
            job = {
                "title": "Contract Senior Web Engineer",
                "company": "Example",
                "location": "Anywhere",
                "url": "https://example.test/contract",
                "source": "Jobicy",
                "tags": "",
            }
            with input_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(job))
                writer.writeheader()
                writer.writerow(job)
            with description_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["url", "description"])
                writer.writeheader()
                writer.writerow({
                    "url": job["url"],
                    "description": "This contract requires 40 hours per week.",
                })

            count = filter_matches(
                min_score=5,
                input=str(input_path),
                output=str(output_path),
                descriptions=str(description_path),
            )
            with output_path.open(encoding="utf-8") as handle:
                matches = list(csv.DictReader(handle))

            self.assertEqual(count, 1)
            self.assertEqual(matches[0]["qualification_status"], VERIFY)
            self.assertIn("verify_hours_do_not_overlap_current_role", matches[0]["qualification_reasons"])

    def test_promote_is_fail_closed_for_verify_or_missing_status(self):
        jobs = [
            {"url": "https://example.test/verify", "_score": 99, "qualification_status": VERIFY},
            {"url": "https://example.test/legacy", "_score": 99},
            {
                "url": "https://example.test/pass",
                "title": "Contract Python Engineer",
                "_score": 20,
                "qualification_status": PASS,
                "application_readiness": "REVIEW_REQUIRED",
            },
        ]
        entries = {}
        added = promote_jobs(jobs, entries, min_score=10, top_n=10)
        self.assertEqual([job["url"] for job in added], ["https://example.test/pass"])
        self.assertEqual(set(entries), {"https://example.test/pass"})

    def test_tracker_promotion_preserves_source_evidence(self):
        jobs = [{
            "url": "https://example.test/pass",
            "title": "Contract Python Engineer",
            "location": "Worldwide",
            "source": "PeoplePerHour",
            "score": "12",
            "_score": 12,
            "qualification_status": PASS,
            "application_readiness": "REVIEW_REQUIRED",
        }]
        entries = {}
        promote_jobs(jobs, entries, min_score=5, top_n=1)
        self.assertEqual(entries[jobs[0]["url"]]["location"], "Worldwide")
        self.assertEqual(entries[jobs[0]["url"]]["source"], "PeoplePerHour")

    def test_legacy_classifier_no_longer_defaults_unknown_or_dot_com(self):
        self.assertEqual(classify_job_type("Software Engineer"), "")
        self.assertEqual(classify_country("Software Engineer", "https://example.com/job"), "")

    def test_live_application_paths_require_explicit_policy_approval(self):
        for filename in ("send_application_emails.py", "ats_auto_apply.py", "email_application.py"):
            source = (SCRIPTS / filename).read_text(encoding="utf-8")
            self.assertIn("is_approved_for_submission", source, filename)

    def test_legacy_email_cli_live_send_stays_locked(self):
        env = os.environ.copy()
        env.pop("BOOK_JOB_LIVE_SEND_ENABLED", None)
        env.pop("BOOK_JOB_SEND_UNLOCK", None)
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "email_application.py"),
                "--url",
                "https://example.test/job",
                "--send",
                "--to",
                "recruiter@example.test",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("BLOCKED", proc.stdout + proc.stderr)

    def test_scheduler_is_contract_first_and_refreshes_matches_every_six_hours(self):
        config = yaml.safe_load((REPO_ROOT / "config" / "jobs.yaml").read_text(encoding="utf-8"))
        jobs = {job["name"]: job for job in config["jobs"]}
        boards = set(jobs["job_postings"]["params"]["boards"])
        self.assertIn("peopleperhour", boards)
        # fastwork removed by the owner 2026-11-03: JS-only search page, and it
        # lists freelancers' service offers, not client job postings.
        self.assertNotIn("fastwork", boards)
        self.assertNotIn("jobthai", boards)
        self.assertNotIn("jobbkk", boards)
        self.assertEqual(jobs["job_match_filter"]["schedule"], "0 */6 * * *")
        self.assertTrue(jobs["job_match_filter"]["params"]["seed_tracker"])
        self.assertEqual(jobs["job_match_filter"]["params"]["seed_min_score"], 5)
        self.assertEqual(jobs["job_match_filter"]["params"]["descriptions"], "data/job_descriptions.csv")

        commands = {task["name"]: task["cmd"] for task in get_daily_commands()}
        auto_seed_cmd = commands["auto_seed"]
        self.assertIn("auto_seed_tracker.py", auto_seed_cmd[1])
        self.assertEqual(auto_seed_cmd[-3:], ["--min-score", "5", "--send-telegram"])
        self.assertNotIn("--send-telegram", commands["pipeline_full"])

    def test_scheduler_can_import_filter_as_package(self):
        module = importlib.import_module("scripts.filter_job_matches")
        self.assertTrue(hasattr(module, "JobMatchFilter"))

    def test_scheduled_filter_seeds_tracker_without_notification(self):
        wrapper = JobMatchFilter(seed_tracker=True, seed_min_score=5)
        with (
            mock.patch("filter_job_matches.main", return_value=2),
            mock.patch("auto_seed_tracker.auto_seed", return_value=2) as seed,
        ):
            rows = asyncio.run(wrapper.run())
        self.assertEqual(len(rows), 2)
        seed.assert_called_once_with(
            min_score=5,
            send_telegram_flag=False,
            dry_run=False,
        )

    def test_peopleperhour_adapter_emits_job_posting_contract(self):
        card = {
            "title": "Build a FastAPI integration",
            "company": "Example Client",
            "location": "Remote/Marketplace",
            "salary": "$500",
            "url": "https://www.peopleperhour.com/freelance-jobs/technology-programming/build-fastapi-123",
            "source": "PeoplePerHour",
            "posted": "1 hour ago",
            "context": "Build a FastAPI integration using Python for $500",
        }
        with mock.patch("scrape_job_postings._load_peopleperhour_cards", return_value=[card]):
            rows = fetch_peopleperhour("python contract")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "PeoplePerHour")
        self.assertIn("freelance", rows[0]["tags"])
        self.assertEqual(rows[0]["salary"], "$500")


if __name__ == "__main__":
    unittest.main()
