# modules.utils.GPT

from llama_index.core.tools import QueryEngineTool, ToolMetadata, FunctionTool
from llama_index.core.response_synthesizers import CompactAndRefine
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.tools.duckduckgo import DuckDuckGoSearchToolSpec
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.llms import MessageRole as Role
from modules.utils.commons import send_long_message
from llama_index.agent.openai import OpenAIAgent
from llama_index.core.agent import ReActAgent
from llama_index.core.llms import ChatMessage
from llama_index.llms.openai import OpenAI
from disnake.ext import commands
from sqlalchemy import make_url
from dotenv import load_dotenv
import traceback
import asyncio
import openai
import torch
import os

class HistoryChatMessage:
    def __init__(self, content, role, user_name=None, additional_kwargs=None):
        self.content = content
        self.role = role
        self.user_name = user_name
        self.additional_kwargs = additional_kwargs if additional_kwargs else {}

async def fetch_reply_chain(message, max_tokens=4096):
    context, tokens_used = [], 0
    max_tokens -= len(message.content) // 4
    while message.reference and tokens_used < max_tokens:
        try:
            message = await message.channel.fetch_message(message.reference.message_id)
            role = Role.ASSISTANT if message.author.bot else Role.USER
            message_tokens = len(message.content) // 4
            if tokens_used + message_tokens <= max_tokens:
                context.append(HistoryChatMessage(f"{message.content}\n", role, message.author.name if not message.author.bot else None))
                tokens_used += message_tokens
            else:
                break
        except Exception as e:
            print(f"Error fetching reply chain message: {e}")
            break
    return context[::-1]

load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')
Settings.llm = OpenAI(model="gpt-4o", max_tokens=1000)
device = "cuda" if torch.cuda.is_available() else "cpu"
print("GPU available:", torch.cuda.is_available())
Settings.embed_model = HuggingFaceEmbedding(model_name="avsolatorio/NoInstruct-small-Embedding-v0", device=device)

connection_string = os.getenv('POSTGRES_CONNECTION_STRING')
db_name, url = "bot_connect", make_url(connection_string)
embed_dim = 384

search_spec = DuckDuckGoSearchToolSpec()
def site_search(input, site):
    query = input if isinstance(input, str) else input.get('query')
    return search_spec.duckduckgo_full_search(query=f"{query} site:{site}")

sites = ["comma.ai", "oneclone.net", "springerelectronics.com", "shop.retropilot.org"]
s_tools = {
    site: FunctionTool.from_defaults(
        fn=lambda input, site=site: site_search(input, site),
        tool_metadata=ToolMetadata(
            name=f"{site.replace('.', '_')}_Search_Tool",
            description=f"A tool that can be used to search {site} for OpenPilot related products."
        )
    ) for site in sites
}

def create_query_engine(collection_name, tool_name, description):
    vector_store = PGVectorStore.from_params(
        database=db_name,
        host=url.host,
        password=url.password,
        port=url.port,
        user=url.username,
        table_name=f"{collection_name}_docs",
        embed_dim=embed_dim,
        hybrid_search=True,
        text_search_config="english",
        cache_ok=True,
    )
    index = VectorStoreIndex.from_vector_store(vector_store)
    retriever = QueryFusionRetriever(
        [index.as_retriever(vector_store_query_mode="default", similarity_top_k=5),
         index.as_retriever(vector_store_query_mode="sparse", similarity_top_k=12)],
        similarity_top_k=5,
        num_queries=1,
        mode="relative_score",
    )
    tool = QueryEngineTool(
        query_engine=RetrieverQueryEngine(
            retriever=retriever,
            response_synthesizer=CompactAndRefine(),
        ),
        metadata=ToolMetadata(name=tool_name, description=description),
    )
    return tool

collections = {
    "discord": {"tool_name": "Discord_Tool", "description": "Data from Discord related to the OpenPilot community."},
    "openpilot-code": {"tool_name": "OpenPilot_code", "description": "This contains the source code for openpilot."},
    "twilsonco-openpilot": {"tool_name": "NNFF_Tool", "description": "Explanation and analysis of Neural Network FeedForward (NNFF) in OpenPilot. More details: https://github.com/twilsonco/openpilot/tree/log-info"},
    "commaai-openpilot-docs": {"tool_name": "OpenPilot_Docs_Tool", "description": "Official OpenPilot documentation."},
    "wiki": {"tool_name": "Wiki_Tool", "description": "The FrogPilot wiki, this contains FrogPilot data such as settings for FrogPilot. This data is a WIP."},
    "commaai-comma-api": {"tool_name": "CommaAPI_Tool", "description": "Comma Connect API documentation and related information."},
}

query_engine_tools = [create_query_engine(name, data["tool_name"], data["description"]) for name, data in collections.items()]
query_engine_tools.extend(s_tools.values())

async def process_message_with_llm(message, client):
    content = message.content.replace(client.user.mention, '').strip()
    if content:
        try:
            async with message.channel.typing():
                reply_chain = await fetch_reply_chain(message)
                chat_history = [ChatMessage(content=msg.content, role=msg.role, user_name=msg.user_name) for msg in reply_chain]
                channel_prompts = {
                    'bug-reports': (
                        "Assist with bug reports. Request: issue details, Route ID, installed branch name, software update status, car details. "
                        "Compile a report for the user to edit and post in #bug-reports. Remind them to backup their settings. "
                        "Remember, comma connect routes must be accessed from the `https://connect.comma.ai` website. "
                        "Routes are stored on the front page of connect."
                    ),
                    'default': (
                        "Provide accurate responses using server and channel names. "
                        "Give context and related information. Use available tools. "
                        "Maintain respectfulness. If an unknown acronym is encountered, use Discord_Tool to find its meaning and then perform another search with the newly found information. "
                        "Provide source links. Use multiple tools for comprehensive responses."
                    )
                }
                system_prompt = (
                    f"You are '{client.user}', assisting '{message.author}' in the '{message.channel}' of the '{message.guild}' server. "
                    "Keep all information relevant to this server and context. Provide accurate support as an OpenPilot community assistant. "
                    "Respond appropriately to the conversation context. Avoid giving code interaction instructions unless specifically asked. "
                    "Examine code for answers when necessary. Use the provided tools to give comprehensive responses and maintain respectfulness throughout the interaction."
                )
                if hasattr(message.channel, 'parent_id') and message.channel.parent_id == 1162100167110053888:
                    system_prompt += channel_prompts['bug-reports']
                else:
                    system_prompt += channel_prompts['default']
                chat_engine = OpenAIAgent.from_tools(query_engine_tools, system_prompt=system_prompt, verbose=True, max_iterations=20, chat_history=chat_history)
                chat_history.append(ChatMessage(content=content, role="user"))
                chat_response = await asyncio.to_thread(chat_engine.chat, content)
                if not chat_response or not chat_response.response:
                    await message.channel.send("There was an error processing the message." if not chat_response else "I didn't get a response.")
                    return
                chat_history.append(ChatMessage(content=chat_response.response, role="assistant"))
                response_text = [chat_response.response]
                if not reply_chain:
                    response_text.append(f"\n*Reply directly to {client.user.mention}'s messages to maintain conversation context.*")
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
