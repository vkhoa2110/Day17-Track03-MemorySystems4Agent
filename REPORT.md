# Memory Systems Lab Report

## 1. Muc tieu

Bai lab so sanh hai cach thiet ke memory cho AI agent:

- `Baseline Agent`: chi giu short-term memory trong tung thread.
- `Advanced Agent`: ket hop short-term memory, persistent memory bang `User.md`, va compact memory cho hoi thoai dai.

Muc tieu chinh khong phai la lam agent "nho tat ca", ma la do trade-off giua recall, token cost, memory growth va do phuc tap cua he thong.

## 2. Ket qua benchmark

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

## 3. Vi sao Advanced recall tot hon Baseline

Baseline chi luu lich su theo `thread_id`, nen khi benchmark hoi recall trong thread moi, agent khong con ngu canh cu. Vi vay Baseline gan nhu khong tra loi duoc cac fact nhu ten, nghe nghiep hien tai, noi o, do uong yeu thich, mon an yeu thich hay style tra loi.

Advanced ghi cac fact on dinh vao `User.md`. Khi sang thread moi, agent van doc lai profile nay, nen co the recall thong tin da hoc tu nhieu session truoc. Lop extraction cung xu ly correction co ban, vi du:

- nghe cu `backend engineer` duoc thay bang `MLOps engineer`
- noi o cu `Da Nang` hoac `Hue` duoc cap nhat theo thong tin moi hon
- cau dua ve `product manager` khong bi ghi de thanh nghe hien tai

Do do Standard Benchmark cho thay recall cua Advanced dat `0.896`, cao hon ro ret so voi Baseline `0.024`.

## 4. Vi sao Advanced co the ton hon o hoi thoai ngan

Trong Standard Benchmark, Advanced xu ly nhieu prompt tokens hon Baseline: `24695` so voi `15692`. Ly do la Advanced khong chi mang recent messages, ma con nap them:

- noi dung `User.md`
- facts da extract
- compact summary neu co
- logic cap nhat memory sau moi turn

Voi hoi thoai ngan hoac vua, chi phi nap profile co the lon hon loi ich compact. Baseline don gian hon nen re hon ve prompt load trong nhung thread chua du dai.

## 5. Vi sao compact co loi o hoi thoai dai

Trong stress benchmark, Baseline tiep tuc keo theo lich su thread dai, nen `prompt tokens processed` tang len `23810`. Advanced kich hoat compact memory `24` lan, giu lai cac message gan nhat va nen noi dung cu thanh summary. Nho vay prompt load giam xuong `20161` trong khi recall van dat `1.000`.

Ket qua nay cho thay compact memory chu yeu toi uu `prompt tokens processed`, khong nhat thiet lam giam `agent tokens only`. Advanced van sinh nhieu token hon Baseline vi no tra loi day du hon va co them noi dung recall chinh xac.

## 6. Memory growth va rui ro

Advanced tao file `User.md`, nen memory co tang truong theo thoi gian. Trong benchmark:

- Standard Benchmark: memory growth `387` bytes
- Stress Benchmark: memory growth `250` bytes

Dung luong nay nho vi implementation chi luu fact on dinh, khong ghi nguyen van tat ca message. Tuy nhien trong he thong production, rui ro van gom:

- luu sai fact neu extractor qua rong
- giu thong tin cu sau khi nguoi dung da correction
- profile phinh to neu luu qua nhieu preference tam thoi
- nham lan giua cau hoi, cau dua, thong tin gay nhieu va fact that

Vi vay agent can guardrail nhu confidence threshold, conflict handling, va co che memory decay neu trien khai that.

## 7. Ket luan

Ket qua benchmark the hien dung logic cua lab:

1. Baseline la moc so sanh don gian, chi nho trong thread.
2. Advanced tang recall nho persistent memory bang `User.md`.
3. O hoi thoai ngan, Advanced co the ton prompt tokens hon vi phai nap profile.
4. O hoi thoai dai, compact memory giup Advanced giam prompt load va van giu du fact quan trong.
5. Memory system manh hon nhung cung can guardrail de tranh luu sai, luu thua va phinh file theo thoi gian.
