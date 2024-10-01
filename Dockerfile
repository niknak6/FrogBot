# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Install rclone and cron
RUN apt-get update && apt-get install -y rclone cron && apt-get clean

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the rest of the application code
COPY . .

# Copy the backup script
COPY backup_script.sh /app/backup_script.sh
RUN chmod +x /app/backup_script.sh

# Set up cron job
COPY crontab /etc/cron.d/backup-cron
RUN chmod 0644 /etc/cron.d/backup-cron
RUN crontab /etc/cron.d/backup-cron

# Command to run the application
CMD ["python", "FrogBot/core.py"]
