"""
ZenSensei Integration Service - Integration Registry

Registers all 67 integrations across 9 categories with full metadata.
The registry is the single source of truth for available integrations;
the catalogue API reads directly from it at runtime.

Categories and counts
---------------------
CALENDAR        5  – Google Calendar, Outlook Calendar, Apple Calendar, Calendly, Cal.com
COMMUNICATION   7  – Gmail, Outlook Mail, Slack, Discord, Microsoft Teams, WhatsApp, Telegram
FINANCIAL       8  – Plaid, Stripe, Venmo, PayPal, Coinbase, Robinhood, Mint, YNAB
CONTENT         7  – Goodreads, Spotify, YouTube, Netflix, Kindle, Audible, Pocket
PRODUCTIVITY    8  – Notion, Todoist, Asana, Linear, Jira, Trello, Monday.com, ClickUp
HEALTH          8  – Apple Health, Google Fit, Fitbit, Oura Ring, Whoop, MyFitnessPal, Headspace, Calm
EDUCATION       8  – Canvas LMS, Blackboard, Google Classroom, Khan Academy, Coursera, Duolingo, Anki, Quizlet
SOCIAL          8  – LinkedIn, Twitter/X, Instagram, Facebook, Strava, Meetup, Reddit, GitHub
SMART_HOME      8  – Google Home, Amazon Alexa, Apple HomeKit, Samsung SmartThings, Philips Hue, Nest, Ring, Ecobee

Total: 67
"""

from __future__ import annotations

from typing import Optional

from shared.models.integrations import IntegrationCategory

from .base import IntegrationMetadata

# ─── Registry data ─────────────────────────────────────────────────────────────────────────────

_REGISTRY: list[IntegrationMetadata] = [

    # ── CALENDAR (5) ───────────────────────────────────────────────────────────────────────

    IntegrationMetadata(
        id="google_calendar",
        name="Google Calendar",
        category=IntegrationCategory.CALENDAR,
        icon_name="logos:google-calendar",
        description="Sync your Google Calendar events as graph Event nodes to track time allocation against goals.",
        required_scopes=[
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/userinfo.email",
        ],
        oauth_url_template=(
            "https://accounts.google.com/o/oauth2/v2/auth"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&scope={scopes}"
            "&state={state}"
            "&access_type=offline"
            "&prompt=consent"
        ),
        supports_webhook=True,
        poll_interval_minutes=15,
    ),

    IntegrationMetadata(
        id="outlook_calendar",
        name="Outlook Calendar",
        category=IntegrationCategory.CALENDAR,
        icon_name="logos:microsoft-outlook",
        description="Connect Outlook Calendar to surface your work and personal events in the knowledge graph.",
        required_scopes=["Calendars.Read", "User.Read", "offline_access"],
        oauth_url_template=(
            "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&scope={scopes}"
            "&state={state}"
            "&response_mode=query"
        ),
        supports_webhook=True,
        poll_interval_minutes=15,
    ),

    IntegrationMetadata(
        id="apple_calendar",
        name="Apple Calendar",
        category=IntegrationCategory.CALENDAR,
        icon_name="logos:apple",
        description="Import Apple Calendar events via CalDAV to track personal commitments alongside your goals.",
        required_scopes=[],
        oauth_url_template=None,
        supports_webhook=False,
        poll_interval_minutes=30,
        is_oauth=False,
    ),

    IntegrationMetadata(
        id="calendly",
        name="Calendly",
        category=IntegrationCategory.CALENDAR,
        icon_name="simple-icons:calendly",
        description="Sync Calendly scheduled meetings to automatically log meetings with contacts in your graph.",
        required_scopes=["default"],
        oauth_url_template=(
            "https://auth.calendly.com/oauth/authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=15,
    ),

    IntegrationMetadata(
        id="cal_com",
        name="Cal.com",
        category=IntegrationCategory.CALENDAR,
        icon_name="simple-icons:cal-dot-com",
        description="Connect Cal.com to track scheduled meetings and coaching sessions in your knowledge graph.",
        required_scopes=["READ_BOOKING", "READ_EVENT_TYPE"],
        oauth_url_template=(
            "https://app.cal.com/oauth/authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=15,
    ),

    # ── COMMUNICATION (7) ───────────────────────────────────────────────────────────────────────

    IntegrationMetadata(
        id="gmail",
        name="Gmail",
        category=IntegrationCategory.COMMUNICATION,
        icon_name="logos:gmail",
        description="Analyse Gmail to extract contacts and relationship patterns, enriching your Person nodes.",
        required_scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/userinfo.email",
        ],
        oauth_url_template=(
            "https://accounts.google.com/o/oauth2/v2/auth"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&scope={scopes}"
            "&state={state}"
            "&access_type=offline"
            "&prompt=consent"
        ),
        supports_webhook=False,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="outlook_mail",
        name="Outlook Mail",
        category=IntegrationCategory.COMMUNICATION,
        icon_name="logos:microsoft-outlook",
        description="Connect Outlook Mail to surface communication patterns and key contacts in your graph.",
        required_scopes=["Mail.Read", "User.Read", "offline_access"],
        oauth_url_template=(
            "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=False,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="slack",
        name="Slack",
        category=IntegrationCategory.COMMUNICATION,
        icon_name="logos:slack",
        description="Integrate Slack to track team interactions, channels you're active in, and key collaborators.",
        required_scopes=["channels:read", "im:read", "users:read", "users:read.email"],
        oauth_url_template=(
            "https://slack.com/oauth/v2/authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=15,
    ),

    IntegrationMetadata(
        id="discord",
        name="Discord",
        category=IntegrationCategory.COMMUNICATION,
        icon_name="logos:discord",
        description="Connect Discord to log community participation and social connections in your knowledge graph.",
        required_scopes=["identify", "guilds", "guilds.members.read"],
        oauth_url_template=(
            "https://discord.com/api/oauth2/authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="microsoft_teams",
        name="Microsoft Teams",
        category=IntegrationCategory.COMMUNICATION,
        icon_name="logos:microsoft-teams",
        description="Sync Microsoft Teams meetings and chats to capture collaboration patterns.",
        required_scopes=["Chat.Read", "User.Read", "offline_access"],
        oauth_url_template=(
            "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=15,
    ),

    IntegrationMetadata(
        id="whatsapp",
        name="WhatsApp",
        category=IntegrationCategory.COMMUNICATION,
        icon_name="logos:whatsapp",
        description="Connect WhatsApp Business API to log key conversations and contact interactions.",
        required_scopes=["whatsapp_business_messaging", "whatsapp_business_management"],
        oauth_url_template=(
            "https://www.facebook.com/v18.0/dialog/oauth"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&scope={scopes}"
            "&state={state}"
            "&response_type=code"
        ),
        supports_webhook=True,
        poll_interval_minutes=15,
    ),

    IntegrationMetadata(
        id="telegram",
        name="Telegram",
        category=IntegrationCategory.COMMUNICATION,
        icon_name="logos:telegram",
        description="Integrate Telegram to capture group participation and direct message patterns.",
        required_scopes=[],
        oauth_url_template=None,
        supports_webhook=True,
        poll_interval_minutes=15,
        is_oauth=False,
    ),

    # ── FINANCIAL (8) ─────────────────────────────────────────────────────────────────────────────

    IntegrationMetadata(
        id="plaid",
        name="Plaid (Banking)",
        category=IntegrationCategory.FINANCIAL,
        icon_name="simple-icons:plaid",
        description="Link bank accounts via Plaid to sync transactions as FinancialArtifact nodes aligned to your goals.",
        required_scopes=["transactions", "accounts", "balance"],
        oauth_url_template=None,  # Uses Plaid Link flow
        supports_webhook=True,
        poll_interval_minutes=60,
        is_oauth=False,
    ),

    IntegrationMetadata(
        id="stripe",
        name="Stripe",
        category=IntegrationCategory.FINANCIAL,
        icon_name="logos:stripe",
        description="Connect Stripe to track revenue, payments, and business financial milestones.",
        required_scopes=["read_only"],
        oauth_url_template=(
            "https://connect.stripe.com/oauth/authorize"
            "?response_type=code"
            "&client_id={client_id}"
            "&scope=read_only"
            "&redirect_uri={redirect_uri}"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="venmo",
        name="Venmo",
        category=IntegrationCategory.FINANCIAL,
        icon_name="simple-icons:venmo",
        description="Sync Venmo transactions to visualise social spending patterns and shared expense relationships.",
        required_scopes=["payments", "profile"],
        oauth_url_template=(
            "https://api.venmo.com/v1/oauth/authorize"
            "?client_id={client_id}"
            "&scope={scopes}"
            "&response_type=code"
            "&redirect_uri={redirect_uri}"
            "&state={state}"
        ),
        supports_webhook=False,
        poll_interval_minutes=60,
    ),

    IntegrationMetadata(
        id="paypal",
        name="PayPal",
        category=IntegrationCategory.FINANCIAL,
        icon_name="logos:paypal",
        description="Connect PayPal to log transactions and business payments in your financial knowledge graph.",
        required_scopes=["openid", "profile", "email", "https://uri.paypal.com/services/transactions/read"],
        oauth_url_template=(
            "https://www.paypal.com/connect"
            "?flowEntry=static"
            "&client_id={client_id}"
            "&scope={scopes}"
            "&redirect_uri={redirect_uri}"
            "&state={state}"
            "&response_type=code"
        ),
        supports_webhook=True,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="coinbase",
        name="Coinbase",
        category=IntegrationCategory.FINANCIAL,
        icon_name="logos:coinbase",
        description="Sync Coinbase portfolio and transactions to track crypto holdings as financial nodes.",
        required_scopes=["wallet:accounts:read", "wallet:transactions:read"],
        oauth_url_template=(
            "https://www.coinbase.com/oauth/authorize"
            "?response_type=code"
            "&client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="robinhood",
        name="Robinhood",
        category=IntegrationCategory.FINANCIAL,
        icon_name="simple-icons:robinhood",
        description="Connect Robinhood to track stock portfolio changes and investing activity over time.",
        required_scopes=["accounts", "investments"],
        oauth_url_template=None,
        supports_webhook=False,
        poll_interval_minutes=60,
        is_oauth=False,
    ),

    IntegrationMetadata(
        id="mint",
        name="Mint",
        category=IntegrationCategory.FINANCIAL,
        icon_name="simple-icons:mint",
        description="Import Mint budgets and transaction categories to analyse spending against financial goals.",
        required_scopes=[],
        oauth_url_template=None,
        supports_webhook=False,
        poll_interval_minutes=120,
        is_oauth=False,
    ),

    IntegrationMetadata(
        id="ynab",
        name="YNAB",
        category=IntegrationCategory.FINANCIAL,
        icon_name="simple-icons:youneedabudget",
        description="Sync YNAB budgets and transactions to align real spending with your financial milestones.",
        required_scopes=["default"],
        oauth_url_template=(
            "https://app.ynab.com/oauth/authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&state={state}"
        ),
        supports_webhook=False,
        poll_interval_minutes=30,
    ),

    # ── CONTENT (7) ─────────────────────────────────────────────────────────────────────────────

    IntegrationMetadata(
        id="goodreads",
        name="Goodreads",
        category=IntegrationCategory.CONTENT,
        icon_name="simple-icons:goodreads",
        description="Sync your Goodreads reading list to create Book content nodes linked to learning goals.",
        required_scopes=["profile", "updates.read"],
        oauth_url_template=(
            "https://www.goodreads.com/oauth/authorize"
            "?oauth_token={state}"
        ),
        supports_webhook=False,
        poll_interval_minutes=60,
    ),

    IntegrationMetadata(
        id="spotify",
        name="Spotify",
        category=IntegrationCategory.CONTENT,
        icon_name="logos:spotify",
        description="Connect Spotify to analyse listening patterns, discover mood correlations, and track podcast learning.",
        required_scopes=[
            "user-read-recently-played",
            "user-top-read",
            "user-read-playback-state",
        ],
        oauth_url_template=(
            "https://accounts.spotify.com/authorize"
            "?response_type=code"
            "&client_id={client_id}"
            "&scope={scopes}"
            "&redirect_uri={redirect_uri}"
            "&state={state}"
        ),
        supports_webhook=False,
        poll_interval_minutes=15,
    ),

    IntegrationMetadata(
        id="youtube",
        name="YouTube",
        category=IntegrationCategory.CONTENT,
        icon_name="logos:youtube",
        description="Sync YouTube watch history and subscriptions to track educational content consumption.",
        required_scopes=[
            "https://www.googleapis.com/auth/youtube.readonly",
        ],
        oauth_url_template=(
            "https://accounts.google.com/o/oauth2/v2/auth"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&scope={scopes}"
            "&state={state}"
            "&access_type=offline"
        ),
        supports_webhook=False,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="netflix",
        name="Netflix",
        category=IntegrationCategory.CONTENT,
        icon_name="logos:netflix",
        description="Import Netflix viewing activity to surface entertainment habits and time allocation patterns.",
        required_scopes=[],
        oauth_url_template=None,
        supports_webhook=False,
        poll_interval_minutes=120,
        is_oauth=False,
    ),

    IntegrationMetadata(
        id="kindle",
        name="Kindle",
        category=IntegrationCategory.CONTENT,
        icon_name="logos:amazon",
        description="Sync Kindle reading progress and highlights to create Book nodes linked to knowledge goals.",
        required_scopes=[],
        oauth_url_template=None,
        supports_webhook=False,
        poll_interval_minutes=120,
        is_oauth=False,
    ),

    IntegrationMetadata(
        id="audible",
        name="Audible",
        category=IntegrationCategory.CONTENT,
        icon_name="logos:amazon",
        description="Connect Audible to log audiobook listening and link titles to learning and development goals.",
        required_scopes=[],
        oauth_url_template=None,
        supports_webhook=False,
        poll_interval_minutes=120,
        is_oauth=False,
    ),

    IntegrationMetadata(
        id="pocket",
        name="Pocket",
        category=IntegrationCategory.CONTENT,
        icon_name="logos:pocket",
        description="Import your Pocket reading list to capture articles and links as Content nodes in the graph.",
        required_scopes=["get", "add", "modify"],
        oauth_url_template=(
            "https://getpocket.com/auth/authorize"
            "?request_token={state}"
            "&redirect_uri={redirect_uri}"
        ),
        supports_webhook=False,
        poll_interval_minutes=30,
    ),

    # ── PRODUCTIVITY (8) ───────────────────────────────────────────────────────────────────────

    IntegrationMetadata(
        id="notion",
        name="Notion",
        category=IntegrationCategory.PRODUCTIVITY,
        icon_name="logos:notion",
        description="Sync Notion pages and databases to create Content and Task nodes aligned with your projects.",
        required_scopes=["read_content"],
        oauth_url_template=(
            "https://api.notion.com/v1/oauth/authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&state={state}"
            "&owner=user"
        ),
        supports_webhook=False,
        poll_interval_minutes=15,
    ),

    IntegrationMetadata(
        id="todoist",
        name="Todoist",
        category=IntegrationCategory.PRODUCTIVITY,
        icon_name="logos:todoist",
        description="Sync Todoist tasks and projects as Task nodes, linking completion to goal progress.",
        required_scopes=["data:read"],
        oauth_url_template=(
            "https://todoist.com/oauth/authorize"
            "?client_id={client_id}"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=15,
    ),

    IntegrationMetadata(
        id="asana",
        name="Asana",
        category=IntegrationCategory.PRODUCTIVITY,
        icon_name="logos:asana",
        description="Connect Asana to map work tasks and projects directly to your professional goals.",
        required_scopes=["default"],
        oauth_url_template=(
            "https://app.asana.com/-/oauth_authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=15,
    ),

    IntegrationMetadata(
        id="linear",
        name="Linear",
        category=IntegrationCategory.PRODUCTIVITY,
        icon_name="logos:linear",
        description="Sync Linear issues and cycles to track engineering work alongside personal and team goals.",
        required_scopes=["read"],
        oauth_url_template=(
            "https://linear.app/oauth/authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=15,
    ),

    IntegrationMetadata(
        id="jira",
        name="Jira",
        category=IntegrationCategory.PRODUCTIVITY,
        icon_name="logos:jira",
        description="Connect Jira to surface sprint tasks and epic progress as actionable graph nodes.",
        required_scopes=["read:jira-user", "read:jira-work", "offline_access"],
        oauth_url_template=(
            "https://auth.atlassian.com/authorize"
            "?audience=api.atlassian.com"
            "&client_id={client_id}"
            "&scope={scopes}"
            "&redirect_uri={redirect_uri}"
            "&state={state}"
            "&response_type=code"
            "&prompt=consent"
        ),
        supports_webhook=True,
        poll_interval_minutes=15,
    ),

    IntegrationMetadata(
        id="trello",
        name="Trello",
        category=IntegrationCategory.PRODUCTIVITY,
        icon_name="logos:trello",
        description="Sync Trello boards and cards to track visual project management alongside your milestones.",
        required_scopes=["read"],
        oauth_url_template=(
            "https://trello.com/1/authorize"
            "?key={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=token"
            "&scope={scopes}"
            "&state={state}"
            "&name=ZenSensei"
        ),
        supports_webhook=True,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="monday_com",
        name="Monday.com",
        category=IntegrationCategory.PRODUCTIVITY,
        icon_name="simple-icons:monday",
        description="Connect Monday.com to integrate workflow boards and project timelines into your knowledge graph.",
        required_scopes=["boards:read", "users:read", "me:read"],
        oauth_url_template=(
            "https://auth.monday.com/oauth2/authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="clickup",
        name="ClickUp",
        category=IntegrationCategory.PRODUCTIVITY,
        icon_name="logos:clickup",
        description="Sync ClickUp tasks and goals to unify work management with your personal goal graph.",
        required_scopes=["tasks:read", "goals:read"],
        oauth_url_template=(
            "https://app.clickup.com/api"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=15,
    ),

    # ── HEALTH (8) ─────────────────────────────────────────────────────────────────────────────

    IntegrationMetadata(
        id="apple_health",
        name="Apple Health",
        category=IntegrationCategory.HEALTH,
        icon_name="logos:apple",
        description="Import Apple Health data (steps, sleep, heart rate) as HealthMetric nodes for wellness tracking.",
        required_scopes=[],
        oauth_url_template=None,
        supports_webhook=False,
        poll_interval_minutes=60,
        is_oauth=False,
    ),

    IntegrationMetadata(
        id="google_fit",
        name="Google Fit",
        category=IntegrationCategory.HEALTH,
        icon_name="logos:google",
        description="Sync Google Fit activity and sleep data to track health metrics alongside your wellbeing goals.",
        required_scopes=[
            "https://www.googleapis.com/auth/fitness.activity.read",
            "https://www.googleapis.com/auth/fitness.sleep.read",
        ],
        oauth_url_template=(
            "https://accounts.google.com/o/oauth2/v2/auth"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&scope={scopes}"
            "&state={state}"
            "&access_type=offline"
        ),
        supports_webhook=False,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="fitbit",
        name="Fitbit",
        category=IntegrationCategory.HEALTH,
        icon_name="simple-icons:fitbit",
        description="Connect Fitbit to log steps, heart rate, and sleep quality as daily health graph nodes.",
        required_scopes=["activity", "heartrate", "sleep", "profile"],
        oauth_url_template=(
            "https://www.fitbit.com/oauth2/authorize"
            "?response_type=code"
            "&client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="oura_ring",
        name="Oura Ring",
        category=IntegrationCategory.HEALTH,
        icon_name="simple-icons:ouraring",
        description="Sync Oura Ring readiness, sleep stages, and HRV data to model recovery and performance patterns.",
        required_scopes=["daily", "personal", "sleep", "readiness"],
        oauth_url_template=(
            "https://cloud.ouraring.com/oauth/authorize"
            "?response_type=code"
            "&client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=False,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="whoop",
        name="Whoop",
        category=IntegrationCategory.HEALTH,
        icon_name="simple-icons:whoop",
        description="Connect Whoop to track strain, recovery scores, and sleep performance over time.",
        required_scopes=["read:recovery", "read:sleep", "read:workout", "read:profile"],
        oauth_url_template=(
            "https://api.prod.whoop.com/oauth/oauth2/auth"
            "?response_type=code"
            "&client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=False,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="myfitnesspal",
        name="MyFitnessPal",
        category=IntegrationCategory.HEALTH,
        icon_name="simple-icons:myfitnesspal",
        description="Sync MyFitnessPal nutrition logs to analyse dietary patterns and link them to energy goals.",
        required_scopes=["public"],
        oauth_url_template=None,
        supports_webhook=False,
        poll_interval_minutes=60,
        is_oauth=False,
    ),

    IntegrationMetadata(
        id="headspace",
        name="Headspace",
        category=IntegrationCategory.HEALTH,
        icon_name="simple-icons:headspace",
        description="Connect Headspace to log mindfulness sessions and correlate meditation streaks with focus metrics.",
        required_scopes=["activity:read"],
        oauth_url_template=None,
        supports_webhook=False,
        poll_interval_minutes=60,
        is_oauth=False,
    ),

    IntegrationMetadata(
        id="calm",
        name="Calm",
        category=IntegrationCategory.HEALTH,
        icon_name="simple-icons:calm",
        description="Import Calm meditation and sleep stories data to track mindfulness habits over time.",
        required_scopes=[],
        oauth_url_template=None,
        supports_webhook=False,
        poll_interval_minutes=120,
        is_oauth=False,
    ),

    # ── EDUCATION (8) ────────────────────────────────────────────────────────────────────────────

    IntegrationMetadata(
        id="canvas_lms",
        name="Canvas LMS",
        category=IntegrationCategory.EDUCATION,
        icon_name="simple-icons:instructure",
        description="Connect Canvas LMS to track course progress and assignment grades as educational milestones.",
        required_scopes=["url:GET|/api/v1/courses", "url:GET|/api/v1/users/:user_id/courses"],
        oauth_url_template=(
            "{base_url}/login/oauth2/auth"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=60,
    ),

    IntegrationMetadata(
        id="blackboard",
        name="Blackboard",
        category=IntegrationCategory.EDUCATION,
        icon_name="simple-icons:blackboard",
        description="Sync Blackboard course content and grades to map academic progress in your knowledge graph.",
        required_scopes=["read"],
        oauth_url_template=(
            "{base_url}/learn/api/public/v1/oauth2/authorizationcode"
            "?redirect_uri={redirect_uri}"
            "&client_id={client_id}"
            "&response_type=code"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=False,
        poll_interval_minutes=60,
    ),

    IntegrationMetadata(
        id="google_classroom",
        name="Google Classroom",
        category=IntegrationCategory.EDUCATION,
        icon_name="logos:google-classroom",
        description="Connect Google Classroom to track assignments, course work, and learning activity.",
        required_scopes=[
            "https://www.googleapis.com/auth/classroom.courses.readonly",
            "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
        ],
        oauth_url_template=(
            "https://accounts.google.com/o/oauth2/v2/auth"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&scope={scopes}"
            "&state={state}"
            "&access_type=offline"
        ),
        supports_webhook=True,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="khan_academy",
        name="Khan Academy",
        category=IntegrationCategory.EDUCATION,
        icon_name="simple-icons:khanacademy",
        description="Sync Khan Academy exercise progress to track skill mastery and learning streaks.",
        required_scopes=["profile", "exercises", "videos"],
        oauth_url_template=(
            "https://www.khanacademy.org/api/auth2/authorize"
            "?response_type=code"
            "&client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=False,
        poll_interval_minutes=60,
    ),

    IntegrationMetadata(
        id="coursera",
        name="Coursera",
        category=IntegrationCategory.EDUCATION,
        icon_name="logos:coursera",
        description="Import Coursera course completions and certificates as educational milestone nodes.",
        required_scopes=["access_business_api"],
        oauth_url_template=(
            "https://accounts.coursera.org/oauth2/v1/auth"
            "?response_type=code"
            "&client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=False,
        poll_interval_minutes=120,
    ),

    IntegrationMetadata(
        id="duolingo",
        name="Duolingo",
        category=IntegrationCategory.EDUCATION,
        icon_name="logos:duolingo",
        description="Sync Duolingo streaks and XP progress to track language learning goals.",
        required_scopes=[],
        oauth_url_template=None,
        supports_webhook=False,
        poll_interval_minutes=60,
        is_oauth=False,
    ),

    IntegrationMetadata(
        id="anki",
        name="Anki",
        category=IntegrationCategory.EDUCATION,
        icon_name="simple-icons:anki",
        description="Connect AnkiConnect to track flashcard review stats and knowledge retention patterns.",
        required_scopes=[],
        oauth_url_template=None,
        supports_webhook=False,
        poll_interval_minutes=60,
        is_oauth=False,
    ),

    IntegrationMetadata(
        id="quizlet",
        name="Quizlet",
        category=IntegrationCategory.EDUCATION,
        icon_name="simple-icons:quizlet",
        description="Sync Quizlet study sets and practice results to log learning activity and retention.",
        required_scopes=["read"],
        oauth_url_template=(
            "https://quizlet.com/authorize"
            "?response_type=code"
            "&client_id={client_id}"
            "&scope={scopes}"
            "&redirect_uri={redirect_uri}"
            "&state={state}"
        ),
        supports_webhook=False,
        poll_interval_minutes=60,
    ),

    # ── SOCIAL (8) ─────────────────────────────────────────────────────────────────────────────

    IntegrationMetadata(
        id="linkedin",
        name="LinkedIn",
        category=IntegrationCategory.SOCIAL,
        icon_name="logos:linkedin",
        description="Sync LinkedIn connections, posts, and career milestones to enrich your professional graph.",
        required_scopes=["r_liteprofile", "r_emailaddress", "r_basicprofile"],
        oauth_url_template=(
            "https://www.linkedin.com/oauth/v2/authorization"
            "?response_type=code"
            "&client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=False,
        poll_interval_minutes=60,
    ),

    IntegrationMetadata(
        id="twitter_x",
        name="Twitter / X",
        category=IntegrationCategory.SOCIAL,
        icon_name="logos:twitter",
        description="Connect Twitter/X to track social engagement, topics of interest, and network growth.",
        required_scopes=["tweet.read", "users.read", "follows.read", "offline.access"],
        oauth_url_template=(
            "https://twitter.com/i/oauth2/authorize"
            "?response_type=code"
            "&client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&scope={scopes}"
            "&state={state}"
            "&code_challenge=challenge"
            "&code_challenge_method=plain"
        ),
        supports_webhook=True,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="instagram",
        name="Instagram",
        category=IntegrationCategory.SOCIAL,
        icon_name="logos:instagram",
        description="Sync Instagram activity to surface creative output, engagement, and audience growth trends.",
        required_scopes=["instagram_basic", "pages_read_engagement"],
        oauth_url_template=(
            "https://api.instagram.com/oauth/authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&scope={scopes}"
            "&response_type=code"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="facebook",
        name="Facebook",
        category=IntegrationCategory.SOCIAL,
        icon_name="logos:facebook",
        description="Connect Facebook to log social interactions and group participation in your knowledge graph.",
        required_scopes=["public_profile", "user_posts", "user_friends"],
        oauth_url_template=(
            "https://www.facebook.com/v18.0/dialog/oauth"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&scope={scopes}"
            "&state={state}"
            "&response_type=code"
        ),
        supports_webhook=True,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="strava",
        name="Strava",
        category=IntegrationCategory.SOCIAL,
        icon_name="logos:strava",
        description="Sync Strava workouts and social kudos to track athletic activities and fitness social graph.",
        required_scopes=["activity:read_all", "profile:read_all"],
        oauth_url_template=(
            "https://www.strava.com/oauth/authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&scope={scopes}"
            "&state={state}"
            "&approval_prompt=auto"
        ),
        supports_webhook=True,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="meetup",
        name="Meetup",
        category=IntegrationCategory.SOCIAL,
        icon_name="logos:meetup",
        description="Import Meetup RSVPs and event attendance to log community engagement and networking.",
        required_scopes=["basic", "event_management"],
        oauth_url_template=(
            "https://secure.meetup.com/oauth2/authorize"
            "?response_type=code"
            "&client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&state={state}"
        ),
        supports_webhook=False,
        poll_interval_minutes=60,
    ),

    IntegrationMetadata(
        id="reddit",
        name="Reddit",
        category=IntegrationCategory.SOCIAL,
        icon_name="logos:reddit",
        description="Connect Reddit to track subreddit activity, posts, and interests as social graph signals.",
        required_scopes=["identity", "history", "mysubreddits", "read"],
        oauth_url_template=(
            "https://www.reddit.com/api/v1/authorize"
            "?client_id={client_id}"
            "&response_type=code"
            "&state={state}"
            "&redirect_uri={redirect_uri}"
            "&duration=permanent"
            "&scope={scopes}"
        ),
        supports_webhook=False,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="github",
        name="GitHub",
        category=IntegrationCategory.SOCIAL,
        icon_name="logos:github",
        description="Sync GitHub contributions, repos, and issues to map coding activity to engineering goals.",
        required_scopes=["read:user", "repo", "read:org"],
        oauth_url_template=(
            "https://github.com/login/oauth/authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=15,
    ),

    # ── SMART_HOME (8) ──────────────────────────────────────────────────────────────────────────

    IntegrationMetadata(
        id="google_home",
        name="Google Home",
        category=IntegrationCategory.SMART_HOME,
        icon_name="logos:google-home",
        description="Connect Google Home to log routines, device usage, and environmental context signals.",
        required_scopes=[
            "https://www.googleapis.com/auth/sdm.service",
        ],
        oauth_url_template=(
            "https://nestservices.google.com/partnerconnections/{project_id}/auth"
            "?redirect_uri={redirect_uri}"
            "&access_type=offline"
            "&prompt=consent"
            "&client_id={client_id}"
            "&response_type=code"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="amazon_alexa",
        name="Amazon Alexa",
        category=IntegrationCategory.SMART_HOME,
        icon_name="logos:amazon-alexa",
        description="Integrate Alexa routines and smart home device state to capture home automation patterns.",
        required_scopes=["alexa::devices:all:read", "alexa::routines:read"],
        oauth_url_template=(
            "https://www.amazon.com/ap/oa"
            "?client_id={client_id}"
            "&scope={scopes}"
            "&response_type=code"
            "&redirect_uri={redirect_uri}"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=30,
    ),

    IntegrationMetadata(
        id="apple_homekit",
        name="Apple HomeKit",
        category=IntegrationCategory.SMART_HOME,
        icon_name="logos:apple",
        description="Sync Apple HomeKit scenes and automations to log home environment data.",
        required_scopes=[],
        oauth_url_template=None,
        supports_webhook=False,
        poll_interval_minutes=60,
        is_oauth=False,
    ),

    IntegrationMetadata(
        id="samsung_smartthings",
        name="Samsung SmartThings",
        category=IntegrationCategory.SMART_HOME,
        icon_name="simple-icons:samsung",
        description="Connect SmartThings to track device automations and home presence patterns.",
        required_scopes=["r:devices:*", "r:locations:*", "r:scenes:*"],
        oauth_url_template=(
            "https://api.smartthings.com/oauth/authorize"
            "?client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=15,
    ),

    IntegrationMetadata(
        id="philips_hue",
        name="Philips Hue",
        category=IntegrationCategory.SMART_HOME,
        icon_name="simple-icons:philipshue",
        description="Sync Philips Hue lighting scenes and schedules to correlate light environment with productivity.",
        required_scopes=[""],
        oauth_url_template=(
            "https://api.meethue.com/oauth2/auth"
            "?clientid={client_id}"
            "&appid=zensensei"
            "&deviceid=zensensei-sync"
            "&state={state}"
            "&response_type=code"
        ),
        supports_webhook=False,
        poll_interval_minutes=60,
    ),

    IntegrationMetadata(
        id="nest",
        name="Nest",
        category=IntegrationCategory.SMART_HOME,
        icon_name="logos:google",
        description="Connect Nest thermostats and cameras to track home environment and energy usage patterns.",
        required_scopes=[
            "https://www.googleapis.com/auth/sdm.service",
        ],
        oauth_url_template=(
            "https://nestservices.google.com/partnerconnections/{project_id}/auth"
            "?redirect_uri={redirect_uri}"
            "&access_type=offline"
            "&prompt=consent"
            "&client_id={client_id}"
            "&response_type=code"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=True,
        poll_interval_minutes=15,
    ),

    IntegrationMetadata(
        id="ring",
        name="Ring",
        category=IntegrationCategory.SMART_HOME,
        icon_name="simple-icons:ring",
        description="Integrate Ring doorbells and cameras to log home entry/exit events as contextual signals.",
        required_scopes=[],
        oauth_url_template=None,
        supports_webhook=True,
        poll_interval_minutes=30,
        is_oauth=False,
    ),

    IntegrationMetadata(
        id="ecobee",
        name="Ecobee",
        category=IntegrationCategory.SMART_HOME,
        icon_name="simple-icons:ecobee",
        description="Sync Ecobee thermostat data to correlate home climate settings with energy and comfort goals.",
        required_scopes=["SmartRead"],
        oauth_url_template=(
            "https://api.ecobee.com/authorize"
            "?response_type=code"
            "&client_id={client_id}"
            "&redirect_uri={redirect_uri}"
            "&scope={scopes}"
            "&state={state}"
        ),
        supports_webhook=False,
        poll_interval_minutes=30,
    ),
]

# ─── Registry accessors ───────────────────────────────────────────────────────────────────────────

_by_id: dict[str, IntegrationMetadata] = {m.id: m for m in _REGISTRY}
_by_category: dict[IntegrationCategory, list[IntegrationMetadata]] = {}
for _meta in _REGISTRY:
    _by_category.setdefault(_meta.category, []).append(_meta)


def get_all() -> list[IntegrationMetadata]:
    """Return all registered integrations (67 total)."""
    return list(_REGISTRY)


def get_by_id(integration_id: str) -> Optional[IntegrationMetadata]:
    """Return metadata for a specific integration, or ``None`` if not found."""
    return _by_id.get(integration_id)


def get_by_category(category: IntegrationCategory) -> list[IntegrationMetadata]:
    """Return all integrations in a given category."""
    return list(_by_category.get(category, []))


def get_categories() -> list[IntegrationCategory]:
    """Return all categories that have at least one registered integration."""
    return list(_by_category.keys())


def total_count() -> int:
    """Return the total number of registered integrations."""
    return len(_REGISTRY)
