#!/bin/bash

current_date=$(date +%Y-%m-%d)
rclone sync /app/FrogBot/user_points.db dropbox:/user_points_$current_date.db --suffix "-$current_date"