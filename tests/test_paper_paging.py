"""Offline scholarly paging contracts, limits, checkpoints and OpenAlex API-key gates."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from mechanical_patent.core import PatentWorkflowError
from mechanical_patent.paper_sources import (
    ArxivProvider, EuropePMCProvider, PubMedProvider, SemanticScholarProvider,
)
from mechanical_patent.papers import OpenAlexProvider
from mechanical_patent.literature_harvest import HarvestBudget, LiteratureHarvester
from mechanical_patent.literature_memory import LiteratureMemoryStore


class PagingTests(unittest.TestCase):
    def test_semantic_scholar_cursor_progresses_until_total(self):
        seen = []
        def get(url, *, headers):
            params = parse_qs(urlsplit(url).query)
            start, length = int(params["offset"][0]), int(params["limit"][0])
            seen.append(start)
            self.assertEqual(length, 2)
            rows = [{"paperId": str(i+1), "title": f"Pump physics {i}",
                     "url": f"https://www.semanticscholar.org/paper/{i+1}",
                     "externalIds": {"DOI": f"10.1111/pump.{i}"}} for i in range(start, min(start+length, 3))]
            return {"total": 3, "data": rows}
        provider = SemanticScholarProvider(fetch_json=get, api_key="test")
        one = provider.search_page("cavitation", cursor="*", limit=2)
        two = provider.search_page("cavitation", cursor=one["next_cursor"], limit=2)
        self.assertEqual(one["next_cursor"], "2")
        self.assertEqual(len(two["records"]), 1)
        self.assertIsNone(two["next_cursor"])
        self.assertEqual(seen, [0, 2])
        with self.assertRaises(PatentWorkflowError):
            provider.search_page("x", cursor="evil", limit=5)

    def test_europe_pmc_official_cursor(self):
        def get(url):
            query = parse_qs(urlsplit(url).query)
            self.assertEqual(query["pageSize"], ["1"])
            cursor = query["cursorMark"][0]
            paper = "A" if cursor == "*" else "B"
            return {
                "hitCount": 2,
                "nextCursorMark": "NEXT" if paper == "A" else "NEXT",
                "resultList": {"result": [{
                    "source": "MED", "id": paper, "title": f"Fluid {paper}",
                }]},
            }
        provider = EuropePMCProvider(fetch_json=get)
        first = provider.search_page("cavitation", cursor="*", limit=1)
        second = provider.search_page("cavitation", cursor=first["next_cursor"], limit=1)
        self.assertEqual(first["next_cursor"], "NEXT")
        self.assertIsNone(second["next_cursor"])

    def test_arxiv_offset_and_atom_total(self):
        def get(url):
            params = parse_qs(urlsplit(url).query)
            start = int(params["start"][0])
            self.assertEqual(params["max_results"], ["1"])
            paper = f"2501.{start+1:05d}"
            return f"""<feed xmlns="http://www.w3.org/2005/Atom"
                       xmlns:os="http://a9.com/-/spec/opensearch/1.1/">
              <os:totalResults>2</os:totalResults><entry>
              <id>https://arxiv.org/abs/{paper}</id>
              <title>Displacement pump {start}</title><summary>Fluids</summary>
              </entry></feed>""".encode()
        provider = ArxivProvider(fetch_xml=get)
        first = provider.search_page("pump", cursor="*", limit=1)
        second = provider.search_page("pump", cursor=first["next_cursor"], limit=1)
        self.assertEqual(first["next_cursor"], "1")
        self.assertIsNone(second["next_cursor"])
        self.assertEqual(second["records"][0].publication, "arxiv:2501.00002")

    def test_pubmed_esearch_retstart_cursor(self):
        def get(url):
            q = parse_qs(urlsplit(url).query)
            start = int(q["retstart"][0])
            return {"esearchresult": {"count": "2", "idlist": [str(200+start)]}}
        def get_xml(url):
            number = parse_qs(urlsplit(url).query)["id"][0]
            return (f"""<PubmedArticleSet><PubmedArticle>
             <MedlineCitation><PMID>{number}</PMID><Article>
             <ArticleTitle>Experimental rescue medicine</ArticleTitle>
             <Abstract><AbstractText>Fluid dynamics</AbstractText></Abstract></MedlineCitation>
             </PubmedArticle></PubmedArticleSet>""").encode()
        provider = PubMedProvider(api_key="", fetch_json=get, fetch_xml=get_xml)
        a = provider.search_page("rescue", cursor="*", limit=1)
        b = provider.search_page("rescue", cursor=a["next_cursor"], limit=1)
        self.assertEqual(a["next_cursor"], "1")
        self.assertIsNone(b["next_cursor"])
        self.assertEqual(len(b["records"]), 1)

    def test_harvest_semantic_scholar_saves_each_page(self):
        counter = {"n": 0}
        def get(_url, *, headers):
            counter["n"] += 1
            idn = counter["n"]
            return {"total": 2, "data": [{
                "paperId": str(idn), "title": f"Hydraulic mechanics {idn}",
                "url": f"https://www.semanticscholar.org/paper/{idn}",
                "externalIds": {"DOI": f"10.2000/hydro.{idn}"},
            }]}
        with tempfile.TemporaryDirectory() as root:
            store = LiteratureMemoryStore(Path(root) / "project")
            provider = SemanticScholarProvider(fetch_json=get)
            runner = LiteratureHarvester(store)
            one = runner.harvest(provider, "pump", budget=HarvestBudget(
                max_documents=2, page_size=1, max_pages=1))
            two = runner.harvest(provider, "pump", budget=HarvestBudget(
                max_documents=2, page_size=1, max_pages=2))
            self.assertEqual(one["status"], "partial")
            self.assertEqual(two["status"], "complete")
            self.assertEqual(store.stats()["by_kind"]["paper"]["documents"], 2)

    def test_openalex_second_cursor_requires_free_api_key(self):
        provider = OpenAlexProvider(api_key="", fetch_json=lambda *_a, **_k: {})
        with self.assertRaises(PatentWorkflowError):
            provider.search_page("cavitation", cursor="opaque-cursor", limit=10)


if __name__ == "__main__":
    unittest.main()
