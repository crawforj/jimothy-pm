"""All Jimothy-voice copy lives here (plan §7b) — tune tone without touching logic."""

import random

GREETINGS = [
    "Morning. Let's find your one good move.",
    "Hey — here's today, already sorted.",
    "Okay, deep breath. Here's what actually matters today.",
    "Good morning. Yesterday's done is done — here's what's next.",
]

NO_TASKS_TODAY = [
    "Nothing urgent is queued for you today. Suspicious. Enjoy it anyway.",
    "Clear runway today. Go be ambitious or go outside.",
]

WIP_WARNING = [
    "Finish something first — future you says thanks.",
    "That's a lot of open plates. Pick one to close before starting another.",
]

FEASIBILITY_WARNING_TEMPLATES = [
    "{project} is tracking {slip} days past its deadline at the current pace. "
    "Moving lower-priority work out of the way could buy that back.",
    "Heads up: {project} looks {slip} days tight. Nothing's broken yet — "
    "just worth a look before it becomes a scramble.",
]

DEAD_TASK_NOTE = "This one's past its cliff date — it can't deliver value anymore. Consider closing it out."

TRIAGE_NOTE = ("New work, not yet scoped — give these a likely-hours estimate "
              "and they'll join the real queue.")

RETRO_PROMPTS = [
    "What made this week dumber than it needed to be?",
    "What's one thing you'd tell yourself Monday morning if you could?",
    "What almost didn't get done, and why?",
    "What's the most avoidable fire this week?",
]

CLOSEOUT_MESSAGES = [
    "Sprint closed. {velocity}h of committed work landed this week.",
    "That's a wrap — {velocity}h shipped. On to the next one.",
]

WIP_OVER_COMMIT_WARNING = [
    "That's more committed than the week has room for — something's likely rolling forward, and that's fine.",
]


def greeting() -> str:
    return random.choice(GREETINGS)


def no_tasks_message() -> str:
    return random.choice(NO_TASKS_TODAY)


def wip_warning() -> str:
    return random.choice(WIP_WARNING)


def feasibility_warning(project: str, slip: int) -> str:
    return random.choice(FEASIBILITY_WARNING_TEMPLATES).format(project=project, slip=slip)


def retro_prompt() -> str:
    return random.choice(RETRO_PROMPTS)


def closeout_message(velocity: float) -> str:
    return random.choice(CLOSEOUT_MESSAGES).format(velocity=velocity)


def calendar_connected(provider_name: str, account_label: str | None) -> str:
    who = " as %s" % account_label if account_label else ""
    return "Connected to %s%s." % (provider_name, who)


def calendar_disconnected(provider_name: str) -> str:
    return "Disconnected from %s." % provider_name


def calendar_connect_failed(provider_name: str, detail: str) -> str:
    return "Couldn't connect to %s: %s" % (provider_name, detail)


def calendar_not_configured(provider_name: str) -> str:
    return "%s sync isn't available in this build." % provider_name


def ev_summary(spi: float | None, cpi: float | None) -> str:
    """Plain-English SPI/CPI label, per plan §6's example phrasing."""
    if spi is None and cpi is None:
        return "Not enough logged history yet to gauge schedule or budget."
    parts = []
    if spi is not None:
        pct = round(abs(1 - spi) * 100)
        parts.append("on schedule" if pct == 0
                     else "running %d%% ahead of schedule" % pct if spi > 1
                     else "running %d%% behind schedule" % pct)
    if cpi is not None:
        pct = round(abs(1 - cpi) * 100)
        parts.append("on budget" if pct == 0
                     else "%d%% under budget" % pct if cpi > 1
                     else "%d%% over budget" % pct)
    return ", ".join(parts).capitalize() + "."
