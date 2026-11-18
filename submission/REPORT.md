# Báo cáo Day 09 — Phạm Hoàng Minh, 2A202603064

## 1. Kết luận trước

Pipeline kết luận **RELEASE**. Intake quét 224 ảnh, loại 31 ảnh (3 BAD_SIZE, 2 CORRUPT_IMAGE, 8 DUP_IMAGE_EXACT, 7 DUP_IMAGE_NEAR và 11 LEAK_TEST), còn 193 ảnh. Dataset `clean_v1` xuất thành công với 193 ảnh và 4 lớp: car, person, truck, bus.

Sau vòng kiểm tra cuối, không còn lỗi bắt buộc; còn 13/193 ảnh có cảnh báo, tương đương 6,74%, thấp hơn ngưỡng Hold 10%. Pipeline hoàn thành trong 2 giây; mô phỏng người duyệt sử dụng đủ ngân sách 80/80 ảnh.

## 2. Lỗi và phân việc

Số liệu lấy từ `02_error_list_v1.txt`. Các lỗi định dạng, hình học và intake được máy xử lý bằng autofix hoặc loại khỏi tập dữ liệu. Các lỗi thiếu nhãn và cảnh báo ngữ nghĩa cần người kiểm tra.

| Mã lỗi | Số ảnh/dòng | Ai sửa | Cách xử lý |
|---|---:|---|---|
| BAD_CLASS_ID | 6 | Máy | Xóa dòng nhãn sai class ID |
| BAD_CLASS_NAME | 2 | Máy | Chuẩn hóa tên class |
| BAD_FORMAT | 3 | Máy | Xóa dòng sai định dạng |
| BAD_SIZE | 3 | Máy | Loại ảnh quá nhỏ |
| BOX_OUT_OF_IMAGE | 8 | Máy | Clip box vào biên ảnh |
| BOX_ZERO | 4 | Máy | Xóa box có diện tích bằng 0 |
| CORRUPT_IMAGE | 2 | Máy | Loại ảnh hỏng |
| DUP_BOX | 7 | Máy | Xóa box trùng |
| DUP_IMAGE_EXACT | 8 | Máy | Loại ảnh trùng chính xác |
| DUP_IMAGE_NEAR | 7 | Máy | Loại ảnh trùng gần đúng |
| LEAK_TEST | 11 | Máy | Loại ảnh trùng tập test/val |
| MISSING_LABEL_FILE | 6 | Người | Chuyển sang người gán nhãn |
| BOX_HUGE | 3 | Người | Kiểm tra box quá lớn |
| BOX_TINY | 6 | Người | Kiểm tra box quá nhỏ |
| CLASS_RARE | 4 | Người | Kiểm tra lớp hiếm |
| EMPTY_LABEL | 11 | Người | Phân biệt ảnh nền và thiếu nhãn |
| POSSIBLE_FALSE_POS | 24 | Người | Kiểm tra box có thể gán nhầm |
| POSSIBLE_LOOSE_BOX | 11 | Người | Kiểm tra box có thể quá rộng |
| POSSIBLE_MISSING | 32 | Người | Kiểm tra đối tượng có thể thiếu box |
| POSSIBLE_WRONG_CLASS | 13 | Người | Kiểm tra class có thể sai |

Hàng đợi có 98 ảnh nhưng ngân sách chỉ 80 ảnh. Ảnh `img_0020` đứng đầu với priority 11.524 do có nhiều tín hiệu cùng lúc: FIXED_DROP_LINE, POSSIBLE_MISSING và POSSIBLE_WRONG_CLASS. Các ảnh NEEDS_LABEL có priority 10 nên cũng được ưu tiên cao. Cách xếp hàng sử dụng trọng số theo mức độ nghiêm trọng và loại cảnh báo.

Trong 80 ảnh được review, có 67 ảnh chứa ít nhất một cảnh báo ngữ nghĩa, tổng cộng 76 lượt cảnh báo: 20 POSSIBLE_FALSE_POS, 11 POSSIBLE_LOOSE_BOX, 32 POSSIBLE_MISSING và 13 POSSIBLE_WRONG_CLASS. Đây là số cảnh báo được đưa ra để xem xét, không đồng nghĩa tất cả đều là lỗi đã được xác nhận.

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall trước → sau | Lý do |
|---|---:|---:|---|---|
| duplicates.phash_dist | 2 | 16 | Near: 1.00/0.50 → 1.00/0.83; Exact: 1.00/1.00 → 1.00/1.00 | Tăng khả năng phát hiện ảnh trùng gần đúng mà vẫn giữ kết quả exact |
| second_opinion.conf | 0.25 | 0.8 | Wrong class: 0.56/0.83 → 1.00/0.83; Missing: 0.50/1.00 → 0.67/0.75 | Ưu tiên dự đoán có độ tin cậy cao, giảm cảnh báo sai cho wrong class |

Với `second_opinion.conf`, loose box có precision/recall thay đổi từ 0.29/0.40 xuống 0.50/0.20; false positive giữ nguyên 0.36/1.00. Vì vậy ngưỡng 0.8 là lựa chọn đánh đổi, không cải thiện mọi nhóm lỗi.

Một điểm dễ gây hiểu nhầm là tăng `phash_dist` không phải lúc nào cũng tốt hơn. Ở giá trị 16, F1 của near duplicate đạt 0.91; nhưng tại 20, F1 exact duplicate giảm còn 0.50 và near duplicate giảm còn 0.67. Trong dữ liệu intake có các cặp near duplicate với pHash 0, 6, 10 và 16. Vì vậy, cần xem trực quan các cặp ảnh trước khi quyết định loại, tránh loại nhầm ảnh khác nhau nhưng có hình thức tương tự.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

### 4.1. Kiểm chứng Gate

Chạy pipeline với `--budget 0`, kết quả vẫn còn 6 lỗi bắt buộc sau vòng kiểm tra cuối. Gate kết luận **REWORK**, mã thoát `20`, đồng thời không xuất dataset. Đã kiểm tra `work/exp_nb/manifest.json` và xác nhận manifest không tồn tại. Điều này chứng minh pipeline không phát hành dữ liệu khi vẫn còn lỗi bắt buộc, kể cả khi không có ngân sách người duyệt.

### 4.2. Điểm mù

- **Không thể tự phân biệt ảnh nền và thiếu nhãn:** sau review vẫn còn 5 cảnh báo EMPTY_LABEL ở `img_0097`, `img_0129`, `img_0147`, `img_0184`, `img_0192`. File nhãn rỗng có thể là ảnh nền hợp lệ hoặc ảnh bị bỏ sót đối tượng; cần xem ảnh thực tế để quyết định.
- **Second Opinion không phải ground truth:** sau review còn 11 POSSIBLE_FALSE_POS, 1 POSSIBLE_MISSING và 1 POSSIBLE_WRONG_CLASS. Ví dụ `img_0183` có đối tượng model phát hiện nhưng chưa có box tương ứng; `img_0078` có class nhãn khác dự đoán model. Model có thể dự đoán sai hoặc bỏ sót vật thể nên các cảnh báo này cần người xác minh.
- **Box nhỏ vẫn cần đánh giá theo ngữ cảnh:** còn 6 cảnh báo BOX_TINY. Đối tượng ở xa có thể có box nhỏ nhưng vẫn đúng, vì vậy không thể tự động xóa chỉ dựa trên kích thước.

## 5. Train: raw vs clean

Thực hiện huấn luyện YOLO26n trên hai biến thể dữ liệu raw và clean, mỗi biến thể chạy 2 seeds (0, 1), 20 epochs, imgsz 640, batch 16. Quá trình train sử dụng GPU NVIDIA Tesla T4 trên Google Colab.

Biến thể	Ảnh train	Seeds	mAP50	mAP50-95	Precision	Recall
raw	224	2	0.726 ± 0.000	0.512 ± 0.004	0.764 ± 0.061	0.649 ± 0.028
clean	193	2	0.730 ± 0.008	0.517 ± 0.007	0.767 ± 0.021	0.642 ± 0.009

Chênh lệch mAP50 (Clean − Raw) là +0.004; mAP50-95 tăng +0.005; Precision tăng +0.003; Recall giảm −0.007.

5.2. Nhận xét
Clean có ít hơn 31 ảnh train so với Raw nhưng đạt mAP50 và mAP50-95 cao hơn một chút. Precision cũng tăng nhẹ, trong khi Recall giảm nhẹ. Điều này cho thấy việc lọc dữ liệu không làm giảm hiệu năng tổng thể trong thử nghiệm này và có dấu hiệu cải thiện chất lượng dự đoán.

Tuy nhiên, mức chênh lệch mAP50 chỉ là 0.004, tương đối nhỏ. Với 2 seeds, chưa đủ cơ sở để khẳng định Clean tốt hơn một cách có ý nghĩa thống kê. Độ dao động giữa các seeds cũng cần được xem xét, đặc biệt ở Precision của Raw (độ lệch 0.061).
5.3. Giả thuyết và cách kiểm chứng
- Giả thuyết 1 – Loại bỏ dữ liệu nhiễu giúp mô hình tổng quát hóa tốt hơn: Raw chứa ảnh trùng, ảnh gần trùng hoặc dữ liệu không phù hợp; việc làm sạch có thể giảm ảnh hưởng của những mẫu này. Cách kiểm chứng: so sánh mAP50 và mAP50-95 trên cùng tập test độc lập, tăng số seeds và đối chiếu các trường hợp dự đoán sai giữa hai mô hình.
- Giả thuyết 2 – Giảm số lượng ảnh có thể làm mất một phần thông tin hữu ích: Clean loại 31 ảnh, trong đó có thể có các mẫu khó hoặc trường hợp hiếm. Điều này có thể góp phần khiến Recall giảm nhẹ. Cách kiểm chứng: phân tích false negative theo lớp, kiểm tra các ảnh bị loại và thực hiện thí nghiệm ablation bằng cách bổ sung lại từng nhóm ảnh đã loại.
5.4. Kết luận
Trong thử nghiệm hiện tại, Clean đạt kết quả mAP50 và mAP50-95 nhỉnh hơn Raw dù sử dụng ít ảnh train hơn. Đây là tín hiệu tích cực cho quy trình AutoQC: chất lượng dữ liệu có thể quan trọng hơn số lượng ảnh đơn thuần. Tuy nhiên, do chỉ sử dụng 2 seeds và chênh lệch còn nhỏ, cần thử nghiệm thêm với nhiều seeds và tập dữ liệu lớn hơn trước khi kết luận chắc chắn.

Kết quả được lưu tại submission/results/, gồm raw_seed0.json, raw_seed1.json, clean_seed0.json, clean_seed1.json, comparison.md, comparison.json và comparison.png.


## 6. Quyết định và ghi chú AI

**Quyết định cuối: RELEASE.** Dataset `clean_v1` có 193 ảnh, không còn lỗi bắt buộc và tỷ lệ ảnh còn cảnh báo là 6,74%, thấp hơn ngưỡng Hold 10%. Các cảnh báo còn lại cần tiếp tục được kiểm tra nếu dùng dữ liệu cho huấn luyện hoặc phát hành ở quy mô lớn.

**Ghi chú sử dụng AI:**
- Prompt chính: hỗ trợ triển khai các module label format, gate, autofix và second opinion theo yêu cầu lab và unit test.
- Cách kiểm tra: chạy pytest (79 tests passed), xem kết quả calibration, chạy pipeline thực tế và thử Gate với ngân sách 0.
- Một lỗi của AI: AI ban đầu chỉ sai tên file báo cáo v3, đề xuất `04_error_list_v3.txt`; sau khi đối chiếu danh sách file thực tế đã sửa thành `07_error_list_v3.txt`.
