import os
import time

import altair as alt
import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000/api").rstrip("/")

st.set_page_config(page_title="Customer Feedback Desk", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background: #f5f7fa; color: #17202a; }
    [data-testid="stMetric"] { background: white; border: 1px solid #dce2eb; padding: 12px; border-radius: 8px; }
    .block-container { padding-top: 1.4rem; }
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


st.title("Customer Feedback Desk")
st.caption("Рабочий кабинет для разбора клиентских обращений: приоритет, категория, тональность и черновик ответа.")

try:
    health = api_get("/health")
    st.success(f"Сервис готов: DB {health['database']}, Redis {health['redis']}, Model {health['model']}")
except requests.RequestException:
    health = None
    st.error("Сервис временно недоступен.")

form_col, result_col = st.columns([1.05, 1])

with form_col:
    st.subheader("Новое обращение")
    customer_name = st.text_input("Клиент", value="Анна")
    channel = st.selectbox("Канал", ["web", "email", "chat", "marketplace", "phone"], index=2)
    text = st.text_area(
        "Сообщение клиента",
        value="Курьер опоздал на два дня, поддержка не отвечает. Срочно верните деньги или решите вопрос сегодня.",
        height=190,
        max_chars=4000,
    )
    creativity = st.slider("Свобода формулировки ответа", 0.0, 1.0, 0.35, 0.05)
    max_tokens = st.slider("Максимальная длина анализа", 32, 1024, 160, 16)
    submitted = st.button("Разобрать обращение", type="primary", use_container_width=True, disabled=health is None)

with result_col:
    st.subheader("Результат")
    if submitted:
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
            history = api_get("/analyses", limit=1)
            item = history[0]
            m1, m2, m3 = st.columns(3)
            m1.metric("Тон", item["sentiment"], f"{item['score']:+.2f}")
            m2.metric("Категория", item["category"])
            m3.metric("Срочность", item["urgency"])
            st.write(item["summary"])
            st.text_area("Черновик ответа", value=item["suggested_reply"], height=100)
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
    else:
        st.info("Заполните обращение, чтобы получить приоритет, категорию и черновик ответа.")

st.divider()
history_title, clear_col = st.columns([4, 1])
history_title.subheader("Очередь и аналитика")
if clear_col.button("Очистить историю", use_container_width=True):
    try:
        api_delete("/analyses")
        st.rerun()
    except requests.RequestException:
        st.error("Не удалось очистить историю.")

try:
    history = api_get("/analyses", limit=50)
except requests.RequestException:
    history = []
    st.warning("История временно недоступна.")

if history:
    df = pd.DataFrame(
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
    c1, c2 = st.columns(2)
    with c1:
        sentiment_chart = alt.Chart(df).mark_bar(color="#2f6fed").encode(
            x=alt.X("Тон:N", title="Тональность"),
            y=alt.Y("count():Q", title="Количество"),
            tooltip=["Тон", "count()"],
        )
        st.altair_chart(sentiment_chart, use_container_width=True)
    with c2:
        category_chart = alt.Chart(df).mark_bar(color="#20a67a").encode(
            x=alt.X("Категория:N", title="Категория"),
            y=alt.Y("count():Q", title="Количество"),
            tooltip=["Категория", "count()"],
        )
        st.altair_chart(category_chart, use_container_width=True)
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.caption("Обращений пока нет.")
