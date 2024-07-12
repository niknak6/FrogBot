# moving local

from llama_index.core import VectorStoreIndex, Settings, StorageContext, SimpleDirectoryReader
from llama_index.readers.github import GithubClient, GithubRepositoryReader
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.readers.file import PandasCSVReader
from sqlalchemy import make_url
from dotenv import load_dotenv
from tqdm import tqdm
import psycopg2
import httpx
import torch
import sys
import os

load_dotenv()
github_client = GithubClient(os.getenv('GITHUB_TOKEN'))
device = "cuda" if torch.cuda.is_available() else "cpu"
print("GPU available:", torch.cuda.is_available())
Settings.embed_model = HuggingFaceEmbedding(model_name="avsolatorio/NoInstruct-small-Embedding-v0", device=device)

'''POSTGRES DATABASE CREATION'''
connection_string = os.getenv('POSTGRES_CONNECTION_STRING')
db_name = "bot_connect"
conn = psycopg2.connect(connection_string)
conn.autocommit = True
with conn.cursor() as c:
    c.execute(f"SELECT datname FROM pg_catalog.pg_database WHERE lower(datname) = lower('{db_name}')")
    exists = c.fetchone()
    if not exists:
        c.execute(f"CREATE DATABASE {db_name}")
url = make_url(connection_string)
embed_dim=384

'''DISCORD DATA'''
print("Loading local files...")
reader = SimpleDirectoryReader(input_dir="DiscordDocs")
discord_docs = reader.load_data()
print("Local files loaded successfully. Setting up vector store for Discord data...")
discord_vector_store = PGVectorStore.from_params(
    database=db_name,
    host=url.host,
    password=url.password,
    port=url.port,
    user=url.username,
    table_name="discord_docs",
    embed_dim=embed_dim,
    hybrid_search=True,
    text_search_config="english",
)
discord_storage_context = StorageContext.from_defaults(vector_store=discord_vector_store)
discord_index = VectorStoreIndex.from_documents(discord_docs, storage_context=discord_storage_context, show_progress=True)
print("Discord data setup complete.")

'''WIKI DATA'''
reader = SimpleDirectoryReader(input_dir="FrogWiki")
wiki_docs = reader.load_data()
print("Wiki data downloaded successfully. Setting up vector store for wiki...")
wiki_vector_store = PGVectorStore.from_params(
    database=db_name,
    host=url.host,
    password=url.password,
    port=url.port,
    user=url.username,
    table_name="wiki_docs",
    embed_dim=embed_dim,
    hybrid_search=True,
    text_search_config="english",
)
wiki_storage_context = StorageContext.from_defaults(vector_store=wiki_vector_store)
wiki_index = VectorStoreIndex.from_documents(wiki_docs, storage_context=wiki_storage_context, show_progress=True)
print("Wiki index setup complete.")

'''COMMIT DATA'''
parser = PandasCSVReader()
file_extractor = {".csv": parser}
reader = SimpleDirectoryReader(input_dir="CommitHistory", file_extractor=file_extractor)
commit_docs = reader.load_data()
print("commit data downloaded successfully. Setting up vector store for commit...")
commit_vector_store = PGVectorStore.from_params(
    database=db_name,
    host=url.host,
    password=url.password,
    port=url.port,
    user=url.username,
    table_name="commit_history",
    embed_dim=embed_dim,
    hybrid_search=True,
    text_search_config="english",
)
commit_storage_context = StorageContext.from_defaults(vector_store=commit_vector_store)
commit_index = VectorStoreIndex.from_documents(commit_docs, storage_context=commit_storage_context, show_progress=True)
print("commit index setup complete.")

'''GITHUB DATA'''
repos_config = [
    {
        "owner": "twilsonco",
        "repo": "openpilot",
        "branch": "log-info",
        "filter_directories": (["sec"], GithubRepositoryReader.FilterType.INCLUDE),
        "filter_file_extensions": ([".md"], GithubRepositoryReader.FilterType.INCLUDE),
    },
    {
        "owner": "commaai",
        "repo": "comma-api",
        "branch": "master",
        "filter_directories": ([""], GithubRepositoryReader.FilterType.INCLUDE),
        "filter_file_extensions": ([".s"], GithubRepositoryReader.FilterType.EXCLUDE),
    },
    {
        "owner": "commaai",
        "repo": "openpilot",
        "branch": "master-ci",
        "filter_directories": (["selfdrive", "docs", "tools"], GithubRepositoryReader.FilterType.INCLUDE),
        "filter_file_extensions": ([".py", ".md", ".h", ".cc"], GithubRepositoryReader.FilterType.INCLUDE),
    },
]

for config in tqdm(repos_config, desc="Loading documents from repositories"):
    try:
        loader = GithubRepositoryReader(
            github_client,
            owner=config["owner"],
            repo=config["repo"],
            filter_directories=config["filter_directories"],
            filter_file_extensions=config["filter_file_extensions"],
            verbose=False,
            concurrent_requests=10,
            timeout=10,
            retries=3,
        )
        documents = loader.load_data(branch=config["branch"])

        print(f"{config['owner']}/{config['repo']} data downloaded successfully. Setting up vector store...")
        github_vector_store = PGVectorStore.from_params(
            database=db_name,
            host=url.host,
            password=url.password,
            port=url.port,
            user=url.username,
            table_name=f"{config['owner']}-{config['repo']}_docs",
            embed_dim=embed_dim,
            hybrid_search=True,
            text_search_config="english",
        )
        github_storage_context = StorageContext.from_defaults(vector_store=github_vector_store)
        github_index = VectorStoreIndex.from_documents(documents, storage_context=github_storage_context, show_progress=True)
        print(f"{config['owner']}/{config['repo']} index setup complete.")

    except httpx.ConnectTimeout:
        print(f"Connection timeout for {config['owner']}/{config['repo']}.", file=sys.stderr)
        sys.exit(1)