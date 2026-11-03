# Legacy Cloudflare backend (reference only)

The former Next route handlers live in `routes/` and are deliberately outside
`app/`: they are not served by the M1 Node application. Their original dependencies
and SQL migrations remain available for regression tests and future migration.
The old deployable baseline is commit `ffccd98`; use an isolated checkout and
independent storage if historical operation is needed. Do not mount these handlers
under the new API or forward Django sessions to them.

`/demo` is a synthetic, in-memory UI. Its connection action is disabled. No legacy
record is silently copied, deleted or linked to a Django identity.
