import requests
import pandas as pd
from google.transit import gtfs_realtime_pb2

# 1. Tải dữ liệu trực tiếp từ Adelaide Metro
url = "https://gtfs.adelaidemetro.com.au/v1/realtime/trip_updates"
headers = {"accept": "application/x-google-protobuf"}
response = requests.get(url, headers=headers)

if response.status_code == 200:
    # 2. Giải mã Protobuf
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)
    
    parsed_data = []
    
    # 3. Bóc tách dữ liệu lồng nhau thành dạng bảng flat
    for entity in feed.entity:
        if entity.HasField('trip_update'):
            trip_update = entity.trip_update
            trip_id = trip_update.trip.trip_id
            route_id = trip_update.trip.route_id
            
            # Duyệt qua từng điểm dừng (Stop Time Updates) trong chuyến đó
            for stop_update in trip_update.stop_time_update:
                stop_id = stop_update.stop_id
                stop_sequence = stop_update.stop_sequence
                
                # Lấy thời gian trễ/đến (nếu có)
                arrival_time = stop_update.arrival.time if stop_update.HasField('arrival') else None
                arrival_delay = stop_update.arrival.delay if stop_update.HasField('arrival') else None
                
                parsed_data.append({
                    "Trip ID": trip_id,
                    "Route ID": route_id,
                    "Stop ID": stop_id,
                    "Stop Sequence": stop_sequence,
                    "Arrival Time (Epoch)": arrival_time,
                    "Delay (Seconds)": arrival_delay
                })
                
    # 4. Xuất ra file CSV
    df = pd.DataFrame(parsed_data)
    df.to_csv("adelaide_trip_updates.csv", index=False)
    print("Xong rồi! File 'adelaide_trip_updates.csv' đã được tạo thành công.")
else:
    print(f"Không thể lấy dữ liệu. Mã lỗi: {response.status_code}")