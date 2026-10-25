"""
test_nlp_pipeline.py
Automated evaluation and compliance test suite for Kavach NLP engine.
"""

import unittest
from ai_pipeline.extractor import process_text
from backend.database import graph_service

SAMPLE_TEXT = (
    "Special Cell surveillance report: Vikas Kumar alias Bicky is operating a syndicate. "
    "Intercepted device 9876543210 with IMEI 864201948201948. This device was in continuous contact "
    "with a master number 9123456789 having IMEI 359876102938475. Financial tracing show karti hai "
    "ki Vikas ne total INR 5,00,000 transfer kiye into SBI Account 30291827465. Yeh account Rajendra Singh "
    "urf Raju Bhai control karta hai."
)

class TestNLPPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ai_output = process_text(SAMPLE_TEXT)
        cls.graph_output = graph_service.transform_to_render_schema(cls.ai_output, raw_text=SAMPLE_TEXT)

    def test_entity_extraction_count(self):
        """Verify exact entity extraction and deduplication count (7 nodes)."""
        entities = self.ai_output.get("entities", [])
        self.assertEqual(len(entities), 7, f"Expected 7 entities, found {len(entities)}")

    def test_person_deduplication_and_aliases(self):
        """Verify street aliases are merged into canonical persons with no orphan sub-tokens."""
        entities = self.ai_output.get("entities", [])
        person_nodes = [e for e in entities if e.get("type") == "PERSON"]
        
        self.assertEqual(len(person_nodes), 2, f"Expected exactly 2 PERSON entities, found {len(person_nodes)}")
        
        names = [p["canonical_name"] for p in person_nodes]
        self.assertTrue(any("Vikas Kumar" in n for n in names))
        self.assertTrue(any("Rajendra Singh" in n for n in names))

        vikas = next(p for p in person_nodes if "Vikas Kumar" in p["canonical_name"])
        self.assertIn("Bicky", vikas.get("aliases", []))

        raju = next(p for p in person_nodes if "Rajendra Singh" in p["canonical_name"])
        self.assertIn("Raju Bhai", raju.get("aliases", []))

    def test_structured_identifiers(self):
        """Verify PHONE, IMEI, and ACCOUNT entities."""
        entities = self.ai_output.get("entities", [])
        phones = [e for e in entities if e.get("type") == "PHONE"]
        imeis = [e for e in entities if e.get("type") == "IMEI"]
        accounts = [e for e in entities if e.get("type") == "ACCOUNT"]

        self.assertEqual(len(phones), 2)
        self.assertEqual(len(imeis), 2)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["bank"], "SBI")

    def test_relationship_count_and_types(self):
        """Verify Contract 1 relationships (6 edges)."""
        relationships = self.ai_output.get("relationships", [])
        self.assertEqual(len(relationships), 6)
        
        rel_types = [r["relation"] for r in relationships]
        self.assertIn("OWNS_DEVICE", rel_types)
        self.assertIn("ASSOCIATED_IMEI", rel_types)
        self.assertIn("COMMUNICATED_WITH", rel_types)
        self.assertIn("TRANSFERRED_FUNDS", rel_types)
        self.assertIn("CONTROLS_ACCOUNT", rel_types)

    def test_kingpin_identification(self):
        """Verify topological centrality identifies the mastermind as Kingpin."""
        summary = self.graph_output.get("summary", {})
        nodes = self.graph_output.get("elements", {}).get("nodes", [])
        
        kingpin_id = summary.get("kingpin_node_id")
        self.assertTrue(bool(kingpin_id), "Kingpin ID must be non-empty.")
        
        kingpin_node = next((n for n in nodes if n["data"]["id"] == kingpin_id), None)
        self.assertIsNotNone(kingpin_node)
        self.assertTrue(kingpin_node["data"]["isKingpin"])
        self.assertIn("Rajendra", kingpin_node["data"]["label"])

if __name__ == "__main__":
    unittest.main()