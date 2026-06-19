# Báo Cáo Lab Memory Systems

## 1. Mục tiêu

Bài lab so sánh hai cách thiết kế memory cho AI agent:

- `Baseline Agent`: chỉ giữ short-term memory trong từng thread.
- `Advanced Agent`: kết hợp short-term memory, persistent memory bằng `User.md`, và compact memory cho hội thoại dài.

Mục tiêu chính không phải là làm agent "nhớ tất cả", mà là đo trade-off giữa recall, token cost, memory growth và độ phức tạp của hệ thống.

## 2. Kết quả benchmark

### Standard Benchmark

Input: `data/conversations.json`

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 1794 | 15692 | 0.024 | 0.219 | 0 | 0 |
| Advanced | 2122 | 24695 | 0.896 | 0.917 | 387 | 0 |

### Long-Context Stress Benchmark

Input: `data/advanced_long_context.json`

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 531 | 23810 | 0.000 | 0.200 | 0 | 0 |
| Advanced | 1205 | 20161 | 1.000 | 1.000 | 250 | 24 |

## 3. Vì sao Advanced recall tốt hơn Baseline

Baseline chỉ lưu lịch sử theo `thread_id`, nên khi benchmark hỏi recall trong thread mới, agent không còn ngữ cảnh cũ. Vì vậy Baseline gần như không trả lời được các fact như tên, nghề nghiệp hiện tại, nơi ở, đồ uống yêu thích, món ăn yêu thích hay style trả lời.

Advanced ghi các fact ổn định vào `User.md`. Khi sang thread mới, agent vẫn đọc lại profile này, nên có thể recall thông tin đã học từ nhiều session trước. Lớp extraction cũng xử lý correction cơ bản, ví dụ:

- nghề cũ `backend engineer` được thay bằng `MLOps engineer`
- nơi ở cũ được cập nhật theo thông tin mới hơn
- câu đùa về `product manager` không bị ghi đè thành nghề hiện tại

Do đó Standard Benchmark cho thấy recall của Advanced đạt `0.896`, cao hơn rõ rệt so với Baseline `0.024`.

## 4. Vì sao Advanced có thể tốn hơn ở hội thoại ngắn

Trong Standard Benchmark, Advanced xử lý nhiều prompt tokens hơn Baseline: `24695` so với `15692`. Lý do là Advanced không chỉ mang recent messages, mà còn nạp thêm:

- nội dung `User.md`
- facts đã extract
- compact summary nếu có
- logic cập nhật memory sau mỗi turn

Với hội thoại ngắn hoặc vừa, chi phí nạp profile có thể lớn hơn lợi ích compact. Baseline đơn giản hơn nên rẻ hơn về prompt load trong những thread chưa đủ dài.

## 5. Vì sao compact có lợi ở hội thoại dài

Trong stress benchmark, Baseline tiếp tục kéo theo lịch sử thread dài, nên `prompt tokens processed` tăng lên `23810`. Advanced kích hoạt compact memory `24` lần, giữ lại các message gần nhất và nén nội dung cũ thành summary. Nhờ vậy prompt load giảm xuống `20161` trong khi recall vẫn đạt `1.000`.

Kết quả này cho thấy compact memory chủ yếu tối ưu `prompt tokens processed`, không nhất thiết làm giảm `agent tokens only`. Advanced vẫn sinh nhiều token hơn Baseline vì nó trả lời đầy đủ hơn và có thêm nội dung recall chính xác.

## 6. Memory growth và rủi ro

Advanced tạo file `User.md`, nên memory có tăng trưởng theo thời gian. Trong benchmark:

- Standard Benchmark: memory growth `387` bytes
- Stress Benchmark: memory growth `250` bytes

Dung lượng này nhỏ vì implementation chỉ lưu fact ổn định, không ghi nguyên văn tất cả message. Tuy nhiên trong hệ thống production, rủi ro vẫn gồm:

- lưu sai fact nếu extractor quá rộng
- giữ thông tin cũ sau khi người dùng đã correction
- profile phình to nếu lưu quá nhiều preference tạm thời
- nhầm lẫn giữa câu hỏi, câu đùa, thông tin gây nhiễu và fact thật

Vì vậy agent cần guardrail như confidence threshold, conflict handling, và cơ chế memory decay nếu triển khai thật.

## 7. Kết luận

Kết quả benchmark thể hiện đúng logic của lab:

1. Baseline là mốc so sánh đơn giản, chỉ nhớ trong thread.
2. Advanced tăng recall nhờ persistent memory bằng `User.md`.
3. Ở hội thoại ngắn, Advanced có thể tốn prompt tokens hơn vì phải nạp profile.
4. Ở hội thoại dài, compact memory giúp Advanced giảm prompt load và vẫn giữ đủ fact quan trọng.
5. Memory system mạnh hơn nhưng cũng cần guardrail để tránh lưu sai, lưu thừa và phình file theo thời gian.
