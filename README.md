# AI-Lexora Backend

The backend for **Lexora** — an AI-powered Legal Assistant — built with **ASP.NET Core (.NET 10)**. This service handles user management, legal document upload & analysis, an AI chatbot (RAG), document search, and template-based document generation.

The project integrates with external AI services (Python-based) to perform the actual contract analysis and chat reasoning, while this backend owns authentication, storage, the database, and orchestration between those services.

---

## Table of Contents

- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup & Run](#setup--run)
- [Configuration (appsettings.json)](#configuration-appsettingsjson)
- [Database & Migrations](#database--migrations)
- [API Endpoints](#api-endpoints)
- [External AI Services](#external-ai-services)
- [Swagger Documentation](#swagger-documentation)
- [Security Notes Before Production](#security-notes-before-production)

---

## Key Features

- **Auth & Roles**: Register/login, email confirmation, password reset, refresh tokens, and user roles (Admin/User) via ASP.NET Identity + JWT.
- **Document Management**: Upload documents (PDF, DOC, DOCX, TXT, images), download, update, and delete them, with automatic text extraction.
- **Contract Analysis**: Smart contract analysis through an external pipeline (M1 → M5 → M6) to extract risks and sensitive clauses, running asynchronously via a background worker and work queue.
- **RAG Chatbot**: Conversations tied to uploaded documents, powered by an external AI (RAG) service.
- **Search**: Keyword-based full-text search over extracted document content, designed to be upgraded later to semantic search (embeddings + vector DB).
- **Document Generator**: Generate ready-made legal documents from templates with token substitution.
- **Admin Dashboard**: Manage users, roles, and account status.
- **Email**: Sends confirmation and password-reset emails via SMTP.
- **Logging**: Structured logging via Serilog.
- **Unified Error Handling**: Custom middleware returning consistent error responses.

---

## Tech Stack

| Component | Technology |
|---|---|
| Framework | ASP.NET Core Web API — .NET 10 |
| Database | SQL Server (via Entity Framework Core 10) |
| Authentication | ASP.NET Identity + JWT Bearer |
| Input Validation | FluentValidation |
| API Docs | Swagger / Swashbuckle |
| Logging | Serilog |
| PDF Text Extraction | PdfPig |
| Email | SMTP |

---

## Project Structure

```
AI-Lexora-backend/
├── Auth/                 # Registration, login, JWT, refresh tokens
├── Chatbot/              # Chatbot controller and DTOs
├── Common/               # Shared error response models
├── Data/                 # AppDbContext and user entity
├── Documents/            # Document upload / contract analysis
├── Email/                # SMTP email service
├── Generator/            # Template-based document generator
├── Middleware/           # Unified exception handling
├── Migrations/           # EF Core migrations
├── Repositories/         # Data access layer
├── Search/               # Document search
├── Services/             # Business logic + AI service integrations
├── Users/                # Admin user management + profile
├── Validators/           # FluentValidation rules
├── Program.cs            # App startup & service configuration
└── appsettings.json       # Global configuration
```

---

## Prerequisites

- [.NET SDK 10](https://dotnet.microsoft.com/download) or later
- SQL Server (local or remote)
- (Optional, for full AI features) The external AI services running on the ports listed in [External AI Services](#external-ai-services)

---

## Setup & Run

```bash
# 1) Go to the project folder
cd AI-Lexora-backend

# 2) Restore packages
dotnet restore

# 3) Update the DB connection string and JWT key in appsettings.json (see next section)

# 4) Apply migrations to create the database
dotnet ef database update

# 5) Run the project
dotnet run
```

After a successful run:
- In Development, hitting `/` redirects automatically to the **Swagger** UI at `/swagger`.
- A health check endpoint is available at: `GET /health`.

On first run, `DbSeeder` automatically creates the base roles and a default Admin account (default credentials are in `appsettings.json` under `AdminSeed` — change them immediately).

---

## Configuration (appsettings.json)

| Section | Description |
|---|---|
| `ConnectionStrings:DefaultConnection` | SQL Server connection string |
| `Jwt:Key / Issuer / Audience` | JWT signing/generation settings — **the key must be changed before deployment** |
| `AdminSeed` | Credentials for the default Admin account auto-created on first run |
| `FileStorage` | Upload storage path, max file size, and allowed extensions |
| `Email` | SMTP settings for confirmation and password-reset emails |
| `AiService` | Base URL for the main AI service (used by the chatbot and M6) |
| `M1Service` / `M5Service` | Base URLs for the first and fifth stages of the contract analysis pipeline |

> **Note:** All current values in `appsettings.json` are local development defaults only, and must be replaced with real, secure values (especially `Jwt:Key`, SMTP credentials, and Admin credentials) before any real deployment.

---

## Database & Migrations

The project uses Entity Framework Core with SQL Server. Key entities:

- `Document` — uploaded documents
- `ContractAnalysis` / `RiskyClause` — contract analysis results and flagged risky clauses
- `RefreshToken` — session refresh tokens
- `GeneratedDocumentRecord` — record of documents generated from templates
- `ChatConversation` / `ChatMessage` — chatbot conversations and messages

To create a new migration after model changes:

```bash
dotnet ef migrations add <MigrationName>
dotnet ef database update
```

---

## API Endpoints

### Auth `/api/auth`
| Method | Route | Description |
|---|---|---|
| POST | `/register` | Register a new account |
| POST | `/login` | Log in |
| POST | `/forgot-password` | Request a password reset |
| POST | `/reset-password` | Reset password |
| POST | `/confirm-email` | Confirm email address |
| POST | `/resend-confirmation` | Resend confirmation email |
| POST | `/change-email` | Request an email change |
| POST | `/confirm-email-change` | Confirm the email change |
| POST | `/refresh` | Refresh access/refresh tokens |
| POST | `/logout` | Log out |
| POST | `/promote-to-admin` | Promote a user to Admin |

### Documents `/api/documents`
| Method | Route | Description |
|---|---|---|
| POST | `/` | Upload a single document |
| POST | `/batch` | Upload multiple documents at once |
| GET | `/` | List documents |
| GET | `/{id}` | Get document details |
| PUT | `/{id}` | Update a document |
| GET | `/{id}/download` | Download a document |
| DELETE | `/{id}` | Delete a document |

### Contract Analysis `/api/documents/{documentId}/analysis`
| Method | Route | Description |
|---|---|---|
| POST | `/` | Create a new analysis request |
| POST | `/start` | Start the analysis (internal/pipeline call) |
| GET | `/` | Get analysis result |
| POST | `/complete` | Report analysis completion (callback) |
| POST | `/fail` | Report analysis failure (callback) |

### Chatbot `/api/chatbot`
| Method | Route | Description |
|---|---|---|
| GET | `/conversations` | List conversations |
| POST | `/conversations` | Create a new conversation |
| GET | `/conversations/{conversationId}/messages` | List messages in a conversation |
| POST | `/conversations/{conversationId}/messages` | Send a new message |

### Search `/api/search`
| Method | Route | Description |
|---|---|---|
| GET | `/` | Search document content |

### Document Generator `/api/document-generator`
| Method | Route | Description |
|---|---|---|
| GET | `/templates` | List available templates |
| POST | `/generate` | Generate a new document from a template |

### Profile `/api/profile`
| Method | Route | Description |
|---|---|---|
| GET | `/` | Get profile data |
| PUT | `/` | Update profile data |
| PUT | `/password` | Change password |

### Admin — User Management `/api/admin/users`
| Method | Route | Description |
|---|---|---|
| GET | `/` | List all users |
| PUT | `/{id}/role` | Update a user's role |
| PUT | `/{id}/status` | Enable/disable a user account |

---

## External AI Services

The project relies on external services (likely Python) for the actual AI processing, communicating over HTTP:

| Service | Config Key | Default URL | Purpose |
|---|---|---|---|
| AI Service | `AiService:BaseUrl` | `http://localhost:8000` | Chatbot (RAG) + contract analysis stage M6 |
| M1 Service | `M1Service:BaseUrl` | `http://localhost:8001` | Contract analysis — stage 1 |
| M5 Service | `M5Service:BaseUrl` | `http://localhost:8002` | Contract analysis — stage 5 |

If these services aren't available during local development, you can switch to built-in offline implementations by commenting out the current registration and uncommenting the alternative in `Program.cs`:

- Chatbot: switch from `LexoraRagChatbotService` to `PlaceholderChatbotService`.
- Contract analysis: switch from `LexoraContractAnalysisService` to `RuleBasedContractAnalysisService`.

---

## Swagger Documentation

In the Development environment, an interactive Swagger UI is automatically available at `/swagger`, supporting Bearer token authentication by pasting the access token directly (Swagger prepends "Bearer" automatically).

---

## Security Notes Before Production

- Replace `Jwt:Key` with a long, random, secure key (at least 32 characters).
- Change the default Admin credentials under `AdminSeed`.
- Configure real SMTP credentials instead of the empty defaults.
- Restrict the current CORS policy (`AllowAnyOrigin`) to trusted domains only.
- Ensure HTTPS is enforced and the database connection string is secured in production.
