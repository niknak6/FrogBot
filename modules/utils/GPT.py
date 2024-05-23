# modules.utils.GPT

from modules.utils.commons import send_long_message, fetch_reply_chain
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.agent.openai import OpenAIAgent
from llama_index.core.agent import ReActAgent
from llama_index.core.llms import ChatMessage
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

def create_query_engine(collection_name, tool_name, description):
    collection = chroma_db.get_collection(collection_name)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    index = VectorStoreIndex.from_vector_store(vector_store)
    engine = index.as_query_engine(similarity_top_k=5)
    tool = QueryEngineTool(
        query_engine=engine,
        metadata=ToolMetadata(
            name=tool_name,
            description=description,
        ),
    )
    return tool

collections = {
    "discord-data": {"tool_name": "Discord_Tool", "description": "Discord data containing information from the OpenPilot community."},
    "FrogAi-FrogPilot-data": {"tool_name": "FrogPilot_Tool", "description": "A tool to search the FrogPilot/OpenPilot code database."},
    "twilsonco-openpilot-data": {"tool_name": "NNFF_Tool", "description": "The write up and breakdown of NNFF(Neural Network FeedForward) and how it works for OpenPilot."},
    "commaai-openpilot-docs-data": {"tool_name": "OpenPilot_Docs_Tool", "description": "The official OpenPilot documentation. This DOES NOT include any code or code-related information."},
    "commaai-comma10k-data": {"tool_name": "Comma10k_Tool", "description": "The comma10k, also known as 'comma pencil', dataset and information."},
    "wiki-data": {"tool_name": "Wiki_Tool", "description": "The OpenPilot wiki data, contains some sparse but detailed information."},
    "oneclone-data": {"tool_name": "OneClone_Tool", "description": "Data from https://oneclone.net/, an online store that sells OpenPilot hardware."},
    "springer-electronics-data": {"tool_name": "SpringerElectronics_Tool", "description": "Data from https://springerelectronics.com/, an online store that sells OpenPilot hardware."},
    "retropilot-data": {"tool_name": "RetroPilot_Tool", "description": "Data from https://shop.retropilot.org/, an online store that sells OpenPilot hardware."},
}

query_engine_tools = [create_query_engine(name, data["tool_name"], data["description"]) for name, data in collections.items()]

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
                        "With a vast knowledge base, your goal is to provide comprehensive, accurate responses. "
                        "\nStrive for well-rounded answers, offering context and related information. "
                        "Value lies in answer's depth, not speed. Use the tools at your disposal, multiple if you need to, to provide the best response. "
                        "\nMaintain a respectful, helpful demeanor to foster a positive environment."
                        "If you don't know an acyronym, use the Discord_Tool tool to search for it. "
                        "\nProvide links to the source of the information when possible."
                    ),
                    verbose=True,
                    max_iterations=20,
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
