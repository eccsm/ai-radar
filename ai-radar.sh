#!/bin/bash
# AI Radar Startup Script (Bash version)
# Enhanced startup script for the complete AI Radar system

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOCKER_COMPOSE_FILE="docker-compose.yaml"
PROFILE="dev"

# Service groups
INFRASTRUCTURE_SERVICES="db nats minio"
SETUP_SERVICES="toolhub"
APPLICATION_SERVICES="api"
AGENT_SERVICES="fetcher scheduler summariser"
UI_SERVICES="ui-dev"

# Helper functions
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

# Check if Docker is available
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        exit 1
    fi
    
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not available"
        exit 1
    fi
    
    log_success "Docker and Docker Compose are available"
}

# Initialize database
init_database() {
    log_info "Initializing database schema..."
    
    # Wait for database to be ready
    local max_attempts=30
    for ((i=1; i<=max_attempts; i++)); do
        if docker compose --profile $PROFILE exec -T db psql -U ai -d ai_radar -c "SELECT 1;" &> /dev/null; then
            log_success "Database is ready"
            break
        fi
        
        if [ $i -eq $max_attempts ]; then
            log_error "Database failed to become ready"
            return 1
        fi
        
        log_info "Waiting for database... ($i/$max_attempts)"
        sleep 2
    done
    
    # Create schema and tables
    log_info "Creating ai_radar schema..."
    docker compose --profile $PROFILE exec -T db psql -U ai -d ai_radar -c "CREATE SCHEMA IF NOT EXISTS ai_radar;" > /dev/null
    
    log_info "Creating sources table..."
    docker compose --profile $PROFILE exec -T db psql -U ai -d ai_radar << 'EOF'
CREATE TABLE IF NOT EXISTS ai_radar.sources (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL DEFAULT 'rss',
    active BOOLEAN NOT NULL DEFAULT true,
    last_fetched_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
EOF

    log_info "Creating articles table..."
    docker compose --profile $PROFILE exec -T db psql -U ai -d ai_radar << 'EOF'
CREATE TABLE IF NOT EXISTS ai_radar.articles (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES ai_radar.sources(id),
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    author TEXT,
    published_at TIMESTAMP WITH TIME ZONE NOT NULL,
    content TEXT,
    summary TEXT,
    importance_score FLOAT DEFAULT 0.5,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
EOF

    log_info "Adding sample RSS sources..."
    docker compose --profile $PROFILE exec -T db psql -U ai -d ai_radar << 'EOF'
INSERT INTO ai_radar.sources (name, url, source_type, active) 
VALUES 
    ('TechCrunch AI', 'https://techcrunch.com/category/artificial-intelligence/feed/', 'rss', true),
    ('Wired AI', 'https://www.wired.com/feed/tag/artificial-intelligence/latest/rss', 'rss', true),
    ('MIT Technology Review', 'https://www.technologyreview.com/feed/', 'rss', true),
    ('VentureBeat AI', 'https://venturebeat.com/ai/feed/', 'rss', true),
    ('The Verge AI', 'https://www.theverge.com/ai-artificial-intelligence/rss/index.xml', 'rss', true)
ON CONFLICT (url) DO NOTHING;
EOF

    log_success "Database initialization completed!"
}

# Start service group
start_services() {
    local services="$1"
    local group_name="$2"
    
    log_info "Starting $group_name services: $services"
    
    if docker compose --profile $PROFILE up -d $services; then
        log_success "$group_name services started"
        return 0
    else
        log_error "Failed to start $group_name services"
        return 1
    fi
}

# Check service health
check_service_health() {
    local service="$1"
    local max_attempts=12
    
    for ((i=1; i<=max_attempts; i++)); do
        if docker compose --profile $PROFILE ps --status running "$service" -q &> /dev/null; then
            log_success "$service is running"
            return 0
        fi
        
        log_info "Waiting for $service to start ($i/$max_attempts)..."
        sleep 5
    done
    
    log_warning "$service failed to start within timeout"
    return 1
}

# Trigger initial feeds
trigger_feeds() {
    log_info "Triggering initial RSS feed fetch..."
    
    # Try the simple fetcher first (more reliable)
    if [ -f "./simple_fetcher.py" ]; then
        if command -v python3 &> /dev/null; then
            python3 ./simple_fetcher.py
        elif command -v python &> /dev/null; then
            python ./simple_fetcher.py
        else
            log_warning "Python not found, skipping feed fetch"
            return 1
        fi
        log_success "RSS feeds fetched successfully!"
        return 0
    fi
    
    # Fallback to NATS trigger method
    if [ -f "./trigger_feed.py" ]; then
        if command -v python3 &> /dev/null; then
            python3 ./trigger_feed.py
        elif command -v python &> /dev/null; then
            python ./trigger_feed.py
        else
            log_warning "Python not found, skipping initial feed trigger"
            return 1
        fi
        log_success "Initial RSS feeds triggered!"
    else
        log_warning "No feed trigger scripts found"
        return 1
    fi
}

# Check database contents
check_database() {
    log_info "Checking database contents..."
    
    if ! docker compose --profile $PROFILE exec -T db psql -U ai -d ai_radar -c "SELECT 1;" &> /dev/null; then
        log_error "Database is not accessible"
        return 1
    fi
    
    log_info "Active RSS sources:"
    docker compose --profile $PROFILE exec -T db psql -U ai -d ai_radar -c "SELECT COUNT(*) FROM ai_radar.sources WHERE active = true;"
    
    log_info "Total articles:"
    docker compose --profile $PROFILE exec -T db psql -U ai -d ai_radar -c "SELECT COUNT(*) FROM ai_radar.articles;"
    
    log_info "Recent articles:"
    docker compose --profile $PROFILE exec -T db psql -U ai -d ai_radar -c "SELECT title, created_at FROM ai_radar.articles ORDER BY created_at DESC LIMIT 5;"
}

# Show help
show_help() {
    echo "AI Radar Management Script"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  up           - Start complete AI Radar system"
    echo "  down         - Stop all services"
    echo "  restart      - Restart all services"
    echo "  status       - Show service status"
    echo "  logs [svc]   - Show logs for service"
    echo "  infra        - Start infrastructure only"
    echo "  agents       - Start agents only"
    echo "  init-db      - Initialize database"
    echo "  check-db     - Check database contents"
    echo "  trigger      - Trigger RSS feeds (simple direct fetch)
  fetch        - Fetch RSS feeds using simple method"
    echo "  help         - Show this help"
}

# Main startup function
start_all() {
    log_info "🚀 Starting AI Radar system..."
    
    check_docker
    
    # Start infrastructure
    if ! start_services "$INFRASTRUCTURE_SERVICES" "Infrastructure"; then
        log_error "Failed to start infrastructure"
        exit 1
    fi
    
    # Wait a bit for infrastructure
    sleep 10
    
    # Initialize database
    init_database
    
    # Start setup services
    start_services "$SETUP_SERVICES" "Setup"
    sleep 5
    
    # Start application services (continue even if API fails)
    if ! start_services "$APPLICATION_SERVICES" "Application"; then
        log_warning "API services had issues, continuing with agents"
    fi
    
    # Start agent services
    if ! start_services "$AGENT_SERVICES" "AI Agents"; then
        log_warning "Some agent services had issues"
    fi
    
    # Start UI services
    if ! start_services "$UI_SERVICES" "UI"; then
        log_warning "UI services had issues"
    fi
    
    # Wait for services to fully start
    sleep 10
    
    # Trigger initial feeds
    trigger_feeds
    
    log_success "🎉 AI Radar system startup complete!"
    echo ""
    echo "Access points:"
    echo "  UI:  http://localhost:3000"
    echo "  API: http://localhost:8000"
    echo ""
    echo "Use '$0 check-db' to verify article fetching"
    echo "Use '$0 logs fetcher' to monitor feed processing"
}

# Main script logic
case "${1:-help}" in
    "up")
        start_all
        ;;
    "down")
        log_info "Stopping all services..."
        docker compose --profile $PROFILE down
        log_success "All services stopped"
        ;;
    "restart")
        log_info "Restarting all services..."
        docker compose --profile $PROFILE down
        sleep 5
        start_all
        ;;
    "status")
        docker compose --profile $PROFILE ps
        ;;
    "logs")
        if [ -n "$2" ]; then
            docker compose --profile $PROFILE logs -f "$2"
        else
            log_error "Please specify a service: $0 logs <service>"
        fi
        ;;
    "infra")
        check_docker
        start_services "$INFRASTRUCTURE_SERVICES" "Infrastructure"
        ;;
    "agents")
        check_docker
        start_services "$AGENT_SERVICES" "AI Agents"
        ;;
    "init-db")
        check_docker
        init_database
        ;;
    "check-db")
        check_database
        ;;
    "trigger"|"fetch")
        trigger_feeds
        ;;
    "help"|*)
        show_help
        ;;
esac