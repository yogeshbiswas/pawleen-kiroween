"""Spooky messages for API errors, plus relative time formatting.

Every message is at most 160 characters and says what the visitor can do next.
Reset times are always relative ("3 hours"), never a clock time or UTC.
"""

import math

MAX_MESSAGE_LENGTH = 160

# Messages with a "{when}" placeholder get a relative duration filled in.
MESSAGES = {
    "visitor_limit": "🌙 The spirits need rest! Your spells return in {when}.",
    "global_cap": "🦇 The photo booth is closed for the night. It reopens in {when}!",
    "config_error": "🕸️ The photo booth isn't open yet. The spirits are still setting up!",
    "no_animal": "The spirits say that's not a pet! 👻 Please upload a photo that shows a pet.",
    "bad_costume": (
        "The spirits couldn't brew that one 👻 "
        "Try something like 'pirate hat with eye patch' or 'superhero cape'."
    ),
    "gatekeeper_failed": (
        "👻 The Gatekeeper dozed off and couldn't check your pet. "
        "Your try wasn't used, so please try again!"
    ),
    "credits_depleted": "🧪 Our cauldron is out of magic. Please come back later!",
    "temporary_failure": "🌩️ A storm is disturbing the spirits. Try again in a moment!",
    "refused": "🔮 The spirits refused this spell. Try a different costume idea!",
    "maker_failed": "🧪 The costume spell fizzled out. Your try wasn't used, so please try again!",
    "maker_timeout": "⏳ The costume took too long to brew. Your try wasn't used, so please try again!",
    "pipeline_timeout": (
        "🧙 The cauldron went cold before the spell finished. "
        "Don't worry, it's on the house. Try again!"
    ),
    "judge_locked": "🔒 The crypt is sealed after too many wrong keys. Try your judge pass again in {when}.",
    "bad_upload": "The spirits can only read photos 📸 Please choose a JPG, PNG or WebP image under 10 MB.",
    "wonky": "🔮 The spell came out a little wonky this time... Want to summon again?",
    "not_verified": (
        "🦉 Our owl inspector fell asleep, so this one wasn't double-checked. "
        "Hope you love it!"
    ),
}


def format_relative(seconds):
    """Return a rounded-up duration such as "1 minute" or "3 hours"."""
    minutes = max(1, math.ceil(seconds / 60))
    if minutes >= 60:
        hours = math.ceil(seconds / 3600)
        return f"{hours} hour" + ("" if hours == 1 else "s")
    return f"{minutes} minute" + ("" if minutes == 1 else "s")

def get_message(code, seconds=None):
    """Return the spooky text for an error code.

    `seconds` is only needed for codes that show a wait time.
    """
    text = MESSAGES[code]
    if "{when}" in text:
        text = text.format(when=format_relative(seconds or 0))
    return text
