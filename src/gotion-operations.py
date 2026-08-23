#!/usr/bin/env python3
"""Deterministic Gotion field-operation store and guarded Odoo executor.

The language model may collect facts and prepare proposals through this program,
but Odoo writes are reachable only from owner-only native Telegram commands.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
from typing import Any
import xmlrpc.client


PROJECT_ID = 265
OWNER_SENDER_ID = os.environ.get("GOTION_OWNER_SENDER_ID", "7532850730").strip()
STATE_DB = Path(
    os.environ.get(
        "GOTION_OPERATIONS_DB",
        "/data/workspace/gotion-coordinator/operations.sqlite3",
    )
)
ALLOWED_CASE_TYPES = {
    "purchase",
    "reception",
    "consumption",
    "worker",
    "daily_report",
    "incident",
}
ALLOWED_ACTION_TYPES = {
    "chatter_note",
    "project_task_create",
    "worker_intake_task",
    "purchase_order_draft",
    "stock_picking_draft",
}
MANAGER_ROLES = {"owner", "project_manager", "co_manager", "finance", "hr", "stock_manager"}
SENSITIVE_KEY_FRAGMENTS = {
    "cin_number",
    "identification_id",
    "birthday",
    "birth_date",
    "bank",
    "rib",
    "password",
    "api_key",
    "token",
    "phone",
    "address",
    "wage",
    "salary",
    "salaire",
    "net_rate",
    "daily_rate",
}

REQUIRED_FIELDS = {
    "purchase": [
        "purchase_date",
        "purchaser",
        "supplier",
        "company",
        "lines",
        "total_amount",
        "payment_source",
        "receipt_location",
        "receipt_proof",
    ],
    "reception": [
        "receipt_date",
        "receiver",
        "supplier",
        "company",
        "purchase_reference",
        "lines",
        "destination_location",
        "receipt_proof",
    ],
    "consumption": [
        "consumption_date",
        "installer",
        "company",
        "source_location",
        "destination_location",
        "zone",
        "lines",
        "installation_proof",
    ],
    "worker": [
        "official_name",
        "cin_collected_private",
        "start_date",
        "site",
        "cnss_status",
        "rate_confirmed_private",
        "worker_status",
        "photo_collected_private",
    ],
    "daily_report": [
        "report_date",
        "reporter",
        "work_done",
        "zone",
        "proof",
        "blockers",
        "next_action",
    ],
    "incident": ["incident_date", "reporter", "zone", "description", "proof", "next_action"],
}

QUESTIONS = {
    "purchase_date": ("Quelle est la date exacte de l'achat ?", "شنو هو التاريخ بالضبط ديال الشرا؟"),
    "purchaser": ("Qui a payé ou effectué l'achat ?", "شكون شرا ولا خلّص؟"),
    "supplier": ("Quel est le nom exact du fournisseur sur le bon ?", "شنو هو السمية بالضبط ديال المورّد لي فالبون؟"),
    "company": ("Pour quelle société : Pépinière Belkora ou Miya Belkora Design ?", "لأي شركة: Pépinière Belkora ولا Miya Belkora Design؟"),
    "lines": ("Donne chaque article avec quantité, unité et prix ; joins une photo lisible du bon.", "عطيني كل سلعة مع الكمية والوحدة والثمن، وصيفط تصويرة واضحة ديال البون."),
    "total_amount": ("Quel est le total TTC exact du justificatif ?", "شحال هو المجموع TTC بالضبط فالبون؟"),
    "payment_source": ("Quelle caisse ou quel moyen de paiement a été utilisé ?", "منين تخلّصات: شنو هي الكاس ولا وسيلة الأداء؟"),
    "receipt_location": ("Où la marchandise a-t-elle été physiquement reçue ?", "فين تسلمات السلعة فعلياً؟"),
    "receipt_proof": ("Envoie la preuve de réception physique, distincte du ticket d'achat.", "صيفط دليل الاستلام الفعلي، ماشي غير تيكي ديال الشرا."),
    "receipt_date": ("Quelle est la date réelle de réception ?", "شنو هو نهار الاستلام الفعلي؟"),
    "receiver": ("Qui a compté et reçu la marchandise ?", "شكون عدّ وتسلم السلعة؟"),
    "purchase_reference": ("Quel est le bon de commande, ticket ou référence d'achat lié ?", "شنو هو رقم البون ولا تيكي ولا مرجع الشرا؟"),
    "destination_location": ("Dans quel emplacement Odoo exact faut-il entrer ou consommer le stock ?", "فأي لوكاسيون Odoo بالضبط خاص تدخل ولا تخرج السلعة؟"),
    "consumption_date": ("Quelle est la date réelle de pose ou d'utilisation ?", "شنو هو نهار التركيب ولا الاستعمال بالضبط؟"),
    "installer": ("Qui a posé ou utilisé le matériel ?", "شكون ركّب ولا استعمل هاد الماتريال؟"),
    "source_location": ("De quel emplacement de stock exact les articles sont-ils sortis ?", "من أي لوكاسيون ديال الستوك خرجات السلعة بالضبط؟"),
    "zone": ("Dans quelle zone exacte du chantier ?", "فاش من بلاصة بالضبط فالشانطي؟"),
    "installation_proof": ("Envoie les photos de pose et indique ce qui est visible sur chacune.", "صيفط تصاور ديال التركيب وشرح شنو باين فكل تصويرة."),
    "official_name": ("Quel est le nom officiel exactement comme sur la CIN ?", "شنو هو الاسم الرسمي كيف مكتوب فالـCIN؟"),
    "cin_collected_private": ("Confirme seulement si la CIN lisible a été reçue en privé ; ne la publie pas ici.", "أكد غير واش توصلنا بالـCIN واضحة فالخاص؛ ما تصيفطهاش هنا."),
    "start_date": ("Quelle est la date réelle d'entrée sur chantier ?", "شنو هو نهار الدخول الفعلي للشانطي؟"),
    "site": ("Quel chantier et quelle équipe ?", "فأي شانطي ومع أي فرقة؟"),
    "cnss_status": ("Déclaré CNSS : oui ou non, après confirmation d'Ahmed ?", "CNSS: مصرح به ولا لا، من بعد تأكيد أحمد؟"),
    "rate_confirmed_private": (
        "Confirme seulement si le taux validé par Ahmed a été reçu en privé ; ne donne aucun montant ici.",
        "أكد غير واش الثمن لي صادق عليه أحمد توصلتو به فالخاص؛ ما تكتب حتى مبلغ هنا.",
    ),
    "worker_status": ("Ouvrier ou chef d'équipe ?", "عامل ولا رئيس فرقة؟"),
    "photo_collected_private": ("La photo chantier pour le badge a-t-elle été reçue en privé ?", "واش توصلنا بتصويرة الشانطي ديال البادج فالخاص؟"),
    "report_date": ("Ce rapport concerne quelle date ?", "هاد التقرير ديال شنو هو النهار؟"),
    "reporter": ("Qui confirme ce rapport ?", "شكون كيأكد هاد التقرير؟"),
    "work_done": ("Qu'est-ce qui a été réellement terminé aujourd'hui ?", "شنو لي تسالى فعلياً اليوم؟"),
    "proof": ("Quelle photo, vidéo ou pièce prouve l'avancement ?", "شنو هي التصويرة ولا الفيديو ولا الوثيقة لي كتثبت الخدمة؟"),
    "blockers": ("Quels blocages restent ouverts ? Écris « aucun » s'il n'y en a pas.", "شنو هي المشاكل لي باقين؟ كتب «والو» إلا ما كاين حتى مشكل."),
    "next_action": ("Quelle est la prochaine action, par qui et pour quand ?", "شنو هي الخطوة الجاية، شكون غادي يديرها وفاش؟"),
    "incident_date": ("Quand l'incident s'est-il produit ?", "فاش وقع المشكل؟"),
    "description": ("Décris uniquement ce qui a été observé, sans supposition.", "شرح غير شنو تشاف بلا تخمين."),
}

BOOTSTRAP_ACTORS = [
    ("7532850730", "Ahmed Belkora", "owner", "fr", 0, 0),
    ("6183355408", "Mariyam El Malyani", "project_manager", "fr", 0, 0),
    ("7080572503", "Abderrahim Moumen", "co_manager", "fr", 0, 0),
    ("6214002681", "Youssef Bennis", "stock_manager", "fr", 0, 0),
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utcnow().isoformat(timespec="seconds")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def fail(message: str) -> None:
    raise ValueError(message)


def connect_db() -> sqlite3.Connection:
    STATE_DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(STATE_DB, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS actors (
          telegram_id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          role TEXT NOT NULL,
          language TEXT NOT NULL DEFAULT 'fr',
          voice_preferred INTEGER NOT NULL DEFAULT 0,
          daily_report_required INTEGER NOT NULL DEFAULT 0,
          active INTEGER NOT NULL DEFAULT 1,
          verified_by TEXT NOT NULL,
          verified_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cases (
          id TEXT PRIMARY KEY,
          dedupe_key TEXT NOT NULL UNIQUE,
          case_type TEXT NOT NULL,
          status TEXT NOT NULL,
          actor_id TEXT NOT NULL,
          work_date TEXT NOT NULL,
          zone TEXT NOT NULL DEFAULT '',
          external_ref TEXT NOT NULL DEFAULT '',
          summary TEXT NOT NULL DEFAULT '',
          facts_json TEXT NOT NULL,
          evidence_json TEXT NOT NULL,
          missing_json TEXT NOT NULL,
          created_by TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          last_question_at TEXT,
          reminder_count INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY(actor_id) REFERENCES actors(telegram_id)
        );
        CREATE TABLE IF NOT EXISTS case_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          case_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          actor_id TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY(case_id) REFERENCES cases(id)
        );
        CREATE TABLE IF NOT EXISTS proposals (
          id TEXT PRIMARY KEY,
          case_id TEXT NOT NULL,
          action_type TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          status TEXT NOT NULL,
          prepared_by TEXT NOT NULL,
          prepared_at TEXT NOT NULL,
          approved_by TEXT,
          approved_at TEXT,
          expires_at TEXT,
          executed_at TEXT,
          odoo_model TEXT,
          odoo_record_id INTEGER,
          readback_json TEXT,
          error TEXT,
          FOREIGN KEY(case_id) REFERENCES cases(id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS proposals_live_hash
          ON proposals(case_id, action_type, payload_hash)
          WHERE status IN ('pending_approval', 'approved', 'executed');
        """
    )
    now = iso_now()
    for actor in BOOTSTRAP_ACTORS:
        db.execute(
            """INSERT INTO actors
               (telegram_id,name,role,language,voice_preferred,daily_report_required,active,verified_by,verified_at,updated_at)
               VALUES (?,?,?,?,?,?,1,?,?,?)
               ON CONFLICT(telegram_id) DO NOTHING""",
            (*actor, OWNER_SENDER_ID, now, now),
        )
    db.commit()
    return db


def parse_json_object(value: Any, label: str) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            fail(f"{label} n'est pas un JSON valide: {exc.msg}")
    if not isinstance(value, dict):
        fail(f"{label} doit être un objet JSON")
    return value


def parse_json_list(value: Any, label: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            fail(f"{label} n'est pas un JSON valide: {exc.msg}")
    if not isinstance(value, list):
        fail(f"{label} doit être une liste JSON")
    return value


def assert_no_sensitive_keys(value: Any, prefix: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if any(fragment in normalized for fragment in SENSITIVE_KEY_FRAGMENTS):
                fail(f"donnée sensible interdite dans le journal de groupe: {prefix}{key}")
            assert_no_sensitive_keys(child, f"{prefix}{key}.")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_no_sensitive_keys(child, f"{prefix}{index}.")


def actor_row(db: sqlite3.Connection, sender_id: str, require_active: bool = True) -> sqlite3.Row:
    row = db.execute("SELECT * FROM actors WHERE telegram_id=?", (sender_id,)).fetchone()
    if not row or (require_active and not row["active"]):
        fail("acteur Telegram non vérifié ou inactif")
    return row


def require_owner(sender_id: str) -> None:
    if str(sender_id) != OWNER_SENDER_ID:
        fail("commande réservée au propriétaire Ahmed")


def require_manager(db: sqlite3.Connection, sender_id: str) -> sqlite3.Row:
    actor = actor_row(db, sender_id)
    if actor["role"] not in MANAGER_ROLES:
        fail("action réservée à un responsable vérifié")
    return actor


def merge_facts(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if value is not None and value != "":
            merged[str(key)] = value
    return merged


def valid_value(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def validate_lines(lines: Any, require_ids: bool = False, require_prices: bool = False) -> list[str]:
    problems: list[str] = []
    if not isinstance(lines, list) or not lines:
        return ["lines"]
    for index, line in enumerate(lines, start=1):
        if not isinstance(line, dict):
            problems.append(f"lines[{index}]")
            continue
        if require_ids and not positive_int(line.get("product_id")):
            problems.append(f"lines[{index}].product_id")
        if not valid_value(line.get("description")) and not positive_int(line.get("product_id")):
            problems.append(f"lines[{index}].description")
        try:
            if float(line.get("qty", 0)) <= 0:
                problems.append(f"lines[{index}].qty")
        except (TypeError, ValueError):
            problems.append(f"lines[{index}].qty")
        if not valid_value(line.get("uom")) and not positive_int(line.get("uom_id")):
            problems.append(f"lines[{index}].uom")
        if require_prices:
            try:
                if float(line.get("price_unit", -1)) < 0:
                    problems.append(f"lines[{index}].price_unit")
            except (TypeError, ValueError):
                problems.append(f"lines[{index}].price_unit")
    return problems


def missing_fields(case_type: str, facts: dict[str, Any]) -> list[str]:
    missing = [field for field in REQUIRED_FIELDS[case_type] if not valid_value(facts.get(field))]
    if valid_value(facts.get("lines")):
        missing.extend(validate_lines(facts["lines"]))
    return list(dict.fromkeys(missing))


def next_questions(missing: list[str], language: str) -> list[str]:
    lang_index = 1 if language in {"ar", "darija"} else 0
    result = []
    for field in missing[:3]:
        base = field.split("[", 1)[0]
        pair = QUESTIONS.get(base)
        result.append(pair[lang_index] if pair else f"Information manquante : {field}")
    return result


def make_id(prefix: str) -> str:
    return f"{prefix}-{utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"


def row_to_case(db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    actor = actor_row(db, row["actor_id"], require_active=False)
    missing = json.loads(row["missing_json"])
    return {
        "id": row["id"],
        "type": row["case_type"],
        "status": row["status"],
        "actor": {"telegram_id": actor["telegram_id"], "name": actor["name"], "language": actor["language"]},
        "work_date": row["work_date"],
        "zone": row["zone"],
        "external_ref": row["external_ref"],
        "summary": row["summary"],
        "facts": json.loads(row["facts_json"]),
        "evidence": json.loads(row["evidence_json"]),
        "missing": missing,
        "next_questions": next_questions(missing, actor["language"]),
        "updated_at": row["updated_at"],
        "reminder_count": row["reminder_count"],
    }


def case_record(db: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    sender_id = str(payload.get("requester_sender_id") or "").strip()
    sender = actor_row(db, sender_id)
    case_type = str(payload.get("case_type") or "").strip().lower()
    if case_type not in ALLOWED_CASE_TYPES:
        fail("type de dossier non autorisé")
    target_actor_id = str(payload.get("actor_id") or sender_id).strip()
    if target_actor_id != sender_id and sender["role"] not in MANAGER_ROLES:
        fail("un acteur terrain ne peut enregistrer que son propre rapport")
    actor = actor_row(db, target_actor_id)
    facts = parse_json_object(payload.get("facts") or {}, "facts")
    assert_no_sensitive_keys(facts)
    evidence = parse_json_list(payload.get("evidence") or [], "evidence")
    assert_no_sensitive_keys(evidence)
    work_date = str(payload.get("work_date") or date.today().isoformat()).strip()
    zone = str(payload.get("zone") or facts.get("zone") or "").strip()
    external_ref = str(payload.get("external_ref") or "").strip()
    summary = str(payload.get("summary") or "").strip()[:4000]
    case_id = str(payload.get("case_id") or "").strip()

    if case_id:
        existing = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        if not existing:
            fail("dossier introuvable")
        if existing["case_type"] != case_type:
            fail("le type d'un dossier existant ne peut pas changer")
    else:
        dedupe_key = f"{case_type}|{work_date}|{target_actor_id}|{zone.lower()}|{external_ref.lower()}"
        existing = db.execute("SELECT * FROM cases WHERE dedupe_key=?", (dedupe_key,)).fetchone()

    now = iso_now()
    if existing:
        current_facts = json.loads(existing["facts_json"])
        current_evidence = json.loads(existing["evidence_json"])
        merged_facts = merge_facts(current_facts, facts)
        merged_evidence = current_evidence[:]
        for item in evidence:
            if item not in merged_evidence:
                merged_evidence.append(item)
        missing = missing_fields(case_type, merged_facts)
        status = "collecting" if missing else "ready_for_review"
        db.execute(
            """UPDATE cases SET status=?, actor_id=?, work_date=?, zone=?, external_ref=?,
               summary=?, facts_json=?, evidence_json=?, missing_json=?, updated_at=? WHERE id=?""",
            (
                status,
                target_actor_id,
                work_date,
                zone,
                external_ref,
                summary or existing["summary"],
                canonical(merged_facts),
                canonical(merged_evidence),
                canonical(missing),
                now,
                existing["id"],
            ),
        )
        case_id = existing["id"]
        event_type = "updated"
    else:
        missing = missing_fields(case_type, facts)
        status = "collecting" if missing else "ready_for_review"
        case_id = make_id("GOT")
        dedupe_key = f"{case_type}|{work_date}|{target_actor_id}|{zone.lower()}|{external_ref.lower()}"
        db.execute(
            """INSERT INTO cases
               (id,dedupe_key,case_type,status,actor_id,work_date,zone,external_ref,summary,
                facts_json,evidence_json,missing_json,created_by,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                case_id,
                dedupe_key,
                case_type,
                status,
                target_actor_id,
                work_date,
                zone,
                external_ref,
                summary,
                canonical(facts),
                canonical(evidence),
                canonical(missing),
                sender_id,
                now,
                now,
            ),
        )
        event_type = "created"
    db.execute(
        "INSERT INTO case_events(case_id,event_type,actor_id,payload_json,created_at) VALUES (?,?,?,?,?)",
        (case_id, event_type, sender_id, canonical({"facts": facts, "evidence": evidence}), now),
    )
    db.commit()
    row = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    result = row_to_case(db, row)
    result["recorded"] = True
    result["voice_preferred"] = bool(actor["voice_preferred"])
    return result


def case_get(db: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    sender_id = str(payload.get("requester_sender_id") or "").strip()
    requester = actor_row(db, sender_id)
    row = db.execute("SELECT * FROM cases WHERE id=?", (str(payload.get("case_id") or ""),)).fetchone()
    if not row:
        fail("dossier introuvable")
    if requester["role"] not in MANAGER_ROLES and row["actor_id"] != sender_id:
        fail("un acteur terrain ne peut lire que ses propres dossiers")
    return row_to_case(db, row)


def case_list(db: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    sender_id = str(payload.get("requester_sender_id") or "").strip()
    actor = actor_row(db, sender_id)
    where = ["1=1"]
    args: list[Any] = []
    status = str(payload.get("status") or "").strip()
    case_type = str(payload.get("case_type") or "").strip()
    if status:
        where.append("status=?")
        args.append(status)
    if case_type:
        where.append("case_type=?")
        args.append(case_type)
    if actor["role"] not in MANAGER_ROLES:
        where.append("actor_id=?")
        args.append(sender_id)
    limit = min(max(int(payload.get("limit") or 10), 1), 30)
    rows = db.execute(
        f"SELECT * FROM cases WHERE {' AND '.join(where)} ORDER BY updated_at DESC LIMIT ?",
        (*args, limit),
    ).fetchall()
    return {"count": len(rows), "cases": [row_to_case(db, row) for row in rows]}


def env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()
    return default


class Odoo:
    def __init__(self) -> None:
        self.url = env("ODOO_URL", default="https://pepiniere-belkora.odoo.com").rstrip("/")
        self.db = env("ODOO_DB", default="pepiniere-belkora")
        self.user = env("ODOO_USER", "ODOO_USERNAME", default="contact@pepinierebelkora.com")
        self.password = env("ODOO_PASSWORD", "ODOO_USER_PASSWORD", "ODOO_API_KEY")
        if not self.password:
            fail("identifiant Odoo indisponible")
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common", allow_none=True)
        self.uid = common.authenticate(self.db, self.user, self.password, {})
        if not self.uid:
            fail("authentification Odoo refusée")
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)

    def call(self, model: str, method: str, args: list[Any], kwargs: dict[str, Any] | None = None) -> Any:
        return self.models.execute_kw(
            self.db,
            self.uid,
            self.password,
            model,
            method,
            args,
            kwargs or {},
        )

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict[str, Any]]:
        return self.call(model, "read", [ids], {"fields": fields})

    def search_read(
        self,
        model: str,
        domain: list[Any],
        fields: list[str],
        limit: int = 10,
        order: str = "id desc",
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {"fields": fields, "limit": limit, "order": order}
        if context:
            kwargs["context"] = context
        return self.call(model, "search_read", [domain], kwargs)


LOOKUPS = {
    "product": ("product.product", ["id", "display_name", "default_code", "barcode", "active", "company_id"], "name"),
    "supplier": ("res.partner", ["id", "display_name", "supplier_rank", "company_id", "active"], "name"),
    "location": ("stock.location", ["id", "complete_name", "usage", "company_id", "active"], "complete_name"),
    "task": ("project.task", ["id", "name", "project_id", "stage_id", "user_ids", "active"], "name"),
    "employee": ("hr.employee", ["id", "name", "registration_number", "company_id", "active"], "name"),
    "purchase": ("purchase.order", ["id", "name", "state", "partner_id", "company_id", "origin", "amount_total"], "name"),
    "picking": ("stock.picking", ["id", "name", "state", "company_id", "location_id", "location_dest_id", "origin"], "name"),
}


def odoo_lookup(db: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    sender_id = str(payload.get("requester_sender_id") or "").strip()
    actor = actor_row(db, sender_id)
    kind = str(payload.get("kind") or "").strip().lower()
    if kind not in LOOKUPS:
        fail("recherche Odoo non autorisée")
    if kind == "employee" and actor["role"] not in MANAGER_ROLES:
        fail("recherche RH réservée aux responsables")
    query = str(payload.get("query") or "").strip()
    if len(query) < 2:
        fail("recherche trop courte")
    model, fields, search_field = LOOKUPS[kind]
    if query.isdigit():
        domain: list[Any] = ["|", ["id", "=", int(query)], [search_field, "ilike", query]]
    else:
        domain = [[search_field, "ilike", query]]
    if kind == "supplier":
        domain.append(["supplier_rank", ">", 0])
    if kind == "task":
        domain.append(["project_id", "=", PROJECT_ID])
    odoo = Odoo()
    records = odoo.search_read(
        model,
        domain,
        fields,
        limit=min(max(int(payload.get("limit") or 10), 1), 10),
        context={"active_test": False} if kind == "employee" else None,
    )
    return {"kind": kind, "model": model, "query": query, "count": len(records), "records": records, "read_only": True}


def positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def required_int(payload: dict[str, Any], key: str, allowed: set[int] | None = None) -> int:
    value = positive_int(payload.get(key))
    if not value or (allowed is not None and value not in allowed):
        fail(f"{key} invalide")
    return value


def validate_action_payload(action_type: str, payload: dict[str, Any], case_id: str) -> dict[str, Any]:
    assert_no_sensitive_keys(payload)
    if action_type == "chatter_note":
        model = str(payload.get("model") or "")
        if model != "project.task":
            fail("seules les notes de tâche Gotion sont autorisées")
        record_id = required_int(payload, "record_id")
        body = str(payload.get("body") or "").strip()
        if not body or case_id not in body:
            fail("la note doit citer le dossier Gotion")
        return {"model": model, "record_id": record_id, "body": body[:12000]}

    if action_type in {"project_task_create", "worker_intake_task"}:
        project_id = required_int(payload, "project_id")
        if project_id != PROJECT_ID:
            fail("la tâche doit rester dans le projet Gotion #265")
        name = str(payload.get("name") or "").strip()
        description = str(payload.get("description") or "").strip()
        if len(name) < 8 or not description or case_id not in description:
            fail("nom, description et référence dossier sont obligatoires")
        required_sections = [
            "Objectif",
            "Entrées",
            "Actions",
            "Responsable",
            "Dépendances",
            "Livrable",
            "Definition of Done",
            "Clarification",
        ]
        absent_sections = [section for section in required_sections if section.lower() not in description.lower()]
        if absent_sections:
            fail("description de tâche incomplète: " + ", ".join(absent_sections))
        user_ids = parse_json_list(payload.get("user_ids") or [], "user_ids")
        if not user_ids or any(not positive_int(value) for value in user_ids):
            fail("au moins un utilisateur Odoo exact est obligatoire")
        deadline = str(payload.get("date_deadline") or "").strip()
        if not deadline:
            fail("échéance obligatoire")
        return {
            "project_id": PROJECT_ID,
            "name": name[:250],
            "description": description[:20000],
            "user_ids": [int(value) for value in user_ids],
            "date_deadline": deadline,
            "action_label": action_type,
        }

    if action_type == "purchase_order_draft":
        company_id = required_int(payload, "company_id", {1, 2})
        partner_id = required_int(payload, "partner_id")
        picking_type_id = required_int(payload, "picking_type_id")
        origin = str(payload.get("origin") or "").strip()
        if not origin or case_id not in origin:
            fail("l'origine doit citer le dossier Gotion")
        lines = parse_json_list(payload.get("lines"), "lines")
        problems = validate_lines(lines, require_ids=True, require_prices=True)
        if problems:
            fail("lignes d'achat incomplètes: " + ", ".join(problems[:8]))
        normalized_lines = []
        for line in lines:
            normalized_lines.append(
                {
                    "product_id": int(line["product_id"]),
                    "description": str(line.get("description") or "").strip(),
                    "qty": float(line["qty"]),
                    "uom_id": required_int(line, "uom_id"),
                    "price_unit": float(line["price_unit"]),
                    "tax_ids": [int(value) for value in parse_json_list(line.get("tax_ids") or [], "tax_ids")],
                    "date_planned": str(line.get("date_planned") or "").strip(),
                    "analytic_distribution": parse_json_object(line.get("analytic_distribution") or {}, "analytic_distribution"),
                }
            )
        return {
            "company_id": company_id,
            "partner_id": partner_id,
            "picking_type_id": picking_type_id,
            "origin": origin[:500],
            "partner_ref": str(payload.get("partner_ref") or "").strip()[:250],
            "lines": normalized_lines,
        }

    if action_type == "stock_picking_draft":
        company_id = required_int(payload, "company_id", {1, 2})
        picking_type_id = required_int(payload, "picking_type_id")
        location_id = required_int(payload, "location_id")
        location_dest_id = required_int(payload, "location_dest_id")
        if location_id == location_dest_id:
            fail("source et destination doivent être distinctes")
        origin = str(payload.get("origin") or "").strip()
        if not origin or case_id not in origin:
            fail("l'origine doit citer le dossier Gotion")
        lines = parse_json_list(payload.get("lines"), "lines")
        problems = validate_lines(lines, require_ids=True)
        if problems:
            fail("lignes de mouvement incomplètes: " + ", ".join(problems[:8]))
        normalized_lines = []
        for line in lines:
            normalized_lines.append(
                {
                    "product_id": int(line["product_id"]),
                    "description": str(line.get("description") or "").strip(),
                    "qty": float(line["qty"]),
                    "uom_id": required_int(line, "uom_id"),
                    "lot_id": positive_int(line.get("lot_id")),
                }
            )
        return {
            "company_id": company_id,
            "picking_type_id": picking_type_id,
            "location_id": location_id,
            "location_dest_id": location_dest_id,
            "origin": origin[:500],
            "scheduled_date": str(payload.get("scheduled_date") or "").strip(),
            "lines": normalized_lines,
        }
    fail("type d'action non pris en charge")


def proposal_summary(action_type: str, payload: dict[str, Any]) -> str:
    if action_type == "chatter_note":
        return f"Note interne sur project.task #{payload['record_id']}"
    if action_type in {"project_task_create", "worker_intake_task"}:
        return f"Créer une tâche Odoo #265 « {payload['name']} » pour user_ids={payload['user_ids']}"
    if action_type == "purchase_order_draft":
        total = sum(line["qty"] * line["price_unit"] for line in payload["lines"])
        return f"Créer un brouillon d'achat société {payload['company_id']}, fournisseur #{payload['partner_id']}, {len(payload['lines'])} lignes, total HT calculé {total:.2f}"
    if action_type == "stock_picking_draft":
        return f"Créer un transfert brouillon {payload['location_id']} → {payload['location_dest_id']}, {len(payload['lines'])} lignes"
    return action_type


def action_prepare(db: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    sender_id = str(payload.get("requester_sender_id") or "").strip()
    require_manager(db, sender_id)
    case_id = str(payload.get("case_id") or "").strip()
    case = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    if not case:
        fail("dossier introuvable")
    if case["status"] != "ready_for_review":
        fail("dossier incomplet: " + ", ".join(json.loads(case["missing_json"])))
    action_type = str(payload.get("action_type") or "").strip()
    if action_type not in ALLOWED_ACTION_TYPES:
        fail("type d'action Odoo non autorisé")
    action_payload = validate_action_payload(
        action_type,
        parse_json_object(payload.get("payload"), "payload"),
        case_id,
    )
    payload_hash = hashlib.sha256(canonical(action_payload).encode()).hexdigest()
    existing = db.execute(
        """SELECT * FROM proposals WHERE case_id=? AND action_type=? AND payload_hash=?
           AND status IN ('pending_approval','approved','executed')""",
        (case_id, action_type, payload_hash),
    ).fetchone()
    if existing:
        proposal_id = existing["id"]
        status = existing["status"]
    else:
        proposal_id = make_id("GOA")
        now = iso_now()
        db.execute(
            """INSERT INTO proposals
               (id,case_id,action_type,payload_json,payload_hash,status,prepared_by,prepared_at)
               VALUES (?,?,?,?,?,'pending_approval',?,?)""",
            (proposal_id, case_id, action_type, canonical(action_payload), payload_hash, sender_id, now),
        )
        db.execute(
            "INSERT INTO case_events(case_id,event_type,actor_id,payload_json,created_at) VALUES (?,?,?,?,?)",
            (case_id, "proposal_prepared", sender_id, canonical({"proposal_id": proposal_id, "action_type": action_type}), now),
        )
        db.commit()
        status = "pending_approval"
    return {
        "proposal_id": proposal_id,
        "case_id": case_id,
        "action_type": action_type,
        "status": status,
        "summary": proposal_summary(action_type, action_payload),
        "payload_hash_short": payload_hash[:12],
        "approval_command": f"/gotion_approve {proposal_id}",
        "execution_command": f"/gotion_execute {proposal_id}",
        "notice": "Aucune écriture Odoo n'a encore été effectuée.",
    }


def actor_upsert(db: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    sender_id = str(payload.get("requester_sender_id") or "").strip()
    require_owner(sender_id)
    telegram_id = str(payload.get("telegram_id") or "").strip()
    if not telegram_id.isdigit() or len(telegram_id) < 5:
        fail("identifiant Telegram numérique invalide")
    name = str(payload.get("name") or "").strip()
    role = str(payload.get("role") or "").strip().lower()
    language = str(payload.get("language") or "fr").strip().lower()
    if len(name) < 3 or role not in MANAGER_ROLES | {"chef_chantier", "field_worker"}:
        fail("nom ou rôle invalide")
    if language not in {"fr", "ar", "darija"}:
        fail("langue invalide")
    active = 1 if bool(payload.get("active", True)) else 0
    voice = 1 if bool(payload.get("voice_preferred")) else 0
    daily = 1 if bool(payload.get("daily_report_required")) else 0
    now = iso_now()
    db.execute(
        """INSERT INTO actors
           (telegram_id,name,role,language,voice_preferred,daily_report_required,active,verified_by,verified_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(telegram_id) DO UPDATE SET name=excluded.name, role=excluded.role,
             language=excluded.language, voice_preferred=excluded.voice_preferred,
             daily_report_required=excluded.daily_report_required, active=excluded.active,
             verified_by=excluded.verified_by, updated_at=excluded.updated_at""",
        (telegram_id, name, role, language, voice, daily, active, sender_id, now, now),
    )
    db.commit()
    return {
        "telegram_id": telegram_id,
        "name": name,
        "role": role,
        "language": language,
        "voice_preferred": bool(voice),
        "daily_report_required": bool(daily),
        "active": bool(active),
        "verified_by": sender_id,
    }


def approve(db: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    sender_id = str(payload.get("requester_sender_id") or "").strip()
    require_owner(sender_id)
    proposal_id = str(payload.get("proposal_id") or "").strip().upper()
    row = db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
    if not row:
        fail("proposition introuvable")
    if row["status"] == "executed":
        return {"proposal_id": proposal_id, "status": "executed", "already_done": True}
    if row["status"] not in {"pending_approval", "approved"}:
        fail(f"proposition non approuvable: {row['status']}")
    current_hash = hashlib.sha256(row["payload_json"].encode()).hexdigest()
    if current_hash != row["payload_hash"]:
        fail("intégrité de proposition invalide")
    now = utcnow()
    expires = now + timedelta(hours=4)
    db.execute(
        "UPDATE proposals SET status='approved', approved_by=?, approved_at=?, expires_at=? WHERE id=?",
        (sender_id, now.isoformat(timespec="seconds"), expires.isoformat(timespec="seconds"), proposal_id),
    )
    db.commit()
    return {
        "proposal_id": proposal_id,
        "status": "approved",
        "expires_at": expires.isoformat(timespec="minutes"),
        "next_command": f"/gotion_execute {proposal_id}",
        "summary": proposal_summary(row["action_type"], json.loads(row["payload_json"])),
    }


def verify_reference(odoo: Odoo, model: str, record_id: int, fields: list[str]) -> dict[str, Any]:
    rows = odoo.read(model, [record_id], fields)
    if len(rows) != 1:
        fail(f"référence Odoo introuvable: {model} #{record_id}")
    return rows[0]


def execute_chatter_note(odoo: Odoo, payload: dict[str, Any]) -> tuple[str, int, dict[str, Any]]:
    task = verify_reference(odoo, "project.task", payload["record_id"], ["id", "name", "project_id", "active"])
    project = task.get("project_id") or []
    if not isinstance(project, list) or not project or project[0] != PROJECT_ID or not task.get("active"):
        fail("la tâche cible n'est pas une tâche Gotion active")
    message_id = odoo.call(
        "project.task",
        "message_post",
        [[payload["record_id"]]],
        {"body": html.escape(payload["body"]), "message_type": "comment", "subtype_xmlid": "mail.mt_note"},
    )
    return "mail.message", int(message_id), {"message_id": int(message_id), "task": task}


def execute_task_create(odoo: Odoo, payload: dict[str, Any]) -> tuple[str, int, dict[str, Any]]:
    project = verify_reference(odoo, "project.project", PROJECT_ID, ["id", "name", "active"])
    if not project.get("active"):
        fail("projet Gotion inactif")
    users = odoo.read("res.users", payload["user_ids"], ["id", "name", "active"])
    if len(users) != len(set(payload["user_ids"])) or any(not user.get("active") for user in users):
        fail("utilisateur Odoo introuvable ou inactif")
    duplicate = odoo.search_read(
        "project.task",
        [["project_id", "=", PROJECT_ID], ["name", "=", payload["name"]], ["active", "=", True]],
        ["id", "name", "stage_id", "user_ids"],
        limit=5,
    )
    if duplicate:
        fail(f"doublon de tâche détecté: #{duplicate[0]['id']}")
    record_id = int(
        odoo.call(
            "project.task",
            "create",
            [
                {
                    "project_id": PROJECT_ID,
                    "name": payload["name"],
                    "description": payload["description"],
                    "user_ids": [(6, 0, payload["user_ids"])],
                    "date_deadline": payload["date_deadline"],
                }
            ],
        )
    )
    readback = verify_reference(odoo, "project.task", record_id, ["id", "name", "project_id", "stage_id", "user_ids", "date_deadline", "active"])
    return "project.task", record_id, readback


def verify_company_reference(record: dict[str, Any], company_id: int, label: str) -> None:
    relation = record.get("company_id")
    if relation and (not isinstance(relation, list) or int(relation[0]) != company_id):
        fail(f"{label} n'appartient pas à la société #{company_id}")


def execute_purchase_draft(odoo: Odoo, payload: dict[str, Any]) -> tuple[str, int, dict[str, Any]]:
    company_id = payload["company_id"]
    company = verify_reference(odoo, "res.company", company_id, ["id", "name", "active"])
    partner = verify_reference(odoo, "res.partner", payload["partner_id"], ["id", "display_name", "active", "supplier_rank"])
    picking_type = verify_reference(odoo, "stock.picking.type", payload["picking_type_id"], ["id", "name", "code", "company_id", "active"])
    if not company.get("active") or not partner.get("active") or int(partner.get("supplier_rank") or 0) <= 0:
        fail("société ou fournisseur inactif/non fournisseur")
    if picking_type.get("code") != "incoming" or not picking_type.get("active"):
        fail("type d'opération non valide pour une réception fournisseur")
    verify_company_reference(picking_type, company_id, "type d'opération")
    product_ids = sorted({line["product_id"] for line in payload["lines"]})
    uom_ids = sorted({line["uom_id"] for line in payload["lines"]})
    products = odoo.read("product.product", product_ids, ["id", "display_name", "active", "purchase_ok", "company_id"])
    uoms = odoo.read("uom.uom", uom_ids, ["id", "name", "active"])
    if len(products) != len(product_ids) or any(not p.get("active") or not p.get("purchase_ok") for p in products):
        fail("produit introuvable, inactif ou non achetable")
    if len(uoms) != len(uom_ids) or any(not u.get("active") for u in uoms):
        fail("unité de mesure introuvable ou inactive")
    duplicate = odoo.search_read(
        "purchase.order",
        [["origin", "=", payload["origin"]], ["partner_id", "=", payload["partner_id"]], ["company_id", "=", company_id], ["state", "!=", "cancel"]],
        ["id", "name", "state", "amount_total"],
        limit=5,
    )
    if duplicate:
        fail(f"doublon d'achat détecté: {duplicate[0]['name']} #{duplicate[0]['id']}")
    order_lines = []
    planned_default = (utcnow() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    for line in payload["lines"]:
        vals: dict[str, Any] = {
            "product_id": line["product_id"],
            "name": line["description"] or f"Produit Odoo #{line['product_id']}",
            "product_qty": line["qty"],
            "product_uom_id": line["uom_id"],
            "price_unit": line["price_unit"],
            "date_planned": line["date_planned"] or planned_default,
            "tax_ids": [(6, 0, line["tax_ids"])],
        }
        if line["analytic_distribution"]:
            vals["analytic_distribution"] = line["analytic_distribution"]
        order_lines.append((0, 0, vals))
    values: dict[str, Any] = {
        "company_id": company_id,
        "partner_id": payload["partner_id"],
        "picking_type_id": payload["picking_type_id"],
        "origin": payload["origin"],
        "order_line": order_lines,
    }
    if payload["partner_ref"]:
        values["partner_ref"] = payload["partner_ref"]
    record_id = int(odoo.call("purchase.order", "create", [values]))
    readback = verify_reference(
        odoo,
        "purchase.order",
        record_id,
        ["id", "name", "state", "company_id", "partner_id", "picking_type_id", "origin", "amount_total", "order_line"],
    )
    if readback.get("state") != "draft":
        fail("le bon créé n'est pas resté en brouillon")
    return "purchase.order", record_id, readback


def execute_picking_draft(odoo: Odoo, payload: dict[str, Any]) -> tuple[str, int, dict[str, Any]]:
    company_id = payload["company_id"]
    verify_reference(odoo, "res.company", company_id, ["id", "name", "active"])
    picking_type = verify_reference(odoo, "stock.picking.type", payload["picking_type_id"], ["id", "name", "code", "company_id", "active"])
    if picking_type.get("code") != "internal" or not picking_type.get("active"):
        fail("seul un transfert interne brouillon est autorisé")
    verify_company_reference(picking_type, company_id, "type d'opération")
    locations = odoo.read("stock.location", [payload["location_id"], payload["location_dest_id"]], ["id", "complete_name", "usage", "company_id", "active"])
    if len(locations) != 2 or any(not loc.get("active") or loc.get("usage") != "internal" for loc in locations):
        fail("emplacement source/destination introuvable, inactif ou non interne")
    for location in locations:
        verify_company_reference(location, company_id, "emplacement")
    product_ids = sorted({line["product_id"] for line in payload["lines"]})
    uom_ids = sorted({line["uom_id"] for line in payload["lines"]})
    products = odoo.read("product.product", product_ids, ["id", "display_name", "active", "company_id", "tracking"])
    uoms = odoo.read("uom.uom", uom_ids, ["id", "name", "active"])
    if len(products) != len(product_ids) or any(not p.get("active") for p in products):
        fail("produit introuvable ou inactif")
    if len(uoms) != len(uom_ids) or any(not u.get("active") for u in uoms):
        fail("unité de mesure introuvable ou inactive")
    product_by_id = {product["id"]: product for product in products}
    for line in payload["lines"]:
        tracking = product_by_id[line["product_id"]].get("tracking")
        if tracking in {"lot", "serial"}:
            fail(
                f"produit #{line['product_id']} suivi par lot/série: préparation automatique bloquée; "
                "Youssef doit vérifier lot, colis et lignes détaillées"
            )
    duplicate = odoo.search_read(
        "stock.picking",
        [["origin", "=", payload["origin"]], ["company_id", "=", company_id], ["location_id", "=", payload["location_id"]], ["location_dest_id", "=", payload["location_dest_id"]], ["state", "!=", "cancel"]],
        ["id", "name", "state"],
        limit=5,
    )
    if duplicate:
        fail(f"doublon de transfert détecté: {duplicate[0]['name']} #{duplicate[0]['id']}")
    moves = []
    for line in payload["lines"]:
        moves.append(
            (
                0,
                0,
                {
                    "name": line["description"] or f"Produit Odoo #{line['product_id']}",
                    "product_id": line["product_id"],
                    "product_uom_qty": line["qty"],
                    "product_uom": line["uom_id"],
                    "location_id": payload["location_id"],
                    "location_dest_id": payload["location_dest_id"],
                    "company_id": company_id,
                },
            )
        )
    values: dict[str, Any] = {
        "company_id": company_id,
        "picking_type_id": payload["picking_type_id"],
        "location_id": payload["location_id"],
        "location_dest_id": payload["location_dest_id"],
        "origin": payload["origin"],
        "move_ids": moves,
    }
    if payload["scheduled_date"]:
        values["scheduled_date"] = payload["scheduled_date"]
    record_id = int(odoo.call("stock.picking", "create", [values]))
    readback = verify_reference(
        odoo,
        "stock.picking",
        record_id,
        ["id", "name", "state", "company_id", "picking_type_id", "location_id", "location_dest_id", "origin", "move_ids"],
    )
    if readback.get("state") != "draft":
        fail("le transfert créé n'est pas resté en brouillon")
    return "stock.picking", record_id, readback


def execute(db: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    sender_id = str(payload.get("requester_sender_id") or "").strip()
    require_owner(sender_id)
    proposal_id = str(payload.get("proposal_id") or "").strip().upper()
    row = db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
    if not row:
        fail("proposition introuvable")
    if row["status"] == "executed":
        return {
            "proposal_id": proposal_id,
            "status": "executed",
            "already_done": True,
            "odoo_model": row["odoo_model"],
            "odoo_record_id": row["odoo_record_id"],
            "readback": json.loads(row["readback_json"] or "{}"),
        }
    if row["status"] != "approved" or not row["expires_at"]:
        fail("la proposition doit d'abord être approuvée")
    if datetime.fromisoformat(row["expires_at"]) < utcnow():
        db.execute("UPDATE proposals SET status='expired' WHERE id=?", (proposal_id,))
        db.commit()
        fail("approbation expirée; prépare une nouvelle proposition")
    current_hash = hashlib.sha256(row["payload_json"].encode()).hexdigest()
    if current_hash != row["payload_hash"]:
        fail("intégrité de proposition invalide")
    action_payload = json.loads(row["payload_json"])
    try:
        odoo = Odoo()
        if row["action_type"] == "chatter_note":
            model, record_id, readback = execute_chatter_note(odoo, action_payload)
        elif row["action_type"] in {"project_task_create", "worker_intake_task"}:
            model, record_id, readback = execute_task_create(odoo, action_payload)
        elif row["action_type"] == "purchase_order_draft":
            model, record_id, readback = execute_purchase_draft(odoo, action_payload)
        elif row["action_type"] == "stock_picking_draft":
            model, record_id, readback = execute_picking_draft(odoo, action_payload)
        else:
            fail("exécuteur absent pour cette action")
    except Exception as exc:
        db.execute("UPDATE proposals SET error=? WHERE id=?", (f"{type(exc).__name__}: {str(exc)[:500]}", proposal_id))
        db.commit()
        raise
    now = iso_now()
    db.execute(
        """UPDATE proposals SET status='executed', executed_at=?, odoo_model=?,
           odoo_record_id=?, readback_json=?, error=NULL WHERE id=?""",
        (now, model, record_id, canonical(readback), proposal_id),
    )
    db.execute(
        "INSERT INTO case_events(case_id,event_type,actor_id,payload_json,created_at) VALUES (?,?,?,?,?)",
        (row["case_id"], "odoo_executed", sender_id, canonical({"proposal_id": proposal_id, "model": model, "record_id": record_id}), now),
    )
    db.commit()
    return {
        "proposal_id": proposal_id,
        "status": "executed",
        "odoo_model": model,
        "odoo_record_id": record_id,
        "odoo_url": f"{env('ODOO_URL', default='https://pepiniere-belkora.odoo.com').rstrip('/')}/web#id={record_id}&model={model}&view_type=form",
        "readback": readback,
        "notice": "Écriture créée et relue. Les brouillons achat/stock ne sont ni confirmés ni validés automatiquement.",
    }


def dashboard(db: sqlite3.Connection, sender_id: str) -> dict[str, Any]:
    actor_row(db, sender_id)
    cases = db.execute(
        "SELECT status, COUNT(*) AS count FROM cases GROUP BY status ORDER BY status"
    ).fetchall()
    proposals = db.execute(
        "SELECT status, COUNT(*) AS count FROM proposals GROUP BY status ORDER BY status"
    ).fetchall()
    actors = db.execute(
        "SELECT telegram_id,name,role,language,voice_preferred,daily_report_required,active FROM actors ORDER BY role,name"
    ).fetchall()
    return {
        "cases": {row["status"]: row["count"] for row in cases},
        "proposals": {row["status"]: row["count"] for row in proposals},
        "actors": [dict(row) for row in actors],
    }


def reminder_text(db: sqlite3.Connection, phase: str, today: str | None = None) -> str:
    work_date = today or date.today().isoformat()
    actors = db.execute(
        "SELECT * FROM actors WHERE active=1 AND daily_report_required=1 ORDER BY name"
    ).fetchall()
    if not actors:
        return "NO_REPLY"
    lines: list[str] = []
    for actor in actors:
        row = db.execute(
            "SELECT * FROM cases WHERE case_type='daily_report' AND work_date=? AND actor_id=? ORDER BY updated_at DESC LIMIT 1",
            (work_date, actor["telegram_id"]),
        ).fetchone()
        if row and row["status"] == "ready_for_review":
            continue
        missing = json.loads(row["missing_json"]) if row else REQUIRED_FIELDS["daily_report"]
        questions = next_questions(missing, actor["language"])
        if phase == "ask":
            if actor["language"] in {"ar", "darija"}:
                lines.append(f"{actor['name']}: عافاك صيفط تقرير اليوم {work_date}. " + " ".join(questions))
            else:
                lines.append(f"{actor['name']} : merci d'envoyer le rapport du {work_date}. " + " ".join(questions))
        elif phase == "escalate":
            if actor["language"] in {"ar", "darija"}:
                lines.append(f"⚠️ {actor['name']}: التقرير ديال {work_date} باقي ناقص ({', '.join(missing[:5])}).")
            else:
                lines.append(f"⚠️ {actor['name']} : rapport du {work_date} toujours incomplet ({', '.join(missing[:5])}).")
        if row:
            db.execute(
                "UPDATE cases SET reminder_count=reminder_count+1, last_question_at=? WHERE id=?",
                (iso_now(), row["id"]),
            )
    db.commit()
    if not lines:
        return "NO_REPLY"
    header = "📋 Rapports chantier Gotion" if phase == "ask" else "🚨 Rapports Gotion à régulariser"
    return header + "\n" + "\n".join(f"• {line}" for line in lines)


def summary_text(db: sqlite3.Connection) -> str:
    rows = db.execute(
        """SELECT c.*, a.name AS actor_name FROM cases c JOIN actors a ON a.telegram_id=c.actor_id
           WHERE c.status IN ('collecting','ready_for_review') ORDER BY c.updated_at ASC LIMIT 20"""
    ).fetchall()
    proposals = db.execute(
        "SELECT * FROM proposals WHERE status IN ('pending_approval','approved') ORDER BY prepared_at ASC LIMIT 20"
    ).fetchall()
    if not rows and not proposals:
        return "NO_REPLY"
    lines = ["🧭 Point opérationnel Gotion"]
    for row in rows:
        missing = json.loads(row["missing_json"])
        suffix = f" — manque: {', '.join(missing[:4])}" if missing else " — prêt pour revue"
        lines.append(f"• {row['id']} [{row['case_type']}] {row['actor_name']}{suffix}")
    for row in proposals:
        lines.append(f"• {row['id']} [{row['status']}] {proposal_summary(row['action_type'], json.loads(row['payload_json']))}")
    return "\n".join(lines)


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    with connect_db() as db:
        if operation == "case_record":
            return case_record(db, payload)
        if operation == "case_get":
            return case_get(db, payload)
        if operation == "case_list":
            return case_list(db, payload)
        if operation == "odoo_lookup":
            return odoo_lookup(db, payload)
        if operation == "action_prepare":
            return action_prepare(db, payload)
        if operation == "actor_upsert":
            return actor_upsert(db, payload)
        if operation == "approve":
            return approve(db, payload)
        if operation == "execute":
            return execute(db, payload)
        if operation == "dashboard":
            return dashboard(db, str(payload.get("requester_sender_id") or ""))
        fail("opération inconnue")


def main() -> int:
    try:
        if len(sys.argv) >= 2 and sys.argv[1] == "tool":
            raw = sys.stdin.read()
            payload = parse_json_object(raw, "commande")
            emit({"ok": True, "result": dispatch(payload)})
            return 0
        if len(sys.argv) >= 3 and sys.argv[1] == "reminder":
            with connect_db() as db:
                print(reminder_text(db, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
            return 0
        if len(sys.argv) >= 2 and sys.argv[1] == "summary":
            with connect_db() as db:
                print(summary_text(db))
            return 0
        print("usage: gotion-operations.py tool|reminder ask|escalate|summary", file=sys.stderr)
        return 2
    except Exception as exc:
        if len(sys.argv) >= 2 and sys.argv[1] == "tool":
            emit({"ok": False, "error": str(exc), "error_type": type(exc).__name__})
        else:
            print("⚠️ Workflow Gotion indisponible; aucune écriture n'a été effectuée.")
            print(type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
