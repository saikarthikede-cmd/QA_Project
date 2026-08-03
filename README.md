# QA Projects

This repository is a collection of FastAPI-based AI demo applications for document understanding, retrieval, and structured generation. It is designed for evaluation, walkthroughs, and QA testing of LLM-assisted workflows rather than for production deployment.

## What this system does

Each app follows a similar pattern:

1. The user uploads a document, text file, PDF, or data input.
2. The app extracts content and prepares it for retrieval or analysis.
3. A shared LLM layer uses the uploaded content to answer questions, generate structured outputs, compare documents, or classify requests.
4. The app returns a result that is meant to be grounded in the provided content, with citations or structured reasoning where possible.

This means the core behavior is not just “chat with an AI,” but “use AI with context and evidence.”

## Apps in this repository

### 1. Resume Screener
- Upload a job description and one or more resumes.
- The app ranks candidates by relevance and provides justification based on the uploaded content.
- Good QA scenarios: invalid file types, duplicate resumes, missing job description, and score ordering.

### 2. Document Diff Analyzer
- Upload two PDF versions of the same document.
- The app compares them and highlights added, removed, and modified content.
- Good QA scenarios: unrelated documents, missing files, and page-level evidence quality.

### 3. FAQ Generator
- Upload a PDF manual or policy document.
- The app builds a local retrieval index and generates grounded FAQ pairs.
- Good QA scenarios: unrelated questions, duplicate questions, regeneration, and citation accuracy.

### 4. Report Agent
- Upload a report-style PDF.
- The app generates a structured report with sections such as summary, recommendations, and risks.
- Good QA scenarios: short versus long PDFs, scanned documents, and whether citations appear for each section.

### 5. Policy Triage Agent
- Upload a policy document and paste a customer support ticket.
- The app decides whether the issue should be escalated or auto-resolved.
- Good QA scenarios: ambiguous tickets, incomplete policy context, and incorrect classifications.

### 6. Data Analyst Agent
- Upload CSV or PDF-based data content.
- The app can answer follow-up analytical questions and perform basic data reasoning.
- Good QA scenarios: malformed input, missing columns, and whether answer quality stays consistent across turns.

### Portal Dashboard
- The portal provides a single landing page to check the status of all six apps.
- It helps users launch or inspect the apps from one place.

## How the system works internally

The repository uses a shared architecture across apps:

- FastAPI provides the web API layer.
- Uvicorn runs each app as a local service.
- The shared code under shared/ handles LLM access, PDF processing, and common errors.
- Many apps use retrieval-based prompting so the AI is grounded in uploaded files rather than relying only on general knowledge.
- LangChain-style components are used in the shared LLM and retrieval flow.

## Prerequisites

- Python 3.11
- Windows PowerShell
- A Groq or OpenAI API key for the model features
- Internet access for live LLM calls

Install dependencies from the repository root:

```powershell
py -3.11 -m pip install -r requirements.txt
```

> Python 3.14 is not currently recommended for this project because of dependency compatibility issues.

## Quick start

### Option 1: Run all apps together

```powershell
./run_all.ps1
```

This starts the portal and all six apps. The default URLs are:

- Portal: http://localhost:8000
- App 1: http://localhost:8001
- App 2: http://localhost:8002
- App 3: http://localhost:8003
- App 4: http://localhost:8004
- App 5: http://localhost:8005
- App 6: http://localhost:8006

### Option 2: Run a single app

```powershell
./run.ps1 1
./run.ps1 2
./run.ps1 3
./run.ps1 4
./run.ps1 5
./run.ps1 6
```

Each script launches the selected app with Uvicorn on its assigned port.

### Option 3: Run with Docker Compose

```powershell
docker compose up -d --build
```

To stop the containers:

```powershell
docker compose down
```

## How a QA person should test it

A QA person should think of each app as a workflow with three stages:

1. Input validation
   - Check whether the app rejects invalid files and missing required inputs.
   - Verify that the UI gives clear feedback when input is missing or incorrect.

2. Core processing
   - Upload a valid document and observe whether the system processes it without crashing.
   - Confirm that the result is generated in a reasonable amount of time.

3. Output quality
   - Confirm the output is structured correctly.
   - Check whether the app references evidence, cites pages, or provides a sensible explanation.
   - Validate that the response is not hallucinated when the input is weak or unrelated.

## Expected behaviors by app

- Resume Screener should produce a ranked result and include evidence-based reasoning.
- Document Diff should compare the two files and return clear added/removed/modified sections.
- FAQ Generator should return a list of FAQs grounded in the uploaded document.
- Report Agent should create a structured report with sections and page references.
- Policy Triage should classify the ticket based on the policy content provided.
- Data Analyst should answer follow-up questions using the uploaded input.

## API key handling

Each app supports entering a Groq or OpenAI API key at runtime through the UI. The shared LLM client validates the key and uses the provider-specific model configuration.

## Project structure

- app1_resume_screener/ — resume screening app
- app2_doc_diff/ — document comparison app
- app3_faq_generator/ — FAQ generation and RAG app
- app4_report_agent/ — report summarization app
- app5_policy_triage/ — policy triage app
- app6_data_analyst/ — data analysis app
- portal/ — unified dashboard service
- shared/ — common utilities for LLM access, PDF handling, errors, and agent logic
- tests/ — pytest-based regression tests

## Testing

Run the test suite from the repository root:

```powershell
pytest
```

## Notes

- These apps are intended as QA/demo tools, not production-grade services.
- The system is optimized for Python 3.11 and the Windows PowerShell workflow shown above.
- If an app fails, check the input format first, then verify the API key and network connectivity.
