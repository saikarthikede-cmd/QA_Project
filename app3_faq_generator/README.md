# App 3 - FAQ Generator RAG Pipeline

Upload a text-based PDF, build a local vector index, generate grounded FAQ pairs with page citations, and ask follow-up questions against the same document.

The QA dataset for this app is `test_pdfs/app3_smartpay_manual.pdf`, a SmartPay Gateway product manual covering setup, payment methods, limits, fees, settlement, refunds, disputes, security, integrations, webhooks, support, and troubleshooting.

## Full Pipeline

1. PDF upload

   `POST /upload` accepts only PDFs up to 50 MB. The app extracts text page by page with `pypdf` and rejects scanned/image PDFs with no usable text.

2. Chunking

   Each page is split into overlapping chunks using the shared chunker. Every chunk keeps its page number and source filename so answers can cite evidence.

3. Embedding

   Chunks are embedded locally with `sentence-transformers/all-MiniLM-L6-v2`. This avoids sending the full private document to an embedding API.

4. Vector index

   The embedded chunks are stored once in a reusable LangChain `InMemoryVectorStore` index. Generation, regeneration, "generate more", and chat all reuse this index instead of rebuilding retrieval state for every query.

5. Coverage retrieval for FAQ generation

   The generator searches the document with topic coverage queries such as overview, requirements, process, definitions, exceptions, fees, support, and timelines. Small manuals use full-context coverage; larger PDFs use diversified top-k retrieval.

6. Agentic FAQ generation

   A LangChain tool-calling loop gives the model a `search_document(query)` tool. If the initial context is not enough for 12 diverse FAQs, the model can retrieve more evidence before returning JSON.

7. FAQ normalization and grounding

   The app parses tolerant JSON, removes duplicate questions, checks generated questions against retrieved evidence, repairs bad page citations from the retrieved chunks, and keeps the frontend-safe fields: `question`, `answer`, and `page`.

8. Generate more / regenerate / delete

   `POST /generate-more` asks for new questions while passing the existing questions as an avoid list. `POST /regenerate` replaces only the selected FAQ. `DELETE /faqs/{index}` removes one item and updates the stored list.

9. Agentic RAG chat

   `POST /ask` first retrieves top-k chunks for the user question. If retrieval is below the relevance threshold, the app returns "No relevant content found in the document." If grounded, a LangChain tool-calling QA agent may call `search_document(query)` for additional context before answering.

10. Answer generation

   The LLM is instructed to answer only from retrieved context, avoid guessing, keep the answer concise, and cite page numbers. The API returns both the answer text and the pages used.

## Run

```powershell
cd app3_faq_generator
py -3.11 -m uvicorn main:app --reload --port 8003
# Open http://localhost:8003
```

Or from the repo root:

```powershell
.\run.ps1 3
```

## Endpoints

- `POST /api/set-key` - set a Groq or OpenAI key for LLM calls
- `POST /upload` - upload and index the source PDF
- `POST /generate` - generate the initial FAQ list
- `POST /generate-more` - generate additional FAQs while avoiding existing questions
- `POST /regenerate` - regenerate one FAQ by index
- `DELETE /faqs/{index}` - delete one FAQ
- `GET /faqs` - list current FAQs
- `POST /ask` - ask a custom RAG question about the indexed PDF

## QA Checklist

- Upload `test_pdfs/app3_smartpay_manual.pdf` and confirm it indexes 8 chunks.
- Ask SmartPay questions such as "What is the standard settlement timeline?" or "How long do merchants have to submit dispute evidence?"
- Ask an unrelated question and confirm the app refuses to guess.
- Generate FAQs and check that each item has `question`, `answer`, and `page`.
- Use Generate More and verify new questions do not repeat existing questions.
- Regenerate one FAQ and confirm only that card changes.
- Delete FAQs and confirm the count updates.
