# Discord Roleplay Session Bot - Setup Guide

## Overview
This Discord bot allows users to register vehicles and notifies them when roleplay sessions start.

## Prerequisites
- Python 3.8+
- A Discord Server where you have Administrator permissions
- Discord Developer Account

## Step 1: Create a Discord Application

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name (e.g., "Roleplay Bot")
3. Go to the "Bot" section and click "Add Bot"
4. Under the TOKEN section, click "Copy" to copy your bot token
5. **IMPORTANT**: Keep this token secret! Never share it publicly.

## Step 2: Set Bot Permissions

1. Go to "OAuth2" → "URL Generator"
2. Under "SCOPES", select: `bot`
3. Under "PERMISSIONS", select:
   - Send Messages
   - Embed Links
   - Read Message History
   - Manage Messages
4. Copy the generated URL and open it in your browser to add the bot to your server

## Step 3: Set Up Environment

1. Create a `.env` file in the same directory as the bot script:
```
DISCORD_BOT_TOKEN=your_bot_token_here
```

2. Replace `your_bot_token_here` with your actual bot token from Step 1

## Step 4: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 5: Run the Bot

```bash
python roleplay_bot.py
```

You should see: `[BotName] has connected to Discord!`

## Commands

### User Commands

#### `/register_vehicle`
Register a new vehicle with the following parameters:
- **year**: Vehicle model year (YYYY format, numeric only)
- **model**: Vehicle model name (e.g., "Mustang")
- **trim**: Vehicle trim name (e.g., "GT")
- **color**: Vehicle color (e.g., "Red")
- **plate**: License plate (max 7 characters)
- **state**: State of registration (e.g., "CA")
- **owner**: Vehicle owner username (Discord username)

**Example:**
```
/register_vehicle year:2023 model:Mustang trim:GT color:Red plate:ABC1234 state:CA owner:JohnDoe
```

#### `/my_vehicles`
View all vehicles you've registered.

#### `/remove_vehicle`
Remove a vehicle by its number.

**Example:**
```
/remove_vehicle vehicle_number:1
```

### Admin Commands

#### `/start_session`
Start a roleplay session and notify all users with registered vehicles.
- **session_name**: Name of the roleplay session (required)
- **description**: Optional description of the session

**Example:**
```
/start_session session_name:"Downtown Chase" description:"High speed pursuit downtown"
```

This command will:
- Send a DM notification to every user with registered vehicles
- Show them how many vehicles they have
- Display the session name and description

#### `/all_vehicles`
View all vehicles registered by all users (Admin only).

### Staff Commands

#### `/loa_request`
Submit a Leave of Absence (LOA) request. Restricted to Staff (a defined list of Staff roles, or Administrators). Opens a form asking for:
- **Start Date & Time** (format `YYYY-MM-DD HH:MM`, e.g. `2025-06-15 18:00`)
- **End Date & Time** (same format)
- **Reason**

The request is saved as **Pending** until HR reviews it.

#### `/loa_approve` (HR only)
Shows a dropdown of every pending LOA request. Selecting one approves it and DMs the requester.

#### `/loa_reject` (HR only)
Shows a dropdown of every pending LOA request. Selecting one rejects it and DMs the requester.

`/loa_approve` and `/loa_reject` are restricted to the HR role (or Administrators).

#### `/say`
Sends a message as the bot itself, in the current channel or an optional channel you specify. Restricted to a specific role (or Administrators).

**Example:**
```
/say message:"Server maintenance starts in 10 minutes." channel:#announcements
```

#### `/supervise_start` / `/supervise_end`
Start/end a private supervised (staff training) session. Restricted to Staff Trainer / Admins. `/supervise_start` posts a notification with the session code hidden.

Pressing **Reveal Session Code** on that notification behaves differently depending on who clicks it:
- **The person who started the session** (first time only): a form pops up asking for **Area Of Roleplay (AORP)** and **FRP Speed Limit**. Submitting it posts a full session notification - code fully shown, no early access - to the Session 1 channel, exactly like `/start_session` would.
- **Anyone else with access** (Staff Trainer, Staff In Training, other Admins), or the starter again after it's already been released: just see the raw code in an ephemeral reply. They have no way to trigger the Session 1 release themselves.

## Data Storage

LOA requests are stored in a `loa_requests.json` file, created automatically. Each entry looks like:

```json
{
  "a1b2c3d4": {
    "request_id": "a1b2c3d4",
    "user_id": "123456789012345678",
    "username": "discord_username",
    "start": "2025-06-15 18:00",
    "end": "2025-06-20 18:00",
    "reason": "Family trip",
    "status": "pending",
    "requested_at": "2025-06-01T10:30:00",
    "decided_by": null,
    "decided_at": null
  }
}
```

Vehicles are stored in a `vehicles.json` file created automatically in the bot's directory. The format is:

```json
{
  "user_id": {
    "username": "discord_username",
    "vehicles": [
      {
        "year": "2023",
        "model": "Mustang",
        "trim": "GT",
        "color": "Red",
        "plate": "ABC1234",
        "state": "CA",
        "owner": "JohnDoe",
        "registered_at": "2024-01-15T10:30:00"
      }
    ]
  }
}
```

## Troubleshooting

### Bot doesn't connect
- Check if the `DISCORD_BOT_TOKEN` is correct in `.env`
- Make sure the bot is added to your server
- Check if the bot has the necessary permissions

### Commands don't appear
- Restart the bot
- Make sure the bot has been given Administrator permissions
- Try restarting Discord

### Notification not received
- Check if your DMs are open in the server (allow direct messages from server members)
- Verify the user has registered vehicles

## Features

✅ **Vehicle Registration** - Register vehicles with detailed information
✅ **Data Validation** - Validates all input before storing
✅ **Session Notifications** - Notify all users when a session starts
✅ **Vehicle Management** - View and remove vehicles
✅ **Admin Tools** - View all registered vehicles
✅ **Error Handling** - Comprehensive error messages
✅ **Persistent Storage** - Vehicles saved to JSON file

## Customization

You can modify:
- The embed colors (change `discord.Color.green()`, etc.)
- Validation rules in the `validate_vehicle_data()` function
- Notification messages
- Add database support instead of JSON (SQLite, PostgreSQL, etc.)

## Security Notes

- Never commit `.env` file to version control
- Keep your bot token private
- Use environment variables for sensitive data
- Regularly rotate your bot token if compromised

## Support

For issues or improvements, check the discord.py documentation:
https://discordpy.readthedocs.io/
