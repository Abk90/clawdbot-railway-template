import assert from "node:assert/strict";
import test from "node:test";

import { ensureGotionCronJobs } from "../src/configure-gotion-cron.js";


test("creates only missing deterministic Gotion cron jobs", async () => {
  const calls = [];
  const run = async (args) => {
    calls.push(args);
    if (args[0] === "cron" && args[1] === "list") {
      return { stdout: JSON.stringify({ jobs: [{ name: "Gotion operations — point matin v1" }] }), stderr: "" };
    }
    return { stdout: "ok", stderr: "" };
  };
  const result = await ensureGotionCronJobs(run);
  assert.equal(result.preserved.length, 1);
  assert.equal(result.created.length, 2);
  assert.equal(calls.filter((args) => args.includes("--command-argv")).length, 2);
  assert.equal(calls.every((args) => !args.includes("--message")), true);
});
