# Repository Analysis: s-ui

**Analysis Date**: December 27, 2024  
**Repository**: Zeeeepa/s-ui  
**Description**: An advanced Web Panel • Built for SagerNet/Sing-Box

---

## Executive Summary

S-UI is an advanced web-based management panel built on SagerNet/Sing-Box, designed for managing VPN and proxy protocol configurations. The project provides a comprehensive interface for configuring multiple proxy protocols, monitoring traffic, managing clients, and providing subscription services.

**Key Characteristics**:
- **Primary Language**: Go (1.25+)
- **Framework**: Gin (Backend) + Vue.js (Frontend as submodule)
- **Architecture**: 3-tier architecture with clean separation of concerns
- **Database**: SQLite with GORM ORM
- **License**: GNU GPL v3.0
- **Platforms**: Linux, Windows, macOS (multi-architecture support)

---

## Repository Overview

### Basic Information
- **Primary Language**: Go
- **Go Version**: 1.25.1
- **Framework**: Gin v1.11.0 (Web framework)
- **Total Go Files**: 66 files
- **Frontend**: Vue.js (separate git submodule: `github.com/alireza0/s-ui-frontend`)
- **License**: GNU General Public License v3.0
- **Last Updated**: Active development

### Community Metrics
- **Purpose**: VPN/Proxy management panel
- **Target Users**: Network administrators, privacy-conscious users
- **Deployment**: Self-hosted on Linux/Windows servers or Docker containers

### Repository Structure

```
s-ui/
├── api/              # API handlers and service layer
├── app/              # Main application initialization
├── cmd/              # CLI commands and migrations
├── config/           # Configuration management
├── core/             # Core engine integration (Sing-Box)
├── cronjob/          # Scheduled tasks
├── database/         # Database layer with models
│   └── model/        # GORM data models
├── frontend/         # Git submodule (Vue.js frontend)
├── logger/           # Logging utilities
├── middleware/       # HTTP middlewares
├── network/          # Network utilities
├── service/          # Business logic services
├── sub/              # Subscription server
├── util/             # Utility functions
├── web/              # Web server and routing
│   └── html/         # Static frontend assets (compiled)
├── windows/          # Windows-specific files
├── .github/          # GitHub Actions workflows
│   └── workflows/    # CI/CD pipelines
│       ├── docker.yml
│       ├── release.yml
│       └── windows.yml
├── Dockerfile        # Multi-stage Docker build
├── docker-compose.yml
├── go.mod            # Go dependencies
├── main.go           # Application entry point
├── install.sh        # Linux/macOS installation script
├── s-ui.sh           # Service management script
└── s-ui.service      # Systemd service file
```

## Architecture & Design Patterns

### Architectural Pattern
**Type**: **Modular 3-Tier Architecture** with clear separation between presentation, business logic, and data layers.

```
┌─────────────────────────────────────────────────────────┐
│                    Presentation Layer                    │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐ │
│  │  Web Server  │  │  Sub Server   │  │  API Routes  │ │
│  │  (:2095/app) │  │ (:2096/sub)   │  │              │ │
│  └──────────────┘  └───────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                   Business Logic Layer                   │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐ │
│  │   Services   │  │  Middlewares  │  │   CronJobs   │ │
│  │  (client,    │  │  (domain      │  │  (traffic    │ │
│  │  config,     │  │  validator)   │  │  cleanup)    │ │
│  │  setting)    │  │               │  │              │ │
│  └──────────────┘  └───────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                      Data Layer                          │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐ │
│  │  Database    │  │  GORM Models  │  │   Core       │ │
│  │  (SQLite)    │  │  (Inbound,    │  │  (Sing-Box)  │ │
│  │              │  │  Outbound,    │  │              │ │
│  │              │  │  TLS, etc.)   │  │              │ │
│  └──────────────┘  └───────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Design Patterns Identified

1. **Singleton Pattern**
   - Core engine instance
   - Service instances (SettingService, ConfigService)
   
2. **Repository Pattern**
   - Database models with GORM
   - Service layer abstracts database operations
   
3. **Factory Pattern**
   - Application initialization in `app.NewApp()`
   - Server creation functions (`web.NewServer()`, `sub.NewServer()`)

4. **Middleware Pattern**
   - Gin middleware stack for request processing
   - Domain validation, session management, gzip compression

5. **Strategy Pattern**
   - Multiple protocol handlers
   - Configurable DNS and routing rules

### Module Organization

**Core Modules**:
- `app/`: Application lifecycle management
- `api/`: HTTP API handlers (v1 and v2)
- `service/`: Business logic services
- `database/`: Data access and models
- `web/`: Web server and frontend
- `sub/`: Subscription service
- `core/`: Sing-Box engine integration

**Supporting Modules**:
- `config/`: Configuration management
- `logger/`: Logging utilities
- `middleware/`: HTTP middlewares
- `util/`: Common utilities
- `cronjob/`: Scheduled task management
- `network/`: Network-related utilities

### Data Flow

**Request Processing Flow**:
```
User Request → Gin Router → Middleware Stack → API Handler
                                                      ↓
                                              Service Layer
                                                      ↓
                                              Database/Core
                                                      ↓
                                              Response
```

**Example: Login Flow**
```go
// api/apiHandler.go
func (a *APIHandler) postHandler(c *gin.Context) {
    switch action {
    case "login":
        a.ApiService.Login(c)  // Delegates to service layer
    }
}

// Session management via Gin sessions
store := cookie.NewStore(secret)
engine.Use(sessions.Sessions("s-ui", store))
```

### State Management
- **Session State**: Managed via Gin cookie-based sessions
- **Application State**: Singleton service instances hold configuration
- **Database State**: SQLite provides persistent storage
- **Runtime State**: Core engine maintains connection/proxy state

