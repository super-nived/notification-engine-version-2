# FastAPI + PocketBase REST Boilerplate — Project Specification

This document explains **WHY each folder exists first**, and **WHAT each file inside it is responsible for**.  
This order must be followed by **all developers and AI/CLI agents**.

---

## 1. `app/` — Application Root

### Purpose
The `app/` folder contains **all backend source code**.
Nothing outside this folder should contain business logic.

---

## 2. `main.py` — Application Entry Point (MOST IMPORTANT FILE)

### Purpose
`main.py` is the **starting point of the application**.

### Responsibilities
- Create the FastAPI application instance
- Register API routers
- Register startup and shutdown events
- Initialize PocketBase authentication (admin login)
- Wire the whole application together

### Allowed
- App creation
- Router inclusion
- Startup logic

### NOT Allowed
- Business logic
- Database queries
- Feature-specific code

### Why this rule exists
Keeping `main.py` clean ensures:
- Predictable startup
- Easy testing
- Easy deployment
- No hidden side effects

---

## 3. `core/` — Application Core (Global Concerns)

### Purpose
The `core/` folder contains **application-wide logic** that is shared by all features.

This code is **not feature-specific**.

### Files inside `core/`

#### `settings.py`
- Loads environment variables
- Stores configuration values
- Central place for:
  - PocketBase URL
  - Credentials
  - Debug flags

#### `security.py`
- Authentication helpers
- Token validation logic
- Role/permission helpers (future)

#### `logging.py`
- Logging configuration
- Log format and levels
- Centralized logging rules
- Structured JSON logging (production)
- Request context tracking

#### `exceptions.py`
- Custom application exceptions
- Base exception classes used across the app
- HTTP status code mapping

#### `startup.py`
- Application startup logic
- PocketBase authentication
- Connection initialization
- Shutdown cleanup

#### `events.py`
- Lifespan context manager
- Modern FastAPI event handling
- Startup/shutdown orchestration

#### `handlers.py`
- Global exception handlers
- Converts exceptions to JSON responses
- Proper HTTP status codes

---

## 4. `api/` — API Version Control Layer

### Purpose
The `api/` folder exists **only to manage API versions**.

It does NOT contain business logic.

### Files inside `api/`

#### `v1.py`
- Combines routers from all features
- Applies `/api/v1` prefix
- Single place to enable/disable features at API level

### Rules
- Only imports feature routers
- No logic
- No validation
- No database calls

---

## 5. `db/` — External Service & Database Access Layer

### Purpose
The `db/` folder is responsible for **talking to PocketBase via REST APIs**.

PocketBase is treated as an **external system**, not as part of the app.

### Files inside `db/`

#### `client.py`
**MOST IMPORTANT FILE AFTER `main.py`**

Responsibilities:
- Admin authentication
- User authentication
- JWT token handling
- HTTP request handling
- Pagination handling
- `expand`, `filter`, `sort`
- Fetch full list (no limit)

### Critical Rule
❌ No other file in the project is allowed to call PocketBase directly  
✅ All PocketBase communication goes through `client.py`

#### `repositories.py`
- Shared DB helper functions (optional)
- Reusable query helpers if needed

---

## 6. `features/` — Business Features (CORE DOMAIN)

### Purpose
Each folder inside `features/` represents **one business feature**.

Features are:
- Independent
- Isolated
- Scalable
- Easy to add or remove

### Example Feature: `features/machines/`

---

### `features/machines/router.py`
**Purpose**
- Define HTTP endpoints
- Handle request/response flow
- **MUST use standard response format**

**Allowed**
- FastAPI decorators
- Dependency injection
- HTTP error handling
- Import `success()` from `utils.response`

**NOT Allowed**
- Database access
- Business logic
- Returning raw dictionaries/arrays

**Response Format Rule (MANDATORY)**
```python
# ✅ CORRECT - Always use success()
from app.utils.response import success

return success(data=machines, message="Success")

# ❌ WRONG - Never return raw data
return machines  # NO!
return {"machines": machines}  # NO!
```

---

### `features/machines/schema.py`
**Purpose**
- Define request and response data shapes
- Act as API contracts

**Rules**
- Pydantic models only
- No logic
- No DB calls

---

### `features/machines/service.py`
**Purpose**
- Business rules
- Validation logic
- Feature-specific workflows

**Rules**
- No FastAPI imports
- No direct DB calls
- Calls repository functions only

---

### `features/machines/repo.py`
**Purpose**
- Data access layer for the feature
- Talks to PocketBase via `db/client.py`

**Rules**
- No FastAPI imports
- No business logic
- No environment access

---

## 7. `middlewares/` — Request/Response Interceptors

### Purpose
Middleware logic that runs **before or after requests**.

### Files inside `middlewares/`

#### `auth.py`
- Authentication middleware
- Token extraction
- User context attachment

---

## 8. `utils/` — Shared Helper Functions

### Purpose
Generic helper logic used across the application.

### Files inside `utils/`

#### `response.py`
- Standard API response formats

#### `pagination.py`
- Pagination helpers for in-memory data

---

## 9. `tests/` — Automated Testing

### Purpose
All tests live here. No test code outside this folder.

### Structure

#### `tests/unit/`
- Test business logic
- Mock repositories
- No external calls

#### `tests/integration/`
- Test API endpoints
- Can use real PocketBase or test instance

---

## 10. Adding a New Feature (MANDATORY STEPS)

1. Copy an existing feature folder (e.g., `machines`)
2. Rename folder and files
3. Implement schema, service, repo
4. Register router in `api/v1.py`
5. Add tests

❌ Features must NOT import each other directly

---

## 11. Coding Standards (MANDATORY — PEP 8)

All contributors (humans and AI agents) must follow **PEP-8**.

### Naming
- Functions: `snake_case`
- Variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_CASE`

### Formatting
- Max line length: **88 characters**
- One responsibility per function
- Explicit return types preferred

### Imports Order
1. Standard library
2. Third-party
3. Local imports

---

## 12. Rules for CLI / AI Agents

- Never place logic in routers
- Never access PocketBase outside `db/client.py`
- Never skip layers
- Follow folder responsibility strictly
- Follow PEP-8 strictly

---

## 13. Final Rule (IMPORTANT)

This file is the **single source of truth**.

If code conflicts with this spec:
➡️ **The code is wrong, not the spec.**

---

**End of Specification**
