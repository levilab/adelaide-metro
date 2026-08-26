import re
import pandas as pd

def parse_gtfs_textproto(file_path):
    records = []
    
    # Các biến tạm để lưu trạng thái khi đọc từng dòng
    current_trip = {}
    current_stop = {}
    vehicle_id = ""
    
    # Trạng thái đang đứng ở block nào
    in_trip = False
    in_stop = False
    in_vehicle = False

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            
            # Phát hiện bắt đầu các block lồng nhau
            if line.startswith('trip {'):
                in_trip = True
            elif line.startswith('stop_time_update {'):
                in_stop = True
                current_stop = {}
            elif line.startswith('vehicle {'):
                in_vehicle = True
                vehicle_id = ""
            
            # Phát hiện đóng block '}'
            elif line == '}':
                if in_stop:
                    in_stop = False
                    # Khi đóng 1 trạm dừng, gộp dữ liệu trip + xe + trạm vào danh sách
                    record = {
                        "trip_id": current_trip.get("trip_id", ""),
                        "route_id": current_trip.get("route_id", ""),
                        "direction_id": current_trip.get("direction_id", ""),
                        "start_date": current_trip.get("start_date", ""),
                        "vehicle_id": vehicle_id,
                        "stop_sequence": current_stop.get("stop_sequence", ""),
                        "stop_id": current_stop.get("stop_id", ""),
                        "arrival_time": current_stop.get("time", "")
                    }
                    records.append(record)
                elif in_trip:
                    in_trip = False
                elif in_vehicle:
                    in_vehicle = False
            
            # Đọc các cặp key-value dữ liệu
            else:
                match = re.match(r'([\w_]+):\s*(.*)', line)
                if match:
                    key = match.group(1)
                    val = match.group(2).strip('"') # Bỏ dấu ngoặc kép nếu có
                    
                    if in_stop:
                        current_stop[key] = val
                    elif in_trip:
                        current_trip[key] = val
                    elif in_vehicle and key == "id":
                        vehicle_id = val

    # Chuyển đổi list thành bảng DataFrame
    df = pd.DataFrame(records)
    
    # Định dạng lại cột thời gian từ số Epoch thành ngày giờ đọc được (Múi giờ Adelaide)
    if not df.empty and 'arrival_time' in df.columns:
        df['arrival_time'] = pd.to_numeric(df['arrival_time'], errors='coerce')
        df['arrival_time'] = pd.to_datetime(df['arrival_time'], unit='s', utc=True)
        df['arrival_time'] = df['arrival_time'].dt.tz_convert('Australia/Adelaide').dt.strftime('%Y-%m-%d %H:%M:%S')
        
    return df

# --- CHẠY CHUYỂN ĐỔI ---
# Thay "trip_updates.txt" bằng tên chính xác file text của bạn
input_file = "trip_updates_debug.txt" 

print("Đang xử lý dữ liệu, vui lòng đợi...")
df_result = parse_gtfs_textproto(input_file)

if not df_result.empty:
    # 1. Xuất CSV
    df_result.to_csv("adelaide_realtime.csv", index=False, encoding='utf-8')
    print(f" Thành công! Đã tạo file 'adelaide_realtime.csv' với {len(df_result)} dòng dữ liệu.")
    
    # 2. Xuất Parquet
    df_result.to_parquet("adelaide_realtime.parquet", index=False)
    print(" Thành công! Đã tạo file 'adelaide_realtime.parquet'.")
else:
    print(" Lỗi: Vẫn không tìm thấy dữ liệu hợp lệ trong file. Hãy kiểm tra lại tên file đầu vào.")