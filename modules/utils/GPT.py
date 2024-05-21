# modules.utils.GPT

from modules.utils.commons import send_long_message, fetch_reply_chain
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core.agent import ReActAgent
from llama_index.core.llms import ChatMessage
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.llms.openai import OpenAI
from dotenv import load_dotenv
import chromadb
import asyncio
import openai
import re
import os

load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')
Settings.llm = OpenAI(model="gpt-4o", max_tokens=1000)
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")

chroma_db = chromadb.PersistentClient(path="./chroma_db")

# Discord Data collection and tool
discord_collection = chroma_db.get_collection("discord-data")
discord_vector_store = ChromaVectorStore(chroma_collection=discord_collection)
discord_index = VectorStoreIndex.from_vector_store(discord_vector_store)
discord_engine = discord_index.as_query_engine(similarity_top_k=5)

# FrogPilot Github Data collection and tool
FrogAi_collection = chroma_db.get_collection("FrogAi-FrogPilot-data")
FrogAi_vector_store = ChromaVectorStore(chroma_collection=FrogAi_collection)
FrogAi_index = VectorStoreIndex.from_vector_store(FrogAi_vector_store)
FrogAi_engine = FrogAi_index.as_query_engine(similarity_top_k=5)

# NNFF Github Data collection and tool
NNFF_collection = chroma_db.get_collection("twilsonco-openpilot-data")
NNFF_vector_store = ChromaVectorStore(chroma_collection=NNFF_collection)
NNFF_index = VectorStoreIndex.from_vector_store(NNFF_vector_store)
NNFF_engine = NNFF_index.as_query_engine(similarity_top_k=5)

# openpilot-docs collection and tool
docs_collection = chroma_db.get_collection("commaai-openpilot-docs-data")
docs_vector_store = ChromaVectorStore(chroma_collection=docs_collection)
docs_index = VectorStoreIndex.from_vector_store(docs_vector_store)
docs_engine = docs_index.as_query_engine(similarity_top_k=5)

# comma10k collection and tool
tenk_collection = chroma_db.get_collection("commaai-comma10k-data")
tenk_vector_store = ChromaVectorStore(chroma_collection=tenk_collection)
tenk_index = VectorStoreIndex.from_vector_store(tenk_vector_store)
tenk_engine = tenk_index.as_query_engine(similarity_top_k=5)

# OpenPilot wiki collection and tools
wiki_collection = chroma_db.get_collection("wiki-data")
wiki_vector_store = ChromaVectorStore(chroma_collection=wiki_collection)
wiki_index = VectorStoreIndex.from_vector_store(wiki_vector_store)
wiki_engine = wiki_index.as_query_engine(similarity_top_k=5)

# Query Engine Tool
query_engine_tools = [
    QueryEngineTool(
        query_engine=discord_engine,
        metadata=ToolMetadata(
            name="Discord_Data",
            description="Discord data containing information from the OpenPilot community.",
        ),
    ),
    QueryEngineTool(
        query_engine=FrogAi_engine,
        metadata=ToolMetadata(
            name="FrogPilot_Data",
            description="A tool to search the FrogPilot/OpenPilot code database.",
        ),
    ),
    QueryEngineTool(
        query_engine=NNFF_engine,
        metadata=ToolMetadata(
            name="NNFF_Data",
            description="The write up and breakdown of NNFF(Neural Network FeedForward) and how it works for OpenPilot.",
        ),
    ),
    QueryEngineTool(
        query_engine=docs_engine,
        metadata=ToolMetadata(
            name="openpilot_docs",
            description="The official OpenPilot documentation. This DOES NOT include any code or code-related information.",
        ),
    ),
    QueryEngineTool(
        query_engine=tenk_engine,
        metadata=ToolMetadata(
            name="comma10k",
            description="The comma10k, also known as 'comma pencil', dataset and information.",
        ),
    ),
    QueryEngineTool(
        query_engine=wiki_engine,
        metadata=ToolMetadata(
            name="openpilot_wiki",
            description="The OpenPilot wiki data, contains some sparse but detailed information.",
        )
    )
]

async def process_message_with_llm(message, client):
    content = message.content.replace(client.user.mention, '').strip()
    if content:
        try:
            async with message.channel.typing():
                reply_chain = await fetch_reply_chain(message)
                chat_history = [ChatMessage(content=msg.content, role=msg.role) for msg in reply_chain]
                memory = ChatMemoryBuffer.from_defaults(chat_history=chat_history, token_limit=8000)
                chat_engine = ReActAgent.from_tools(
                    query_engine_tools,
                    system_prompt=(
                        f"You, {client.user.name}, are a Discord bot in '{message.channel.name}', facilitating OpenPilot discussions. "
                        "\nConsider all provided facts before answering questions or forming a reply. "
                        "With a vast knowledge base, your goal is to provide comprehensive, accurate responses. "
                        "\nStrive for well-rounded answers, offering context and related information. "
                        "Value lies in answer's depth, not speed. Use the tools at your disposal, multiple if you need to, to provide the best response. "
                        "\nMaintain a respectful, helpful demeanor to foster a positive environment."
                        "If you don't know an acyronym, use the Discord_Data tool to search for it. "
                        "\nProvide links to the source of the information when possible."
                    ),
                    verbose=True,
                    allow_parallel_tool_calls=True,
                    memory=memory,
                )
                memory.put(ChatMessage(content=content, role="user"))
                chat_response = await asyncio.to_thread(chat_engine.chat, content)
                if not chat_response or not chat_response.response:
                    await message.channel.send("There was an error processing the message." if not chat_response else "I didn't get a response.")
                    return
                memory.put(ChatMessage(content=chat_response.response, role="assistant"))
                response_text = chat_response.response
                response_text = re.sub(r'^[^:]+:\s(?=[A-Z])', '', response_text)
                await send_long_message(message, response_text)
        except Exception as e:
            await message.channel.send(f"An error occurred: {str(e)}")