# Sources and technology guidelines

Reviewed 28 September 2026. These sources inform implementation mechanics; local project policy remains in contracts and guardrails. Dependency versions and account/model availability must be verified when implementation begins.

## Project inputs

- ASSIGNMENT.pdf: three pages, read from the user's Downloads folder; not copied into this package. Page 1: scenario and Python/React requirement. Page 2: grounding, four tools, immutable rules, context, decision questions. Page 3: submission/run/secrets requirements.
- inputs/knowledge.md: five source sections; verbatim copy of user-supplied file.
- inputs/work_orders.json: currentUser and ten work orders; verbatim copy of user-supplied file.

## Official implementation references

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling): use structured tool definitions, correlate results to call IDs, and enable strict schemas/disable parallel calls where supported. Server business validation remains mandatory. Preserve required provider continuation items in the adapter. Initial provider choice is an implementation proposal; an API key/model has not been tested.
- [FastAPI settings](https://fastapi.tiangolo.com/advanced/settings/): central typed environment configuration using settings objects; load once and inject into services.
- [Pydantic strict mode](https://pydantic.dev/docs/validation/latest/concepts/strict_mode/): validate external values without permissive coercion. Project contracts also require rejecting extra fields and explicit business validation.
- [SQLite transactions](https://www.sqlite.org/lang_transaction.html): supports concurrent readers and a single writer; use short explicit transactions and handle busy/conflict errors. SQLite is a small-service design choice, not a claim of unlimited write scalability.
- [React quick start](https://react.dev/learn): minimal components, events and local state are sufficient for the requested UI; avoid global state frameworks for a single chat view.
- [Docker Compose quick start](https://docs.docker.com/compose/gettingstarted/): the implementation must supply and test its declarative launcher. The current package does not include a working Compose service.
- [Git configuration](https://git-scm.com/docs/git-config): repository-local user.name/user.email configuration supports the requested commit identity. Verify author and committer; do not change global settings.

No web content is used as runtime maintenance evidence. Runtime technical answers are constrained to the supplied knowledge base. Source links above help developers use tools; they do not expand the assistant's allowed knowledge.
