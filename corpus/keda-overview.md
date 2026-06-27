# KEDA Overview

KEDA is a Kubernetes-based Event Driven Autoscaler. With KEDA, you can drive the scaling of any container in Kubernetes based on the number of events needing to be processed.

KEDA is a single-purpose and lightweight component that can be added into any Kubernetes cluster. KEDA works alongside standard Kubernetes components like the Horizontal Pod Autoscaler and can extend functionality without overwriting or duplication.

## Architecture

KEDA performs three key roles within Kubernetes:

- Agent — activates and deactivates Kubernetes Deployments to scale to and from zero on no events.
- Metrics — acts as a Kubernetes metrics server that exposes rich event data like queue length or stream lag to the Horizontal Pod Autoscaler to drive scale out.
- Admission Webhooks — automatically validate resource changes to prevent misconfiguration and enforce best practices.

## ScaledObject

A ScaledObject represents the desired mapping between an event source and a Deployment, StatefulSet, or any custom resource that defines /scale subresource.

The minReplicaCount field defines the minimum number of replicas (default 0). When events arrive, KEDA activates the workload and the HPA scales it up. When events stop, KEDA scales it back down to minReplicaCount.

## Authentication

To consume events from authenticated sources like Azure Service Bus or AWS SQS, KEDA needs credentials. The TriggerAuthentication CR provides a re-usable bundle of credentials. With Azure Workload Identity, the TriggerAuthentication references the managed identity client_id and KEDA fetches a fresh token per scaler call — no static secrets.

## Activation and scaling

KEDA has two phases: activation (0 → 1 replica) and scaling (1 → N).

The activationMessageCount metadata controls activation — set it higher than 0 so a single straggler doesn't wake the pool.

The messageCount target drives the HPA-style scaling once activated.
