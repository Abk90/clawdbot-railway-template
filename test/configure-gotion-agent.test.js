import assert from "node:assert/strict";
import test from "node:test";

import {
  GOTION_AGENT_ID,
  GOTION_ALLOWED_SENDERS,
  GOTION_GROUP_ID,
  GOTION_OPERATION_TOOLS,
  GOTION_PLUGIN_PATH,
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
  assert.equal(group.requireMention, false);
  assert.equal(group.groupPolicy, "allowlist");
  assert.deepEqual(group.allowFrom, GOTION_ALLOWED_SENDERS);
  assert.deepEqual(group.skills, []);
  assert.deepEqual(group.tools.allow, ["session_status", ...GOTION_OPERATION_TOOLS]);
  assert.equal(group.tools.deny.includes("exec"), true);
  assert.equal(group.tools.deny.includes("message"), true);
  assert.match(group.systemPrompt, /projet Odoo #265/);
  assert.match(group.systemPrompt, /ne mentionne aucun bootstrap/);
  assert.match(group.systemPrompt, /gotion_case_record/);
  assert.match(group.systemPrompt, /trois questions/);
  assert.match(group.systemPrompt, /arabe marocain\/darija/);
  assert.match(group.systemPrompt, /\/gotion_approve/);
  assert.match(group.systemPrompt, /restent en brouillon/);
  assert.deepEqual(config.tools.media.image.attachments, { mode: "all", maxAttachments: 4 });
  assert.equal(config.tools.media.audio.models[0].model, "gpt-4o-transcribe");
  assert.equal(config.plugins.entries["gotion-operations"].enabled, true);
  assert.equal(config.plugins.load.paths.includes(GOTION_PLUGIN_PATH), true);

  const agent = config.agents.list.find((item) => item.id === GOTION_AGENT_ID);
  assert.deepEqual(agent.model, {
    primary: "openai/gpt-5.5",
    fallbacks: ["deepseek/deepseek-v4-flash", "google/gemini-2.5-flash"],
  });
  assert.equal(agent.thinkingDefault, "low");
  assert.deepEqual(agent.tools.allow, ["session_status", ...GOTION_OPERATION_TOOLS]);
  assert.equal(agent.tools.deny.includes("exec"), true);
  assert.equal(agent.tools.deny.includes("message"), true);
  assert.equal(agent.tools.elevated.enabled, false);
  assert.equal(agent.tts.auto, "tagged");
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

test("preserves exact field actors added by the owner", () => {
  const config = {
    channels: {
      telegram: {
        groups: {
          [GOTION_GROUP_ID]: { allowFrom: ["9999912345"], requireMention: true },
        },
      },
    },
  };
  applyGotionConfig(config);
  assert.equal(config.channels.telegram.groups[GOTION_GROUP_ID].allowFrom.includes("9999912345"), true);
  assert.equal(config.channels.telegram.groups[GOTION_GROUP_ID].requireMention, false);
});
