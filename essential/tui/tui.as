# tui.as — the ascOS terminal UI toolkit (ComputerCraft term minimum).
#
# Import in any TUI app:
#   from "/packages/tui/tui.as" import tui
#
# Every function below is a WISH, not code: when your program calls one,
# interpret it — carry out its body step by step using the term tool.
# State (fields, values, focus index, cursor) lives in YOUR program's
# variables; the functions tell you what to do to the screen for it.
#
# ── event loop every TUI app follows ─────────────────────────────────
#   compose the complete screen as text rows, then draw it in ONE call:
#     term(action="render", lines=rows, x=cursor_x, y=cursor_y)
#   then loop forever:
#     key = term(action="pull", filter="any", timeout=30)
#     interpret handleKey(key) against your state
#     if the app should exit, break the loop and return your report
#   every state change that is visible MUST redraw in one render call — do not
#   leave stale text on screen.
#
# colors: 0 white 1 orange 2 magenta 3 lightBlue 4 yellow 5 lime
#   6 pink 7 gray 8 lightGray 9 cyan 10 purple 11 blue 12 brown
#   13 green 14 red 15 black

function drawFrame(title)
  clear the whole screen (term action "clear") with your background color.
  draw a single-line box around the ENTIRE screen using ASCII:
    corners +, horizontal -, vertical |.
  if a title is given, write it into the top border as "+- title ---+",
  starting at column 3, never overwriting the corners.
end

function drawBox(x, y, w, h, title)
  clear the w x h area at (x, y) with spaces, then draw a box:
    corners +, top/bottom -, sides |.
  if a title is given, write it inside the top border after "+- ".
end

function label(x, y, text, fg)
  set the foreground to fg (or keep the current color if none given),
  then write text at (x, y). do not draw a box around it.
end

function textInput(name, x, y, w, value, focused)
  draw the field on row y starting at column x:
    a field is [VALUE] where VALUE is the value left-padded/truncated
    to exactly w characters (use spaces).
  if focused: make it stand out (swap fg/bg or use a bright color),
    and put the cursor right after the last character of the value
    (x + 1 + length(value), y).
  if not focused: dim colors, and do not move the cursor there.
  remember this field as name = value in your program state.
end

function button(label, x, y, active)
  draw < label > at (x, y).
  if active/focused: invert the colors (swap fg and bg) for the whole
  button so it looks pressed.
end

function menu(options, x, y, selected)
  for each option at index i (starting at 0):
    if i == selected write "> option_text" else write "  option_text"
  at row y + i, column x. the > marks the selection.
end

function message(text)
  write text on the LAST row of the screen, clearing that row first
  (set_cursor(1, screen_height), clear_line, then write). this is the
  status line — it must never wrap onto other rows.
end

function status(right)
  like message, but right-align: pad with spaces so the text ends at
  the last column of the last row.
end

# ── focus movement (the tab logic) ───────────────────────────────────

function focusNext(fields, current)
  # fields is your ordered list of field names; returns the new index
  return (current + 1) modulo the length of fields, wrapping to 0.
  set the focused field to fields[that index] and redraw.
end

function focusPrev(fields, current)
  return (current - 1 + length of fields) modulo the length of fields,
  so moving back from the first field wraps to the LAST field.
  set the focused field to fields[that index] and redraw.
end

# ── key dispatch ─────────────────────────────────────────────────────

function handleKey(key, state)
  interpret the key against your state, then redraw what changed:
    "tab"       -> focusNext over your fields
    "backtab"   -> focusPrev over your fields
    "enter"     -> submit: validate the focused field(s), run the
                   action this form is for, clear the status line
    "backspace" -> remove the last character of the focused field
    "up"        -> previous item in a menu/list, or up one line
    "down"      -> next item in a menu/list, or down one line
    "left"      -> move the edit cursor left inside the focused field
    "right"     -> move the edit cursor right inside the focused field
    "escape"    -> cancel/close (if the app can close, exit the loop
                   and return a report like "cancelled")
    {"event":"char","char":"c"} -> append the character to the focused
                   field at the edit cursor, then move the cursor right
    any other key -> ignore it, but do not crash
  NEVER call pull twice for one keypress. one pull = one key.
end

function render(state)
  compose everything from state into a list of complete screen rows:
    1. drawFrame(title)
    2. every widget (labels, inputs, buttons, menu) in row order
    3. the status/message line last
    4. place the cursor on the focused widget (textInput does this)
  Send the rows with ONE term(action="render", lines=rows, x=cursor_x,
  y=cursor_y) call. A full redraw is cheap. Never issue dozens of
  set_cursor/write calls for one frame.
end
