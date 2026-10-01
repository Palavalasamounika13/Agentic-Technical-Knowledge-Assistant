# Example API Client

## Retry logic

The client retries failed HTTP requests up to 3 times. Between attempts it waits
using exponential backoff: 1 second, then 2 seconds, then 4 seconds. Only network
errors and HTTP 429, 500, 502, 503 and 504 responses are retried. Other 4xx errors
fail immediately because retrying will not change the result.

## Authentication

Every request must include an `Authorization: Bearer <token>` header. Tokens expire
after 60 minutes. The client refreshes the token automatically when it receives a
401 response, then repeats the original request once.

## Rate limiting

The API allows 100 requests per minute per token. When the limit is hit the server
returns HTTP 429 with a `Retry-After` header. The client honours that header and
sleeps for the given number of seconds before the next retry.
