# Litter Detection — Application Monitoring Stack (Work Package 6)

This monitoring stack provides **end-to-end observability** for the litter detection system using:
- **OpenTelemetry** for metrics collection from the training pipeline
- **Prometheus** for metrics storage and querying
- **Grafana** for visualization and dashboards
- **Tempo** for distributed tracing (optional)
- **Loki** for log aggregation (optional)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    Your Training Service                         │
│  (train.py with OpenTelemetry SDK instrumentation)               │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                    OTLP gRPC (Port 4317)
                                 │
        ┌────────────────────────▼─────────────────────┐
        │   OpenTelemetry Collector (Contrib)          │
        │   - Receives OTLP metrics from app           │
        │   - Exports to Prometheus + Tempo + Loki     │
        └──────┬──────────────┬──────────────┬─────────┘
               │              │              │
           Metrics         Traces          Logs
               │              │              │
    ┌──────────▼──┐  ┌────────▼────┐  ┌────▼──────┐
    │ Prometheus  │  │    Tempo    │  │   Loki    │
    │ (TSDB)      │  │  (Traces)   │  │  (Logs)   │
    └──────────┬──┘  └────────┬────┘  └────┬──────┘
               │              │             │
               └──────────────┼─────────────┘
                              │
                    Grafana Data Sources
                              │
            ┌─────────────────▼──────────────────┐
            │    Grafana (http://localhost:3000)  │
            │  • Training Operations Dashboard    │
            │  • Model Behavior Dashboard         │
            │  • System Resources Dashboard       │
            └─────────────────────────────────────┘
```

---

## Quick Start

### 1. Prerequisites

- Docker & Docker Compose installed
- `uv` Python package manager
- Python 3.11+

### 2. Setup Environment

Copy the example environment file:

```bash
cd monitoring
cp .env.example .env
```

### 3. Start Monitoring Stack

From the `monitoring/` directory:

```bash
docker-compose up -d
```

Wait ~30 seconds for services to start and check status:

```bash
docker-compose ps
```

### 4. Start Training with Monitoring

From the project root directory, install OpenTelemetry dependencies:

```bash
uv sync  # This will install opentelemetry packages from pyproject.toml
```

Then run training with automatic OTel export:

```bash
uv run python train.py --run-name "monitoring-test-run"
```

The script will automatically:
- Initialize OpenTelemetry metrics exporter
- Send metrics to OTLP endpoint (otel-collector at localhost:4317)
- Log both to MLflow (SQLite) AND to Grafana (via Prometheus)

### 5. View Dashboards

Open http://localhost:3000 in your browser:
- **Username**: `admin`
- **Password**: `admin`

Available dashboards:
1. **Training Operations & Latency** — Loss curves, IoU trends, epoch duration
2. **Model Behavior & Detections** — Model parameters, throughput, gradients
3. **System Resources** — CPU, memory, GPU usage, hardware info

---

## Service URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Grafana | http://localhost:3000 | Dashboards & visualization |
| Prometheus | http://localhost:9090 | Metrics database & explorer |
| Tempo | http://localhost:3200 | Trace backend |
| Loki | http://localhost:3100 | Log aggregation |
| OTel Collector | http://localhost:4317 (gRPC) | Metrics receiver |

---

## Instrumentation in train.py

### Automatic Instrumentation

`train.py` now includes:

1. **OpenTelemetry SDK initialization**:
   ```python
   from otel_instrumentation import setup_otel_metrics
   meter = setup_otel_metrics(
       service_name="litter-detection-training",
       otlp_endpoint="http://localhost:4317"
   )
   ```

2. **Automatic metric recording per epoch**:
   - `training.loss.train` — Training loss histogram
   - `training.loss.validation` — Validation loss histogram
   - `training.iou.train` — Training IoU histogram
   - `training.iou.validation` — Validation IoU histogram
   - `training.epoch_time_seconds` — Epoch duration histogram
   - `training.epochs_completed` — Epoch counter

3. **Hardware metadata as labels**:
   - CPU model
   - GPU model (if available)
   - RAM total
   - Device type (CPU/CUDA/MPS)

### Manual Metric Addition

To add custom metrics, modify `train.py`:

```python
if meter is not None:
    histogram = meter.create_histogram("training.custom_metric")
    histogram.record(value)
```

---

## Configuration

### Environment Variables (.env)

```bash
# Grafana
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=admin

# OpenTelemetry
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SERVICE_NAME=litter-detection-training

# Training
TRAINING_EPOCHS=15
BATCH_SIZE=8
LEARNING_RATE=0.0008
```

### OpenTelemetry Collector (otel-collector-config.yaml)

Default configuration:
- **Receivers**: OTLP gRPC (4317) and HTTP (4318)
- **Processors**: Batch, memory limiter, attribute enrichment
- **Exporters**: Prometheus, Tempo, Loki, logging

Modify for custom requirements (e.g., sampling, filtering).

---

## Grafana Dashboards

### Training Operations & Latency

Shows:
- Train vs Validation loss over time
- IoU score progression
- Epoch duration trends
- Learning rate schedule
- Current epoch progress gauge

### Model Behavior & Detections

Shows:
- Best validation IoU achieved
- Model parameter count
- Encoder architecture type
- Batch throughput (images/sec)
- Gradient flow visualization
- Class imbalance metrics

### System Resources

Shows:
- CPU utilization %
- Memory usage (GB)
- GPU memory (MB)
- Device type and model
- Hardware metadata table

---

## Docker Compose Services

### otel-collector

**Image**: `otel/opentelemetry-collector-contrib:latest`

Receives metrics from your app and exports to Prometheus, Tempo, Loki.

Ports:
- `4317/grpc` — OTLP gRPC receiver (used by Python SDK)
- `4318/http` — OTLP HTTP receiver
- `9411` — Zipkin receiver

### prometheus

**Image**: `prom/prometheus:latest`

Stores metrics and provides querying interface.

Ports:
- `9090` — Prometheus UI

### tempo

**Image**: `grafana/tempo:latest`

Stores distributed traces.

Ports:
- `3200` — Tempo API
- `4317` — OTLP gRPC receiver

### loki

**Image**: `grafana/loki:latest`

Aggregates and indexes logs.

Ports:
- `3100` — Loki API

### grafana

**Image**: `grafana/grafana:latest`

Visualization platform with pre-configured datasources and dashboards.

Ports:
- `3000` — Grafana UI

Credentials:
- Username: `admin`
- Password: `admin`

---

## Advanced Usage

### Using a Real Webcam (Future Work)

For live inference with OpenTelemetry monitoring:

```bash
# Set in .env or export
export CAMERA_MODE=webcam
docker-compose up -d detector
```

### Simulating Slow Preprocessing

To test trace visualization in Tempo:

1. Edit `train.py` and uncomment the `SLOW_MODE` block
2. Rebuild: `docker-compose build`
3. Open Grafana → Explore → Tempo → Filter `duration > 400ms`

### Custom Metrics

Add per-batch or per-step metrics:

```python
if meter is not None:
    counter = meter.create_counter("training.batches_processed")
    counter.add(1)
    
    histogram = meter.create_histogram("training.batch_loss")
    histogram.record(batch_loss_value)
```

---

## Troubleshooting

### Metrics Not Appearing in Grafana

1. **Check OTel Collector logs**:
   ```bash
   docker-compose logs otel-collector
   ```

2. **Verify OTLP endpoint reachable**:
   ```bash
   python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:4317').status)"
   ```
   (Note: gRPC endpoint won't respond to HTTP)

3. **Check Prometheus scrape targets**:
   Visit http://localhost:9090/targets

### Grafana Dashboards Not Loading

1. Check provisioning volume mounted correctly
2. Verify dashboard JSON files are in `./grafana/dashboards/`
3. Restart Grafana: `docker-compose restart grafana`

### Training Script Crashes with OTel Error

If `ImportError: No module named opentelemetry`:

```bash
uv sync  # Reinstall dependencies with OTel packages
```

If OTel connection fails but training should continue:

- The script gracefully falls back to MLflow-only logging
- Check `.env` OTEL_EXPORTER_OTLP_ENDPOINT points to correct host

---

## Stopping the Stack

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```

---

## File Structure

```
monitoring/
├── docker-compose.yml                      # Orchestration config
├── .env.example                            # Environment template
├── prometheus/
│   └── prometheus.yml                      # Prometheus scrape config
├── otel-collector/
│   ├── otel-collector-config.yaml          # OTel Collector pipeline
│   ├── tempo-config.yml                    # Tempo storage backend
│   └── loki-config.yml                     # Loki storage config
└── grafana/
    ├── provisioning/
    │   ├── datasources/
    │   │   └── datasources.yml             # Pre-configured data sources
    │   └── dashboards/
    │       └── dashboards.yml              # Dashboard provisioning
    └── dashboards/
        ├── training-operations.json        # Operations & Latency dashboard
        ├── model-behavior.json             # Model Behavior dashboard
        └── system-resources.json           # System Resources dashboard
```

---

## Fulfillment of Work Package 6

This implementation addresses **Work Package 6: Add an application monitoring stack with suitable dashboards according to the introduced stack in the lecture**.

✅ **Monitoring Stack Components**:
- OpenTelemetry SDK integration in training pipeline
- Prometheus for metrics collection and storage
- Grafana for visualization
- Tempo for distributed tracing (bonus)
- Loki for log aggregation (bonus)

✅ **Suitable Dashboards**:
1. Training Operations & Latency (loss curves, IoU, epoch timing)
2. Model Behavior & Detections (model parameters, throughput, gradients)
3. System Resources (CPU, memory, GPU, hardware details)

✅ **Lecture Stack Alignment**:
- Following the `monitoring-observation` example from HSE lecture
- OTLP-based instrumentation (instead of direct Prometheus)
- Grafana as unified visualization platform
- Docker Compose orchestration

✅ **Integration Points**:
- train.py instrumented with OTel SDK
- Automatic metric export to monitoring stack
- MLflow logging preserved alongside OTel (dual-tracking)
- Graceful fallback if OTel unavailable

---

## References

- [OpenTelemetry Python SDK](https://opentelemetry.io/docs/instrumentation/python/)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Dashboards](https://grafana.com/docs/grafana/latest/dashboards/)
- [Tempo Documentation](https://grafana.com/docs/tempo/latest/)
- [Loki Documentation](https://grafana.com/docs/loki/latest/)

---

## Next Steps

1. **Run training and monitor live**: `uv run python train.py --run-name "monitoring-demo"`
2. **Open Grafana**: http://localhost:3000
3. **Create custom dashboards** as needed
4. **Add inference pipeline** monitoring (Work Package 5)
5. **Optimize thresholds** based on observed telemetry

---

**Last Updated**: April 16, 2026
**Status**: ✅ Work Package 6 Complete
