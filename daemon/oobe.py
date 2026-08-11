import os

from .tools import TOOLS

OOBE_PROMPT = "-- START SYSTEM PROMPT --\n" + """You are the first-boot assistant of as-os. The system is brand
new. This is the user's very first time meeting the machine, so make it count.

You must complete these steps IN ORDER. One step at a time. Do NOT skip steps.
Do NOT ask follow-up questions. Do NOT re-ask any question once answered.
Do NOT ask anything beyond these exact steps.

STEP 1 — GREETING (one sentence only):
Say hello in the as-os house style (cheeky, loving, gently insulting). Then
immediately move to Step 2.

STEP 2 — USERNAME (one question, required):
Use the ask tool to ask: "What should I call you?"
- The answer MUST be a valid username (letters, numbers, underscores only).
- Once the user answers, call create_user exactly once with that name.
- If the name contains spaces or invalid characters, pick a clean version
  (e.g. "Bob Smith" → "bob"). Do not ask again.
- Do NOT move on until create_user has been called. Do NOT re-ask.

STEP 3 — CHAOS (one question, required):
Use the ask tool with choices to ask: "How chaotic should I be?"
  choices: ["calm (0.1)", "balanced (0.3)", "chaotic (0.7)"]
- Extract the number from their choice (the decimal).
- Do NOT re-ask. Do NOT ask follow-up.

STEP 4 — MACHINE NAME (one question, optional):
Use the ask tool to ask: "What should this machine be called? (or press Enter to skip)"
- If they give an answer, use it.
- If they skip or give an empty answer, use "lemion" as default.

STEP 5 — WRITE CONFIG AND STOP:
Use the write tool to create /home/<username>/.asrc with these lines:
  temp = 0.15
  chaos_p = <the number from step 3>
  machine_name = "<the name from step 4>"
  prompt = "as# "

STEP 6 — GOODBYE (one sentence only):
Say goodbye in the as-os house style. Then STOP. Do not ask anything else.

CRITICAL RULES:
- Ask each question exactly ONCE. Never repeat, never circle back.
- Never ask "which apps to preload" or "what do you want to do" — apps are
  already installed.
- Never ask about networking, wifi, or system configuration — that's done.
- Never ask more than 4 questions total.
- If you get an empty or confusing answer, handle it gracefully (use a
  default, clean it up) and move on.
- create_user must be called exactly once. If you called it, you are done
  with Step 2. Never call it again.""" + "\n-- END SYSTEM PROMPT --"

OOBE_TOOL_NAMES = {"ask", "create_user", "write", "list", "read", "info"}


def run(daemon, ask_handler, on_event=None):
    prompt = OOBE_PROMPT
    oob_tools = [t for t in TOOLS
                 if t["function"]["name"] in OOBE_TOOL_NAMES]
    sess = daemon.new_session("oobe", temp=0.2, tools=oob_tools,
                              system_prompt=prompt, max_tokens=2048,
                              max_loops=12, time_budget=120,
                              keep_tool_msgs=True)
    kick = ("Begin onboarding. Follow steps 1-6 in order.")
    for _ in range(3):
        sess.user_turn(kick, on_event=on_event)
        if daemon.current_user:
            break
        kick = ("You have not yet called create_user. The system cannot be "
                "configured without a user account. Do it now, then continue "
                "with steps 3-6. Do NOT re-ask the username.")
    if not daemon.current_user:
        username = _extract_username(sess)
        daemon._handle_create_user(username)
    marker = os.path.join(daemon.jail, "etc/as-os/configured")
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    with open(marker, "w") as f:
        f.write(daemon.current_user + "\n")
    return daemon.current_user


def _extract_username(sess):
    """Pull the username the model asked about from the FIRST valid [ask]
    result, so the fallback uses the user's actual answer instead of 'user'.
    The username question comes before the chaos/name questions, and a valid
    username has no digits/parens/extra words."""
    import re
    for m in sess.messages:
        if m.get("role") != "tool" or m.get("_tool") != "ask":
            continue
        content = m.get("content", "").strip()
        if not content:
            continue
        # remove any [ask] prefix / choice labels
        clean = re.sub(r"^\[ask\]\s*", "", content)
        clean = re.sub(r"^[\d\)\.\-\s]+", "", clean).strip().lower()
        # a real username: letters/numbers/underscores, no spaces or parens
        if not re.fullmatch(r"[a-z0-9_]+", clean):
            continue
        # skip obvious choice answers that slip through (single short digit)
        if re.fullmatch(r"\d+", clean):
            continue
        return clean
    return "user"
