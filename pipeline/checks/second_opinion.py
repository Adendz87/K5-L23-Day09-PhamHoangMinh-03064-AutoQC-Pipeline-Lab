"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds


def run(ds, cfg, preds=None):
    """So sánh nhãn YOLO với dự đoán model và trả về các cảnh báo."""
    thresholds = cfg["second_opinion"]

    conf_threshold = thresholds["conf"]
    min_area_px = thresholds["min_area_px"]
    fp_conf = thresholds["fp_conf"]
    iou_missing = thresholds["iou_missing"]
    iou_match = thresholds["iou_match"]
    iou_loose = thresholds["iou_loose"]

    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    issues = []

    # Duyệt theo thứ tự ảnh của dataset.
    for image_path in ds.image_files():
        stem = image_path.stem

        # Bỏ qua ảnh không có nhãn hoặc không có dự đoán.
        if not ds.label_path(stem).exists() or stem not in preds:
            continue

        image_size = ds.image_size(stem)
        if image_size is None:
            continue

        image_width, image_height = image_size

        # Đọc nhãn và giữ nguyên số dòng gốc.
        labels = []
        for line_no, raw_line in ds.read_label_lines(stem) or []:
            try:
                class_id, cx, cy, w, h = parse_yolo_line(raw_line)
            except (ValueError, OverflowError):
                continue

            if not 0 <= class_id < len(ds.classes):
                continue
            if w <= 0 or h <= 0:
                continue

            labels.append({
                "class_id": class_id,
                "box": (cx, cy, w, h),
                "line": line_no,
            })

        # Chuẩn hóa dự đoán và tách hai nhóm theo ngưỡng confidence.
        eligible_preds = []
        fp_preds = []

        for raw_pred in preds[stem]:
            try:
                class_id, conf, cx, cy, w, h = raw_pred
                class_id = int(class_id)
                conf = float(conf)
                box = (float(cx), float(cy), float(w), float(h))
            except (ValueError, TypeError, OverflowError):
                continue

            if not all(map(lambda v: v == v and abs(v) != float("inf"), box)):
                continue
            if conf != conf or abs(conf) == float("inf"):
                continue
            if w <= 0 or h <= 0:
                continue

            pred_item = {
                "class_id": class_id,
                "conf": conf,
                "box": box,
            }

            # Nhóm dùng để tìm missing / wrong class / loose box.
            area_px = w * image_width * h * image_height
            if conf >= conf_threshold and area_px >= min_area_px:
                eligible_preds.append(pred_item)

            # Nhóm dùng để tìm false positive: không lọc diện tích.
            if conf >= fp_conf:
                fp_preds.append(pred_item)

        # 1. So sánh từng dự đoán với nhãn.
        for pred in eligible_preds:
            pred_box = pred["box"]
            pred_class = pred["class_id"]

            candidates = []
            for label in labels:
                overlap = iou_xywh(pred_box, label["box"])
                if overlap >= iou_missing:
                    candidates.append((label, overlap))

            # Không có nhãn nào khớp đủ IoU.
            if not candidates:
                issues.append(Issue(
                    check="second_opinion",
                    severity=WARN,
                    code="POSSIBLE_MISSING",
                    image=stem,
                    message="Model phát hiện đối tượng chưa có box nhãn tương ứng.",
                    extra={"conf": pred["conf"]},
                ))
                continue

            same_class = [
                (label, overlap)
                for label, overlap in candidates
                if label["class_id"] == pred_class
            ]

            other_class = [
                (label, overlap)
                for label, overlap in candidates
                if label["class_id"] != pred_class
            ]

            # Ưu tiên nhãn cùng class nếu có.
            if same_class:
                best_iou = max(overlap for _, overlap in same_class)

                if best_iou < iou_loose:
                    issues.append(Issue(
                        check="second_opinion",
                        severity=WARN,
                        code="POSSIBLE_LOOSE_BOX",
                        image=stem,
                        message="Box nhãn cùng class có thể quá rộng hoặc lệch so với dự đoán.",
                        extra={"conf": pred["conf"], "iou": best_iou},
                    ))
                continue

            # Không có nhãn cùng class: chỉ báo nhầm class khi IoU đủ cao.
            if other_class:
                best_iou = max(overlap for _, overlap in other_class)

                if best_iou >= iou_match:
                    issues.append(Issue(
                        check="second_opinion",
                        severity=WARN,
                        code="POSSIBLE_WRONG_CLASS",
                        image=stem,
                        message="Class của nhãn có thể khác với dự đoán của model.",
                        extra={"conf": pred["conf"], "iou": best_iou},
                    ))

        # 2. Tìm nhãn có thể là false positive.
        # Dùng mọi dự đoán conf >= fp_conf, không lọc diện tích.
        for label in labels:
            overlaps = [
                iou_xywh(label["box"], pred["box"])
                for pred in fp_preds
            ]

            best_iou = max(overlaps, default=0.0)

            if best_iou < iou_missing:
                issues.append(Issue(
                    check="second_opinion",
                    severity=WARN,
                    code="POSSIBLE_FALSE_POS",
                    image=stem,
                    line=label["line"],
                    message="Box nhãn không khớp với dự đoán nào của model.",
                    extra={"iou": best_iou},
                ))

    return issues
