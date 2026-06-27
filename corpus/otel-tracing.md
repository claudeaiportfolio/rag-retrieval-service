# Traces

Traces give us the big picture of what happens when a request is made to an application. Whether your application is a monolith with a single database or a sophisticated mesh of services, traces are essential to understanding the full "path" a request takes in your application.

## Spans

A span represents a unit of work or operation. Spans are the building blocks of traces. In OpenTelemetry, they include the following information:

- Name
- Parent span ID (empty for root spans)
- Start and end timestamps
- Span context
- Attributes
- Span events
- Span links
- Span status

### Span context

Span context is an immutable object on every span that contains the trace ID, span ID, trace flags, and trace state. Span context is the part of a span that is serialised and propagated alongside distributed context and baggage.

### Attributes

Attributes are key-value pairs that contain metadata that you can use to annotate a span to carry information about the operation it is tracking.

For example, if a span tracks an operation that adds an item to a user's shopping cart in an e-commerce system, you can capture the user ID, the ID of the item being added, and the cart ID.

OpenTelemetry's semantic conventions provide standard names for common attributes like HTTP method, URL, status code, and span kind.

## Sampling

Sampling is a process that controls the volume of telemetry data your system generates and ingests. There are two main types: head sampling and tail sampling.

- Head sampling decides whether to sample a trace at the beginning, before the spans are created.
- Tail sampling decides at the end of a trace, with all data available. This is more accurate but harder to implement.

The collector tail-sampling processor is the most flexible way to implement tail-based sampling.
