# RUN: rlc %s -o %t -i %stdlib 
# RUN: %t%exeext

import serialization.to_byte_vector

cls Struct2:
  Vector<Int> values

cls Struct1:
  Int asd
  Bool x
  Float[2] ras
  Vector<Struct2> inners

fun eq(Struct2 lhs, Struct2 rhs) -> Bool:
  let index = 0
  if lhs.values.size() != rhs.values.size():
    return false
  while index < lhs.values.size():
    if lhs.values.get(index) != rhs.values.get(index):
      return false
    index = index + 1
  return true

fun eq(Vector<Struct2> lhs, Vector<Struct2> rhs) -> Bool:
  let index = 0
  if lhs.size() != rhs.size():
    return false
  while index < lhs.size():
    if !eq(lhs.get(index), rhs.get(index)):
      return false
    index = index + 1
  return true

fun eq(Struct1 lhs, Struct1 rhs) -> Bool:
  if lhs.asd != rhs.asd:
    return false
  if lhs.ras[0] != rhs.ras[0]:
    return false
  if lhs.ras[1] != rhs.ras[1]:
    return false
  if lhs.x != rhs.x:
    return false
  return eq(lhs.inners, rhs.inners)

fun main() -> Int:
  let var : Struct1
  var.asd = 2
  var.x = true
  var.ras[1] = 10.0
  var.ras[0] = 2.0
  let transformed = as_byte_vector(var)
  let result : Struct1
  from_byte_vector(result, transformed)
  return int(eq(var, result)) - 1

