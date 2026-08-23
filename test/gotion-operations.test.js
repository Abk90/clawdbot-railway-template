import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";


const SCRIPT = path.resolve("src/gotion-operations.py");
const OWNER = "7532850730";

function harness(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "gotion-operations-test-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const env = { ...process.env, GOTION_OPERATIONS_DB: path.join(dir, "operations.sqlite3") };
  const tool = (payload, expectedStatus = 0) => {
    const run = spawnSync("python3", [SCRIPT, "tool"], {
      env,
      input: JSON.stringify(payload),
      encoding: "utf8",
    });
    assert.equal(run.status, expectedStatus, run.stderr || run.stdout);
    return JSON.parse(run.stdout);
  };
  return { env, tool };
}

test("rejects an unverified Telegram actor", (t) => {
  const { tool } = harness(t);
  const result = tool(
    {
      operation: "case_record",
      requester_sender_id: "9999999999",
      case_type: "daily_report",
      summary: "rapport",
      facts: {},
    },
    1,
  );
  assert.equal(result.ok, false);
  assert.match(result.error, /non vérifié/);
});

test("records, completes and deduplicates a purchase case", (t) => {
  const { tool } = harness(t);
  const first = tool({
    operation: "case_record",
    requester_sender_id: OWNER,
    case_type: "purchase",
    work_date: "2026-08-23",
    external_ref: "ticket-42",
    summary: "Deux raccords achetés",
    facts: {
      purchase_date: "2026-08-23",
      purchaser: "Mustapha",
      lines: [{ description: "Raccord", qty: 2, uom: "unité" }],
    },
    evidence: ["photo ticket 42"],
  });
  assert.equal(first.ok, true);
  assert.equal(first.result.status, "collecting");
  assert.equal(first.result.next_questions.length, 3);

  const second = tool({
    operation: "case_record",
    requester_sender_id: OWNER,
    case_type: "purchase",
    work_date: "2026-08-23",
    external_ref: "ticket-42",
    summary: "Achat complété",
    facts: {
      supplier: "Droguerie Exemple",
      company: "Miya Belkora Design",
      total_amount: 100,
      payment_source: "Caisse Mustapha",
      receipt_location: "Chantier Gotion",
      receipt_proof: "photo comptage réception",
    },
  });
  assert.equal(second.result.id, first.result.id);
  assert.equal(second.result.status, "ready_for_review");
  assert.deepEqual(second.result.missing, []);
});

test("refuses sensitive identity fields in a group case", (t) => {
  const { tool } = harness(t);
  const result = tool(
    {
      operation: "case_record",
      requester_sender_id: OWNER,
      case_type: "worker",
      summary: "nouvel ouvrier",
      facts: { cin_number: "AB123456" },
    },
    1,
  );
  assert.equal(result.ok, false);
  assert.match(result.error, /donnée sensible interdite/);
});

test("prepares and approves but does not execute an Odoo note", (t) => {
  const { tool } = harness(t);
  const recorded = tool({
    operation: "case_record",
    requester_sender_id: OWNER,
    case_type: "incident",
    work_date: "2026-08-23",
    external_ref: "incident-1",
    summary: "Incident documenté",
    facts: {
      incident_date: "2026-08-23",
      reporter: "Ahmed",
      zone: "Zone test",
      description: "Fuite observée",
      proof: "photo 1",
      next_action: "Contrôle vanne",
    },
  });
  const caseId = recorded.result.id;
  const prepared = tool({
    operation: "action_prepare",
    requester_sender_id: OWNER,
    case_id: caseId,
    action_type: "chatter_note",
    payload: { model: "project.task", record_id: 4107, body: `${caseId} — fuite observée` },
  });
  assert.equal(prepared.result.status, "pending_approval");
  assert.match(prepared.result.approval_command, /gotion_approve/);
  assert.match(prepared.result.notice, /Aucune écriture/);

  const approved = tool({
    operation: "approve",
    requester_sender_id: OWNER,
    proposal_id: prepared.result.proposal_id,
  });
  assert.equal(approved.result.status, "approved");
  assert.match(approved.result.next_command, /gotion_execute/);
});

test("daily reminder uses darija for a verified field chief", (t) => {
  const { env, tool } = harness(t);
  tool({
    operation: "actor_upsert",
    requester_sender_id: OWNER,
    telegram_id: "9999912345",
    name: "Mustapha Test",
    role: "chef_chantier",
    language: "darija",
    daily_report_required: true,
    voice_preferred: true,
    active: true,
  });
  const run = spawnSync("python3", [SCRIPT, "reminder", "ask", "2026-08-23"], {
    env,
    encoding: "utf8",
  });
  assert.equal(run.status, 0, run.stderr);
  assert.match(run.stdout, /Mustapha Test/);
  assert.match(run.stdout, /عافاك/);
});
