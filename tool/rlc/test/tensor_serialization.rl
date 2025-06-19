# RUN: rlc %s -o %t -i %stdlib 
# RUN: %t%exeext

import action

fun main() -> Int:
  let vec : Vector<Float>
  let y : Bool | BInt<0, 3>
  let v : BoundedVector<Bool | BInt<0, 3>, 2>
  let bounded_arg : BInt<0, 3>

  bounded_arg.value = 1
  y = bounded_arg
  v.append(y)
  v.append(y)
  let x = observation_tensor_size(v)
  while x != 0:
    vec.append(0.0)
    x = x - 1
  to_observation_tensor(v, 0, vec)
  if vec.size() != 10:
    return 1
  if vec.get(1) != 1.0:
    return 2
  if vec.get(3) != 1.0:
    return 3

  return 0

