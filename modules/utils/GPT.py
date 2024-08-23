# modules.utils.GPT

from llama_index.vector_stores.elasticsearch import ElasticsearchStore, AsyncDenseVectorStrategy
from llama_index.core.tools import QueryEngineTool, ToolMetadata, FunctionTool
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.llms import ChatMessage, MessageRole as Role
from llama_index.tools.duckduckgo import DuckDuckGoSearchToolSpec
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.memory import ChatMemoryBuffer
from modules.utils.commons import send_long_message
from llama_index.agent.openai import OpenAIAgent
from llama_index.llms.openai import OpenAI
from disnake.ext import commands
from core import read_config
import traceback
import tiktoken
import disnake
import asyncio
import openai
import torch

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
        if msg.id in processed_message_ids:
            return False
        processed_message_ids.add(msg.id)
        role = Role.ASSISTANT if msg.author.bot else Role.USER
        message_tokens = count_tokens(msg.content)
        if tokens_used + message_tokens > remaining_tokens:
            return False
        context.append(HistoryChatMessage(msg.content, role, msg.author.name))
        tokens_used += message_tokens
        return True
    if isinstance(message.channel, disnake.Thread):
        try:
            top_message = await message.channel.parent.fetch_message(message.channel.id)
            await process_message(top_message)
        except Exception as e:
            print(f"Error fetching top subject message: {e}")
        async for msg in message.channel.history(limit=None, oldest_first=True):
            if not await process_message(msg):
                break
    else:
        while message.reference and tokens_used < remaining_tokens:
            try:
                message = await message.channel.fetch_message(message.reference.message_id)
                if not await process_message(message):
                    break
            except Exception as e:
                print(f"Error fetching reply chain message: {e}")
                break
    return context[::-1]

openai.api_key = read_config().get('OPENAI_API_KEY')
Settings.llm = OpenAI(model='gpt-4o-mini', max_tokens=1000)
device = "cuda" if torch.cuda.is_available() else "cpu"
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5", device=device)

search_spec = DuckDuckGoSearchToolSpec()
def site_search(input, site):
    query = input if isinstance(input, str) else input.get('query')
    return search_spec.duckduckgo_full_search(query=f"{query} site:{site}")

sites = ["comma.ai", "oneclone.net", "springerelectronics.com", "shop.retropilot.org"]
s_tools = {
    site: FunctionTool.from_defaults(
        fn = lambda input, site=site: site_search(input, site),
        tool_metadata = ToolMetadata(
            name = f"{site.replace('.', '_')}_Search_Tool",
            description = f"A tool that can be used to search {site} for OpenPilot related products."
        )
    ) for site in sites
}

def create_query_engine(collection_name, tool_name, description):
    vector_store = ElasticsearchStore(
        index_name = f"{collection_name}",
        es_url = read_config().get('ELASTICSEARCH_URL'),
        retrieval_strategy = AsyncDenseVectorStrategy(hybrid=True)
    )
    index = VectorStoreIndex.from_vector_store(vector_store)
    engine = index.as_query_engine()
    tool = QueryEngineTool(
        query_engine = engine,
        metadata = ToolMetadata(
            name = tool_name,
            description = description,
        ),
    )
    return tool

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
        "tool_name": "NNFF_Tool",
        "description": "This tool provides an in-depth explanation and analysis of the Neural Network FeedForward (NNFF) mechanism used in OpenPilot. It includes detailed documentation and examples to help understand how NNFF is implemented and utilized in the OpenPilot system. More details can be found at: https://github.com/twilsonco/openpilot/tree/log-info"
    },
    "commit": {
        "tool_name": "commit_data",
        "description": "This collection contains the commit history of the FrogPilot codebase. It provides detailed information about each commit, including changes made, authorship, and timestamps, allowing for comprehensive tracking of the project's development over time."
    },
    "wiki": {
        "tool_name": "Wiki_Tool",
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
        async with message.channel.typing():
            reply_chain = await fetch_reply_chain(message)
            chat_history = [ChatMessage(content=msg.content, role=msg.role) for msg in reply_chain]
            memory = ChatMemoryBuffer.from_defaults(chat_history=chat_history, token_limit=8192)
            channel_prompts = {
                'bug-reports': (
                    "Assist with bug reports by gathering: issue description, Route ID, branch name, update status, and car details. "
                    "Draft a report for user review and post in #bug-reports. Remind users to back up settings. "
                    "Access routes from `https://connect.comma.ai`. Use available tools to find accurate information."
                ),
                'default': (
                    "Provide accurate, context-aware responses using server and channel names. "
                    "Include relevant info and use available tools. "
                    "Maintain a respectful tone. Use Wiki_Tool for unknown acronyms and search again. "
                    "Use available tools to find accurate information and avoid making up answers."
                )
            }
            system_prompt = (
                "Ensure all information is relevant to this server and context. Provide accurate support as an OpenPilot community assistant. "
                "Respond appropriately to the conversation context. Avoid code interaction instructions unless asked. "
                "Examine code for answers when necessary. Use provided tools for comprehensive responses and maintain respectfulness. "
                "Provide source links for all information. Use available tools to find accurate information and avoid making up answers."
            ) + channel_prompts['bug-reports' if getattr(message.channel, 'parent_id', None) == 1162100167110053888 else 'default']
            user_msg = ChatMessage(role="user", content=content)
            memory.put(user_msg)
            chat_engine = OpenAIAgent.from_tools(query_engine_tools, system_prompt=system_prompt, verbose=True, memory=memory)
            chat_response = await asyncio.to_thread(chat_engine.chat, content)
        if not chat_response or not chat_response.response:
            await message.channel.send("There was an error processing the message." if not chat_response else "I didn't get a response.")
            return
        assistant_msg = ChatMessage(content=chat_response.response, role="assistant")
        memory.put(assistant_msg)
        response_text = [chat_response.response]
        if not reply_chain:
            response_text.append(f"\n*Reply directly to {client.user.mention}'s messages to maintain conversation context.*")
        if not isinstance(message.channel, disnake.Thread):
            thread = await message.channel.create_thread(name=f"{content[:50]}", message=message)
            await send_long_message(thread, '\n'.join(response_text))
        else:
            await send_long_message(message, '\n'.join(response_text))
    except Exception as e:
        await message.channel.send(f"An error occurred: {str(e)}")

class OpenPilotAssistant(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.client.user or message.author.bot:
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
            print(f'An error occurred: {error}\n{tb_str}')

def setup(client):
    client.add_cog(OpenPilotAssistant(client))