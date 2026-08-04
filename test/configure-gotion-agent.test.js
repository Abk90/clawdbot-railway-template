import assert from "node:assert/strict";
import test from "node:test";

import {
  GOTION_AGENT_ID,
  GOTION_ALLOWED_SENDERS,
  GOTION_GROUP_ID,
  OPENCLAW_CONTROL_UI_ORIGIN,
  applyGotionConfig,
} from "../src/configure-gotion-agent.js";

test("adds a fail-closed Gotion Telegram route without removing other projects", () => {
  const config = {
    channels: { telegram: { groups: { "-5247758900": { requireMention: true } } } },
    agents: { list: [{ id: "main", default: true }, { id: "oulali-coordinator" }] },
    bindings: [
      {
        agentId: "oulali-coordinator",
        match: {
          channel: "telegram",
          accountId: "default",
          peer: { kind: "group", id: "-5247758900" },
        },
      },
    ],
  };

  assert.equal(applyGotionConfig(config), true);
  assert.deepEqual(config.gateway.controlUi.allowedOrigins, [OPENCLAW_CONTROL_UI_ORIGIN]);
  assert.equal(config.gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback, false);
  assert.equal(config.channels.telegram.dmPolicy, "allowlist");
  assert.deepEqual(config.channels.telegram.allowFrom, ["7532850730"]);
  assert.equal(config.channels.telegram.groupPolicy, "allowlist");
  assert.equal(config.channels.telegram.contextVisibility, "allowlist_quote");
  assert.equal(config.channels.telegram.historyLimit, 40);
  assert.equal(config.channels.telegram.configWrites, false);
  assert.equal(config.channels.telegram.actions.sendMessage, undefined);
  assert.equal(config.channels.telegram.actions.deleteMessage, false);
  assert.equal(config.channels.telegram.groups["-5247758900"].requireMention, true);

  const group = config.channels.telegram.groups[GOTION_GROUP_ID];
  assert.equal(group.requireMention, true);
  assert.equal(group.groupPolicy, "allowlist");
  assert.deepEqual(group.allowFrom, GOTION_ALLOWED_SENDERS);
  assert.deepEqual(group.skills, []);
  assert.deepEqual(group.tools.allow, ["session_status"]);
  assert.equal(group.tools.deny.includes("exec"), true);
  assert.equal(group.tools.deny.includes("message"), true);
  assert.match(group.systemPrompt, /projet 265/);
  assert.match(group.systemPrompt, /5 000 m²/);
  assert.match(group.systemPrompt, /Ne modifie jamais Odoo, paiement/i);
  assert.match(group.systemPrompt, /Definition of Done/);
  assert.match(group.systemPrompt, /Mustapha est arabophone/);
  assert.match(group.systemPrompt, /aucune écriture Odoo ne doit être tentée/);

  const agent = config.agents.list.find((item) => item.id === GOTION_AGENT_ID);
  assert.deepEqual(agent.model, { primary: "deepseek/deepseek-v4-flash" });
  assert.equal(agent.thinkingDefault, "off");
  assert.deepEqual(agent.tools.allow, ["session_status"]);
  assert.equal(agent.tools.deny.includes("exec"), true);
  assert.equal(agent.tools.deny.includes("message"), true);
  assert.equal(agent.tools.elevated.enabled, false);
  assert.equal(config.agents.list.some((item) => item.id === "oulali-coordinator"), true);
  assert.equal(config.bindings.some((item) => item.agentId === "oulali-coordinator"), true);

  assert.deepEqual(config.bindings[0], {
    agentId: GOTION_AGENT_ID,
    match: {
      channel: "telegram",
      accountId: "default",
      peer: { kind: "group", id: GOTION_GROUP_ID },
    },
  });
});

test("is idempotent", () => {
  const config = { channels: { telegram: {} } };
  assert.equal(applyGotionConfig(config), true);
  assert.equal(applyGotionConfig(config), false);
  assert.equal(config.bindings.filter((binding) => binding.agentId === GOTION_AGENT_ID).length, 1);
});
