"""
benchmark.py
Run this script to generate the ablation study for the evaluators.
It compares the open-access Davlan/xlm-roberta-base-ner-hrl against the gated ai4bharat/IndicNER.
"""
import os
import time
from transformers import pipeline

# Note for Dev A: To test IndicNER, set your Hugging Face token as an environment variable in your terminal:
# $env:HF_TOKEN="your_huggingface_token_here"
# If not set, the script will gracefully skip IndicNER and only benchmark XLM-RoBERTa.

DATASET = [
    {
        "text": "suspect Vikas Kumar urf Bicky Sector 42 se arrest hua mastermind Rajendra Singh ke order par.",
        "ground_truth_persons": ["Vikas Kumar", "Rajendra Singh"]
    },
    {
        "text": "Pooja Sharma ne 50000 rupees transfer kiye Amit Desai ke account mein hawala ke douran.",
        "ground_truth_persons": ["Pooja Sharma", "Amit Desai"]
    },
    {
        "text": "main accused Rahul Verma farar hai aur uski location unknown hai.",
        "ground_truth_persons": ["Rahul Verma"]
    },
    {
        "text": "FIR lodged against Suresh Patil for illegal arms dealing near the border.",
        "ground_truth_persons": ["Suresh Patil"]
    },
    {
        "text": "informant ne bataya ki don Dawood Ibrahim ka right hand Chhota Rajan Mumbai mein active hai.",
        "ground_truth_persons": ["Dawood Ibrahim", "Chhota Rajan"]
    }
]

def evaluate_model(model_id, is_gated=False):
    print(f"\n--- Loading Model: {model_id} ---")
    
    hf_token = os.environ.get("HF_TOKEN")
    if is_gated and not hf_token:
        print(f"[SKIPPED] {model_id} requires authentication. Please set the HF_TOKEN environment variable.")
        return None

    try:
        ner_pipe = pipeline(
            "ner", 
            model=model_id, 
            aggregation_strategy="simple", 
            device=-1, 
            token=hf_token if is_gated else None
        )
    except Exception as e:
        print(f"[ERROR] Failed to load {model_id}: {e}")
        return None

    print(f"Benchmarking {model_id}...")
    total_expected = 0
    total_matched = 0
    start_time = time.time()

    for item in DATASET:
        text = item["text"]
        expected = set(item["ground_truth_persons"])
        total_expected += len(expected)
        
        results = ner_pipe(text)
        
        # Handle the different tag mapping conventions between the two models
        extracted = set([
            res["word"].strip() 
            for res in results 
            if res["entity_group"] in ["PER", "PERSON", "LABEL_1", "LABEL_2"]
        ])
        
        # Exact/Partial Match logic
        for exp_name in expected:
            if any(exp_name.lower() in ext.lower() or ext.lower() in exp_name.lower() for ext in extracted):
                total_matched += 1

    latency = time.time() - start_time
    accuracy = (total_matched / total_expected) * 100 if total_expected > 0 else 0
    
    return {
        "Accuracy": f"{accuracy:.1f}%",
        "Total Entities Found": f"{total_matched}/{total_expected}",
        "Inference Time": f"{latency:.2f}s"
    }

if __name__ == "__main__":
    print("============================================================")
    print("CRIMI-NEX ABLATION STUDY: Model Evaluation Framework")
    print("============================================================")
    
    # 1. Open-Access Multilingual Fallback
    model_1 = "Davlan/xlm-roberta-base-ner-hrl"
    res_1 = evaluate_model(model_1, is_gated=False)
    
    # 2. Gated Indic-Specific Model
    model_2 = "ai4bharat/IndicNER"
    res_2 = evaluate_model(model_2, is_gated=True)
    
    print("\n============================================================")
    print("FINAL BENCHMARK RESULTS")
    print("============================================================")
    print(f"{'Model':<40} | {'Accuracy':<10} | {'Found':<10} | {'Time'}")
    print("-" * 75)
    
    if res_1:
        print(f"{model_1:<40} | {res_1['Accuracy']:<10} | {res_1['Total Entities Found']:<10} | {res_1['Inference Time']}")
    if res_2:
        print(f"{model_2:<40} | {res_2['Accuracy']:<10} | {res_2['Total Entities Found']:<10} | {res_2['Inference Time']}")
    else:
        print(f"{model_2:<40} | [Requires HF_TOKEN]")
    print("============================================================")