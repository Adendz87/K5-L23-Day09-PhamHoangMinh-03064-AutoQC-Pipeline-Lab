# Calibration: đo chính công cụ kiểm

Slide Day 09: *“Script bắt đủ lỗi đã chèn thì mới đáng tin trên dữ liệu thật.”* Kiểm tra công cụ trước khi tin báo cáo của nó.

## Bộ `data/calib/`

- 30 ảnh nhãn **người** (sạch) + 9 ảnh trùng thêm vào (3 trùng byte, 6 gần trùng, mức biến đổi tăng dần).
- Đã **chèn lỗi cố ý** ở vị trí biết trước; `data/calib/MANIFEST.csv` ghi `type, image, line, detail`.
- Khác bộ `raw`: raw **không có đáp án** (đúng như dữ liệu thật).

## Cách chấm (`pipeline/calibrate.py`)

| Khái niệm | Nghĩa |
|---|---|
| TP | Cờ đúng chỗ có lỗi chèn |
| FP | Cờ chỗ **không** có lỗi chèn loại đó (báo động giả: người kiểm phải mở xem uổng công) |
| FN | Lỗi chèn mà không cờ (**bỏ sót**: lỗi lọt vào dataset) |
| precision = TP/(TP+FP) | Cờ có đáng tin không |
| recall = TP/(TP+FN) | Bắt được bao nhiêu lỗi |

Lỗi cú pháp so theo (ảnh, **dòng**); lỗi khác so theo ảnh. Ảnh sạch cũng có thể có lệch tự nhiên giữa model và nhãn người — vẫn tính FP, vì đó đúng là báo động giả bạn sẽ gặp.

## Đọc bảng sweep

Mỗi ô có dạng `precision / recall / F1`.

Với `second_opinion.conf`:

| Giá trị | WRONG_CLASS (P/R/F1) | MISSING (P/R/F1) |
|---|---|---|
| 0.25 | 0.56 / 0.83 / 0.67 | 0.50 / 1.00 / 0.67 |
| 0.80 | 1.00 / 0.83 / 0.91 | 0.67 / 0.75 / 0.71 |

Tăng `conf` làm checker chỉ giữ lại các dự đoán có độ tin cậy cao hơn. Trong kết quả này, WRONG_CLASS tăng precision từ 0.56 lên 1.00 trong khi recall giữ ở 0.83. Với MISSING, precision tăng từ 0.50 lên 0.67 nhưng recall giảm từ 1.00 xuống 0.75. Như vậy, cảnh báo đáng tin hơn nhưng có thể bỏ sót nhiều lỗi hơn.

## Chọn ngưỡng thế nào

- **Lỗi bắt buộc tự sửa/loại** (`phash_dist`): ưu tiên **precision cao** — cờ sai nghĩa là xóa nhầm ảnh/box tốt. Chọn `phash_dist = 16` vì DUP_IMAGE_EXACT đạt precision 1.00, recall 1.00; DUP_IMAGE_NEAR đạt precision 1.00, recall 0.83 và F1 0.91. Đây là kết quả tốt nhất trong sweep. Ở ngưỡng 20, recall của DUP_IMAGE_EXACT giảm còn 0.33 và DUP_IMAGE_NEAR giảm còn 0.50.

- **Cảnh báo cho người** (`second_opinion.conf`): chấp nhận precision thấp hơn để recall cao, nhưng **hàng đợi lớn hơn ngân sách duyệt (80 ảnh) thì phần dư không ai xem**. Chọn `conf = 0.8` để ưu tiên độ tin cậy của cảnh báo WRONG_CLASS (precision 1.00, recall 0.83). Tuy nhiên, MISSING chỉ đạt recall 0.75 và LOOSE_BOX chỉ đạt recall 0.20, nên vẫn có nguy cơ bỏ sót. Trong lần chạy pipeline, đã duyệt 80 ảnh; sau vòng kiểm tra cuối còn 13/193 ảnh có cảnh báo (6.74%), thấp hơn ngưỡng Hold 10%. Không được hạ recall chỉ để hàng đợi vừa ngân sách: một hàng đợi nhỏ vì checker mù là Release giả.

- Đừng chỉ chọn "F1 lớn nhất": cần hỏi **giá của một FP** và **giá của một FN** trong dự án này. FP làm người kiểm tra tốn thời gian xác minh cảnh báo giả; FN khiến lỗi thật lọt vào dataset. Với lỗi tự động loại ảnh, FP đặc biệt nguy hiểm vì có thể xóa nhầm dữ liệu tốt. Với cảnh báo ngữ nghĩa, FN cũng nguy hiểm vì lỗi nhãn có thể không được người kiểm tra phát hiện.

## Hạn chế cần nhớ

1. Calibration chỉ có 39 ảnh: ô nào chỉ có 2–5 lỗi chèn thì precision/recall nhảy từng bước 20–50%.

2. Lỗi chèn là **lỗi dễ hình dung**. Lỗi thật hiếm khi sạch sẽ như vậy.

3. Ngưỡng tối ưu cho calibration chưa chắc tối ưu cho raw. **Luôn mở xem** vài kết quả trên raw (`viz_labels.py`), đặc biệt các cặp ảnh bị cho là trùng để tránh xóa nhầm ảnh hợp lệ.

4. Lỗi chèn trong calibration **không giống hệt** lỗi tự nhiên trong raw: calibration dựng từ nhãn người (sạch), raw từ nhãn model; các lỗi `WRONG_CLASS` trong calibration chủ yếu là person → car, còn raw nghiêng về car/truck/bus; calibration **không có** ca `LEAK_TEST`. Đừng tin recall trên calibration như recall trên raw.

5. Có lỗi mà không ngưỡng nào bắt được (ví dụ ảnh bị cắt 80% rồi thu nhỏ): ghi vào báo cáo như một **điểm mù đã biết**.