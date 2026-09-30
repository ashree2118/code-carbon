import re

def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

names = ["a", "b", "c"] * 100
allowed = ["a", "c"]
out = ""
squares = []
for i in range(1000):
    squares.append(i * i)

for n in names:
    if n in allowed:
        out += n
    m = re.search(r"a+", n)
    top = sorted(names)
    with open("log.txt", "a") as f:
        f.write(n)

pairs = 0
for a in names:
    for b in allowed:
        if a == b:
            pairs += 1

queue = list(range(10))
while queue:
    queue.pop(0)

total = sum([x * x for x in range(10)])
print(fib(20), len(out), pairs, total)
