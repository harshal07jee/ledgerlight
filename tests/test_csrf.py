"""
CSRF Protection and Cookie Security Tests (Requirement 8).

Verifies that:
1. Cookie-authenticated state-changing requests (POST, PUT, PATCH, DELETE) reject cross-origin requests (403 Forbidden).
2. Cookie-authenticated state-changing requests with matching/allowed Origin succeed.
3. Bearer token-authenticated requests succeed regardless of Origin header.
4. Session cookies are issued with SameSite=Strict and HttpOnly.
"""
import pytest
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api.database import SessionLocal
from apps.api.models import User, Organization, Membership
from apps.api.core.auth import create_session_token, hash_password


@pytest.fixture(scope="module")
def csrf_client():
    return TestClient(app)


@pytest.fixture(scope="module")
def csrf_user_and_cookie():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "csrf-test@ledgerlight.io").first()
        org = db.query(Organization).filter(Organization.name == "CSRF Test Corp").first()
        if not user or not org:
            if not org:
                org = Organization(name="CSRF Test Corp")
                db.add(org)
                db.flush()
            if not user:
                user = User(
                    email="csrf-test@ledgerlight.io",
                    hashed_password=hash_password("Password123!"),
                    full_name="CSRF Tester",
                    is_active=True,
                    is_admin=False
                )
                db.add(user)
                db.flush()
            membership = Membership(org_id=org.id, user_id=user.id, role="Owner")
            db.add(membership)
            db.commit()
            db.refresh(user)
            db.refresh(org)

        token = create_session_token(user.id, db)
        org_id = org.id
        return {"user_id": user.id, "org_id": org_id, "token": token}
    finally:
        db.close()


def test_login_sets_samesite_strict(csrf_client):
    """Assert login issues cookie with SameSite=Strict and HttpOnly."""
    resp = csrf_client.post("/auth/login", json={
        "email": "admin@ledgerlight.io",
        "password": "Password123!"
    })
    assert resp.status_code == 200
    cookie_header = resp.headers.get("set-cookie", "")
    assert "ledgerlight_session=" in cookie_header
    assert "samesite=strict" in cookie_header.lower()
    assert "httponly" in cookie_header.lower()


def test_csrf_blocks_cross_origin_cookie_mutation(csrf_client, csrf_user_and_cookie):
    """A cross-origin site attempting to POST with ambient session cookie is blocked with 403."""
    token = csrf_user_and_cookie["token"]
    org_id = csrf_user_and_cookie["org_id"]
    
    # Attacker site sends POST with cookie
    resp = csrf_client.post(
        f"/orgs/{org_id}/assessments",
        json={"name": "Malicious CSRF Assessment", "transaction_type": "VC_GROWTH_FINANCING", "industry": "SOFTWARE"},
        cookies={"ledgerlight_session": token},
        headers={"Origin": "https://evil-hacker-site.com"}
    )
    assert resp.status_code == 403
    data = resp.json()
    assert "CSRF verification failed" in data.get("detail", "")


def test_csrf_allows_same_origin_cookie_mutation(csrf_client, csrf_user_and_cookie):
    """Legitimate frontend Origin with session cookie is allowed through."""
    token = csrf_user_and_cookie["token"]
    org_id = csrf_user_and_cookie["org_id"]

    resp = csrf_client.post(
        f"/orgs/{org_id}/assessments",
        json={"name": "Legit Assessment Via Cookie", "transaction_type": "VC_GROWTH_FINANCING", "industry": "SOFTWARE"},
        cookies={"ledgerlight_session": token},
        headers={"Origin": "http://localhost:3000"}
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["assessment"]["name"] == "Legit Assessment Via Cookie"


def test_bearer_token_exempt_from_browser_csrf(csrf_client, csrf_user_and_cookie):
    """Bearer token headers (which cannot be sent cross-origin ambiently by browsers) succeed."""
    token = csrf_user_and_cookie["token"]
    org_id = csrf_user_and_cookie["org_id"]

    resp = csrf_client.post(
        f"/orgs/{org_id}/assessments",
        json={"name": "Legit Assessment Via Bearer", "transaction_type": "VC_GROWTH_FINANCING", "industry": "SOFTWARE"},
        headers={
            "Authorization": f"Bearer {token}",
            "Origin": "https://external-api-client.com"
        }
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["assessment"]["name"] == "Legit Assessment Via Bearer"
