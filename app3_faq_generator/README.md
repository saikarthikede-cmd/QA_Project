# App 3 — FAQ Generator

Upload any PDF and generate FAQ-style Q&A pairs with page citations. Regenerate or delete individual FAQs, or generate more on demand.

## Run

```powershell
cd app3_faq_generator
py -3.11 -m uvicorn main:app --reload --port 8003
# Open http://localhost:8003
```

Or use the root launcher:

```powershell
.\run.ps1 3
```

## Endpoints

- `POST /upload` — upload the source PDF
- `POST /generate` — generate the initial FAQ list
- `POST /generate-more` — generate additional FAQs avoiding existing questions
- `POST /regenerate` — regenerate one FAQ by index
- `DELETE /faqs/{index}` — delete one FAQ
- `GET /faqs` — list current FAQs
- `POST /ask` — ask a custom question about the source PDF

## QA Checklist

- [ ] Upload non-PDF file → rejected
- [ ] Scanned PDF rejected
- [ ] Generate blocked until PDF uploaded
- [ ] Each FAQ has `question`, `answer`, `page`
- [ ] Regenerate replaces only the selected FAQ
- [ ] Delete reduces total count
- [ ] Generate-more avoids duplicate questions
