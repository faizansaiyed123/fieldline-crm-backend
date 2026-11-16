from fastapi.testclient import TestClient

from demo_app import ORG_ID, app, reset_demo_state


def _login(client: TestClient, email: str = "alex@fieldline.demo") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Demo1234!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _client() -> TestClient:
    reset_demo_state()
    return TestClient(app)


def test_seeded_workspace_and_tenant_boundary() -> None:
    with _client() as client:
        headers = _login(client)
        companies = client.get(f"/api/v1/organizations/{ORG_ID}/companies", headers=headers)
        contacts = client.get(f"/api/v1/organizations/{ORG_ID}/contacts", headers=headers)
        assert companies.status_code == 200
        assert companies.json()["total"] == 5
        assert contacts.status_code == 200
        assert contacts.json()["total"] == 8

        denied = client.get("/api/v1/organizations/not-the-demo-org/contacts", headers=headers)
        assert denied.status_code == 403


def test_company_contact_crud_and_search_readback() -> None:
    with _client() as client:
        headers = _login(client)
        company = client.post(
            f"/api/v1/organizations/{ORG_ID}/companies",
            headers=headers,
            json={"name": "Recruiter Demo Co", "website": "https://recruiter.example"},
        )
        assert company.status_code == 201
        company_id = company.json()["id"]

        contact = client.post(
            f"/api/v1/organizations/{ORG_ID}/contacts",
            headers=headers,
            json={
                "first_name": "Taylor",
                "last_name": "Example",
                "email": "taylor@recruiter.example",
                "lifecycle": "prospect",
                "company_id": company_id,
            },
        )
        assert contact.status_code == 201
        contact_id = contact.json()["id"]

        updated = client.patch(
            f"/api/v1/organizations/{ORG_ID}/contacts/{contact_id}",
            headers=headers,
            json={"lifecycle": "customer"},
        )
        assert updated.json()["lifecycle"] == "customer"

        listed = client.get(
            f"/api/v1/organizations/{ORG_ID}/contacts?q=taylor",
            headers=headers,
        )
        assert listed.json()["total"] == 1
        assert listed.json()["items"][0]["company_id"] == company_id


def test_task_activity_and_planner_completion() -> None:
    with _client() as client:
        headers = _login(client)
        contact_id = "ct-2001"
        activity = client.post(
            f"/api/v1/organizations/{ORG_ID}/engagement/activities",
            headers=headers,
            json={"contact_id": contact_id, "activity_type": "call", "title": "Demo discovery call"},
        )
        assert activity.status_code == 201
        assert client.get(
            f"/api/v1/organizations/{ORG_ID}/contacts/{contact_id}/timeline",
            headers=headers,
        ).json()["items"][0]["title"] == "Demo discovery call"

        task = client.post(
            f"/api/v1/organizations/{ORG_ID}/engagement/tasks",
            headers=headers,
            json={"contact_id": contact_id, "title": "Send recap", "priority": "high"},
        )
        task_id = task.json()["id"]
        planner = client.get(f"/api/v1/organizations/{ORG_ID}/work-planner", headers=headers)
        assert any(item["entity_id"] == task_id for item in planner.json()["items"])

        completed = client.patch(
            f"/api/v1/organizations/{ORG_ID}/engagement/tasks/{task_id}",
            headers=headers,
            json={"completed": True},
        )
        assert completed.json()["completed_at"] is not None
        planner_after = client.get(f"/api/v1/organizations/{ORG_ID}/work-planner", headers=headers)
        assert all(item["entity_id"] != task_id for item in planner_after.json()["items"])


def test_pipeline_outcome_runs_automation_and_creates_followup() -> None:
    with _client() as client:
        headers = _login(client)
        updated = client.patch(
            f"/api/v1/organizations/{ORG_ID}/opportunities/op-3001",
            headers=headers,
            json={"stage_id": "st-5"},
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "won"

        runs = client.get(f"/api/v1/organizations/{ORG_ID}/automation/runs", headers=headers)
        assert runs.status_code == 200
        assert runs.json()[0]["trigger"] == "opportunity.won"
        tasks = client.get(f"/api/v1/organizations/{ORG_ID}/engagement/tasks", headers=headers)
        assert tasks.status_code == 404  # task listing is intentionally not exposed in this simulator
        assert any(task["title"] == "Schedule customer kickoff" for task in __import__("demo_app").STATE["tasks"])


def test_member_role_cannot_manage_owner_automation() -> None:
    with _client() as client:
        headers = _login(client, "jordan@fieldline.demo")
        response = client.get(f"/api/v1/organizations/{ORG_ID}/automation/rules", headers=headers)
        assert response.status_code == 403


def test_csv_preview_dry_run_and_commit_readback() -> None:
    with _client() as client:
        headers = _login(client)
        csv_data = "first_name,last_name,email,phone,job_title\nTaylor,North,taylor.north@example.com,555-0100,Buyer\n"
        preview = client.post(
            f"/api/v1/organizations/{ORG_ID}/imports/contacts/preview",
            headers=headers,
            files={"file": ("contacts.csv", csv_data, "text/csv")},
        )
        assert preview.status_code == 200
        job_id = preview.json()["id"]
        assert preview.json()["valid_rows"] == 1

        dry_run = client.post(
            f"/api/v1/organizations/{ORG_ID}/imports/{job_id}/commit",
            headers=headers,
            json={"dry_run": True},
        )
        assert dry_run.json()["would_create"] == 1
        assert dry_run.json()["committed_rows"] == 0

        committed = client.post(
            f"/api/v1/organizations/{ORG_ID}/imports/{job_id}/commit",
            headers=headers,
            json={"dry_run": False},
        )
        assert committed.json()["committed_rows"] == 1
        contacts = client.get(
            f"/api/v1/organizations/{ORG_ID}/contacts?q=taylor.north",
            headers=headers,
        )
        assert contacts.json()["total"] == 1


def test_invalid_import_rows_are_flagged_before_commit() -> None:
    with _client() as client:
        headers = _login(client)
        csv_data = "first_name,last_name,email\nMissing,Email,not-an-email\n"
        preview = client.post(
            f"/api/v1/organizations/{ORG_ID}/imports/contacts/preview",
            headers=headers,
            files={"file": ("invalid.csv", csv_data, "text/csv")},
        )
        assert preview.json()["invalid_rows"] == 1
        assert preview.json()["errors"][0]["row_number"] == 2
        blocked = client.post(
            f"/api/v1/organizations/{ORG_ID}/imports/{preview.json()['id']}/commit",
            headers=headers,
            json={"dry_run": False},
        )
        assert blocked.status_code == 409
