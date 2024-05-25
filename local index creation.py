# moving local

from llama_index.core import VectorStoreIndex, Settings, StorageContext, SimpleDirectoryReader
from llama_index.readers.github import GithubClient, GithubRepositoryReader
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.duckdb import DuckDBVectorStore
from llama_index.readers.web import WholeSiteReader
from dotenv import load_dotenv
from tqdm import tqdm
import httpx
import torch
import sys
import os

load_dotenv()
github_client = GithubClient(os.getenv('GITHUB_TOKEN'))
device = "cuda" if torch.cuda.is_available() else "cpu"
print("GPU available:", torch.cuda.is_available())
Settings.embed_model = HuggingFaceEmbedding(model_name="avsolatorio/NoInstruct-small-Embedding-v0", device=device)
embed_dim=384

'''DISCORD DATA'''
print("Loading local files...")
dir_path = 'DiscordDocs'
reader = SimpleDirectoryReader(input_dir=dir_path, required_exts=[".txt"])
discord_docs = reader.load_data()

print("Local files loaded successfully. Setting up vector store for Discord data...")
discord_vector_store = DuckDBVectorStore(database_name="discord.duckdb", embed_dim=embed_dim, persist_dir="./db_files/")
discord_storage_context = StorageContext.from_defaults(vector_store=discord_vector_store)

discord_index = VectorStoreIndex.from_documents(discord_docs, storage_context=discord_storage_context, show_progress=True)
print("Discord data setup complete.")

'''WIKI DATA'''
scraper = WholeSiteReader(
    prefix="https://github.com/commaai/openpilot/wiki/", max_depth=2
)
wiki = scraper.load_data(
    base_url="https://github.com/commaai/openpilot/wiki"
)

print("Wiki data downloaded successfully. Setting up vector store for wiki...")
wiki_vector_store = DuckDBVectorStore(database_name="wiki.duckdb", embed_dim=embed_dim, persist_dir="./db_files/")
wiki_storage_context = StorageContext.from_defaults(vector_store=wiki_vector_store)

wiki_index = VectorStoreIndex.from_documents(wiki, storage_context=wiki_storage_context, show_progress=True)
print("Wiki index setup complete.")

'''RETROPILOT STOREFRONT DATA'''
retropilot_scraper = WholeSiteReader(
    prefix="https://shop.retropilot.org/", max_depth=2
)
retropilot_data = retropilot_scraper.load_data(
    base_url="https://shop.retropilot.org/"
)

print("RetroPilot data downloaded successfully. Setting up vector store for RetroPilot...")
retropilot_vector_store = DuckDBVectorStore(database_name="retropilot.duckdb", embed_dim=embed_dim, persist_dir="./db_files/")
retropilot_storage_context = StorageContext.from_defaults(vector_store=retropilot_vector_store)

retropilot_index = VectorStoreIndex.from_documents(retropilot_data, storage_context=retropilot_storage_context, show_progress=True)
print("RetroPilot index setup complete.")

'''ONECLONE DATA'''
oneclone_scraper = WholeSiteReader(
    prefix="https://oneclone.net/", max_depth=2
)
oneclone_data = oneclone_scraper.load_data(
    base_url="https://oneclone.net/"
)

print("OneClone data downloaded successfully. Setting up vector store for OneClone...")
oneclone_vector_store = DuckDBVectorStore(database_name="oneclone.duckdb", embed_dim=embed_dim, persist_dir="./db_files/")
oneclone_storage_context = StorageContext.from_defaults(vector_store=oneclone_vector_store)

oneclone_index = VectorStoreIndex.from_documents(oneclone_data, storage_context=oneclone_storage_context, show_progress=True)
print("OneClone index setup complete.")

'''SPRINGER ELECTRONICS DATA'''
springer_scraper = WholeSiteReader(
    prefix="https://springerelectronics.com/", max_depth=2
)
springer_data = springer_scraper.load_data(
    base_url="https://springerelectronics.com/"
)

print("Springer Electronics data downloaded successfully. Setting up vector store for Springer Electronics...")
springer_vector_store = DuckDBVectorStore(database_name="springer.duckdb", embed_dim=embed_dim, persist_dir="./db_files/")
springer_storage_context = StorageContext.from_defaults(vector_store=springer_vector_store)

springer_index = VectorStoreIndex.from_documents(springer_data, storage_context=springer_storage_context, show_progress=True)
print("Springer Electronics index setup complete.")

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
        "repo": "openpilot-docs",
        "branch": "gh-pages",
        "filter_directories": (["docs"], GithubRepositoryReader.FilterType.INCLUDE),
        "filter_file_extensions": ([".s"], GithubRepositoryReader.FilterType.EXCLUDE),
    },
    {
        "owner": "commaai",
        "repo": "comma10k",
        "branch": "master",
        "filter_directories": (["imgs", "imgs2", "imgsd", "masks", "masks2", "masksd"], GithubRepositoryReader.FilterType.EXCLUDE),
        "filter_file_extensions": ([".png", ".jpg"], GithubRepositoryReader.FilterType.EXCLUDE),
    },
    {
        "owner": "FrogAi",
        "repo": "FrogPilot",
        "branch": "FrogPilot-Development",
        "filter_directories": (["selfdrive", "README.md", "docs", "tools"], GithubRepositoryReader.FilterType.INCLUDE),
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
        github_vector_store = DuckDBVectorStore(database_name=f"{config['owner']}-{config['repo']}.duckdb", embed_dim=embed_dim, persist_dir="./db_files/")
        github_storage_context = StorageContext.from_defaults(vector_store=github_vector_store)

        github_index = VectorStoreIndex.from_documents(documents, storage_context=github_storage_context, show_progress=True)
        print(f"{config['owner']}/{config['repo']} index setup complete.")

    except httpx.ConnectTimeout:
        print(f"Connection timeout for {config['owner']}/{config['repo']}.", file=sys.stderr)
        sys.exit(1)