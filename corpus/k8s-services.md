# Services

In Kubernetes, a Service is a method for exposing a network application that is running as one or more Pods in your cluster.

A key aim of Services in Kubernetes is that you don't need to modify your existing application to use an unfamiliar service discovery mechanism. You can run code in Pods, whether this is a code designed for a cloud-native world, or an older app you've containerized.

## Defining a Service

A Service in Kubernetes is a REST object, similar to a Pod. Like all of the REST objects, you can POST a Service definition to the API server to create a new instance.

Suppose you have a set of Pods that each listen on TCP port 9376 and are labelled as `app.kubernetes.io/name=MyApp`. You can define a Service to publish that TCP listener.

## Service types

For some parts of your application (for example, frontends) you may want to expose a Service onto an external IP address, that's outside of your cluster.

Kubernetes Service types allow you to specify what kind of Service you want:

- `ClusterIP` — Exposes the Service on a cluster-internal IP. Choosing this value makes the Service only reachable from within the cluster. This is the default that is used if you don't explicitly specify a type for a Service.
- `NodePort` — Exposes the Service on each Node's IP at a static port. A ClusterIP Service, to which the NodePort Service routes, is automatically created.
- `LoadBalancer` — Exposes the Service externally using a cloud provider's load balancer.
- `ExternalName` — Maps the Service to the contents of the externalName field by returning a CNAME record with its value.

## Headless services

Sometimes you don't need load-balancing and a single Service IP. In this case, you can create what are termed "headless" Services, by explicitly specifying `"None"` for the cluster IP address.

You can use a headless Service to interface with other service discovery mechanisms, without being tied to Kubernetes' implementation.

## Discovering services

Kubernetes supports two primary modes of finding a Service — environment variables and DNS.
