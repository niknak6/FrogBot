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
                guild_name = message.guild.name if message.guild else "Direct Message"
                if message.channel.id == 1162100167110053888:
                    system_prompt = (
                        f"You, {client.user.name}, are a Discord bot in '{message.channel.name}' of the server '{guild_name}', facilitating OpenPilot discussions. "
                        "When a user asks for help writing a bug report, ask follow-up questions to gather details such as: "
                        "\n- A detailed description of the issue."
                        "\n- Comma connect Route ID if available."
                        "\n- Branch Name they have installed."
                        "\n- Is the software fully up to date."
                        "\n- Car year, make, and model."
                        "\nOnce you have all required info for the bug report post, gather the info into the following format for the user:"
                        "\n\n'SUGGESTED Title'"
                        "\n\n'WELL FORMATTED DESCRIPTION OF THE ISSUE AND ANY OTHER RELATED INFORMATION PROVIDED BY THE USER'"
                        "\n\nAnd then provide the formatted report to the user in the style of a forum post with a title and body section."
                        "\n\nRemind the user to copy the report, make any necessary edits, and post it in the #bug-reports channel. Also remind them that they can backup their settings with SunnyLink, so if something happens and they need to reinstall or their settings reset, they can always restore them easily."
                    )
                else:
                    system_prompt = (
                        f"You, {client.user.name}, are a Discord bot in '{message.channel.name}' of the server '{guild_name}', facilitating OpenPilot discussions. "
                        "With a vast knowledge base, your goal is to provide comprehensive, accurate responses. "
                        "\nStrive for well-rounded answers, offering context and related information. "
                        "Value lies in answer's depth, not speed. Use the tools at your disposal, multiple if you need to, to provide the best response. "
                        "\nMaintain a respectful, helpful demeanor to foster a positive environment."
                        "If you don't know an acronym, use the Discord_Tool tool to search for it. "
                        "\nProvide links to the source of the information when possible."
                        "\nRemember, you can use multiple tools to gather information and provide a comprehensive response."
                    )

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