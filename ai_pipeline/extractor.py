"""
extractor.py
Main extraction pipeline called by Team 3 (FastAPI backend).
Integrates Dev A (model_engine) and Dev B (regex_engine) into Contract 1 JSON.
Merges deep-learning AI NER person entities with regex entities without discarding AI outputs.
"""

import sys
import os

# Add ai_pipeline directory and project root to Python module search path
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import Dict, Any, List
from model_engine import extract_persons
from regex_engine import extract_regex_entities, compile_contract_1

__all__ = ["process_text", "compile_contract_1", "extract_regex_entities", "extract_persons"]


def process_text(raw_text: str, source_doc_id: str = "FIR_45_2026") -> Dict[str, Any]:
    """
    Main extraction pipeline called by Team 3 (FastAPI backend).
    Enforces the 5000-character safety limit and assembles Contract 1 JSON.
    Merges Dev A's deep-learning AI NER person entities with Dev B's regex entities
    and contextual aliases without discarding AI predictions or confidence scores.
    """
    if not raw_text or not raw_text.strip():
        return {
            "error": "NO_ENTITIES_FOUND",
            "elements": {"nodes": [], "edges": []}
        }

    # Contract Rule: Cap input text at 5000 characters
    if len(raw_text) > 5000:
        raw_text = raw_text[:5000]

    # 1. Dev A's engine extracts people and aliases via Indic NER / XLM-RoBERTa
    persons = extract_persons(raw_text)

    # 2. Dev B's engine extracts numbers and bank accounts
    objects = extract_regex_entities(raw_text)

    # 3. Dev B's compiler merges AI person entities and regex entities into Contract 1 JSON
    final_json = compile_contract_1(source_doc_id, persons, objects, raw_text=raw_text)

    return final_json


if __name__ == "__main__":
    import json

    # Test directly using the team's golden input file
    sample_path = os.path.join(os.path.dirname(__file__), "..", "contracts", "sample_input.txt")
    if os.path.exists(sample_path):
        with open(sample_path, "r", encoding="utf-8") as f:
            test_text = f.read()
    else:
        test_text = (
            "FIR No. 45/2026 ki investigation ke dauran, yeh clear ho gaya ki suspect Vikas Kumar urf Bicky "
            "Sector 42 se ek illegal hawala operation run kar raha tha. Arrest ke time, uske paas se ek burner mobile "
            "number 9876543210 (IMEI: 864201948201948) recover hua. Telecom CDR analysis se pata chala ki this "
            "device was in continuous contact with a master number 9123456789 (IMEI: 359876102938475). "
            "Financial tracing show karti hai ki Vikas ne total INR 5,00,000 transfer kiye into SBI Account "
            "30291827465, jo ki syndicate mastermind Rajendra Singh @ Raju Bhai dwara strictly control kiya jaata hai."
        )

    output = process_text(test_text)
    print(json.dumps(output, indent=2))
