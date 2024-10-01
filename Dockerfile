# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Install rclone and cron
RUN apt-get update && apt-get install -y rclone cron && apt-get clean

# Set the working directory in the container
WORKDIR /app

# Copy all files from the current directory to /app in the container
COPY . .

# Install Python dependencies
RUN pip install -r requirements.txt

# Make the backup script executable
RUN chmod +x backup_script.sh

# Copy the crontab file to the appropriate location
COPY crontab /etc/cron.d/backup-cron

# Set the correct permissions for the crontab file
RUN chmod 0644 /etc/cron.d/backup-cron

# Apply the crontab
RUN crontab /etc/cron.d/backup-cron

# Command to run the application
CMD ["python", "FrogBot/core.py"]