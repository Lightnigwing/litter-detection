# Monitoring Stack Quickstart

This guide shows the exact command sequence to start and use the litter-detection monitoring stack on Windows.

## 1. Start the monitoring stack

Open PowerShell in the repository root and run:

```powershell
cd C:\Users\Leina\Documents\litter-detection-1\monitoring
docker-compose up -d
docker-compose ps
```

## 2. Check that the services are ready

Run these checks from the same PowerShell window:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:3000/api/health | Select-Object -ExpandProperty StatusCode
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:9090/-/ready | Select-Object -ExpandProperty StatusCode
```

You should see `200` for both.

## 3. Open Grafana and Prometheus

```powershell
Start-Process "http://127.0.0.1:3000"
Start-Process "http://127.0.0.1:9090"
```

Grafana login:

```text
username: admin
password: admin
```

## 4. Run a monitored training test

Go back to the repository root and start a short smoke test:

```powershell
cd C:\Users\Leina\Documents\litter-detection-1
uv run python train.py --run-name monitoring-smoketest --epochs 1
```

For a longer run, increase the epoch count:

```powershell
uv run python train.py --run-name monitoring-fulltest --epochs 3
```

## 5. Verify that training metrics are arriving

In another PowerShell window, check Prometheus for the exported OTel metrics:

```powershell
$pair = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes('admin:admin'))
Invoke-WebRequest -UseBasicParsing -Headers @{Authorization = "Basic $pair"} 'http://127.0.0.1:9090/api/v1/query?query=training_epochs_completed_total' | Select-Object -ExpandProperty Content
Invoke-WebRequest -UseBasicParsing -Headers @{Authorization = "Basic $pair"} 'http://127.0.0.1:9090/api/v1/query?query=training_loss_train_sum' | Select-Object -ExpandProperty Content
Invoke-WebRequest -UseBasicParsing -Headers @{Authorization = "Basic $pair"} 'http://127.0.0.1:9090/api/v1/query?query=training_iou_validation_sum' | Select-Object -ExpandProperty Content
```

## 6. Use the Grafana dashboards

Open Grafana and look for these dashboards:

```text
Litter Detection Training — Operations & Latency
Litter Detection — System Resources
Litter Detection — Model Behavior & Detections
```

If they do not appear immediately, wait a few seconds and refresh the page once.

## 7. Stop the stack

When you are done, shut everything down from the monitoring directory:

```powershell
cd C:\Users\Leina\Documents\litter-detection-1\monitoring
docker-compose down
```

## Optional: clean restart

If you want a full reset of the stack:

```powershell
cd C:\Users\Leina\Documents\litter-detection-1\monitoring
docker-compose down -v
docker-compose up -d
docker-compose ps
```

## Useful URLs

```text
Grafana:            http://127.0.0.1:3000
Prometheus:         http://127.0.0.1:9090
Tempo:              http://127.0.0.1:3200
Loki:               http://127.0.0.1:3100
OTel Collector OTLP http://127.0.0.1:4317
```
