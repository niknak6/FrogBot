# modules.utils.database

import aiosqlite
import asyncio
import logging

DATABASE_FILE = 'user_points.db'

async def initialize_database():
    try:
        async with aiosqlite.connect(DATABASE_FILE) as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_points (
                    user_id INTEGER PRIMARY KEY,
                    points INTEGER NOT NULL DEFAULT 0
                )
            ''')
            await conn.commit()
    except Exception as e:
        logging.error(f"Error initializing database: {e}")

async def db_access_with_retry(sql_operation, args=(), max_attempts=5, delay=1, timeout=10.0):
    for attempt in range(max_attempts):
        try:
            async with aiosqlite.connect(DATABASE_FILE, timeout=timeout) as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(sql_operation, args)
                    if sql_operation.strip().upper().startswith('SELECT'):
                        results = await cursor.fetchall()
                        return results
                    await conn.commit()
                return
        except aiosqlite.OperationalError as e:
            logging.error(f"Failed to execute sql operation: {e}")
            if attempt == max_attempts - 1:
                raise
            await asyncio.sleep(delay)

async def initialize_points_database(user):
    user_points = {}
    rows = await db_access_with_retry('SELECT * FROM user_points')
    user_points = {user_id: points or 0 for user_id, points in rows}
    if user.id not in user_points:
        user_points[user.id] = 0
        await db_access_with_retry('INSERT INTO user_points (user_id, points) VALUES (?, ?)', (user.id, 0))
    return user_points

async def update_points(user_id, points):
    try:
        await db_access_with_retry('UPDATE user_points SET points = ? WHERE user_id = ?', (points, user_id))
        return True
    except Exception as e:
        logging.error(f"Failed to update points: {e}")
        return False

async def get_user_points(user_id):
    rows = await db_access_with_retry('SELECT points FROM user_points WHERE user_id = ?', (user_id,))
    if rows:
        return rows[0][0]
    return 0