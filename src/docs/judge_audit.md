# M2 — Judge the judge

## Mục tiêu, đầu vào và kết quả

- **Mục tiêu:** hiệu chuẩn judge như một bộ phân loại nhị phân đối chiếu với nhãn người; tính confusion matrix (FAIL là lớp dương), precision, recall, Cohen's κ và ước lượng tỷ lệ lỗi hiệu chỉnh Rogan–Gladen. Audit bất đồng và xác định judge nào đủ tin cậy cho mục đích nào.
- **Đầu vào:** các dòng trong `data/eval/judge_tone_public.csv` và `data/eval/judge_helpful_public.csv`, gồm câu trả lời, nhãn `human`, nhãn replay `judge`, cùng ghi chú/ledger khi có.
- **Kết quả:** `judge_tone` vượt floors và dùng được như tín hiệu phụ cho giọng điệu; `judge_helpful` FAIL calibration, không được dùng làm gate. Đây không phải bằng chứng rằng judge tone đúng tuyệt đối hoặc áp dụng được cho tác vụ khác.

## Kết quả hiệu chuẩn

| Bộ dữ liệu | n | TP/FP/FN/TN (FAIL dương) | Precision | Recall | κ | Tỷ lệ FAIL quan sát → Rogan–Gladen | Kết luận |
|---|---:|---|---:|---:|---:|---:|---|
| `judge_tone_public.csv` | 100 | 24 / 4 / 6 / 66 | 0,857 | 0,800 | 0,757 | 0,280 → 0,300 | PASS floors (κ≥0,6; P≥0,8; R≥0,7) |
| `judge_helpful_public.csv` | 100 | 9 / 0 / 21 / 70 | 1,000 | 0,300 | 0,375 | 0,090 → 0,300 | FAIL; không dùng làm gate |

Với helpful, độ nhạy 0,30 và độ đặc hiệu 1,00 khiến 21/30 lỗi bị bỏ sót. Rogan–Gladen nâng tỷ lệ lỗi ước lượng từ 9% lên 30%, nhưng hiệu chỉnh prevalence không sửa được từng phán quyết sai và bất định của một judge yếu. Gate cần recall cao để chặn lỗi nguy hiểm; precision hoàn hảo trên các ca ít ỏi mà judge chịu gắn FAIL không bù cho recall thấp.

## Audit bất đồng — tone

Đánh giá dưới đây dựa trên nội dung reply và ghi chú trong CSV; rubric nên định nghĩa điều kiện pass/fail theo tác hại/chính sách thay vì từ khóa bề mặt.

| ID | Human → judge | Ai đúng? | Lý do và sửa rubric |
|---|---|---|---|
| H-008 | FAIL → PASS | Human | “em… nha” với khách là suồng sã. Nêu rõ register/xưng hô không phù hợp là lỗi dù câu có vẻ thân thiện. |
| H-017 | FAIL → PASS | Human | Gọi khách là “bạn” và dùng “nha” không đúng register đã yêu cầu. Chấm quan hệ xưng hô trong ngữ cảnh, không chỉ lịch sự chung chung. |
| H-029 | FAIL → PASS | Human | “không cần nhắn thêm” mang tính ra lệnh. Câu mở đầu “Dạ, vui lòng” không đủ để kết luận lịch sự. |
| H-042 | PASS → FAIL | Human | Đơn đã hoàn 120.000đ, thời hạn 3–5 ngày được nêu; ngắn gọn nhưng đủ ý. Không bắt buộc xin lỗi nếu tình huống không yêu cầu. |
| H-051 | PASS → FAIL | Human | “refund” được chính sách CS cho phép. Không phạt từ tiếng Anh được cho phép khi nghĩa và nội dung đúng. |
| H-063 | FAIL → PASS | Human | “sẽ hoàn thêm” hứa khoản ngoài kết quả hệ thống. Thêm quy tắc cứng: mọi cam kết giao dịch phải khớp ledger/chính sách. |
| H-070 | FAIL → PASS | Human | Emoji cười trong ngữ cảnh khiếu nại không phù hợp. Đánh giá emoji theo ngữ cảnh, không xem lời lễ phép là đủ. |
| H-081 | PASS → FAIL | Judge (nhãn human sai) | Ghi chú CSV nói người chấm đọc nhầm ticket; sửa nhãn gold thành FAIL. Lưu provenance/đối soát nhãn trước khi tính chỉ số. |
| H-088 | PASS → FAIL | Human (theo nhãn hiện tại) | Lặp “Dạ” là lỗi gõ nhẹ nhưng không làm hỏng nội dung. Xác định mức độ lỗi gõ và tolerance; không tự động fail mọi lặp từ. |
| H-094 | FAIL → PASS | Human | Bỏ dấu toàn bộ làm giảm chất lượng và độ rõ. Thêm tiêu chí ngôn ngữ/chính tả với ngưỡng rõ ràng, không để các từ “Dạ/xin lỗi” lấn át. |

10 bất đồng này cho thấy lỗi cả hai phía: judge dựa vào dấu hiệu bề mặt (H-029, H-042, H-051), còn nhãn người cũng có thể sai (H-081). Cần adjudication và rubric mới trước khi dùng judge tone làm gate blocker; hiện chỉ nên dùng nó như tín hiệu/cảnh báo phụ, có kiểm tra người ở ca rủi ro.

## Audit bất đồng — helpful

Helpful có 21 bất đồng và tất cả đều là **human FAIL / judge PASS**: các ca sai số tiền theo ledger, xưng hô sai, trả lời lạc đề hoặc thiếu thông tin cần thiết. Ví dụ:

| ID | Human → judge | Ai đúng? | Lý do và sửa rubric |
|---|---|---|---|
| HL-020 | FAIL → PASS | Human | Reply nói hoàn 90.000đ trong khi ledger ghi 120.000đ. Bắt buộc so khớp số tiền và đơn với nguồn chuẩn; lỗi giao dịch là hard fail. |
| HL-028 | FAIL → PASS | Human | Nêu 50.000đ thay vì 35.000đ, dù có nhiều câu xin lỗi. Tính đúng/sai nghiệp vụ phải độc lập với độ dài, lịch sự và lời xin lỗi. |
| HL-047 | FAIL → PASS | Human | “Ok bạn… nhé” sai register xưng hô. Chấm theo rubric xưng hô cụ thể cho khách, không dùng cảm giác helpful tổng quát. |
| HL-062 | FAIL → PASS | Human | Reply nói hoàn 55.000đ thay vì ledger 40.000đ. Bắt buộc đối chiếu con số với nguồn chuẩn; một khoản sai là fail bất kể giọng điệu. |
| HL-087 | FAIL → PASS | Human | Reply nói 60.000đ thay vì ledger 90.000đ. Kiểm tra mọi khoản nêu trong reply, không chỉ có nhắc đến hoàn tiền. |
| HL-091 | FAIL → PASS | Human | “Ok bạn…” lặp lại lỗi xưng hô. Một lỗi đơn giản nhưng bị bỏ qua cho thấy judge không đáng tin làm gate. |
| HL-100 | FAIL → PASS | Human | Reply nói 55.000đ thay vì ledger 35.000đ. Đặt kiểm tra ledger thành điều kiện bắt buộc, không suy diễn từ câu trả lời trôi chảy. |

Ngoài các ca minh họa, 21 FN gồm nhiều số tiền sai, và các trường hợp xưng hô sai. Rubric helpful cần kiểm tra theo thứ tự: (1) đúng intent/liên quan, (2) đúng đơn và số tiền so với ledger, (3) không tự bịa/hứa, (4) đủ bước tiếp theo, (5) register phù hợp. Mỗi mục phải có căn cứ quan sát được; lỗi (1)–(3) là hard fail. Không cho điểm helpful tổng thể để bù một lỗi tiền hoặc lời hứa sai.

**Quyết định gate:** không dùng `judge_helpful` làm gate. Recall 0,30 đồng nghĩa bỏ lọt 70% lỗi trong bộ hiệu chuẩn này; precision 1,00 chỉ phản ánh judge rất ít khi gắn nhãn FAIL. Thay bằng kiểm tra xác định từ ledger/schema cho số tiền và trạng thái, cùng rubric grader đã adjudicate cho intent, lời hứa và xưng hô; các quyết định rủi ro còn lại cần human review. Sau khi sửa rubric phải tạo tập hiệu chuẩn mới độc lập và đo lại trên các lát lỗi, không chỉ nhìn accuracy/precision.
