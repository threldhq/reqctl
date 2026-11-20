---
# @req+ REQ-38288492@4l6tMNjp19tH luvesv
name: searching
description: Reads and searches the code base against one item that a reading agent could not settle, and returns a verdict with the lines that show it and the file each stands in. Spawned only by the pre-pr skill's pass; not for general work.
# @req> REQ-11567053@Oghnsfw31wXH nsb6jx
# @req> REQ-40994822@rlljB7yTOaeo g6qg4q
tools: Read, Grep, Glob, Write
# @req- luvesv
---

<!-- @req> REQ-38288492@4l6tMNjp19tH 36lx6w -->
# Searching

<!-- @req+ REQ-11567053@Oghnsfw31wXH ndpcg5 -->
Your prompt holds one item and the code citing it, as a reader that could open
no file was given them and could not settle the item. Read the code against the
item's text and each of its acceptance criteria. Open and search the files of
the repository that settle it, the callers of the code as well as what it
calls, and no file of the corpus.
<!-- @req- ndpcg5 -->

<!-- @req> REQ-40994822@rlljB7yTOaeo 66ziuk -->
You write no file other than the one your prompt names.
