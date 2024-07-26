# moving local

from llama_index.core import VectorStoreIndex, Settings, StorageContext, SimpleDirectoryReader
from llama_index.readers.github import GithubClient, GithubRepositoryReader
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.postgres import PGVectorStore
from sqlalchemy.orm import sessionmaker, scoped_session
from llama_index.readers.file import PandasCSVReader
from sqlalchemy import create_engine, make_url, text
from llama_index.readers.web import WholeSiteReader
from dotenv import load_dotenv
from tqdm import tqdm
import psycopg2
import httpx
import sys
import os

load_dotenv()
github_client = GithubClient(os.getenv('GITHUB_TOKEN'))
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5", device="cpu")

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
embed_dim = 384

'''SQLAlchemy engine and session setup'''
def get_engine(connection_string):
    return create_engine(connection_string, pool_size=10, max_overflow=20)

def get_session(engine):
    session_factory = sessionmaker(bind=engine)
    return scoped_session(session_factory)

engine = get_engine(connection_string)

def ensure_schema_exists(conn, schema_name):
    with conn.cursor() as c:
        c.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        c.execute(f'CREATE SCHEMA "{schema_name}"')

schemas = ["schema_wiki", "schema_commit"]
for schema in schemas:
    ensure_schema_exists(conn, schema)

def setup_vector_store(engine, schema_name, table_name, docs):
    with engine.connect() as conn:
        conn.execute(text(f'SET search_path TO "{schema_name}"'))
        
        vector_store = PGVectorStore.from_params(
            database=db_name,
            host=url.host,
            password=url.password,
            port=url.port,
            user=url.username,
            table_name=table_name,
            embed_dim=embed_dim,
            hybrid_search=True,
            text_search_config="english",
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex.from_documents(docs, storage_context=storage_context, show_progress=True)
    return index

'''WIKI DATA'''
scraper = WholeSiteReader(prefix="https://frogpilot.wiki.gg/", max_depth=1)
wiki_docs = scraper.load_data(base_url="https://frogpilot.wiki.gg/wiki/Special:AllPages")
print("Wiki data downloaded successfully. Setting up vector store for wiki...")
wiki_index = setup_vector_store(engine, "schema_wiki", "wiki_docs", wiki_docs)
print("Wiki index setup complete.")

'''COMMIT DATA'''
parser = PandasCSVReader()
file_extractor = {".csv": parser}
reader = SimpleDirectoryReader(input_dir="CommitHistory", file_extractor=file_extractor)
commit_docs = reader.load_data()
print("Commit data downloaded successfully. Setting up vector store for commit...")
commit_index = setup_vector_store(engine, "schema_commit", "commit_history", commit_docs)
print("Commit index setup complete.")

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

        schema_name = f"schema_{config['owner']}_{config['repo']}".replace("-", "_")
        ensure_schema_exists(conn, schema_name)

        print(f"{config['owner']}/{config['repo']} data downloaded successfully. Setting up vector store...")
        github_index = setup_vector_store(engine, schema_name, f"{config['owner']}_{config['repo']}_docs".replace("-", "_"), documents)
        print(f"{config['owner']}/{config['repo']} index setup complete.")

    except httpx.ConnectTimeout:
        print(f"Connection timeout for {config['owner']}/{config['repo']}.", file=sys.stderr)
        sys.exit(1)
