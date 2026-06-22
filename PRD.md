Setelah melihat spesifikasi aktual hardware yang sudah Anda miliki:

* Raspberry Pi 5 8GB
* Hailo-8 Firmware 4.23
* Debian 13 (Trixie)
* NVMe 256GB
* RAM tersedia >7GB
* Kernel terbaru Raspberry Pi
* Hailo PCIe berjalan normal

maka saya akan merevisi rekomendasi sebelumnya.

Awalnya saya menyarankan menghilangkan Re-ID dari Fase 1 karena saya menganggap target hardware masih "tipikal Raspi". Namun dengan konfigurasi Anda sekarang, saya justru setuju bahwa **Re-ID layak dimasukkan sejak Fase 1** karena ada manfaat penelitian yang besar untuk validasi identitas pekerja dan akan mengurangi refactoring besar pada Fase 2.

Yang saya ubah bukan Re-ID-nya, tetapi cara implementasinya.

---

# REVISI PRD V2.0

# ErgoQuipt Ergonomic Assessment Platform

## Product Vision

Membangun platform ergonomi industri yang mampu:

* Mendeteksi pekerja secara real-time
* Mengidentifikasi pekerja secara konsisten (Re-ID)
* Menghitung RULA & REBA
* Menyimpan histori ergonomi pekerja
* Membangun database risiko ergonomi perusahaan
* Mendukung upgrade dari Single Camera menjadi Multi Camera 3D tanpa perubahan arsitektur backend

---

# FASE 1

# Smart Single Camera Assessment System

Target:

```text
1 Kamera
1 Raspberry Pi 5 + Hailo-8
1 Master Node
```

Namun seluruh backend dan database sudah dirancang seolah-olah sistem multi kamera.

---

# ARSITEKTUR SISTEM

```text
┌────────────────────────────┐
│ Raspberry Pi Edge Node     │
├────────────────────────────┤
│ Camera                     │
│ YOLO Pose (Hailo)          │
│ ByteTrack                  │
│ Re-ID Embedding            │
│ Frame Snapshot             │
│ WebSocket Client           │
└─────────────┬──────────────┘
              │
              │
              ▼
┌────────────────────────────┐
│ FastAPI Backend Server     │
├────────────────────────────┤
│ Session Manager            │
│ Worker Registry            │
│ History Database           │
│ Analytics Engine           │
│ REST API                   │
│ WebSocket Hub              │
└─────────────┬──────────────┘
              │
              │
              ▼
┌────────────────────────────┐
│ Electron Desktop App       │
├────────────────────────────┤
│ Live Monitoring            │
│ RULA Engine                │
│ REBA Engine                │
│ Review Session             │
│ History Viewer             │
│ Analytics Dashboard        │
└────────────────────────────┘
```

---

# EDGE NODE (RASPBERRY PI)

## AI Pipeline

Saya tidak lagi merekomendasikan MediaPipe.

Pipeline baru:

```text
Camera
↓
YOLO-Pose Hailo
↓
ByteTrack
↓
Re-ID Feature Extraction
↓
Packaging JSON
↓
WebSocket
```

---

## Kenapa YOLO-Pose?

Karena sekarang:

```text
YOLO Detection
+
Pose Estimation
```

langsung keluar dari satu inference.

Tidak ada:

```text
Crop
↓
MediaPipe
↓
Pose
```

yang membebani CPU.

---

# Re-ID FASE 1

Status:

```text
WAJIB
```

Namun implementasi:

```text
Soft Re-ID
```

bukan

```text
Enterprise Multi-Camera Re-ID
```

---

## Tujuan

Jika pekerja:

```text
Keluar frame
↓
10 detik
↓
Masuk lagi
```

maka sistem berusaha mempertahankan:

```text
Worker ID yang sama
```

---

## Output

Contoh:

```json
{
  "worker_id":"REID_E47A",
  "tracking_id":3,
  "embedding_confidence":0.91
}
```

---

# FOTO SNAPSHOT

Fitur baru.

Setiap:

```text
5 detik
```

atau

```text
perubahan score signifikan
```

Edge Node menyimpan:

```text
JPEG
Overlay Skeleton
Bounding Box
Timestamp
```

---

## Tujuan

Digunakan saat:

```text
Review Session
```

dan

```text
Validasi Pekerja
```

---

# FASTAPI CENTRAL SERVER

Ini menurut saya harus menjadi jantung sistem.

---

## Fungsi

### Device Manager

Mendeteksi:

```text
Camera Node 1
Camera Node 2
Camera Node 3
```

---

### Session Manager

Membuat:

```text
Session
```

misalnya:

```text
SESSION_20260623_001
```

---

### Worker Registry

Menyimpan:

```text
Worker Name
Department
Position
Employee Number
```

---

### History Database

Menyimpan:

```text
RULA
REBA
Activity Score
Load Score
Timestamp
```

---

### Analytics

Menghasilkan:

```text
Average Risk
Peak Risk
Exposure Duration
Trend Analysis
```

---

# DATABASE

Saya sarankan:

## PostgreSQL

Bukan SQLite.

Karena nanti akan berkembang.

---

Struktur utama:

```text
workers
sessions
camera_nodes
assessments
snapshots
activities
reports
```

---

# ELECTRON DESKTOP APP

Saya setuju sejak awal langsung Electron.

Karena:

Fase 2 juga akan memakai ThreeJS.

---

# HALAMAN 1

# Live Assessment

Menampilkan:

```text
Skeleton
Worker ID
RULA Score
REBA Score
Risk Level
```

---

# HALAMAN 2

# Session Review

Fitur baru yang menurut saya sangat penting.

Saat user menekan:

```text
Save Session
```

maka muncul review.

---

## Langkah 1

Tampilkan:

```text
Foto Snapshot
Overlay Skeleton
Timeline
```

---

## Langkah 2

Konfirmasi Identitas

```text
Worker Detected:
REID_E47A
```

dropdown:

```text
Fariz Achmad
Budi
Andi
```

atau

```text
Create New Worker
```

---

## Langkah 3

Konfirmasi Beban

REBA membutuhkan:

```text
Load Score
```

yang AI tidak bisa ketahui.

User mengisi:

```text
<5 kg
5-10 kg
10-20 kg
>20 kg
```

---

## Langkah 4

Konfirmasi Aktivitas

Untuk:

```text
Activity Score
```

---

Pilihan:

```text
Static Standing
Walking
Lifting
Carrying
Pushing
Pulling
Overhead Work
Repetitive Task
```

---

## Langkah 5

Generate Final Score

Baru sistem menghitung:

```text
Final RULA
Final REBA
```

---

# DASHBOARD ANALYTICS

Tambahan baru.

## Risk Heatmap

Menampilkan:

```text
Pekerja mana paling sering berisiko
```

---

## Trend

Grafik:

```text
Hari
Minggu
Bulan
```

---

## Department Comparison

Misalnya:

```text
Warehouse
Production
Packing
```

---

## Top High Risk Activities

---

# DEFINITION OF DONE FASE 1

## Edge

✅ Auto Start

✅ Headless

✅ YOLO Pose

✅ Re-ID

✅ WebSocket

---

## Backend

✅ FastAPI

✅ PostgreSQL

✅ Session Management

✅ Recording

✅ Analytics

---

## Desktop

✅ Electron

✅ Live Monitoring

✅ Session Review

✅ Worker Validation

✅ Load Validation

✅ History

---

## Performa

✅ 25 FPS minimum

✅ 2–3 pekerja

✅ Latensi <100 ms

✅ Re-ID mempertahankan ID setelah keluar frame ≤10 detik

---

Menurut saya revisi ini jauh lebih dekat dengan **produk komersial yang benar-benar bisa dipakai oleh tim HSE**, bukan sekadar demonstrasi penelitian pose estimation. Fase 1 sudah menghasilkan sistem yang bisa melakukan monitoring, review, validasi pekerja, penyimpanan histori, analitik, dan nantinya tinggal ditingkatkan ke triangulasi 3D pada Fase 2 tanpa mengubah fondasi backend maupun database.
