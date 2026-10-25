"""
backend/main.py
FastAPI application for SIH26189: AI-Powered Criminal Network Analysis System.
Exposes endpoints to extract criminal networks from raw text reports and return
graph elements conforming to contracts/graph_render_schema.json.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

from ai_pipeline.extractor import process_text
from backend.database import graph_service

app = FastAPI(
    title="Kavach Crime Network API",
    description="Criminal Network Extraction & Graph Intelligence Engine",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisRequest(BaseModel):
    text: str = Field(..., description="Raw FIR, narrative, or surveillance report text")
    doc_id: Optional[str] = Field("FIR_45_2026", description="Unique case/document identifier")


@app.get("/")
def health_check() -> Dict[str, str]:
    return {"status": "online", "system": "Kavach SIH26189 Backend"}


@app.post("/api/analyze")
def analyze_network(request: AnalysisRequest) -> Dict[str, Any]:
    """
    Extracts entities & relationships via Indic NLP/Regex pipeline (Contract 1),
    computes network centrality & kingpin metrics, and returns the graph render payload (Contract 2).
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Report text must not be empty.")

    try:
        # Step 1: Run AI extraction pipeline
        ai_output = process_text(request.text)

        # Step 2: Transform to Graph Render Schema (Contract 2) with Centrality & Kingpin
        graph_payload = graph_service.transform_to_render_schema(ai_output, raw_text=request.text)

        return graph_payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis pipeline error: {str(e)}")