# modules.utils.commons

from disnake.ext import commands
import logging
import disnake
import re

async def send_message(message, content, should_reply):
    try:
        if should_reply:
            if isinstance(message, disnake.Thread):
                return await message.send(content)
            else:
                return await message.reply(content)
        else:
            return await message.channel.send(content)
    except Exception as e:
        logging.error(f"Error sending message: {e}")
        return None

def split_message(response):
    max_length = 1950
    markdown_chars = ['*', '_', '~', '|']
    words = response.split(' ')
    parts = []
    current_part = ''
    code_block_type = None
    for word in words:
        if len(current_part) + len(word) + 1 > max_length:
            for char in markdown_chars:
                if current_part.count(char) % 2 != 0 and not current_part.endswith('```'):
                    if current_part.rfind(char) > 0 and current_part[current_part.rfind(char) - 1] in [' ', '\n'] and current_part[current_part.rfind(char) + 1] in [' ', '\n']:
                        current_part += char
            code_block_start = current_part.rfind('```')
            code_block_end = current_part.rfind('```', code_block_start + 3)
            if code_block_start != -1 and (code_block_end == -1 or code_block_end < code_block_start):
                code_block_type = current_part[code_block_start + 3:].split('\n', 1)[0]
                current_part += '```'
                word = '```' + (code_block_type + '\n' if code_block_type else '') + word
            parts.append(current_part.strip())
            current_part = ''
        current_part += ' ' + word
    parts.append(current_part.strip())
    return parts

async def send_long_message(message, response, should_reply=True):
    try:
        chunks = re.split(r'(```.*?```)', response, flags=re.DOTALL)
        result = ''
        for chunk in chunks:
            if chunk.startswith('```'):
                result += chunk
            else:
                chunk = re.sub(r'\((http[s]?://\S+)\)', r'(<\1>)', chunk)
                chunk = re.sub(r'(?<![\(<`])http[s]?://\S+(?![>\).,`])', r'<\g<0>>', chunk)
                result += chunk
        response = result
        messages = []
        parts = split_message(response)
        for part in parts:
            last_message = await send_message(message, part, should_reply)
            if last_message is None:
                break
            messages.append(last_message)
            message = last_message
        return messages
    except Exception as e:
        logging.error(f"Error in send_long_message: {e}")
        return None

def is_admin():
    async def predicate(ctx):
        author = ctx.user
        is_admin = author.guild_permissions.administrator
        logging.error(f"Checking admin status for {author} (ID: {author.id}): {is_admin}")
        return is_admin
    return commands.check(predicate)

def is_admin_or_user(user_id=126123710435295232):
    async def predicate(ctx):
        is_admin = ctx.author.guild_permissions.administrator
        is_specific_user = ctx.author.id == user_id
        return is_admin or is_specific_user
    return commands.check(predicate)

def is_admin_or_rank(rank_id=1198482895342411846):
    async def predicate(ctx):
        is_admin = ctx.author.guild_permissions.administrator
        has_rank = any(role.id == rank_id for role in ctx.author.roles)
        return is_admin or has_rank
    return commands.check(predicate)