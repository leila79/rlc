# RUN: rlc %s -i %stdlib -o %t --sanitize
# RUN: %t%exeext
import collections.vector

act asd() -> Move:
  let vector : Vector<Int>
  act inner()

fun main() -> Int:
  asd()
  return 0

