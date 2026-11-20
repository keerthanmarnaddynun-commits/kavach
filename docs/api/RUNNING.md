# Running the KAVACH API

This document provides operational instructions for running the KAVACH API server, initializing user accounts, and loading the synthetic demo case.

## Environment Setup

Use the Python 3.11 virtual environment:

```powershell
.\.venv311\Scripts\python.exe -m pip list
```

## 1. Creating the First Admin User

To initialize authentication, create an administrative account using `scripts/create_user.py`:

```powershell
.\.venv311\Scripts\python.exe scripts/create_user.py <username> <password> --role admin
```

Requirements:
- `username`: 3 to 40 characters matching `^[A-Za-z0-9_.-]{3,40}$`
- `password`: at least 10 characters
- `role`: `admin`, `analyst`, or `viewer`

## 2. Loading the Synthetic Demo Case

To populate the runtime store with the reference synthetic demo case (100 FIR documents, CDR records, bank transactions, and derived graph and leads):

```powershell
.\.venv311\Scripts\python.exe scripts/load_demo_case.py
```

Optional arguments:
- `--runtime-dir <path>`: override the default runtime directory

## 3. Starting the API Server

Start the uvicorn server on `127.0.0.1:8000`:

```powershell
.\.venv311\Scripts\python.exe scripts/run_api.py
```

Optional arguments:
- `--host <ip>`: bind address (default `127.0.0.1`)
- `--port <number>`: port number (default `8000`)

The server sets `HF_HUB_OFFLINE=1` automatically upon launch.

## 4. Exporting OpenAPI Specification

To export the OpenAPI JSON specification:

```powershell
.\.venv311\Scripts\python.exe scripts/export_openapi.py docs/api/openapi.json
```
