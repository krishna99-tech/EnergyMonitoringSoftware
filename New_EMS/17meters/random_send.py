import json
import random
import time
import socket
from datetime import datetime

# ================= CONFIGURATION =================
DEVICE_ID = "Automotive"
TOTAL_METERS = 17

# Meter configuration (matching your ESP32 setup)
# 0 = Schneider, 1 = Elmeasure
meters = [
    {"id": 18, "type": "ELMEASURE"},
    {"id": 2, "type": "SCHNEIDER"},
    {"id": 3, "type": "SCHNEIDER"},
    {"id": 4, "type": "SCHNEIDER"},
    {"id": 5, "type": "SCHNEIDER"},
    {"id": 6, "type": "SCHNEIDER"},
    {"id": 7, "type": "SCHNEIDER"},
    {"id": 8, "type": "SCHNEIDER"},
    {"id": 9, "type": "ELMEASURE"},
    {"id": 10, "type": "ELMEASURE"},
    {"id": 11, "type": "ELMEASURE"},
    {"id": 12, "type": "ELMEASURE"},
    {"id": 13, "type": "ELMEASURE"},
    {"id": 14, "type": "ELMEASURE"},
    {"id": 15, "type": "ELMEASURE"},
    {"id": 16, "type": "ELMEASURE"},
    {"id": 17, "type": "ELMEASURE"}
]

# UDP Configuration
UDP_IP = "192.168.29.139"  # Your remote IP
UDP_PORT = 6503

# Simulation settings
OFFLINE_PROBABILITY = 0.05  # 5% chance a meter goes offline
KWH_RANGE = (0, 10000)  # kWh range
DRIFT_RATE = 0.1  # Max drift percentage per reading

# ================= METER SIMULATION CLASS =================
class MeterSimulator:
    def __init__(self, meter_id, meter_type):
        self.id = meter_id
        self.type = meter_type
        self.kwh = random.uniform(KWH_RANGE[0], KWH_RANGE[1])
        self.previous_kwh = self.kwh
        self.status = True
        
    def update_reading(self):
        """Update kWh reading with realistic drift"""
        # Save previous reading
        self.previous_kwh = self.kwh
        
        # Random drift (±DRIFT_RATE%)
        drift = random.uniform(-DRIFT_RATE, DRIFT_RATE)
        drift_amount = self.kwh * drift / 100
        
        # Add small random increment (energy consumption)
        increment = random.uniform(0, 5)  # 0-5 kWh increase
        
        self.kwh += drift_amount + increment
        
        # Ensure non-negative
        self.kwh = max(0, self.kwh)
        
        return self.kwh
    
    def simulate_status(self):
        """Simulate meter online/offline status"""
        if random.random() < OFFLINE_PROBABILITY:
            self.status = False
        else:
            self.status = True
        return self.status
    
    def get_reading(self):
        """Get current meter reading with status"""
        self.simulate_status()
        
        if self.status:
            self.update_reading()
            return {
                "id": self.id,
                "status": "OK",
                "kwh": round(self.kwh, 2)
            }
        else:
            return {
                "id": self.id,
                "status": "OFFLINE"
            }

# ================= DATA GENERATOR =================
class DataGenerator:
    def __init__(self):
        self.device_id = DEVICE_ID
        self.meters = []
        
        # Initialize meters
        for meter in meters:
            self.meters.append(
                MeterSimulator(meter["id"], meter["type"])
            )
    
    def generate_json(self):
        """Generate complete JSON payload"""
        data = {
            "device": self.device_id,
            "timestamp": datetime.now().isoformat(),
            "meters": []
        }
        
        # Get readings from all meters
        for meter in self.meters:
            reading = meter.get_reading()
            data["meters"].append(reading)
        
        return data
    
    def print_readings(self):
        """Print formatted readings to console"""
        print("\n" + "="*60)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        for meter in self.meters:
            status = meter.status
            print(f"Meter ID: {meter.id:2d} | Type: {meter.type:10} | Status: ", end="")
            
            if status:
                print(f"OK     | kWh: {meter.kwh:10.2f}")
            else:
                print("OFFLINE")
    
    def get_json_string(self):
        """Get JSON as string"""
        data = self.generate_json()
        return json.dumps(data, ensure_ascii=False)

# ================= UDP SENDER =================
class UDPSender:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    def send(self, message):
        """Send UDP message"""
        try:
            self.sock.sendto(message.encode('utf-8'), (self.ip, self.port))
            return True
        except Exception as e:
            print(f"UDP Send Error: {e}")
            return False
    
    def close(self):
        self.sock.close()

# ================= MAIN SIMULATION =================
def main():
    print("="*60)
    print("METER DATA SIMULATOR")
    print("="*60)
    print(f"Sending to: {UDP_IP}:{UDP_PORT}")
    print(f"Device ID: {DEVICE_ID}")
    print(f"Total Meters: {TOTAL_METERS}")
    print(f"Offline Probability: {OFFLINE_PROBABILITY*100}%")
    print("="*60)
    
    # Initialize generator and sender
    generator = DataGenerator()
    sender = UDPSender(UDP_IP, UDP_PORT)
    
    try:
        while True:
            # Generate data
            json_data = generator.get_json_string()
            
            # Print to console
            generator.print_readings()
            print(f"\nJSON Payload:\n{json_data}")
            
            # Send via UDP
            success = sender.send(json_data)
            
            if success:
                print(f"\n✓ UDP Sent successfully")
            else:
                print(f"\n✗ UDP Send failed")
            
            # Wait before next reading
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\nSimulation stopped by user")
    finally:
        sender.close()
        print("UDP socket closed")

# ================= RUN =================
if __name__ == "__main__":
    main()