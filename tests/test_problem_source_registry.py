"""Offline regression for the reusable fire-apparatus source and opportunity catalog."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.core import PatentWorkflowError
from mechanical_patent.problem_sources import ProblemSourceRegistry
from mechanical_patent.project_storage import ProjectStorage


RSS=b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>NASA Technology</title>
<item><title>Novel mechanical pump robot research for rescue</title>
<link>https://www.nasa.gov/technology/pump-robot-study/</link>
<description>Thermal hydraulic safety research.</description>
<pubDate>Thu, 19 Nov 2026 00:00:00 GMT</pubDate></item></channel></rss>"""


class ProblemCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.catalog=ProblemSourceRegistry(self.root)

    def test_seed_idempotence_and_project_isolation(self):
        sources=self.catalog.sources()
        topics=self.catalog.topics()
        self.assertGreaterEqual(len(sources),20)
        self.assertEqual(len(topics),20)
        self.assertEqual(self.catalog.seed(),{"sources_added":0,"topics_added":0})
        self.assertTrue(all(t["novelty_checked"]==0 for t in topics))
        project_a=ProjectStorage(self.root,"PM80")
        project_b=ProjectStorage(self.root,"PM120")
        self.assertNotEqual(project_a.db_path,project_b.db_path)
        self.assertNotEqual(self.catalog.path,project_a.db_path)
        with project_a.workspace.connect() as db:
            self.assertFalse(db.execute("SELECT count(*) FROM sqlite_master WHERE name='sources'").fetchone()[0])
        self.assertTrue(self.catalog.audit_verify()["valid"])

    def test_new_platform_quarantined_and_url_safety(self):
        with self.assertRaises(PatentWorkflowError):
            self.catalog.propose("dangerous site","http://127.0.0.1:5000","please analyze public challenge")
        with self.assertRaises(PatentWorkflowError):
            self.catalog.propose("localhost","https://localhost/metadata","please analyze public challenge")
        item=self.catalog.propose("New research platform",
            "https://future.example.org/challenge/important?utm_source=test",
            "International equipment research challenge",discovered_from="manual")
        self.assertEqual(item["status"],"pending")
        self.assertFalse(item["requires_human_source_approval"] is False)
        self.assertEqual(self.catalog.propose("New research platform",
            "https://future.example.org/challenge/important",
            "International equipment research challenge")["created"],False)
        with self.assertRaises(PatentWorkflowError):
            self.catalog.observe(item["source_id"],
                 "https://future.example.org/challenge/important","Candidate research")
        with self.assertRaises(PatentWorkflowError):
            self.catalog.approve(item["source_id"],reviewer="research admin",rights_reviewed=False)
        with self.assertRaises(PatentWorkflowError):
            self.catalog.approve(item["source_id"],reviewer="research admin",
                 rights_reviewed=True,mode="rss",feed_url="https://other.example.org/rss")
        self.assertEqual(self.catalog.approve(item["source_id"],reviewer="research admin",
                     rights_reviewed=True)["status"],"approved")
        self.assertEqual(self.catalog.sources("pending"),[])
        self.assertTrue(self.catalog.audit_verify()["valid"])

    def test_observation_versions_topic_derivation_and_unverified_note(self):
        url="https://www.faa.gov/airports/airport_safety/aircraft_rescue_fire_fighting/research"
        x=self.catalog.observe("US-FAA-ARFF",url,"Fire pump hydraulic test",
                               summary="Cavitation pressure tests",published_at="2026-11-19")
        self.assertEqual(x["status"],"created")
        self.assertTrue(x["relevant"])
        self.assertEqual(self.catalog.observe("US-FAA-ARFF",url,"Fire pump hydraulic test",
                 summary="Cavitation pressure tests",published_at="2026-11-19")["status"],"unchanged")
        y=self.catalog.observe("US-FAA-ARFF",url,"Fire pump hydraulic test",
                    summary="New actuator fatigue result",published_at="2026-11-19")
        self.assertEqual(y["revision"],2)
        with self.catalog.connect() as db:
            versions=db.execute("SELECT count(*) FROM observation_revisions WHERE observation_id=?",
                                (x["observation_id"],)).fetchone()[0]
        self.assertEqual(versions,2)
        with self.assertRaises(PatentWorkflowError):
            self.catalog.observe("US-FAA-ARFF","https://evil.example.net/",
                                 "Fire pump hydraulic test")
        idea=self.catalog.derive_topic(x["observation_id"],
                     "Pump fails intermittently during aerated suction",
                     "Passive air separator chamber on the pump inlet",
                     "Measure NPSH and pressure recovery against baseline","消防泵")
        self.assertTrue(idea["created"])
        self.assertFalse(idea["novelty_checked"])
        self.assertEqual(self.catalog.derive_topic(x["observation_id"],
                     "Pump fails intermittently during aerated suction",
                     "Passive air separator chamber on the pump inlet",
                     "Measure NPSH and pressure recovery against baseline","消防泵")["created"],False)
        self.assertFalse(self.catalog.plan(idea["topic_id"])["patent_novelty_certified"])
        with self.assertRaises(PatentWorkflowError):
            self.catalog.record_research(idea["topic_id"],"agent",
                      "Preliminary mechanical concept; patent checks not done.",[])
        note=self.catalog.record_research(idea["topic_id"],"agent",
             "Preliminary mechanical concept; patent checks not done.",
             ["https://www.faa.gov/airports/airport_safety/aircraft_rescue_fire_fighting"],
             public_only=True)
        self.assertEqual(note["status"],"unverified_ai_assessment")
        self.assertTrue(self.catalog.audit_verify()["valid"])
        self.assertTrue(any(t["id"]==idea["topic_id"] for t in self.catalog.topics()))

    def test_offline_cycle_fetch_incremental_and_failure_backoff(self):
        preview=self.catalog.cycle(allow_network=False,max_sources=2)
        self.assertEqual(preview["status"],"offline_preview")
        self.assertFalse(preview["network_used"])
        self.assertEqual(preview["fetched"],0)
        def fake_fetch(source):
            self.assertEqual(source["status"],"approved")
            return {"status":200,"data":RSS,"etag":"v1","last_modified":""}
        result=self.catalog.cycle(allow_network=True,max_sources=5,fetcher=fake_fetch)
        self.assertGreater(result["fetched"],0)
        self.assertGreater(result["added"],0)
        inbox=self.catalog.inbox()
        self.assertTrue(any(x["source_id"].startswith("US-NASA") for x in inbox["new_observations"]))
        with self.catalog.connect(write=True) as db:
            db.execute("UPDATE sources SET next_due='' WHERE mode='rss'")
        result2=self.catalog.cycle(allow_network=True,max_sources=5,fetcher=fake_fetch)
        self.assertEqual(result2["added"],0)
        with self.catalog.connect(write=True) as db:
            db.execute("UPDATE sources SET next_due='' WHERE mode='rss'")
        fail=self.catalog.cycle(allow_network=True,max_sources=5,
                 fetcher=lambda source: (_ for _ in ()).throw(OSError("supplier offline")))
        self.assertEqual(fail["status"],"partial_or_failed")
        self.assertTrue(fail["errors"])
        self.assertTrue(self.catalog.audit_verify()["valid"])

    def test_xml_entity_and_invalid_feed_rejected(self):
        from mechanical_patent.problem_sources import _feed_entries
        with self.assertRaises(PatentWorkflowError):
            _feed_entries(b'<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss/>')
        with self.assertRaises(PatentWorkflowError):
            _feed_entries(b'<html><body>No feed</body></html>')


    def test_cli_and_worker_safety_contract(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from mechanical_patent.cli import main as cli_main
        from mechanical_patent.source_catalog_worker import main as worker_main
        output=StringIO()
        with redirect_stdout(output):
            self.assertEqual(cli_main(["source-catalog","topics",
                                      "--storage-root",str(self.root)]),0)
        self.assertEqual(len(json.loads(output.getvalue())["topics"]),20)
        with self.assertRaises(SystemExit) as secret:
            worker_main(["--once","--storage-root",str(self.root)])
        self.assertEqual(secret.exception.code,2)
        with self.assertRaises(SystemExit) as short:
            worker_main(["--once","--allow-public-network",
                         "--interval-minutes","1","--storage-root",str(self.root)])
        self.assertEqual(short.exception.code,2)


if __name__=="__main__":
    unittest.main()
