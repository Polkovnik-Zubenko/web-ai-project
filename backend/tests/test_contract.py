from app.main import app
from app.schemas import LoginRequest, TicketRequest


def test_openapi_contains_core_business_endpoints():
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/auth/login" in paths
    assert "/api/auth/register" in paths
    assert "/api/tickets" in paths
    assert "/api/tasks/{task_id}" in paths
    assert "/api/health" in paths


def test_ticket_schema_accepts_business_payload():
    payload = TicketRequest(
        customer_name="Анна",
        channel="chat",
        text="Курьер опоздал, поддержка не отвечает. Срочно верните деньги.",
        creativity=0.3,
        max_tokens=160,
    )
    assert payload.channel == "chat"


def test_login_schema_accepts_email_and_password():
    payload = LoginRequest(email="manager@example.com", password="manager123")
    assert payload.email == "manager@example.com"
