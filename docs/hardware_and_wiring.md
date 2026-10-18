# Sơ đồ Kết nối và Chi tiết Phần cứng - Smart Room

Tài liệu chi tiết về sơ đồ đấu nối chân (pinout) giữa các linh kiện ngoại vi và bo mạch **Raspberry Pi 4B** cho hệ thống Smart Room Digital Twin.

---

## 1. Bảng tra cứu đấu nối chân GPIO (Pinout Mapping)

Các chân GPIO trong code được định nghĩa theo chuẩn **BCM** (Broadcom numbering) trong [src/config.py](../src/config.py) và cấu hình qua file [.env.example](../.env.example).

| Thiết bị / Module | Chân trên Module | Chân BCM (Code) | Số chân vật lý (Header 40 chân) | Loại tín hiệu & Điện áp | Ghi chú kỹ thuật |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Cảm biến DHT11** | **VCC** | - | **Chân 1** (3.3V) | Nguồn 3.3V DC | Khuyên dùng 3.3V để mức logic an toàn cho chân Pi |
| | **GND** | - | **Chân 6** hoặc **9** (GND) | Ground | Nối đất chung |
| | **DATA** | **GPIO 4** | **Chân 7** | Digital In/Out | Module 3 chân đã có sẵn trở kéo lên (pull-up 4.7k-10k) |
| **Đèn LED** | **Anode (+)** | **GPIO 17** | **Chân 11** | Digital Output (3.3V) | **Bắt buộc** nối qua điện trở hạn dòng 220Ω – 330Ω |
| | **Cathode (-)** | - | **Chân 9** (GND) | Ground | Chân ngắn hơn hoặc cạnh vát của LED |
| **Quạt DC (Mạch cầu H L298N)** | **IN1** | **GPIO 27** | **Chân 13** | Digital Output | Điều khiển hướng quay / bật |
| | **IN2** | **GPIO 22** | **Chân 15** | Digital Output | Điều khiển hướng quay / đảo |
| | **ENA (PWM)** | **GPIO 18** | **Chân 12** | PWM Hardware | Điều chỉnh tốc độ quạt (Duty cycle 0.0 - 1.0) |
| | **GND** | - | **Chân 14** (GND) | Ground chung | **Bắt buộc nối chung GND nguồn ngoài với GND của Pi** |
| | **+12V / +5V (VCC)**| - | **Cực Dương (+) Nguồn ngoài** | Nguồn động cơ độc lập | **TUYỆT ĐỐI KHÔNG** lấy từ chân 5V của Pi |
| *Quạt (Module MOSFET 1 chân)* | **SIG** | **GPIO 27** | **Chân 13** | PWM / Digital Output | Bỏ trống `FAN_PIN_IN2` và `FAN_PIN_ENABLE` trong cấu hình |
| **Camera CSI** | **Cáp FPC 15-pin** | - | **Cổng CSI trên Pi** | Dữ liệu MIPI-CSI | Nằm giữa cổng micro-HDMI và jack âm thanh 3.5mm |

---

## 2. Sơ đồ nối dây chi tiết từng linh kiện

### A. Cảm biến nhiệt độ & độ ẩm DHT11
```text
  DHT11 Module (3 pins)                Raspberry Pi 4B (Header)
  +--------------------+               +-----------------------+
  |               VCC  | ------------> | Chân 1  (3.3V Power)  |
  |               DATA | ------------> | Chân 7  (GPIO 4)      |
  |               GND  | ------------> | Chân 6  (GND)         |
  +--------------------+               +-----------------------+
```

### B. Đèn LED (Báo hiệu / Chiếu sáng)

**Đấu trực tiếp vào chân GPIO (Đèn LED đơn Đỏ/Vàng hoặc Module LED)**
* Với LED đơn Đỏ/Vàng: Dùng trở **$100\Omega - 150\Omega$** (đạt dòng ~10mA, sáng rõ).
* Với Module LED có sẵn trở SMD: Cắm chân SIG trực tiếp vào GPIO 17 (không cần thêm trở ngoài).
```text
  Mạch LED đơn                        Raspberry Pi 4B (Header)
  +--------------------+               +-----------------------+
  |  Anode (+)         | ---> [Trở 100Ω-150Ω] ---> Chân 11 (GPIO 17)
  |  Cathode (-)       | ------------------------> Chân 9  (GND)
  +--------------------+               +-----------------------+
```

### C. Động cơ quạt DC điều khiển qua mạch cầu H (L298N)
```text
  Mạch L298N                          Raspberry Pi 4B & Nguồn ngoài
  +--------------------+               +-------------------------------+
  |  IN1               | ------------> | Chân 13 (GPIO 27)             |
  |  IN2               | ------------> | Chân 15 (GPIO 22)             |
  |  ENA (bỏ jumper)   | ------------> | Chân 12 (GPIO 18 - PWM)       |
  |  GND               | ----+-------> | Chân 14 (GND Pi)              |
  |                    |     |         +-------------------------------+
  |                    |     +-------> Cực Âm (-) Adapter / Pin ngoài (GND)
  |  +12V / +5V        | ------------> Cực Dương (+) Adapter / Pin ngoài
  |                    |
  |  OUT1, OUT2        | ------------> 2 dây động cơ Quạt DC
  +--------------------+
```

### D. Camera CSI (Picamera2 + OpenCV Haar Cascade)
* Cắm dải cáp dẹt FPC vào khe cắm **CSI** (giữa jack Audio 3.5mm và cổng micro-HDMI).
* **Chiều cắm:** Mặt tiếp xúc kim loại quay về phía cổng micro-HDMI, chốt cài màu đen được kéo lên trước khi cắm và ấn chặt xuống để cố định.

---

## 3. Bản đồ chân Header 40-Pin Raspberry Pi 4B tham khảo

```text
               3.3V Power [ 1] [ 2] 5V Power
             GPIO 2 (SDA) [ 3] [ 4] 5V Power
             GPIO 3 (SCL) [ 5] [ 6] Ground           <-- DHT11 GND
(DHT11 DATA) GPIO 4       [ 7] [ 8] GPIO 14 (TXD)
                    Ground [ 9] [10] GPIO 15 (RXD)    <-- LED GND
(LED)        GPIO 17      [11] [12] GPIO 18 (PWM)    <-- FAN ENA (PWM)
(FAN IN1)    GPIO 27      [13] [14] Ground           <-- FAN GND Chung
(FAN IN2)    GPIO 22      [15] [16] GPIO 23
                      3.3V [17] [18] GPIO 24
             GPIO 10 (MOSI)[19] [20] Ground
                           ...  ...
```

---

## 4. Các lệnh kiểm tra phần cứng (Hardware Diagnostic)

Sau khi đấu dây xong, có thể kiểm tra từng linh kiện độc lập mà không cần kết nối ThingsBoard:

```bash
# Kiểm tra đèn LED (nháy 3 lần)
python main.py --check led

# Kiểm tra quạt DC (chạy 3 giây rồi tắt)
python main.py --check fan

# Kiểm tra cảm biến DHT11 (đọc mẫu 6 lần)
python main.py --check dht

# Kiểm tra camera (mở camera 15 giây và nhận diện người)
python main.py --check camera

# Kiểm tra toàn bộ linh kiện liên tục
python main.py --check all
```

---

## 5. Các nguyên tắc an toàn quan trọng

1. **Tuyệt đối không cấp nguồn động cơ quạt từ chân 5V của Raspberry Pi:**
   - Dòng khởi động và dòng cảm ứng ngược (back-EMF) từ động cơ DC có thể làm tụt áp gây sập nguồn Pi (brownout) hoặc làm cháy chip nguồn. Hãy dùng pin hoặc nguồn adapter ngoài riêng biệt.
2. **Nối chung Mass (Common GND):**
   - Chân GND của nguồn nuôi động cơ ngoài **bắt buộc** phải nối chung với chân GND của Raspberry Pi để mức logic điều khiển (HIGH/LOW) có cùng điện thế tham chiếu.
3. **Điện trở hạn dòng cho LED:**
   - Luôn sử dụng điện trở 220Ω - 330Ω nối tiếp với chân Anode hoặc Cathode của LED để tránh chập tải dòng ra trên chân GPIO 17 (dòng tối đa khuyến nghị mỗi chân GPIO của Pi chỉ khoảng 16mA).
