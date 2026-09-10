# Crimi-Nex: Model Evaluation & Benchmark Results Log
**Date:** 10-09-2026

## 1. Hinglish FIR Ablation Study (`benchmark.py`)

* **Test Suite:** 5 Synthetic FIR texts containing Romanized Hinglish phrasing.
* **Ground Truth:** 8 total target Person (`PER`) entities.
* **Environment:** Local CPU execution (`device=-1`).

### Raw Comparative Output:
```text
============================================================
CRIMI-NEX ABLATION STUDY: Model Evaluation Framework
============================================================

Model                                    | Accuracy   | Found      | Time
---------------------------------------------------------------------------
Davlan/xlm-roberta-base-ner-hrl          | 100.0%     | 8/8        | 0.31s
ai4bharat/IndicNER                       | 87.5%      | 7/8        | 0.32s
============================================================
```

## 2. Native Devanagari A/B Benchmark (`benchmark_indic.py`)

* **Test Suite:** 6 Native Hindi FIR scenarios (Devanagari script).
* **Evaluation Focus:** Entity completeness, matra/vowel integrity, subword fragmentation, and latency.

### Raw Comparative Output:
```text
=========================================================================================================
CRIMI-NEX A/B BENCHMARK: Native Devanagari (Hindi) NER Evaluation
=========================================================================================================

[Case #1] Input: "अपराधी विकास कुमार को सेक्टर ४२ से गिरफ्तार किया गया।"
Davlan/xlm-roberta-base-ner-hrl     | 0.0537s    | विकास कुमार [PER|1.00]
ai4bharat/IndicNER                  | 0.1368s    | विकास कमार [PER|0.97], सक [LOC|0.63]

[Case #2] Input: "राजेंद्र सिंह ने बैंक से पैसे चुराए और फरार हो गया।"
Davlan/xlm-roberta-base-ner-hrl     | 0.0390s    | राजेंद्र सिंह [PER|1.00]
ai4bharat/IndicNER                  | 0.0422s    | र [PER|1.00], ##ाजदर सिह [PER|0.93]

[Case #3] Input: "पीड़िता पूजा शर्मा ने अमित देसाई के खिलाफ धोखाधड़ी की प्राथमिकी दर्ज कराई।"
Davlan/xlm-roberta-base-ner-hrl     | 0.0450s    | पूजा शर्मा [PER|1.00], अमित देसाई [PER|1.00]
ai4bharat/IndicNER                  | 0.0513s    | पजा शरमा [PER|0.88], अमित दसा [PER|0.87]

[Case #4] Input: "मुख्य आरोपी राहुल वर्मा की तलाश में पुलिस जगह-जगह छापेमारी कर रही है।"
Davlan/xlm-roberta-base-ner-hrl     | 0.0491s    | राहुल वर्मा [PER|1.00]
ai4bharat/IndicNER                  | 0.0438s    | र [PER|1.00], ##ाह [PER|0.99], वरमा [PER|0.96]

[Case #5] Input: "खुफिया सूचना के आधार पर दाऊद इब्राहिम और छोटा राजन के मुंबई ठिकानों पर दबिश दी गई।"
Davlan/xlm-roberta-base-ner-hrl     | 0.0405s    | दाऊद इब्राहिम [PER|0.94], छोटा राजन [PER|0.93], मुंबई [LOC|1.00]
ai4bharat/IndicNER                  | 0.0462s    | द [PER|0.98], ##ाऊद इबराह [PER|0.86], छोटा राज [PER|0.87], मबई [LOC|0.95]

[Case #6] Input: "अवैध हथियार तस्करी मामले में सुरेश पाटिल को सीमा सुरक्षा बल ने पकड़ा।"
Davlan/xlm-roberta-base-ner-hrl     | 0.0342s    | सुरेश पाटिल [PER|1.00]
ai4bharat/IndicNER                  | 0.0514s    | सरश पाट [PER|0.86]

=========================================================================================================
SUMMARY
=========================================================================================================
Total Sentences Tested: 6
Davlan/xlm-roberta-base-ner-hrl     Total Latency: 0.2615s (Avg: 0.0436s/sentence)
ai4bharat/IndicNER                  Total Latency: 0.3717s (Avg: 0.0619s/sentence)
=========================================================================================================
```
