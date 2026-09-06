### Overview
Lily (Version 0.1) is a comprehensive Discord roleplay session and moderation bot. It handles vehicle registration, session notifications, law enforcement citations, staff leave of absences (LOA), and strict server moderation tools like role-stripping and delayed blacklisting.

### Setup & Installation
To get Lily up and running on your server, please refer to the official **[Setup Guide](https://github.com/yograts-playground/Jily-The-Discord-Bot/blob/Lily/SETUP_GUIDE.md)**.

### User & Roleplay Commands
* `/version`: Displays the current bot software version (Lily v0.1) and developer credits.
* `/register_vehicle`: Registers a new vehicle requiring year, model, trim, color, plate, state, and owner[cite: 3].
* `/my_vehicles`: Views all vehicles you have registered[cite: 3].
* `/remove_vehicle`: Removes a vehicle by its assigned index number[cite: 3].

### Law Enforcement Commands
* `/issue_citation`: Issues a logged fine to a user and sends them a DM with the citation ID.
* `/my_citations`: Allows any user to check their own outstanding and paid citations.
* `/mark_citation_paid`: Updates a citation's status to paid.

### Session Management Commands
* `/start_session`: Starts a roleplay session, asking for AORP and FRP speeds, and notifies users[cite: 3].
* `/over` & `/force_end`: Ends active sessions and schedules the channel for a message purge.
* `/set_peacetime`: Updates the peacetime status (On, Off, Strict) of an active session.
* `/earlyaccess` & `/release`: Allows law enforcement and session managers to securely reveal the hidden session code on public notifications.

### Staff & HR Commands
* `/loa_request`: Submits a Leave of Absence request requiring start/end dates and a reason[cite: 3].
* `/loa_approve` & `/loa_reject`: Allows HR to review pending LOA requests via dropdowns and automatically notifies the requester[cite: 3].
* `/say`: Sends a message as the bot in a designated channel[cite: 3].
* `/supervise_start` & `/supervise_end`: Manages private staff training sessions[cite: 3].

### Moderation & Admin Commands
* `/infract`: Issues a strike to a user. Staff members climb a separate "Staff Strike" role ladder than regular members.
* `/user_profile`: Displays a user's registered vehicles, total citations, and infraction history.
* `/terminate`: Instantly strips all staff-related roles from a target member (enforces Discord role hierarchy to prevent abuse).
* `/blacklist add`: Strips a user of all roles, assigns a restricted channel role, and starts a randomized 1-3 hour ban countdown.
* `/blacklist remove`: Cancels an active ban countdown and restores all original roles to the user.
* `/all_vehicles`: Admin-only command to view the entire server's vehicle registry[cite: 3].

### Data Storage & Formats
The bot uses local JSON files for persistent storage.

**`vehicles.json`**[cite: 3]
Stores user vehicle registries tied to their Discord ID[cite: 3].
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

**`loa_requests.json`**[cite: 3]
Tracks pending and resolved staff leave requests[cite: 3].
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
    "requested_at": "2025-06-01T10:30:00"
  }
}
```

**`blacklist.json`**
Tracks active ban countdowns and saves user roles for restoration.
```json
{
  "123456789012345678": {
    "username": "discord_username",
    "blacklisted_by": "admin_name",
    "reason": "Severe rule violation",
    "ban_timestamp": 1718478000.0,
    "guild_id": 987654321098765432,
    "saved_roles": [111111111, 222222222]