# modules.utils.memory_check

import os
import psutil
import time
import threading
from datetime import datetime
from disnake.ext import commands

class MemoryMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.interval = 60
        self.process = psutil.Process(os.getpid())
        self.memory_usage_history = []
        self.max_memory_usage = 0
        self.average_memory_usage = 0
        self.running = True
        self.monitor_thread = threading.Thread(target=self.monitor_memory_usage)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def monitor_memory_usage(self):
        while self.running:
            current_memory_usage = self.process.memory_info().rss / (1024 * 1024)
            self.memory_usage_history.append(current_memory_usage)
            self.max_memory_usage = max(self.max_memory_usage, current_memory_usage)
            if len(self.memory_usage_history) > self.interval:
                self.average_memory_usage = sum(self.memory_usage_history) / len(self.memory_usage_history)
                self.memory_usage_history = []  # Reset history every interval
                print(f"[{datetime.now()}] Average Memory Usage: {self.average_memory_usage:.2f} MB, Max Memory Usage: {self.max_memory_usage:.2f} MB")
            time.sleep(1)

    def stop(self):
        self.running = False
        self.monitor_thread.join()

    def cog_unload(self):
        self.stop()

def setup(bot):
    bot.add_cog(MemoryMonitor(bot))
