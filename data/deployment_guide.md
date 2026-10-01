# Deployment Guide

## Environments

We run three environments: `dev`, `staging` and `production`. Code merged to `main` deploys to
`staging` automatically. Production deploys need a manual approval in the CI pipeline.

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | none, required |
| `GATEWAY_API_KEY` | key for the card gateway | none, required |
| `LOG_LEVEL` | logging verbosity | `INFO` |
| `MAX_RETRIES` | HTTP retry attempts to the gateway | `3` |

## Health checks

The service exposes `/healthz` (process is alive) and `/readyz` (database and gateway reachable).
Kubernetes uses `/readyz` to decide when to send traffic. A pod that fails `/readyz` three times in
a row is removed from the load balancer.

## Rollback

To roll back, run `kubectl rollout undo deployment/payment-service`. Rollback takes about 90
seconds. Database migrations are backward compatible for one release, so a rollback never needs a
database restore. After every rollback, write an incident note in the #ops channel.

## Release schedule

Production releases happen on Tuesdays and Thursdays before 15:00 UTC. No releases on Fridays
unless it is a security fix.
