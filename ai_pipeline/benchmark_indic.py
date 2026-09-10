"""
benchmark_indic.py
Isolated A/B benchmark evaluating Davlan/xlm-roberta-base-ner-hrl vs. ai4bharat/IndicNER
on native Devanagari (Hindi) investigative FIR narratives.
"""
import os
import sys
import time
from dotenv import load_dotenv
from transformers import pipeline

# Ensure UTF-8 output encoding for terminals handling Devanagari script (e.g. Windows cp1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Immediately load environment variables from .env
load_dotenv()

# Test sentences in native Devanagari script
TEST_SENTENCES = [
    "अपराधी विकास कुमार को सेक्टर ४२ से गिरफ्तार किया गया।",
    "राजेंद्र सिंह ने बैंक से पैसे चुराए और फरार हो गया।",
    "पीड़िता पूजा शर्मा ने अमित देसाई के खिलाफ धोखाधड़ी की प्राथमिकी दर्ज कराई।",
    "मुख्य आरोपी राहुल वर्मा की तलाश में पुलिस जगह-जगह छापेमारी कर रही है।",
    "खुफिया सूचना के आधार पर दाऊद इब्राहिम और छोटा राजन के मुंबई ठिकानों पर दबिश दी गई।",
    "अवैध हथियार तस्करी मामले में सुरेश पाटिल को सीमा सुरक्षा बल ने पकड़ा।",
]

def format_entities(results):
    """Format pipeline output into readable entity strings: 'Name [TAG|score]'."""
    if not results:
        return "None detected"
    
    formatted = []
    for res in results:
        entity_name = res.get("word", "").strip()
        label = res.get("entity_group") or res.get("entity") or "UNK"
        score = res.get("score", 0.0)
        formatted.append(f"{entity_name} [{label}|{score:.2f}]")
    
    return ", ".join(formatted) if formatted else "None detected"

def run_benchmarks():
    hf_token = os.environ.get("HF_TOKEN")
    
    model_xlmr_id = "Davlan/xlm-roberta-base-ner-hrl"
    model_indic_id = "ai4bharat/IndicNER"

    print("=" * 105)
    print("CRIMI-NEX A/B BENCHMARK: Native Devanagari (Hindi) NER Evaluation")
    print("=" * 105)

    # 1. Load Davlan/xlm-roberta-base-ner-hrl
    print(f"\n[1/2] Loading '{model_xlmr_id}'...")
    try:
        pipe_xlmr = pipeline(
            "ner",
            model=model_xlmr_id,
            aggregation_strategy="simple",
            device=-1
        )
        print(" -> Successfully loaded XLM-RoBERTa.")
    except Exception as e:
        print(f" -> [ERROR] Failed to load {model_xlmr_id}: {e}")
        pipe_xlmr = None

    # 2. Load ai4bharat/IndicNER
    print(f"\n[2/2] Loading '{model_indic_id}'...")
    try:
        pipe_indic = pipeline(
            "ner",
            model=model_indic_id,
            aggregation_strategy="simple",
            device=-1,
            token=hf_token
        )
        print(" -> Successfully loaded IndicNER.")
    except Exception as e:
        print(f" -> [ERROR] Failed to load {model_indic_id}: {e}")
        pipe_indic = None

    print("\n" + "=" * 105)
    print("SIDE-BY-SIDE EVALUATION RESULTS")
    print("=" * 105)

    total_time_xlmr = 0.0
    total_time_indic = 0.0

    for idx, sentence in enumerate(TEST_SENTENCES, start=1):
        print(f"\n[Case #{idx}] Input Sentence:")
        print(f"  \"{sentence}\"")
        print("-" * 105)

        # Evaluate XLM-R
        if pipe_xlmr:
            t0 = time.time()
            res_xlmr = pipe_xlmr(sentence)
            time_xlmr = time.time() - t0
            total_time_xlmr += time_xlmr
            entities_xlmr = format_entities(res_xlmr)
            time_xlmr_str = f"{time_xlmr:.4f}s"
        else:
            time_xlmr_str = "N/A"
            entities_xlmr = "Model not loaded"

        # Evaluate IndicNER
        if pipe_indic:
            t0 = time.time()
            res_indic = pipe_indic(sentence)
            time_indic = time.time() - t0
            total_time_indic += time_indic
            entities_indic = format_entities(res_indic)
            time_indic_str = f"{time_indic:.4f}s"
        else:
            time_indic_str = "N/A"
            entities_indic = "Requires HF_TOKEN / Model not loaded"

        # Formatted side-by-side comparison
        print(f"{'Model':<35} | {'Latency':<10} | Extracted Entities")
        print("-" * 36 + "+-" + "-" * 11 + "+-" + "-" * 54)
        print(f"{model_xlmr_id:<35} | {time_xlmr_str:<10} | {entities_xlmr}")
        print(f"{model_indic_id:<35} | {time_indic_str:<10} | {entities_indic}")
        print("-" * 105)

    print("\n" + "=" * 105)
    print("SUMMARY")
    print("=" * 105)
    print(f"Total Sentences Tested: {len(TEST_SENTENCES)}")
    if pipe_xlmr:
        print(f"{model_xlmr_id:<35} Total Latency: {total_time_xlmr:.4f}s (Avg: {total_time_xlmr/len(TEST_SENTENCES):.4f}s/sentence)")
    if pipe_indic:
        print(f"{model_indic_id:<35} Total Latency: {total_time_indic:.4f}s (Avg: {total_time_indic/len(TEST_SENTENCES):.4f}s/sentence)")
    print("=" * 105)

if __name__ == "__main__":
    run_benchmarks()
