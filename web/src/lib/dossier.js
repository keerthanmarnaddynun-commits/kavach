import { chipLabel } from "./chips.js";

/**
 * Pure helper to format evidence references as plain text strings for print.
 * Handles FIR excerpts with character spans, CSV row references, and money flow evidence.
 */
export function formatEvidenceRefs(evidence) {
  if (!evidence) {
    return [];
  }
  const refs = [];

  function formatFirItem(item) {
    if (!item) return;
    const docId = item.doc_id || item.docId || "doc";
    let spanStr = "";
    if (Array.isArray(item.char_span)) {
      spanStr = item.char_span.join("-");
    } else if (item.char_span) {
      spanStr = String(item.char_span);
    } else if (item.start !== undefined && item.end !== undefined) {
      spanStr = `${item.start}-${item.end}`;
    }
    refs.push(spanStr ? `${docId}, ${spanStr}` : docId);
  }

  function formatCsvItem(item) {
    if (!item) return;
    const file = item.file || item.fileName || "csv";
    const rawRows = item.row_numbers || item.rows || [];
    const rows = Array.isArray(rawRows) ? rawRows : [];
    const sample = rows.slice(0, 10).join(", ");
    const total = item.row_count ?? (item.total_rows ?? rows.length);
    refs.push(
      `${file}, ${sample ? `data rows ${sample}` : "rows none"} (${total} total rows)`
    );
  }

  if (Array.isArray(evidence)) {
    for (const item of evidence) {
      if (item && (item.doc_id || item.char_span)) {
        formatFirItem(item);
      } else if (item && (item.file || item.row_numbers || item.rows)) {
        formatCsvItem(item);
      } else if (typeof item === "string") {
        refs.push(item);
      }
    }
    return refs;
  }

  if (Array.isArray(evidence.fir_evidence)) {
    for (const item of evidence.fir_evidence) {
      formatFirItem(item);
    }
  } else if (evidence.fir_evidence && typeof evidence.fir_evidence === "object") {
    formatFirItem(evidence.fir_evidence);
  }

  if (Array.isArray(evidence.csv_evidence)) {
    for (const item of evidence.csv_evidence) {
      formatCsvItem(item);
    }
  } else if (evidence.csv_evidence && typeof evidence.csv_evidence === "object") {
    formatCsvItem(evidence.csv_evidence);
  }

  if (evidence.evidence_rows && typeof evidence.evidence_rows === "object") {
    formatCsvItem(evidence.evidence_rows);
  }

  if (evidence.doc_id || evidence.char_span) {
    formatFirItem(evidence);
  }

  if (evidence.file && (evidence.row_numbers || evidence.rows || evidence.row_count !== undefined)) {
    formatCsvItem(evidence);
  }

  if (refs.length === 0 && (evidence.accounts || evidence.paise_flow !== undefined)) {
    const accts = Array.isArray(evidence.accounts) ? evidence.accounts : [];
    const sample = accts.slice(0, 10).join(", ");
    const total = evidence.controlled_account_count ?? accts.length;
    const parts = [];
    if (sample) parts.push(`accounts ${sample}`);
    if (total) parts.push(`(${total} controlled)`);
    if (evidence.paise_flow !== undefined) parts.push(`paise flow ${evidence.paise_flow}`);
    if (parts.length > 0) {
      refs.push(parts.join(" "));
    }
  }

  return refs;
}

/**
 * Builds the complete dossier view model from raw API response shapes.
 * Pure function with no clock access, no network calls, and deterministic output.
 */
export function buildDossier({ caseDetail, leads, graph, people, user, generatedAt } = {}) {
  const isCaseAnalyzed = Boolean(caseDetail?.case?.analyzed);
  const analyzed = Boolean(isCaseAnalyzed && leads);

  const fingerprint = (leads && leads.document_hash) || "";

  const title = {
    heading: "Case dossier (draft for review)",
    caseName: caseDetail?.case?.name || "",
    caseId: caseDetail?.case?.case_id || "",
    synthetic: Boolean(caseDetail?.case?.synthetic),
    fingerprint,
    generatedAt: generatedAt || "",
    userName: user?.username || "",
    userRole: user?.role || "",
    notAnalyzedMessage: "Case not analyzed: no leads or graph summary.",
  };

  const disclaimer = (leads && leads.disclaimer) || "";

  const facts = {
    documents: caseDetail?.documents?.length || 0,
    cdrRows: caseDetail?.files?.cdr?.rows || 0,
    bankRows: caseDetail?.files?.bank?.rows || 0,
  };

  let graphSummary = null;
  if (analyzed && graph) {
    const nodes = graph?.elements?.nodes || [];
    const edges = graph?.elements?.edges || [];
    const summary = graph?.summary || {};
    const typeCounts = {};
    for (const n of nodes) {
      const t = (n.data && n.data.type) || "UNKNOWN";
      typeCounts[t] = (typeCounts[t] || 0) + 1;
    }
    const sortedTypes = Object.keys(typeCounts).sort();
    const countsPerType = sortedTypes.map((t) => ({ type: t, count: typeCounts[t] }));
    const byType = {};
    for (const t of sortedTypes) {
      byType[t] = typeCounts[t];
    }
    graphSummary = {
      totalNodes: nodes.length,
      totalEdges: summary.total_edges ?? edges.length,
      schemaVersion: summary.schema_version || "",
      countsPerType,
      byType,
      counts: byType,
    };
  } else {
    graphSummary = {
      totalNodes: 0,
      totalEdges: 0,
      schemaVersion: "",
      countsPerType: [],
      byType: {},
      counts: {},
    };
  }

  let priorityLeads = [];
  if (analyzed && leads && Array.isArray(leads.money_flow)) {
    const peopleList = Array.isArray(people) ? people : [];
    const peopleById = new Map();
    for (const p of peopleList) {
      const pid = p?.person_id || p?.id;
      if (pid) {
        peopleById.set(pid, p);
      }
    }

    const rawLeads = leads.money_flow.slice(0, 10);
    priorityLeads = rawLeads.map((item) => {
      const rawChips = leads.role_chips?.[item.person_id] || [];
      const chips = rawChips.map(chipLabel).filter(Boolean);
      const person = peopleById.get(item.person_id);
      const docRefs = Array.isArray(person?.document_references) ? person.document_references : [];
      const firDocuments = docRefs.slice(0, 10);
      const firDocumentTotal = docRefs.length;

      return {
        rank: item.rank,
        name: item.name,
        personId: item.person_id,
        score: item.score,
        accounts: item.accounts || [],
        chips,
        reasons: item.reasons || [],
        evidenceRefs: formatEvidenceRefs(item.evidence),
        evidence: item.evidence,
        firDocuments,
        firDocumentTotal,
      };
    });
  }

  let detectorLeads = {
    mules: [],
    burners: [],
    all: [],
    hasFlagged: false,
    emptyMessage: "No flagged items.",
  };

  if (analyzed && leads) {
    const mules = (leads.mule_accounts || [])
      .filter((m) => Boolean(m.flagged))
      .map((m) => ({
        id: m.id,
        type: "mule_account",
        score: m.score,
        reasons: m.reasons || [],
        evidenceRowsText: formatEvidenceRefs(m.evidence_rows)[0] || "",
        evidence_rows: m.evidence_rows,
      }));

    const burners = (leads.burner_phones || [])
      .filter((b) => Boolean(b.flagged))
      .map((b) => ({
        id: b.id,
        type: "burner_phone",
        score: b.score,
        reasons: b.reasons || [],
        evidenceRowsText: formatEvidenceRefs(b.evidence_rows)[0] || "",
        evidence_rows: b.evidence_rows,
      }));

    const all = [...mules, ...burners];
    detectorLeads = {
      mules,
      burners,
      all,
      hasFlagged: all.length > 0,
      emptyMessage: "No flagged items.",
    };
  }

  const docs = (caseDetail?.documents || []).map((d) => ({
    docId: d.doc_id,
    fileName: d.filename,
    sha256Raw: d.sha256_raw,
    sha256Text: d.sha256_text,
    chars: d.chars,
  }));

  const cdrFile = {
    name: "CDR",
    fileName: "uploaded file name not recorded",
    rows: caseDetail?.files?.cdr?.rows || 0,
    sha256: caseDetail?.files?.cdr?.sha256 || "",
  };

  const bankFile = {
    name: "Bank Transactions",
    fileName: "uploaded file name not recorded",
    rows: caseDetail?.files?.bank?.rows || 0,
    sha256: caseDetail?.files?.bank?.sha256 || "",
  };

  const hashTable = {
    documents: docs,
    cdr: cdrFile,
    bank: bankFile,
    fingerprint,
    note: "SHA-256 values were computed by the system when each file was stored. sha256_raw is the hash of the uploaded bytes; sha256_text is the hash of the stored text.",
  };

  const baseLimits = leads && Array.isArray(leads.limitations) ? [...leads.limitations] : [];
  const extraLimits = [
    "Typed text only: no OCR",
    "Same person may appear as several entries (same name in different FIRs, or Hindi and Roman spellings)",
  ];
  const limits = [...baseLimits];
  for (const item of extraLimits) {
    if (!limits.includes(item)) {
      limits.push(item);
    }
  }

  const certificateLines = [
    "CERTIFICATE UNDER SECTION 63(4)(c) OF THE BHARATIYA SAKSHYA ADHINIYAM, 2023: PART A (DRAFT TEMPLATE)",
    "This is a draft template produced by KAVACH from recorded values. It is not a signed certificate. The format of the Schedule to the Act governs and the final text must be reviewed by a legal officer before use.",
    "",
    "I, ________, ________, ________, state as follows:",
    "1. The electronic records listed in the hash table of this dossier were taken from the KAVACH case named above (case id and fingerprint as printed in the title block).",
    "2. Identification of each record: the file name, the SHA-256 value of the uploaded bytes and the SHA-256 value of the stored text are listed in the hash table. The algorithm used is SHA-256.",
    "3. The system that produced this dossier is the KAVACH application. The stored texts and CSV files are kept exactly as uploaded; the system computes the hash values when the file is stored.",
    "4. Particulars of the computer or device used to produce this printout: ________.",
    "5. Statement on lawful control and regular use of the device during the relevant period: ________.",
    `6. Date and time of this printout: ${generatedAt || "________"}.`,
    "",
    "Place: ________     Date: ________     Signature: ________",
    "Name and designation: ________",
    "",
    `Hash value (SHA-256) of this case fingerprint: ${fingerprint || "________"}`,
  ];

  const certificateText = certificateLines.join("\n");
  const partBText = "Part B (expert) is not completed by this system.";

  return {
    title,
    disclaimer,
    facts,
    graphSummary,
    priorityLeads,
    detectorLeads,
    hashTable,
    limits,
    certificateText,
    partBText,
    analyzed,
  };
}
