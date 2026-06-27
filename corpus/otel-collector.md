# OpenTelemetry Collector

The OpenTelemetry Collector offers a vendor-agnostic implementation of how to receive, process and export telemetry data. It removes the need to run, operate, and maintain multiple agents/collectors.

## Components

The Collector consists of three components that access telemetry data: receivers, processors, and exporters. These components can then be wired together using pipelines that can be defined via YAML configuration.

### Receivers

A receiver, which can be push or pull-based, is how data gets into the Collector. Receivers may support one or more data sources. For example, the OTLP receiver accepts traces, metrics and logs.

### Processors

Processors take the data collected by receivers and modify or transform it before sending it to the exporters. Processors can be configured to do things like batching telemetry data, attaching attributes, filtering data, sampling, or memory limiting.

### Exporters

An exporter, which can be push or pull-based, is how you send data to one or more backends/destinations. Exporters may support one or more data sources. For example, the OTLP exporter sends data to OTLP-compatible backends.

## Deployment models

The Collector has two primary deployment models:

- As an agent — instance running with the application or on the same host as the application
- As a gateway — one or more instances running as a standalone service per cluster, datacenter or region

A common deployment uses the agent-gateway pattern: agents collect data from applications and forward to a gateway that fans out to backends.

## Configuration

The configuration is broken into sections, listing the receivers, processors, exporters, extensions and pipelines. The pipelines section combines the receivers, processors and exporters into the data flow.
