# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Install rclone, cron, busybox, and git
RUN apt-get update && \
    apt-get install -y rclone cron busybox git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the contents of the FrogBot directory to /app in the container
COPY . /app

# Update pip and install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Make the backup script executable
RUN chmod +x backup_script.sh

# Copy the crontab file to the appropriate location
COPY crontab /etc/cron.d/backup-cron

# Set the correct permissions for the crontab file
RUN chmod 0644 /etc/cron.d/backup-cron

# Apply the crontab
RUN crontab /etc/cron.d/backup-cron

# Command to run the application
CMD ["python", "core.py"]