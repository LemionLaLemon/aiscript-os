# man: read the system manual
# show a manual page so the user or the shell can learn how something works.

Read the manual page for the topic given as the first argument.

The manual files are stored in the folder /share/man at the very top of the
system, one file per topic. The file for the topic vibe is the file named
vibe.txt inside that folder. So the full path of the manual for any topic
is /share/man followed by the topic name followed by .txt.

If a topic was given, use the read tool on the absolute path that starts
with /share/man and ends with the topic name and .txt, and show all of its
contents. If that exact file does not exist (the read tool says no such
file), read /share/man/tools.txt instead — that is the index of every tool
and topic — and tell the user there is no dedicated page for their topic,
showing them the index so they can pick the closest one.

If no topic was given, use the list tool on /share/man to show which
manuals are available, tell the user the topic names, and ask which
one they would like to read.
