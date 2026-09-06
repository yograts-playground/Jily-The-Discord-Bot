# Lily Bot - Comprehensive Setup Guide

## Prerequisites
- Python 3.8 or higher installed on your system.
- A Discord Server with Administrator permissions.
- A Discord Developer Account.

## Step 1: Create and Configure the Discord Application
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application** and name it (e.g., "Lily Bot").
3. Navigate to the **Bot** tab on the left menu:
   - Click **Add Bot**.
   - Under the **Token** section, click **Copy** and keep your token secure. Never share it publicly.
   - **CRITICAL (Privileged Intents):** Scroll down to **Privileged Gateway Intents** and enable both:
     - **Server Members Intent** (Required for role tracking, member lookups, and moderation).
     - **Message Content Intent** (Required for command handling and processing).
4. Save your changes.

## Step 2: Invite the Bot to Your Server
1. Go to **OAuth2** → **URL Generator** in the Developer Portal.
2. Under **Scopes**, check:
   - `bot`
   - `applications.commands`
3. Under **Bot Permissions**, select the following privileges:
   - Administrator (or individual permissions: Send Messages, Embed Links, Read Message History, Manage Messages, Manage Roles, Ban Members).
4. Copy the generated URL at the bottom, paste it into your browser, select your server, and authorize the bot.

## Step 3: Configure Environment Variables
1. Create a file named `.env` in the root directory of your bot project.
2. Add your bot token to the file:
   ```env
   DISCORD_BOT_TOKEN=your_actual_bot_token_here