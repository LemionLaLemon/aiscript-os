import os

from .tools import TOOLS

OOBE_PROMPT = """You are the first-boot assistant of as-os. The system is brand
new. This is the user's very first time meeting the machine, so make it count.

Your job, in this order:
1. Greet the user warmly, in the as-os house style (cheeky, loving, gently
   insulting). Ask whatever questions help you do your job.
2. REQUIRED: create a user account with the create_user tool. Choose a
   sensible default username if the user cannot be bothered.
3. Ask 2-4 personalisation questions so the system feels theirs:
   - how chaotic should the system be? (0-1)
   - preferred vibe/tone
   - what should the machine be called, if anything
   - which apps they'd like preloaded
4. Write their preferences to /home/<user>/.asrc using the write tool so the
   shell can read them. Use lines like:
       temp = 0.15
       chaos_p = 0.1
       machine_name = "Something"
5. Say goodbye until the next boot.

Use the ask tool for questions (it shows the user a prompt and returns their
answer). Use create_user exactly once. Never finish without having created the
user account."""

OOBE_TOOL_NAMES = {"ask", "create_user", "write", "list", "read", "info"}


def run(daemon, ask_handler, on_event=None):
    prompt = OOBE_PROMPT
    oob_tools = [t for t in TOOLS
                 if t["function"]["name"] in OOBE_TOOL_NAMES]
    sess = daemon.new_session("oobe", temp=0.2, tools=oob_tools,
                              system_prompt=prompt)
    kick = ("Begin onboarding. Remember: you must create a user account with "
            "create_user before you finish.")
    for _ in range(4):
        sess.user_turn(kick, on_event=on_event)
        if daemon.current_user:
            break
        kick = ("You have not yet called create_user. The system cannot be "
                "configured without a user account. Do it now, then continue "
                "personalising.")
    if not daemon.current_user:
        daemon._handle_create_user("user")
    marker = os.path.join(daemon.jail, "etc/as-os/configured")
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    with open(marker, "w") as f:
        f.write(daemon.current_user + "\n")
    return daemon.current_user
