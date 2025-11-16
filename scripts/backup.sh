#!/bin/bash

# Backup Script for AP/AR Working-Capital Copilot
# Usage: ./backup.sh

set -euo pipefail

# Configuration
DB_HOST="postgres"
DB_PORT="5432"
DB_NAME="deal_desk_os_prod"
DB_USER="deal_desk"
BACKUP_DIR="/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/deal_desk_os_backup_${TIMESTAMP}.sql"
RETENTION_DAYS=30

# Create backup directory if it doesn't exist
mkdir -p "${BACKUP_DIR}"

# Log file
LOG_FILE="${BACKUP_DIR}/backup.log"
exec > >(tee -a "${LOG_FILE}")
exec 2>&1

echo "================================"
echo "Backup started at $(date)"
echo "================================"

# Create database backup
echo "Creating database backup..."
if pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" > "${BACKUP_FILE}"; then
    echo "Database backup created successfully: ${BACKUP_FILE}"

    # Compress the backup
    echo "Compressing backup..."
    gzip "${BACKUP_FILE}"
    BACKUP_FILE_GZ="${BACKUP_FILE}.gz"
    echo "Backup compressed: ${BACKUP_FILE_GZ}"

    # Verify backup file
    if [ -f "${BACKUP_FILE_GZ}" ] && [ -s "${BACKUP_FILE_GZ}" ]; then
        BACKUP_SIZE=$(du -h "${BACKUP_FILE_GZ}" | cut -f1)
        echo "Backup verification successful. Size: ${BACKUP_SIZE}"
    else
        echo "ERROR: Backup verification failed!"
        exit 1
    fi
else
    echo "ERROR: Database backup failed!"
    exit 1
fi

# Clean up old backups
echo "Cleaning up old backups (older than ${RETENTION_DAYS} days)..."
find "${BACKUP_DIR}" -name "deal_desk_os_backup_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
echo "Old backups cleaned up"

# Backup application data (uploads directory)
echo "Creating application data backup..."
UPLOAD_BACKUP_DIR="${BACKUP_DIR}/uploads_backup_${TIMESTAMP}"
if [ -d "/app/uploads" ]; then
    cp -r /app/uploads "${UPLOAD_BACKUP_DIR}"
    tar -czf "${UPLOAD_BACKUP_DIR}.tar.gz" -C "${BACKUP_DIR}" "uploads_backup_${TIMESTAMP}"
    rm -rf "${UPLOAD_BACKUP_DIR}"
    echo "Application data backup created: ${UPLOAD_BACKUP_DIR}.tar.gz"
else
    echo "No uploads directory found, skipping application data backup"
fi

# Clean up old application backups
find "${BACKUP_DIR}" -name "uploads_backup_*.tar.gz" -mtime +${RETENTION_DAYS} -delete

echo "================================"
echo "Backup completed successfully at $(date)"
echo "================================"

# Exit with success
exit 0