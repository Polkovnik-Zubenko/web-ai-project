import os
import time
from datetime import datetime

import altair as alt
import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000/api").rstrip("/")

DEMO_USERS = {
    "manager@example.com": {
        "password": "manager123",
        "name": "Анна Смирнова",
        "role": "Менеджер поддержки",
        "company": "Northwind Retail",
    },
    "admin@example.com": {
        "password": "admin123",
        "name": "Саша Зубенко",
        "role": "Руководитель поддержки",
        "company": "Northwind Retail",
    },
}

st.set_page_config(page_title="Customer Feedback Desk", layout="wide")

st.markdown(
    """
    <style>
    :root {
      --bg: #111827;
      --panel: #172033;
      --panel-2: #1f2a44;
      --text: #eef2ff;
      --muted: #a8b3cf;
      --line: #2f3b57;
      --accent: #60a5fa;
      --green: #34d399;
      --amber: #fbbf24;
      --red: #fb7185;
    }
    .stApp { background: var(--bg); color: var(--text); }
    .block-container { padding-top: 1.25rem; max-width: 1280px; }
    h1, h2, h3, label, .stMarkdown, .stText, p, span { color: var(--text) !important; }
    .stCaption, caption, [data-testid="stCaptionContainer"] { color: var(--muted) !important; }
    section[data-testid="stSidebar"] { background: #0b1220; border-right: 1px solid var(--line); }
    section[data-testid="stSidebar"] * { color: var(--text) !important; }
    div[data-testid="stTextInput"] input,
    div[data-testid="stTextArea"] textarea,
    div[data-baseweb="select"] > div {
      background: #0f172a !important;
      color: var(--text) !important;
      border: 1px solid #3b4968 !important;
      border-radius: 8px !important;
    }
    div[data-testid="stTextArea"] textarea { min-height: 150px; }
    .stButton > button {
      background: #2563eb;
      color: white;
      border: 0;
      border-radius: 8px;
      font-weight: 700;
    }
    .stButton > button:hover { background: #1d4ed8; color: white; }
    [data-testid="stMetric"] {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-height: 112px;
    }
    [data-testid="stMetric"] * { color: var(--text) !important; }
    div[data-testid="stAlert"] {
      background: #12243a;
      border: 1px solid #315a86;
      color: var(--text);
    }
    .desk-card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px 18px;
      margin-bottom: 14px;
    }
    .desk-card strong { color: white; }
    .desk-muted { color: var(--muted); }
    .desk-badge {
      display: inline-block;
      padding: 4px 8px;
      border-radius: 999px;
      background: #22304d;
      border: 1px solid #3b4968;
      color: var(--text);
      font-size: 12px;
      margin-right: 6px;
    }
    .desk-hero {
      background: linear-gradient(135deg, #172033 0%, #111827 70%);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 16px;
    }
    .stDataFrame, div[data-testid="stTable"] { color: var(--text); }
    </style>
    """,
    unsafe_allow_html=True,
)


def api_get(path: str, **params):
    response = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=8)
    response.raise_for_status()
    return response.json()


def api_post(path: str, payload: dict):
    response = requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def api_delete(path: str):
    response = requests.delete(f"{API_BASE_URL}{path}", timeout=8)
    response.raise_for_status()


def init_state():
    st.session_state.setdefault("authenticated", False)
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("page", "Кабинет")


def sign_in(email: str, password: str) -> bool:
    user = DEMO_USERS.get(email.strip().lower())
    if user and user["password"] == password:
        st.session_state.authenticated = True
        st.session_state.user = {"email": email.strip().lower(), **user}
        return True
    return False


def poll_task(task_id: str):
    progress = st.progress(0)
    status_box = st.empty()
    for _ in range(45):
        status = api_get(f"/tasks/{task_id}")
        progress.progress(status["progress"])
        status_box.caption(f"Статус задачи: {status['state']} · этап: {status['stage']}")
        if status["state"] == "SUCCESS":
            progress.progress(100)
            return status
        if status["state"] in {"FAILURE", "REVOKED"}:
            raise RuntimeError("Задача завершилась с ошибкой.")
        time.sleep(1)
    raise TimeoutError("Анализ занимает больше обычного. Проверьте историю через несколько секунд.")


def load_history(limit: int = 50) -> list[dict]:
    try:
        return api_get("/analyses", limit=limit)
    except requests.RequestException:
        st.warning("История временно недоступна.")
        return []


def history_frame(history: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ID": item["id"],
                "Клиент": item["customer_name"],
                "Канал": item["channel"],
                "Тон": item["sentiment"],
                "Категория": item["category"],
                "Срочность": item["urgency"],
                "Оценка": item["score"],
                "Слова": item["metrics"].get("words"),
                "Время": item["created_at"],
            }
            for item in history
        ]
    )


def render_login():
    left, right = st.columns([0.9, 1.1])
    with left:
        st.markdown(
            """
            <div class="desk-hero">
              <h1>Customer Feedback Desk</h1>
              <p class="desk-muted">Личный кабинет поддержки для разбора входящих сообщений клиентов.</p>
              <span class="desk-badge">Очередь обращений</span>
              <span class="desk-badge">AI приоритизация</span>
              <span class="desk-badge">Черновик ответа</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class="desk-card">
              <strong>Демо-доступ</strong><br>
              <span class="desk-muted">manager@example.com / manager123</span><br>
              <span class="desk-muted">admin@example.com / admin123</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.subheader("Вход по почте и паролю")
        email = st.text_input("Почта", value="manager@example.com")
        password = st.text_input("Пароль", value="manager123", type="password")
        if st.button("Войти", type="primary", use_container_width=True):
            if sign_in(email, password):
                st.rerun()
            st.error("Неверная почта или пароль.")


def render_sidebar():
    user = st.session_state.user
    st.sidebar.title("Feedback Desk")
    st.sidebar.caption(f"{user['company']}")
    st.sidebar.markdown(f"**{user['name']}**")
    st.sidebar.caption(f"{user['role']} · {user['email']}")
    st.sidebar.divider()
    st.session_state.page = st.sidebar.radio(
        "Раздел",
        ["Кабинет", "Новое обращение", "Обращения", "Аналитика", "Настройки"],
        index=["Кабинет", "Новое обращение", "Обращения", "Аналитика", "Настройки"].index(st.session_state.page),
    )
    st.sidebar.divider()
    if st.sidebar.button("Выйти", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user = None
        st.rerun()


def render_header():
    st.markdown(
        f"""
        <div class="desk-hero">
          <h1>{st.session_state.page}</h1>
          <p class="desk-muted">Сегодня: {datetime.now().strftime('%d.%m.%Y')} · рабочий кабинет клиентской поддержки</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard():
    render_header()
    try:
        health = api_get("/health")
        st.success(f"Сервис готов: DB {health['database']}, Redis {health['redis']}, Model {health['model']}")
    except requests.RequestException:
        st.error("Сервис временно недоступен.")
    history = load_history(50)
    total = len(history)
    high = sum(item["urgency"] == "high" for item in history)
    negative = sum(item["sentiment"] == "negative" for item in history)
    categories = {item["category"] for item in history}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Всего обращений", total)
    c2.metric("Высокий приоритет", high)
    c3.metric("Негатив", negative)
    c4.metric("Категории", len(categories))
    if history:
        st.subheader("Последние обращения")
        st.dataframe(history_frame(history[:8]), use_container_width=True, hide_index=True)


def render_new_ticket():
    render_header()
    try:
        health = api_get("/health")
    except requests.RequestException:
        health = None
        st.error("Сервис временно недоступен.")
    form_col, result_col = st.columns([1.05, 1])
    with form_col:
        st.subheader("Карточка обращения")
        customer_name = st.text_input("Клиент", value="Анна")
        channel = st.selectbox("Канал", ["web", "email", "chat", "marketplace", "phone"], index=2)
        text = st.text_area(
            "Сообщение клиента",
            value="Курьер опоздал на два дня, поддержка не отвечает. Срочно верните деньги или решите вопрос сегодня.",
            height=210,
            max_chars=4000,
        )
        creativity = st.slider("Свобода формулировки ответа", 0.0, 1.0, 0.35, 0.05)
        max_tokens = st.slider("Максимальная длина анализа", 32, 1024, 160, 16)
        submitted = st.button("Разобрать обращение", type="primary", use_container_width=True, disabled=health is None)
    with result_col:
        st.subheader("AI-разбор")
        if not submitted:
            st.info("Заполните обращение и запустите анализ.")
            return
        try:
            created = api_post(
                "/tickets",
                {
                    "customer_name": customer_name,
                    "channel": channel,
                    "text": text,
                    "creativity": creativity,
                    "max_tokens": max_tokens,
                },
            )
            status = poll_task(created["task_id"])
            st.success(f"Задача готова, обращение #{status['ticket_id']}")
            item = api_get("/analyses", limit=1)[0]
            m1, m2, m3 = st.columns(3)
            m1.metric("Тон", item["sentiment"], f"{item['score']:+.2f}")
            m2.metric("Категория", item["category"])
            m3.metric("Срочность", item["urgency"])
            st.write(item["summary"])
            st.text_area("Черновик ответа", value=item["suggested_reply"], height=120)
            for recommendation in item["metrics"].get("recommendations", []):
                st.write(f"- {recommendation}")
        except requests.HTTPError as exc:
            detail = "Не удалось обработать обращение."
            try:
                detail = exc.response.json().get("detail", detail)
            except ValueError:
                pass
            st.error(detail)
        except (requests.RequestException, RuntimeError, TimeoutError) as exc:
            st.error(str(exc) or "Сервис временно недоступен.")


def render_tickets():
    render_header()
    history = load_history(100)
    if st.button("Очистить историю", use_container_width=False):
        try:
            api_delete("/analyses")
            st.rerun()
        except requests.RequestException:
            st.error("Не удалось очистить историю.")
    if history:
        st.dataframe(history_frame(history), use_container_width=True, hide_index=True)
    else:
        st.caption("Обращений пока нет.")


def render_analytics():
    render_header()
    history = load_history(100)
    if not history:
        st.caption("Недостаточно данных для аналитики.")
        return
    df = history_frame(history)
    c1, c2 = st.columns(2)
    with c1:
        chart = alt.Chart(df).mark_bar(color="#60a5fa").encode(
            x=alt.X("Тон:N", title="Тональность", axis=alt.Axis(labelColor="#eef2ff", titleColor="#eef2ff")),
            y=alt.Y("count():Q", title="Количество", axis=alt.Axis(labelColor="#eef2ff", titleColor="#eef2ff")),
            tooltip=["Тон", "count()"],
        ).properties(background="#172033")
        st.altair_chart(chart, use_container_width=True)
    with c2:
        chart = alt.Chart(df).mark_bar(color="#34d399").encode(
            x=alt.X("Категория:N", title="Категория", axis=alt.Axis(labelColor="#eef2ff", titleColor="#eef2ff")),
            y=alt.Y("count():Q", title="Количество", axis=alt.Axis(labelColor="#eef2ff", titleColor="#eef2ff")),
            tooltip=["Категория", "count()"],
        ).properties(background="#172033")
        st.altair_chart(chart, use_container_width=True)
    st.markdown(
        '<div class="desk-card"><strong>Grafana</strong><br><span class="desk-muted">Мониторинг API доступен по адресу /grafana/ после пересборки compose.</span></div>',
        unsafe_allow_html=True,
    )


def render_settings():
    render_header()
    user = st.session_state.user
    left, right = st.columns(2)
    with left:
        st.subheader("Профиль")
        st.text_input("Имя", value=user["name"])
        st.text_input("Почта", value=user["email"], disabled=True)
        st.text_input("Роль", value=user["role"])
        st.text_input("Компания", value=user["company"])
        st.button("Сохранить профиль", use_container_width=True)
    with right:
        st.subheader("Правила обработки")
        st.selectbox("SLA для высокого приоритета", ["15 минут", "30 минут", "1 час"], index=1)
        st.checkbox("Автоматически помечать негатив как приоритет", value=True)
        st.checkbox("Показывать черновик ответа после анализа", value=True)
        st.button("Сохранить настройки", use_container_width=True)


init_state()
if not st.session_state.authenticated:
    render_login()
else:
    render_sidebar()
    pages = {
        "Кабинет": render_dashboard,
        "Новое обращение": render_new_ticket,
        "Обращения": render_tickets,
        "Аналитика": render_analytics,
        "Настройки": render_settings,
    }
    pages[st.session_state.page]()
