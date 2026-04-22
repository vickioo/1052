/**
 * Approval Card Module — Callback Handler (Phase 2)
 *
 * Validates a portal callback, stores the decision, and returns a Feishu toast.
 *
 * Token scheme: plain HMAC-SHA256
 *   token = HMAC-SHA256(secret, `${approvalId}:${decidedAt}`)
 *   where decidedAt is the ISO-8601 timestamp included in the payload.
 *   JWT is deferred to v3.
 *
 * The secret is read from process.env.APPROVAL_TOKEN_SECRET (default: 'dev-secret').
 */

import crypto from 'node:crypto'
import type { ApprovalCallbackPayload, ApprovalCallbackResult, ApprovalDecision } from './types.js'

// ---------------------------------------------------------------------------
// In-memory store: approvalId → { decision, note, operator, decidedAt }
// Suitable for single-instance deployments; replace with DB-backed store as needed.
// ---------------------------------------------------------------------------

type StoredDecision = {
  decision: ApprovalDecision
  note?: string
  operator?: string
  decidedAt: string
  requestId?: string
}

const decisionStore = new Map<string, StoredDecision>()

export function getStoredDecision(approvalId: string): StoredDecision | undefined {
  return decisionStore.get(approvalId)
}

// ---------------------------------------------------------------------------
// HMAC token helpers
// ---------------------------------------------------------------------------

function getSecret(): string {
  return process.env.APPROVAL_TOKEN_SECRET ?? 'dev-secret'
}

/**
 * Generate a callback verification token.
 * The caller (portal) and the handler must use the same secret + decidedAt.
 */
export function generateCallbackToken(approvalId: string, decidedAt: string): string {
  return crypto
    .createHmac('sha256', getSecret())
    .update(`${approvalId}:${decidedAt}`)
    .digest('hex')
}

/**
 * Verify that the token in the callback payload is valid.
 * Uses timing-safe comparison to prevent timing attacks.
 */
function verifyToken(approvalId: string, decidedAt: string, token: string): boolean {
  const expected = generateCallbackToken(approvalId, decidedAt)
  try {
    return crypto.timingSafeEqual(Buffer.from(token, 'hex'), Buffer.from(expected, 'hex'))
  } catch {
    return false
  }
}

// ---------------------------------------------------------------------------
// Idempotency
// ---------------------------------------------------------------------------

const seenRequestIds = new Set<string>()

function isDuplicate(requestId: string | undefined): boolean {
  if (!requestId) return false
  if (seenRequestIds.has(requestId)) return true
  seenRequestIds.add(requestId)
  return false
}

// ---------------------------------------------------------------------------
// Main handler
// ---------------------------------------------------------------------------

export type CallbackError =
  | { code: 'MISSING_FIELDS'; message: string }
  | { code: 'INVALID_TOKEN'; message: string }
  | { code: 'DUPLICATE'; message: string }
  | { code: 'INVALID_DECISION'; message: string }

export type CallbackHandlerResult =
  | { ok: true; result: ApprovalCallbackResult }
  | { ok: false; error: CallbackError }

/**
 * Process an approval callback payload.
 *
 * Expected payload shape (from portal POST body):
 *   {
 *     approvalId: string,
 *     decision: 'approved' | 'rejected',
 *     decidedAt: string,   // ISO-8601 — used as HMAC input
 *     token: string,       // HMAC-SHA256 hex
 *     note?: string,
 *     operator?: string,
 *     requestId?: string,
 *   }
 */
export async function handleCallback(
  payload: ApprovalCallbackPayload & { token?: string },
): Promise<CallbackHandlerResult> {
  const { approvalId, decision, note, operator, requestId } = payload
  const decidedAt = payload.decidedAt ?? new Date().toISOString()
  const token = payload.token ?? ''

  // 1. Validate required fields
  if (!approvalId || !decision) {
    return {
      ok: false,
      error: { code: 'MISSING_FIELDS', message: 'approvalId and decision are required' },
    }
  }

  // 2. Validate decision value
  if (decision !== 'approved' && decision !== 'rejected') {
    return {
      ok: false,
      error: { code: 'INVALID_DECISION', message: `Unknown decision: ${decision}` },
    }
  }

  // 3. Verify HMAC token
  if (!verifyToken(approvalId, decidedAt, token)) {
    return {
      ok: false,
      error: { code: 'INVALID_TOKEN', message: 'Token verification failed' },
    }
  }

  // 4. Idempotency check
  if (isDuplicate(requestId)) {
    return {
      ok: false,
      error: {
        code: 'DUPLICATE',
        message: `Request ${requestId} has already been processed`,
      },
    }
  }

  // 5. Store decision
  decisionStore.set(approvalId, { decision, note, operator, decidedAt, requestId })

  return {
    ok: true,
    result: {
      updated: true,
      status: decision,
    },
  }
}
