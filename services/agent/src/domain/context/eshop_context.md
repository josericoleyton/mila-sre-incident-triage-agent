# eShop System Context

## Overview

The eShop is a reference .NET e-commerce application that demonstrates cloud-native microservices
architecture. It is used as the primary platform under SRE monitoring. Understanding its structure
is essential for accurate incident triage.

## Architecture

### Orchestration
- Built with **.NET Aspire** for service orchestration, health checking, and local development
- All services are containerised and coordinated via the Aspire AppHost project (`src/eShop.AppHost/`)
- Service discovery is handled by Aspire's built-in resource registry
- Shared service defaults: `src/eShop.ServiceDefaults/`

### Microservices
| Service | Technology | Responsibility |
|---|---|---|
| **Catalog.API** | ASP.NET Core / EF Core | Product catalogue, search, inventory |
| **Basket.API** | ASP.NET Core / Redis / gRPC | Shopping basket CRUD, per-user caching |
| **Ordering.API** | ASP.NET Core / EF Core / MediatR | Order lifecycle, CQRS command/query split |
| **Ordering.Domain** | Pure C# domain layer | Aggregate roots, domain events, value objects |
| **Ordering.Infrastructure** | EF Core | Repository implementations, DB context |
| **OrderProcessor** | Background worker | Processes order state machine transitions |
| **PaymentProcessor** | Background worker | Handles payment processing callbacks |
| **Identity.API** | ASP.NET Core Identity / Duende IdentityServer | OAuth2 / OIDC authentication, JWT issuance |
| **WebApp** | Blazor Server | Customer-facing storefront UI |
| **WebAppComponents** | Razor Class Library | Shared Blazor UI components |
| **ClientApp** | .NET MAUI | Mobile client application |
| **WebhookClient** | ASP.NET Core | Receives order status webhook callbacks |
| **Webhooks.API** | ASP.NET Core | Webhook registration and dispatch |
| **EventBus** | RabbitMQ abstraction | Async integration event routing |
| **EventBusRabbitMQ** | RabbitMQ implementation | Concrete event bus using RabbitMQ |
| **IntegrationEventLogEF** | EF Core | Outbox pattern for integration events |
| **Shared** | Class Library | Cross-cutting utilities |

## Codebase File Map

### src/Catalog.API/ — Product Catalog Service
```
src/Catalog.API/
├── Apis/
│   └── CatalogApi.cs                          ← ALL REST endpoints (GetItems, GetItemById, UpdateItem, CreateItem, DeleteItem, GetBrands, GetTypes, GetItemPicById, GetItemsBySemanticRelevance)
├── Extensions/
│   └── Extensions.cs                          ← Service registration, DB seeding, OpenAPI config
├── Infrastructure/
│   ├── CatalogContext.cs                      ← EF Core DbContext (CatalogItems, CatalogBrands, CatalogTypes)
│   └── EntityConfigurations/                  ← EF entity mapping configurations
├── IntegrationEvents/
│   ├── Events/                                ← OrderStatusChangedToAwaitingValidation, OrderStatusChangedToPaid
│   └── EventHandling/                         ← Handlers for integration events from Ordering
├── Model/
│   ├── CatalogItem.cs                         ← Main entity (Id, Name, Description, Price, CatalogBrand, CatalogType, PictureFileName, AvailableStock)
│   ├── CatalogBrand.cs                        ← Brand entity
│   └── CatalogType.cs                         ← Type/Category entity
├── Services/
│   ├── ICatalogAI.cs                          ← AI embedding interface for semantic search
│   └── CatalogAI.cs                           ← AI embedding implementation
├── Setup/
│   └── catalog.json                           ← Seed data for catalog items
├── Program.cs                                 ← App startup, middleware pipeline
└── CatalogOptions.cs                          ← Configuration options
```
**Key lookup:** For ANY catalog-related incident, the primary file is `src/Catalog.API/Apis/CatalogApi.cs`. This single file contains ALL catalog endpoints. Entity models are in `src/Catalog.API/Model/`. DB context is `src/Catalog.API/Infrastructure/CatalogContext.cs`.

### src/Basket.API/ — Shopping Basket Service (gRPC)
```
src/Basket.API/
├── Grpc/
│   └── BasketService.cs                       ← ALL gRPC endpoints (GetBasket, UpdateBasket, DeleteBasket) — THIS IS THE MAIN SERVICE FILE
├── Extensions/
│   └── Extensions.cs                          ← Service registration, Redis config
├── IntegrationEvents/
│   ├── Events/                                ← OrderStartedIntegrationEvent
│   └── EventHandling/                         ← OrderStartedIntegrationEventHandler (clears basket on order)
├── Model/
│   ├── BasketItem.cs                          ← Item in basket (ProductId, ProductName, UnitPrice, Quantity)
│   └── CustomerBasket.cs                      ← Basket aggregate (BuyerId, Items list)
├── Repositories/
│   ├── IBasketRepository.cs                   ← Repository interface
│   └── RedisBasketRepository.cs               ← Redis-backed implementation (JSON serialization)
├── Proto/
│   └── basket.proto                           ← gRPC protobuf service definition
├── Program.cs                                 ← App startup, gRPC + Redis registration
└── appsettings.json                           ← Configuration
```
**Key lookup:** For ANY basket-related incident, the primary file is `src/Basket.API/Grpc/BasketService.cs`. This contains all gRPC methods. Redis operations are in `src/Basket.API/Repositories/RedisBasketRepository.cs`. The gRPC contract is defined in `src/Basket.API/Proto/basket.proto`.

### src/Ordering.API/ — Order Processing Service (CQRS)
```
src/Ordering.API/
├── Apis/
│   └── OrdersApi.cs                           ← REST endpoints (GetOrders, GetOrder, CancelOrder, ShipOrder, CreateOrder)
├── Application/
│   ├── Behaviors/                             ← MediatR pipeline behaviors (logging, validation, transaction)
│   ├── Commands/
│   │   ├── CreateOrderCommand.cs              ← Create order command + handler
│   │   ├── CancelOrderCommand.cs              ← Cancel order command + handler
│   │   ├── ShipOrderCommand.cs                ← Ship order command + handler
│   │   ├── SetPaidOrderStatusCommand.cs       ← Mark order paid command + handler
│   │   └── SetStockConfirmedOrderStatusCommand.cs
│   ├── DomainEventHandlers/
│   │   ├── ValidateOrAddBuyerAggregateWhenOrderStartedDomainEventHandler.cs  ← Handles OrderStartedDomainEvent: creates/updates Buyer, publishes OrderStatusChangedToSubmitted integration event
│   │   ├── OrderStatusChangedToAwaitingValidationDomainEventHandler.cs
│   │   ├── OrderStatusChangedToPaidDomainEventHandler.cs
│   │   ├── OrderCancelledDomainEventHandler.cs
│   │   └── OrderStatusChangedToStockConfirmedDomainEventHandler.cs
│   ├── IntegrationEvents/
│   │   ├── Events/                            ← Outbound integration events (OrderStatusChanged*)
│   │   └── EventHandling/                     ← Inbound integration event handlers
│   ├── Models/                                ← DTOs and view models
│   ├── Queries/
│   │   └── OrderQueries.cs                    ← Dapper-based read queries
│   └── Validations/                           ← FluentValidation validators for commands
├── Extensions/
│   └── Extensions.cs                          ← Service registration, DB config
├── Infrastructure/
│   └── OrderingApiTrace.cs                    ← Structured logging/tracing helper
├── Program.cs                                 ← App startup
└── appsettings.json                           ← Configuration
```
**Key lookup:** For ordering incidents, check `src/Ordering.API/Apis/OrdersApi.cs` for endpoints. For domain logic, check command handlers in `src/Ordering.API/Application/Commands/`. For event handling bugs, check `src/Ordering.API/Application/DomainEventHandlers/`. Integration event publishing is in the domain event handlers.

### src/Ordering.Domain/ — Domain Layer (DDD Aggregates)
```
src/Ordering.Domain/
├── AggregatesModel/
│   ├── BuyerAggregate/
│   │   ├── Buyer.cs                           ← Buyer aggregate root (VerifyOrAddPaymentMethod)
│   │   ├── CardType.cs                        ← Card type value object
│   │   └── PaymentMethod.cs                   ← Payment method entity
│   └── OrderAggregate/
│       ├── Order.cs                           ← Order aggregate root (state machine: Submitted→AwaitingValidation→StockConfirmed→Paid→Shipped/Cancelled)
│       ├── OrderItem.cs                       ← Order line item entity
│       └── Address.cs                         ← Address value object
├── Events/
│   ├── OrderStartedDomainEvent.cs             ← Raised when order is created
│   ├── OrderStatusChangedToAwaitingValidationDomainEvent.cs
│   ├── OrderStatusChangedToPaidDomainEvent.cs
│   ├── OrderStatusChangedToStockConfirmedDomainEvent.cs
│   ├── OrderCancelledDomainEvent.cs
│   └── BuyerAndPaymentMethodVerifiedDomainEvent.cs
├── Exceptions/
│   └── OrderingDomainException.cs             ← Domain-specific exception type
└── SeedWork/
    ├── Entity.cs                              ← Base entity with domain events
    ├── IAggregateRoot.cs                      ← Aggregate root marker interface
    ├── IRepository.cs                         ← Repository interface
    └── IUnitOfWork.cs                         ← Unit of work interface
```

### src/Ordering.Infrastructure/ — Ordering Persistence
```
src/Ordering.Infrastructure/
├── OrderingContext.cs                          ← EF Core DbContext for Ordering
├── EntityConfigurations/                      ← EF entity type configurations
├── Repositories/
│   ├── BuyerRepository.cs                     ← IBuyerRepository implementation
│   └── OrderRepository.cs                     ← IOrderRepository implementation
└── Idempotency/                               ← Idempotent command handling
```

### src/Identity.API/ — Authentication Service
```
src/Identity.API/
├── Configuration/                             ← IdentityServer client/resource configuration
├── Data/                                      ← EF migration data
├── Models/
│   └── ApplicationUser.cs                     ← Extended IdentityUser
├── Services/
│   ├── IProfileService.cs                     ← Profile claims service interface
│   └── ProfileService.cs                      ← Profile claims implementation
├── Views/                                     ← MVC login/consent/logout views
├── Program.cs                                 ← App startup with IdentityServer config
└── UsersSeed.cs                               ← Default user seeding
```

### src/WebApp/ — Blazor Storefront UI
```
src/WebApp/
├── Components/                                ← Blazor component pages
├── Services/                                  ← HTTP service clients (Catalog, Basket, Order)
├── Extensions/                                ← Service registration
└── Program.cs                                 ← App startup
```

### src/eShop.AppHost/ — Aspire Orchestrator
```
src/eShop.AppHost/
├── Program.cs                                 ← Defines all services, dependencies, and resource wiring
└── appsettings.json                           ← Orchestration configuration (connection strings, OTEL)
```

### Cross-Service Libraries
```
src/EventBus/                                  ← Abstract event bus interfaces (IEventBus, IntegrationEvent)
src/EventBusRabbitMQ/                          ← RabbitMQ event bus implementation
src/IntegrationEventLogEF/                     ← Outbox pattern: persists integration events before publishing
src/Shared/                                    ← Shared utilities across services
src/eShop.ServiceDefaults/                     ← Aspire service defaults (health checks, telemetry, resilience)
```

## Communication Patterns
- **gRPC**: Internal service-to-service calls (e.g., Basket → Catalog for price lookup via `BasketService.cs`)
- **HTTP REST**: External API consumers and BFF→API calls (endpoints in `*Api.cs` files)
- **RabbitMQ**: Asynchronous integration events (order placed, stock confirmed, payment processed)
- **SignalR**: Real-time order status updates pushed to the Blazor UI
- **MediatR**: In-process CQRS command/query dispatching inside Ordering.API

## Data Stores
| Store | Used By | Notes |
|---|---|---|
| **PostgreSQL** | Catalog.API, Ordering.API | Primary relational store; EF Core migrations |
| **Redis** | Basket.API | Per-user basket cache; JSON serialization; key = buyerId |
| **SQL Server** | Identity.API | ASP.NET Identity tables |

## Key Architectural Patterns

### CQRS (Ordering.API)
- Commands handled by MediatR command handlers in `src/Ordering.API/Application/Commands/`
- Queries handled by Dapper in `src/Ordering.API/Application/Queries/OrderQueries.cs`
- Domain events raised inside aggregates (`src/Ordering.Domain/`), dispatched post-persistence
- Domain event handlers in `src/Ordering.API/Application/DomainEventHandlers/` publish integration events

### Domain Events → Integration Events Pipeline
1. Order aggregate raises `OrderStartedDomainEvent` (in `src/Ordering.Domain/Events/`)
2. `ValidateOrAddBuyerAggregateWhenOrderStartedDomainEventHandler` handles it
3. Handler creates/validates Buyer, then publishes `OrderStatusChangedToSubmittedIntegrationEvent` via `_orderingIntegrationEventService.AddAndSaveEventAsync()`
4. Integration event propagates to other services via RabbitMQ
5. **If integration event publishing fails silently, downstream services never learn about the order state change**

### Health Checks
- Every service exposes `/health` (liveness) and `/health/ready` (readiness) endpoints
- Aspire dashboard aggregates health status; failures here surface as startup or runtime alerts

## Component-to-File Quick Reference

When an incident mentions a component, go to these files FIRST:

| Incident Component / Keyword | Primary File to Read |
|---|---|
| catalog, product, item, brand, price, CatalogItem | `src/Catalog.API/Apis/CatalogApi.cs` |
| catalog database, catalog entity, CatalogContext | `src/Catalog.API/Infrastructure/CatalogContext.cs` |
| basket, cart, shopping cart, BasketService | `src/Basket.API/Grpc/BasketService.cs` |
| basket redis, basket repository | `src/Basket.API/Repositories/RedisBasketRepository.cs` |
| order, ordering, CreateOrder | `src/Ordering.API/Apis/OrdersApi.cs` + `src/Ordering.API/Application/Commands/CreateOrderCommand.cs` |
| order status, OrderStarted, buyer, payment method | `src/Ordering.API/Application/DomainEventHandlers/ValidateOrAddBuyerAggregateWhenOrderStartedDomainEventHandler.cs` |
| order domain, aggregate, Order state | `src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs` |
| integration event, event bus, event publishing | `src/Ordering.API/Application/DomainEventHandlers/` + `src/EventBusRabbitMQ/` |
| identity, login, auth, JWT, token | `src/Identity.API/Program.cs` + `src/Identity.API/Configuration/` |
| aspire, orchestration, service discovery, OTEL | `src/eShop.AppHost/Program.cs` + `src/eShop.AppHost/appsettings.json` |
| gRPC error, service unavailable, deadline | `src/Basket.API/Grpc/BasketService.cs` (gRPC is mainly in Basket) |
| NullReferenceException | Check the stack trace for file/class name; common in `CatalogApi.cs` (entity navigation) and domain handlers |
| timeout, latency, slow, delay | Check gRPC methods in `BasketService.cs`, Redis in `RedisBasketRepository.cs`, DB queries in `OrderQueries.cs` |

## Common Error Sources for SRE Triage

### gRPC (Basket.API)
- `StatusCode.Unavailable` — target service not reachable; check container/network state
- `StatusCode.DeadlineExceeded` — latency spike or CPU starvation; look for artificial delays or blocking calls in `BasketService.cs`
- `StatusCode.Unauthenticated` — user identity not extracted from gRPC context
- Certificate / TLS errors in non-dev environments

### Database (Catalog.API, Ordering.API)
- EF Core migration failures on startup (schema mismatch after deploy)
- PostgreSQL connection pool exhaustion under load
- `NullReferenceException` when EF navigation properties (e.g., `CatalogItem.CatalogBrand`) are not loaded via `.Include()`
- Identity.API SQL Server connection string misconfiguration blocks all logins

### Event Bus (RabbitMQ / Integration Events)
- Deserialisation errors when event schema changes without a compatible migration
- Dead-letter queue growth indicates persistent consumer failures
- **Silent exception swallowing** in domain event handlers causes lost integration events — orders get stuck
- Exchange or queue misconfiguration after infrastructure reprovisioning
- `AddAndSaveEventAsync()` failures in `_orderingIntegrationEventService` prevent state propagation

### Configuration / AppSettings
- Missing or wrong `ConnectionStrings` section causes startup crashes
- `ASPNETCORE_ENVIRONMENT` mismatch changes feature flags and logging
- Secrets not injected (Docker secrets, env vars) result in null-reference exceptions at startup
- `OTEL_EXPORTER_OTLP_ENDPOINT` misconfiguration in `appsettings.json` affects telemetry export

### Basket / Redis
- Redis `CONNECTIONTIMEOUT` or `WRONGTYPE` errors indicate cache corruption or key collision
- Basket data loss on Redis restart if persistence (AOF/RDB) is not configured
- Artificial delays (`Task.Delay`) in `BasketService.cs` cause gRPC deadline exceeded

### Identity / Authentication
- Expired or misconfigured signing certificates cause JWT validation failures across all services
- CORS misconfiguration in Identity.API blocks browser-based token requests from WebApp
