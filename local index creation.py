# moving local

from llama_index.core import VectorStoreIndex, Settings, StorageContext, SimpleDirectoryReader
from llama_index.readers.github import GithubClient, GithubRepositoryReader
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.readers.web import WholeSiteReader
from dotenv import load_dotenv
from tqdm import tqdm
import chromadb
import httpx
import sys
import os

load_dotenv()
github_client = GithubClient(os.getenv('GITHUB_TOKEN'))
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")
chroma_db = chromadb.PersistentClient(path="./chroma_db")
all_docs = {}

# '''DISCORD DATA'''
# print("Documents loaded successfully. Loading local files...")
# dir_path = 'DiscordDocs'
# reader = SimpleDirectoryReader(input_dir=dir_path, required_exts=[".txt"])
# local_docs = reader.load_data()
# all_docs.update({"local_files": local_docs})
# print("Local files loaded successfully.")

# print("Discord data downloaded successfully. Setting up vector store...")
# discord_collection = chroma_db.create_collection("discord-data")
# discord_vector_store = ChromaVectorStore(chroma_collection=discord_collection)
# discord_storage_context = StorageContext.from_defaults(vector_store=discord_vector_store)
# print("Discord data vector store setup complete.")

# documents = []
# for repo_docs in tqdm(all_docs.values(), desc="Flattening documents"):
#     documents.extend(repo_docs)
# print("Discord data documents flattened successfully. Setting up Discord data index...")

# discord_index = VectorStoreIndex.from_documents(documents, storage_context=discord_storage_context, show_progress=True)
# print("Discord data setup complete.")

'''WIKI DATA'''
scraper = WholeSiteReader(
    prefix="https://github.com/commaai/openpilot/wiki/", max_depth=2
)
wiki = scraper.load_data(
    base_url="https://github.com/commaai/openpilot/wiki"
)

print("Wiki data downloaded successfully. Setting up vector store for wiki...")
wiki_collection = chroma_db.get_or_create_collection("wiki-data")
wiki_vector_store = ChromaVectorStore(chroma_collection=wiki_collection)
wiki_storage_context = StorageContext.from_defaults(vector_store=wiki_vector_store)

wiki_documents = []
for wiki_doc in tqdm(wiki, desc="Flattening wiki documents"):
    wiki_documents.append(wiki_doc)
print("Wiki documents flattened successfully. Setting up index for wiki...")

wiki_index = VectorStoreIndex.from_documents(wiki_documents, storage_context=wiki_storage_context, show_progress=True)
print("Wiki index setup complete.")

# '''GITHUB DATA'''
# repos_config = [
#     {
#         "owner": "twilsonco",
#         "repo": "openpilot",
#         "branch": "log-info",
#         "filter_directories": (["sec"], GithubRepositoryReader.FilterType.INCLUDE),
#         "filter_file_extensions": ([".md"], GithubRepositoryReader.FilterType.INCLUDE),
#     },
#     {
#         "owner": "commaai",
#         "repo": "openpilot-docs",
#         "branch": "master",
#         "filter_directories": (["docs"], GithubRepositoryReader.FilterType.INCLUDE),
#         "filter_file_extensions": ([".md"], GithubRepositoryReader.FilterType.INCLUDE),
#     },
#     {
#         "owner": "commaai",
#         "repo": "comma10k",
#         "branch": "master",
#         "filter_directories": (["imgs", "imgs2", "imgsd", "masks", "masks2", "masksd"], GithubRepositoryReader.FilterType.EXCLUDE),
#         "filter_file_extensions": ([".png", ".jpg"], GithubRepositoryReader.FilterType.EXCLUDE),
#     },
#     {
#         "owner": "FrogAi",
#         "repo": "FrogPilot",
#         "branch": "FrogPilot-Development",
#         "filter_directories": (["selfdrive", "README.md", "docs", "tools"], GithubRepositoryReader.FilterType.INCLUDE),
#         "filter_file_extensions": ([".py", ".md", ".h", ".cc"], GithubRepositoryReader.FilterType.INCLUDE),
#     },
# ]

# for config in tqdm(repos_config, desc="Loading documents from repositories"):
#     try:
#         loader = GithubRepositoryReader(
#             github_client,
#             owner=config["owner"],
#             repo=config["repo"],
#             filter_directories=config["filter_directories"],
#             filter_file_extensions=config["filter_file_extensions"],
#             verbose=False,
#             concurrent_requests=10,
#             timeout=10,
#             retries=3,
#         )
#         documents = loader.load_data(branch=config["branch"])
#         all_docs.update({f"{config['owner']}/{config['repo']}": documents})

#         print(f"{config['owner']}/{config['repo']} data downloaded successfully. Setting up vector store...")
#         github_collection = chroma_db.create_collection(f"{config['owner']}-{config['repo']}-data")
#         github_vector_store = ChromaVectorStore(chroma_collection=github_collection)
#         github_storage_context = StorageContext.from_defaults(vector_store=github_vector_store)

#         github_documents = []
#         for repo_docs in tqdm(all_docs.values(), desc="Flattening documents"):
#             github_documents.extend(repo_docs)
#         print(f"{config['owner']}/{config['repo']} documents flattened successfully. Setting up index...")

#         github_index = VectorStoreIndex.from_documents(github_documents, storage_context=github_storage_context, show_progress=True)
#         print(f"{config['owner']}/{config['repo']} index setup complete.")

#     except httpx.ConnectTimeout:
#         print(f"Connection timeout for {config['owner']}/{config['repo']}.", file=sys.stderr)
#         sys.exit(1)