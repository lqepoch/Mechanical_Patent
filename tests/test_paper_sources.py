"""论文数据源统一契约、付费门禁、开放全文链接和持久化离线测试。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from mechanical_patent.core import Evidence, PatentWorkflowError
from mechanical_patent.papers import OpenAlexProvider, CrossrefProvider
from mechanical_patent.paper_sources import (
    ArxivProvider, COREProvider, EuropePMCProvider, LensProvider,
    PubMedProvider, SemanticScholarProvider, UnpaywallEnricher,
    build_paper_providers, merge_paper_records, paper_source_catalog,
)
from mechanical_patent.workflow import PatentResearch
from mechanical_patent.local_workspace import LocalPatentWorkspace


DOI = "10.1000/test.paper"


class SourceTests(unittest.TestCase):
    def test_semantic_scholar_normalizes_pdf_and_citations(self):
        def fake(url, *, headers):
            self.assertIn("fields=", url)
            self.assertEqual(headers, {"x-api-key": "TOKEN"})
            return {"data": [{
                "paperId": "abc123", "title": "High altitude pump cavitation",
                "externalIds": {"DOI": DOI.upper()}, "abstract": "Measured pressure threshold",
                "authors": [{"name": "Lin"}], "citationCount": 27, "isOpenAccess": True,
                "openAccessPdf": {"url": "https://example.org/paper.pdf"},
                "publicationDate": "2024-02-01",
            }]}
        paper, = SemanticScholarProvider(api_key="TOKEN", fetch_json=fake).search("cavitation")
        self.assertEqual(paper.publication, DOI)
        self.assertEqual(paper.pdf_url, "https://example.org/paper.pdf")
        self.assertEqual(paper.paper_metadata["citation_count"], 27)
        self.assertEqual(paper.paper_metadata["authors"], ["Lin"])
        self.assertEqual(paper.paper_metadata["pdf_link_status"], "unverified_discovery")
        self.assertFalse(paper.paper_metadata["full_text_verified"])

    def test_openalex_oa_metadata_and_crossref_merge(self):
        def openalex(_url, **_kwargs):
            return {"results": [{
                "id": "https://openalex.org/W123", "doi": "https://doi.org/" + DOI,
                "display_name": "High altitude pump cavitation",
                "abstract_inverted_index": {"Pump": [0], "test": [1]},
                "publication_date": "2024-03-01", "cited_by_count": 12,
                "open_access": {"is_oa": True, "oa_status": "gold"},
                "best_oa_location": {"pdf_url": "https://example.org/p.pdf", "license": "cc-by"},
                "authorships": [{"author": {"display_name": "Chen"}}],
            }]}
        def crossref(_url, **_kwargs):
            return {"message": {"items": [{
                "DOI": DOI, "title": ["High altitude pump cavitation"],
                "abstract": "<jats:p>Longer detailed introduction.</jats:p>",
                "author": [{"given": "Jane", "family": "Doe"}],
                "published": {"date-parts": [[2024, 3, 2]]},
            }]}}
        oa, = OpenAlexProvider(fetch_json=openalex).search("pump")
        cr, = CrossrefProvider(fetch_json=crossref).search("pump")
        merged, = merge_paper_records([oa, cr])
        self.assertEqual(merged.paper_metadata["sources"], ["openalex", "crossref"])
        self.assertEqual(merged.paper_metadata["source_ids"]["openalex"], "W123")
        self.assertEqual(merged.abstract, "Longer detailed introduction.")
        self.assertTrue(merged.pdf_url.endswith(".pdf"))

    def test_arxiv_atom_parses_preprint(self):
        xml = b"""<?xml version='1.0'?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
          <id>https://arxiv.org/abs/2401.12345v3</id>
          <title>New Pump Physics</title><summary>Experiments in air-water flows</summary>
          <published>2024-01-30T00:00:00Z</published>
          <author><name>Example Researcher</name></author>
          <link title="pdf" type="application/pdf" href="https://arxiv.org/pdf/2401.12345"/>
          </entry>
        </feed>"""
        paper, = ArxivProvider(fetch_xml=lambda _url: xml).search("pump")
        self.assertEqual(paper.publication, "arxiv:2401.12345")
        self.assertEqual(paper.paper_metadata["authors"], ["Example Researcher"])
        self.assertEqual(paper.pdf_url, "https://arxiv.org/pdf/2401.12345")

    def test_europe_pmc_normalizes_abstract(self):
        def fake(_url):
            return {"resultList": {"result": [{
                "id": "123456", "source": "MED", "doi": DOI,
                "title": "Hypoxia and fluid machinery",
                "abstractText": "<h4>BACKGROUND</h4>Fluid test",
                "fullTextUrlList": {"fullTextUrl": [
                    {"documentStyle": "pdf", "url": "https://europepmc.org/articles/p.pdf"}
                ]},
                "authorList": {"author": [{"fullName": "Example Author"}]},
                "isOpenAccess": "Y",
            }]}}
        paper, = EuropePMCProvider(fetch_json=fake).search("hypoxia")
        self.assertEqual(paper.publication, DOI)
        self.assertEqual(paper.paper_metadata["authors"], ["Example Author"])
        self.assertEqual(paper.pdf_url, "https://europepmc.org/articles/p.pdf")

    def test_pubmed_esearch_and_efetch(self):
        hits = []
        def ids(url):
            hits.append(url)
            return {"esearchresult": {"idlist": ["3141592"]}}
        xml = b"""<PubmedArticleSet><PubmedArticle><MedlineCitation>
          <PMID>3141592</PMID><Article><ArticleTitle>Pump Physiology</ArticleTitle>
          <Abstract><AbstractText>Fluid flow model</AbstractText></Abstract>
          <AuthorList><Author><ForeName>John</ForeName><LastName>Doe</LastName></Author></AuthorList>
          <Journal><JournalIssue><PubDate><Year>2022</Year></PubDate></JournalIssue></Journal>
          </Article></MedlineCitation>
          <PubmedData><ArticleIdList><ArticleId IdType="doi">10.1000/test.paper</ArticleId></ArticleIdList></PubmedData>
        </PubmedArticle></PubmedArticleSet>"""
        paper, = PubMedProvider(fetch_json=ids, fetch_xml=lambda _url: xml, api_key="").search("pump")
        self.assertTrue(hits and "db=pubmed" in hits[0])
        self.assertEqual(paper.publication, DOI)
        self.assertEqual(paper.paper_metadata["authors"], ["John Doe"])

    def test_core_with_explicit_token(self):
        def fake(url, *, headers):
            self.assertIn("/v3/search/works?", url)
            self.assertEqual(headers["Authorization"], "Bearer token")
            return {"results": [{
                "id": 123, "title": "Fluid Survey", "doi": DOI,
                "abstract": "Survey of fluid mechanics",
                "downloadUrl": "https://core.ac.uk/download/123.pdf",
                "authors": [{"name": "A Scholar"}],
            }]}
        paper, = COREProvider(api_key="token", fetch_json=fake).search("fluid")
        self.assertEqual(paper.pdf_url, "https://core.ac.uk/download/123.pdf")
        self.assertEqual(paper.paper_metadata["authors"], ["A Scholar"])

    def test_lens_uses_documented_post_payload(self):
        def fake(url, *, body, headers):
            self.assertEqual(url, "https://api.lens.org/scholarly/search")
            self.assertEqual(body["query"], "cavitation")
            self.assertEqual(body["size"], 4)
            self.assertEqual(headers["Authorization"], "Bearer secret")
            return {"data": [{
                "lens_id": "111-222-333", "title": "Flow Structure",
                "external_ids": [{"type": "doi", "value": DOI}],
                "open_access": {"pdf_urls": ["https://example.org/oa.pdf"]},
                "authors": [{"display_name": "Scholar"}],
                "scholarly_citations_count": 2,
            }]}
        paper, = LensProvider(api_key="secret", fetch_json=fake).search("cavitation", limit=4)
        self.assertEqual(paper.publication, DOI)
        self.assertEqual(paper.pdf_url, "https://example.org/oa.pdf")

    def test_unpaywall_only_enriches_doi_records(self):
        paper = Evidence(publication=DOI, title="Flow", url="https://doi.org/" + DOI,
                         source="crossref", retrieved_at="2026-01-01", kind="paper",
                         paper_metadata={"doi": DOI, "sources": ["crossref"]})
        def fake(url):
            self.assertIn("?email=", url)
            return {"is_oa": True, "oa_status": "green",
                    "best_oa_location": {"url_for_pdf": "https://repo.edu/accepted.pdf",
                                         "license": "cc-by"}}
        enriched = UnpaywallEnricher(contact_email="researcher@example.org", fetch_json=fake).enrich(paper)
        self.assertEqual(enriched.pdf_url, "https://repo.edu/accepted.pdf")
        self.assertEqual(enriched.paper_metadata["sources"], ["crossref", "unpaywall"])
        self.assertFalse(enriched.paper_metadata["full_text_verified"])
        self.assertFalse(paper.pdf_url)

    def test_source_selection_and_commercial_gate(self):
        with patch.dict(os.environ, {"CORE_API_KEY": "token", "LENS_API_TOKEN": "token"}):
            with self.assertRaises(PatentWorkflowError):
                build_paper_providers(["lens"])
            with self.assertRaises(PatentWorkflowError):
                build_paper_providers(["core"])
            sources, warnings = build_paper_providers(["all"])
            self.assertEqual([x.name for x in sources][-2:], ["europe-pmc", "pubmed"])
            self.assertEqual(len(warnings), 2)
            enabled, warnings = build_paper_providers(["core", "lens"], allow_paid=True)
            self.assertEqual([x.name for x in enabled], ["core", "lens"])
            self.assertFalse(warnings)
        self.assertEqual(paper_source_catalog()[-1]["capability"], "doi_enrich")

    def test_workflow_memory_and_sqlite_metadata(self):
        class OnePaperProvider:
            name = "fixture-paper"
            def search(self, _query, *, limit=10):
                return [Evidence(
                    publication=DOI, title="Pump Research",
                    url="https://doi.org/" + DOI, source="fixture-paper",
                    retrieved_at="2026-11-18T00:00:00+00:00", kind="paper",
                    abstract="Verified API metadata only", verified=True,
                    pdf_url="https://repository.org/pump.pdf",
                    paper_metadata={"doi": DOI, "authors": ["Researcher"],
                                    "sources": ["fixture-paper"], "is_open_access": True},
                )]
        with tempfile.TemporaryDirectory() as temp:
            dossier = Path(temp) / "case-1"
            result = PatentResearch(None, [OnePaperProvider()], dossier).run(
                "Pump", [], ["low pressure"], case_id="case-1")
            self.assertEqual(result["papers_discovered"], 1)
            paper_doc = json.loads((dossier / "03_papers.json").read_text())
            self.assertEqual(paper_doc["pdf_links_discovered"], 1)
            self.assertTrue(list((dossier / "03_paper_memory").glob("EV-*.md")))
            db = LocalPatentWorkspace(Path(temp) / "index.sqlite3")
            db.import_case(dossier)
            records = db.search_documents("Pump", case_id="case-1")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["public_pdf_url"], "https://repository.org/pump.pdf")
            self.assertEqual(records[0]["paper_metadata"]["authors"], ["Researcher"])
            self.assertEqual(records[0]["verification_status"], "待核验")

    def test_legacy_sqlite_migration_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            dbpath = Path(temp) / "legacy.sqlite3"
            workspace = LocalPatentWorkspace(dbpath)
            with workspace.connect(write=True) as db:
                db.execute("UPDATE documents SET indexed_at=indexed_at")
            again = LocalPatentWorkspace(dbpath)
            with again.connect() as db:
                columns = {r["name"] for r in db.execute("PRAGMA table_info(documents)")}
            self.assertIn("paper_metadata_json", columns)

    def test_invalid_pdf_url_is_rejected(self):
        with self.assertRaises(ValueError):
            Evidence(publication=DOI, title="Flow", url="https://doi.org/" + DOI,
                     source="x", retrieved_at="2026-01-01", kind="paper",
                     pdf_url="http://insecure.example/paper.pdf")


if __name__ == "__main__":
    unittest.main()
