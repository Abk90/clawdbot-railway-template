import assert from "node:assert/strict";
import test from "node:test";

import {
  OULALI_AGENT_ID,
  OULALI_ALLOWED_SENDERS,
  OULALI_GROUP_ID,
  applyOulaliConfig,
} from "../src/configure-oulali-agent.js";

test("adds a fail-closed Oulali Telegram route without removing main", () => {
  const config = { channels: { telegram: { groups: { "*": { requireMention: false } } } } };

  assert.equal(applyOulaliConfig(config), true);
  assert.equal(config.channels.telegram.dmPolicy, "allowlist");
  assert.deepEqual(config.channels.telegram.allowFrom, ["7532850730"]);
  assert.equal(config.channels.telegram.groupPolicy, "allowlist");
  assert.equal(config.channels.telegram.contextVisibility, "allowlist_quote");
  assert.equal(config.channels.telegram.historyLimit, 30);
  assert.equal(config.channels.telegram.configWrites, false);
  assert.equal(config.channels.telegram.actions.sendMessage, undefined);
  assert.equal(config.channels.telegram.actions.deleteMessage, false);
  assert.equal(config.channels.telegram.groups["*"], undefined);

  const group = config.channels.telegram.groups[OULALI_GROUP_ID];
  assert.equal(group.requireMention, true);
  assert.equal(group.groupPolicy, "allowlist");
  assert.deepEqual(group.allowFrom, OULALI_ALLOWED_SENDERS);
  assert.deepEqual(group.skills, []);
  assert.deepEqual(group.tools.allow, ["session_status"]);
  assert.equal(group.tools.deny.includes("exec"), true);
  assert.equal(group.tools.deny.includes("message"), true);
  assert.match(group.systemPrompt, /validation d'Ahmed est requise/);

  assert.equal(config.agents.list.some((agent) => agent.id === "main" && agent.default), true);
  const agent = config.agents.list.find((item) => item.id === OULALI_AGENT_ID);
  assert.deepEqual(agent.tools.allow, ["session_status"]);
  assert.equal(agent.tools.deny.includes("exec"), true);
  assert.equal(agent.tools.deny.includes("message"), true);
  assert.equal(agent.tools.elevated.enabled, false);

  assert.deepEqual(config.bindings[0], {
    agentId: OULALI_AGENT_ID,
    match: {
      channel: "telegram",
      accountId: "default",
      peer: { kind: "group", id: OULALI_GROUP_ID },
    },
  });
});

test("is idempotent and preserves unrelated agents, bindings, and explicit groups", () => {
  const config = {
    channels: { telegram: { groups: { "-100999": { requireMention: true } } } },
    agents: { list: [{ id: "main", default: true }, { id: "other" }] },
    bindings: [{ agentId: "other", match: { channel: "telegram", accountId: "ally" } }],
  };

  assert.equal(applyOulaliConfig(config), true);
  assert.equal(applyOulaliConfig(config), false);
  assert.equal(config.channels.telegram.groups["-100999"].requireMention, true);
  assert.equal(config.agents.list.some((agent) => agent.id === "other"), true);
  assert.equal(config.bindings.some((binding) => binding.agentId === "other"), true);
  assert.equal(config.bindings.filter((binding) => binding.agentId === OULALI_AGENT_ID).length, 1);
});
