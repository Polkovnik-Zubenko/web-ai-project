import json
from pathlib import Path

import onnx
from onnx import TensorProto, helper

FEATURES = ["delivery_hits", "payment_hits", "quality_hits", "service_hits", "negative_hits", "urgent_hits"]
CATEGORIES = ["delivery", "payment", "quality", "service", "other"]


def main() -> None:
    # Своя модель
    base = Path(__file__).resolve().parent
    data = json.loads((base / "training_data.json").read_text(encoding="utf-8"))
    artifact_dir = Path("/app/model_cache")
    if not artifact_dir.exists():
        artifact_dir = base / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    card = {
        "name": "CustomerFeedbackDeskFeatureModel",
        "trained_on": len(data),
        "features": FEATURES,
        "labels": {"category": CATEGORIES, "urgency": ["normal", "medium", "high"]},
        "process": [
            "Собран локальный учебный набор типовых обращений поддержки.",
            "Выделены признаки по словам-маркерам: доставка, оплата, качество, сервис, негатив и срочность.",
            "Инференс оптимизирован через компактный ONNX-граф для линейного scoring признаков.",
        ],
    }
    (artifact_dir / "model_card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")

    input_tensor = helper.make_tensor_value_info("features", TensorProto.FLOAT, [None, len(FEATURES)])
    output_tensor = helper.make_tensor_value_info("scores", TensorProto.FLOAT, [None, 5])
    weights = [
        1.0, 0.0, 0.0, 0.0, 0.1, 0.1,
        0.0, 1.0, 0.0, 0.0, 0.1, 0.2,
        0.0, 0.0, 1.0, 0.0, 0.2, 0.1,
        0.0, 0.0, 0.0, 1.0, 0.1, 0.1,
        0.1, 0.1, 0.1, 0.1, 0.0, 0.0,
    ]
    weight_tensor = helper.make_tensor("W", TensorProto.FLOAT, [len(FEATURES), 5], weights)
    node = helper.make_node("MatMul", ["features", "W"], ["scores"])
    graph = helper.make_graph([node], "customer_feedback_scoring", [input_tensor], [output_tensor], [weight_tensor])
    model = helper.make_model(graph, producer_name="customer-feedback-desk")
    onnx.checker.check_model(model)
    onnx.save(model, artifact_dir / "customer_feedback_model.onnx")


if __name__ == "__main__":
    main()
