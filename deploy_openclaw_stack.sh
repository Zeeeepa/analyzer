#!/bin/bash
set -euo pipefail

# OpenClaw Stack Deployment Script
# Integrates: docker-openclaw v3.8 + unbrowse-openclaw + ClawWork
# Purpose: Content aggregation system for NPM, GitHub, PyPI, DockerHub, VSIX, Chrome/Firefox stores, News

VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_DIR="${DEPLOYMENT_DIR:-$HOME/openclaw-deployment}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    local missing_deps=()
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        missing_deps+=("docker")
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        missing_deps+=("docker-compose")
    fi
    
    # Check Git
    if ! command -v git &> /dev/null; then
        missing_deps+=("git")
    fi
    
    # Check Node.js (for unbrowse)
    if ! command -v node &> /dev/null; then
        missing_deps+=("node")
    fi
    
    # Check npm
    if ! command -v npm &> /dev/null; then
        missing_deps+=("npm")
    fi
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        log_error "Missing required dependencies: ${missing_deps[*]}"
        log_info "Please install missing dependencies and try again."
        exit 1
    fi
    
    log_success "All prerequisites met!"
}

# Create directory structure
create_directory_structure() {
    log_info "Creating directory structure at $DEPLOYMENT_DIR..."
    
    mkdir -p "$DEPLOYMENT_DIR"/{configs,init-scripts,volumes/{workspace,config,skills,data,logs},docs,projects}
    
    log_success "Directory structure created!"
}

# Clone required projects
clone_projects() {
    log_info "Cloning required projects..."
    
    cd "$DEPLOYMENT_DIR/projects"
    
    # Clone ClawWork
    if [ ! -d "ClawWork" ]; then
        log_info "Cloning ClawWork..."
        git clone https://github.com/HKUDS/ClawWork.git
        log_success "ClawWork cloned!"
    else
        log_warning "ClawWork already exists, skipping..."
    fi
    
    # Clone unbrowse-openclaw
    if [ ! -d "unbrowse-openclaw" ]; then
        log_info "Cloning unbrowse-openclaw..."
        git clone --branch stable https://github.com/lekt9/unbrowse-openclaw.git
        log_success "unbrowse-openclaw cloned!"
    else
        log_warning "unbrowse-openclaw already exists, skipping..."
    fi
    
    # Clone OpenClaw (for docker setup)
    if [ ! -d "openclaw" ]; then
        log_info "Cloning OpenClaw..."
        git clone https://github.com/openclaw/openclaw.git
        log_success "OpenClaw cloned!"
    else
        log_warning "OpenClaw already exists, skipping..."
    fi
    
    cd "$DEPLOYMENT_DIR"
}

# Generate docker-compose.yml
generate_docker_compose() {
    log_info "Generating docker-compose.yml..."
    
    cat > "$DEPLOYMENT_DIR/docker-compose.yml" << 'EOF'
version: '3.8'

services:
  # PostgreSQL database for content storage
  postgres:
    image: postgres:16-alpine
    container_name: openclaw-postgres
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-openclaw}
      POSTGRES_USER: ${POSTGRES_USER:-openclaw}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-changeme}
    volumes:
      - ./volumes/data/postgres:/var/lib/postgresql/data
      - ./init-scripts/02-setup-database.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-openclaw}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - openclaw-network

  # Neo4j graph database (optional, for relationship storage)
  neo4j:
    image: neo4j:5-community
    container_name: openclaw-neo4j
    environment:
      NEO4J_AUTH: ${NEO4J_USER:-neo4j}/${NEO4J_PASSWORD:-changeme}
      NEO4J_PLUGINS: '["apoc", "graph-data-science"]'
    volumes:
      - ./volumes/data/neo4j:/data
      - ./volumes/logs/neo4j:/logs
    ports:
      - "7474:7474"  # HTTP
      - "7687:7687"  # Bolt
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u ${NEO4J_USER:-neo4j} -p ${NEO4J_PASSWORD:-changeme} 'RETURN 1'"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - openclaw-network
    profiles:
      - with-neo4j

  # OpenClaw main container
  openclaw:
    image: openclaw/openclaw:latest
    container_name: openclaw-main
    environment:
      - OPENCLAW_API_KEY=${OPENCLAW_API_KEY}
      - POSTGRES_HOST=postgres
      - POSTGRES_DB=${POSTGRES_DB:-openclaw}
      - POSTGRES_USER=${POSTGRES_USER:-openclaw}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-changeme}
      - NEO4J_URI=bolt://neo4j:7687
      - NEO4J_USER=${NEO4J_USER:-neo4j}
      - NEO4J_PASSWORD=${NEO4J_PASSWORD:-changeme}
      - NPM_REGISTRY_URL=https://registry.npmjs.org
      - PYPI_API_URL=https://pypi.org/pypi
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - DOCKERHUB_TOKEN=${DOCKERHUB_TOKEN}
    volumes:
      - ./volumes/workspace:/workspace
      - ./volumes/config:/config
      - ./volumes/skills:/skills
      - ./volumes/logs/openclaw:/logs
      - ./configs:/app/configs:ro
      - ./projects/unbrowse-openclaw:/unbrowse:ro
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "3000:3000"  # OpenClaw API
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:3000/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
    networks:
      - openclaw-network

  # Initialization container (runs once)
  init:
    image: openclaw/openclaw:latest
    container_name: openclaw-init
    environment:
      - POSTGRES_HOST=postgres
      - POSTGRES_DB=${POSTGRES_DB:-openclaw}
      - POSTGRES_USER=${POSTGRES_USER:-openclaw}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-changeme}
    volumes:
      - ./init-scripts:/init-scripts:ro
      - ./volumes/skills:/skills
      - ./projects/unbrowse-openclaw:/unbrowse:ro
    depends_on:
      postgres:
        condition: service_healthy
      openclaw:
        condition: service_healthy
    command: /bin/bash -c "cd /init-scripts && ./01-install-unbrowse.sh && ./03-generate-skills.sh"
    networks:
      - openclaw-network
    profiles:
      - init

networks:
  openclaw-network:
    driver: bridge

volumes:
  postgres-data:
  neo4j-data:
EOF

    log_success "docker-compose.yml generated!"
}

# Generate environment template
generate_env_template() {
    log_info "Generating .env.template..."
    
    cat > "$DEPLOYMENT_DIR/.env.template" << 'EOF'
# OpenClaw Stack Configuration
# Copy this file to .env and fill in your values

# OpenClaw API Key (required)
OPENCLAW_API_KEY=your_openclaw_api_key_here

# PostgreSQL Configuration
POSTGRES_DB=openclaw
POSTGRES_USER=openclaw
POSTGRES_PASSWORD=changeme_strong_password

# Neo4j Configuration (optional, for graph storage)
NEO4J_USER=neo4j
NEO4J_PASSWORD=changeme_strong_password

# Platform API Keys
GITHUB_TOKEN=your_github_token_here
DOCKERHUB_TOKEN=your_dockerhub_token_here
NPM_TOKEN=your_npm_token_here

# Monitoring Configuration
POLL_INTERVAL_NPM=300        # seconds (5 minutes)
POLL_INTERVAL_PYPI=600       # seconds (10 minutes)
POLL_INTERVAL_GITHUB=300     # seconds (5 minutes)
POLL_INTERVAL_DOCKERHUB=600  # seconds (10 minutes)
POLL_INTERVAL_NEWS=1800      # seconds (30 minutes)

# Feature Flags
ENABLE_NPM=true
ENABLE_PYPI=true
ENABLE_GITHUB=true
ENABLE_DOCKERHUB=true
ENABLE_VSIX=true
ENABLE_CHROME_STORE=true
ENABLE_FIREFOX_STORE=true
ENABLE_NEWS=true

# Logging
LOG_LEVEL=info
LOG_FORMAT=json
EOF

    log_success ".env.template generated!"
    
    if [ ! -f "$DEPLOYMENT_DIR/.env" ]; then
        cp "$DEPLOYMENT_DIR/.env.template" "$DEPLOYMENT_DIR/.env"
        log_warning "Created .env file from template. Please edit it with your credentials!"
    fi
}

# Generate platform configuration
generate_platform_config() {
    log_info "Generating platforms.yml..."
    
    cat > "$DEPLOYMENT_DIR/configs/platforms.yml" << 'EOF'
# Platform Configuration for Content Aggregation

platforms:
  npm:
    enabled: true
    name: "NPM Registry"
    api_endpoint: "https://registry.npmjs.org"
    poll_interval: 300  # seconds
    rate_limit: 100     # requests per minute
    skills:
      - npm-search
      - npm-package-info
      - npm-download-stats
    
  pypi:
    enabled: true
    name: "Python Package Index"
    api_endpoint: "https://pypi.org/pypi"
    poll_interval: 600
    rate_limit: 60
    skills:
      - pypi-search
      - pypi-package-info
      - pypi-download-stats
    
  github:
    enabled: true
    name: "GitHub"
    api_endpoint: "https://api.github.com"
    poll_interval: 300
    rate_limit: 5000  # per hour with token
    skills:
      - github-search-repos
      - github-repo-info
      - github-trending
    
  dockerhub:
    enabled: true
    name: "Docker Hub"
    api_endpoint: "https://hub.docker.com/v2"
    poll_interval: 600
    rate_limit: 100
    skills:
      - dockerhub-search
      - dockerhub-image-info
      - dockerhub-tags
    
  vsix:
    enabled: true
    name: "VS Code Marketplace"
    api_endpoint: "https://marketplace.visualstudio.com/_apis/public/gallery"
    poll_interval: 600
    rate_limit: 60
    skills:
      - vsix-search
      - vsix-extension-info
    
  chrome_store:
    enabled: true
    name: "Chrome Web Store"
    api_endpoint: "https://chrome.google.com/webstore"
    poll_interval: 600
    rate_limit: 60
    skills:
      - chrome-search
      - chrome-extension-info
    
  firefox_store:
    enabled: true
    name: "Firefox Add-ons"
    api_endpoint: "https://addons.mozilla.org/api/v5"
    poll_interval: 600
    rate_limit: 60
    skills:
      - firefox-search
      - firefox-addon-info
    
  news:
    enabled: true
    name: "News Aggregation"
    sources:
      - name: "Hacker News"
        api_endpoint: "https://hacker-news.firebaseio.com/v0"
        poll_interval: 1800
      - name: "Reddit Programming"
        api_endpoint: "https://www.reddit.com/r/programming.json"
        poll_interval: 1800
    skills:
      - news-fetch
      - news-parse
      - news-summarize

# Storage configuration
storage:
  database: "postgres"  # or "neo4j" for graph storage
  retention_days: 90
  backup_enabled: true
  backup_interval: 86400  # daily

# Monitoring configuration
monitoring:
  health_check_interval: 60
  alert_on_failure: true
  metrics_enabled: true
EOF

    log_success "platforms.yml generated!"
}

# Generate initialization scripts
generate_init_scripts() {
    log_info "Generating initialization scripts..."
    
    # Script 1: Install unbrowse
    cat > "$DEPLOYMENT_DIR/init-scripts/01-install-unbrowse.sh" << 'EOF'
#!/bin/bash
set -euo pipefail

echo "[INIT] Installing unbrowse-openclaw plugin..."

cd /unbrowse

# Install dependencies
npm install

# Build unbrowse
npm run build

# Copy built files to skills directory
cp -r dist/* /skills/unbrowse/

echo "[INIT] unbrowse-openclaw installed successfully!"
EOF

    chmod +x "$DEPLOYMENT_DIR/init-scripts/01-install-unbrowse.sh"
    
    # Script 2: Setup database
    cat > "$DEPLOYMENT_DIR/init-scripts/02-setup-database.sql" << 'EOF'
-- OpenClaw Content Aggregation Database Schema

-- Packages table (for NPM, PyPI, etc.)
CREATE TABLE IF NOT EXISTS packages (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    version VARCHAR(100),
    description TEXT,
    author VARCHAR(255),
    homepage VARCHAR(500),
    repository VARCHAR(500),
    license VARCHAR(100),
    downloads_total BIGINT DEFAULT 0,
    downloads_monthly BIGINT DEFAULT 0,
    stars INTEGER DEFAULT 0,
    forks INTEGER DEFAULT 0,
    issues_open INTEGER DEFAULT 0,
    last_updated TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, name, version)
);

CREATE INDEX idx_packages_platform ON packages(platform);
CREATE INDEX idx_packages_name ON packages(name);
CREATE INDEX idx_packages_updated ON packages(updated_at);

-- Files table (for package files)
CREATE TABLE IF NOT EXISTS package_files (
    id SERIAL PRIMARY KEY,
    package_id INTEGER REFERENCES packages(id) ON DELETE CASCADE,
    filename VARCHAR(500) NOT NULL,
    size_bytes BIGINT,
    hash VARCHAR(128),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_files_package ON package_files(package_id);

-- Dependencies table
CREATE TABLE IF NOT EXISTS dependencies (
    id SERIAL PRIMARY KEY,
    package_id INTEGER REFERENCES packages(id) ON DELETE CASCADE,
    dependency_name VARCHAR(255) NOT NULL,
    dependency_version VARCHAR(100),
    dependency_type VARCHAR(50), -- runtime, dev, peer, optional
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_deps_package ON dependencies(package_id);

-- News articles table
CREATE TABLE IF NOT EXISTS news_articles (
    id SERIAL PRIMARY KEY,
    source VARCHAR(100) NOT NULL,
    title TEXT NOT NULL,
    url VARCHAR(1000) NOT NULL UNIQUE,
    content TEXT,
    author VARCHAR(255),
    published_at TIMESTAMP,
    tags TEXT[],
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_news_source ON news_articles(source);
CREATE INDEX idx_news_published ON news_articles(published_at);

-- Monitoring logs table
CREATE TABLE IF NOT EXISTS monitoring_logs (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(50) NOT NULL,
    action VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL, -- success, failure, partial
    duration_ms INTEGER,
    items_processed INTEGER DEFAULT 0,
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_logs_platform ON monitoring_logs(platform);
CREATE INDEX idx_logs_created ON monitoring_logs(created_at);

-- Skills table (for unbrowse-generated skills)
CREATE TABLE IF NOT EXISTS skills (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    platform VARCHAR(50) NOT NULL,
    skill_type VARCHAR(50), -- api, scraper, parser
    endpoint VARCHAR(500),
    method VARCHAR(10),
    parameters JSONB,
    response_schema JSONB,
    success_rate DECIMAL(5,2) DEFAULT 100.00,
    avg_latency_ms INTEGER,
    last_used TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_skills_platform ON skills(platform);
CREATE INDEX idx_skills_name ON skills(name);

-- Create views for analytics
CREATE OR REPLACE VIEW platform_stats AS
SELECT 
    platform,
    COUNT(*) as total_packages,
    COUNT(DISTINCT name) as unique_packages,
    MAX(updated_at) as last_sync,
    AVG(downloads_monthly) as avg_monthly_downloads
FROM packages
GROUP BY platform;

CREATE OR REPLACE VIEW monitoring_health AS
SELECT 
    platform,
    COUNT(*) as total_runs,
    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful_runs,
    AVG(duration_ms) as avg_duration_ms,
    MAX(created_at) as last_run
FROM monitoring_logs
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY platform;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO openclaw;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO openclaw;
EOF

    # Script 3: Generate skills
    cat > "$DEPLOYMENT_DIR/init-scripts/03-generate-skills.sh" << 'EOF'
#!/bin/bash
set -euo pipefail

echo "[INIT] Generating platform skills..."

# Create skills directory structure
mkdir -p /skills/{npm,pypi,github,dockerhub,vsix,chrome,firefox,news}

# Generate NPM skills
cat > /skills/npm/npm-search.skill.ts << 'SKILL_EOF'
// Auto-generated by unbrowse-openclaw
export async function npmSearch(query: string, limit: number = 20) {
  const response = await fetch(
    `https://registry.npmjs.org/-/v1/search?text=${encodeURIComponent(query)}&size=${limit}`
  );
  return await response.json();
}
SKILL_EOF

cat > /skills/npm/npm-package-info.skill.ts << 'SKILL_EOF'
// Auto-generated by unbrowse-openclaw
export async function npmPackageInfo(packageName: string) {
  const response = await fetch(
    `https://registry.npmjs.org/${encodeURIComponent(packageName)}`
  );
  return await response.json();
}
SKILL_EOF

# Generate PyPI skills
cat > /skills/pypi/pypi-search.skill.ts << 'SKILL_EOF'
// Auto-generated by unbrowse-openclaw
export async function pypiSearch(query: string) {
  const response = await fetch(
    `https://pypi.org/search/?q=${encodeURIComponent(query)}`
  );
  // Note: PyPI doesn't have a JSON search API, would need HTML parsing
  // or use third-party APIs like pypistats
  return await response.text();
}
SKILL_EOF

cat > /skills/pypi/pypi-package-info.skill.ts << 'SKILL_EOF'
// Auto-generated by unbrowse-openclaw
export async function pypiPackageInfo(packageName: string) {
  const response = await fetch(
    `https://pypi.org/pypi/${encodeURIComponent(packageName)}/json`
  );
  return await response.json();
}
SKILL_EOF

# Generate GitHub skills
cat > /skills/github/github-search-repos.skill.ts << 'SKILL_EOF'
// Auto-generated by unbrowse-openclaw
export async function githubSearchRepos(query: string, token?: string) {
  const headers: Record<string, string> = {
    'Accept': 'application/vnd.github.v3+json'
  };
  if (token) {
    headers['Authorization'] = `token ${token}`;
  }
  
  const response = await fetch(
    `https://api.github.com/search/repositories?q=${encodeURIComponent(query)}`,
    { headers }
  );
  return await response.json();
}
SKILL_EOF

echo "[INIT] Skills generated successfully!"
echo "[INIT] Skills location: /skills/"
EOF

    chmod +x "$DEPLOYMENT_DIR/init-scripts/03-generate-skills.sh"
    
    log_success "Initialization scripts generated!"
}

# Generate documentation
generate_documentation() {
    log_info "Generating documentation..."
    
    cat > "$DEPLOYMENT_DIR/docs/DEPLOYMENT.md" << 'EOF'
# OpenClaw Stack Deployment Guide

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- Node.js 18+
- Git
- 4GB RAM minimum
- 20GB disk space

## Quick Start

1. **Configure environment:**
   ```bash
   cd openclaw-deployment
   cp .env.template .env
   # Edit .env with your API keys and credentials
   ```

2. **Start the stack:**
   ```bash
   docker-compose up -d
   ```

3. **Initialize (first time only):**
   ```bash
   docker-compose --profile init up init
   ```

4. **Verify deployment:**
   ```bash
   docker-compose ps
   docker-compose logs -f openclaw
   ```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     OpenClaw Stack                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐      ┌──────────────┐                   │
│  │   OpenClaw   │◄────►│  unbrowse    │                   │
│  │   Container  │      │   Plugin     │                   │
│  └──────┬───────┘      └──────────────┘                   │
│         │                                                   │
│         ├──────────────┬──────────────┬──────────────┐    │
│         ▼              ▼              ▼              ▼    │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌────────┐│
│  │PostgreSQL│   │  Neo4j   │   │  Skills  │   │  Logs  ││
│  │ Database │   │  (opt)   │   │ Storage  │   │        ││
│  └──────────┘   └──────────┘   └──────────┘   └────────┘│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

### Platform Configuration

Edit `configs/platforms.yml` to enable/disable platforms and adjust polling intervals.

### Environment Variables

Key variables in `.env`:
- `OPENCLAW_API_KEY`: Your OpenClaw API key
- `GITHUB_TOKEN`: GitHub personal access token
- `POSTGRES_PASSWORD`: Database password
- `POLL_INTERVAL_*`: Polling intervals for each platform

## Monitoring

### Health Checks

```bash
# Check all services
docker-compose ps

# Check OpenClaw health
curl http://localhost:3000/health

# Check database
docker-compose exec postgres pg_isready
```

### Logs

```bash
# View all logs
docker-compose logs -f

# View specific service
docker-compose logs -f openclaw

# View initialization logs
docker-compose logs init
```

### Database Queries

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U openclaw

# View platform stats
SELECT * FROM platform_stats;

# View monitoring health
SELECT * FROM monitoring_health;
```

## Troubleshooting

### unbrowse Plugin Not Working

```bash
# Reinstall unbrowse
docker-compose --profile init up init --force-recreate
```

### Database Connection Issues

```bash
# Check database is running
docker-compose ps postgres

# Check database logs
docker-compose logs postgres

# Verify credentials in .env
```

### Skills Not Generating

```bash
# Check skills directory
ls -la volumes/skills/

# Regenerate skills
docker-compose exec openclaw /init-scripts/03-generate-skills.sh
```

## Scaling

### Horizontal Scaling

To scale OpenClaw workers:
```bash
docker-compose up -d --scale openclaw=3
```

### Database Optimization

For high-volume deployments:
1. Increase PostgreSQL shared_buffers
2. Enable connection pooling (PgBouncer)
3. Add read replicas

## Backup

### Database Backup

```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dump -U openclaw openclaw > backup.sql

# Restore
docker-compose exec -T postgres psql -U openclaw openclaw < backup.sql
```

### Skills Backup

```bash
# Backup skills
tar -czf skills-backup.tar.gz volumes/skills/
```

## Updates

### Update OpenClaw

```bash
docker-compose pull openclaw
docker-compose up -d openclaw
```

### Update unbrowse

```bash
cd projects/unbrowse-openclaw
git pull origin stable
docker-compose --profile init up init --force-recreate
```

## Security

1. **Change default passwords** in `.env`
2. **Use secrets management** for production (Docker secrets, Vault)
3. **Enable TLS** for database connections
4. **Restrict network access** using firewall rules
5. **Regular updates** of all components

## Support

- OpenClaw: https://github.com/openclaw/openclaw
- unbrowse: https://github.com/lekt9/unbrowse-openclaw
- ClawWork: https://github.com/HKUDS/ClawWork
EOF

    log_success "Documentation generated!"
}

# Main deployment function
deploy() {
    log_info "Starting OpenClaw Stack deployment..."
    log_info "Deployment directory: $DEPLOYMENT_DIR"
    
    check_prerequisites
    create_directory_structure
    clone_projects
    generate_docker_compose
    generate_env_template
    generate_platform_config
    generate_init_scripts
    generate_documentation
    
    log_success "Deployment structure created successfully!"
    echo ""
    log_info "Next steps:"
    echo "  1. cd $DEPLOYMENT_DIR"
    echo "  2. Edit .env with your API keys and credentials"
    echo "  3. docker-compose up -d"
    echo "  4. docker-compose --profile init up init"
    echo "  5. Check logs: docker-compose logs -f"
    echo ""
    log_info "Documentation: $DEPLOYMENT_DIR/docs/DEPLOYMENT.md"
}

# Run deployment
deploy
