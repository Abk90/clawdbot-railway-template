#!/usr/bin/env python3
"""Read-only, project-scoped Odoo control for the Gotion Telegram group."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import xmlrpc.client


PROJECT_ID = 265
STATE_FILE = Path(
    os.environ.get(
        "GOTION_STATUS_STATE_FILE",
        "/data/workspace/gotion-coordinator/.odoo-status-state.json",
    )
)
TRACKED = {
    4115: "Métré contradictoire Lots 2 & 3",
    4176: "Plantation gazon selon métrés et BC validés",
    4211: "Avenants plateaux/rouleaux",
    4107: "Pression et débit d'eau",
    4226: "Manomètres, débit et registres d'arrosage",
    4425: "Arrosage",
    4231: "Livraisons gazon et matériel",
    4374: "Transitaire et dossier douane",
    4375: "Stockage sécurisé AFZ",
}


def env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()
    return default


def read_tasks() -> list[dict]:
    url = env("ODOO_URL", default="https://pepiniere-belkora.odoo.com").rstrip("/")
    db = env("ODOO_DB", default="pepiniere-belkora")
    user = env("ODOO_USER", "ODOO_USERNAME", default="contact@pepinierebelkora.com")
    password = env("ODOO_PASSWORD", "ODOO_USER_PASSWORD", "ODOO_API_KEY")
    if not password:
        raise RuntimeError("identifiant Odoo de lecture indisponible")

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(db, user, password, {})
    if not uid:
        raise RuntimeError("authentification Odoo refusée")
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
    return models.execute_kw(
        db,
        uid,
        password,
        "project.task",
        "search_read",
        [[("project_id", "=", PROJECT_ID), ("active", "=", True), ("id", "in", list(TRACKED))]],
        {
            "fields": ["id", "name", "stage_id", "date_deadline", "write_date"],
            "limit": len(TRACKED),
            "order": "id asc",
        },
    )


def clean(value: object) -> str:
    return " ".join(str(value).split())


def build_report(tasks: list[dict]) -> str:
    by_id = {task["id"]: task for task in tasks}
    now = datetime.now(timezone.utc)
    lines = [
        "🔎 Contrôle Gotion — lecture seule Odoo #265",
        f"Passage : {now.astimezone().strftime('%d/%m/%Y %H:%M %Z')}",
        "",
        "Priorité immédiate : faire confirmer le positionnement des 5 000 m² de rouleaux, puis l'eau et les zones réellement libres avant tout GO.",
        "",
        "État des tâches de référence :",
    ]
    for task_id, label in TRACKED.items():
        task = by_id.get(task_id)
        if not task:
            lines.append(f"• #{task_id} {label} — introuvable ou inactive")
            continue
        stage = task.get("stage_id")
        stage_name = stage[1] if isinstance(stage, list) and len(stage) > 1 else "étape inconnue"
        deadline = task.get("date_deadline") or "sans échéance"
        updated = task.get("write_date") or "date inconnue"
        lines.append(
            f"• #{task_id} {clean(label)} — {clean(stage_name)} — échéance {clean(deadline)} — MAJ {clean(updated)}"
        )

    lines.extend(
        [
            "",
            "Écarts non couverts par une tâche dédiée dans l'audit du 04/08 :",
            "• position exacte et validation client de la démonstration 5 000 m² rouleaux ;",
            "• fin du terrassement des bancs, absence de canalisation restante et finalisation de la zone plateaux ;",
            "• arbitrage DN63/DN75 entre le point d'eau Est et la grande zone Sud ;",
            "• dommages de tranchées sur gazon déjà planté et remise en état ;",
            "• lot potentiel bande Est ~15 000 m² : eau, signature et statut de la production à risque.",
            "",
            "Ce contrôle ne modifie ni Odoo, ni paiement, ni commande, ni contrat, ni RH, ni stock, ni production. Toute validation opérationnelle reste humaine.",
        ]
    )
    return "\n".join(lines)


def deduplicate(report: str) -> str:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(report.split("Passage :", 1)[-1].split("\n", 1)[-1].encode()).hexdigest()
    previous = {}
    try:
        previous = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    STATE_FILE.write_text(
        json.dumps({"digest": digest, "checked_at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )
    if previous.get("digest") == digest:
        return (
            "🔎 Contrôle Gotion — aucun changement des tâches Odoo suivies depuis le dernier passage.\n"
            "Priorité inchangée : positionnement des 5 000 m² rouleaux, eau disponible et zones libres à confirmer humainement.\n"
            "Les écarts de dépendances signalés le 04/08 restent ouverts tant qu'une mise à jour Odoo vérifiée ne les couvre pas."
        )
    return report


def main() -> int:
    try:
        print(deduplicate(build_report(read_tasks())))
        return 0
    except Exception as exc:  # fail closed without leaking credentials
        print(
            "⚠️ Contrôle Gotion non exécuté : lecture Odoo indisponible. "
            "Aucune donnée n'a été modifiée. Vérification humaine requise."
        )
        print(f"Cause technique limitée : {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
