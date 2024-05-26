# modules.utils.GPT

from llama_index.core.tools import QueryEngineTool, ToolMetadata, FunctionTool
from modules.utils.commons import send_long_message, fetch_reply_chain
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.tools.duckduckgo import DuckDuckGoSearchToolSpec
from llama_index.vector_stores.duckdb import DuckDBVectorStore
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.agent import ReActAgent
from llama_index.core.llms import ChatMessage
from llama_index.llms.openai import OpenAI
from dotenv import load_dotenv
import asyncio
import openai
import torch
import re
import os

load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')
Settings.llm = OpenAI(model="gpt-4o", max_tokens=1000)
device = "cuda" if torch.cuda.is_available() else "cpu"
print("GPU available:", torch.cuda.is_available())
Settings.embed_model = HuggingFaceEmbedding(model_name="avsolatorio/NoInstruct-small-Embedding-v0", device=device)

google_search_spec = DuckDuckGoSearchToolSpec()
search_spec = DuckDuckGoSearchToolSpec()
def site_search(input, site):
    query = input if isinstance(input, str) else input.get('query')
    return search_spec.duckduckgo_full_search(query=query + " site:" + site)

sites = ["comma.ai", "oneclone.net", "springerelectronics.com", "shop.retropilot.org"]
s_tools = {}
for site in sites:
    t_name = site.replace('.', '_')
    desc = f"A tool that can be used to search {site} for OpenPilot related products."
    s_tools[site] = FunctionTool.from_defaults(
        fn=lambda input, site=site: site_search(input, site),
        tool_metadata=ToolMetadata(name=f"{t_name}_Search_Tool", description=desc)
    )

def create_query_engine(collection_name, tool_name, description):
    vector_store = DuckDBVectorStore(database_name=f"{collection_name}.duckdb", embed_dim=384, persist_dir="./db_files/")
    index = VectorStoreIndex.from_vector_store(vector_store)
    engine = index.as_query_engine()
    tool = QueryEngineTool(
        query_engine=engine,
        metadata=ToolMetadata(
            name=tool_name,
            description=description,
        ),
    )
    return tool

collections = {
    "discord": {"tool_name": "Discord_Tool", "description": "Discord data containing information from the OpenPilot community."},
    "FrogAi-FrogPilot": {"tool_name": "FrogPilot_Tool", "description": "The code base and settings for FrogPilot/OpenPilot."},
    "twilsonco-openpilot": {"tool_name": "NNFF_Tool", "description": "The write up and breakdown of NNFF(Neural Network FeedForward) and how it works for OpenPilot. https://github.com/twilsonco/openpilot/tree/log-info"},
    "commaai-openpilot-docs": {"tool_name": "OpenPilot_Docs_Tool", "description": "The official OpenPilot documentation. This DOES NOT include any code or code-related information like settings."},
    "commaai-comma10k": {"tool_name": "Comma10k_Tool", "description": "The comma10k, also known as 'comma pencil', dataset and information."},
    "wiki": {"tool_name": "Wiki_Tool", "description": "The OpenPilot wiki data, contains some sparse but detailed information."},
}

query_engine_tools = [create_query_engine(name, data["tool_name"], data["description"]) for name, data in collections.items()]
query_engine_tools.extend(s_tools.values())

async def process_message_with_llm(message, client):
    content = message.content.replace(client.user.mention, '').strip()
    if content:
        try:
            async with message.channel.typing():
                reply_chain = await fetch_reply_chain(message)
                chat_history = [ChatMessage(content=msg.content, role=msg.role) for msg in reply_chain]
                memory = ChatMemoryBuffer.from_defaults(chat_history=chat_history, token_limit=8000)
                channel_prompts = {
                    'bug-reports': (
                        "In this channel, assist users in writing bug reports by requesting: "
                        "\n- Detailed issue description."
                        "\n- Comma-separated Route ID (if available)."
                        "\n- Installed Branch Name."
                        "\n- Software update status."
                        "\n- Car details (year, make, model)."
                        "\nCompile the information into a report. Encourage the user to copy, edit, and post the report in the #bug-reports channel."
                        "\nAlso, remind them to backup their settings in the device settings tab for easy restoration."
                    ),
                    'default': (
                        "Consider the server and channel names to provide comprehensive, accurate responses. "
                        "\nProvide context and related information for well-rounded answers. "
                        "Use the tools at your disposal to provide the best response. "
                        "\nMaintain a respectful, helpful demeanor. "
                        "If an acronym is unknown, use the Discord_Tool to search for it. "
                        "\nProvide source links when possible."
                        "\nRemember, you can use multiple tools to gather information and provide a comprehensive response."
                    )
                }
                system_prompt = (
                    f"Assistant Name: '{client.user}'.\n"
                    f"Channel: '{message.channel}'.\n"
                    f"Server: '{message.guild}'.\n"
                    f"User: '{message.author}'.\n"
                    "As an OpenPilot community assistant, your role is to provide accurate information and support.\n"
                    "Remember to check the context of the conversation and provide the best response possible.\n"
                    "Avoid instructing the user to edit or interact with code unless they're specifically asking about code. However, you should still examine the code to find answers, especially when the settings table is in code and needs to be read to guide users about the GUI.\n"
                )
                category = message.channel.category
                print("Category:", category.name)
                if category and category.name == 'bug-reports':
                    system_prompt += channel_prompts['bug-reports']
                else:
                    system_prompt += channel_prompts['default']
                print("System Prompt:", system_prompt)
                chat_engine = ReActAgent.from_tools(
                    query_engine_tools,
                    system_prompt=system_prompt,
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