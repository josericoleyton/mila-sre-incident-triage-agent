# eShop System Context

## Overview

The eShop is a reference .NET e-commerce application that demonstrates cloud-native microservices
architecture. It is used as the primary platform under SRE monitoring. Understanding its structure
is essential for accurate incident triage.

## Architecture

### Orchestration
- Built with **.NET Aspire** for service orchestration, health checking, and local development
- All services are containerised and coordinated via the Aspire AppHost project
- Service discovery is handled by Aspire's built-in resource registry

### Microservices
| Service | Technology | Responsibility |
|---|---|---|
| **Catalog.API** | ASP.NET Core / EF Core | Product catalogue, search, inventory |
| **Basket.API** | ASP.NET Core / Redis | Shopping basket CRUD, per-user caching |
| **Ordering.API** | ASP.NET Core / EF Core | Order lifecycle, CQRS command/query split |
| **Identity.API** | ASP.NET Core Identity / Duende IdentityServer | OAuth2 / OIDC authentication, JWT issuance |
| **WebApp** | Blazor Server | Customer-facing storefront UI |
| **Mobile.Bff** | ASP.NET Core | Backend-for-frontend for mobile clients |
| **WebhookClient** | ASP.NET Core | Receives order status webhook callbacks |
| **EventBus** | RabbitMQ abstraction | Async integration event routing |

### Communication Patterns
- **gRPC**: Internal service-to-service calls (e.g., Basket → Catalog for price lookup)
- **HTTP REST**: External API consumers and BFF→API calls
- **RabbitMQ**: Asynchronous integration events (order placed, stock confirmed, payment processed)
- **SignalR**: Real-time order status updates pushed to the Blazor UI

### Data Stores
| Store | Used By | Notes |
|---|---|---|
| **PostgreSQL** | Catalog.API, Ordering.API | Primary relational store; EF Core migrations |
| **Redis** | Basket.API | Per-user basket cache; key expiry used for session TTL |
| **SQL Server** | Identity.API | ASP.NET Identity tables |

## Key Architectural Patterns

### CQRS (Ordering.API)
- Commands handled by MediatR command handlers (e.g., `CreateOrderCommandHandler`)
- Queries return lightweight DTOs, bypassing the domain model
- Domain events raised inside aggregates, dispatched post-persistence

### Domain Events & Integration Events
- **Domain events** are internal to Ordering bounded context (e.g., `OrderStartedDomainEvent`)
- **Integration events** cross service boundaries via RabbitMQ (e.g., `OrderStatusChangedToAwaitingValidationIntegrationEvent`)
- Failure to deserialise an integration event will cause the consumer to dead-letter the message

### Health Checks
- Every service exposes `/health` (liveness) and `/health/ready` (readiness) endpoints
- Aspire dashboard aggregates health status; failures here surface as startup or runtime alerts

## Common Error Sources for SRE Triage

### gRPC
- `StatusCode.Unavailable` — target service not reachable; check container/network state
- `StatusCode.DeadlineExceeded` — latency spike or CPU starvation on the downstream service
- Certificate / TLS errors in non-dev environments

### Database
- EF Core migration failures on startup (schema mismatch after deploy)
- PostgreSQL connection pool exhaustion under load
- Identity.API SQL Server connection string misconfiguration blocks all logins

### Event Bus (RabbitMQ)
- Deserialisation errors when event schema changes without a compatible migration
- Dead-letter queue growth indicates persistent consumer failures
- Exchange or queue misconfiguration after infrastructure reprovisioning

### Configuration / AppSettings
- Missing or wrong `ConnectionStrings` section causes startup crashes
- `ASPNETCORE_ENVIRONMENT` mismatch (Development vs Production) changes feature flags and logging
- Secrets not injected (Docker secrets, env vars) result in null-reference exceptions at startup

### Docker / Networking
- Bridge network DNS failures between containers (service name resolution)
- Port mapping conflicts on the host
- Volume mount permission issues for PostgreSQL data directory

### Basket / Redis
- Redis `CONNECTIONTIMEOUT` or `WRONGTYPE` errors indicate cache corruption or key collision
- Basket data loss on Redis restart if persistence (AOF/RDB) is not configured

### Identity / Authentication
- Expired or misconfigured signing certificates cause JWT validation failures across all services
- CORS misconfiguration in Identity.API blocks browser-based token requests from WebApp
