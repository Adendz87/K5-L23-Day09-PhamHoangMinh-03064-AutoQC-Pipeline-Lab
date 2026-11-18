"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


DROP_CODES = {
    "BAD_FORMAT",
    "BAD_CLASS_ID",
    "BOX_ZERO",
    "DUP_BOX",
}

REMOVE_PREFIXES = (
    "DUP_IMAGE_",
)

REMOVE_CODES = {
    "LEAK_TEST",
    "CORRUPT_IMAGE",
    "BAD_SIZE",
}


def _fix_record(image, line, action, before, after):
    return {
        "image": image,
        "line": line,
        "action": action,
        "before": before,
        "after": after,
    }


def _format_number(value):
    """Định dạng số gọn, tránh ghi nhiều chữ số thập phân không cần thiết."""
    return f"{value:.10f}".rstrip("0").rstrip(".") or "0"


def _clip_line(raw_line):
    """Cắt box vào ảnh. Trả về None nếu box không còn diện tích."""
    class_id, cx, cy, w, h = parse_yolo_line(raw_line)

    left = max(0.0, cx - w / 2)
    top = max(0.0, cy - h / 2)
    right = min(1.0, cx + w / 2)
    bottom = min(1.0, cy + h / 2)

    if right <= left or bottom <= top:
        return None

    new_w = right - left
    new_h = bottom - top
    new_cx = (left + right) / 2
    new_cy = (top + bottom) / 2

    return " ".join(_format_number(v) for v in (
        class_id, new_cx, new_cy, new_w, new_h
    ))


def fix(ds, issues, cfg):
    """Sửa các lỗi ERROR an toàn và trả về danh sách thay đổi."""
    fixes = []

    errors = [issue for issue in issues if issue.severity == ERROR]

    # Tập hợp ảnh cần xóa trước để không xử lý tiếp các issue của chúng.
    removed_images = {
        issue.image
        for issue in errors
        if issue.code in REMOVE_CODES
        or issue.code.startswith(REMOVE_PREFIXES)
    }

    # 1. Xóa ảnh và nhãn tương ứng.
    for stem in sorted(removed_images):
        image_path = ds.image_path(stem)
        label_path = ds.label_path(stem)

        if image_path is None and not label_path.exists():
            continue

        before = []
        if image_path is not None:
            before.append(image_path.name)
        if label_path.exists():
            before.append(label_path.name)

        if image_path is not None:
            image_path.unlink()
        if label_path.exists():
            label_path.unlink()

        fixes.append(_fix_record(
            stem, None, "remove_image",
            ", ".join(before),
            "đã xóa ảnh và nhãn",
        ))

    # 2. Sửa tên lớp trong data.yaml.
    rename_issues = [
        issue for issue in errors
        if issue.code == "BAD_CLASS_NAME"
    ]

    if rename_issues and ds.yaml_path.exists():
        data = yaml.safe_load(
            ds.yaml_path.read_text(encoding="utf-8")
        ) or {}

        before = data.get("names")
        data["names"] = list(cfg["classes"])

        ds.yaml_path.write_text(
            yaml.safe_dump(
                data,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        fixes.append(_fix_record(
            "data.yaml", None, "rename_classes",
            str(before),
            str(data["names"]),
        ))

    # 3. Ảnh chưa có nhãn: chuyển cho người, tuyệt đối không tạo file.
    missing_stems = {
        issue.image
        for issue in errors
        if issue.code == "MISSING_LABEL_FILE"
        and issue.image not in removed_images
    }

    for stem in sorted(missing_stems):
        if not ds.label_path(stem).exists():
            fixes.append(_fix_record(
                stem, None, "needs_label",
                "(không có file)",
                "chuyển người gán",
            ))

    # 4. Gom các lỗi dòng theo file và số dòng gốc.
    line_issues = defaultdict(list)

    for issue in errors:
        if issue.image in removed_images:
            continue

        if issue.code in DROP_CODES or issue.code == "BOX_OUT_OF_IMAGE":
            if issue.line is not None:
                line_issues[issue.image].append(issue)

    for stem in sorted(line_issues):
        label_path = ds.label_path(stem)

        if not label_path.exists():
            continue

        original_lines = label_path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()

        issues_by_line = defaultdict(list)
        for issue in line_issues[stem]:
            issues_by_line[issue.line].append(issue)

        new_lines = []
        changed = False

        for line_no, raw_line in enumerate(original_lines, start=1):
            current_issues = issues_by_line.get(line_no, [])

            if not current_issues:
                new_lines.append(raw_line)
                continue

            codes = {issue.code for issue in current_issues}

            # Ưu tiên xóa nếu dòng có bất kỳ lỗi bắt buộc phải xóa nào.
            if codes & DROP_CODES:
                fixes.append(_fix_record(
                    stem, line_no, "drop_line",
                    raw_line, "",
                ))
                changed = True
                continue

            # Chỉ clip nếu dòng không có lỗi cần xóa.
            if "BOX_OUT_OF_IMAGE" in codes:
                try:
                    clipped = _clip_line(raw_line)
                except (ValueError, OverflowError):
                    clipped = None

                if clipped is None:
                    fixes.append(_fix_record(
                        stem, line_no, "drop_line",
                        raw_line, "",
                    ))
                else:
                    fixes.append(_fix_record(
                        stem, line_no, "clip_box",
                        raw_line, clipped,
                    ))
                    new_lines.append(clipped)

                changed = True
                continue

            new_lines.append(raw_line)

        if changed:
            label_path.write_text(
                "\n".join(new_lines) + ("\n" if new_lines else ""),
                encoding="utf-8",
            )

    return fixes
