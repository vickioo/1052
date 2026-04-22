# Approval Card — MVP Skeleton Notes

## What is here (Phase 1)

| File | Role |
|------|------|
| `types.ts` | All shared types: `ApprovalDecision`, `ApprovalLinkParams`, `ApprovalCardParams`, `ApprovalCallbackPayload`, `ApprovalCallbackResult` |
| `link-builder.ts` | `buildApprovalLink()` — builds signed portal URL, pure function |
| `card-renderer.ts` | `renderApprovalCard()` — returns Feishu card JSON, pure function, no API call |
| `index.ts` | Barrel re-export; callers import only from here |

## What is NOT here (Phase 2+)

- `handleCallback()` — patch card after portal completes decision
- Route registration (`POST /api/channels/feishu/approval-card/callback`)
- `feishu.service.ts` facade (sendApprovalCard / patchApprovalCard)
- `feishu.store.ts` approvalId → messageId mapping
- mycc `approval-bridge.ts` replacement

## Integration sketch (Phase 2)

```
mycc approval-bridge.ts
  → buildApprovalLink()  ←──────────────── approval-card/link-builder
  → renderApprovalCard() ←──────────────── approval-card/card-renderer
  → feishu.service.sendCard(card)

Portal (mobile-approval-portal)
  user approves/rejects
  → POST /api/channels/feishu/approval-card/callback  (Phase 2 route)
      → handleCallback()  ←───────────────── approval-card service (Phase 2)
          → feishu.service.patchCard(messageId, updatedCard)
```

## Smoke checklist (Phase 2 pre-merge)

- [ ] `buildApprovalLink` encodes special chars in token correctly
- [ ] `renderApprovalCard` with status=approved hides "Open" button
- [ ] Callback with duplicate requestId returns `updated: false`
- [ ] Patch card reflects correct status label after callback
- [ ] `tsc --noEmit` passes with zero errors

---

## Phase 2 Update (2026-04-22)

### What is here now

| File | Role |
|------|------|
| `callback-handler.ts` | `handleCallback()` — HMAC-SHA256 token verify, idempotency, in-memory decision store |
| `index.ts` | Updated barrel: exports `handleCallback`, `generateCallbackToken`, `getStoredDecision` |
| `types.ts` | `ApprovalCallbackPayload` extended with optional `token` field |
| `feishu.service.ts` | `approval_submit` / `approval_decide` branches in `handleFeishuCardAction` |

### Token scheme (Phase 2 — plain HMAC)

```
token = HMAC-SHA256(process.env.APPROVAL_TOKEN_SECRET || 'dev-secret', `${approvalId}:${decidedAt}`)
```

- `decidedAt`: ISO-8601 timestamp, included in the callback payload
- JWT upgrade deferred to v3

### Environment variable

```
APPROVAL_TOKEN_SECRET=<your-secret>   # default: 'dev-secret' (dev only)
```

### Card action value shape (for button `value`)

```json
{
  "actionType": "approval_decide",
  "approvalId": "APV-001",
  "decision": "approved",
  "decidedAt": "2026-04-22T10:00:00.000Z",
  "token": "<hmac-hex>",
  "note": "",
  "version": 2
}
```

### Updated smoke checklist

- [x] `handleCallback` rejects invalid HMAC token → returns INVALID_TOKEN error
- [x] `handleCallback` deduplicates by requestId → returns DUPLICATE error
- [x] `handleCallback` stores decision in memory → `getStoredDecision(approvalId)` works
- [x] `feishu.service.ts` `approval_decide` branch wired into `handleFeishuCardAction`
- [x] `tsc --noEmit` passes with zero errors
- [ ] Route `POST /api/channels/feishu/approval-card/callback` (Phase 3)
- [ ] `feishu.store.ts` approvalId → messageId mapping (Phase 3)
- [ ] patchCard on callback to flip card status (Phase 3)
