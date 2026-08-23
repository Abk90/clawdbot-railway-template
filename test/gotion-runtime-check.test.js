import test from "node:test";
import assert from "node:assert/strict";

import {
  parseGatewayJsonOutput,
  runtimeStatusFromGatewayPayload,
} from "../src/gotion-runtime-check.js";

test("runtime readiness accepts names and slash aliases from commands.list", () => {
  const status = runtimeStatusFromGatewayPayload(
    {
      commands: [
        { name: "gotion_status" },
        { nativeName: "gotion_actor" },
        { textAliases: ["/gotion_approve", "/gotion_execute"] },
      ],
    },
    "2026-08-23T15:00:00.000Z",
  );

  assert.equal(status.ok, true);
  assert.deepEqual(status.missingCommands, []);
  assert.equal(status.checkedAt, "2026-08-23T15:00:00.000Z");
});

test("runtime readiness reports every missing Gotion command", () => {
  const status = runtimeStatusFromGatewayPayload({ result: { commands: [] } });

  assert.equal(status.ok, false);
  assert.deepEqual(status.availableCommands, []);
  assert.deepEqual(status.missingCommands, [
    "gotion_status",
    "gotion_actor",
    "gotion_approve",
    "gotion_execute",
  ]);
});

test("gateway JSON parser tolerates non-secret CLI warning text", () => {
  const payload = parseGatewayJsonOutput('warning before JSON\n{"commands":[]}\n');
  assert.deepEqual(payload, { commands: [] });
});
