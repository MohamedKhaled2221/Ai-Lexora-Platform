# AI-Lexora Qdrant Deployment

AI-Lexora uses a local Qdrant instance for legal-document
vector retrieval.

## Pinned Runtime

The deployment is pinned to the exact Qdrant image that was
validated during development:

- Qdrant version: `1.19.0`
- REST port: `127.0.0.1:6333`
- gRPC port: `127.0.0.1:6334`
- Container name: `ai-lexora-qdrant`
- Persistent volume: `ai_lexora_qdrant_storage`

The Docker image is pinned by digest in `compose.yml` to avoid
unexpected upgrades.

## Storage

Qdrant storage is persisted using the external Docker volume:

`ai_lexora_qdrant_storage`

The volume must exist before starting the Compose deployment.

Check it with:

```bash
docker volume inspect ai_lexora_qdrant_storage
