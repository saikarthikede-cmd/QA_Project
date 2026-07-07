# App 5 — PDF Policy Triage Agent

Upload a policy PDF and paste a support ticket. The agent retrieves relevant policy clauses via tool calls, decides whether to **ESCALATE** or **AUTO-RESOLVE**, and drafts a grounded reply with page citations.

## Run

```powershell
cd app5_policy_triage
py -3.11 -m uvicorn main:app --reload --port 8005
# Open http://localhost:8005
```

Or use the root launcher:

```powershell
.\run.ps1 5
```

## Endpoints

- `POST /upload` — upload the policy PDF
- `POST /triage` — submit a support ticket and receive a decision + draft reply

## QA Checklist

- [ ] Ticket box blocked until policy PDF uploaded
- [ ] Agent shows tool call steps (what queries it ran)
- [ ] Decision (ESCALATE/AUTO-RESOLVE) is grounded in retrieved policy text
- [ ] Draft reply cites policy page numbers
- [ ] Ticket about something not in policy → escalates with explanation
- [ ] Scanned PDF rejected
