# Chi tiết Chức năng & Logic Hoạt động - Smart Room

Tài liệu tổng hợp toàn bộ tính năng, luồng dữ liệu và logic vận hành của dự án **Smart Room Digital Twin** chạy trên Raspberry Pi 4B kết nối với nền tảng **ThingsBoard**.

---

## 1. Kiến trúc Tổng quan (Device-level Attributes)

Toàn bộ **Shared Attributes** được cấu hình trực tiếp trên từng **Device** tương ứng của ThingsBoard (không phụ thuộc Asset):

| Thiết bị | Phần cứng | Dữ liệu gửi lên (Telemetry) | Shared Attributes nhận về | RPC hỗ trợ |
| :--- | :--- | :--- | :--- | :--- |
| **A101 Environment Sensor** | Cảm biến DHT11 | `temperature`, `humidity` (định kỳ) | `temperatureThreshold` (float, °C) | - |
| **A101 Presence Detector** | Camera CSI + OpenCV | `personDetected` (chỉ gửi khi đổi) | `absenceTimeout` (float, giây) | - |
| **A101 Smart Fan** | Động cơ DC (L298N) | `state` (`true`/`false`) | `autoMode` (boolean) | `getState`, `setState`, `toggle` |
| **A101 Smart Light** | Đèn LED | `state` (`true`/`false`) | `autoMode` (boolean) | `getState`, `setState`, `toggle` |

---

## 2. Logic Vận hành Cốt lõi

Hệ thống quản lý chế độ tự động **độc lập cho từng thiết bị** thông qua biến `autoMode` (Boolean):
* `autoMode = true`: Thiết bị hoạt động tự động theo cảm biến & thuật toán cục bộ trên Raspberry Pi.
* `autoMode = false`: Thiết bị ở chế độ thủ công (MANUAL), cho phép người dùng điều khiển tự do qua nút bấm/RPC trên Dashboard.

> **Lợi ích:** Bạn có thể để Đèn tự động (`autoMode = true`) trong khi Quạt chỉnh tay (`autoMode = false`), hoặc ngược lại.

### 2.1. Logic Tự động khi `autoMode = true`

Chu kỳ đánh giá của bộ điều khiển `AutoController` là mỗi **1 giây** (cấu hình qua `CONTROL_INTERVAL`):

#### A. Điều khiển Đèn (Smart Light - khi `autoMode = true`)
* **Bật đèn (`state = true`):** Khi phát hiện có người trong phòng (`personDetected = true`).
* **Tắt đèn (`state = false`):** Khi **hết người** và thời gian vắng mặt đã vượt quá `absenceTimeout` (mặc định 10 giây).
  > **Chống chập chờn:** Tránh đèn tắt đột ngột nếu người chỉ cúi xuống hoặc tạm khuất tầm nhìn camera vài giây.

#### B. Điều khiển Quạt (Smart Fan - khi `autoMode = true`)
Quạt chỉ hoạt động khi **có người** VÀ **nhiệt độ vượt ngưỡng**:
* **Bật quạt:** `Có người` **VÀ** `temperature > temperatureThreshold` (mặc định 30°C).
* **Tắt quạt:** 
  * Không có người (hoặc vắng mặt quá `absenceTimeout`).
  * Hoặc nhiệt độ giảm xuống: $\le temperatureThreshold - fan\_hysteresis$ (mặc định: $30 - 1.0 = 29^\circ\text{C}$).
  * Hoặc dữ liệu nhiệt độ quá hạn ($> 60$ giây) $\rightarrow$ Tự tắt quạt để an toàn.
* **Độ trễ nhiệt (Hysteresis):** Trong khoảng $29.0^\circ\text{C} - 30.0^\circ\text{C}$, quạt giữ nguyên trạng thái cũ để tránh relay/động cơ đóng ngắt liên tục.

---

### 2.2. Điều khiển Thủ công (RPC) khi `autoMode = false`

#### A. Lấy trạng thái hiện tại (`getState`)
* Dashboard ThingsBoard (hoặc widget công tắc) gửi RPC `getState` (hỗ trợ cả `get_state`, `getValue`, `get_status`).
* Raspberry Pi đọc trạng thái thực tế của chân phần cứng và phản hồi ngay lập tức:
  ```json
  {"state": true, "value": true, "autoMode": false}
  ```

#### B. Bật/Tắt thiết bị (`setState` / `setValue` / `toggle`)
* **Hỗ trợ đa dạng định dạng tham số RPC:** Nhận boolean (`true`/`false`), string (`"true"`, `"false"`, `"on"`, `"off"`, `"1"`, `"0"`), hoặc dictionary/object từ widget ThingsBoard (`{"value": true}`, `{"state": true}`, `{"enabled": true}`).
* **Điều kiện Tiên quyết (Precondition):**
  * Lệnh bật/tắt thủ công **chỉ được phép thực thi khi `autoMode = false`**.
  * Nếu thiết bị đang ở chế độ tự động (`autoMode = true`), Raspberry Pi sẽ **từ chối lệnh (reject)** và phản hồi lại trạng thái hiện tại để widget công tắc trên Dashboard tự động gạt về vị trí cũ:
    ```json
    {
      "error": "Manual control disabled while autoMode is True on fan.",
      "state": false,
      "value": false,
      "autoMode": true,
      "success": false
    }
    ```
  * Khi `autoMode = false`: Thiết bị thực thi lệnh bật/tắt ngay lập tức và đồng bộ telemetry trạng thái mới lên ThingsBoard:
    ```json
    {"state": true, "value": true, "autoMode": false, "success": true}
    ```

---

## 3. Các Cơ chế Xử lý & Độ tin cậy (Resilience)

### 3.1. Đồng bộ Shared Attributes 2 Chiều (Initial Sync & Live Update)
* **Initial Sync (Đồng bộ khi khởi động):**
  - Ngay khi kết nối MQTT thành công (`on_connected`), từng thiết bị gửi yêu cầu `request_shared_attributes` lên ThingsBoard qua topic `v1/devices/me/attributes/request/{id}`.
  - ThingsBoard phản hồi giá trị cấu hình hiện có trên server qua topic `v1/devices/me/attributes/response/{id}`.
  - Hệ thống cập nhật các tham số (`temperatureThreshold`, `absenceTimeout`, `autoMode`) vào bộ nhớ và in bảng thông báo `[INITIAL SYNC]`. Nhờ đó, nếu Raspberry Pi khởi động lại, nó vẫn giữ đúng các giá trị bạn đã cài đặt trước đó trên ThingsBoard.
* **Live Update (Cập nhật tức thời):**
  - Khi bạn sửa Shared Attributes trên ThingsBoard Web, ThingsBoard gửi bản tin MQTT xuống qua topic `v1/devices/me/attributes`.
  - Thiết bị nhận được, cập nhật ngay lập tức và in bảng `[LIVE UPDATE]`.

### 3.2. Lọc nhiễu nhận diện người (Camera Haar Cascade)
* **`confirm_frames = 2`:** Phải phát hiện thấy người liên tiếp 2 frame mới báo `personDetected = True`.
* **`hold_seconds = 2.0s`:** Giữ trạng thái có người thêm 2 giây sau frame cuối cùng thấy người để chống hiện tượng nhấp nháy khung hình.

### 3.3. Tự phục hồi kết nối (Auto Reconnect)
* Từng thiết bị kết nối MQTT hoàn toàn độc lập với Client ID và Access Token riêng.
* Nếu mất mạng hoặc ngắt kết nối, client tự động reconnect (1–30s). Ngay khi kết nối lại thành công (`on_connect`), thiết bị gửi lại telemetry trạng thái và yêu cầu đồng bộ lại Shared Attributes mới nhất.

### 3.4. Dừng an toàn (Graceful Shutdown)
* Khi bấm `Ctrl+C` (SIGINT/SIGTERM), hệ thống tắt quạt, tắt đèn, gửi telemetry `state = false` lên ThingsBoard rồi mới đóng GPIO và Camera.

### 3.5. Hiển thị Camera qua VNC (Live Preview GUI)
* **Cấu hình:** Chạy kèm cờ `python main.py --preview` (hoặc đặt `CAMERA_PREVIEW=true` trong `.env`).
* **Xem qua VNC:** Cửa sổ OpenCV GUI xuất hiện trực tiếp trên màn hình desktop của Raspberry Pi (hoặc RealVNC Viewer), tự động vẽ bounding box quanh người được phát hiện kèm nhãn HUD thời gian thực.

---

## 4. Kiểm thử Tự động (Unit Tests)

Chạy bộ kiểm thử tự động để kiểm tra bảng chân lý, thời gian trễ và logic RPC mà không cần phần cứng thật:

```bash
# Chạy toàn bộ test
python -m unittest discover tests

# Hoặc chạy riêng file test logic
python -m unittest tests/test_logic.py

# Kiểm tra logic nạp cấu hình và validation
python -m unittest tests/test_config.py
```
