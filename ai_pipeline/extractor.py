# ai_pipeline/extractor.py

from .model_engine import extract_persons
from .regex_engine import extract_regex_entities, compile_contract_1

def process_text(raw_text: str) -> dict:
    """
    Main function called by Team 3 (Backend).
    """
    # 1. Dev A's engine gets the people
    persons = extract_persons(raw_text)
    
    # 2. Dev B's engine gets the numbers/accounts
    objects = extract_regex_entities(raw_text)
    
    # 3. Dev B's compiler builds the final Contract 1 JSON
    final_json = compile_contract_1("FIR_45_2026", persons, objects)
    
    return final_json

