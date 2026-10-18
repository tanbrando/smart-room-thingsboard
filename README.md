# Smart Room Digital Twin (Smart Room Lite)

Hệ thống IoT Digital Twin mô phỏng và điều khiển phòng thông minh chạy trên **Raspberry Pi 4B**, kết nối với nền tảng **ThingsBoard** thông qua 4 Device MQTT độc lập (A101 Environment Sensor, A101 Presence Detector, A101 Smart Fan, A101 Smart Light).

---

## 1. Cấu trúc Dự án

Mã nguồn được cấu trúc theo phân tầng module rõ ràng, tách bạch giữa code, tài liệu và tài nguyên:

```
smart_room_lite/
├── docs/                                # Toàn bộ tài liệu kỹ thuật
│   ├── logic_and_features.md            # Chi tiết logic, Shared Attributes, RPC ThingsBoard
│   └── hardware_and_wiring.md           # Sơ đồ đấu nối chân GPIO (BCM) và an toàn điện
├── resources/                           # File mô hình Haar Cascade (haarcascade_fullbody.xml)
├── tests/                               # Bộ kiểm thử tự động (Unit Tests)
│   ├── test_logic.py                    # Test bảng chân lý AUTO, hysteresis, timeout, RPC
│   └── test_config.py                   # Test nạp cấu hình và validation
├── .env.example                         # File mẫu cấu hình toàn bộ tham số (chỉ trống token)
├── .gitignore                           # Danh sách loại trừ file nhạy cảm và tạm thời
├── install.sh                           # Shell script tự động cài đặt môi trường trên Pi
├── requirements.txt                     # Các gói thư viện Python cần cài đặt
│
├── config.py                            # [1/5] Quản lý & xác thực cấu hình từ .env
├── hardware.py                          # [2/5] Drivers phần cứng Raspberry Pi (DHT11, LED, DC Fan, Camera)
├── logic.py                             # [3/5] RoomState (bộ nhớ chia sẻ) & AutoController
├── thingsboard.py                       # [4/5] Kết nối ThingsBoard MQTT (Environment, Presence, Actuator)
└── main.py                              # [5/5] Entry point khởi động ứng dụng & Camera Preview (VNC)
```

---

## 2. Hướng dẫn Cài đặt & Vận hành

### Bước 1: Cài đặt thư viện môi trường trên Raspberry Pi
```bash
bash install.sh
```

### Bước 2: Thiết lập file cấu hình `.env`
Sao chép từ file mẫu `.env.example` và điền 4 Access Token tương ứng từ ThingsBoard:
```bash
cp .env.example .env
nano .env
```
Điền 4 token vào các biến:
```env
TB_TOKEN_ENVIRONMENT=your_env_token_here
TB_TOKEN_PRESENCE=your_presence_token_here
TB_TOKEN_FAN=your_fan_token_here
TB_TOKEN_LIGHT=your_light_token_here
```

### Bước 3: Khởi động chương trình
Chạy hệ thống chế độ chạy nền chuẩn:
```bash
python main.py
```

Hoặc bật cửa sổ xem trước camera trực tiếp (hỗ trợ VNC / HDMI desktop):
```bash
python main.py --preview
```

---

## 3. Chạy Kiểm thử Tự động (Unit Tests)

Dự án đi kèm bộ test toàn diện kiểm tra logic đóng/ngắt, trễ nhiệt (hysteresis), timeout và xử lý RPC:
```bash
python -m unittest discover tests
# Hoặc chạy riêng từng file test:
python -m unittest tests/test_logic.py
python -m unittest tests/test_config.py
```

---

## 4. Tài liệu Chi tiết
- [docs/logic_and_features.md](docs/logic_and_features.md): Bảng chân lý AUTO, cơ chế Manual Override, đồng bộ Shared Attributes và phản hồi RPC.
- [docs/hardware_and_wiring.md](docs/hardware_and_wiring.md): Bảng tra cứu chân BCM, sơ đồ nối dây mạch cầu H L298N, điện trở hạn dòng LED và camera CSI.
