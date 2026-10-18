# Chi tiết Chức năng & Logic Hoạt động - Smart Room Lite

Tài liệu tổng hợp toàn bộ tính năng, luồng dữ liệu và logic vận hành của dự án **Smart Room Lite** chạy trên Raspberry Pi 4B kết nối với nền tảng **ThingsBoard**.

---

## 1. Kiến trúc Tổng quan (Device-level Attributes)

Toàn bộ **Shared Attributes** hiện được cấu hình trực tiếp trên từng **Device** tương ứng của ThingsBoard (không phụ thuộc Asset):

| Thiết bị | Phần cứng | Dữ liệu gửi lên (Telemetry) | Shared Attributes nhận về | RPC hỗ trợ |
| :--- | :--- | :--- | :--- | :--- |
| **A101 Environment Sensor** | Cảm biến DHT11 | `temperature`, `humidity` (định kỳ) | `temperatureThreshold` (float, °C) | - |
| **A101 Presence Detector** | Camera CSI + OpenCV | `personDetected` (chỉ gửi khi đổi) | `absenceTimeout` (float, giây) | - |
| **A101 Smart Fan** | Động cơ DC (L298N) | `state` (`true`/`false`) | `autoMode` (boolean) | `getState`, `setState` |
| **A101 Smart Light** | Đèn LED | `state` (`true`/`false`) | `autoMode` (boolean) | `getState`, `setState` |

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
* Dashboard ThingsBoard (hoặc widget công tắc) gửi RPC `getState` (hỗ trợ cả `get_state`, `getValue`).
* Raspberry Pi đọc trạng thái thực tế của chân phần cứng và phản hồi ngay lập tức:
  ```json
  {"state": true, "value": true, "autoMode": false}
  ```

#### B. Bật/Tắt thiết bị (`setState` / `setValue` / `toggle`)
* **Hỗ trợ đa dạng định dạng tham số RPC:** Nhận boolean (`true`/`false`), string (`"true"`, `"false"`, `"on"`, `"off"`, `"1"`, `"0"`), hoặc dictionary/object từ widget ThingsBoard (`{"value": true}`, `{"state": true}`, `{"enabled": true}`).
* **Điều kiện Tiên quyết (Precondition):**
  * Lệnh bật/tắt thủ công **chỉ được phép thực thi khi `autoMode = false`**.
  * Nếu thiết bị đang ở chế độ tự động (`autoMode = true`), Raspberry Pi sẽ **từ chối lệnh (reject)** và trả về thông báo lỗi, yêu cầu người dùng tắt `autoMode` trước:
    ```json
    {
      "error": "Manual control is disabled while autoMode is True on fan. Turn off autoMode first.",
      "state": false,
      "value": false,
      "autoMode": true,
      "success": false
    }
    ```
  * Khi `autoMode = false`: Thiết bị thực thi lệnh bật/tắt ngay lập tức và đồng bộ telemetry trạng thái mới lên ThingsBoard:
    ```json
    {"state": true, "value": true, "autoMode": false, "success": True}
    ```

#### C. Điều khiển Chế độ Tự động (`autoMode`) từ ThingsBoard
Có 2 cách chuẩn để thay đổi `autoMode` từ xa trên ThingsBoard:

1. **Cách 1: Sử dụng Widget Switch RPC trên Dashboard (Khuyên dùng)**
   - Thêm widget **Control > Switch control** (hoặc Toggle/Round Switch) vào Dashboard.
   - Cấu hình widget:
     - **Get value method:** `getAutoMode` (hoặc `getState`)
     - **Set value method:** `setAutoMode`
     - **Value type:** Boolean
   - Khi bạn bấm gạt công tắc này, ThingsBoard gửi RPC `setAutoMode(true/false)`. Pi sẽ cập nhật ngay lập tức và đồng bộ trạng thái về lại Dashboard.

2. **Cách 2: Sử dụng Shared Attributes trên ThingsBoard**
   - Vào **ThingsBoard > Devices > Chọn A101 Smart Fan / Smart Light > Tab Attributes**.
   - Trong dropdown Scope, **bắt buộc chọn `Shared attributes`** (TUYỆT ĐỐI KHÔNG sửa trong `Client attributes` vì ThingsBoard không gửi Client Attributes ngược xuống thiết bị).
   - Thêm hoặc sửa thuộc tính:
     - Key: `autoMode` (hỗ trợ cả `auto_mode`, `automode`)
     - Type: `Boolean`
     - Value: `true` hoặc `false`
   - Khi lưu, ThingsBoard sẽ tự động bắn bản tin MQTT xuống Pi cập nhật tức thì.

3. **Đồng bộ Đa kênh (Dual Sync):**
   - Mỗi khi `autoMode` thay đổi (do RPC, Shared Attribute hay Manual Override), Pi gửi cập nhật đồng thời lên cả **Client Attributes** và **Telemetry** (`v1/devices/me/telemetry`). Mọi widget hiển thị trạng thái trên Dashboard đều được làm mới ngay lập tức.

---

## 3. Các Cơ chế Xử lý & Độ tin cậy (Resilience)

### 3.1. Phân tách và Đồng bộ Attributes từng Device
* **Environment Sensor:** Gửi yêu cầu lấy `temperatureThreshold` khi vừa kết nối (`request_shared_attributes`). Khi người dùng đổi ngưỡng trên web, thuộc tính lập tức được cập nhật vào bộ nhớ `RoomState`.
* **Presence Detector:** Gửi yêu cầu lấy `absenceTimeout` khi kết nối. Cập nhật ngay khi có thay đổi.
* **Smart Fan & Smart Light:** Tự động request `autoMode` của chính mình khi kết nối MQTT thành công.

### 3.2. Lọc nhiễu nhận diện người (Camera Haar Cascade)
* **`confirm_frames = 2`:** Phải phát hiện thấy người liên tiếp 2 frame mới báo `personDetected = True`.
* **`hold_seconds = 2.0s`:** Giữ trạng thái có người thêm 2 giây sau frame cuối cùng thấy người để chống hiện tượng nhấp nháy khung hình.

### 3.3. Tự phục hồi kết nối (Auto Reconnect)
* Từng thiết bị kết nối MQTT hoàn toàn độc lập với Client ID và Access Token riêng.
* Nếu mất kết nối, client tự động reconnect (1–30s). Ngay khi kết nối lại thành công (`on_connect`), thiết bị lập tức gửi lại `state` và request lại Shared Attributes mới nhất từ ThingsBoard.

### 3.4. Dừng an toàn (Graceful Shutdown)
* Khi bấm `Ctrl+C` (SIGINT/SIGTERM), hệ thống tắt quạt, tắt đèn, gửi telemetry `state = false` lên ThingsBoard rồi mới đóng GPIO và Camera.

### 3.5. Hiển thị Camera qua VNC (Live Preview GUI)
* **Cấu hình trong `.env`:** `CAMERA_PREVIEW=true` (hoặc khởi động kèm cờ: `python main.py --preview`).
* **Xem qua VNC:** Cửa sổ OpenCV GUI xuất hiện trực tiếp trên màn hình desktop của Raspberry Pi, cho phép theo dõi trực quan qua RealVNC Viewer.
* **Tính năng:** Tự động vẽ bounding box quanh người được phát hiện kèm nhãn HUD thời gian thực (`State: PERSON DETECTED` hoặc `State: VACANT`), tối ưu hóa render 50ms mượt mà không làm đơ giao diện VNC.

---

## 4. Công cụ Kiểm tra Phần cứng tích hợp

Chạy trực tiếp từ file `main.py` để test nhanh phần cứng tại chỗ:

```bash
# Kiểm tra đèn LED (nháy 3 lần)
python main.py --check led

# Kiểm tra quạt DC (chạy 3 giây rồi tắt)
python main.py --check fan

# Kiểm tra cảm biến DHT11 (đọc mẫu 6 lần)
python main.py --check dht

# Kiểm tra Camera nhận diện người (mở 15 giây)
python main.py --check camera

# Kiểm tra lần lượt toàn bộ linh kiện
python main.py --check all
```
