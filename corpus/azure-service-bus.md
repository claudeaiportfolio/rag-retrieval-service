# Azure Service Bus

Azure Service Bus is a fully managed enterprise message broker with message queues and publish-subscribe topics. Service Bus is used to decouple applications and services from each other.

## Queues vs Topics

A queue allows processing of a message by a single consumer. Multiple receivers can compete for messages, but each message is delivered to exactly one consumer that takes responsibility for processing it.

A topic provides a one-to-many form of communication, in a publish/subscribe pattern. Useful for scaling to large numbers of recipients.

## Dead-letter queue

The dead-letter queue (DLQ) is a sub-queue that holds messages that can't be delivered to any receiver or that couldn't be processed. The two events that move a message to the DLQ are:

- `MaxDeliveryCount` exceeded — the message has been received more than the configured number of times. The default is 10.
- `MessageExpiration` — when `DeadLetteringOnMessageExpiration` is true, messages that exceed their TTL land in the DLQ.

The DLQ is enabled by default for both events on Standard and Premium tiers; just configure `max_delivery_count` and `dead_lettering_on_message_expiration` to govern when messages are forwarded.

## Authentication

For workload identity scenarios, applications acquire an OAuth 2 token from Azure Active Directory and present it to Service Bus. Service Bus authorises the token against role assignments — typically `Azure Service Bus Data Sender` for producers and `Azure Service Bus Data Receiver` for consumers — and no shared access signature key is needed.

The `local_auth_enabled = false` flag on the namespace disables SAS entirely.

## Message size limits

The Standard tier supports messages up to 256 KB. The Premium tier supports up to 100 MB. For larger payloads, store the body in Blob Storage and put a reference in the message body.
