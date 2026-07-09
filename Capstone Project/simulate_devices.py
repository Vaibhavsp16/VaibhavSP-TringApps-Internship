import json
import time
import random
import sys
from datetime import datetime

try:
    import requests
except ImportError:
    print("Error: The 'requests' library is required to run this simulator.")
    print("Please install it by running: pip install requests")
    sys.exit(1)

API_ENDPOINT = input("Enter your API Gateway Endpoint URL (from outputs.tf): ").strip()
if not API_ENDPOINT.endswith('/telemetry'):
    API_ENDPOINT = f"{API_ENDPOINT.rstrip('/')}/telemetry"

devices = ["api-gateway-prod", "auth-service-pod", "pdf-generator-worker"]

print(f"\nServerWatch APM Simulator Initialized against: {API_ENDPOINT}")
print("Press Ctrl+C to terminate the simulation at any time.\n")

iteration = 0
try:
    while True:
        iteration += 1
        print(f"--- Server Metric Broadcast cycle #{iteration} ---")
        
        for device in devices:
            latency = round(random.uniform(50.0, 150.0), 1)
            cpu = round(random.uniform(20.0, 60.0), 1)
            memory = round(random.uniform(40.0, 75.0), 1)
            
            if device == "api-gateway-prod" and iteration % 6 == 0:
                latency = round(random.uniform(260.0, 350.0), 1)
                print(f"[INCIDENT TRIGGERED] Simulating latency spike on {device}...")
            elif device == "auth-service-pod" and iteration % 6 == 0:
                cpu = round(random.uniform(91.0, 98.0), 1)
                print(f"[INCIDENT TRIGGERED] Simulating CPU overload on {device}...")
            elif device == "pdf-generator-worker" and iteration % 6 == 0:
                memory = round(random.uniform(96.0, 99.0), 1)
                print(f"[INCIDENT TRIGGERED] Simulating Out-Of-Memory load on {device}...")
                
            payload = {
                "device_id": device,
                "latency": latency,
                "cpu_utilization": cpu,
                "memory_utilization": memory,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "submitted_by": "System Simulator"
            }
            
            try:
                headers = {"Content-Type": "application/json"}
                response = requests.post(API_ENDPOINT, data=json.dumps(payload), headers=headers, timeout=5)
                
                if response.status_code in [200, 201, 202]:
                    print(f" SUCCESS: {device} | CPU: {cpu}% | RAM: {memory}% | Latency: {latency}ms | Status: {response.status_code}")
                else:
                    print(f" FAILED: {device} | Server returned code: {response.status_code} | Details: {response.text}")
            except Exception as conn_err:
                print(f" CONNECTION ERROR on {device}: {str(conn_err)}")
                
        time.sleep(5)
        print()

except KeyboardInterrupt:
    print("\nSimulation terminated. Server telemetry broadcast stopped.")
