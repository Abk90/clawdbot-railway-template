import { execFile } from "node:child_process";
import { promisify } from "node:util";


const execFileAsync = promisify(execFile);
const OPENCLAW = process.env.OPENCLAW_BIN || "openclaw";
const GROUP_ID = process.env.OPENCLAW_GOTION_GROUP_ID || "-5488938863";
const STATE_DB = process.env.GOTION_OPERATIONS_DB || "/data/workspace/gotion-coordinator/operations.sqlite3";
const SCRIPT = "/app/src/gotion-operations.py";
const TIMEZONE = "Africa/Casablanca";

const JOBS = [
  {
    name: "Gotion operations — point matin v1",
    cron: "30 7 * * 1-6",
    argv: ["python3", SCRIPT, "summary"],
  },
  {
    name: "Gotion operations — demande rapport v1",
    cron: "30 16 * * 1-6",
    argv: ["python3", SCRIPT, "reminder", "ask"],
  },
  {
    name: "Gotion operations — relance rapport v1",
    cron: "0 18 * * 1-6",
    argv: ["python3", SCRIPT, "reminder", "escalate"],
  },
];

function parseJobs(raw) {
  const parsed = JSON.parse(raw);
  if (Array.isArray(parsed)) return parsed;
  if (Array.isArray(parsed.jobs)) return parsed.jobs;
  if (Array.isArray(parsed.result?.jobs)) return parsed.result.jobs;
  return [];
}

async function openclaw(args) {
  const { stdout, stderr } = await execFileAsync(OPENCLAW, args, {
    env: process.env,
    maxBuffer: 2 * 1024 * 1024,
    timeout: 120_000,
  });
  return { stdout, stderr };
}

export async function ensureGotionCronJobs(run = openclaw) {
  const listed = await run(["cron", "list", "--json"]);
  const existingNames = new Set(parseJobs(listed.stdout).map((job) => String(job.name || "")));
  const created = [];
  const preserved = [];
  for (const job of JOBS) {
    if (existingNames.has(job.name)) {
      preserved.push(job.name);
      continue;
    }
    await run([
      "cron",
      "create",
      job.cron,
      "--name",
      job.name,
      "--tz",
      TIMEZONE,
      "--command-argv",
      JSON.stringify(job.argv),
      "--command-env",
      `GOTION_OPERATIONS_DB=${STATE_DB}`,
      "--announce",
      "--channel",
      "telegram",
      "--to",
      GROUP_ID,
    ]);
    created.push(job.name);
  }
  return { created, preserved };
}

const isCli = process.argv[1] && new URL(import.meta.url).pathname === process.argv[1];
if (isCli) {
  ensureGotionCronJobs()
    .then((result) => {
      console.log(`[boot] Gotion cron: ${result.created.length} created, ${result.preserved.length} already present.`);
    })
    .catch((error) => {
      console.error(`[boot] Gotion cron configuration failed: ${String(error.message || error)}`);
      process.exitCode = 1;
    });
}
