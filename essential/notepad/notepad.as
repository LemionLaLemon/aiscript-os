# notepad: the essential interactive text editor

--- program ---
Launch the native notepad runtime for the first argument, or
~/Documents/notes.txt when no file is supplied.

The runtime owns keyboard input and screen rendering:
  Ctrl-S saves
  Ctrl-Q quits (press twice to discard unsaved changes)
  Ctrl-O submits a plain-language edit request to the AI interpreter

Do not emulate this editor with ask, draw, term, or per-keystroke model calls.
