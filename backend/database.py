"""
backend/database.py
Graph persistence and analytics engine.
Connects to Neo4j to persist Contract 1 criminal networks using Cypher MERGE queries;
computes mathematical network centrality and dynamic Kingpin detection via NetworkX.
Outputs schema compliant with contracts/graph_render_schema.json.
"""

import os
import re
import hashlib
from typing import Dict, Any, List, Optional
import networkx as nx

# Optional Neo4j driver
try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False


class GraphService:
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "")
        self.driver = None

        if NEO4J_AVAILABLE and self.uri and self.password:
            try:
                self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            except Exception as e:
                print(f"[WARN] Failed to connect to Neo4j: {e}. Using local graph engine.")

    def close(self):
        if self.driver:
            self.driver.close()

    def persist_contract_1(self, ai_output: Dict[str, Any]) -> bool:
        """
        Ingests Contract 1 entities and relationships into Neo4j using Cypher MERGE queries.
        Creates or updates typed nodes (PERSON, PHONE, IMEI, ACCOUNT) and directed edges
        (OWNS_DEVICE, ASSOCIATED_IMEI, COMMUNICATED_WITH, TRANSFERRED_FUNDS, CONTROLS_ACCOUNT).
        """
        if not self.driver:
            return False

        entities = ai_output.get("entities", [])
        relationships = ai_output.get("relationships", [])

        try:
            with self.driver.session() as session:
                # 1. Ingest / Update Entities as Typed Nodes
                for ent in entities:
                    e_id = ent.get("id")
                    if not e_id:
                        continue

                    e_type = ent.get("type", "ENTITY").upper()
                    label = (
                        re.sub(r"[^A-Za-z0-9_]", "", e_type)
                        if e_type in {"PERSON", "PHONE", "IMEI", "ACCOUNT"}
                        else "Entity"
                    )

                    node_query = f"""
                    MERGE (n:{label} {{id: $id}})
                    SET n:Entity,
                        n.id = $id,
                        n.type = $type,
                        n.canonical_name = $canonical_name,
                        n.aliases = $aliases,
                        n.value = $value,
                        n.bank = $bank,
                        n.ai_confidence = $ai_confidence,
                        n.char_span = $char_span
                    """
                    params = {
                        "id": e_id,
                        "type": ent.get("type", "UNKNOWN"),
                        "canonical_name": ent.get("canonical_name", ""),
                        "aliases": ent.get("aliases", []),
                        "value": ent.get("value", ""),
                        "bank": ent.get("bank", ""),
                        "ai_confidence": float(ent.get("ai_confidence", 1.0)),
                        "char_span": ent.get("char_span", []),
                    }
                    session.run(node_query, params)

                # 2. Ingest / Update Directed Relationships
                for rel in relationships:
                    source_id = rel.get("source")
                    target_id = rel.get("target")
                    if not source_id or not target_id:
                        continue

                    raw_relation = rel.get("relation", "RELATED_TO").upper()
                    rel_type = re.sub(r"[^A-Za-z0-9_]", "", raw_relation) or "RELATED_TO"

                    rel_query = f"""
                    MATCH (s {{id: $source}})
                    MATCH (t {{id: $target}})
                    MERGE (s)-[r:{rel_type}]->(t)
                    SET r.relation = $relation,
                        r.amount = $amount
                    """
                    rel_params = {
                        "source": source_id,
                        "target": target_id,
                        "relation": raw_relation,
                        "amount": rel.get("amount"),
                    }
                    session.run(rel_query, rel_params)

            return True
        except Exception as e:
            print(f"[WARN] Neo4j persistence error: {e}")
            return False

    def transform_to_render_schema(self, ai_output: Dict[str, Any], raw_text: str = "") -> Dict[str, Any]:
        """
        Converts AI extraction output (Contract 1) into graph_render_schema.json (Contract 2).
        Calculates mathematical degree, betweenness, and eigenvector centralities to dynamically
        pinpoint the syndicate Kingpin without hardcoded string matching.
        """
        # Persist to Neo4j if driver is active
        if self.driver:
            self.persist_contract_1(ai_output)

        entities = ai_output.get("entities", [])
        relationships = ai_output.get("relationships", [])

        # Build NetworkX graph with domain relationship weights
        G = nx.Graph()
        for ent in entities:
            G.add_node(ent["id"], type=ent.get("type", "UNKNOWN"))

        # Domain edge weights reflect operational command & financial authority in criminal networks
        REL_WEIGHTS = {
            "CONTROLS_ACCOUNT": 3.0,
            "COMMUNICATED_WITH": 1.5,
            "OWNS_DEVICE": 1.5,
            "TRANSFERRED_FUNDS": 1.0,
            "ASSOCIATED_IMEI": 0.5,
        }

        for rel in relationships:
            r_type = rel.get("relation", "RELATED_TO").upper()
            w = REL_WEIGHTS.get(r_type, 1.0)
            G.add_edge(rel["source"], rel["target"], weight=w, distance=1.0 / w, relation=r_type)

        # Mathematical Centrality Calculations
        scores: Dict[str, float] = {}
        if len(G) <= 1:
            scores = {n: 1.0 for n in G.nodes}
        else:
            # Weighted Degree Centrality (Strength)
            strength = dict(G.degree(weight="weight"))
            max_strength = max(strength.values()) if strength and max(strength.values()) > 0 else 1.0
            deg_centrality = {n: strength.get(n, 0.0) / max_strength for n in G.nodes}

            # Weighted Betweenness Centrality (Shortest path distance = 1 / weight)
            bet_centrality = (
                nx.betweenness_centrality(G, weight="distance", normalized=True)
                if len(G) > 2
                else {n: 0.0 for n in G.nodes}
            )

            # Eigenvector Centrality (Influence propagation)
            try:
                eig_centrality = nx.eigenvector_centrality(G, weight="weight", max_iter=1000)
            except Exception:
                eig_centrality = nx.degree_centrality(G)

            # Mathematical Composite Centrality Score
            for node_id in G.nodes:
                raw_score = (
                    0.40 * deg_centrality.get(node_id, 0.0)
                    + 0.30 * bet_centrality.get(node_id, 0.0)
                    + 0.30 * eig_centrality.get(node_id, 0.0)
                )
                scores[node_id] = round(max(0.05, raw_score), 2)

        # Dynamic Kingpin Determination based strictly on highest composite centrality score
        person_nodes = [e for e in entities if e.get("type") == "PERSON"]
        candidates = [p["id"] for p in person_nodes] if person_nodes else list(G.nodes)
        kingpin_id = max(candidates, key=lambda nid: scores.get(nid, 0.0)) if candidates else None

        # Format elements.nodes with accurate, un-overridden centrality scores
        render_nodes = []
        for ent in entities:
            e_id = ent["id"]
            e_type = ent.get("type", "UNKNOWN")

            # Label formatting
            if e_type == "PERSON":
                aliases = ent.get("aliases", [])
                label = f"{ent.get('canonical_name')}"
                if aliases:
                    label += f" ({aliases[0]})"
            elif e_type == "PHONE":
                label = ent.get("value", "")
            elif e_type == "IMEI":
                val = ent.get("value", "")
                label = f"IMEI: {val[:5]}..." if len(val) > 8 else f"IMEI: {val}"
            elif e_type == "ACCOUNT":
                bank = ent.get("bank", "ACC")
                val = ent.get("value", "")
                label = f"{bank}: {val[:5]}..." if len(val) > 8 else f"{bank}: {val}"
            else:
                label = ent.get("value", e_id)

            is_kingpin = (e_id == kingpin_id)
            # Use actual mathematical centrality score calculated by NetworkX
            c_score = scores.get(e_id, 0.0)

            render_nodes.append({
                "data": {
                    "id": e_id,
                    "label": label,
                    "type": e_type,
                    "isKingpin": is_kingpin,
                    "centrality_score": c_score,
                    "ai_confidence": ent.get("ai_confidence", 1.0)
                }
            })

        # Format elements.edges
        render_edges = []
        for idx, rel in enumerate(relationships, 1):
            render_edges.append({
                "data": {
                    "id": f"edge_{idx:02d}",
                    "source": rel["source"],
                    "target": rel["target"],
                    "label": rel["relation"]
                }
            })

        # Generate deterministic document hash
        doc_hash = (
            hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            if raw_text
            else "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

        return {
            "summary": {
                "total_nodes": len(render_nodes),
                "total_edges": len(render_edges),
                "kingpin_node_id": kingpin_id or (entities[0]["id"] if entities else ""),
                "document_hash": doc_hash
            },
            "elements": {
                "nodes": render_nodes,
                "edges": render_edges
            }
        }


graph_service = GraphService()
