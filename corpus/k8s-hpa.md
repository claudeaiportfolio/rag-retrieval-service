# Horizontal Pod Autoscaling

In Kubernetes, a HorizontalPodAutoscaler automatically updates a workload resource (such as a Deployment or StatefulSet), with the aim of automatically scaling the workload to match demand.

Horizontal scaling means that the response to increased load is to deploy more Pods. This is different from vertical scaling, which for Kubernetes would mean assigning more resources (for example: memory or CPU) to the Pods that are already running for the workload.

## How does a HorizontalPodAutoscaler work

The HorizontalPodAutoscaler controller, running within the Kubernetes control plane, periodically adjusts the desired scale of its target (for example, a Deployment) to match observed metrics such as average CPU utilization, average memory utilization, or any other custom metric you specify.

The common use for HorizontalPodAutoscaler is to configure it to fetch metrics from aggregated APIs (`metrics.k8s.io`, `custom.metrics.k8s.io`, or `external.metrics.k8s.io`).

## Algorithm details

From the most basic perspective, the HorizontalPodAutoscaler controller operates on the ratio between desired metric value and current metric value:

```
desiredReplicas = ceil[currentReplicas * (currentMetricValue / desiredMetricValue)]
```

For example, if the current metric value is 200m, and the desired value is 100m, the number of replicas will be doubled.

## Configurable scaling behavior

If you use the v2 HorizontalPodAutoscaler API, you can use the behavior field to configure separate scale-up and scale-down behaviors.

## Considerations for KEDA

KEDA extends Kubernetes HPA with event-driven autoscaling using a ScaledObject CR. KEDA can scale workloads to zero, which a plain HPA cannot. It works alongside the HPA — KEDA creates a managed HPA internally for the metric ranges it covers.
