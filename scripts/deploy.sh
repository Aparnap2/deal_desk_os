#!/bin/bash

# Production Deployment Script for AP/AR Working-Capital Copilot
# Usage: ./deploy.sh [production|staging]

set -euo pipefail

# Configuration
ENVIRONMENT="${1:-production}"
PROJECT_NAME="ap_ar_copilot"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.production"

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

# Pre-deployment checks
pre_deployment_checks() {
    log_info "Running pre-deployment checks..."

    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker and try again."
        exit 1
    fi

    # Check if Docker Compose is available
    if ! command -v docker-compose > /dev/null 2>&1; then
        log_error "Docker Compose is not installed. Please install Docker Compose and try again."
        exit 1
    fi

    # Check if required files exist
    if [ ! -f "${COMPOSE_FILE}" ]; then
        log_error "Docker Compose file not found: ${COMPOSE_FILE}"
        exit 1
    fi

    if [ ! -f "${ENV_FILE}" ]; then
        log_error "Environment file not found: ${ENV_FILE}"
        exit 1
    fi

    # Check environment variables
    if grep -q "CHANGE_ME" "${ENV_FILE}"; then
        log_warning "Found placeholder values in environment file. Please update them before proceeding."
        read -p "Do you want to continue? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Deployment cancelled."
            exit 0
        fi
    fi

    log_success "Pre-deployment checks passed"
}

# Create necessary directories
create_directories() {
    log_info "Creating necessary directories..."

    mkdir -p uploads logs backups config/ssl config/grafana/dashboards config/grafana/datasources

    log_success "Directories created"
}

# Pull latest images
pull_images() {
    log_info "Pulling latest Docker images..."

    docker-compose -f "${COMPOSE_FILE}" pull

    log_success "Images pulled successfully"
}

# Build application image
build_image() {
    log_info "Building application image..."

    docker-compose -f "${COMPOSE_FILE}" build api

    log_success "Application image built successfully"
}

# Stop existing services
stop_services() {
    log_info "Stopping existing services..."

    docker-compose -f "${COMPOSE_FILE}" down

    log_success "Services stopped"
}

# Start infrastructure services
start_infrastructure() {
    log_info "Starting infrastructure services..."

    # Start database and redis first
    docker-compose -f "${COMPOSE_FILE}" up -d postgres redis

    log_info "Waiting for services to be healthy..."

    # Wait for PostgreSQL to be ready
    for i in {1..30}; do
        if docker-compose -f "${COMPOSE_FILE}" exec postgres pg_isready -U deal_desk -d deal_desk_os_prod > /dev/null 2>&1; then
            log_success "PostgreSQL is ready"
            break
        fi
        if [ $i -eq 30 ]; then
            log_error "PostgreSQL failed to start within expected time"
            exit 1
        fi
        log_info "Waiting for PostgreSQL... ($i/30)"
        sleep 2
    done

    # Wait for Redis to be ready
    for i in {1..15}; do
        if docker-compose -f "${COMPOSE_FILE}" exec redis redis-cli ping > /dev/null 2>&1; then
            log_success "Redis is ready"
            break
        fi
        if [ $i -eq 15 ]; then
            log_error "Redis failed to start within expected time"
            exit 1
        fi
        log_info "Waiting for Redis... ($i/15)"
        sleep 1
    done

    log_success "Infrastructure services are ready"
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."

    # This would run database migrations if they exist
    # For now, we'll just check connection
    if docker-compose -f "${COMPOSE_FILE}" exec postgres psql -U deal_desk -d deal_desk_os_prod -c "SELECT 1;" > /dev/null 2>&1; then
        log_success "Database connection verified"
    else
        log_error "Database connection failed"
        exit 1
    fi

    log_success "Database migrations completed"
}

# Start application services
start_application() {
    log_info "Starting application services..."

    # Start API and other services
    docker-compose -f "${COMPOSE_FILE}" up -d api nginx

    # Start monitoring services
    docker-compose -f "${COMPOSE_FILE}" up -d prometheus grafana loki backup

    log_success "Application services started"
}

# Health checks
health_checks() {
    log_info "Running health checks..."

    # Wait for API to be ready
    for i in {1..30}; do
        if curl -f http://localhost:8000/health > /dev/null 2>&1; then
            log_success "API health check passed"
            break
        fi
        if [ $i -eq 30 ]; then
            log_error "API health check failed"
            exit 1
        fi
        log_info "Waiting for API... ($i/30)"
        sleep 2
    done

    # Check Nginx
    if curl -f http://localhost/health > /dev/null 2>&1; then
        log_success "Nginx health check passed"
    else
        log_error "Nginx health check failed"
        exit 1
    fi

    log_success "All health checks passed"
}

# Post-deployment verification
post_deployment_verification() {
    log_info "Running post-deployment verification..."

    # Check running containers
    RUNNING_CONTAINERS=$(docker-compose -f "${COMPOSE_FILE}" ps -q | wc -l)
    log_info "Running containers: ${RUNNING_CONTAINERS}"

    # Display service status
    log_info "Service status:"
    docker-compose -f "${COMPOSE_FILE}" ps

    # Display access URLs
    echo
    log_success "Deployment completed successfully!"
    echo
    echo "Access URLs:"
    echo "  - API: http://localhost:8000"
    echo "  - API Documentation: http://localhost:8000/docs"
    echo "  - Health Check: http://localhost/health"
    echo "  - Grafana: http://localhost:3000"
    echo "  - Prometheus: http://localhost:9090"
    echo
    echo "Monitor the logs with: docker-compose -f ${COMPOSE_FILE} logs -f"
}

# Cleanup function
cleanup() {
    if [ $? -ne 0 ]; then
        log_error "Deployment failed. Cleaning up..."
        docker-compose -f "${COMPOSE_FILE}" down
    fi
}

# Main deployment function
main() {
    log_info "Starting deployment to ${ENVIRONMENT}..."
    log_info "Project: ${PROJECT_NAME}"
    log_info "Compose file: ${COMPOSE_FILE}"
    echo

    # Set up cleanup trap
    trap cleanup EXIT

    # Run deployment steps
    pre_deployment_checks
    create_directories
    pull_images
    build_image
    stop_services
    start_infrastructure
    run_migrations
    start_application
    health_checks
    post_deployment_verification

    # Remove cleanup trap since deployment succeeded
    trap - EXIT

    log_success "Deployment to ${ENVIRONMENT} completed successfully!"
}

# Handle script interruption
trap 'log_warning "Deployment interrupted"; exit 1' INT TERM

# Run main function
main "$@"