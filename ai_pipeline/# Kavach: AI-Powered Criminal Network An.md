# Kavach: AI-Powered Criminal Network Analysis & Extraction Engine (SIH26189)

An end-to-end NLP and Graph Intelligence system designed to extract complex criminal syndicates, entity hierarchies, and transaction topologies from unstructured, code-mixed (Hinglish/Devanagari) police First Information Reports (FIRs) and surveillance logs.

---

## 1. Problem Statement & Architecture
Analyzing police records in multilingual environments poses distinct NLP challenges:
- **Code-Mixing & Transliteration:** Blending Romanized Hindi (Hinglish) with formal legal terminology.
- **Underworld Aliases & Operative Handles:** Linking contextual street names (`urf`, `alias`, `@`, `aka`) to formal canonical names.
- **Entity Fragmentation:** Sub-token splits breaking downstream relational graphs.

### Technical Architecture Overview