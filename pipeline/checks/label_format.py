"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line


def run(ds, cfg):
    """Kiểm tra các file nhãn YOLO và trả về danh sách Issue."""
    thresholds = cfg["label_format"]
    overflow_tol = thresholds["overflow_tol"]
    min_box_px = thresholds["min_box_px"]
    max_box_frac = thresholds["max_box_frac"]
    dup_box_iou = thresholds["dup_box_iou"]

    issues = []

    for label_path in ds.label_files():
        stem = label_path.stem
        lines = ds.read_label_lines(stem) or []
        image_size = ds.image_size(stem)
        previous_boxes = []

        for line_no, raw_line in lines:
            # 1. Kiểm tra cú pháp YOLO
            try:
                class_id, cx, cy, w, h = parse_yolo_line(raw_line)
            except (ValueError, OverflowError):
                issues.append(Issue(
                    check="label_format",
                    severity=ERROR,
                    code="BAD_FORMAT",
                    image=stem,
                    line=line_no,
                    message="Dòng nhãn không đúng định dạng YOLO gồm 5 giá trị hợp lệ.",
                ))
                continue

            # 2. Kiểm tra class ID
            if not 0 <= class_id < len(ds.classes):
                issues.append(Issue(
                    check="label_format",
                    severity=ERROR,
                    code="BAD_CLASS_ID",
                    image=stem,
                    line=line_no,
                    message=f"Class ID {class_id} nằm ngoài danh sách lớp hợp lệ.",
                ))
                continue

            # 3. Kiểm tra box rỗng
            if w <= 0 or h <= 0:
                issues.append(Issue(
                    check="label_format",
                    severity=ERROR,
                    code="BOX_ZERO",
                    image=stem,
                    line=line_no,
                    message="Chiều rộng hoặc chiều cao của box phải lớn hơn 0.",
                ))
                continue

            box = (cx, cy, w, h)

            # 4. Kiểm tra box tràn khỏi ảnh
            left = cx - w / 2
            right = cx + w / 2
            top = cy - h / 2
            bottom = cy + h / 2

            overflow = max(
                0.0,
                -left,
                -top,
                right - 1.0,
                bottom - 1.0,
            )

            if overflow > overflow_tol:
                issues.append(Issue(
                    check="label_format",
                    severity=ERROR,
                    code="BOX_OUT_OF_IMAGE",
                    image=stem,
                    line=line_no,
                    message="Box vượt ra ngoài biên ảnh.",
                    extra={"overflow": overflow},
                ))

            # 5. Kiểm tra box trùng với box trước đó cùng class
            for previous_class, previous_box in previous_boxes:
                if (
                    class_id == previous_class
                    and iou_xywh(box, previous_box) > dup_box_iou
                ):
                    issues.append(Issue(
                        check="label_format",
                        severity=ERROR,
                        code="DUP_BOX",
                        image=stem,
                        line=line_no,
                        message="Box trùng với một box trước đó cùng class.",
                    ))
                    break

            previous_boxes.append((class_id, box))

            # 6. Kiểm tra box quá nhỏ (tính theo pixel)
            if image_size is not None:
                image_width, image_height = image_size
                short_side_px = min(w * image_width, h * image_height)

                if short_side_px < min_box_px:
                    issues.append(Issue(
                        check="label_format",
                        severity=WARN,
                        code="BOX_TINY",
                        image=stem,
                        line=line_no,
                        message="Cạnh ngắn của box nhỏ hơn ngưỡng pixel cho phép.",
                    ))

            # 7. Kiểm tra box chiếm diện tích quá lớn
            if w * h > max_box_frac:
                issues.append(Issue(
                    check="label_format",
                    severity=WARN,
                    code="BOX_HUGE",
                    image=stem,
                    line=line_no,
                    message="Diện tích box vượt ngưỡng cho phép.",
                ))

    return issues
