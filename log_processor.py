from kafka import KafkaConsumer
import json
import requests
from prometheus_client import CollectorRegistry, Counter, Histogram, push_to_gateway

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = 'localhost:9092'
API_ACCESS_TOPIC = 'api_access_logs'

# Prometheus Configuration
PROMETHEUS_PUSHGATEWAY = 'http://localhost:9090'
registry = CollectorRegistry()
request_count = Counter('api_request_count', 'Count of API requests', ['endpoint', 'method'], registry=registry)
response_time_histogram = Histogram('api_response_time', 'Response time of API requests', ['endpoint', 'method'], registry=registry)

# Loki Configuration
LOKI_URL = 'http://localhost:3100/loki/api/v1/push'

# Initialize Kafka Consumer
consumer = KafkaConsumer(
    API_ACCESS_TOPIC,
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)

def push_to_loki(log):
    """Send log to Loki."""
    try:
        headers = {'Content-Type': 'application/json'}
        payload = {
            "streams": [
                {
                    "stream": {"job": "api_logs"},
                    "values": [[str(int(log['timestamp'] * 1e9)), json.dumps(log)]]
                }
            ]
        }
        response = requests.post(LOKI_URL, headers=headers, json=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to push log to Loki: {e}")

def process_log(log):
    """Process log and push to Prometheus and Loki."""
    try:
        # Push metrics to Prometheus
        request_count.labels(endpoint=log['endpoint'], method=log['method']).inc()
        response_time_histogram.labels(endpoint=log['endpoint'], method=log['method']).observe(log['response_time'])
        push_to_gateway(PROMETHEUS_PUSHGATEWAY, job='api_metrics', registry=registry)

        # Push log to Loki
        push_to_loki(log)
    except Exception as e:
        print(f"Error processing log: {e}")

# Consume logs
for message in consumer:
    process_log(message.value)
