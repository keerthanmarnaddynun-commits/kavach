# Running KAVACH Web Application

This document provides instructions for running the KAVACH web application frontend and backend.
The web application requires the backend API running to load cases, authenticate, and process queries.

## 1. Network Ports

- Backend API: `http://127.0.0.1:8000`
- Frontend Development Server: `http://127.0.0.1:5173`

The frontend communicates with the backend via the Vite dev proxy configured in `web/vite.config.js`.

## 2. Starting the Backend API

To start the FastAPI backend service:

```powershell
.\.venv311\Scripts\python.exe scripts/run_api.py
```

The API service runs on host `127.0.0.1` and port `8000`.

## 3. Loading the Demo Case

To load the pre-configured synthetic demo case into the active runtime:

```powershell
.\.venv311\Scripts\python.exe scripts/load_demo_case.py
```

Stop any running backend API instance prior to running `load_demo_case.py` to prevent concurrent audit-log access.

## 3b. Creating a User

The login page needs an account. Create one before starting the backend (the script asks for the password, at least 10 characters):

```powershell
.\.venv311\Scripts\python.exe scripts/create_user.py --username <name> --role admin
```

Roles are viewer, analyst and admin. Uploads, analysis and break analysis need analyst or admin.
## 4. Starting the Frontend Development Server

To launch the local Vite development server:

```powershell
npm --prefix web run dev
```

The server binds to port `5173` with `strictPort: true`. Access the web user interface in a browser at:
`http://localhost:5173`

## 5. Building the Production Bundle

To build the static production distribution in `web/dist`:

```powershell
npm --prefix web run build
```

Alternatively, use the runner check script:

```powershell
.\.venv311\Scripts\python.exe scripts/web_check.py build
```

## 6. Running Frontend Unit Tests

To run the Vitest test suite:

```powershell
npm --prefix web test
```

Or via the check runner:

```powershell
.\.venv311\Scripts\python.exe scripts/web_check.py test
```

## 7. Checking Bundle Size

To verify that the production bundle in `web/dist` does not exceed 3 MB:

```powershell
.\.venv311\Scripts\python.exe scripts/web_check.py size
```
