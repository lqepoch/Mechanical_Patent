"""Scholarly metadata parsing and deduplication; no live network calls."""
from urllib.parse import parse_qs, urlsplit
import unittest

from mechanical_patent.core import deduplicate
from mechanical_patent.papers import (
    OpenAlexProvider, CrossrefProvider, _abstract_from_inverted_index, _crossref_abstract,
)


def openalex_result(query, **kwargs):
    qs = parse_qs(urlsplit(query).query)
    assert qs["search"] == ["cavitation pump"]
    return {"results": [
        {
            "id": "https://openalex.org/W100",
            "doi": "https://doi.org/10.1000/Pump.Flow",
            "display_name": "Pump cavitation research",
            "publication_date": "2023-08-01",
            "abstract_inverted_index": {"High": [0], "altitude": [1], "pump": [2], "flow": [3]},
        },
        {"id": "https://openalex.org/W101", "display_name": "No DOI study", "publication_date": "2022-03-02"},
    ]}


def crossref_result(url, **kwargs):
    assert "query.bibliographic" in parse_qs(urlsplit(url).query)
    return {"message": {"items": [
        {"DOI": "10.1000/pump.flow", "title": ["Pump cavitation research"],
         "abstract": "<jats:p>Fluid <i>flow</i>.</jats:p>",
         "published": {"date-parts": [[2023, 8, 1]]}},
        {"DOI": "10.1000/another", "title": ["Second study"],
         "issued": {"date-parts": [[2024]]}},
    ]}}


class PaperTests(unittest.TestCase):
    def test_openalex_reconstructs_abstract(self):
        self.assertEqual(_abstract_from_inverted_index({"Flow": [2], "High": [0], "speed": [1]}),
                         "High speed Flow")
        provider = OpenAlexProvider(fetch_json=openalex_result)
        results = provider.search("cavitation pump")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].kind, "paper")
        self.assertTrue(results[0].verified)
        self.assertEqual(results[0].abstract, "High altitude pump flow")
        self.assertEqual(results[0].publication, "10.1000/pump.flow")
        self.assertEqual(results[1].publication, "W101")

    def test_crossref_cleans_jats_and_dates(self):
        result = CrossrefProvider(fetch_json=crossref_result).search("cavitation pump")
        self.assertEqual(result[0].abstract, "Fluid flow .")
        self.assertEqual(result[0].publication_date, "2023-08-01")
        self.assertEqual(result[1].publication_date, "2024")

    def test_doi_dedupes_across_providers(self):
        a = OpenAlexProvider(fetch_json=openalex_result).search("cavitation pump")
        b = CrossrefProvider(fetch_json=crossref_result).search("cavitation pump")
        distinct = deduplicate(a+b)
        self.assertEqual(len(distinct), 3)
        self.assertEqual({e.source for e in distinct if e.publication == "10.1000/pump.flow"},
                         {"openalex"})


if __name__ == "__main__":
    unittest.main()
