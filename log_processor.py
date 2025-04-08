from kafka import KafkaConsumer
import json
import requests
import time
from prometheus_client import CollectorRegistry, Counter, Histogram, push_to_gateway

# Configuration
KAFKA_BOOTSTRAP_SERVERS = 'localhost:9092'
API_ACCESS_TOPIC = 'api_access_logs'
PROMETHEUS_PUSHGATEWAY = 'http://localhost:9091'
LOKI_URL = 'http://localhost:3100/loki/api/v1/push'

# Feature flags
ENABLE_PROMETHEUS = True
ENABLE_LOKI = True

# Prometheus Metrics
registry = CollectorRegistry()
request_count = Counter('api_request_count', 'Count of API requests', ['endpoint', 'method'], registry=registry)
response_time_histogram = Histogram('api_response_time', 'Response time of API requests', ['endpoint', 'method'], registry=registry)
error_count = Counter('api_error_count', 'Count of API errors', ['endpoint', 'status_code', 'error_type'], registry=registry)

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

def check_services():
    """Verify services are accessible before starting with retries."""
    services_status = {}
    max_attempts = 3
    attempt_delay = 5  # seconds between attempts

    if ENABLE_PROMETHEUS:
        for attempt in range(max_attempts):
            try:
                response = requests.get(PROMETHEUS_PUSHGATEWAY, timeout=5)
                services_status['prometheus'] = response.status_code == 200
                print(f"Prometheus Pushgateway {'accessible' if services_status['prometheus'] else 'inaccessible'} at {PROMETHEUS_PUSHGATEWAY}")
                break
            except requests.exceptions.RequestException as e:
                print(f"WARNING: Prometheus Pushgateway not accessible (attempt {attempt + 1}/{max_attempts}): {e}")
                if attempt < max_attempts - 1:
                    time.sleep(attempt_delay)
                else:
                    services_status['prometheus'] = False

    if ENABLE_LOKI:
        for attempt in range(max_attempts):
            try:
                response = requests.get(f"{LOKI_URL.split('/loki/api/v1/push')[0]}/ready", timeout=5)
                services_status['loki'] = response.status_code == 200
                print(f"Loki {'accessible' if services_status['loki'] else 'inaccessible'} at {LOKI_URL}")
                break
            except requests.exceptions.RequestException as e:
                print(f"WARNING: Loki not accessible (attempt {attempt + 1}/{max_attempts}): {e}")
                if attempt < max_attempts - 1:
                    time.sleep(attempt_delay)
                else:
                    services_status['loki'] = False
    
    return services_status

def push_to_prometheus(log):
    """Send metrics to Prometheus Pushgateway with retries."""
    if not ENABLE_PROMETHEUS:
        return False
    
    retries = 0
    while retries < MAX_RETRIES:
        try:
            request_count.labels(endpoint=log['endpoint'], method=log['method']).inc()
            response_time_histogram.labels(endpoint=log['endpoint'], method=log['method']).observe(log['response_time'])
            if log.get('status_code', 200) >= 400:
                error_type = 'client_error' if log['status_code'] < 500 else 'server_error'
                error_count.labels(endpoint=log['endpoint'], status_code=str(log['status_code']), error_type=error_type).inc()
            
            push_to_gateway(PROMETHEUS_PUSHGATEWAY, job='api_metrics', registry=registry)
            return True
        except Exception as e:
            retries += 1
            print(f"Failed to push to Prometheus (attempt {retries}/{MAX_RETRIES}): {e}")
            if retries < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    print(f"ERROR: Could not push to Prometheus after {MAX_RETRIES} attempts")
    return False

def push_to_loki(log):
    """Send log to Loki with retries."""
    if not ENABLE_LOKI:
        return False
    
    retries = 0
    while retries < MAX_RETRIES:
        try:
            headers = {'Content-Type': 'application/json'}
            payload = {
                "streams": [
                    {
                        "stream": {"job": "api_logs", "endpoint": log['endpoint'], "method": log['method']},
                        "values": [[str(int(time.time() * 1e9)), json.dumps(log)]]
                    }
                ]
            }
            response = requests.post(LOKI_URL, headers=headers, json=payload, timeout=5)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            retries += 1
            print(f"Failed to push to Loki (attempt {retries}/{MAX_RETRIES}): {e}")
            if retries < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    print(f"ERROR: Could not push to Loki after {MAX_RETRIES} attempts")
    return False

def process_log(log):
    """Process log and push to available services."""
    results = {'prometheus': push_to_prometheus(log), 'loki': push_to_loki(log)}
    endpoint = log.get('endpoint', 'unknown')
    if not any(results.values()):
        print(f"Failed to process log for {endpoint} - all services unavailable")
    else:
        print(f"Processed log for {endpoint} to: {', '.join(k for k, v in results.items() if v)}")

if __name__ == "__main__":
    print("Waiting for services to start...")
    time.sleep(10)  # Initial delay to let services initialize
    print("Checking services...")
    services_status = check_services()
    if not any(services_status.values()):
        print("ERROR: No monitoring services available. Exiting.")
        exit(1)

    print(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}...")
    try:
        consumer = KafkaConsumer(
            API_ACCESS_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest'
        )
        print("Kafka consumer started successfully")
    except Exception as e:
        print(f"Failed to connect to Kafka: {e}")
        exit(1)

    print("Consuming logs...")
    for message in consumer:
        process_log(message.value)