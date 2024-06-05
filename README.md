# 🐸 FrogBot

[![GitHub issues](https://img.shields.io/github/issues/idontneedonetho/FrogBot)](https://github.com/idontneedonetho/FrogBot/issues)
[![GitHub stars](https://img.shields.io/github/stars/idontneedonetho/FrogBot)](https://github.com/idontneedonetho/FrogBot/stargazers)
[![License](https://img.shields.io/github/license/idontneedonetho/FrogBot)](https://github.com/idontneedonetho/FrogBot/blob/main/LICENSE)

**FrogBot** is a collaborative effort among a few of us to create the best bot possible. Please note that the bot is still in a very rough state, and things are constantly breaking.

## Table of Contents
- [Branches](#branches)
- [🚀 Current Features](#-current-features)
- [💬 Usage Examples](#-usage-examples)
- [🧱 DLM (_May be depreciated soon_)](#-dlm)
- [🤝 Contributing](#-contributing)
- [📞 Connect](#-connect)
- [🙌 Acknowledgments](#-acknowledgments)

## Branches
- **🔥 Beta:** This is the most updated branch and is constantly being updated and may break.
- **🛠️ Dev:** A go-to point for PRs and other contributions, it's the more stable of the newer branches but not immune to breaking.
- **🕰️ Old:** This is the first revision of the bot; there are a few broken things with it, and we wouldn't recommend using it.

*Note: Dev is considered the starting point for most people, as it's primarily for PRs, and we aim to keep it stable.*

## 🚀 Current Features
- [DLM](#-dlm)
- Automatic role assignment based on points
- Points assignment and removal
- Points tracking
- Add points via reactions
- Updating via commands
- AI LLM and RAG integration via Llama Index
- Reply context chain for the LLM; you can simply reply to the bot's message to continue the conversation
- Web search for specific sites

## 💬 Usage Examples
- To add points to a user: `/add points user`
- To remove points from a user: `/remove points user`
- To check a user's points: `/check_points`
- Ask questions or seek information by mentioning the bot in your message: `@{bot name} What's the current price of a C3?`
- Use `/help` for more information on available commands.

## 🧱 DLM
*(_May be deprecated soon_)*

Dynamically Loaded Modules, or DLM for short, is a different way to add to the bot. Why use this when discord.py has Cogs? Cogs, for me, seem to be hit or miss, and we needed something more robust, something that wouldn't need us to change any other code to work.

What I wanted was a system that would take .py files and load them into the system in an easy-to-use way. If you look at all the modules already here, they can help you with making your own.

Now it isn't perfect, but it's the best we can get and allows most modules to be pretty freeform. If you want to add a feature, simply write a new .py file and make it a PR! For now, I'll work directly with devs of modules to make sure DLM works, and works right.

Hopefully in the future, PRs will be automated to an extent. We'll see... For now, this is where we are.

## 🤝 Contributing
Contributions to FrogBot are welcome! Follow these steps to contribute:
1. Create a DLM.
2. Create a new PR for it.
3. Profit???

## 📞 Connect
For support and questions, join our Discord server: [FrogPilot Discord](https://discord.gg/frogpilot).

*Just go-to [`#bot-general`](https://discord.com/channels/1137853399715549214/1201763192884428861) channel at the bottom!*

## 🙌 Acknowledgments
### Thanks-
- [Joeslinky](https://github.com/Joeslinky)
- [twilsonco](https://github.com/twilsonco)
- [nik.olas](https://github.com/niknak6)
- cone_guy_03312
- pkp24
- [mike854](https://github.com/mike86437)
- [frogsgomoo](https://github.com/FrogAi)
- And all those that help to test the bot

*Disclaimer this README file was written mostly by ChatGPT 3.5 Turbo.*
