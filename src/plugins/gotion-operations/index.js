import { spawn } from "node:child_process";

import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";


const PLUGIN_ID = "gotion-operations";
const DEFAULT_OWNER = "7532850730";
const DEFAULT_GROUP = "-5488938863";

const stringSchema = (description, options = {}) => ({
  type: "string",
  description,
  ...options,
});

function jsonResult(value) {
  return {
    content: [{ type: "text", text: JSON.stringify(value, null, 2) }],
    details: value,
  };
}

function textResult(text) {
  return { content: [{ type: "text", text }] };
}

function normalizedConfig(api) {
  const raw = api.pluginConfig && typeof api.pluginConfig === "object" ? api.pluginConfig : {};
  return {
    pythonPath: String(raw.pythonPath || "/usr/bin/python3"),
    scriptPath: String(raw.scriptPath || "/app/src/gotion-operations.py"),
    stateDb: String(raw.stateDb || "/data/workspace/gotion-coordinator/operations.sqlite3"),
    ownerSenderId: String(raw.ownerSenderId || DEFAULT_OWNER),
    groupId: String(raw.groupId || DEFAULT_GROUP),
  };
}

function senderFromToolContext(context) {
  return String(context.requesterSenderId || "").trim();
}

async function runOperation(api, payload) {
  const cfg = normalizedConfig(api);
  const stdout = await new Promise((resolve, reject) => {
    const child = spawn(cfg.pythonPath, [cfg.scriptPath, "tool"], {
      env: {
        ...process.env,
        GOTION_OPERATIONS_DB: cfg.stateDb,
        GOTION_OWNER_SENDER_ID: cfg.ownerSenderId,
      },
      stdio: ["pipe", "pipe", "pipe"],
    });
    let out = "";
    let err = "";
    const maxBytes = 2 * 1024 * 1024;
    const timeout = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error("délai du workflow Gotion dépassé"));
    }, 120_000);
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      out += chunk;
      if (Buffer.byteLength(out) > maxBytes) child.kill("SIGKILL");
    });
    child.stderr.on("data", (chunk) => {
      err += chunk;
      if (Buffer.byteLength(err) > maxBytes) child.kill("SIGKILL");
    });
    child.on("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timeout);
      if (code !== 0 && !out.trim()) {
        reject(new Error(err.trim() || `workflow Gotion terminé avec le code ${code}`));
        return;
      }
      resolve(out);
    });
    child.stdin.end(JSON.stringify(payload));
  });
  let parsed;
  try {
    parsed = JSON.parse(stdout.trim());
  } catch {
    throw new Error("réponse invalide du workflow Gotion");
  }
  if (!parsed.ok) throw new Error(parsed.error || "workflow Gotion refusé");
  return parsed.result;
}

function ownerCommandAllowed(ctx, ownerSenderId) {
  return (
    ctx.channel === "telegram" &&
    ctx.isAuthorizedSender === true &&
    String(ctx.senderId || "").trim() === ownerSenderId
  );
}

function normalizeProposalId(raw) {
  const value = String(raw || "").trim().toUpperCase();
  return /^GOA-\d{8}-[A-F0-9]{6}$/.test(value) ? value : "";
}

function parseBooleanToken(token, expected) {
  return String(token || "").toLowerCase() === expected;
}

async function updateGotionSenderAccess(api, groupId, telegramId, active) {
  if (!api.runtime.config?.mutateConfigFile) return;
  await api.runtime.config.mutateConfigFile({
    afterWrite: { mode: "auto" },
    mutate: (draft) => {
      const telegram = draft.channels?.telegram;
      const group = telegram?.groups?.[groupId];
      if (!group) throw new Error("groupe Gotion absent de la configuration");
      const existing = Array.isArray(group.allowFrom) ? group.allowFrom.map(String) : [];
      group.allowFrom = active
        ? [...new Set([...existing, telegramId])]
        : existing.filter((value) => value !== telegramId);
    },
  });
}

export default definePluginEntry({
  id: PLUGIN_ID,
  name: "Gotion Operations Guard",
  description: "Dossiers chantier et exécution Odoo à double validation.",
  register(api) {
    api.registerTool((context) => ({
      name: "gotion_case_record",
      label: "Enregistrer un dossier Gotion",
      description:
        "Créer ou compléter un dossier terrain Gotion à partir de faits explicitement transmis. Utiliser pour achat, réception, consommation/pose, nouvel ouvrier, rapport journalier ou incident. Ne jamais inclure de CIN, téléphone, adresse, salaire brut, secret ou donnée bancaire.",
      parameters: {
        type: "object",
        additionalProperties: false,
        required: ["case_type", "summary", "facts_json"],
        properties: {
          case_id: stringSchema("Identifiant GOT-... à compléter ; omettre pour un nouveau dossier."),
          case_type: {
            type: "string",
            enum: ["purchase", "reception", "consumption", "worker", "daily_report", "incident"],
          },
          actor_id: stringSchema("Identifiant Telegram exact de l'acteur concerné ; omettre pour l'expéditeur."),
          work_date: stringSchema("Date métier YYYY-MM-DD."),
          zone: stringSchema("Zone chantier exacte si connue."),
          external_ref: stringSchema("Référence ticket, bon, tâche ou message si connue."),
          summary: stringSchema("Résumé factuel court, sans inférence."),
          facts_json: stringSchema("Objet JSON des faits explicitement reçus."),
          evidence_json: stringSchema("Liste JSON de références de preuves visibles ; [] si aucune."),
        },
      },
      async execute(_toolCallId, params) {
        const result = await runOperation(api, {
          operation: "case_record",
          requester_sender_id: senderFromToolContext(context),
          case_id: params.case_id,
          case_type: params.case_type,
          actor_id: params.actor_id,
          work_date: params.work_date,
          zone: params.zone,
          external_ref: params.external_ref,
          summary: params.summary,
          facts: params.facts_json,
          evidence: params.evidence_json || "[]",
        });
        return jsonResult(result);
      },
    }));

    api.registerTool((context) => ({
      name: "gotion_case_get",
      label: "Lire un dossier Gotion",
      description: "Lire le dossier, les champs manquants et les trois prochaines questions déterministes.",
      parameters: {
        type: "object",
        additionalProperties: false,
        required: ["case_id"],
        properties: { case_id: stringSchema("Identifiant GOT-...") },
      },
      async execute(_toolCallId, params) {
        return jsonResult(
          await runOperation(api, {
            operation: "case_get",
            requester_sender_id: senderFromToolContext(context),
            case_id: params.case_id,
          }),
        );
      },
    }));

    api.registerTool((context) => ({
      name: "gotion_case_list",
      label: "Lister les dossiers Gotion",
      description: "Lister les dossiers ouverts ou prêts pour revue. Un acteur terrain ne voit que ses propres dossiers.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          status: stringSchema("Filtre optionnel : collecting, ready_for_review."),
          case_type: stringSchema("Filtre optionnel par type."),
          limit: { type: "integer", minimum: 1, maximum: 30 },
        },
      },
      async execute(_toolCallId, params) {
        return jsonResult(
          await runOperation(api, {
            operation: "case_list",
            requester_sender_id: senderFromToolContext(context),
            status: params.status,
            case_type: params.case_type,
            limit: params.limit,
          }),
        );
      },
    }));

    api.registerTool((context) => ({
      name: "gotion_odoo_lookup",
      label: "Recherche Odoo Gotion",
      description:
        "Recherche Odoo strictement en lecture seule pour résoudre un produit, fournisseur, emplacement, tâche, employé, achat ou transfert exact. Ne jamais choisir un homonyme si plusieurs résultats restent possibles.",
      parameters: {
        type: "object",
        additionalProperties: false,
        required: ["kind", "query"],
        properties: {
          kind: {
            type: "string",
            enum: ["product", "supplier", "location", "task", "employee", "purchase", "picking"],
          },
          query: stringSchema("Référence, identifiant ou fragment exact à rechercher.", { minLength: 2 }),
          limit: { type: "integer", minimum: 1, maximum: 10 },
        },
      },
      async execute(_toolCallId, params) {
        return jsonResult(
          await runOperation(api, {
            operation: "odoo_lookup",
            requester_sender_id: senderFromToolContext(context),
            kind: params.kind,
            query: params.query,
            limit: params.limit,
          }),
        );
      },
    }));

    api.registerTool((context) => ({
      name: "gotion_action_prepare",
      label: "Préparer une action Odoo Gotion",
      description:
        "Préparer sans exécuter une note, tâche, admission ouvrier, demande de prix achat ou transfert interne en brouillon. Le dossier doit être complet. Retourne les commandes propriétaire séparées d'approbation et d'exécution.",
      parameters: {
        type: "object",
        additionalProperties: false,
        required: ["case_id", "action_type", "payload_json"],
        properties: {
          case_id: stringSchema("Identifiant GOT-... complet."),
          action_type: {
            type: "string",
            enum: [
              "chatter_note",
              "project_task_create",
              "worker_intake_task",
              "purchase_order_draft",
              "stock_picking_draft",
            ],
          },
          payload_json: stringSchema("Objet JSON exact de l'action, avec tous les identifiants Odoo résolus."),
        },
      },
      async execute(_toolCallId, params) {
        return jsonResult(
          await runOperation(api, {
            operation: "action_prepare",
            requester_sender_id: senderFromToolContext(context),
            case_id: params.case_id,
            action_type: params.action_type,
            payload: params.payload_json,
          }),
        );
      },
    }));

    api.registerCommand({
      name: "gotion_status",
      description: "État des dossiers, propositions et acteurs Gotion.",
      acceptsArgs: false,
      channels: ["telegram"],
      handler: async (ctx) => {
        try {
          const dashboard = await runOperation(api, {
            operation: "dashboard",
            requester_sender_id: String(ctx.senderId || ""),
          });
          const actorLines = (dashboard.actors || []).map((actor) => {
            const report = actor.daily_report_required ? "rapport quotidien" : "sans rapport obligatoire";
            return `• ${actor.name} — ${actor.role} — ${actor.language} — ${report}`;
          });
          const caseLines = Object.entries(dashboard.cases || {}).map(
            ([status, count]) => `• ${status} : ${count}`,
          );
          const proposalLines = Object.entries(dashboard.proposals || {}).map(
            ([status, count]) => `• ${status} : ${count}`,
          );
          return {
            text: [
              "📋 État Gotion",
              "",
              "Acteurs autorisés :",
              ...(actorLines.length ? actorLines : ["• aucun"]),
              "",
              "Dossiers :",
              ...(caseLines.length ? caseLines : ["• aucun dossier ouvert"]),
              "",
              "Propositions Odoo :",
              ...(proposalLines.length ? proposalLines : ["• aucune proposition"]),
            ].join("\n"),
          };
        } catch (error) {
          return { text: `⚠️ ${String(error.message || error)}` };
        }
      },
    });

    api.registerCommand({
      name: "gotion_actor",
      description: "Ajouter/retirer un acteur Telegram Gotion vérifié (Ahmed uniquement).",
      acceptsArgs: true,
      channels: ["telegram"],
      handler: async (ctx) => {
        const cfg = normalizedConfig(api);
        if (!ownerCommandAllowed(ctx, cfg.ownerSenderId)) {
          return { text: "⚠️ Commande réservée à Ahmed sur son compte Telegram vérifié." };
        }
        const tokens = String(ctx.args || "").trim().split(/\s+/).filter(Boolean);
        const action = String(tokens.shift() || "").toLowerCase();
        const telegramId = String(tokens.shift() || "");
        if (!/^[0-9]{5,}$/.test(telegramId)) {
          return {
            text:
              "Usage : /gotion_actor add <telegram_id> <role> <fr|darija|ar> <daily|nodaily> <voice|text> <nom complet>\n" +
              "ou /gotion_actor remove <telegram_id>",
          };
        }
        try {
          if (action === "remove") {
            const existing = await runOperation(api, {
              operation: "actor_upsert",
              requester_sender_id: String(ctx.senderId || ""),
              telegram_id: telegramId,
              name: `Acteur ${telegramId}`,
              role: "field_worker",
              language: "fr",
              active: false,
            });
            await updateGotionSenderAccess(api, cfg.groupId, telegramId, false);
            return { text: `✅ Accès Gotion retiré pour ${existing.telegram_id}.` };
          }
          if (action !== "add" || tokens.length < 5) {
            return { text: "Syntaxe incomplète. Utilise /gotion_actor add <id> <role> <langue> <daily|nodaily> <voice|text> <nom>." };
          }
          const role = String(tokens.shift() || "").toLowerCase();
          const language = String(tokens.shift() || "").toLowerCase();
          const dailyToken = String(tokens.shift() || "").toLowerCase();
          const voiceToken = String(tokens.shift() || "").toLowerCase();
          const name = tokens.join(" ").trim();
          const result = await runOperation(api, {
            operation: "actor_upsert",
            requester_sender_id: String(ctx.senderId || ""),
            telegram_id: telegramId,
            name,
            role,
            language,
            daily_report_required: parseBooleanToken(dailyToken, "daily"),
            voice_preferred: parseBooleanToken(voiceToken, "voice"),
            active: true,
          });
          await updateGotionSenderAccess(api, cfg.groupId, telegramId, true);
          return {
            text: `✅ Acteur vérifié enregistré : ${result.name} (${result.telegram_id}), rôle ${result.role}, langue ${result.language}, rapport quotidien ${result.daily_report_required ? "oui" : "non"}.`,
          };
        } catch (error) {
          return { text: `⚠️ Aucun accès modifié : ${String(error.message || error)}` };
        }
      },
    });

    api.registerCommand({
      name: "gotion_approve",
      description: "Approuver une proposition Odoo Gotion pendant quatre heures (Ahmed uniquement).",
      acceptsArgs: true,
      channels: ["telegram"],
      handler: async (ctx) => {
        const cfg = normalizedConfig(api);
        if (!ownerCommandAllowed(ctx, cfg.ownerSenderId)) {
          return { text: "⚠️ Approbation refusée : compte propriétaire requis." };
        }
        const proposalId = normalizeProposalId(ctx.args);
        if (!proposalId) return { text: "Usage exact : /gotion_approve GOA-YYYYMMDD-XXXXXX" };
        try {
          const result = await runOperation(api, {
            operation: "approve",
            requester_sender_id: String(ctx.senderId || ""),
            proposal_id: proposalId,
          });
          return { text: `✅ ${proposalId} approuvée jusqu'à ${result.expires_at}.\n${result.summary}\nPour exécuter : ${result.next_command}` };
        } catch (error) {
          return { text: `⚠️ Aucune approbation enregistrée : ${String(error.message || error)}` };
        }
      },
    });

    api.registerCommand({
      name: "gotion_execute",
      description: "Exécuter puis relire une proposition Odoo Gotion approuvée (Ahmed uniquement).",
      acceptsArgs: true,
      channels: ["telegram"],
      handler: async (ctx) => {
        const cfg = normalizedConfig(api);
        if (!ownerCommandAllowed(ctx, cfg.ownerSenderId)) {
          return { text: "⚠️ Exécution refusée : compte propriétaire requis." };
        }
        const proposalId = normalizeProposalId(ctx.args);
        if (!proposalId) return { text: "Usage exact : /gotion_execute GOA-YYYYMMDD-XXXXXX" };
        try {
          const result = await runOperation(api, {
            operation: "execute",
            requester_sender_id: String(ctx.senderId || ""),
            proposal_id: proposalId,
          });
          return {
            text:
              `✅ ${proposalId} exécutée et relue dans Odoo.\n` +
              `${result.odoo_model} #${result.odoo_record_id}\n${result.odoo_url}\n${result.notice || ""}`,
          };
        } catch (error) {
          return { text: `⚠️ Aucune écriture finalisée : ${String(error.message || error)}` };
        }
      },
    });
  },
});
