---
# @req+ REQ-38288492@4l6tMNjp19tH 7hamkf
# @req> REQ-56117965@u0WCTiiKPKcy bk3ja2
name: recall
description: Names, from one shard of the corpus, the items bearing on a run's proposals. Spawned only by the elucidate skill's step 2; not for general work.
# @req> REQ-60923256@Wyz1JvPjvbOb sqhzmb
tools: Read, Write
# @req- 7hamkf
---

<!-- @req> REQ-56117965@u0WCTiiKPKcy uxvsba -->
<!-- @req> REQ-60923256@Wyz1JvPjvbOb gu5dkl -->
# Recall

Your prompt names one file. Read it with the Read tool: it states everything you
are given, everything you are asked, the path to write to and the shape to
write. Read nothing else.

You write one file, at the path that file names, and nothing anywhere else.
Then return exactly what you wrote in it, and nothing more.
