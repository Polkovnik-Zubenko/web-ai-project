import os
import time

import altair as alt
import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000/api").rstrip("/")

st.set_page_config(page_title="AI Text Service", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background: #f7f8fb; color: #17202a; }
    .metric-box { padding: 12px 14px; border: 1px solid #d9dee8; border-radius: 8px; background: white; }
    .status-ok { color: #176b3a; font-weight: 700; }
    .status-bad { color: #a13b32; font-weight: 700; }
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


st.title("AI Text Service")

status_col, action_col = st.columns([3, 1])
try:
    health = api_get("/health")
    status_col.markdown(
        f"Статус: <span class='status-ok'>{health['status']}</span> · DB {health['database']} · Redis {health['redis']} · Model {health['model']}",
        unsafe_allow_html=True,
    )
except requests.RequestException:
    status_col.error("Сервис временно недоступен. Попробуйте обновить страницу позже.")
    health = None

with action_col:
    refresh = st.button("Обновить", use_container_width=True)
    if refresh:
        st.rerun()

left, right = st.columns([1.2, 1])

with left:
    text = st.text_area(
        "Текст для анализа",
        value="FastAPI помогает быстро собрать понятный сервис, а аккуратный интерфейс делает результат удобным для пользователя.",
        height=190,
        max_chars=4000,
    )
    creativity = st.slider("Креативность рекомендаций", 0.0, 1.0, 0.3, 0.05)
    max_tokens = st.slider("Максимальная длина ответа", 32, 1024, 160, 16)
    submitted = st.button("Проанализировать", type="primary", use_container_width=True, disabled=health is None)

with right:
    st.subheader("Результат")
    if submitted:
        progress = st.progress(0)
        try:
            # UX асинхронности
            for value in (20, 45, 70):
                progress.progress(value)
                time.sleep(0.12)
            result = api_post("/analyze", {"text": text, "creativity": creativity, "max_tokens": max_tokens})
            progress.progress(100)
            st.success("Анализ готов")
            st.metric("Тональность", result["sentiment"], f"{result['score']:+.2f}")
            st.write(result["summary"])
            st.write("Рекомендации")
            for item in result["recommendations"]:
                st.write(f"- {item}")
            metrics = result["metrics"]
            chart_data = pd.DataFrame(
                [
                    {"metric": "Символы", "value": metrics["characters"]},
                    {"metric": "Слова", "value": metrics["words"]},
                    {"metric": "Предложения", "value": metrics["sentences"]},
                    {"metric": "Читабельность", "value": metrics["readability_score"]},
                ]
            )
            chart = alt.Chart(chart_data).mark_bar(color="#3478f6").encode(
                x=alt.X("metric:N", title=""),
                y=alt.Y("value:Q", title="Значение"),
                tooltip=["metric", "value"],
            )
            st.altair_chart(chart, use_container_width=True)
        except requests.HTTPError as exc:
            try:
                detail = exc.response.json().get("detail", "Не удалось выполнить анализ.")
            except ValueError:
                detail = "Не удалось выполнить анализ."
            st.error(detail)
        except requests.RequestException:
            st.error("Сервис временно недоступен.")
        finally:
            progress.empty()
    else:
        st.info("Введите текст и запустите анализ.")

st.divider()

history_col, clear_col = st.columns([4, 1])
history_col.subheader("История анализов")
if clear_col.button("Очистить", use_container_width=True):
    try:
        api_delete("/analyses")
        st.rerun()
    except requests.RequestException:
        st.error("Не удалось очистить историю.")

try:
    history = api_get("/analyses", limit=10)
    if history:
        rows = [
            {
                "ID": item["id"],
                "Тон": item["sentiment"],
                "Оценка": item["score"],
                "Слова": item["metrics"].get("words"),
                "Читабельность": item["metrics"].get("readability_score"),
                "Время": item["created_at"],
            }
            for item in history
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.caption("История пока пустая.")
except requests.RequestException:
    st.warning("История недоступна, но интерфейс продолжает работать.")
