### Prerequisites
* Python 3.8+[cite: 3].
* A Discord Server where you have Administrator permissions[cite: 3].
* A Discord Developer Account[cite: 3].

### Step 1: Create a Discord Application
1. Go to the Discord Developer Portal[cite: 3].
2. Click "New Application" and give it a name[cite: 3].
3. Go to the "Bot" section and click "Add Bot"[cite: 3].
4. Under the TOKEN section, click "Copy" to copy your bot token[cite: 3]. Keep this token secret[cite: 3].
5. On the same Bot page, scroll down to **Privileged Gateway Intents** and enable **Server Members Intent** and **Message Content Intent**.

### Step 2: Set Bot Permissions
1. Go to "OAuth2" → "URL Generator"[cite: 3].
2. Under "SCOPES", select: `bot`[cite: 3].
3. Under "PERMISSIONS", select the following:
   * Send Messages[cite: 3].
   * Embed Links[cite: 3].
   * Read Message History[cite: 3].
   * Manage Messages[cite: 3].
   * Manage Roles.
   * Ban Members.
4. Copy the generated URL and open it in your browser to add the bot to your server[cite: 3].

### Step 3: Script Configuration
1. Create a `.env` file in the same directory as the bot script containing your token: `DISCORD_BOT_TOKEN=your_bot_token_here`[cite: 3].
2. Open `roleplay_bot.py` and replace the placeholder `BLACKLISTED_ROLE_ID` with the actual ID of a role in your server that has "View Channels" explicitly denied.

### Step 4: Install Dependencies & Run
1. Run `pip install -r requirements.txt` in your terminal[cite: 3].
2. Run `python roleplay_bot.py`[cite: 3].