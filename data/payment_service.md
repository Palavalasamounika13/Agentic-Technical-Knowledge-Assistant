# Payment Service Guide

## Overview

The payment service handles card charges, refunds and payouts for the shop. It exposes a REST API
on port 8080 and stores all records in PostgreSQL. Every charge is linked to an order ID.

## Idempotency

Clients must send an `Idempotency-Key` header with every POST request. If the same key is sent
twice within 24 hours, the service returns the original response instead of charging the card
again. Keys are stored in the `idempotency_keys` table and cleaned up nightly at 02:00 UTC.

## Refunds

Refunds are allowed up to 30 days after the original charge. A partial refund is allowed, but the
total refunded amount can never exceed the original charge. Refunds above 500 USD need manager
approval, and the request stays in the `pending_approval` state until approved. Approved refunds
reach the customer's bank in 5 to 7 business days.

## Error handling

- `402 payment_declined`: the card issuer rejected the charge. Do not retry.
- `409 duplicate_request`: idempotency key already used with different parameters.
- `503 gateway_unavailable`: upstream card gateway is down. Safe to retry with backoff.

## Timeouts

The gateway call times out after 10 seconds. After a timeout the charge status is set to
`unknown` and a reconciliation job checks the gateway every 5 minutes until the state is known.
