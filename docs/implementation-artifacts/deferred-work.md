# Deferred Work

Items identified during code reviews that are deferred for future stories or cross-cutting concerns.

## From Story 4-1: Ticket-Service Scaffold

| # | Finding | File | Reason |
|---|---------|------|--------|
| 1 | asyncio.gather doesn't restart on single-task failure | main.py:40-43 | Pre-existing pattern shared by agent service; needs project-wide decision |
| 2 | No request size limit on webhook endpoint | webhook_listener.py | Nginx reverse proxy handles upstream body limits |
| 3 | No rate limiting on webhook endpoint | webhook_listener.py | Nginx reverse proxy handles upstream rate limiting |
| 4 | Handler exception crashes redis consumer loop | redis_consumer.py:52 | Pre-existing code not changed by this story; needs try/except in consumer loop |
