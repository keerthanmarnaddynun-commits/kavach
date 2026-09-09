"""
Crimi-Nex AI Pipeline: Model Engine (Dev A - Phase 3)
=====================================================
Named Entity Recognition (NER) pipeline optimized for Indic and multilingual texts,
specifically targeted at criminal investigation reports, FIRs, and intelligence briefs.

Hardware Constraint: Laptop CPU execution (no GPU required).
Design: Global lazy loading / singleton pattern to prevent redundant weight reloads.
Post-Processing: Contextual alias extraction (urf, alias, @, aka).
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import torch
from transformers import Pipeline, pipeline

from dotenv import load_dotenv
load_dotenv() 

hf_token = os.environ.get("HF_TOKEN")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("ai_pipeline.model_engine")

# Model identifiers:
# Primary Indic NER model (ai4bharat/IndicNER) with fallback to multilingual XLM-RoBERTa NER
PRIMARY_MODEL_ID = os.getenv("NER_PRIMARY_MODEL", "ai4bharat/IndicNER")
FALLBACK_MODEL_ID = os.getenv("NER_FALLBACK_MODEL", "Davlan/xlm-roberta-base-ner-hrl")

# Global singleton holder for the Hugging Face pipeline
_NER_PIPELINE: Optional[Pipeline] = None


def get_target_device() -> int:
    """
    Returns device ID for CPU execution.
    Per project hardware constraints, inference runs on CPU (device=-1 in transformers).
    """
    return -1


def load_pipeline(force_reload: bool = False) -> Pipeline:
    """
    Initializes and returns the Hugging Face NER pipeline object.
    
    Adheres to lazy loading / singleton strategy:
    - If the pipeline is already loaded into memory, it returns the cached instance.
    - If not, it attempts to initialize ai4bharat/IndicNER on CPU.
    - If the primary model is unavailable (e.g. gated access / authentication / timeout),
      it gracefully falls back to the reliable XLM-R multilingual model (Davlan/xlm-roberta-base-ner-hrl).
    
    Args:
        force_reload: If True, forces re-initialization of the model pipeline.
        
    Returns:
        Pipeline: Active Hugging Face 'ner' pipeline.
    """
    global _NER_PIPELINE

    if _NER_PIPELINE is not None and not force_reload:
        return _NER_PIPELINE

    logger.info("Initializing NER Pipeline on CPU...")
    device = get_target_device()
    hf_token = os.environ.get("HF_TOKEN")

    # Attempt 1: Try Primary Indic Model (ai4bharat/IndicNER)
    try:
        logger.info(f"Attempting to load primary model: '{PRIMARY_MODEL_ID}' (CPU mode)...")
        _NER_PIPELINE = pipeline(
            task="ner",
            model=PRIMARY_MODEL_ID,
            tokenizer=PRIMARY_MODEL_ID,
            aggregation_strategy="simple",
            device=device,
            token=hf_token,
        )
        logger.info(f"Successfully loaded primary model: '{PRIMARY_MODEL_ID}'.")
        return _NER_PIPELINE

    except Exception as primary_exc:
        logger.warning(
            f"Primary model '{PRIMARY_MODEL_ID}' could not be loaded. "
            f"Reason: {type(primary_exc).__name__}: {primary_exc}"
        )
        logger.info(f"Falling back to high-reliability XLM-R Indic-capable model: '{FALLBACK_MODEL_ID}'...")

    # Attempt 2: Fallback to XLM-RoBERTa multilingual NER model
    try:
        _NER_PIPELINE = pipeline(
            task="ner",
            model=FALLBACK_MODEL_ID,
            tokenizer=FALLBACK_MODEL_ID,
            aggregation_strategy="simple",
            device=device,
        )
        logger.info(f"Successfully loaded fallback model: '{FALLBACK_MODEL_ID}'.")
        return _NER_PIPELINE

    except Exception as fallback_exc:
        logger.error(
            f"Failed to initialize fallback model '{FALLBACK_MODEL_ID}'. "
            f"Reason: {type(fallback_exc).__name__}: {fallback_exc}"
        )
        raise RuntimeError(
            f"Failed to load both primary ('{PRIMARY_MODEL_ID}') and fallback ('{FALLBACK_MODEL_ID}') models. "
            "Please verify internet connection and Hugging Face cache."
        ) from fallback_exc


# Alias indicator pattern: looks for 'urf', 'alias', '@', 'aka' immediately following the person
# Extracts 1 to 3 words for the alias, stopping before common boundary prepositions, location words, or punctuation.
ALIAS_REGEX = re.compile(
    r"^\s*[\(\[]?\s*(?:urf|alias|@|aka)\s*[:\-\s]?\s*[\"\'\(\[]?\s*"
    r"([A-Za-z0-9_]+(?:\s+[A-Za-z0-9_]+){0,2}?)\s*[\"\'\)\]]?"
    r"(?=\s+(?:se|ke|ki|ka|ko|ne|mein|me|par|aur|dwara|arrest|arrested|escaped|absconding|sector|road|street|gali|lane|"
    r"village|thana|chowki|police|ps|r/o|s/o|d/o|w/o|near|for|is|was|from|at|in|on|to|resident|having|aged)\b|[,\.;\(\)\[\]]|\s*$)",
    re.IGNORECASE,
)


def _extract_alias(text: str, end_idx: int) -> List[str]:
    """
    Contextually scans the raw text immediately following a person entity's char_span
    to detect aliases preceded by indicators: 'urf', 'alias', '@', 'aka'.
    
    Args:
        text: Full raw narrative text.
        end_idx: Ending character index of the detected person's char_span.
        
    Returns:
        List[str]: List containing the extracted alias string if found, otherwise empty list.
    """
    following_text = text[end_idx:]
    match = ALIAS_REGEX.search(following_text)
    if not match:
        return []

    alias_candidate = match.group(1).strip()
    # Remove leading/trailing enclosing quotes or brackets if present
    alias_candidate = re.sub(r"^[\"\'\(\[]+|[\"\'\)\]]+$", "", alias_candidate).strip()
    if alias_candidate:
        return [alias_candidate]
    return []


def extract_persons(text: str) -> List[Dict[str, Any]]:
    """
    Extracts PERSON entities from text using the NER pipeline and post-processes aliases (Dev A - Phase 3).
    
    Inference:
        Passes text through the lazily-loaded Hugging Face pipeline.
        
    Filtering:
        Strictly filters detected entities for 'PER' or 'PERSON' labels.
        
    Alias Resolution:
        Scans text immediately following each person's char_span for keywords
        ('urf', 'alias', '@', 'aka') and populates the 'aliases' list.
        
    Formatting:
        Structures detected persons according to the Crimi-Nex contract schema:
        - 'id': Sequential identifier string (e.g., 'ent_01', 'ent_02').
        - 'canonical_name': Extracted entity name stripped of whitespace.
        - 'aliases': List of alias strings (e.g., ['Bicky']).
        - 'type': Statically set to 'PERSON'.
        - 'char_span': [start, end] integer character indices.
        - 'ai_confidence': Model probability score rounded to 4 decimal places.
        
    Args:
        text: Raw investigative narrative / FIR text.
        
    Returns:
        List[Dict[str, Any]]: List of formatted PERSON entity dictionaries.
    """
    if not text or not text.strip():
        return []

    ner_pipeline = load_pipeline()
    raw_entities = ner_pipeline(text)

    persons: List[Dict[str, Any]] = []
    idx = 1

    for ent in raw_entities:
        label = (ent.get("entity_group") or ent.get("entity") or "").strip().upper()
        
        # Strictly filter for person entities
        if label in {"PER", "PERSON"}:
            name = ent.get("word", "").strip()
            if not name:
                continue

            start_idx = int(ent["start"])
            end_idx = int(ent["end"])

            # Phase 3: Extract contextual aliases
            aliases = _extract_alias(text, end_idx)

            person_record: Dict[str, Any] = {
                "id": f"ent_{idx:02d}",
                "canonical_name": name,
                "aliases": aliases,
                "type": "PERSON",
                "char_span": [start_idx, end_idx],
                "ai_confidence": round(float(ent["score"]), 4),
            }
            persons.append(person_record)
            idx += 1

    return persons


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("CRIMI-NEX AI ENGINE: Alias Resolution Verification (Phase 3)")
    print("=" * 60)

    start_time = time.perf_counter()
    active_pipe = load_pipeline()
    load_duration = time.perf_counter() - start_time

    print(f"\n[OK] NER Pipeline ready in {load_duration:.2f} seconds.")
    print(f"     Active Model: {getattr(active_pipe.model, 'name_or_path', 'Custom')}")
    print(f"     Device:       {active_pipe.device} (CPU)")
    print(f"     Task:         {active_pipe.task}")

    # Phase 3 test sentence
    sample_sentence = (
        "suspect Vikas Kumar urf Bicky Sector 42 se arrest hua mastermind Rajendra Singh ke order par."
    )
    print("\n--- Input Sentence ---")
    print(sample_sentence)

    print("\n--- Running extract_persons() with Alias Resolution ---")
    extract_start = time.perf_counter()
    extracted_persons = extract_persons(sample_sentence)
    extract_duration = time.perf_counter() - extract_start

    print(f"Extracted {len(extracted_persons)} person(s) in {extract_duration:.4f}s:\n")
    print(json.dumps(extracted_persons, indent=2))

    # Assertions for verification
    assert len(extracted_persons) >= 2, "Expected at least 2 persons."
    assert extracted_persons[0]["aliases"] == ["Bicky"], f"Expected ['Bicky'], got {extracted_persons[0]['aliases']}"
    assert extracted_persons[1]["aliases"] == [], f"Expected [], got {extracted_persons[1]['aliases']}"

    print("\n[VERIFIED] Vikas Kumar aliases:   ", extracted_persons[0]["aliases"])
    print("[VERIFIED] Rajendra Singh aliases: ", extracted_persons[1]["aliases"])
    print("\n" + "=" * 60)
    print("PHASE 3 VERIFICATION COMPLETE")
    print("=" * 60 + "\n")
