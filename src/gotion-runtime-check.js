export const GOTION_AGENT_ID = "gotion-coordinator";
export const GOTION_RUNTIME_COMMANDS = [
  "gotion_status",
  "gotion_actor",
  "gotion_approve",
  "gotion_execute",
];

export function parseGatewayJsonOutput(output) {
  const raw = String(output || "").trim();
  try {
    return JSON.parse(raw);
  } catch {
    const start = raw.indexOf("{");
    const end = raw.lastIndexOf("}");
    if (start < 0 || end <= start) throw new Error("commands.list returned invalid JSON");
    return JSON.parse(raw.slice(start, end + 1));
  }
}

export function commandNamesFromGatewayPayload(payload) {
  const commands = Array.isArray(payload?.commands)
    ? payload.commands
    : Array.isArray(payload?.result?.commands)
      ? payload.result.commands
      : [];
  const names = new Set();
  for (const command of commands) {
    if (typeof command?.name === "string") names.add(command.name.replace(/^\//, ""));
    if (typeof command?.nativeName === "string") names.add(command.nativeName.replace(/^\//, ""));
    for (const alias of Array.isArray(command?.textAliases) ? command.textAliases : []) {
      if (typeof alias === "string") names.add(alias.replace(/^\//, ""));
    }
  }
  return names;
}

export function runtimeStatusFromGatewayPayload(payload, checkedAt = new Date().toISOString()) {
  const names = commandNamesFromGatewayPayload(payload);
  const availableCommands = GOTION_RUNTIME_COMMANDS.filter((name) => names.has(name));
  const missingCommands = GOTION_RUNTIME_COMMANDS.filter((name) => !names.has(name));
  return {
    checked: true,
    ok: missingCommands.length === 0,
    checkedAt,
    availableCommands,
    missingCommands,
    error: null,
  };
}
