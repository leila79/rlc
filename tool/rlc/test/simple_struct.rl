# RUN: rlc %s -o %t -i %stdlib 
# RUN: %t%exeext

cls Asd:
  Int rsd
  Int tasd

fun main() -> Int:
  return 0

fun some_function(Asd field) -> Int:
  return 1

