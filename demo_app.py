from __future__ import annotations

import csv
import io
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response

ORG_ID = "org-fieldline-demo"
OWNER_ID = "user-fieldline-owner"
MEMBER_ID = "user-fieldline-member"
PASSWORD = "Demo1234!"


def _now() -> datetime:
    return datetime.now(UTC)


def _iso_days_ago(days: int) -> str:
    return (_now() - timedelta(days=days)).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


def _seed_state() -> dict[str, Any]:
    users = [
        {
            "id": OWNER_ID,
            "email": "alex@fieldline.demo",
            "full_name": "Alex Morgan",
            "is_active": True,
            "memberships": [{"organization_id": ORG_ID, "role": "owner"}],
        },
        {
            "id": MEMBER_ID,
            "email": "jordan@fieldline.demo",
            "full_name": "Jordan Lee",
            "is_active": True,
            "memberships": [{"organization_id": ORG_ID, "role": "member"}],
        },
    ]
    companies = [
        {"id": "co-1001", "organization_id": ORG_ID, "owner_user_id": OWNER_ID, "name": "Northstar Studio", "website": "https://northstar.studio", "phone": "+1 415 555 0101"},
        {"id": "co-1002", "organization_id": ORG_ID, "owner_user_id": OWNER_ID, "name": "Meridian Health", "website": "https://meridian.health", "phone": "+1 415 555 0102"},
        {"id": "co-1003", "organization_id": ORG_ID, "owner_user_id": MEMBER_ID, "name": "Juniper Financial", "website": "https://juniper.financial", "phone": "+1 415 555 0103"},
        {"id": "co-1004", "organization_id": ORG_ID, "owner_user_id": OWNER_ID, "name": "Atlas Works", "website": "https://atlasworks.example", "phone": "+1 415 555 0104"},
        {"id": "co-1005", "organization_id": ORG_ID, "owner_user_id": MEMBER_ID, "name": "Cedar & Co", "website": "https://cedar.example", "phone": "+1 415 555 0105"},
    ]
    contact_seed = [
        ("ct-2001", "Maya", "Chen", "maya@northstar.studio", "Director of Operations", "customer", "co-1001", OWNER_ID),
        ("ct-2002", "Oliver", "Grant", "oliver@meridian.health", "VP Partnerships", "prospect", "co-1002", OWNER_ID),
        ("ct-2003", "Priya", "Shah", "priya@juniper.financial", "Chief of Staff", "prospect", "co-1003", MEMBER_ID),
        ("ct-2004", "Ethan", "Brooks", "ethan@atlasworks.example", "Founder", "lead", "co-1004", OWNER_ID),
        ("ct-2005", "Sofia", "Rivera", "sofia@cedar.example", "Finance Lead", "customer", "co-1005", MEMBER_ID),
        ("ct-2006", "Noah", "Williams", "noah@brightpath.example", "Commercial Director", "prospect", None, OWNER_ID),
        ("ct-2007", "Morgan", "Reed", "morgan@atlasworks.example", "Operations Manager", "prospect", "co-1004", OWNER_ID),
        ("ct-2008", "Morgan", "Redd", "morgan@atlasworks.example", "Operations Manager", "lead", "co-1004", OWNER_ID),
    ]
    contacts = [
        {
            "id": row[0],
            "organization_id": ORG_ID,
            "first_name": row[1],
            "last_name": row[2],
            "email": row[3],
            "phone": f"+1 415 555 {2200 + index}",
            "job_title": row[4],
            "lifecycle": row[5],
            "company_id": row[6],
            "owner_user_id": row[7],
        }
        for index, row in enumerate(contact_seed)
    ]
    stages = [
        {"id": "st-1", "organization_id": ORG_ID, "name": "Lead", "order_index": 0, "win_probability": 10, "is_closed": False, "is_won": False},
        {"id": "st-2", "organization_id": ORG_ID, "name": "Qualified", "order_index": 1, "win_probability": 25, "is_closed": False, "is_won": False},
        {"id": "st-3", "organization_id": ORG_ID, "name": "Proposal", "order_index": 2, "win_probability": 60, "is_closed": False, "is_won": False},
        {"id": "st-4", "organization_id": ORG_ID, "name": "Negotiation", "order_index": 3, "win_probability": 85, "is_closed": False, "is_won": False},
        {"id": "st-5", "organization_id": ORG_ID, "name": "Closed Won", "order_index": 4, "win_probability": 100, "is_closed": True, "is_won": True},
        {"id": "st-6", "organization_id": ORG_ID, "name": "Closed Lost", "order_index": 5, "win_probability": 0, "is_closed": True, "is_won": False},
    ]
    opportunities = [
        {"id": "op-3001", "organization_id": ORG_ID, "owner_user_id": OWNER_ID, "company_id": "co-1001", "contact_id": "ct-2001", "stage_id": "st-3", "name": "Northstar customer portal", "amount": "48000.00", "status": "open", "expected_close_date": "2026-12-15", "lost_reason": None, "created_at": _iso_days_ago(24)},
        {"id": "op-3002", "organization_id": ORG_ID, "owner_user_id": OWNER_ID, "company_id": "co-1002", "contact_id": "ct-2002", "stage_id": "st-4", "name": "Meridian partner rollout", "amount": "72000.00", "status": "open", "expected_close_date": "2026-11-28", "lost_reason": None, "created_at": _iso_days_ago(39)},
        {"id": "op-3003", "organization_id": ORG_ID, "owner_user_id": MEMBER_ID, "company_id": "co-1003", "contact_id": "ct-2003", "stage_id": "st-2", "name": "Juniper onboarding", "amount": "18500.00", "status": "open", "expected_close_date": "2026-12-05", "lost_reason": None, "created_at": _iso_days_ago(11)},
        {"id": "op-3004", "organization_id": ORG_ID, "owner_user_id": OWNER_ID, "company_id": "co-1005", "contact_id": "ct-2005", "stage_id": "st-5", "name": "Cedar finance workspace", "amount": "32000.00", "status": "won", "expected_close_date": "2026-11-02", "lost_reason": None, "created_at": _iso_days_ago(48)},
    ]
    activities = [
        {"id": "act-1", "organization_id": ORG_ID, "actor_user_id": OWNER_ID, "company_id": "co-1001", "contact_id": "ct-2001", "opportunity_id": "op-3001", "activity_type": "meeting", "title": "Quarterly planning call", "body": "Reviewed launch milestones and procurement timeline.", "occurred_at": _iso_days_ago(2)},
        {"id": "act-2", "organization_id": ORG_ID, "actor_user_id": MEMBER_ID, "company_id": "co-1003", "contact_id": "ct-2003", "opportunity_id": "op-3003", "activity_type": "email", "title": "Shared onboarding outline", "body": "Sent the proposed onboarding checklist.", "occurred_at": _iso_days_ago(5)},
    ]
    tasks = [
        {"id": "task-1", "organization_id": ORG_ID, "created_by_user_id": OWNER_ID, "assigned_to_user_id": OWNER_ID, "company_id": "co-1002", "contact_id": "ct-2002", "opportunity_id": "op-3002", "title": "Confirm Meridian stakeholder review", "description": "Follow up on the commercial proposal.", "priority": "high", "due_at": _iso_days_ago(1), "completed_at": None, "created_at": _iso_days_ago(8), "updated_at": _iso_days_ago(1)},
        {"id": "task-2", "organization_id": ORG_ID, "created_by_user_id": OWNER_ID, "assigned_to_user_id": MEMBER_ID, "company_id": "co-1001", "contact_id": "ct-2001", "opportunity_id": "op-3001", "title": "Send Northstar implementation plan", "description": "Share a scoped delivery plan.", "priority": "normal", "due_at": (_now() + timedelta(days=2)).isoformat(), "completed_at": None, "created_at": _iso_days_ago(2), "updated_at": _iso_days_ago(2)},
    ]
    return {
        "users": users,
        "sessions": {},
        "companies": companies,
        "contacts": contacts,
        "stages": stages,
        "opportunities": opportunities,
        "activities": activities,
        "tasks": tasks,
        "saved_views": [
            {"id": "view-1", "organization_id": ORG_ID, "created_by_user_id": OWNER_ID, "resource": "contacts", "name": "Prospects to follow up", "shared": True, "definition_version": 1, "definition": {"query": None, "lifecycle": ["prospect"], "company_id": None, "owner_user_id": None, "has_email": True, "sort": "updated_desc"}}
        ],
        "automation_rules": [
            {"id": "rule-1", "organization_id": ORG_ID, "name": "Won deal handoff", "trigger": "opportunity.won", "action_type": "create_task", "action_config": {"title": "Schedule customer kickoff", "priority": "high", "due_days": 1}, "enabled": True, "created_at": _iso_days_ago(20), "updated_at": _iso_days_ago(20)},
            {"id": "rule-2", "organization_id": ORG_ID, "name": "Lost deal learning loop", "trigger": "opportunity.lost", "action_type": "create_task", "action_config": {"title": "Record loss feedback", "priority": "normal", "due_days": 3}, "enabled": True, "created_at": _iso_days_ago(20), "updated_at": _iso_days_ago(20)},
        ],
        "automation_runs": [],
        "business_rules": {"stale_contact_days": 21, "stuck_opportunity_days": 30, "overdue_task_days": 0},
        "import_jobs": {},
    }


STATE: dict[str, Any] = _seed_state()


def reset_demo_state() -> None:
    global STATE
    STATE = _seed_state()


def _active(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if not row.get("archived_at")]


def _page(rows: list[dict[str, Any]], request: Request) -> dict[str, Any]:
    page = max(1, int(request.query_params.get("page", "1")))
    page_size = min(100, max(1, int(request.query_params.get("page_size", "25"))))
    start = (page - 1) * page_size
    return {"items": rows[start : start + page_size], "page": page, "page_size": page_size, "total": len(rows)}


def _auth_payload(user: dict[str, Any]) -> dict[str, Any]:
    return {"access_token": "fieldline-demo-" + user["id"], "token_type": "bearer", "user": user}


def _user_for_token(token: str | None) -> dict[str, Any] | None:
    if not token or not token.startswith("fieldline-demo-"):
        return None
    user_id = token.removeprefix("fieldline-demo-")
    return next((user for user in STATE["users"] if user["id"] == user_id), None)


def _require_user(request: Request) -> dict[str, Any]:
    header = request.headers.get("authorization", "")
    token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
    user = _user_for_token(token)
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _require_org(request: Request, organization_id: str) -> dict[str, Any]:
    user = _require_user(request)
    if organization_id != ORG_ID or not any(
        membership["organization_id"] == organization_id
        for membership in user["memberships"]
    ):
        raise HTTPException(status_code=403, detail="Organization access denied")
    return user


def _require_admin(user: dict[str, Any]) -> None:
    role = user["memberships"][0]["role"]
    if role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Owner/admin access is required")


def _find(rows: list[dict[str, Any]], item_id: str, label: str) -> dict[str, Any]:
    item = next((row for row in rows if row["id"] == item_id and not row.get("archived_at")), None)
    if not item:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return item


def _timeline(contact_id: str) -> dict[str, Any]:
    items = [
        {"id": row["id"], "kind": "activity", "timestamp": row["occurred_at"], "title": row["title"], "summary": row.get("body"), "actor_user_id": row.get("actor_user_id")}
        for row in STATE["activities"] if row.get("contact_id") == contact_id
    ]
    items += [
        {"id": row["id"], "kind": "task", "timestamp": row["updated_at"], "title": row["title"], "summary": "Task completed" if row.get("completed_at") else "Follow-up task", "actor_user_id": row.get("created_by_user_id")}
        for row in STATE["tasks"] if row.get("contact_id") == contact_id
    ]
    items.sort(key=lambda item: item["timestamp"], reverse=True)
    return {"items": items[:20], "limit": 20, "next_before": None, "next_before_id": None}


def _quality_report() -> dict[str, Any]:
    ids = {"ct-2007", "ct-2008"}
    duplicate_exists = all(
        any(row["id"] == item_id and not row.get("archived_at") for row in STATE["contacts"])
        for item_id in ids
    )
    duplicate_candidates = [{
        "entity_type": "contact",
        "first_id": "ct-2007",
        "second_id": "ct-2008",
        "first_label": "Morgan Reed",
        "second_label": "Morgan Redd",
        "similarity": 0.97,
        "reasons": ["Same email address", "Same company", "Similar full name"],
    }] if duplicate_exists else []
    issues = []
    for contact in _active(STATE["contacts"]):
        if not contact.get("email"):
            issues.append({
                "code": "missing_email", "entity_type": "contact", "entity_id": contact["id"],
                "severity": "medium", "title": "Contact has no email",
                "detail": f'{contact["first_name"]} {contact["last_name"]} is missing an email address.',
                "fixable": True,
            })
    if duplicate_exists:
        issues.append({
            "code": "possible_duplicate_contact", "entity_type": "contact", "entity_id": "ct-2008",
            "severity": "high", "title": "Possible duplicate contact",
            "detail": "Two contact records share the same email and organization.", "fixable": True,
        })
    overdue = sum(
        1 for task in STATE["tasks"]
        if not task.get("completed_at") and task.get("due_at") and task["due_at"] < _now().isoformat()
    )
    return {
        "generated_at": _now().isoformat(),
        "summary": {
            "total_issues": len(issues) + 1, "high": sum(x["severity"] == "high" for x in issues),
            "medium": sum(x["severity"] == "medium" for x in issues), "low": 1,
            "duplicate_contacts": len(duplicate_candidates), "duplicate_companies": 0,
            "incomplete_records": sum(x["code"] == "missing_email" for x in issues),
            "stale_contacts": 1, "opportunity_issues": 1, "overdue_tasks": overdue,
        },
        "duplicate_candidates": duplicate_candidates, "issues": issues,
    }


def _trigger_automation(opportunity: dict[str, Any], previous_status: str) -> None:
    if opportunity["status"] == previous_status:
        return
    trigger = (
        "opportunity.won" if opportunity["status"] == "won"
        else "opportunity.lost" if opportunity["status"] == "lost"
        else None
    )
    if not trigger:
        return
    for rule in STATE["automation_rules"]:
        if not rule["enabled"] or rule["trigger"] != trigger:
            continue
        config = rule["action_config"]
        task_id = _new_id("task")
        task = {
            "id": task_id, "organization_id": ORG_ID, "created_by_user_id": OWNER_ID,
            "assigned_to_user_id": opportunity["owner_user_id"],
            "company_id": opportunity.get("company_id"), "contact_id": opportunity.get("contact_id"),
            "opportunity_id": opportunity["id"], "title": config["title"],
            "description": f'Created by {rule["name"]}', "priority": config["priority"],
            "due_at": (_now() + timedelta(days=int(config["due_days"]))).isoformat(),
            "completed_at": None, "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
        }
        STATE["tasks"].insert(0, task)
        STATE["automation_runs"].insert(0, {
            "id": _new_id("run"), "workflow": rule["name"], "trigger": trigger,
            "event_key": f'{opportunity["id"]}:{trigger}', "status": "completed",
            "action_type": rule["action_type"], "result": {"task_id": task_id, "title": task["title"]},
            "created_at": _now().isoformat(), "completed_at": _now().isoformat(),
        })


app = FastAPI(
    title="Fieldline CRM Demo API",
    description="Isolated in-memory simulator. It does not import or connect to the production database.",
    version="1.0.0",
)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "fieldline-demo-api", "status": "ok", "mode": "in-memory-demo"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "fieldline-demo-api", "mode": "in-memory-demo"}


@app.api_route(
    "/api/v1/{full_path:path}",
    methods=["GET", "POST", "PATCH", "DELETE"],
)
async def api_dispatch(full_path: str, request: Request, response: Response) -> Any:
    parts = [part for part in full_path.split("/") if part]
    method = request.method.upper()
    try:
        payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    if parts and parts[0] == "auth":
        action = parts[1] if len(parts) > 1 else ""
        if action == "login" and method == "POST":
            email = str(payload.get("email", "")).lower()
            user = next((item for item in STATE["users"] if item["email"] == email), None)
            if not user or payload.get("password") != PASSWORD:
                raise HTTPException(status_code=401, detail="Invalid demo credentials")
            refresh = _new_id("refresh")
            csrf = _new_id("csrf")
            STATE["sessions"][refresh] = {"user_id": user["id"], "csrf": csrf}
            response.set_cookie("fieldline_refresh", refresh, httponly=True, samesite="lax", path="/")
            response.set_cookie("fieldline_csrf", csrf, httponly=False, samesite="lax", path="/")
            return _auth_payload(user)
        if action == "signup" and method == "POST":
            email = str(payload.get("email", "")).strip().lower()
            if not email or any(user["email"] == email for user in STATE["users"]):
                raise HTTPException(status_code=409, detail="An account with that email already exists")
            user = {
                "id": _new_id("user"), "email": email,
                "full_name": str(payload.get("full_name", "New user")),
                "is_active": True, "memberships": [{"organization_id": ORG_ID, "role": "owner"}],
            }
            STATE["users"].append(user)
            refresh = _new_id("refresh")
            csrf = _new_id("csrf")
            STATE["sessions"][refresh] = {"user_id": user["id"], "csrf": csrf}
            response.set_cookie("fieldline_refresh", refresh, httponly=True, samesite="lax", path="/")
            response.set_cookie("fieldline_csrf", csrf, httponly=False, samesite="lax", path="/")
            response.status_code = 201
            return _auth_payload(user)
        if action == "refresh" and method == "POST":
            refresh = request.cookies.get("fieldline_refresh")
            csrf_cookie = request.cookies.get("fieldline_csrf")
            csrf_header = request.headers.get("x-csrf-token")
            session = STATE["sessions"].get(refresh or "")
            if not session or not csrf_cookie or csrf_cookie != csrf_header or csrf_cookie != session["csrf"]:
                raise HTTPException(status_code=401, detail="Not authenticated")
            user = next((item for item in STATE["users"] if item["id"] == session["user_id"]), None)
            if not user:
                raise HTTPException(status_code=401, detail="Invalid demo session")
            return _auth_payload(user)
        if action == "logout" and method == "POST":
            refresh = request.cookies.get("fieldline_refresh")
            session = STATE["sessions"].get(refresh or "")
            csrf_cookie = request.cookies.get("fieldline_csrf")
            if session and csrf_cookie != request.headers.get("x-csrf-token"):
                raise HTTPException(status_code=403, detail="CSRF validation failed")
            if refresh:
                STATE["sessions"].pop(refresh, None)
            response.delete_cookie("fieldline_refresh", path="/")
            response.delete_cookie("fieldline_csrf", path="/")
            response.status_code = 204
            return response
        if action == "me" and method == "GET":
            header = request.headers.get("authorization", "")
            token = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
            user = _user_for_token(token)
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return user

    if len(parts) < 3 or parts[0] != "organizations":
        raise HTTPException(status_code=404, detail="Demo endpoint not found")
    user = _require_org(request, parts[1])
    resource = parts[2]
    tail = parts[3:]
    item_id = tail[0] if tail else None
    action = tail[1] if len(tail) > 1 else None
    is_admin = user["memberships"][0]["role"] in {"owner", "admin"}

    if resource in {"companies", "contacts"}:
        rows = STATE[resource]
        label = "Company" if resource == "companies" else "Contact"
        if not item_id and method == "GET":
            visible = _active(rows)
            query = request.query_params.get("q", "").strip().lower()
            if query:
                visible = [
                    row for row in visible
                    if query in " ".join(str(row.get(key) or "") for key in (
                        ("name", "website", "phone") if resource == "companies"
                        else ("first_name", "last_name", "email", "job_title")
                    )).lower()
                ]
            return _page(visible, request)
        if not item_id and method == "POST":
            if resource == "companies":
                name = str(payload.get("name", "")).strip()
                if not name:
                    raise HTTPException(status_code=422, detail="Company name is required")
                item = {
                    "id": _new_id("company"), "organization_id": ORG_ID,
                    "owner_user_id": user["id"], "name": name,
                    "website": payload.get("website"), "phone": payload.get("phone"),
                }
            else:
                first = str(payload.get("first_name", "")).strip()
                last = str(payload.get("last_name", "")).strip()
                if not first or not last:
                    raise HTTPException(status_code=422, detail="First and last name are required")
                item = {
                    "id": _new_id("contact"), "organization_id": ORG_ID,
                    "owner_user_id": user["id"], "first_name": first, "last_name": last,
                    "email": payload.get("email"), "phone": payload.get("phone"),
                    "job_title": payload.get("job_title"), "lifecycle": payload.get("lifecycle", "lead"),
                    "company_id": payload.get("company_id"),
                }
            rows.insert(0, item)
            response.status_code = 201
            return item
        if item_id and len(tail) == 1:
            if resource == "contacts" and method == "GET":
                contact = _find(rows, item_id, label)
                return contact
            item = _find(rows, item_id, label)
            if method == "PATCH":
                item.update(payload)
                return item
            if method == "DELETE":
                item["archived_at"] = _now().isoformat()
                return Response(status_code=204)

        if resource == "contacts" and item_id and action == "relationship-health" and method == "GET":
            contact = _find(rows, item_id, label)
            activities = [row for row in STATE["activities"] if row.get("contact_id") == item_id]
            recent = max(activities, key=lambda row: row["occurred_at"]) if activities else None
            return {
                "contact_id": contact["id"], "score": 82 if recent else 54,
                "band": "healthy" if recent else "warming",
                "last_activity_at": recent["occurred_at"] if recent else None,
                "activity_count_30d": len(activities),
                "open_opportunity_count": sum(row["contact_id"] == item_id and row["status"] == "open" for row in STATE["opportunities"]),
                "overdue_task_count": sum(row.get("contact_id") == item_id and not row.get("completed_at") and row.get("due_at", "") < _now().isoformat() for row in STATE["tasks"]),
                "evidence": [{"code": "recent_activity", "impact": 12, "description": "Recent customer activity is recorded." if recent else "No recent activity is recorded."}],
            }
        if resource == "contacts" and item_id and action == "timeline" and method == "GET":
            _find(rows, item_id, label)
            return _timeline(item_id)
        if resource == "contacts" and item_id and action == "relationship-graph" and method == "GET":
            contact = _find(rows, item_id, label)
            nodes = [{"id": contact["id"], "type": "contact", "label": contact["first_name"] + " " + contact["last_name"], "meta": {"lifecycle": contact["lifecycle"], "email": contact.get("email")}}]
            edges = []
            related: list[tuple[str, list[dict[str, Any]], str, str]] = [
                ("company", STATE["companies"], "company_id", "works at"),
                ("opportunity", STATE["opportunities"], "contact_id", "engaged in"),
                ("task", STATE["tasks"], "contact_id", "follow-up"),
                ("activity", STATE["activities"], "contact_id", "activity"),
            ]
            for kind, collection, relation_key, edge_label in related:
                for row in collection:
                    matches = row.get(relation_key) == contact["company_id"] if kind == "company" else row.get(relation_key) == item_id
                    if matches and not row.get("archived_at"):
                        nodes.append({"id": row["id"], "type": kind, "label": row.get("name") or row.get("title") or row.get("first_name", kind), "meta": {}})
                        edges.append({"id": _new_id("edge"), "source": item_id, "target": row["id"], "label": edge_label})
            return {"contact_id": item_id, "nodes": nodes, "edges": edges}

    if resource == "opportunities":
        rows = STATE["opportunities"]
        if not item_id and method == "GET":
            visible = _active(rows)
            status = request.query_params.get("status")
            if status:
                visible = [row for row in visible if row["status"] == status]
            return _page(visible, request)
        if not item_id and method == "POST":
            name = str(payload.get("name", "")).strip()
            if not name:
                raise HTTPException(status_code=422, detail="Opportunity name is required")
            item = {
                "id": _new_id("opportunity"), "organization_id": ORG_ID,
                "owner_user_id": user["id"], "company_id": payload.get("company_id"),
                "contact_id": payload.get("contact_id"), "stage_id": payload.get("stage_id", "st-1"),
                "name": name, "amount": str(payload["amount"]) if payload.get("amount") is not None else None,
                "status": payload.get("status", "open"),
                "expected_close_date": payload.get("expected_close_date"), "lost_reason": payload.get("lost_reason"),
                "created_at": _now().isoformat(),
            }
            rows.insert(0, item)
            response.status_code = 201
            return item
        if item_id:
            item = _find(rows, item_id, "Opportunity")
            if method == "GET":
                return item
            if method == "PATCH":
                previous = item["status"]
                item.update(payload)
                stage = next((row for row in STATE["stages"] if row["id"] == item.get("stage_id")), None)
                if stage and stage.get("is_won"):
                    item["status"] = "won"
                elif stage and stage["name"].lower() == "closed lost":
                    item["status"] = "lost"
                _trigger_automation(item, previous)
                return item
            if method == "DELETE":
                item["archived_at"] = _now().isoformat()
                return Response(status_code=204)

    if resource == "pipeline" and item_id == "stages" and method == "GET":
        return STATE["stages"]
    if resource == "pipeline" and item_id == "stages" and method == "POST":
        _require_admin(user)
        name = str(payload.get("name", "")).strip()
        if not name:
            raise HTTPException(status_code=422, detail="Stage name is required")
        if any(row["name"].lower() == name.lower() for row in STATE["stages"]):
            raise HTTPException(status_code=409, detail="Stage already exists")
        stage = {
            "id": _new_id("stage"), "organization_id": ORG_ID, "name": name,
            "order_index": len(STATE["stages"]), "win_probability": float(payload.get("win_probability", 50)),
            "is_closed": False, "is_won": False,
        }
        STATE["stages"].append(stage)
        response.status_code = 201
        return stage
    if resource == "pipeline" and item_id == "stuck" and method == "GET":
        items = []
        for opportunity in STATE["opportunities"]:
            age = (_now() - datetime.fromisoformat(opportunity["created_at"])).days
            if opportunity["status"] == "open" and age >= STATE["business_rules"]["stuck_opportunity_days"]:
                stage = next((row for row in STATE["stages"] if row["id"] == opportunity["stage_id"]), {})
                items.append({
                    "id": opportunity["id"], "name": opportunity["name"], "stage_id": opportunity["stage_id"],
                    "stage_name": stage.get("name", "Unknown"), "amount": opportunity.get("amount"),
                    "status": opportunity["status"], "stage_age_days": age, "last_activity_at": None,
                    "expected_close_date": opportunity.get("expected_close_date"), "overdue_task_count": 0,
                    "has_next_action": False, "reasons": ["No recent pipeline activity"],
                    "recommended_action": "Confirm the next customer decision and update the close plan.",
                })
        return {"generated_at": _now().isoformat(), "configured_threshold_days": STATE["business_rules"]["stuck_opportunity_days"], "items": items}

    if resource == "attention" and method == "GET":
        items = [
            {"entity_type": "task", "entity_id": row["id"], "priority": 96 if row["priority"] == "high" else 82,
             "title": row["title"], "reason": "Task is overdue and still open.", "due_at": row["due_at"], "last_activity_at": None}
            for row in STATE["tasks"]
            if not row.get("completed_at") and row.get("due_at") and row["due_at"] < _now().isoformat()
        ]
        limit = max(1, min(50, int(request.query_params.get("limit", "6"))))
        return {"items": items[:limit], "generated_at": _now().isoformat()}

    if resource == "work-planner" and method == "GET":
        items = []
        for row in STATE["tasks"]:
            if row.get("completed_at"):
                continue
            overdue = bool(row.get("due_at") and row["due_at"] < _now().isoformat())
            items.append({
                "entity_type": "task", "entity_id": row["id"],
                "priority": 96 if row["priority"] == "high" else 82 if overdue else 55,
                "title": row["title"], "reason": "This follow-up is overdue." if overdue else "A planned customer action is still open.",
                "next_action": "Complete the follow-up and record the customer outcome.",
                "evidence": ["Past due date" if overdue else "Open task", row["priority"] + " priority"],
                "due_at": row.get("due_at"), "last_activity_at": None,
            })
        items.sort(key=lambda item: item["priority"], reverse=True)
        return {"generated_at": _now().isoformat(), "items": items}

    if resource == "engagement" and item_id == "activities":
        if method == "GET":
            return STATE["activities"]
        if method == "POST":
            activity = {
                "id": _new_id("activity"), "organization_id": ORG_ID, "actor_user_id": user["id"],
                "company_id": payload.get("company_id"), "contact_id": payload.get("contact_id"),
                "opportunity_id": payload.get("opportunity_id"), "activity_type": payload.get("activity_type", "note"),
                "title": str(payload.get("title", "Customer activity")), "body": payload.get("body"),
                "occurred_at": _now().isoformat(),
            }
            if not any(activity.get(key) for key in ("company_id", "contact_id", "opportunity_id")):
                raise HTTPException(status_code=422, detail="Activity must be linked to a CRM record")
            STATE["activities"].insert(0, activity)
            response.status_code = 201
            return activity
    if resource == "engagement" and item_id == "tasks":
        if method == "POST":
            task = {
                "id": _new_id("task"), "organization_id": ORG_ID, "created_by_user_id": user["id"],
                "assigned_to_user_id": payload.get("assigned_to_user_id", user["id"]),
                "company_id": payload.get("company_id"), "contact_id": payload.get("contact_id"),
                "opportunity_id": payload.get("opportunity_id"), "title": str(payload.get("title", "Follow-up task")),
                "description": payload.get("description"), "priority": payload.get("priority", "normal"),
                "due_at": payload.get("due_at"), "completed_at": None,
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            }
            STATE["tasks"].insert(0, task)
            response.status_code = 201
            return task
        if action and method == "PATCH":
            task = next((row for row in STATE["tasks"] if row["id"] == action), None)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            if payload.get("completed") is True:
                task["completed_at"] = _now().isoformat()
            task.update({key: value for key, value in payload.items() if key != "completed"})
            task["updated_at"] = _now().isoformat()
            return task

    if resource == "data-quality" and method == "GET" and not item_id:
        return _quality_report()
    if resource == "data-quality" and item_id in {"contact", "company"} and action and len(tail) > 2 and method == "POST":
        _require_admin(user)
        duplicate_id = action
        survivor_id = str(payload.get("survivor_id", ""))
        collection = STATE["contacts"] if item_id == "contact" else STATE["companies"]
        duplicate = _find(collection, duplicate_id, item_id.title())
        survivor = _find(collection, survivor_id, item_id.title())
        if item_id == "contact":
            for collection_name in ("activities", "tasks", "opportunities"):
                for row in STATE[collection_name]:
                    if row.get("contact_id") == duplicate_id:
                        row["contact_id"] = survivor_id
        else:
            for collection_name in ("contacts", "activities", "tasks", "opportunities"):
                for row in STATE[collection_name]:
                    if row.get("company_id") == duplicate_id:
                        row["company_id"] = survivor_id
        duplicate["archived_at"] = _now().isoformat()
        return {"operation_id": _new_id("merge"), "entity_type": item_id, "survivor_id": survivor["id"], "merged_id": duplicate_id, "completed_at": _now().isoformat()}

    if resource == "saved-views":
        rows = STATE["saved_views"]
        if not item_id and method == "GET":
            return rows
        if not item_id and method == "POST":
            item = {
                "id": _new_id("view"), "organization_id": ORG_ID, "created_by_user_id": user["id"],
                "resource": "contacts", "name": str(payload.get("name", "New view")),
                "shared": bool(payload.get("shared", False)), "definition_version": 1,
                "definition": payload.get("definition", {"query": None, "lifecycle": [], "company_id": None, "owner_user_id": None, "has_email": None, "sort": "updated_desc"}),
            }
            rows.insert(0, item)
            response.status_code = 201
            return item
        if item_id:
            item = next((row for row in rows if row["id"] == item_id), None)
            if not item:
                raise HTTPException(status_code=404, detail="Saved view not found")
            if action == "execute" and method == "GET":
                contacts = _active(STATE["contacts"])
                definition = item["definition"]
                lifecycle = definition.get("lifecycle") or []
                if lifecycle:
                    contacts = [row for row in contacts if row["lifecycle"] in lifecycle]
                if definition.get("query"):
                    query = str(definition["query"]).lower()
                    contacts = [row for row in contacts if query in (row["first_name"] + " " + row["last_name"] + " " + (row.get("email") or "")).lower()]
                if definition.get("has_email") is True:
                    contacts = [row for row in contacts if row.get("email")]
                return _page(contacts, request)
            if method == "PATCH":
                item.update(payload)
                if "definition" in payload:
                    item["definition_version"] += 1
                return item
            if method == "DELETE":
                rows.remove(item)
                return Response(status_code=204)
            if method == "GET":
                return item

    if resource == "automation":
        if item_id == "rules" and method == "GET":
            _require_admin(user)
            return STATE["automation_rules"]
        if item_id == "rules" and method == "POST":
            _require_admin(user)
            rule = {
                "id": _new_id("rule"), "organization_id": ORG_ID,
                "name": str(payload.get("name", "New rule")), "trigger": payload.get("trigger", "opportunity.won"),
                "action_type": payload.get("action_type", "create_task"),
                "action_config": payload.get("action_config", {"title": "Follow up", "priority": "normal", "due_days": 1}),
                "enabled": payload.get("enabled", True), "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            }
            STATE["automation_rules"].insert(0, rule)
            response.status_code = 201
            return rule
        if item_id == "rules" and action and method == "PATCH":
            _require_admin(user)
            rule = next((row for row in STATE["automation_rules"] if row["id"] == action), None)
            if not rule:
                raise HTTPException(status_code=404, detail="Automation rule not found")
            rule.update(payload)
            rule["updated_at"] = _now().isoformat()
            return rule
        if item_id == "runs" and method == "GET":
            _require_admin(user)
            return STATE["automation_runs"][:50]

    if resource == "business-rules":
        if not item_id and method == "GET":
            descriptions = {
                "stale_contact_days": "Days without a customer interaction before a contact is considered stale",
                "stuck_opportunity_days": "Days an open opportunity can remain without progress",
                "overdue_task_days": "Grace period for overdue follow-up tasks",
            }
            defaults = {"stale_contact_days": 21, "stuck_opportunity_days": 30, "overdue_task_days": 0}
            return [{"key": key, "value": value, "default": defaults[key], "description": descriptions[key]} for key, value in STATE["business_rules"].items()]
        if item_id and method == "PATCH":
            _require_admin(user)
            value = payload.get("value")
            if not isinstance(value, int) or not 0 <= value <= 365:
                raise HTTPException(status_code=422, detail="Value must be an integer from 0 to 365")
            if item_id not in STATE["business_rules"]:
                raise HTTPException(status_code=404, detail="Business rule not found")
            STATE["business_rules"][item_id] = value
            return {"key": item_id, "value": value, "default": value, "description": "Updated demo operating threshold"}

    if resource == "system-health" and method == "GET":
        return {
            "generated_at": _now().isoformat(), "status": "warning",
            "checks": {
                "demo_mode": {"status": "warning", "detail": "In-memory synthetic data only; no production database is connected."},
                "database": {"status": "warning", "detail": "The simulator does not start or connect to PostgreSQL."},
                "automation": {"status": "ok", "detail": "Configured rules execute deterministically in this process."},
            },
        }

    if resource == "imports" and item_id == "contacts" and action == "preview" and method == "POST":
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(status_code=422, detail="Choose a CSV file")
        raw = (await upload.read()).decode("utf-8-sig")
        rows = []
        reader = csv.DictReader(io.StringIO(raw))
        known_emails = {str(row.get("email", "")).lower() for row in STATE["contacts"] if row.get("email")}
        for row_number, row in enumerate(reader, start=2):
            values = {str(key or "").strip().lower(): str(value or "").strip() for key, value in row.items()}
            errors = []
            if not values.get("first_name"):
                errors.append("First name is required")
            if not values.get("last_name"):
                errors.append("Last name is required")
            email = values.get("email", "")
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                errors.append("A valid email is required")
            if email.lower() in known_emails:
                errors.append("Email already exists in this workspace")
            rows.append({"row_number": row_number, "row": values, "errors": errors})
            if email:
                known_emails.add(email.lower())
        valid = sum(not row["errors"] for row in rows)
        invalid = len(rows) - valid
        job_id = _new_id("import")
        job = {
            "id": job_id, "status": "preview_ready", "filename": getattr(upload, "filename", "contacts.csv"),
            "total_rows": len(rows), "valid_rows": valid, "invalid_rows": invalid,
            "committed_rows": 0, "created_at": _now().isoformat(), "completed_at": None,
            "errors": [{"row_number": row["row_number"], "errors": row["errors"]} for row in rows if row["errors"]],
            "errors_truncated": False, "rows": rows,
        }
        STATE["import_jobs"][job_id] = job
        return {key: value for key, value in job.items() if key != "rows"}

    if resource == "imports" and item_id and action == "commit" and method == "POST":
        job = STATE["import_jobs"].get(item_id)
        if not job:
            raise HTTPException(status_code=404, detail="Import job not found")
        if job["invalid_rows"]:
            raise HTTPException(status_code=409, detail="Resolve invalid rows before committing")
        dry_run = bool(payload.get("dry_run", False))
        would_create = job["valid_rows"]
        if not dry_run and job["status"] != "completed":
            for entry in job["rows"]:
                row = entry["row"]
                STATE["contacts"].insert(0, {
                    "id": _new_id("contact"), "organization_id": ORG_ID, "owner_user_id": user["id"],
                    "first_name": row["first_name"], "last_name": row["last_name"],
                    "email": row["email"], "phone": row.get("phone"), "job_title": row.get("job_title"),
                    "lifecycle": "lead", "company_id": None,
                })
            job["status"] = "completed"
            job["committed_rows"] = would_create
            job["completed_at"] = _now().isoformat()
        return {
            "job_id": item_id, "status": "dry_run" if dry_run else job["status"], "dry_run": dry_run,
            "total_rows": job["total_rows"], "valid_rows": job["valid_rows"],
            "invalid_rows": job["invalid_rows"], "would_create": would_create,
            "committed_rows": 0 if dry_run else job["committed_rows"],
        }

    raise HTTPException(status_code=404, detail=f"Demo endpoint not found: {method} /{full_path}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)
