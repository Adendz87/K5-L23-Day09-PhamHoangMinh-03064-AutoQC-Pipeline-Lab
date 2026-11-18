"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN  # noqa: F401


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    """Quyết định trạng thái dataset dựa trên lỗi và cảnh báo."""
    image_stems = set(image_stems)
    reviewed = set(reviewed)

    n_images = len(image_stems)

    # Lỗi ERROR luôn chặn pipeline, kể cả ảnh đã review.
    errors = [
        issue for issue in issues
        if issue.severity == ERROR
    ]
    n_errors = len(errors)

    # Chỉ đếm ảnh thuộc dataset, chưa được review và có ít nhất một WARN.
    warn_images = {
        issue.image
        for issue in issues
        if issue.severity == WARN
        and issue.image in image_stems
        and issue.image not in reviewed
    }

    n_warn_images = len(warn_images)
    warn_ratio = round(n_warn_images / n_images, 4) if n_images else 0.0

    threshold = cfg["gate"]["warn_ratio_hold"]

    if n_errors > 0:
        decision = "Rework"
        reasons = [
            f"Còn {n_errors} lỗi bắt buộc (ERROR), cần sửa lại dữ liệu."
        ]
    elif warn_ratio >= threshold:
        decision = "Hold"
        reasons = [
            f"Có {n_warn_images}/{n_images} ảnh còn cảnh báo "
            f"({warn_ratio:.2%}), đạt hoặc vượt ngưỡng "
            f"{threshold:.2%}; cần xem xét thêm."
        ]
    else:
        decision = "Release"
        reasons = [
            f"Không còn lỗi bắt buộc; có {n_warn_images}/{n_images} "
            f"ảnh còn cảnh báo ({warn_ratio:.2%}), thấp hơn ngưỡng "
            f"{threshold:.2%}."
        ]

    return {
        "decision": decision,
        "n_errors": n_errors,
        "n_warn_images": n_warn_images,
        "n_images": n_images,
        "warn_ratio": warn_ratio,
        "reasons": reasons,
    }
