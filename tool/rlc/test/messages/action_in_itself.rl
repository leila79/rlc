# RUN: rlc %s -o %t -i %stdlib --print-ir-on-failure=false 2>&1 --expect-fail --shared | FileCheck %s

# CHECK: 5:1: error: Action type contains itself, this in not allowed

act action() -> Asd:
    act inner(frm Asd x)
