# modules.utils.GPT

from llama_index.vector_stores.elasticsearch import ElasticsearchStore, AsyncDenseVectorStrategy
from llama_index.core.tools import QueryEngineTool, ToolMetadata, FunctionTool
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.llms import ChatMessage, MessageRole as Role
from llama_index.tools.duckduckgo import DuckDuckGoSearchToolSpec
from llama_index.core import Settings, VectorStoreIndex
from modules.utils.commons import send_long_message
from llama_index.agent.openai import OpenAIAgent
from llama_index.llms.openai import OpenAI
from disnake.ext import commands
from core import read_config
import traceback
import tiktoken
import logging
import disnake
import asyncio

class HistoryChatMessage:
    def __init__(self, content, role, user_name=None):
        self.content = content
        self.role = role
        self.user_name = user_name

async def fetch_reply_chain(message, max_tokens=8192):
    encoding = tiktoken.encoding_for_model("gpt-4")
    count_tokens = lambda text: len(encoding.encode(text))
    context = []
    tokens_used = 0
    remaining_tokens = max_tokens - count_tokens(message.content)
    processed_message_ids = set()
    async def process_message(msg):
        nonlocal tokens_used
        if msg.id in processed_message_ids or tokens_used >= remaining_tokens:
            return False
        processed_message_ids.add(msg.id)
        role = Role.ASSISTANT if msg.author.bot else Role.USER
        message_tokens = count_tokens(msg.content)
        if tokens_used + message_tokens > remaining_tokens:
            return False
        context.append(HistoryChatMessage(msg.content, role, msg.author.name))
        tokens_used += message_tokens
        return True
    async def process_thread(thread):
        try:
            thread_starter = await thread.parent.fetch_message(thread.id)
            messages = [thread_starter] + [msg async for msg in thread.history(limit=None, oldest_first=False)]
            for msg in reversed(messages):
                if not await process_message(msg):
                    break
        except Exception as e:
            logging.error(f"Error processing thread: {e}")
    async def process_reply_chain(msg):
        messages = []
        while msg and tokens_used < remaining_tokens:
            messages.append(msg)
            if msg.reference:
                try:
                    msg = await msg.channel.fetch_message(msg.reference.message_id)
                except Exception as e:
                    logging.error(f"Error fetching reply chain message: {e}")
                    break
            else:
                break
        for msg in reversed(messages):
            if not await process_message(msg):
                break
    if isinstance(message.channel, disnake.Thread):
        await process_thread(message.channel)
    else:
        await process_reply_chain(message)
    return context[::-1]

Settings.llm = OpenAI(model='gpt-4o-mini', max_tokens=1000, api_key=read_config().get('OPENAI_API_KEY'))
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5", device="cpu")

search_spec = DuckDuckGoSearchToolSpec()
def site_search(input, site):
    query = input if isinstance(input, str) else input.get('query')
    return search_spec.duckduckgo_full_search(query=f"{query} site:{site}")

def create_site_tool(site):
    return FunctionTool.from_defaults(
        fn=lambda input, site=site: site_search(input, site),
        tool_metadata=ToolMetadata(
            name=f"{site.replace('.', '_')}_Search_Tool",
            description=f"A tool that can be used to search {site} for OpenPilot related products, clones, and other items."
        )
    )

sites = ["comma.ai", "oneclone.net", "springerelectronics.com", "shop.retropilot.org", "torqueinterceptor.com"]
s_tools = {site: create_site_tool(site) for site in sites}

def create_query_engine(collection_name, tool_name, description):
    config = read_config()
    vector_store = ElasticsearchStore(
        index_name=collection_name,
        es_url=config.get('ELASTICSEARCH_URL'),
        retrieval_strategy=AsyncDenseVectorStrategy(hybrid=True)
    )
    index = VectorStoreIndex.from_vector_store(vector_store)
    engine = index.as_query_engine()
    return QueryEngineTool(
        query_engine=engine,
        metadata=ToolMetadata(
            name=tool_name,
            description=description,
        ),
    )

collections = {
    "frogai_frogpilot": {
        "tool_name": "FrogPilot_code",
        "description": "This collection contains the complete source code for FrogPilot, a fork of OpenPilot, an open-source driving agent that performs the functions of Adaptive Cruise Control (ACC) and Lane Keeping Assist System (LKAS) for various car models."
    },
    "commaai_openpilot": {
        "tool_name": "OpenPilot_Docs-Tools",
        "description": "Contains the docs and tools used for OpenPilot."
    },
    "twilsonco_openpilot": {
        "tool_name": "NNFF",
        "description": "This tool provides an in-depth explanation and analysis of the Neural Network FeedForward (NNFF) mechanism used in OpenPilot. It includes detailed documentation and examples to help understand how NNFF is implemented and utilized in the OpenPilot system. More details can be found at: https://github.com/twilsonco/openpilot/tree/log-info"
    },
    "commit": {
        "tool_name": "commit_data",
        "description": "This collection contains the commit history of the FrogPilot codebase. It provides detailed information about each commit, including changes made, authorship, and timestamps, allowing for comprehensive tracking of the project's development over time."
    },
    "wiki": {
        "tool_name": "Wiki",
        "description": "This is the main wiki for FrogPilot, containing extensive data and documentation such as settings, configuration guides, and usage instructions. This data is a work in progress (WIP) and is continuously updated to provide the most accurate and helpful information for users."
    },
}

query_engine_tools = [create_query_engine(name, data["tool_name"], data["description"]) for name, data in collections.items()]
query_engine_tools.extend(s_tools.values())

async def process_message_with_llm(message, client):
    content = message.content.replace(client.user.mention, '').strip()
    if not content:
        return
    try:
        thread = message.channel if isinstance(message.channel, disnake.Thread) else await message.channel.create_thread(name=f"{content[:50]}", message=message)
        reply_chain = await fetch_reply_chain(message)
        chat_history = [ChatMessage(content=msg.content, role=msg.role, user_name=msg.user_name) for msg in reply_chain]
        channel_prompts = {
            'bug-reports': (
                "Gather issue description, Route ID, branch name, update status, and car details. "
                "Draft a report for user review and post in #bug-reports. Remind users to back up settings. "
                "Access routes from `https://connect.comma.ai`. Use tools for accurate information."
            ),
            'default': (
                "Include relevant info and use tools. Maintain a respectful tone. "
                "Verify unknown acronyms with multiple sources. Avoid making up answers."
            )
        }
        system_prompt = (
            "Provide accurate support as an OpenPilot community assistant. "
            "Respond to the conversation context. Avoid code interaction instructions unless asked. "
            "Examine code for answers when necessary. Use tools for comprehensive responses and maintain respectfulness. "
            "Provide source links for all information. Avoid making up answers."
        ) + channel_prompts['bug-reports' if getattr(message.channel, 'parent_id', None) == 1162100167110053888 else 'default']
        async with thread.typing():
            chat_engine = OpenAIAgent.from_tools(query_engine_tools, system_prompt=system_prompt, verbose=False, chat_history=chat_history)
            chat_history.append(ChatMessage(content=content, role="user"))
            chat_response = await asyncio.to_thread(chat_engine.chat, content)
        if chat_response and chat_response.response:
            chat_history.append(ChatMessage(content=chat_response.response, role="assistant"))
            await send_long_message(thread, chat_response.response)
        else:
            await thread.send("There was an error processing the message." if not chat_response else "I didn't get a response.")
    except Exception as e:
        await thread.send(f"An error occurred: {str(e)}")

class OpenPilotAssistant(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if self.client.user in message.mentions:
            await process_message_with_llm(message, self.client)
        else:
            await self.client.process_commands(message)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send("Sorry, I didn't understand that command.")
        else:
            tb_str = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            logging.error(f'An error occurred: {error}\n{tb_str}')

def setup(client):
    client.add_cog(OpenPilotAssistant(client))