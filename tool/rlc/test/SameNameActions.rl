# RUN: rlc %s -o %t -i %stdlib 
# RUN: %t%exeext

act action() -> Action:
  frm result = 5

  act first(Int x)
  result = x

  act first(Int x)
  result = x + x

act outer() -> Outer:
  subaction* frame1 = action()
  subaction* frame2 = action()

fun main() -> Int:
  let frame = outer()
  frame.first(1)
  frame.first(2)
  frame.first(4)
  frame.first(8)
  if !frame.is_done():
    return -1
  return frame.frame2.result - 16

