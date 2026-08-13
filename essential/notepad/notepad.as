# notepad: an interactive text editor
# (aiscript is interpreted by an AI, so this is a wish, not syntax)

open the file given as the first argument (default ~/Documents/notes.txt).
show me the current contents with line numbers.

then loop:
  ask the user what they want to do:
    "insert" — ask which line and what text, then insert it
    "replace" — ask which line and what the new text should be
    "delete" — ask which line to remove
    "show" — re-display the buffer with line numbers
    "done" — save and stop

apply each change immediately using the file tools, then re-show the buffer.
repeat until the user says "done".
