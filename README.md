# Smart Room Digital Twin - ThingsBoard IoT System

Hệ thống IoT Digital Twin điều khiển và giám sát phòng học/phòng làm việc thông minh chạy trên **Raspberry Pi 4B**, kết nối với nền tảng **ThingsBoard** thông qua 4 Virtual Device MQTT độc lập:
1. **A101 Environment Sensor**: Đọc cảm biến nhiệt độ & độ ẩm DHT11, đồng bộ cấu hình ngưỡng `temperatureThreshold`.
2. **A101 Presence Detector**: Nhận diện người qua Camera CSI (OpenCV Haar Cascade), đồng bộ thời gian chờ tắt `absenceTimeout`.
3. **A101 Smart Fan**: Động cơ quạt DC (L298N) tự động bật khi có người và trời nóng (kèm độ trễ nhiệt hysteresis).
4. **A101 Smart Light**: Đèn LED tự động bật khi có người, tự tắt khi phòng trống quá thời gian chờ.

---

## 1. Cấu trúc Dự án

```text
smart-room-thingsboard/
├── docs/                                # Toàn bộ tài liệu kỹ thuật chi tiết
│   ├── logic_and_features.md            # Logic tự động, Shared Attributes & RPC ThingsBoard
│   └── hardware_and_wiring.md           # Sơ đồ đấu nối chân GPIO (BCM) & an toàn điện
├── resources/                           # File mô hình Haar Cascade (haarcascade_fullbody.xml)
├── tests/                               # Bộ kiểm thử tự động (Unit Tests)
│   ├── test_logic.py                    # Test bảng chân lý AUTO, hysteresis, timeout, RPC
│   └── test_config.py                   # Test nạp cấu hình và validation từ .env
├── .env.example                         # File mẫu cấu hình tham số hệ thống
├── .gitignore                           # Danh sách loại trừ file nhạy cảm và tạm thời
├── install.sh                           # Shell script tự động cài đặt thư viện trên Raspberry Pi
├── requirements.txt                     # Các gói thư viện Python cần thiết
│
├── config.py                            # Quản lý & xác thực cấu hình từ file .env
├── hardware.py                          # Drivers phần cứng (DHT11, LED, Quạt DC L298N, Camera CSI)
├── logic.py                             # Bộ nhớ trạng thái RoomState & vòng lặp AutoController
├── thingsboard.py                       # Kết nối MQTT ThingsBoard độc lập cho 4 Virtual Devices
└── main.py                              # Entry point khởi động hệ thống & Camera Preview
```

---

## 2. Hướng dẫn Cài đặt & Vận hành

### Bước 1: Cài đặt môi trường trên Raspberry Pi
Chạy script cài đặt các gói hệ thống và thư viện Python:
```bash
bash install.sh
```

### Bước 2: Thiết lập file cấu hình `.env`
Sao chép từ file mẫu `.env.example` và điền 4 Access Token tương ứng từ ThingsBoard:
```bash
cp .env.example .env
nano .env
```
Điền 4 access token vào các biến tương ứng:
```env
TB_TOKEN_ENVIRONMENT=your_environment_token
TB_TOKEN_PRESENCE=your_presence_token
TB_TOKEN_FAN=your_fan_token
TB_TOKEN_LIGHT=your_light_token
```

### Bước 3: Khởi động chương trình
Chạy hệ thống ở chế độ thông thường (terminal):
```bash
python main.py
```

Hoặc chạy kèm cửa sổ xem trước camera thời gian thực (hỗ trợ VNC / HDMI desktop):
```bash
python main.py --preview
```

Để dừng chương trình an toàn, bấm `Ctrl+C`. Hệ thống sẽ tự động tắt quạt, tắt đèn và giải phóng phần cứng an toàn (Graceful Shutdown).

---

## 3. Chạy Kiểm thử Tự động (Unit Tests)

Dự án bao gồm bộ test kiểm thử tự động toàn bộ logic điều khiển, bảng chân lý AUTO, độ trễ nhiệt (hysteresis), thời gian chờ (timeout) và các lệnh RPC:
```bash
python -m unittest discover tests
```
Hoặc chạy riêng từng file test:
```bash
python -m unittest tests/test_logic.py
python -m unittest tests/test_config.py
```

---

## 4. Tài liệu Chi tiết
- [docs/logic_and_features.md](docs/logic_and_features.md): Bảng chân lý AUTO, cơ chế đồng bộ Shared Attributes (Initial Sync & Live Update), từ chối điều khiển thủ công khi bật autoMode và danh sách RPC.
- [docs/hardware_and_wiring.md](docs/hardware_and_wiring.md): Bảng tra cứu chân GPIO theo chuẩn BCM, sơ đồ nối dây chi tiết cho DHT11, LED, mạch cầu H L298N, Camera CSI và các lưu ý an toàn điện.
