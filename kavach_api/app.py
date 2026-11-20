"""FastAPI application factory, authentication, middleware, and API endpoints."""
from __future__ import annotations

from collections import defaultdict
from contextlib import asynccontextmanager
import logging
from typing import Any, Callable, Sequence

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from kavach_api.analysis_service import NothingToAnalyzeError, build_graph
from kavach_api.evidence import (
    EvidenceError,
    document_view,
    edge_evidence_by_id,
    node_evidence,
    rows as fetch_csv_rows,
)
from kavach_api.extract_service import default_extractor, model_loaded
from kavach_api.jobs import JobNotFoundError, JobRunner, JobStore, validate_job_id
from kavach_api.leads import (
    BreakError,
    InvalidGroupError,
    _extract_owner_maps,
    build_leads,
    run_break,
)
from kavach_api.render import compute_edge_id, render_graph
from kavach_api.security import (
    ROLES,
    TokenError,
    UserStore,
    UserStoreCorrupt,
    create_token,
    decode_token,
    load_or_create_secret,
    role_at_least,
)
from kavach_api.settings import Settings, load_settings
from kavach_api.storage import (
    CaseNotFoundError,
    DocumentNotFoundError,
    DuplicateDocument,
    InvalidIdError,
    Storage,
    StorageError,
    validate_case_id,
    validate_doc_id,
)
from kavach_api.timeline import build_timeline

logger = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str


def _get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Dependency: Extract and validate Bearer token, verifying user exists."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
        )

    token = parts[1]
    secret = request.app.state.secret
    try:
        claims = decode_token(secret, token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        )

    username = claims.get("sub") or claims.get("username", "")
    user = request.app.state.user_store.get(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )

    return {"username": user["username"], "role": user["role"], "claims": claims}


def require_role(min_role: str) -> Callable[..., dict[str, Any]]:
    """Dependency factory enforcing minimum user role."""
    def _role_checker(user: dict[str, Any] = Depends(_get_current_user)) -> dict[str, Any]:
        if not role_at_least(user["role"], min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user['role']}' is insufficient. Required: '{min_role}'",
            )
        return user

    return _role_checker


def create_app(
    settings: Settings | None = None,
    extractor: Callable[..., dict[str, Any]] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        settings = load_settings()

    settings.runtime_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Storage(settings)
        secret_path = settings.runtime_dir / "secret.key"
        secret = load_or_create_secret(secret_path)
        user_store = UserStore(
            settings.runtime_dir / "users.json",
            iterations=settings.pbkdf2_iterations,
        )
        audit_log = store.audit_log if hasattr(store, "audit_log") else None
        if audit_log is None:
            from kavach_api.audit import AuditLog
            audit_log = AuditLog(settings.runtime_dir / "audit.log")

        job_store = JobStore(settings.runtime_dir)
        job_runner = JobRunner(job_store=job_store)
        from kavach_api.security import LoginLimiter
        limiter = LoginLimiter(
            limit=settings.login_fail_limit,
            window_seconds=settings.login_fail_window_seconds,
        )

        app.state.settings = settings
        app.state.store = store
        app.state.secret = secret
        app.state.user_store = user_store
        app.state.audit_log = audit_log
        app.state.job_store = job_store
        app.state.job_runner = job_runner
        app.state.limiter = limiter
        app.state.extractor = extractor or default_extractor()

        yield

        job_runner.shutdown()

    app = FastAPI(title="KAVACH API", version="1.1", lifespan=lifespan)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Consistent Error Handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        code_map = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
            413: "upload_too_large",
            422: "validation_error",
            429: "too_many_requests",
            500: "internal_error",
        }
        code = getattr(exc, "code", None) or code_map.get(exc.status_code, "http_error")
        headers = exc.headers or {}
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": exc.detail}},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": "validation_error", "message": "Request validation failed"}},
        )

    @app.exception_handler(InvalidIdError)
    async def invalid_id_handler(request: Request, exc: InvalidIdError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": {"code": "invalid_id", "message": str(exc)}},
        )

    @app.exception_handler(CaseNotFoundError)
    async def case_not_found_handler(request: Request, exc: CaseNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": {"code": "case_not_found", "message": str(exc)}},
        )

    @app.exception_handler(DocumentNotFoundError)
    async def doc_not_found_handler(request: Request, exc: DocumentNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": {"code": "document_not_found", "message": str(exc)}},
        )

    @app.exception_handler(DuplicateDocument)
    async def duplicate_doc_handler(request: Request, exc: DuplicateDocument):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": {"code": "duplicate_document", "message": str(exc)}},
        )

    @app.exception_handler(EvidenceError)
    async def evidence_error_handler(request: Request, exc: EvidenceError):
        status_code = (
            status.HTTP_404_NOT_FOUND
            if exc.code in ("node_not_found", "edge_not_found", "document_missing")
            else status.HTTP_400_BAD_REQUEST
        )
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(JobNotFoundError)
    async def job_not_found_handler(request: Request, exc: JobNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": {"code": "job_not_found", "message": str(exc)}},
        )

    @app.exception_handler(InvalidGroupError)
    async def invalid_group_handler(request: Request, exc: InvalidGroupError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": "invalid_groups", "message": str(exc)}},
        )

    @app.exception_handler(NothingToAnalyzeError)
    async def nothing_to_analyze_handler(request: Request, exc: NothingToAnalyzeError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": {"code": "nothing_to_analyze", "message": str(exc)}},
        )

    @app.exception_handler(TokenError)
    async def token_error_handler(request: Request, exc: TokenError):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": {"code": "unauthorized", "message": str(exc)}},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled internal exception: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"code": "internal_error", "message": "Internal server error"}},
        )

    # Public Routes
    @app.get("/api/health")
    def health():
        """Health check endpoint: public, returns status and queue state without paths."""
        return {
            "model_loaded": model_loaded(),
            "queue_length": app.state.job_runner.queue_length(),
            "status": "ok",
            "version": "1.1",
        }

    @app.post("/api/auth/login")
    def login(body: LoginRequest):
        """User login endpoint returning HS256 access token."""
        username = body.username
        password = body.password
        limiter = app.state.limiter

        blocked, retry_after = limiter.is_blocked(username)
        if blocked:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts",
                headers={"Retry-After": str(retry_after)},
            )

        user = app.state.user_store.authenticate(username, password)
        if user is None:
            limiter.record_failure(username)
            app.state.audit_log.append(
                actor=username,
                role="none",
                action="login_failed",
                detail={"username": username},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        limiter.record_success(username)
        ttl = settings.jwt_ttl_minutes * 60
        token = create_token(
            secret=app.state.secret,
            username=user["username"],
            role=user["role"],
            ttl_seconds=ttl,
        )
        app.state.audit_log.append(
            actor=user["username"],
            role=user["role"],
            action="login_success",
            detail={"username": user["username"]},
        )
        return {
            "access_token": token,
            "expires_in": ttl,
            "role": user["role"],
            "token_type": "bearer",
            "username": user["username"],
        }

    @app.get("/api/auth/me")
    def me(user: dict[str, Any] = Depends(require_role("viewer"))):
        """Return authenticated user identity and role."""
        return {"role": user["role"], "username": user["username"]}

    # Admin Routes
    @app.post("/api/admin/users", status_code=status.HTTP_201_CREATED)
    def create_user_endpoint(
        body: CreateUserRequest,
        current_user: dict[str, Any] = Depends(require_role("admin")),
    ):
        """Admin endpoint to create a new user."""
        if len(body.password) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 10 characters",
            )

        try:
            created = app.state.user_store.create_user(body.username, body.password, body.role)
        except ValueError as exc:
            msg = str(exc)
            if "already exists" in msg.lower():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

        app.state.audit_log.append(
            actor=current_user["username"],
            role=current_user["role"],
            action="user_created",
            detail={"assigned_role": body.role, "created_user": body.username},
        )
        return {"role": created["role"], "username": created["username"]}

    @app.get("/api/admin/audit")
    def get_audit(
        limit: int = Query(default=50, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        current_user: dict[str, Any] = Depends(require_role("admin")),
    ):
        """Admin endpoint to retrieve audit log entries."""
        return app.state.audit_log.read(limit=limit, offset=offset)

    @app.get("/api/admin/audit/verify")
    def verify_audit(current_user: dict[str, Any] = Depends(require_role("admin"))):
        """Admin endpoint to verify hash chain integrity of audit log."""
        ok, count, first_bad = app.state.audit_log.verify()
        return {"entries": count, "first_bad_index": first_bad, "ok": ok}

    # Case Read Routes (Viewer Role)
    @app.get("/api/cases")
    def list_cases_endpoint(current_user: dict[str, Any] = Depends(require_role("viewer"))):
        """List cases with summary counts and analyzed status."""
        cases = app.state.store.list_cases()
        summaries: list[dict[str, Any]] = []
        for c in cases:
            cid = c["case_id"]
            cdir = app.state.store.case_dir(cid)
            finfo = app.state.store.files_info(cid)
            doc_count = len(app.state.store.list_documents(cid))
            cdr_info = finfo.get("cdr") or {}
            bank_info = finfo.get("bank") or {}
            cdr_rows_cnt = cdr_info.get("row_count", 0) if isinstance(cdr_info, dict) else 0
            bank_rows_cnt = bank_info.get("row_count", 0) if isinstance(bank_info, dict) else 0
            analyzed = (cdir / "derived" / "graph.json").is_file()

            summaries.append(
                {
                    "analyzed": analyzed,
                    "case_id": cid,
                    "counts": {
                        "bank_rows": bank_rows_cnt,
                        "cdr_rows": cdr_rows_cnt,
                        "documents": doc_count,
                    },
                    "created_at": c.get("created_at", ""),
                    "name": c.get("name", ""),
                    "synthetic": bool(c.get("synthetic", False)),
                }
            )
        return summaries

    @app.get("/api/cases/{case_id}")
    def get_case_detail_endpoint(
        case_id: str,
        current_user: dict[str, Any] = Depends(require_role("viewer")),
    ):
        """Get case detail, documents, files, and recent jobs. Logs case_opened audit."""
        validate_case_id(case_id)
        case = app.state.store.get_case(case_id)
        app.state.audit_log.append(
            actor=current_user["username"],
            role=current_user["role"],
            action="case_opened",
            case_id=case_id,
        )
        docs = app.state.store.list_documents(case_id)
        files = app.state.store.files_info(case_id)
        jobs = app.state.job_store.list_for_case(case_id)
        return {
            "case": case,
            "documents": docs,
            "files": files,
            "latest_jobs": jobs[-5:] if jobs else [],
        }

    @app.get("/api/cases/{case_id}/graph")
    def get_graph_endpoint(
        case_id: str,
        current_user: dict[str, Any] = Depends(require_role("viewer")),
    ):
        """Retrieve Contract 2 Cytoscape rendered graph for a case."""
        validate_case_id(case_id)
        app.state.store.get_case(case_id)
        graph = build_graph(app.state.store, case_id)
        return render_graph(graph)

    @app.get("/api/cases/{case_id}/leads")
    def get_leads_endpoint(
        case_id: str,
        current_user: dict[str, Any] = Depends(require_role("viewer")),
    ):
        """Retrieve prioritized leads and detector outputs. Logs leads_viewed audit."""
        validate_case_id(case_id)
        app.state.store.get_case(case_id)
        app.state.audit_log.append(
            actor=current_user["username"],
            role=current_user["role"],
            action="leads_viewed",
            case_id=case_id,
        )
        return build_leads(app.state.store, case_id)

    @app.get("/api/cases/{case_id}/people")
    def get_people_endpoint(
        case_id: str,
        current_user: dict[str, Any] = Depends(require_role("viewer")),
    ):
        """List person nodes with aliases, roles, devices, accounts, and document references."""
        validate_case_id(case_id)
        app.state.store.get_case(case_id)
        graph = build_graph(app.state.store, case_id)
        person_nodes = [n for n in graph.get("nodes", []) if n.get("type") == "PERSON"]
        owner_maps = _extract_owner_maps(graph)
        person_to_accounts = owner_maps["person_to_accounts"]
        person_to_phones = owner_maps["person_to_phones"]

        # Collect candidate same_as relationships if present in internal graph
        suggested_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for e in graph.get("edges", []):
            if e.get("relation") == "SAME_AS_CANDIDATE":
                u = str(e.get("source"))
                v = str(e.get("target"))
                reasons = e.get("reasons", [])
                suggested_map[u].append({"other_person_id": v, "reasons": reasons})
                suggested_map[v].append({"other_person_id": u, "reasons": reasons})

        people_list: list[dict[str, Any]] = []
        for n in person_nodes:
            pid = n["id"]
            pname = n.get("canonical_name") or (n.get("names", [None])[0] if n.get("names") else pid)
            ctrl_accts = sorted([a for a in person_to_accounts.get(pid, []) if not str(a).startswith("ACCOUNT:")])
            owned_phs = sorted([p for p in person_to_phones.get(pid, []) if not str(p).startswith("PHONE:")])
            docs = sorted(n.get("source_firs", []))

            people_list.append(
                {
                    "aliases": n.get("aliases", []),
                    "canonical_name": pname,
                    "controlled_accounts": ctrl_accts,
                    "document_references": docs,
                    "documents": docs,
                    "id": pid,
                    "name": pname,
                    "owned_phones": owned_phs,
                    "person_id": pid,
                    "roles": n.get("roles", []),
                    "suggested_same_person": suggested_map.get(pid, []),
                }
            )
        return people_list

    @app.get("/api/cases/{case_id}/nodes/{node_id}")
    def get_node_endpoint(
        case_id: str,
        node_id: str,
        current_user: dict[str, Any] = Depends(require_role("viewer")),
    ):
        """Retrieve node detail with FIR spans, CSV row references, and neighbours."""
        validate_case_id(case_id)
        app.state.store.get_case(case_id)
        graph = build_graph(app.state.store, case_id)
        return node_evidence(app.state.store, case_id, graph, node_id)

    @app.get("/api/cases/{case_id}/edges/{edge_id}")
    def get_edge_endpoint(
        case_id: str,
        edge_id: str,
        current_user: dict[str, Any] = Depends(require_role("viewer")),
    ):
        """Retrieve edge detail by Contract 2 edge ID combining all internal edges."""
        validate_case_id(case_id)
        app.state.store.get_case(case_id)
        graph = build_graph(app.state.store, case_id)
        return edge_evidence_by_id(app.state.store, case_id, graph, edge_id)

    @app.get("/api/cases/{case_id}/documents/{doc_id}")
    def get_document_endpoint(
        case_id: str,
        doc_id: str,
        current_user: dict[str, Any] = Depends(require_role("viewer")),
    ):
        """Retrieve document text, hashes, and entity/relation spans."""
        validate_case_id(case_id)
        validate_doc_id(doc_id)
        app.state.store.get_case(case_id)
        graph = build_graph(app.state.store, case_id)
        return document_view(app.state.store, case_id, doc_id, graph)

    @app.get("/api/cases/{case_id}/rows")
    def get_rows_endpoint(
        case_id: str,
        file: str = Query(..., pattern="^(cdr|bank)$"),
        rows: str = Query(..., description="Comma-separated 1-based row numbers"),
        current_user: dict[str, Any] = Depends(require_role("viewer")),
    ):
        """Retrieve requested raw rows (max 200) from stored CSV."""
        validate_case_id(case_id)
        app.state.store.get_case(case_id)

        try:
            row_numbers = [int(x.strip()) for x in rows.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="rows parameter must contain comma-separated integers",
            )

        if not row_numbers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one row number must be specified",
            )

        if len(row_numbers) > 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At most 200 rows can be requested",
            )

        finfo = app.state.store.files_info(case_id)
        f_entry = finfo.get(file) or {}
        sha256_hash = f_entry.get("sha256", "") if isinstance(f_entry, dict) else ""

        try:
            matched_rows = fetch_csv_rows(app.state.store, case_id, file, row_numbers)
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"CSV file '{file}' does not exist for case {case_id}",
            )

        return {
            "file": f"{file}.csv",
            "rows": matched_rows,
            "sha256": sha256_hash,
        }

    @app.get("/api/cases/{case_id}/timeline")
    def get_timeline_endpoint(
        case_id: str,
        bucket: str = Query(default="day", pattern="^(day|hour)$"),
        current_user: dict[str, Any] = Depends(require_role("viewer")),
    ):
        """Retrieve aggregated event timeline per day or hour bucket."""
        validate_case_id(case_id)
        app.state.store.get_case(case_id)
        return build_timeline(app.state.store, case_id, bucket)

    @app.get("/api/jobs/{job_id}")
    def get_job_endpoint(
        job_id: str,
        current_user: dict[str, Any] = Depends(require_role("viewer")),
    ):
        """Retrieve background job status by job ID."""
        validate_job_id(job_id)
        job = app.state.job_store.get(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job not found: {job_id}",
            )
        return job

    return app
