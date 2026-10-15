"""Leiden community detection, ported line by line from the Diarios Explorer
(explorer_src/worker/35a_engine__leiden.js) so that the MCP and the explorer give the same
communities for the same graph and seed (checked by tests/test_networks.py against the JS).

Leiden (Traag, Waltman & van Eck 2019, Scientific Reports 9:5233) on an undirected weighted graph,
maximising modularity with resolution γ (Reichardt-Bornholdt). Implementation choices, recorded with
every result so it can be reproduced:
  - node visiting order shuffled with a fixed seed (mulberry32): same seed, same result;
  - greedy refinement (θ → 0): merge with the subset of largest gain instead of sampling it;
  - the whole algorithm is iterated from the previous partition until quality stops improving;
  - final safety net: every community is split into its connected components.
"""
from __future__ import annotations

import math

EPS = 1e-12
_M = 0xFFFFFFFF


# ── graph in CSR form ─────────────────────────────────────────────────────────

def _from_edges(n: int, edges) -> dict:
    """CSR graph from [u, v, w] edges (u ≠ v; repeated edges are summed; weights ≤ 0 ignored)."""
    degree = [0] * n
    for u, v, w in edges:
        if u != v and w > 0:
            degree[u] += 1
            degree[v] += 1
    off = [0] * (n + 1)
    for i in range(n):
        off[i + 1] = off[i] + degree[i]
    adj = [0] * off[n]
    wt = [0.0] * off[n]
    pos = off[:n]
    for u, v, w in edges:
        if u == v or not (w > 0):
            continue
        adj[pos[u]] = v
        wt[pos[u]] = float(w)
        pos[u] += 1
        adj[pos[v]] = u
        wt[pos[v]] = float(w)
        pos[v] += 1
    return _compact({"n": n, "off": off, "adj": adj, "wt": wt, "auto": [0.0] * n})


def _compact(g: dict) -> dict:
    """Sum repeated neighbours and compute degrees (degree = Σ weights to others + 2 · self-loop)."""
    n, off, adj, wt, auto = g["n"], g["off"], g["adj"], g["wt"], g["auto"]
    off2 = [0] * (n + 1)
    adj2, wt2 = [], []
    mark = [-1] * n
    slot = [0] * n
    for v in range(n):
        start = len(adj2)
        for e in range(off[v], off[v + 1]):
            u = adj[e]
            if mark[u] == v:
                wt2[slot[u]] += wt[e]
                continue
            mark[u] = v
            slot[u] = len(adj2)
            adj2.append(u)
            wt2.append(wt[e])
        off2[v + 1] = off2[v] + (len(adj2) - start)
    degree = [0.0] * n
    m2 = 0.0
    for v in range(n):
        s = 2 * auto[v]
        for e in range(off2[v], off2[v + 1]):
            s += wt2[e]
        degree[v] = s
        m2 += s
    return {"n": n, "off": off2, "adj": adj2, "wt": wt2, "auto": auto, "degree": degree, "m2": m2}


# ── seeded randomness (mulberry32, bit for bit as in JavaScript) ──────────────

def mulberry32(seed: int):
    a = seed & _M

    def rand() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & _M
        t = a
        t = ((t ^ (t >> 15)) * (t | 1)) & _M
        t = (t ^ ((t + (((t ^ (t >> 7)) * (t | 61)) & _M)) & _M)) & _M
        return ((t ^ (t >> 14)) & _M) / 4294967296
    return rand


def _shuffled(n: int, rand) -> list[int]:
    o = list(range(n))
    for i in range(n - 1, 0, -1):
        j = math.floor(rand() * (i + 1))
        o[i], o[j] = o[j], o[i]
    return o


# ── quality ───────────────────────────────────────────────────────────────────

def _quality(g: dict, com, gamma: float) -> float:
    """Modularity with resolution γ: Σ_c [ L_c/m − γ (K_c/2m)² ]."""
    n, off, adj, wt, auto, degree, m2 = g["n"], g["off"], g["adj"], g["wt"], g["auto"], g["degree"], g["m2"]
    if not (m2 > 0):
        return 0.0
    m = m2 / 2
    L: dict = {}
    K: dict = {}
    for v in range(n):
        c = com[v]
        K[c] = K.get(c, 0.0) + degree[v]
        internal = auto[v]
        for e in range(off[v], off[v + 1]):
            if com[adj[e]] == c and adj[e] > v:
                internal += wt[e]
        L[c] = L.get(c, 0.0) + internal
    q = 0.0
    for c, k in K.items():
        q += L.get(c, 0.0) / m - gamma * (k / m2) * (k / m2)
    return q


# ── Leiden phases ─────────────────────────────────────────────────────────────

def _move_nodes(g: dict, P: list[int], gamma: float, order: list[int]) -> list[int]:
    """Fast local moving (queue): each node goes to the neighbouring community of largest gain, or to an empty one."""
    n, off, adj, wt, degree, m2 = g["n"], g["off"], g["adj"], g["wt"], g["degree"], g["m2"]
    Ktot = [0.0] * n
    size = [0] * n
    for v in range(n):
        Ktot[P[v]] += degree[v]
        size[P[v]] += 1
    empty = [c for c in range(n - 1, -1, -1) if size[c] == 0]
    queue = [0] * n
    in_queue = [False] * n
    head, length = 0, n
    for i in range(n):
        queue[i] = order[i]
        in_queue[order[i]] = True
    weight = [0.0] * n
    touched: list[int] = []
    while length > 0:
        v = queue[head]
        head = (head + 1) % n
        length -= 1
        in_queue[v] = False
        cv, kv = P[v], degree[v]
        for e in range(off[v], off[v + 1]):
            c = P[adj[e]]
            if weight[c] == 0:
                touched.append(c)
            weight[c] += wt[e]
        Ktot[cv] -= kv
        size[cv] -= 1
        best, best_gain = cv, weight[cv] - gamma * Ktot[cv] * kv / m2
        for c in touched:
            if c == cv:
                continue
            gain = weight[c] - gamma * Ktot[c] * kv / m2
            if gain > best_gain + EPS:
                best, best_gain = c, gain
        # an empty community has gain 0; if v was alone, staying already is that
        if size[cv] > 0 and 0 > best_gain + EPS and empty:
            best = empty.pop()
        for c in touched:
            weight[c] = 0.0
        touched.clear()
        P[v] = best
        Ktot[best] += kv
        size[best] += 1
        if size[cv] == 0 and cv != best:
            empty.append(cv)
        if best != cv:
            for e in range(off[v], off[v + 1]):
                u = adj[e]
                if P[u] != best and not in_queue[u]:
                    queue[(head + length) % n] = u
                    length += 1
                    in_queue[u] = True
    return P


def _refine(g: dict, P: list[int], gamma: float, order: list[int]) -> list[int]:
    """Within each community S of P, start from singletons and merge a node well connected to S only with a
    subset also well connected to S, picking the largest positive gain.
    Well connected (modularity with resolution γ): E(X, S − X) ≥ γ · K_X · (K_S − K_X) / 2m."""
    n, off, adj, wt, degree, m2 = g["n"], g["off"], g["adj"], g["wt"], g["degree"], g["m2"]
    R = list(range(n))
    Kr = list(degree)
    sizeR = [1] * n
    ext = [0.0] * n
    KS = [0.0] * n
    for v in range(n):
        KS[P[v]] += degree[v]
    for v in range(n):
        s = 0.0
        for e in range(off[v], off[v + 1]):
            if P[adj[e]] == P[v]:
                s += wt[e]
        ext[v] = s
    weight = [0.0] * n
    touched: list[int] = []
    for i in range(n):
        v = order[i]
        if sizeR[R[v]] != 1:                                   # v is no longer alone in the refined partition
            continue
        S = P[v]
        if ext[v] < gamma * degree[v] * (KS[S] - degree[v]) / m2 - EPS:   # v badly connected to S
            continue
        for e in range(off[v], off[v + 1]):
            u = adj[e]
            if P[u] != S:
                continue
            c = R[u]
            if c == R[v]:
                continue
            if weight[c] == 0:
                touched.append(c)
            weight[c] += wt[e]
        best, best_gain = -1, 0.0
        for c in touched:
            if ext[c] < gamma * Kr[c] * (KS[S] - Kr[c]) / m2 - EPS:    # subset badly connected
                continue
            gain = weight[c] - gamma * Kr[c] * degree[v] / m2
            if gain > best_gain + EPS:                         # greedy: only merges with positive gain
                best, best_gain = c, gain
        if best >= 0:
            r0 = R[v]
            ext[best] = ext[best] + ext[r0] - 2 * weight[best]
            Kr[best] += degree[v]
            sizeR[best] += 1
            Kr[r0] = 0.0
            sizeR[r0] = 0
            ext[r0] = 0.0
            R[v] = best
        for c in touched:
            weight[c] = 0.0
        touched.clear()
    return R


def _aggregate(g: dict, R: list[int]) -> tuple[dict, list[int]]:
    """Aggregate network from the refined partition R (compacted ids): nodes = subsets of R."""
    n, off, adj, wt, auto = g["n"], g["off"], g["adj"], g["wt"], g["auto"]
    ident = [-1] * n
    k = 0
    new = [0] * n
    for v in range(n):
        if ident[R[v]] < 0:
            ident[R[v]] = k
            k += 1
        new[v] = ident[R[v]]
    autoN = [0.0] * k
    edges = []
    for v in range(n):
        a = new[v]
        autoN[a] += auto[v]
        for e in range(off[v], off[v + 1]):
            u = adj[e]
            if u < v:                                          # each edge once
                continue
            b = new[u]
            if a == b:
                autoN[a] += wt[e]
            else:
                edges.append([a, b, wt[e]])
    gr = _from_edges(k, edges)
    for i in range(k):
        gr["auto"][i] = autoN[i]
    g2 = _compact({"n": k, "off": gr["off"], "adj": gr["adj"], "wt": gr["wt"], "auto": gr["auto"]})
    return g2, new


def _split_components(g: dict, com) -> list[int]:
    """Split every community into its connected components (in the original graph)."""
    n, off, adj = g["n"], g["off"], g["adj"]
    out = [-1] * n
    k = 0
    stack: list[int] = []
    for s in range(n):
        if out[s] >= 0:
            continue
        out[s] = k
        stack.append(s)
        while stack:
            v = stack.pop()
            for e in range(off[v], off[v + 1]):
                u = adj[e]
                if out[u] < 0 and com[u] == com[s]:
                    out[u] = k
                    stack.append(u)
        k += 1
    return out


def _compact_ids(com) -> tuple[list[int], int]:
    mapping: dict = {}
    out = [0] * len(com)
    for i, c in enumerate(com):
        if c not in mapping:
            mapping[c] = len(mapping)
        out[i] = mapping[c]
    return out, len(mapping)


def _one_pass(g0: dict, initial, gamma: float, rand) -> list[int]:
    """One full Leiden pass starting from the partition `initial` (ids 0..n-1) of the original graph."""
    g = g0
    P = list(initial)
    node_of = list(range(g0["n"]))
    for _level in range(64):
        P = _move_nodes(g, P, gamma, _shuffled(g["n"], rand))
        P, nc = _compact_ids(P)
        if nc == g["n"]:                                       # every node is its own community
            break
        R = _refine(g, P, gamma, _shuffled(g["n"], rand))
        gA, new = _aggregate(g, R)
        if gA["n"] == g["n"]:                                  # refinement merged nothing: safe stop
            break
        PA = [0] * gA["n"]
        for v in range(g["n"]):
            PA[new[v]] = P[v]                                  # the aggregate starts from the NON-refined partition
        node_of = [new[x] for x in node_of]
        g, P = gA, PA
    return [P[node_of[i]] for i in range(g0["n"])]


# ── API ───────────────────────────────────────────────────────────────────────

def communities(n: int, edges, resolution: float = 1.0, seed: int = 1, max_iterations: int = 10) -> dict:
    """Communities of an undirected weighted graph with n nodes and [u, v, w] edges."""
    gamma = float(resolution)
    seed = int(seed) & _M
    g = _from_edges(n, edges)
    rand = mulberry32(seed or 1)
    com = list(range(n))
    q = _quality(g, com, gamma)
    it = 0
    if not (g["m2"] > 0):
        # no edge with positive weight: in JavaScript every gain is 0/0 = NaN, no node moves, and the loop stops
        # after one pass; the result is every node on its own
        it = min(1, max_iterations)
    while g["m2"] > 0 and it < max_iterations:
        new = _compact_ids(_one_pass(g, com, gamma, rand))[0]
        qn = _quality(g, new, gamma)
        if qn <= q + 1e-10 and it > 0:
            break
        com, q = new, qn
        it += 1
    final, nc = _compact_ids(_split_components(g, com))
    return {"community": final, "n_communities": nc, "quality": _quality(g, final, gamma),
            "modularity": _quality(g, final, 1.0), "iterations": it,
            "parameters": {"algorithm": "Leiden", "quality_function": "modularity (RB)", "resolution": gamma,
                           "seed": seed, "refinement": "greedy (θ → 0)", "max_iterations": max_iterations,
                           "implementation": "port of the Diarios Explorer's engine/leiden.js"}}


def modularity(n: int, edges, community, resolution: float = 1.0) -> float:
    return _quality(_from_edges(n, edges), community, resolution)
